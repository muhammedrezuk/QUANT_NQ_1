"""2026-10-23 (owner's sealed red lines, law 6): the part is closed at market first and only then the stop moves -- that is
574's job. This atom moves nothing before 574's ticket list has been heard, nor on the cycle a ticket first appears (574
names it at the end of that same cycle); a ticket 574 names is left to it."""
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))

from core.contracts.atom import AtomContext  # noqa: E402
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("_atom572_law6", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom572_law6"] = _mod
_spec.loader.exec_module(_mod)


class _Log:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.published = []

    def subscribe(self, name, handler):
        pass

    async def publish(self, name, payload):
        self.published.append((name, payload))


def _pos(ticket, current):
    # a buy at 4000 with its stop at 3990 (1R = 10) -- at 4020 it is 2R up
    return {"account_id": "A", "ticket": ticket, "symbol": "XAUUSD", "side": "BUY", "volume": 0.3,
            "entry_price": 4000.0, "current_price": current, "stop_loss": 3990.0, "take_profit": 4100.0}


async def _new():
    bus = _Bus()
    atom = _mod.Atom()
    await atom.initialize(AtomContext(atom_id=572, config={"breakeven_at_r": 1.0}, logger=_Log(),
                                      publish=bus.publish, subscribe=bus.subscribe))
    await atom.start()
    return atom, bus


def _sent(bus):
    return [p["ticket"] for n, p in bus.published if n == _mod.EVENT_OUT]


async def test_nothing_moves_before_574s_list_is_heard():
    atom, bus = await _new()
    for _ in range(3):
        await atom._on_positions({"positions": [_pos(1, 4020.0)]})
    assert _sent(bus) == [] and atom._awaiting_plan == {"1"}
    health = await atom.health_check()
    assert "plan_heard=False awaiting_574=1" in health.message


async def test_a_ticket_is_not_moved_on_the_cycle_it_first_appears():
    atom, bus = await _new()
    await atom._on_plan({"tickets": []})
    await atom._on_positions({"positions": [_pos(1, 4020.0)]})          # first sight: 574 has not named it yet
    assert _sent(bus) == []
    await atom._on_plan({"tickets": ["1"]})                             # 574 names it at the end of that cycle
    await atom._on_positions({"positions": [_pos(1, 4020.0)]})
    assert _sent(bus) == [] and atom._plan_yielded == {"1"}


async def test_a_ticket_574_never_names_is_still_guarded_from_its_second_cycle():
    atom, bus = await _new()
    await atom._on_plan({"tickets": []})
    await atom._on_positions({"positions": [_pos(2, 4020.0)]})
    await atom._on_positions({"positions": [_pos(2, 4020.0)]})
    assert _sent(bus) == [2] and atom._awaiting_plan == set()
