"""2026-10-26 (owner's law, seal "NQ"): the open positions here are the system's alone; the owner's are only counted apart."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("_t659_owner", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t659_owner"] = m
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


async def test_only_the_systems_positions_are_listed():
    b = B(); a = m.Atom()
    await a.initialize(m.AtomContext(659, {}, L(), b.publish, b.subscribe)); await a.start()
    await a._on({"account_id": "A", "positions": [
        {"account_id": "A", "symbol": "XAUUSD", "ticket": 1, "volume": 0.1, "profit": -2.0, "magic": 20260801},
        {"account_id": "A", "symbol": "USTEC", "ticket": 2, "volume": 20, "profit": 500.0, "magic": 0}]})
    out = [p for n, p in b.e if n == m.EVENT_OUT][-1]
    assert out["open_count"] == 1 and out["floating_pnl"] == -2.0 and out["by_symbol"] == {"XAUUSD": 0.1}
    assert [p["ticket"] for p in out["positions"]] == [1] and out["owner_open_count"] == 1
    await a._on({"account_id": "A", "positions": [
        {"account_id": "A", "symbol": "USTEC", "ticket": 2, "volume": 20, "profit": 500.0, "magic": 0}]})
    out = [p for n, p in b.e if n == m.EVENT_OUT][-1]
    assert out["open_count"] == 0 and out["positions"] == [] and out["owner_open_count"] == 1


async def test_a_complete_empty_picture_after_a_start_is_published():
    """2026-10-26, after the hot reload: 609 sends each account a complete picture with its number; a flat account must be
    known at once, not only after a position appears."""
    b = B(); a = m.Atom()
    await a.initialize(m.AtomContext(659, {}, L(), b.publish, b.subscribe)); await a.start()
    await a._on({"account_id": "A", "positions": [], "complete": True})
    out = [p for n, p in b.e if n == m.EVENT_OUT][-1]
    assert out["account_id"] == "A" and out["open_count"] == 0 and out["owner_open_count"] == 0
