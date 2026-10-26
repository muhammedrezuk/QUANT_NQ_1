"""565 on the sealed red lines of 2026-10-23: a red news window closes only the positions whose asset holds the item's
currency (USD closes every symbol), and on Saturday bitcoin is closed like the rest (law 23)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_atom as T  # noqa: E402

INSIDE = T.INSIDE   # Friday 17:00 Turkey: New York and the general window are open, London too
SATURDAY = T.at("2026-10-17T12:00")


def build():
    atom, bus = T.build()
    asyncio.run(atom._on_positions({"account_id": "ACC", "positions": [
        {"ticket": 11, "symbol": "BTCUSD", "side": "BUY", "volume": 0.5, "magic": 20260801},
        {"ticket": 12, "symbol": "USTEC", "side": "SELL", "volume": 2.0, "magic": 20260801},
        {"ticket": 14, "symbol": "EURUSD", "side": "BUY", "volume": 1.0, "magic": 20260801},
        {"ticket": 13, "symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "magic": 0}]}))
    return atom, bus


def closed_after(atom, bus, moment, *currencies):
    asyncio.run(atom._on_calendar({"utc": moment - 5, "in_event_window": bool(currencies),
                                   "status": "BLOCKED" if currencies else "CLEAR",
                                   "blocked_currencies": list(currencies)}))
    T.pulse(atom, moment)
    return sorted(i["ticket"] for i in bus.of("execution.manage.intent"))


def test_a_red_euro_window_closes_the_euro_pair_only():
    atom, bus = build()
    assert closed_after(atom, bus, INSIDE, "EUR") == [14]
    assert bus.of("execution.manage.intent")[0]["reason"] == "NEWS_RED_LINE"


def test_a_red_dollar_window_closes_every_symbol_of_ours():
    atom, bus = build()
    assert closed_after(atom, bus, INSIDE, "USD") == [11, 12, 14]     # the owner's own gold is left alone


def test_on_saturday_bitcoin_is_closed_like_the_rest():
    atom, bus = build()
    assert closed_after(atom, bus, SATURDAY) == [11, 12, 14]
    assert {i["reason"] for i in bus.of("execution.manage.intent")} == {"OUTSIDE_TRADING_WINDOW"}
