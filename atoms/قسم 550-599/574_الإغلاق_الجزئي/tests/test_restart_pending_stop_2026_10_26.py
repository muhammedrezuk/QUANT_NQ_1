"""2026-10-26 (owner seal "NQ" on the project-audit fixes, item 8): the deferred stop survives a restart. The part is closed
at the first target, the core restarts before the platform shows the smaller volume, and the stop must still move once it
does -- before, the snapshot carried it but the restore dropped it while the stage came back advanced."""
import importlib.util as _ilu
import json
import sys
from pathlib import Path as _Path

# The helpers of this atom's own 2026-10-02 test, by path under a name of their own: 577 has a test file of the same name.
_spec = _ilu.spec_from_file_location("_t574_fix_b_restart", _Path(__file__).resolve().parent / "test_fix_2026_10_02b.py")
F = _ilu.module_from_spec(_spec)
sys.modules["_t574_fix_b_restart"] = F
_spec.loader.exec_module(F)

stage_apply = sys.modules["stage_apply"]


async def _after_first_part():
    atom, bus = await F._new()
    await bus.deliver("feed.mt5.tick", F._mt5(51355.3, 51356.0))
    await atom._on_positions(F._us30(51355.3))
    await atom._on_positions(F._us30(51357.10))                      # first target touched: the part goes out
    assert [p["action"] for p in F._outs(bus)] == ["CLOSE_PARTIAL"]
    return json.loads(json.dumps(await atom.snapshot()))             # as written to disk


async def test_the_deferred_stop_moves_after_a_restart():
    state = await _after_first_part()
    atom, bus = await F._new()
    await atom.restore(state)
    await bus.deliver("feed.mt5.tick", F._mt5(51357.10, 51357.8))
    await atom._on_positions(F._us30(51357.10, volume=0.7))          # the platform shows it smaller
    actions = [p["action"] for p in F._outs(bus)]
    assert actions == ["MODIFY_SL"], actions                         # the stop moves; the part is not sent again


async def test_the_deferred_stop_is_still_withheld_if_the_part_never_closed():
    state = await _after_first_part()
    atom, bus = await F._new()
    await atom.restore(state)
    await bus.deliver("feed.mt5.tick", F._mt5(51357.10, 51357.8))
    for _ in range(40):
        await atom._on_positions(F._us30(51357.10, volume=1.0))      # never smaller
    assert not [p for p in F._outs(bus) if p["action"] == "MODIFY_SL"]


def test_a_damaged_deferred_stop_is_not_restored():
    good = {"body": {"action": "MODIFY_SL", "stop_loss": 51356.0}, "cycles": 2, "volume_before": 1.0, "stage": 1}
    assert stage_apply.restore_pending_stop(good)["volume_before"] == 1.0
    for bad in (None, "x", {}, dict(good, body={"action": "CLOSE", "stop_loss": 1.0}),
                dict(good, body={"action": "MODIFY_SL", "stop_loss": 0}), dict(good, volume_before=None),
                dict(good, stage="1"), dict(good, stage=True), dict(good, cycles=1.5)):
        assert stage_apply.restore_pending_stop(bad) is None, bad
