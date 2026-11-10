# -*- coding: utf-8 -*-
"""Writes shared/dow_month_seed.json: the broker's closed month candles of the US indices, from the stored history.

Why (2026-10-17, owner seal on the adopted Dow readings): the primary group needs the month frame, the live feed has no
month candle, and 450 day candles give about 21 months -- measured: the month trend built from them matched the measured
one at 0 of 3,150 moments (the week matched at all 3,150). So the closed months come from here, and atom 209 builds only
the months after the last one here from its day candles. Read-only on the history; run again to refresh.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DB = ROOT / "forex_runtime" / "var" / "history" / "ctrader_history.db"
OUT = ROOT / "shared" / "dow_month_seed.json"
SYMBOLS = ("USTEC", "US500", "US30")


def main() -> None:
    con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    seed = {}
    for symbol in SYMBOLS:
        rows = con.execute("SELECT period_start, open, high, low, close, tick_volume FROM candles_history "
                           "WHERE symbol=? AND period='MN1' ORDER BY period_start", (symbol,)).fetchall()
        seed[symbol] = [[float(x) for x in r] for r in rows[:-1]]       # the newest one may still be open
    con.close()
    OUT.write_text(json.dumps({"built_at": int(time.time()), "source": "ctrader_history MN1", "symbols": seed}),
                   encoding="utf-8")
    print({s: len(v) for s, v in seed.items()})


if __name__ == "__main__":
    main()
