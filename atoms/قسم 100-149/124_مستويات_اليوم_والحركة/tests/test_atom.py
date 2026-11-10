"""124 day levels: on a live quarter-hour close the Nasdaq map holds yesterday's New York session, the pre-market
(04:00-09:30 NY), the night, the open and its first quarter hour, the gap, and the distances in pips; history only fills."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("atom_124", Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def at(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


class Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, name: str, payload: dict | None = None) -> None:
        self.events.append((name, payload or {}))

    def subscribe(self, name, handler) -> None:
        pass


def price(start: float) -> float:
    """A path that is easy to reason about: 25,000 + one point per quarter hour since Wednesday 00:00 UTC."""
    return 25000.0 + (start - at("2026-10-14T00:00")) / 900.0


def candle(start: float, history: bool, frame: str = "15m") -> dict:
    p = price(start)
    return {"symbol": "USTEC", "timeframe": frame, "period_start": start, "open": p, "high": p + 0.5,
            "low": p - 0.5, "close": p + 0.25, "history": history}


def build():
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    ctx = AtomContext(atom_id=124, config={"symbols": ["USTEC"]}, logger=None,
                      publish=bus.publish, subscribe=bus.subscribe, subscribe_all=lambda h: None)
    asyncio.run(atom.initialize(ctx))
    asyncio.run(atom.start())
    return atom, bus


def test_history_fills_and_a_live_close_publishes_the_nasdaq_map():
    atom, bus = build()
    t = at("2026-10-14T00:00")
    while t < at("2026-10-16T14:15"):
        asyncio.run(atom._on_candle(candle(t, history=True)))
        t += 900
    assert bus.events == []                                            # history only fills
    asyncio.run(atom._on_candle(candle(at("2026-10-16T14:15"), history=False)))   # Friday 10:15 New York
    body = [p for n, p in bus.events if n == "knowledge.levels.state"][-1]
    assert body["available"] and body["session"] == "NEW_YORK" and body["window"]["inside"]
    yesterday = body["yesterday"]                                      # Thursday 13:30-20:00 UTC
    assert yesterday["open"] == price(at("2026-10-15T13:30")) and yesterday["close"] == price(at("2026-10-15T19:45")) + 0.25
    assert body["premarket"]["low"] == price(at("2026-10-16T08:00")) - 0.5   # 04:00 New York
    assert body["premarket"]["high"] == price(at("2026-10-16T13:15")) + 0.5
    assert body["overnight"]["low"] == price(at("2026-10-15T20:00")) - 0.5
    assert body["opening"]["price"] == price(at("2026-10-16T13:30"))
    gap = body["gap"]
    assert gap["opened"] == "above_yesterday_close" and gap["filled"] is False and round(gap["pips"], 2) == round(
        price(at("2026-10-16T13:30")) - (price(at("2026-10-15T19:45")) + 0.25), 2)
    assert all(m["side"] == "below" for m in body["nearest_below"]) and body["nearest_below"][0]["pips_from_last"] < 0


def test_other_frames_and_symbols_are_ignored_and_health_counts():
    atom, bus = build()
    asyncio.run(atom._on_candle({**candle(at("2026-10-16T14:15"), False), "symbol": "EURUSD"}))
    asyncio.run(atom._on_candle(candle(at("2026-10-16T14:00"), False, frame="1h")))
    assert bus.events == []
    asyncio.run(atom._on_candle(candle(at("2026-10-15T21:00"), True, frame="1d")))
    health = asyncio.run(atom.health_check())
    assert "USTEC:0/1" in health.message
