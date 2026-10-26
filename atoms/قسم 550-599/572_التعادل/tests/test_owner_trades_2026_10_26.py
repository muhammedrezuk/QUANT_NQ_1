"""2026-10-26 (owner's law, seal "NQ"): the owner's own trades have nothing to do with the system -- 572 never tracks or moves
the stop of a position that is not the system's, however far it runs; the system's position beside it is moved as before."""
import importlib.util as _ilu
import sys
from pathlib import Path as _Path

_spec = _ilu.spec_from_file_location("_t572_law6_owner", _Path(__file__).resolve().parent / "test_law6_2026_10_23.py")
L = _ilu.module_from_spec(_spec)
sys.modules["_t572_law6_owner"] = L
_spec.loader.exec_module(L)


def _owner(ticket, current):
    return dict(L._pos(ticket, current), magic=0)


async def test_the_owners_position_is_never_tracked_or_moved():
    atom, bus = await L._new()
    await atom._on_plan({"tickets": []})
    for _ in range(3):
        await atom._on_positions({"positions": [_owner(7, 4030.0)]})       # 3R up, far past 1R
    assert L._sent(bus) == [] and atom._tracked == {} and atom._awaiting_plan == set()


async def test_the_systems_position_beside_it_is_still_moved():
    atom, bus = await L._new()
    await atom._on_plan({"tickets": []})
    for _ in range(2):
        await atom._on_positions({"positions": [_owner(7, 4030.0), dict(L._pos(2, 4020.0), magic=20260801)]})
    assert L._sent(bus) == [2] and set(atom._tracked) == {"2"}
