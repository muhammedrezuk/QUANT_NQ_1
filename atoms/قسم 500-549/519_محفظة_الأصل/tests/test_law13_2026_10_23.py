"""2026-10-23 (owner seal NQ, sealed red lines law 13 -- hedging is forbidden in every form): 519 has no HEDGING state any
more -- a warning holds (never REQUEST_HEDGE), force_hedge is no command, and an owner intent saved with HEDGING scopes
is read as NORMAL instead of failing closed."""
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("_t519_law13", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t519_law13"] = m
_spec.loader.exec_module(m)

SCOPE = "A\x1fBR\x1fNQ"


class _Log:
    def __getattr__(self, _name):
        return lambda *a, **k: None


async def _new():
    events = []

    async def publish(name, payload):
        events.append((name, payload))

    atom = m.Atom()
    await atom.initialize(m.AtomContext(519, {"exit_ratio": 0.9}, _Log(), publish, lambda *a: None))
    await atom.start()
    return atom, events


def test_no_hedging_state_or_command_is_left():
    assert not hasattr(m, "HEDGING") and not hasattr(m, "REQUEST_HEDGE") and not hasattr(m, "FORCE_HEDGE")
    assert "HEDGING" not in m._VALID_STATES


def test_a_warning_holds_and_never_asks_for_a_hedge():
    atom, _ = asyncio.run(_new())
    assert atom.next_state(SCOPE, 0.96, True, False) == (m.WARNING, m.HOLD)


def test_force_hedge_is_no_command():
    atom, _ = asyncio.run(_new())
    asyncio.run(atom._on_account({"account_id": "A", "broker": "BR", "margin_mode": 2}))
    asyncio.run(atom._on_command({"account_id": "A", "broker": "BR", "symbol": "NQ", "command": "force_hedge"}))
    assert atom._states.get(SCOPE) != "HEDGING"


def test_an_old_intent_with_hedging_is_read_as_normal_not_fail_closed():
    atom, _ = asyncio.run(_new())
    asyncio.run(atom.restore({"halted_accounts": [], "paused": [], "states": {SCOPE: "HEDGING"}}))
    assert atom._restore_error == "" and atom._states[SCOPE] == m.NORMAL and atom._halted_accounts == set()
