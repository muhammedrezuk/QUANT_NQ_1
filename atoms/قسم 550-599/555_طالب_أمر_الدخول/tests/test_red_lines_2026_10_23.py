"""The sealed red lines of 2026-10-23 at the entry gate: no hedge with another account (law 13) and each account's positions
counted on their own; no symbol on the weekend, bitcoin included (law 23); a red news window blocks the assets holding the
item's currency, USD every symbol (laws 24-25); and the expected crossing cost inside the stop when sizing (laws 2-3)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_atom as T  # noqa: E402
from shared import red_lines  # noqa: E402

REAL_SESSION_STATE = red_lines.session_state   # read at import, before any fixture holds the window open


def at(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


FRIDAY = at("2026-10-16T12:00")     # Friday 15:00 Turkey: London and the general window are open
SATURDAY = at("2026-10-17T12:00")   # Saturday 15:00 Turkey


@pytest.fixture(autouse=True)
def _real_window(monkeypatch):
    monkeypatch.setattr(red_lines, "session_state", REAL_SESSION_STATE)
    monkeypatch.setattr(T._sizing, "min_stop_pips", lambda symbol: 1.0)   # toy prices, as in test_atom


def run(moment, symbol="BTCUSD", side="buy", calendar=None, positions=None, more_positions=None):
    atom, bus = T.build()
    T.feed(atom, "_on_pulse", {"official_time": moment})
    if calendar is not None:
        T.feed(atom, "_on_calendar", calendar)
    if positions is not None:
        T.feed(atom, "_on_positions", positions)
    if more_positions is not None:
        T.feed(atom, "_on_positions", more_positions)
    T.feed(atom, "_on_size", {**T.size(), "symbol": symbol})
    T.feed(atom, "_on_decision", {**T.decision(side), "symbol": symbol})
    return bus.of("execution.order.requested"), bus.of("execution.entry.state")


def held(account, side, profit=3.0, symbol="BTCUSD"):
    return {"account_id": account, "positions": [
        {"account_id": account, "ticket": 7, "symbol": symbol, "side": side, "profit": profit}]}


def test_law_13_the_opposite_side_open_in_another_account_is_refused():
    orders, states = run(FRIDAY, side="buy", positions=held("OTHER", "SELL"))
    assert orders == [] and states[-1]["reason"] == "HEDGE_WITH_OTHER_ACCOUNT", states[-1]
    assert states[-1]["other_account"] == "OTHER"


def test_law_13_the_same_side_in_another_account_is_left_to_law_11():
    orders, _ = run(FRIDAY, side="buy", positions=held("OTHER", "BUY"))
    assert len(orders) == 1


def test_law_13_another_accounts_picture_no_longer_erases_this_accounts_position():
    # 609 publishes one picture per account; the second used to overwrite the first's count
    orders, states = run(FRIDAY, side="sell", positions=held("ACC", "BUY"),
                         more_positions={"account_id": "OTHER", "positions": []})
    assert orders == [] and states[-1]["reason"] == "POSITION_ALREADY_OPEN", states[-1]


def test_law_23_bitcoin_is_refused_on_saturday():
    orders, states = run(SATURDAY)
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_WINDOW, states[-1]


def calendar(*currencies):
    return {"utc": FRIDAY - 5, "in_event_window": bool(currencies), "status": "BLOCKED" if currencies else "CLEAR",
            "blocked_currencies": list(currencies)}


def test_law_24_a_red_euro_item_blocks_the_euro_pair_and_not_bitcoin():
    orders, states = run(FRIDAY, symbol="EURUSD", calendar=calendar("EUR"))
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_NEWS, states[-1]
    assert len(run(FRIDAY, symbol="BTCUSD", calendar=calendar("EUR"))[0]) == 1


def test_law_24_a_red_dollar_item_blocks_every_symbol():
    for symbol in ("BTCUSD", "EURUSD"):
        orders, states = run(FRIDAY, symbol=symbol, calendar=calendar("USD"))
        assert orders == [] and states[-1]["reason"] == red_lines.REASON_NEWS, (symbol, states[-1])


def test_law_24_the_nearest_red_line_counts_only_the_assets_currencies():
    new_york = at("2026-10-16T14:00")   # Friday 10:00 New York: six hours to the close
    euro_item = {"title": "German ZEW", "currency": "EUR", "red_line_from": new_york + 600}
    state = {"utc": new_york, "next_blocking": [euro_item], "blocked_currencies": []}
    assert red_lines.seconds_to_red_line(new_york, "USTEC", state) == 6 * 3600
    assert red_lines.seconds_to_red_line(new_york, "EURUSD", state) == 600
    assert red_lines.seconds_to_red_line(new_york, "USTEC", {**state, "next_blocking": [
        {**euro_item, "currency": "USD"}]}) == 600


def test_laws_2_3_the_expected_crossing_cost_sits_inside_the_stop():
    def lot(symbol, price, spread, distance, tick_value):
        size = {"symbol": symbol, "close": price, "spread": spread, "risk_amount": 100.0, "tick_value": tick_value,
                "tick_size": 1.0, "commission_per_lot": 0.0, "volume_step": 0.01, "volume_min": 0.01}
        return T._sizing._lot_for_stop(size, distance), size["_cost_used"]
    # the Dow has no slippage record: the worst measured (bitcoin's entry, 0.00327%) sits on top of the spread
    dow, dow_cost = lot("US30", 47000.0, 2.0, 40.0, 1.0)
    assert dow_cost == pytest.approx(2.0 + 47000.0 * 0.0000327) and dow == 2.29
    assert 90.0 <= dow * (40.0 + dow_cost) <= 100.0
    # the Nasdaq's measured slippage (0.26 points) is inside its spread (1.5): its lot does not change
    nasdaq, nasdaq_cost = lot("USTEC", 25000.0, 1.5, 30.0, 1.0)
    assert nasdaq_cost == 1.5 and nasdaq == 3.17
