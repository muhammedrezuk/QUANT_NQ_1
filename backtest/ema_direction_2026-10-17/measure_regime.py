# -*- coding: utf-8 -*-
"""Attempt 2 (declared in the attempts ledger before running): the owner's law -- "the averages work in a trend and fail in
accumulation and chop". Can the moment be split, from the past only, into trend and not-trend, and do the averages
(5 over 10 over 50) know the direction inside the trend part?

2024-10-01 .. 2025-09-30, one year (the owner: "why every year -- one year is enough"); the holdout stays untouched.
USTEC, eight frames (the month has too little history). Three splits, each computed from the frame's own closed bars only:
  A "ordered": the averages have read the same way for at least 10 bars in a row;
  B "efficiency": |close - close 20 bars ago| / sum of the 20 absolute moves -- top third = trend, bottom third = chop
    (the thirds are cut per frame on the year before, 2023-10 .. 2024-09);
  C "dow": the Dow trend of the same frame (shared.dow_theory rules, one pass) is rising or falling.
Asks at every quarter-hour close 09:45-15:45 NY on trading days. Right = the price went the averages' way 5 bars of the
frame later, and at the 16:00 close. Beside each rate: how often the market rose in the same moments, and in how many of
the 4 quarters of the year the rate beat it.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from array import array
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measure_ema as me  # noqa: E402
from shared import dow_theory as dt  # noqa: E402
from shared import market_clock  # noqa: E402

m1 = me.m1
FROM, TO = date(2024, 10, 1), date(2025, 9, 30)
THIRDS_FROM, THIRDS_TO = date(2023, 10, 1), date(2024, 9, 30)      # the year before: the thirds never see the measured year
LOAD_FROM = date(2023, 6, 1)
OUT_NAME = "result_regime.json"
if len(sys.argv) == 6:                                   # the same measure on another year: from to thirds_from thirds_to out
    FROM, TO, THIRDS_FROM, THIRDS_TO = (date.fromisoformat(x) for x in sys.argv[1:5])
    LOAD_FROM, OUT_NAME = date(THIRDS_FROM.year - 1, THIRDS_FROM.month, 1), sys.argv[5]
FRAMES = (("1m", "M1", 60), ("5m", "M5", 300), ("15m", "M15", 900), ("30m", "M30", 1800), ("1h", "H1", 3600),
          ("4h", "H4", 14400), ("1d", "D1", 86400), ("1w", "W1", None))
ORDERED_MIN = 10
ER_WINDOW = 20
AHEAD = 5
RISING, FALLING, NONE = me.RISING, me.FALLING, me.NONE


def load(period: str, until_s: float, since_s: float = 0.0) -> tuple[array, array]:
    con = sqlite3.connect("file:%s?mode=ro" % m1.HISTORY_DB, uri=True)
    starts, closes = array("d"), array("d")
    for s, c in con.execute("SELECT period_start, close FROM candles_history WHERE symbol=? AND period=? AND period_start<? "
                            "AND period_start>=? ORDER BY period_start", (m1.SYMBOL, period, until_s, since_s)):
        starts.append(float(s))
        closes.append(float(c))
    con.close()
    return starts, closes


def ema_marks(closes: array) -> list[str]:
    return me.ema_states([(0, 0, 0, 0, c) for c in closes])


def run_lengths(marks: list[str]) -> array:
    out, run = array("i"), 0
    for i, m in enumerate(marks):
        run = run + 1 if i and m != NONE and m == marks[i - 1] else (1 if m != NONE else 0)
        out.append(run)
    return out


def efficiency(closes: array) -> array:
    out = array("d", [-1.0] * len(closes))
    moves = [abs(closes[i] - closes[i - 1]) if i else 0.0 for i in range(len(closes))]
    total = 0.0
    for i in range(len(closes)):
        total += moves[i]
        if i > ER_WINDOW:
            total -= moves[i - ER_WINDOW]
        if i >= ER_WINDOW and total > 0:
            out[i] = abs(closes[i] - closes[i - ER_WINDOW]) / total
    return out


def dow_marks(closes: array, starts: array) -> list[str]:
    """The Dow trend at every bar in one pass, with shared.dow_theory's rules (closes, span 2)."""
    span, pivots, trend, out = dt.PIVOT_SPAN, [], NONE, []
    cl = list(closes)
    for i in range(len(cl)):
        j, fresh = i - span, False
        if j >= span:
            kind = dt._pivot_at(cl, j, span)
            if kind:
                fresh = dt._add_pivot(pivots, (j, kind, cl[j], starts[j]))
        lows, highs = dt._last(pivots, dt.LOW, 1), dt._last(pivots, dt.HIGH, 1)
        if trend == RISING and lows and cl[i] < lows[0][2]:
            trend = NONE
        elif trend == FALLING and highs and cl[i] > highs[0][2]:
            trend = NONE
        if fresh:
            shape = dt.structure(pivots)[0]
            if shape == dt.HH_HL and trend != RISING and lows and cl[i] >= lows[0][2]:
                trend = RISING
            elif shape == dt.LH_LL and trend != FALLING and highs and cl[i] <= highs[0][2]:
                trend = FALLING
        out.append(trend)
        if len(pivots) > 8:
            del pivots[:-8]
    return out


