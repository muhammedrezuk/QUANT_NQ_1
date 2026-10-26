"""2026-10-26 (owner seal "NQ" on the project-audit fixes, items 7 and 9): a tightening the broker refused is computed and sent
again after a doubling wait, up to a bounded number of tries; and a position of ours without a stop is announced instead of
being skipped in silence."""
import importlib.util as _ilu
import json
import sys
from pathlib import Path as _Path

# The helpers of this atom's own 2026-10-02 test, by path under a name of their own: 574 has a test file of the same name.
_spec = _ilu.spec_from_file_location("_t577_fix_b_guard", _Path(__file__).resolve().parent / "test_fix_2026_10_02b.py")
F = _ilu.module_from_spec(_spec)
sys.modules["_t577_fix_b_guard"] = F
_spec.loader.exec_module(F)

guard = sys.modules["stop_maintenance_guard"]
OURS = 20260801


async def _tightened():
    atom, bus = await F._new()
    await atom._on_positions({"positions": [F._pos(3996.0)]})
    out = F._sent(bus)
    assert len(out) == 1 and out[0]["request_id"].startswith("riskcap-11-"), out
    return atom, bus, out[0]["request_id"]


async def test_a_refused_tightening_is_sent_again_after_its_wait():
    atom, bus, rid = await _tightened()
    await bus.deliver("execution.command.failed", {"request_id": rid, "reason": "RETCODE_10016"})
    await atom._on_positions({"positions": [F._pos(3996.0)]})
    assert len(F._sent(bus)) == 1, "resent before its wait"
    atom._cap_retry_at[11] = 0.0                                   # the wait is over
    await atom._on_positions({"positions": [F._pos(3996.0)]})
    out = F._sent(bus)
    assert len(out) == 2 and out[1]["request_id"] != rid and abs(out[1]["stop_loss"] - 3995.0) < 1e-9, out
    assert atom._cap_attempts[11] == 2 and atom._cap_retried == 1


async def test_an_acknowledged_tightening_clears_its_tries():
    atom, bus, rid = await _tightened()
    await bus.deliver("execution.command.ack", {"request_id": rid, "status": "DONE"})
    assert 11 not in atom._cap_attempts and not atom._cap_pending


async def test_tries_are_bounded_and_the_last_refusal_is_announced():
    atom, bus, rid = await _tightened()
    atom._cap_attempts[11] = guard.MAX_ATTEMPTS
    await bus.deliver("execution.command.failed", {"request_id": rid, "reason": "STALE_3s"})
    assert atom._cap_abandoned == 1 and 11 not in atom._cap_retry_at and 11 in atom._capped


async def test_results_of_other_commands_are_left_alone():
    atom, bus, rid = await _tightened()
    await bus.deliver("execution.command.failed", {"request_id": "manage-A1-11-abc", "reason": "X"})
    assert atom._cap_refused == 0 and atom._cap_foreign == 1 and rid in atom._cap_pending


async def test_a_position_of_ours_without_a_stop_is_announced():
    atom, bus = await F._new()
    naked = dict(F._pos(3996.0), stop_loss=0.0, magic=OURS)
    manual = dict(F._pos(3996.0), ticket=12, stop_loss=0.0, magic=7)
    await atom._on_positions({"positions": [naked, manual]})
    health = await atom.health_check()
    assert list(atom._unprotected) == [11] and "بلا_وقف=1" in health.message, health.message
    assert health.state.name == "DEGRADED"
    await atom._on_positions({"positions": [dict(naked, stop_loss=3990.0)]})
    assert not atom._unprotected and (await atom.health_check()).state.name == "HEALTHY"


async def test_tries_and_waits_survive_a_restart():
    atom, bus, rid = await _tightened()
    await bus.deliver("execution.command.failed", {"request_id": rid, "reason": "RETCODE_10016"})
    state = json.loads(json.dumps(await atom.snapshot()))
    again, _ = await F._new()
    await again.restore(state)
    assert again._cap_attempts == {11: 1} and 11 in again._cap_retry_at and 11 in again._capped
