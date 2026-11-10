# -*- coding: utf-8 -*-
"""Fidelity check, not an attempt: the live feed has no week or month candles, so atom 209 builds them from the last 450
day candles. Over attempt 2's six months, does that give the same week/month states -- and the same "primary agree"
record -- as the broker's stored week and month candles that were measured?"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measure_dow as m1  # noqa: E402
import measure_dow2 as m2  # noqa: E402
from shared import dow_theory as dt  # noqa: E402


def main() -> None:
    day = m2.load("D1", None)
    week, month = m2.load("W1", None), m2.load("MN1", None)
    week_end, month_end = m2.closes_at(week, None), m2.closes_at(month, None)
    m15 = m2.load("M15", None)
    sessions = {}
    for b in m15:
        d, minute = m1.ny_minute(b[0] + 900)
        sessions.setdefault(d, {})[minute] = b[4]
    same = {"1w": 0, "1mo": 0, "agree": 0}
    record = {"stored": {"right": 0, "wrong": 0}, "built": {"right": 0, "wrong": 0}}
    asks = 0
    for b in m15:
        t = b[0] + 900
        d, minute = m1.ny_minute(t)
        if not (m2.FROM <= d <= m2.TO) or not m1.FIRST_ASK <= minute <= m1.LAST_ASK or d.weekday() >= 5:
            continue
        if sum(1 for m in sessions[d] if m1.FIRST_ASK <= m <= m1.SESSION_CLOSE) < m1.MIN_SESSION_BARS:
            continue
        asks += 1
        days = [r for r in day if r[0] + 86400 <= t][-m1.MAX_BARS:]
        d1 = dt.frame_facts(days)["dow_trend"]
        stored = {"1w": dt.frame_facts([w for w, e in zip(week, week_end) if e <= t][-m1.MAX_BARS:])["dow_trend"],
                  "1mo": dt.frame_facts([x for x, e in zip(month, month_end) if e <= t][-m1.MAX_BARS:])["dow_trend"]}
        built = {"1w": dt.frame_facts(dt.aggregate(days, dt.WEEK, t))["dow_trend"],
                 "1mo": dt.frame_facts(dt.aggregate(days, dt.MONTH, t))["dow_trend"]}
        for k in ("1w", "1mo"):
            same[k] += stored[k] == built[k]
        a, c = dt.agree([d1, stored["1w"], stored["1mo"]]), dt.agree([d1, built["1w"], built["1mo"]])
        same["agree"] += a == c
        later = sessions[d].get(m1.SESSION_CLOSE)
        if later is None or later == b[4]:
            continue
        for name, state in (("stored", a), ("built", c)):
            if state != dt.NONE:
                record[name]["right" if (later > b[4]) == (state == dt.RISING) else "wrong"] += 1
    print("asks", asks, "same", same, "record", record)


if __name__ == "__main__":
    main()
