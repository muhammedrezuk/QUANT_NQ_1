"""2026-10-26 (owner's law, seal "NQ"): the owner's own trades have nothing to do with the system -- 577 never tightens,
trails, announces or keeps a picture of a position that is not the system's; and a refusal saying the position is not the
system's (foreign magic, ownership mismatch) is final, never sent again."""
import importlib.util as _ilu
import json
import sys
from pathlib import Path as _Path

# The helpers of this atom's own 2026-10-02 test, by path under a name of their own: 574 has a test file of the same name.
_spec = _ilu.spec_from_file_location("_t577_fix_b_owner", _Path(__file__).resolve().parent / "test_fix_2026_10_02b.py")
F = _ilu.module_from_spec(_spec)
sys.modules["_t577_fix_b_owner"] = F
_spec.loader.exec_module(F)

OURS = 20260801


def _owner(current=3996.0, **extra):
    """The owner's manual position: magic 0, its stop far beyond the system's cap (200$ > 105$)."""
    row = dict(F._pos(current), ticket=21, magic=0)
    row.update(extra)
    return row


async def test_the_owners_position_is_never_tightened_kept_or_announced():
    atom, bus = await F._new()
    await atom._on_positions({"positions": [_owner(), _owner(stop_loss=0.0, ticket=22)]})
    await bus.deliver("feed.mt5.tick", {"account_id": "A1", "symbol": "XAUUSD", "bid": 3996.0, "ask": 3996.5})
    assert not F._sent(bus), "a command went out on the owner's position"
    assert not atom._snapshots and not atom._legs and not atom._unprotected and not atom._capped
    assert atom._cap_attempts == {} and atom._cap_pending == {}


async def test_the_systems_position_beside_the_owners_is_still_tightened():
    atom, bus = await F._new()
    await atom._on_positions({"positions": [_owner(), F._pos(3996.0)]})
    out = F._sent(bus)
    assert len(out) == 1 and out[0]["ticket"] == 11 and out[0]["magic"] == OURS, out


async def test_a_row_without_a_magic_is_the_systems():
    atom, bus = await F._new()
    row = F._pos(3996.0)
    del row["magic"]
    await atom._on_positions({"positions": [row]})
    assert len(F._sent(bus)) == 1, "a position of ours without the field was left unmanaged"


async def _refused(reason, magic=0):
    """The refusal carries the refused command back (575: `{**payload, "reason": ...}`), its magic with it."""
    atom, bus = await F._new()
    await atom._on_positions({"positions": [F._pos(3996.0)]})
    rid = F._sent(bus)[0]["request_id"]
    await bus.deliver("execution.command.failed", {"request_id": rid, "reason": reason, "magic": magic})
    return atom, bus


async def test_a_refusal_on_the_systems_own_position_is_sent_again():
    """Review 2026-10-26: a refusal on a position the system counts as its own (its magic, or none) never switches its
    loss cap off -- it waits and is computed again, as before."""
    for magic in (OURS, None):
        atom, bus = await _refused("MISSING_OR_FOREIGN_MAGIC", magic=magic)
        assert not atom._cap_final and 11 in atom._cap_retry_at, magic
        atom._cap_retry_at[11] = 0.0
        await atom._on_positions({"positions": [F._pos(3996.0)]})
        assert len(F._sent(bus)) == 2, magic


async def test_a_foreign_magic_refusal_is_final():
    for reason in ("MISSING_OR_FOREIGN_MAGIC", "POSITION_OWNERSHIP_MISMATCH", "COMMAND_OWNERSHIP_MISMATCH"):
        atom, bus = await _refused(reason)
        assert atom._cap_final == {11: reason} and 11 not in atom._cap_retry_at, reason
        for _ in range(3):
            await atom._on_positions({"positions": [F._pos(3996.0)]})
            await bus.deliver("feed.mt5.tick", {"account_id": "A1", "symbol": "XAUUSD", "bid": 3996.0, "ask": 3996.5})
        assert len(F._sent(bus)) == 1, "sent again after a final refusal: %s" % reason
        assert "ليس_للمنظومة=1" in (await atom.health_check()).message


async def test_a_passing_refusal_is_still_sent_again():
    atom, bus = await _refused("RETCODE_10016")
    assert not atom._cap_final and 11 in atom._cap_retry_at
    atom._cap_retry_at[11] = 0.0
    await atom._on_positions({"positions": [F._pos(3996.0)]})
    assert len(F._sent(bus)) == 2


async def test_a_final_refusal_survives_a_restart_and_leaves_with_its_ticket():
    atom, _ = await _refused("MISSING_OR_FOREIGN_MAGIC")
    state = json.loads(json.dumps(await atom.snapshot()))
    again, bus = await F._new()
    await again.restore(state)
    await again._on_positions({"positions": [F._pos(3996.0)]})
    assert again._cap_final == {11: "MISSING_OR_FOREIGN_MAGIC"} and not F._sent(bus)
    await again._on_positions({"positions": []})
    assert again._cap_final == {}
