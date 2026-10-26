"""2026-10-26 (owner's law, seal "NQ"): the owner's manual position is never a leg to extract from -- no CLOSE nor
CLOSE_PARTIAL is ever sent on it. It was chosen as a winner and closed with the system's magic, stopped only by 575."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FOLDER))
_spec = importlib.util.spec_from_file_location("_t579_owner", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t579_owner"] = m
_spec.loader.exec_module(m)


class L:
    def __getattr__(self, n):
        return lambda *a, **k: None


class B:
    def __init__(self):
        self.e = []

    def subscribe(self, *a):
        pass

    async def publish(self, n, p):
        self.e.append((n, p))

    def commands(self):
        return [p for n, p in self.e if n == m.EVENT_MANAGE]


async def _new():
    b = B(); a = m.Atom()
    await a.initialize(m.AtomContext(579, {"lot_step": .01}, L(), b.publish, b.subscribe)); await a.start()
    return a, b


OWNER = {"account_id": "A", "symbol": "USTEC", "ticket": 2036216648, "side": "BUY", "volume": 20, "profit": 655.8, "magic": 0}
SYSTEM = {"account_id": "A", "symbol": "USTEC", "ticket": 1, "side": "BUY", "volume": 1, "profit": 100, "magic": 20260801}


async def test_a_partial_extraction_takes_the_systems_leg_not_the_owners():
    a, b = await _new()
    await a._on_positions({"positions": [OWNER, SYSTEM]})
    await a._on_partial({"extraction_id": "e1", "account_id": "A", "symbol": "USTEC", "amount": 50})
    assert [str(c["ticket"]) for c in b.commands()] == ["1"]


async def test_with_only_the_owners_winner_the_request_waits():
    a, b = await _new()
    await a._on_positions({"positions": [OWNER]})
    await a._on_partial({"extraction_id": "e2", "account_id": "A", "symbol": "USTEC", "amount": 50})
    assert b.commands() == [] and "e2" in a._deferred


async def test_a_full_extraction_never_closes_the_owners_position():
    a, b = await _new()
    await a._on_positions({"positions": [OWNER, SYSTEM]})
    await a._on_full({"extraction_id": "f1", "account_id": "A", "symbol": "USTEC", "amount": 200})
    assert [str(c["ticket"]) for c in b.commands()] == ["1"]


async def test_a_leg_with_no_magic_known_is_the_systems_as_before():
    a, b = await _new()
    await a._on_positions({"positions": [{k: v for k, v in SYSTEM.items() if k != "magic"}]})
    await a._on_partial({"extraction_id": "e3", "account_id": "A", "symbol": "USTEC", "amount": 50})
    assert [str(c["ticket"]) for c in b.commands()] == ["1"]
