"""2026-10-26 (owner's law, seal "NQ"; and the review of the same day): the drawdown is the system's own realized curve --
the sum of its trade results here, on one path -- not the account's equity with the owner's trades in it, and not a
floating that arrives at another moment than its close. A peak kept on the equity is started again once."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("_t666_owner", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t666_owner"] = m
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

    def last(self):
        return [p for n, p in self.e if n == m.EVENT_OUT][-1]


async def _new():
    b = B(); a = m.Atom()
    await a.initialize(m.AtomContext(666, {}, L(), b.publish, b.subscribe)); await a.start()
    return a, b


async def test_the_drawdown_follows_the_systems_realized_curve():
    a, b = await _new()
    for i, profit in enumerate((100.0, -60.0, 30.0, -90.0)):
        await a._on_trade({"account_id": "A", "profit": profit, "event_id": "e%d" % i})
    out = b.last()
    assert out["max_drawdown"] == 120.0 and out["drawdown_basis"] == m.DRAWDOWN_BASIS   # peak 100, low -20


async def test_the_equity_and_the_net_move_nothing():
    a, b = await _new()
    await a._on_trade({"account_id": "A", "profit": 300.0, "event_id": "w"})
    await a._on_pnl({"account_id": "A", "net_pnl": 0.0, "equity": 9000.0})    # the floating gone before the close arrived
    await a._on_pnl({"account_id": "A", "net_pnl": -250.0, "equity": 9700.0})  # a restart reading the floating late
    assert b.last()["max_drawdown"] == 0.0


async def test_a_peak_kept_on_the_equity_starts_again_and_the_trades_stay():
    a, b = await _new()
    old = {"version": "1.1.0", "stats": {"A": {"trades": 3, "wins": 1, "losses": 2, "profit": -16.0,
                                               "peak": 10808.04, "drawdown": 10808.04}}}
    await a.restore(old)
    await a._on_pnl({"account_id": "A", "net_pnl": -16.0})
    out = b.last()
    assert out["trades"] == 3 and out["realized_profit"] == -16.0 and out["max_drawdown"] == 0.0
    await a._on_trade({"account_id": "A", "profit": -10.0, "event_id": "x"})
    state = await a.snapshot()
    c, cb = await _new()
    await c.restore(state)
    await c._on_trade({"account_id": "A", "profit": -5.0, "event_id": "y"})
    assert cb.last()["max_drawdown"] == 15.0
