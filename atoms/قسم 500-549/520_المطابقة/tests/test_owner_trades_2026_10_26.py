"""2026-10-26 (owner's law and answer, seal "NQ"): reconciliation is the system's own -- the owner's manual position is
never an "extra at the broker", and an account holding only the owner's positions is empty for the system."""
import importlib.util
import sys
import tempfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_t520_owner", Path(__file__).resolve().parent / "test_atom.py")
T = importlib.util.module_from_spec(_spec)
sys.modules["_t520_owner"] = T
_spec.loader.exec_module(T)
mod = T.mod


async def test_the_owners_position_is_not_an_extra_at_the_broker():
    with tempfile.TemporaryDirectory() as t:
        b = T.Bus(); a = mod.Atom(); await a.initialize(b.ctx(str(Path(t) / "desired.json"))); await a.start()
        await a._on_desired({"account_id": "A", "broker": "BR", "symbol": "USTEC", "version": 1, "timestamp": 1, "legs": []})
        await a._on_actual({"source": "broker", "timestamp": 2, "account_id": "A", "broker": "BR", "positions": [
            {"account_id": "A", "broker": "BR", "symbol": "USTEC", "ticket": "2036216648", "side": "BUY", "volume": 20,
             "magic": 0}]})
        outs = [p for n, p in b.events if n == mod.EVENT_OUT]
        assert any(p.get("status") == "MATCH_EMPTY_ACCOUNT" for p in outs), outs
        st = a.state(mod.scope("A", "USTEC", "BR"))
        assert st["status"] == "MATCH" and "EXTRA_AT_BROKER" not in st["classification_counts"], st


async def test_the_systems_extra_position_still_alarms_beside_the_owners():
    with tempfile.TemporaryDirectory() as t:
        b = T.Bus(); a = mod.Atom(); await a.initialize(b.ctx(str(Path(t) / "desired.json"))); await a.start()
        await a._on_desired({"account_id": "A", "broker": "BR", "symbol": "USTEC", "version": 1, "timestamp": 1, "legs": []})
        await a._on_actual({"source": "broker", "timestamp": 2, "account_id": "A", "broker": "BR", "positions": [
            {"account_id": "A", "broker": "BR", "symbol": "USTEC", "ticket": "1", "side": "BUY", "volume": 1, "magic": 0},
            {"account_id": "A", "broker": "BR", "symbol": "USTEC", "ticket": "2", "side": "BUY", "volume": 1}]})
        st = a.state(mod.scope("A", "USTEC", "BR"))
        assert st["status"] == "ATTENTION" and st["classification_counts"] == {"EXTRA_AT_BROKER": 1}, st
