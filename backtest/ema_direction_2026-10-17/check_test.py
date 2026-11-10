# -*- coding: utf-8 -*-
"""Check of attempt 1 (the owner: "either the test is wrong or something is not right"). Same period, same readings.

(A) Is the indicator computed right? When it reads rising (falling), was the price higher (lower) than 10 bars of that
    frame earlier? -- what the averages describe: the past.
(B) Is the horizon fair? Attempt 1 judged every frame at 15 minutes / 1 hour / the session close, even the day and the
    week. Here each frame is judged on its own bars: the close 1, 5 and 10 bars of that frame later.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measure_ema as me  # noqa: E402

FRAMES = (("1m", "M1"), ("5m", "M5"), ("15m", "M15"), ("30m", "M30"), ("1h", "H1"), ("4h", "H4"), ("1d", "D1"), ("1w", "W1"))
BACK = 10
AHEAD = (1, 5, 10)


def main() -> None:
    until = datetime(2016, 6, 1, tzinfo=me.m1.NY).timestamp()
    for name, period in FRAMES:
        bars = me.load_until(period, until)
        marks = me.ema_states(bars)
        past = {"right": 0, "n": 0}
        future = {k: {"right": 0, "n": 0, "up": 0, "moves": 0} for k in AHEAD}
        for i, bar in enumerate(bars):
            day = datetime.fromtimestamp(bar[0], me.m1.NY.__class__("UTC")).date() if False else \
                datetime.utcfromtimestamp(bar[0]).date()
            if not (me.FROM <= day <= me.TO) or i < BACK:
                continue
            state = marks[i]
            for k in AHEAD:
                if i + k < len(bars) and bars[i + k][4] != bar[4]:
                    up = bars[i + k][4] > bar[4]
                    future[k]["moves"] += 1
                    future[k]["up"] += up
                    if state != me.NONE:
                        future[k]["n"] += 1
                        future[k]["right"] += up == (state == me.RISING)
            if state != me.NONE and bars[i - BACK][4] != bar[4]:
                past["n"] += 1
                past["right"] += (bar[4] > bars[i - BACK][4]) == (state == me.RISING)
        line = ["%-3s" % name, "past10 %.1f%% (%d)" % (100 * past["right"] / max(1, past["n"]), past["n"])]
        for k in AHEAD:
            f = future[k]
            line.append("next%d %.1f%% vs rose %.1f%%" % (k, 100 * f["right"] / max(1, f["n"]), 100 * f["up"] / max(1, f["moves"])))
        print(" | ".join(line))


if __name__ == "__main__":
    main()
