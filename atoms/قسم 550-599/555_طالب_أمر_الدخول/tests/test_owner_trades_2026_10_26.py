"""2026-10-26 (owner's law and answer, seal "NQ": "it must know the owner's trades and open nothing on any pair that has a
trade of mine"): the entry gate is the one place the owner's trades are read -- no entry, either side, on a symbol where
the owner has an open trade in any account; and every other count here is the system's own."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_red_lines_2026_10_23 as R  # noqa: E402
from shared import red_lines  # noqa: E402

FRIDAY = R.FRIDAY
OURS, OWNER = 20260801, 0


@pytest.fixture(autouse=True)
def _real_window(monkeypatch):
    monkeypatch.setattr(red_lines, "session_state", R.REAL_SESSION_STATE)
    monkeypatch.setattr(R.T._sizing, "min_stop_pips", lambda symbol: 1.0)


def owners(account, side, symbol="BTCUSD", profit=-40.0, magic=OWNER):
    return {"account_id": account, "positions": [
        {"account_id": account, "ticket": 9, "symbol": symbol, "side": side, "profit": profit, "magic": magic}]}


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_nothing_opens_either_way_on_a_symbol_with_the_owners_trade(side):
    orders, states = R.run(FRIDAY, side=side, positions=owners("ACC", "BUY"))
    assert orders == [] and states[-1]["reason"] == "OWNER_POSITION_OPEN" and states[-1]["owner_positions"] == 1


def test_the_owners_trade_in_another_account_holds_the_symbol_too():
    orders, states = R.run(FRIDAY, side="buy", positions=owners("OTHER", "BUY"),
                           more_positions={"account_id": "ACC", "positions": []})
    assert orders == [] and states[-1]["reason"] == "OWNER_POSITION_OPEN"


def test_another_symbol_beside_the_owners_trade_is_free():
    orders, _ = R.run(FRIDAY, side="buy", positions=owners("ACC", "BUY", symbol="XAUUSD"))
    assert len(orders) == 1


def test_the_owners_closed_trade_frees_the_symbol():
    orders, _ = R.run(FRIDAY, side="buy", positions=owners("ACC", "BUY"),
                      more_positions={"account_id": "ACC", "positions": []})
    assert len(orders) == 1


def test_the_systems_own_counts_never_hold_the_owners():
    atom, _ = R.T.build()
    R.T.feed(atom, "_on_positions", owners("OTHER", "SELL"))
    assert atom._open_by_account == {"OTHER": {}} and atom._sides_by_account == {"OTHER": {}}
    assert atom._losing_open == {"OTHER": set()} and atom._open_counts == {}
    assert atom._owner_by_account == {"OTHER": {"BTCUSD": 1}}


def test_the_systems_own_position_still_holds_its_symbol():
    orders, states = R.run(FRIDAY, side="sell", positions=owners("ACC", "BUY", magic=OURS))
    assert orders == [] and states[-1]["reason"] == "POSITION_ALREADY_OPEN"
