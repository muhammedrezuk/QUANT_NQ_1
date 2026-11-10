"""123 time and sessions context: publishes once a minute on the official pulse, with the owner's time position, the
sessions and their overlaps, the asset schedule and the holidays around today."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("atom_123", Path(__file__).resolve().parents[1] / "atom.py")
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


def build():
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    ctx = AtomContext(atom_id=123, config={"publish_every_s": 60.0}, logger=None,
                      publish=bus.publish, subscribe=bus.subscribe, subscribe_all=lambda h: None)
    asyncio.run(atom.initialize(ctx))
    asyncio.run(atom.start())
    return atom, bus


def test_publishes_once_a_minute_with_the_owners_time_position():
    atom, bus = build()
    t = at("2026-10-16T07:30")          # Friday 10:30 Turkey
    for step in (0, 10, 59, 60):
        asyncio.run(atom._on_pulse({"official_time": t + step}))
    out = [p for n, p in bus.events if n == "knowledge.context.state"]
    assert len(out) == 2
    tp = out[0]["time"]
    assert (tp["year"], tp["quarter"], tp["half"], tp["month"], tp["week_of_month"], tp["weeks_in_month"]) == (2026, 4, 2, 10, 3, 5)
    assert tp["owner_time"] == "2026-10-16 10:30:00" and tp["first_week_full"] is False


def test_sessions_overlap_and_schedule_on_the_owners_clock():
    atom, bus = build()
    asyncio.run(atom._on_pulse({"official_time": at("2026-10-16T07:30")}))
    body = [p for n, p in bus.events if n == "knowledge.context.state"][0]
    assert set(body["sessions"]["open_now"]) == {"HONG_KONG", "SINGAPORE", "FRANKFURT", "LONDON"}
    assert {"a": "FRANKFURT", "b": "LONDON"}.items() <= body["sessions"]["overlaps"][-1].items()
    nasdaq = [r for r in body["schedule"] if r["symbol"] == "USTEC"][0]
    assert (nasdaq["open"], nasdaq["open_owner"], nasdaq["close_owner"]) == (False, "16:30", "23:00")


def test_holidays_around_today():
    h = mod.holidays_around(date(2026, 10, 17))
    assert h["previous_holiday"]["name"] == "columbus-day" and h["previous_holiday"]["days_ago"] == 5
    assert h["next_holiday"]["name"] == "veterans-day" and h["next_holiday"]["days_left"] == 25
    assert mod.holidays_around(date(2026, 11, 26))["today_holiday"] == "thanksgiving-day"


def test_health_and_snapshot():
    atom, bus = build()
    asyncio.run(atom._on_pulse({"official_time": at("2026-10-16T07:30")}))
    health = asyncio.run(atom.health_check())
    assert "published=1" in health.message and "Q4 W3/5" in health.message
    fresh = mod.Atom()
    asyncio.run(fresh.restore(asyncio.run(atom.snapshot())))
    assert fresh._published == 1
