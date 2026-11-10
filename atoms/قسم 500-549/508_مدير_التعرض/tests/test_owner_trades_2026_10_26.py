"""2026-10-26 (owner's law and answer, seal "NQ"): exposure is the system's own -- the owner's manual position never adds
to it, never trips the exposure halt, and an owner's position the system cannot price never makes the picture unknown."""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_t508_owner", Path(__file__).resolve().parent / "test_atom.py")
T = importlib.util.module_from_spec(_spec)
sys.modules["_t508_owner"] = T
_spec.loader.exec_module(T)


def _with_magic(payload, *magics):
    for row, magic in zip(payload["positions"], magics):
        row["magic"] = magic
    return payload


async def test_the_owners_position_adds_no_exposure_and_trips_nothing():
    atom, bus = await T._new(max_pct=50.0)
    await atom._on_specs(T._specs(X=1.0))
    await atom._on_account({"account_id": "A1", "broker": "BR"})
    await atom._on_truth_equity({"account_id": "A1", "broker": "BR", "equity": 1000.0})
    await atom._on_positions(_with_magic(T._positions(("A1", "X", 6.0, 100.0), ("A1", "X", 2.0, 100.0)), 0, 20260801))
    st = T._last(bus, T.EVENT_OUT, "A1")
    assert st["notional"] == 200.0 and st["open_positions"] == 1 and st["breached"] is False, st
    assert T._last(bus, T.EVENT_HALT_REQUEST, "A1") is None


async def test_an_owners_position_without_specs_never_makes_the_picture_unknown():
    atom, bus = await T._new(max_pct=50.0)
    await atom._on_specs(T._specs(X=1.0))
    await atom._on_account({"account_id": "A1", "broker": "BR"})
    await atom._on_truth_equity({"account_id": "A1", "broker": "BR", "equity": 1000.0})
    await atom._on_positions(_with_magic(T._positions(("A1", "UNPRICED", 1.0, 100.0)), 0))
    st = T._last(bus, T.EVENT_OUT, "A1")
    assert st["status"] == "OK" and st["unknown_position_count"] == 0, st
    # Review 2026-10-26: the rows the picture carries as unknown (no account) are filtered the same way.
    payload = T._positions(("A1", "X", 1.0, 100.0))
    payload["positions"][0]["magic"] = 20260801
    payload["unknown_positions"] = [{"ticket": 77, "symbol": "X", "volume": 1.0, "magic": 0}]
    await atom._on_positions(payload)
    st = T._last(bus, T.EVENT_OUT, "A1")
    assert st["status"] == "OK" and st["unknown_position_count"] == 0 and st["open_positions"] == 1, st
