"""The account limits of 2026-10-23 (sealed red lines, laws 7-10) at the entry gate: 509's state refuses entries -- the total
drawdown, the global daily limit, a pair's daily limit -- and a missing or stale state, or an account not known, refuses too."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import conftest  # noqa: E402
import test_atom as T  # noqa: E402
from shared import account_limits as al  # noqa: E402

MOMENT = 1_792_500_000.0


@pytest.fixture(autouse=True)
def _real_limits(monkeypatch):
    monkeypatch.setattr(al, "entry_block", conftest.REAL_LIMITS_BLOCK)
    monkeypatch.setattr(T._sizing, "min_stop_pips", lambda symbol: 1.0)   # toy prices, as in test_atom


def limits(**account):
    view = {"known": True, "total_blocked": False, "daily_blocked": False, "blocked_pairs": [], **account}
    return {"id": "account_limits", "official_time": MOMENT - 5, "accounts": {"ACC": view}}


def run(state=None, symbol="BTCUSD"):
    atom, bus = T.build()
    T.feed(atom, "_on_pulse", {"official_time": MOMENT})
    if state is not None:
        T.feed(atom, "_on_limits", state)
    T.feed(atom, "_on_size", {**T.size(), "symbol": symbol})
    T.feed(atom, "_on_decision", {**T.decision("buy"), "symbol": symbol})
    return bus.of("execution.order.requested"), bus.of("execution.entry.state")


def test_without_509s_state_no_entry():
    orders, states = run()
    assert orders == [] and states[-1]["reason"] == al.REASON_UNKNOWN, states[-1]


def test_a_clear_state_lets_the_order_out():
    assert len(run(limits())[0]) == 1


def test_a_stale_state_or_an_unknown_account_refuses():
    stale = {**limits(), "official_time": MOMENT - 600}
    assert run(stale)[1][-1]["reason"] == al.REASON_UNKNOWN
    assert run(limits(known=False))[1][-1]["reason"] == al.REASON_UNKNOWN


def test_total_drawdown_and_the_global_daily_limit_refuse_every_symbol():
    assert run(limits(total_blocked=True))[1][-1]["reason"] == al.REASON_TOTAL
    assert run(limits(daily_blocked=True), symbol="EURUSD")[1][-1]["reason"] == al.REASON_DAILY


def test_a_pairs_daily_limit_refuses_that_pair_only():
    state = limits(blocked_pairs=["BTCUSD"], pair_loss={"BTCUSD": 151.0}, pair_limit={"BTCUSD": 150.0})
    orders, states = run(state)
    assert orders == [] and states[-1]["reason"] == al.REASON_PAIR and states[-1]["pair_loss"] == 151.0
    assert len(run(state, symbol="EURUSD")[0]) == 1
