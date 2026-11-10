# -*- coding: utf-8 -*-
"""Attempt 2 (declared in the attempts ledger before running): the owner's nine frames in three groups -- secondary (1m,
5m, 15m), sub (30m, 1h, 4h), primary (day, week, month) -- over six months (2024-04-01 .. 2024-09-30, never measured by
Dow before; the holdout untouched). Everything else as attempt 1: the live atom's code, closes, span 2, 450 bars, closed
candles only, asks at every quarter-hour close 09:45-15:45 NY, horizons 15m / 60m / session close, base rate beside it.
Each rate also carries the number of distinct days it came from (consecutive asks overlap)."""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measure_dow as m1  # noqa: E402
from shared import dow_theory as dt  # noqa: E402
from shared import market_clock  # noqa: E402

FROM, TO = date(2024, 4, 1), date(2024, 9, 30)
GROUPS = {"secondary": (("1m", "M1", 60), ("5m", "M5", 300), ("15m", "M15", 900)),
          "sub": (("30m", "M30", 1800), ("1h", "H1", 3600), ("4h", "H4", 14400)),
          "primary": (("1d", "D1", 86400), ("1w", "W1", None), ("1mo", "MN1", None))}   # None: closes at the next bar's start
LOOKBACK_S = {"M1": 3 * 86400, "M5": 10 * 86400, "M15": 20 * 86400, "M30": 40 * 86400, "H1": 80 * 86400,
              "H4": 300 * 86400}


def load(period: str, since: float | None) -> list[tuple]:
    con = sqlite3.connect("file:%s?mode=ro" % m1.HISTORY_DB, uri=True)
    sql = ("SELECT period_start, open, high, low, close, tick_volume FROM candles_history WHERE symbol=? AND period=? "
           + ("AND period_start>=? " if since else "") + "ORDER BY period_start")
    args = (m1.SYMBOL, period) + ((since,) if since else ())
    rows = [tuple(float(x) for x in r) for r in con.execute(sql, args).fetchall()]
    con.close()
    return rows


def closes_at(bars: list[tuple], length: int | None) -> list[float]:
    if length:
        return [b[0] + length for b in bars]
    return [bars[i + 1][0] if i + 1 < len(bars) else float("inf") for i in range(len(bars))]


def main() -> None:
    began = time.time()
    first = datetime(FROM.year, FROM.month, FROM.day, tzinfo=m1.NY).timestamp()
    frames = {}
    for group, items in GROUPS.items():
        for name, period, length in items:
            back = LOOKBACK_S.get(period)
            bars = load(period, first - back if back else None)
            frames[name] = (group, bars, closes_at(bars, length))
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
    cache: dict[str, tuple[int, str]] = {}
    tally = defaultdict(lambda: {"right": 0, "wrong": 0, "flat": 0, "days": set()})
    states = defaultdict(lambda: defaultdict(int))
    base = defaultdict(lambda: {"up": 0, "down": 0, "flat": 0})
    for t, d, minute, close in asks:
        trend = {}
        for name, (_, bars, ends) in frames.items():
            i = hints[name]
            while i < len(bars) and ends[i] <= t:
                i += 1
            hints[name] = i
            if name not in cache or cache[name][0] != i:
                rows = bars[max(0, i - m1.MAX_BARS):i]
                cache[name] = (i, dt.frame_facts(rows)["dow_trend"] if rows else dt.NONE)
            trend[name] = cache[name][1]
        calls = [(name, trend[name]) for name in frames]
        for group, items in GROUPS.items():
            values = {trend[n] for n, _, _ in items}
            calls.append(("%s_all_same" % group, values.pop() if len(values) == 1 else dt.NONE))
        every = set(trend.values())
        calls.append(("all_nine_same", every.pop() if len(every) == 1 else dt.NONE))
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
                if state == dt.NONE:
                    continue
                cell = tally["%s|%s" % (name, horizon)]
                if move == "flat":
                    cell["flat"] += 1
                    continue
                cell["right" if (move == "up") == (state == dt.RISING) else "wrong"] += 1
                cell["days"].add(d)
    out = {"months": [str(FROM), str(TO)], "asks": len(asks), "days": len({a[1] for a in asks}),
           "states_per_ask": {k: dict(v) for k, v in states.items()}, "base": {k: dict(v) for k, v in base.items()},
           "tally": {k: {**{x: v[x] for x in ("right", "wrong", "flat")}, "days": len(v["days"])} for k, v in tally.items()},
           "seconds": round(time.time() - began, 1)}
    (HERE / "result2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done", out["asks"], out["days"], out["seconds"])


if __name__ == "__main__":
    main()
