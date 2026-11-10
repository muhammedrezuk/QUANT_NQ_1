"""2026-10-23 (owner's sealed red lines, law 6): at each target the part is closed at market *first* and the stop moves only
after the platform shows the smaller volume -- the second and third targets the same. A single-target ticket (its third
inside the round-trip cost: no parts, no stop move) stays on 574's list too, so 572 does not secure it at 1R."""
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))
import test_fix_2026_10_02b as F  # noqa: E402

PLAN = "management.level_plan.state"


def _published(bus):
    return [(n, p) for n, p in bus.published]


async def test_each_target_closes_its_part_before_any_stop_moves():
    atom, bus = await F._new()
    await bus.deliver("feed.mt5.tick", F._mt5(51355.3, 51356.0))
    await atom._on_positions(F._us30(51355.3))
    await atom._on_positions(F._us30(51357.10))                      # first target touched
    assert [p["action"] for p in F._outs(bus)] == ["CLOSE_PARTIAL"]   # the part, and no stop yet
    await atom._on_positions(F._us30(51357.10, volume=0.7))          # the platform shows it smaller
    assert [p["action"] for p in F._outs(bus)] == ["CLOSE_PARTIAL", "MODIFY_SL"]
    await atom._on_positions(F._us30(51358.20, volume=0.7))          # second target touched
    assert [p["action"] for p in F._outs(bus)][2:] == ["CLOSE_PARTIAL"]
    await atom._on_positions(F._us30(51358.20, volume=0.4))
    assert [p["action"] for p in F._outs(bus)][2:] == ["CLOSE_PARTIAL", "MODIFY_SL"]
    await atom._on_positions(F._us30(51359.30, volume=0.4))          # third target: out in full
    assert F._outs(bus)[-1]["action"] == "CLOSE"


async def test_a_single_target_ticket_stays_on_the_list_for_572():
    atom, bus = await F._new()
    await bus.deliver("feed.mt5.tick", F._mt5(20000.0, 20000.9, symbol="USTEC"))
    pos = {"positions": [{"account_id": "A", "ticket": 1966045088, "symbol": "USTEC", "side": "BUY", "volume": 1.0,
                          "entry_price": 20000.9, "current_price": 20000.0, "stop_loss": 19976.9,
                          "take_profit": 20003.09}]}
    await atom._on_positions(pos)
    await atom._on_positions(pos)
    assert atom._single_target == 1
    plans = [p for n, p in _published(bus) if n == PLAN]
    assert plans and plans[-1]["tickets"] == ["1966045088"], plans
