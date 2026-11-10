# -*- coding: utf-8 -*-
"""Do the owner's averages (exponential 5, 10, 50 on closes) know the Nasdaq's direction? Attempt 1, declared in the
attempts ledger before running.

2014-07-17 .. 2015-12-31 (the only stretch no moving-average measurement touched), USTEC only, the owner's nine frames.
Rising = ema5 > ema10 > ema50, falling = ema5 < ema10 < ema50, else no reading; no reading before 150 bars of the frame.
Asks at every quarter-hour close 09:45-15:45 NY on trading days, from the bars closed by then; right when the price went
that way after 15 minutes, after 60 minutes, and at the 16:00 close; flat not counted; base rate beside it.
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOW = HERE.parent / "dow_direction_2026-10-17"
sys.path.insert(0, str(DOW))
import measure_dow as m1  # noqa: E402
import measure_dow2 as m2  # noqa: E402
from shared import market_clock  # noqa: E402

FROM, TO = date(2014, 7, 17), date(2015, 12, 31)
PERIODS = (5, 10, 50)
MIN_BARS = 3 * PERIODS[-1]
RISING, FALLING, NONE = "rising", "falling", "none"


def ema_states(bars: list[tuple]) -> list[str]:
    """The reading at every bar's close: order of the three averages."""
    alphas = [2.0 / (p + 1.0) for p in PERIODS]
    values: list[float] = []
    out = []
    for i, bar in enumerate(bars):
        close = bar[4]
        values = [close] * len(PERIODS) if i == 0 else [a * close + (1 - a) * v for a, v in zip(alphas, values)]
        if i + 1 < MIN_BARS:
            out.append(NONE)
        elif values[0] > values[1] > values[2]:
            out.append(RISING)
        elif values[0] < values[1] < values[2]:
            out.append(FALLING)
        else:
            out.append(NONE)
    return out


def load_until(period: str, until_s: float) -> list[tuple]:
    import sqlite3
    con = sqlite3.connect("file:%s?mode=ro" % m1.HISTORY_DB, uri=True)
    rows = con.execute("SELECT period_start, open, high, low, close, tick_volume FROM candles_history WHERE symbol=? AND "
                       "period=? AND period_start<? ORDER BY period_start", (m1.SYMBOL, period, until_s)).fetchall()
    con.close()
    return [tuple(float(x) for x in r) for r in rows]


def main() -> None:
    began = time.time()
    until = datetime(TO.year + 1, 2, 1, tzinfo=m1.NY).timestamp()      # a month past the end: every horizon is inside
    frames = {}
    for group, items in m2.GROUPS.items():
        for name, period, length in items:
            bars = load_until(period, until)
            frames[name] = (group, bars, m2.closes_at(bars, length), ema_states(bars))
    m15 = frames["15m"][1]
    sessions: dict[date, dict[int, float]] = defaultdict(dict)
    for b in m15:
        d, minute = m1.ny_minute(b[0] + 900)
        sessions[d][minute] = b[4]
    asks = []
    for b in m15:
        t = b[0] + 900
        d, minute = m1.ny_minute(t)
        if not (FROM <= d <= TO) or not m1.FIRST_ASK <= minute <= m1.LAST_ASK or d.weekday() >= 5:
            continue
        inside = sum(1 for m in sessions[d] if m1.FIRST_ASK <= m <= m1.SESSION_CLOSE)
        noon = datetime(d.year, d.month, d.day, 12, tzinfo=m1.NY).timestamp()
        if inside < m1.MIN_SESSION_BARS or market_clock.no_trade_day(noon):
            continue
        asks.append((t, d, minute, b[4]))
    hints = {name: 0 for name in frames}
    tally = defaultdict(lambda: {"right": 0, "wrong": 0, "flat": 0, "days": set()})
    states = defaultdict(lambda: defaultdict(int))
    base = defaultdict(lambda: {"up": 0, "down": 0, "flat": 0})
    for t, d, minute, close in asks:
        reading = {}
        for name, (_, bars, ends, marks) in frames.items():
            i = hints[name]
            while i < len(bars) and ends[i] <= t:
                i += 1
            hints[name] = i
            reading[name] = marks[i - 1] if i else NONE
        calls = [(name, reading[name]) for name in frames]
        for group, items in m2.GROUPS.items():
            values = {reading[n] for n, _, _ in items}
            calls.append(("%s_all_same" % group, values.pop() if len(values) == 1 else NONE))
        every = set(reading.values())
        calls.append(("all_nine_same", every.pop() if len(every) == 1 else NONE))
        for horizon, step in m1.HORIZONS.items():
            target = m1.SESSION_CLOSE if step is None else minute + step
            later = sessions[d].get(target)
            if target > m1.SESSION_CLOSE or later is None:
                continue
            move = "up" if later > close else "down" if later < close else "flat"
            base[horizon][move] += 1
            for name, state in calls:
                if horizon == "15m":
                    states[name][state] += 1
                if state == NONE:
                    continue
                cell = tally["%s|%s" % (name, horizon)]
                if move == "flat":
                    cell["flat"] += 1
                    continue
                cell["right" if (move == "up") == (state == RISING) else "wrong"] += 1
                cell["days"].add(d)
    rates = {}
    for key, cell in tally.items():
        horizon = key.split("|")[1]
        b = base[horizon]
        n = cell["right"] + cell["wrong"]
        p = cell["right"] / n if n else 0.0
        rose = b["up"] / (b["up"] + b["down"])
        bar = 2 * 0.5 / math.sqrt(len(cell["days"])) if cell["days"] else 1.0
        rates[key] = {"right": cell["right"], "wrong": cell["wrong"], "pct": round(100 * p, 1), "days": len(cell["days"]),
                      "market_rose_pct": round(100 * rose, 1), "beyond_bar": (p - rose) > bar}
    out = {"period": [str(FROM), str(TO)], "asks": len(asks), "days": len({a[1] for a in asks}),
           "states_per_ask": {k: dict(v) for k, v in states.items()}, "base": {k: dict(v) for k, v in base.items()},
           "rates": rates, "seconds": round(time.time() - began, 1)}
    (HERE / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done", out["asks"], out["days"], out["seconds"])


if __name__ == "__main__":
    main()
