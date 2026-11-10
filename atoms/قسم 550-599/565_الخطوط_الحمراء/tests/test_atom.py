"""565 red lines: each asset's own window end and a fresh red USD news window close every position of ours in full; a foreign
magic is left alone; the intent is not repeated inside the resend gap. 2026-10-25 (owner seal, law 17): the general window
(bitcoin, gold) now ends at 16:00 New York with the Nasdaq -- 23:00 on the owner's clock, 22:00 until then."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("atom_565", Path(__file__).resolve().parents[1] / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def at(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


INSIDE = at("2026-10-16T14:00")    # 17:00 Turkey: New York open (Nasdaq) and the general window (bitcoin)
EARLY = at("2026-10-16T00:00")     # 03:00 Turkey: the general window is open since Sydney (bitcoin); New York is not (Nasdaq)
NIGHT = at("2026-10-16T19:00")     # 22:00 Turkey: both still open since 2026-10-25 (bitcoin closed here until then)
NY_CLOSE = at("2026-10-16T20:00")  # 23:00 Turkey: New York closes and the general window with it


class Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, name: str, payload: dict | None = None) -> None:
        self.events.append((name, payload or {}))

    def subscribe(self, name, handler) -> None:
        pass

    def of(self, name: str) -> list[dict]:
        return [p for n, p in self.events if n == name]


def build():
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    ctx = AtomContext(atom_id=565, config={"magic": 20260801, "resend_after_s": 30.0}, logger=None,
                      publish=bus.publish, subscribe=bus.subscribe, subscribe_all=lambda h: None)
    asyncio.run(atom.initialize(ctx))
    asyncio.run(atom.start())
    asyncio.run(atom._on_positions({"account_id": "ACC", "positions": [
        {"ticket": 11, "symbol": "BTCUSD", "side": "BUY", "volume": 0.5, "magic": 20260801},
        {"ticket": 12, "symbol": "USTEC", "side": "SELL", "volume": 2.0, "magic": 20260801},
        {"ticket": 13, "symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "magic": 0}]}))
    return atom, bus


def pulse(atom, moment: float) -> None:
    asyncio.run(atom._on_pulse({"official_time": moment}))


def test_inside_the_window_nothing_is_closed():
    atom, bus = build()
    pulse(atom, INSIDE)
    assert bus.of("execution.manage.intent") == []
    assert bus.of("risk.red_line.state")[-1]["line"] == "CLEAR"


def test_each_position_closes_on_its_own_assets_red_line_and_a_foreign_one_is_left():
    atom, bus = build()
    pulse(atom, EARLY)
    intents = bus.of("execution.manage.intent")
    assert [i["ticket"] for i in intents] == [12], intents          # the Nasdaq outside New York; bitcoin trades on
    assert intents[0]["action"] == "CLOSE" and intents[0]["side"] == "SELL" and intents[0]["reason"] == "OUTSIDE_TRADING_WINDOW"
    pulse(atom, NY_CLOSE)
    later = bus.of("execution.manage.intent")[1:]                    # the Nasdaq still open hours on: closed again, with bitcoin
    assert sorted(i["ticket"] for i in later) == [11, 12] and [i["side"] for i in later if i["ticket"] == 11] == ["BUY"]
    assert bus.of("risk.red_line.state")[-1]["active"] is True      # the state's own line is the general window's


def test_at_22_turkey_the_general_window_is_still_open():
    """2026-10-25 (law 17, «نافذة لا 23:00»): bitcoin and gold are no longer closed at 22:00 on the owner's clock."""
    atom, bus = build()
    pulse(atom, NIGHT)
    assert bus.of("execution.manage.intent") == []


def test_the_close_is_resent_only_after_the_gap_and_forgotten_once_the_position_is_gone():
    atom, bus = build()
    pulse(atom, NY_CLOSE)
    pulse(atom, NY_CLOSE + 10)
    assert len(bus.of("execution.manage.intent")) == 2
    pulse(atom, NY_CLOSE + 31)
    assert len(bus.of("execution.manage.intent")) == 4
    asyncio.run(atom._on_positions({"account_id": "ACC", "positions": []}))
    pulse(atom, NY_CLOSE + 70)
    assert len(bus.of("execution.manage.intent")) == 4


def test_red_news_closes_inside_the_window_and_a_stale_calendar_does_not():
    atom, bus = build()
    asyncio.run(atom._on_calendar({"utc": INSIDE - 600, "in_event_window": True, "status": "BLOCKED"}))
    pulse(atom, INSIDE)
    assert bus.of("execution.manage.intent") == []
    asyncio.run(atom._on_calendar({"utc": INSIDE - 5, "in_event_window": True, "status": "BLOCKED"}))
    pulse(atom, INSIDE + 1)
    intents = bus.of("execution.manage.intent")
    assert len(intents) == 2 and all(i["reason"] == "NEWS_RED_LINE" for i in intents)