def main() -> None:
    began = time.time()
    until = datetime(TO.year, TO.month, TO.day, tzinfo=m1.NY).timestamp() + 40 * 86400
    m15s, m15c = load("M15", until)
    sessions: dict[date, dict[int, float]] = defaultdict(dict)
    for s, c in zip(m15s, m15c):
        d, minute = m1.ny_minute(s + 900)
        sessions[d][minute] = c
    asks = []
    for s, c in zip(m15s, m15c):
        t = s + 900
        d, minute = m1.ny_minute(t)
        if not (FROM <= d <= TO) or not m1.FIRST_ASK <= minute <= m1.LAST_ASK or d.weekday() >= 5:
            continue
        inside = sum(1 for m in sessions[d] if m1.FIRST_ASK <= m <= m1.SESSION_CLOSE)
        noon = datetime(d.year, d.month, d.day, 12, tzinfo=m1.NY).timestamp()
        if inside < m1.MIN_SESSION_BARS or market_clock.no_trade_day(noon):
            continue
        asks.append((t, d, minute, c))
    t_from = datetime(THIRDS_FROM.year, THIRDS_FROM.month, THIRDS_FROM.day, tzinfo=m1.NY).timestamp()
    t_to = datetime(THIRDS_TO.year, THIRDS_TO.month, THIRDS_TO.day, tzinfo=m1.NY).timestamp() + 86400
    since = datetime(LOAD_FROM.year, LOAD_FROM.month, LOAD_FROM.day, tzinfo=m1.NY).timestamp()
    out = {"asks": len(asks), "days": len({a[1] for a in asks}), "frames": {}}
    for name, period, length in FRAMES:
        starts, closes = load(period, until, since if period not in ("D1", "W1") else 0.0)
        ends = [starts[i] + length if length else (starts[i + 1] if i + 1 < len(starts) else float("inf"))
                for i in range(len(starts))]
        marks, runs, er, dow = ema_marks(closes), None, efficiency(closes), dow_marks(closes, starts)
        runs = run_lengths(marks)
        sample = sorted(er[i] for i in range(len(er)) if er[i] >= 0 and t_from <= starts[i] < t_to)
        low_cut, high_cut = sample[len(sample) // 3], sample[2 * len(sample) // 3]
        cells = defaultdict(lambda: {"right": 0, "wrong": 0, "rose": 0, "fell": 0, "years": defaultdict(lambda: [0, 0, 0, 0])})
        i = 0
        for t, d, minute, price in asks:
            while i < len(starts) and ends[i] <= t:
                i += 1
            k = i - 1
            if k < 0 or marks[k] == NONE:
                continue
            reading = marks[k]
            splits = {"all": "all",
                      "ordered": "trend" if runs[k] >= ORDERED_MIN else "not",
                      "efficiency": "trend" if er[k] >= high_cut else "chop" if 0 <= er[k] <= low_cut else "middle",
                      "dow": "trend" if dow[k] != NONE else "not",
                      "dow_same_way": "same" if dow[k] == reading else "other"}
            outcomes = {}
            if k + AHEAD < len(closes) and closes[k + AHEAD] != closes[k]:
                outcomes["ahead5"] = closes[k + AHEAD] > closes[k]
            later = sessions[d].get(m1.SESSION_CLOSE)
            if later is not None and later != price:
                outcomes["close"] = later > price
            for split, part in splits.items():
                for horizon, up in outcomes.items():
                    cell = cells["%s|%s|%s" % (split, part, horizon)]
                    right = up == (reading == RISING)
                    cell["right" if right else "wrong"] += 1
                    cell["rose" if up else "fell"] += 1
                    y = cell["years"]["Q%d" % ((d.month - 10) % 12 // 3 + 1)]
                    y[0] += right
                    y[1] += 1
                    y[2] += up
                    y[3] += 1
        rows = {}
        for key, c in cells.items():
            n = c["right"] + c["wrong"]
            beat = sum(1 for r, nn, u, uu in c["years"].values() if nn >= 20 and r / nn > u / uu)
            rows[key] = {"n": n, "right_pct": round(100 * c["right"] / n, 1), "market_rose_pct": round(100 * c["rose"] / n, 1),
                         "quarters_beat": beat, "quarters": sum(1 for v in c["years"].values() if v[1] >= 20)}
        out["frames"][name] = {"er_thirds": [round(low_cut, 3), round(high_cut, 3)], "rows": rows}
        print(name, "done", round(time.time() - began, 1), flush=True)
    out["seconds"] = round(time.time() - began, 1)
    (HERE / OUT_NAME).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
