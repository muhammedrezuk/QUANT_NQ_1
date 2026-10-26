# -*- coding: utf-8 -*-
"""Does Dow theory know the Nasdaq's direction? Attempt 1, declared in the attempts ledger before running.

One year (2024-10-01 .. 2025-09-30, the last year before the untouched holdout), USTEC only. At every quarter-hour close of
the New York session from 09:45 to 15:45 NY, the Dow state of each frame (day, hour, quarter hour) is computed with the
live atom's own code (shared.dow_theory, 450 bars, span 2) from the candles closed by then. A rising (falling) state is
right when the price is higher (lower) after 15 minutes, after 60 minutes, and at the 16:00 session close; a flat move is
not counted; a "none" state is counted apart. The base rate (how often the market rose) is reported beside it.
No trades, no stops, no targets.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from shared import dow_theory as dt  # noqa: E402
from shared import market_clock  # noqa: E402

HISTORY_DB = ROOT / "forex_runtime" / "var" / "history" / "ctrader_history.db"
SYMBOL = "USTEC"
NY = ZoneInfo("America/New_York")
YEAR_FROM, YEAR_TO = date(2024, 10, 1), date(2025, 9, 30)
FRAMES = {"primary": ("D1", 86400), "secondary": ("H1", 3600), "minor": ("M15", 900)}
MAX_BARS = 450
FIRST_ASK, LAST_ASK, SESSION_CLOSE = 9 * 60 + 45, 15 * 60 + 45, 16 * 60
MIN_SESSION_BARS = 24
HORIZONS = {"15m": 15, "60m": 60, "close": None}


def load(period: str) -> list[tuple]:
    con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    rows = con.execute("SELECT period_start, open, high, low, close, tick_volume FROM candles_history "
                       "WHERE symbol=? AND period=? ORDER BY period_start", (SYMBOL, period)).fetchall()
    con.close()
    return [tuple(float(x) for x in r) for r in rows]


def ny_minute(epoch: float) -> tuple[date, int]:
    local = datetime.fromtimestamp(epoch, timezone.utc).astimezone(NY)
    return local.date(), local.hour * 60 + local.minute


def closed_upto(bars: list[tuple], length: int, t: float, hint: int) -> int:
    """Index after the last bar closed by t (bars sorted); hint = previous answer (t only grows)."""
    i = hint
    while i < len(bars) and bars[i][0] + length <= t:
        i += 1
    return i


def main() -> None:
    began = time.time()
    data = {deg: load(per) for deg, (per, _) in FRAMES.items()}
    m15 = data["minor"]
    sessions: dict[date, dict[int, float]] = defaultdict(dict)          # NY date -> close minute -> close
    for b in m15:
        d, minute = ny_minute(b[0] + 900)
        sessions[d][minute] = b[4]
    asks = []
    for b in m15:
        t = b[0] + 900
        d, minute = ny_minute(t)
        if not (YEAR_FROM <= d <= YEAR_TO) or not FIRST_ASK <= minute <= LAST_ASK or d.weekday() >= 5:
            continue
        day = sessions[d]
        inside = sum(1 for m in day if 9 * 60 + 45 <= m <= SESSION_CLOSE)
        noon = datetime(d.year, d.month, d.day, 12, tzinfo=NY).timestamp()
        if inside < MIN_SESSION_BARS or market_clock.no_trade_day(noon):
            continue
        asks.append((t, d, minute, b[4]))
    hints = {deg: 0 for deg in FRAMES}
    cache: dict[str, tuple[int, str]] = {}
    tally = defaultdict(lambda: defaultdict(lambda: {"right": 0, "wrong": 0, "flat": 0}))
    states = defaultdict(lambda: defaultdict(int))
    base = defaultdict(lambda: {"up": 0, "down": 0, "flat": 0})
    for t, d, minute, close in asks:
        trend = {}
        for deg, (_, length) in FRAMES.items():
            end = hints[deg] = closed_upto(data[deg], length, t, hints[deg])
            if deg not in cache or cache[deg][0] != end:
                rows = data[deg][max(0, end - MAX_BARS):end]
                cache[deg] = (end, dt.frame_facts(rows)["dow_trend"] if rows else dt.NONE)
            trend[deg] = cache[deg][1]
        quarter = "Q%d" % ((d.month - 10) % 12 // 3 + 1)                 # quarters of the measured year (Oct = Q1)
        groups = [(deg, trend[deg]) for deg in FRAMES]
        if trend["primary"] == trend["secondary"] == trend["minor"]:
            groups.append(("all_three_same", trend["primary"]))
        if trend["primary"] == trend["secondary"]:
            groups.append(("primary_and_secondary_same", trend["primary"]))
        for name, horizon in HORIZONS.items():
            target = SESSION_CLOSE if horizon is None else minute + horizon
            later = sessions[d].get(target)
            if target > SESSION_CLOSE or later is None:
                continue
            move = "up" if later > close else "down" if later < close else "flat"
            base[name][move] += 1
            base["%s|%s" % (name, quarter)][move] += 1
            for group, state in groups:
                states[group][state] += 1 if name == "15m" else 0
                if state == dt.NONE:
                    continue
                cell = "right" if (move == "up") == (state == dt.RISING) and move != "flat" else \
                    "flat" if move == "flat" else "wrong"
                tally["%s|%s" % (group, name)][state][cell] += 1
                tally["%s|%s|%s" % (group, name, quarter)][state][cell] += 1
    out = {"year": [str(YEAR_FROM), str(YEAR_TO)], "asks": len(asks), "days": len({a[1] for a in asks}),
           "states_per_ask": {g: dict(s) for g, s in states.items()},
           "base": {k: dict(v) for k, v in base.items()},
           "tally": {k: {s: dict(c) for s, c in v.items()} for k, v in tally.items()},
           "seconds": round(time.time() - began, 1)}
    (HERE / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done", out["asks"], out["days"], out["seconds"])


if __name__ == "__main__":
    main()
