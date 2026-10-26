"""2026-10-26 (owner's law, seal "NQ"): the owner's own trades have nothing to do with the system -- 574 never tracks, plans,
closes a part of or moves the stop of a position that is not the system's, and never names it to 572."""
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))
import test_fix_2026_10_02b as F  # noqa: E402

PLAN = "management.level_plan.state"


def _owner(price, volume=1.0):
    payload = F._us30(price, volume=volume)
    payload["positions"] = [dict(row, magic=0) for row in payload["positions"]]
    return payload


async def test_the_owners_position_is_never_divided_or_named():
    atom, bus = await F._new()
    await bus.deliver("feed.mt5.tick", F._mt5(51355.3, 51356.0))
    for price in (51355.3, 51357.10, 51358.20, 51359.30):           # every target touched
        await atom._on_positions(_owner(price))
    assert F._outs(bus) == [] and atom._tracked == {}
    plans = [p for n, p in bus.published if n == PLAN]
    assert all(not p.get("tickets") for p in plans), plans


async def test_the_systems_position_is_still_divided():
    atom, bus = await F._new()
    await bus.deliver("feed.mt5.tick", F._mt5(51355.3, 51356.0))
    system = F._us30(51355.3)
    system["positions"] = [dict(row, magic=20260801) for row in system["positions"]]
    await atom._on_positions(system)
    touched = F._us30(51357.10)
    touched["positions"] = [dict(row, magic=20260801) for row in touched["positions"]]
    await atom._on_positions(touched)
    assert [p["action"] for p in F._outs(bus)] == ["CLOSE_PARTIAL"]