def test_health_and_snapshot():
    atom, bus = build()
    pulse(atom, NY_CLOSE)
    health = asyncio.run(atom.health_check())
    # 2026-10-26 (owner's law): the owner's position (ticket 13, magic 0) is neither counted open nor tallied.
    assert "intents=2" in health.message and "open=2" in health.message and "foreign" not in health.message
    assert "13" not in atom._positions["ACC"] and "foreign_positions" not in bus.of("risk.red_line.state")[-1]
    state = asyncio.run(atom.snapshot())
    fresh = mod.Atom()
    asyncio.run(fresh.restore(state))
    assert fresh._intents == 2 and fresh._lines["OUTSIDE_TRADING_WINDOW"] == 1

# --- 2026-10-26 (owner seal "nq", after the project audit): a stalled 806 pulse no longer freezes the lines -------------

def test_a_silent_806_pulse_hands_the_red_lines_to_the_003_heartbeat():
    atom, bus = build()
    pulse(atom, INSIDE)
    asyncio.run(atom._on_backup_pulse({"official_time": NY_CLOSE}))     # 806 is fresh: the heartbeat does nothing
    assert bus.of("execution.manage.intent") == [] and atom._backup_judged == 0
    atom._pulse_seen_at -= mod.PULSE_MAX_AGE_S + 1                     # 806 silent past the limit
    asyncio.run(atom._on_backup_pulse({"official_time": NY_CLOSE}))
    intents = bus.of("execution.manage.intent")
    assert sorted(i["ticket"] for i in intents) == [11, 12], intents    # the owner's own gold is left alone
    assert atom._backup_judged == 1
    health = asyncio.run(atom.health_check())
    assert health.state.name == "DEGRADED" and health.message.startswith(mod.PULSE_STALE), health.message
    pulse(atom, NY_CLOSE + 1)                                          # 806 is back
    assert asyncio.run(atom.health_check()).state.name == "HEALTHY"


def test_no_806_pulse_at_all_since_the_start_counts_as_stale():
    atom, bus = build()
    asyncio.run(atom._on_backup_pulse({"official_time": NY_CLOSE}))     # just started: not stale yet
    assert atom._backup_judged == 0
    atom._started_at -= mod.PULSE_MAX_AGE_S + 1
    asyncio.run(atom._on_backup_pulse({"official_time": NY_CLOSE}))
    assert atom._backup_judged == 1 and sorted(i["ticket"] for i in bus.of("execution.manage.intent")) == [11, 12]

# --- 2026-10-26 (owner seal "NQ"): a calendar that does not know closes every position of ours --------------------------

def _known(moment, *currencies):
    return {"utc": moment, "known": True, "status": "BLOCKED" if currencies else "CLEAR",
            "in_event_window": bool(currencies), "blocked_currencies": list(currencies)}


def test_an_unknown_calendar_closes_ours_and_leaves_the_owners_once_the_starts_grace_is_over():
    atom, bus = build()
    atom._started_at -= mod.UNKNOWN_GRACE_S + 1
    pulse(atom, INSIDE)                                                 # no calendar state at all
    intents = bus.of("execution.manage.intent")
    assert sorted(i["ticket"] for i in intents) == [11, 12], intents    # the owner's own gold is left alone
    assert {i["reason"] for i in intents} == {mod.REASON_NEWS_UNKNOWN}
    assert bus.of("risk.red_line.state")[-1]["line"] == mod.REASON_NEWS_UNKNOWN


def test_a_stale_or_unknowing_calendar_is_unknown_too():
    for calendar in ({**_known(INSIDE - 121)}, {**_known(INSIDE), "known": False}):
        atom, bus = build()
        atom._started_at -= mod.UNKNOWN_GRACE_S + 1
        asyncio.run(atom._on_calendar(calendar))
        pulse(atom, INSIDE)
        assert sorted(i["ticket"] for i in bus.of("execution.manage.intent")) == [11, 12], calendar


def test_a_known_calendar_closes_nothing_inside_the_window():
    atom, bus = build()
    atom._started_at -= mod.UNKNOWN_GRACE_S + 1
    asyncio.run(atom._on_calendar(_known(INSIDE - 5)))
    pulse(atom, INSIDE)
    assert bus.of("execution.manage.intent") == []
    assert bus.of("risk.red_line.state")[-1]["line"] == "CLEAR"


def test_no_close_on_an_unknown_calendar_inside_the_starts_grace():
    atom, bus = build()                                                 # just started: 109's first state may be on its way
    pulse(atom, INSIDE)
    assert bus.of("execution.manage.intent") == []
