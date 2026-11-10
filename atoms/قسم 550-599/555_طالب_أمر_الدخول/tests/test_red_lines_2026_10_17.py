"""The red lines and the waits at the entry gate (owner seals 2026-10-17, steps 6-11): every asset on its own exchange's
window (bitcoin on the general one: Sydney open -> 16:00 New York since 2026-10-25, 15:00 until then), the first 15 minutes of
it closed, a red USD news window closed, 15 minutes after a trade on the asset, and the funder's cross-account waits after a
loss. 2026-10-25 (owner seal, law 21): the time-enough check is gone -- no new entry in the window's last hour instead."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_atom as T  # noqa: E402
from shared import red_lines  # noqa: E402

REAL_SESSION_STATE = red_lines.session_state   # read at import, before any fixture holds the window open
REAL_IN_LAST_HOUR = red_lines.in_last_hour


def at(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


INSIDE = at("2026-10-16T12:00")    # Friday 15:00 Turkey: bitcoin's general window is open
OUTSIDE = at("2026-10-16T20:00")   # Friday 23:00 Turkey: 16:00 New York, the general window's close since 2026-10-25
# 2026-10-23 (law 23): Friday 23:05 UTC is Saturday's Sydney open -- bitcoin is closed on the weekend now, so the first quarter
# hour is checked on Monday's Sydney open (Sunday 23:05 UTC, 02:05 Turkey on Monday).
SYDNEY_OPEN = at("2026-10-18T23:05")


@pytest.fixture(autouse=True)
def _real_window(monkeypatch):
    monkeypatch.setattr(red_lines, "session_state", REAL_SESSION_STATE)
    monkeypatch.setattr(red_lines, "in_last_hour", REAL_IN_LAST_HOUR)
    monkeypatch.setattr(T._sizing, "min_stop_pips", lambda symbol: 1.0)   # toy prices, as in test_atom


def run(moment: float, calendar: dict | None = None, before=None):
    atom, bus = T.build()
    T.feed(atom, "_on_pulse", {"official_time": moment})
    if calendar is not None:
        T.feed(atom, "_on_calendar", calendar)
    if before is not None:
        before(atom)
    T.feed(atom, "_on_size", T.size())
    T.feed(atom, "_on_decision", T.decision("buy"))
    return bus.of("execution.order.requested"), bus.of("execution.entry.state")


def test_inside_the_window_the_order_goes_out():
    orders, _ = run(INSIDE)
    assert len(orders) == 1


def test_at_16_new_york_bitcoin_too_is_refused():
    orders, states = run(OUTSIDE)
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_WINDOW, states[-1]


def test_first_quarter_hour_after_sydney_open_is_refused():
    orders, states = run(SYDNEY_OPEN)
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_FIRST_MINUTES, states[-1]


def test_red_usd_news_window_refuses_entry():
    orders, states = run(INSIDE, {"utc": INSIDE - 5, "in_event_window": True, "status": "BLOCKED"})
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_NEWS, states[-1]


def test_stale_or_clear_calendar_does_not_block():
    assert len(run(INSIDE, {"utc": INSIDE - 600, "in_event_window": True, "status": "BLOCKED"})[0]) == 1
    assert len(run(INSIDE, {"utc": INSIDE - 5, "in_event_window": False, "status": "CLEAR"})[0]) == 1


def closed(account: str, profit: float, ago_s: float):
    def feed(atom):
        T.feed(atom, "_on_trade", {"event_type": "CLOSED", "account_id": account, "symbol": "BTCUSD",
                                    "profit": profit, "timestamp": INSIDE - ago_s})
    return feed


def test_seventy_five_minutes_after_a_trade_on_the_asset():
    # 2026-10-23 (law 12): an hour and a quarter (a quarter of an hour until then)
    orders, states = run(INSIDE, before=closed("ACC", 5.0, 74 * 60))
    assert orders == [] and states[-1]["reason"] == "WAIT_AFTER_TRADE_75M", states[-1]
    assert len(run(INSIDE, before=closed("ACC", 5.0, 76 * 60))[0]) == 1


def test_a_loss_in_another_account_holds_the_symbol_seventy_five_minutes():
    # 2026-10-23 (law 11): an hour and a quarter (an hour until then)
    orders, states = run(INSIDE, before=closed("OTHER", -12.0, 70 * 60))
    assert orders == [] and states[-1]["reason"] == "WAIT_AFTER_LOSS_OTHER_ACCOUNT_75M", states[-1]
    assert len(run(INSIDE, before=closed("OTHER", -12.0, 76 * 60))[0]) == 1
    assert len(run(INSIDE, before=closed("OTHER", 12.0, 40 * 60))[0]) == 1   # a winner elsewhere holds nothing


def test_a_losing_position_open_in_another_account_blocks_the_symbol():
    def losing_elsewhere(atom):
        T.feed(atom, "_on_positions", {"account_id": "OTHER", "positions": [
            {"account_id": "OTHER", "ticket": 9, "symbol": "BTCUSD", "side": "BUY", "profit": -3.0}]})
    orders, states = run(INSIDE, before=losing_elsewhere)
    assert orders == [] and states[-1]["reason"] == "LOSING_POSITION_OPEN_OTHER_ACCOUNT", states[-1]


def test_waits_survive_a_restart():
    atom, _ = T.build()
    T.feed(atom, "_on_trade", {"event_type": "CLOSED", "account_id": "ACC", "symbol": "BTCUSD", "profit": 1.0,
                               "timestamp": 1_000.0})
    import asyncio
    state = asyncio.run(atom.snapshot())
    assert state["waits"]["closed_at"] == {"ACC|BTCUSD": 1000.0}


NY_MORNING = at("2026-10-16T14:00")   # Friday 10:00 New York: the Nasdaq window is open, six hours to its close
NY_LAST_HOUR = at("2026-10-16T19:30")  # Friday 15:30 New York: the last hour of the Nasdaq's window


def nasdaq_run(moment: float):
    atom, bus = T.build()
    T.feed(atom, "_on_pulse", {"official_time": moment})
    T.feed(atom, "_on_size", {**T.size(), "symbol": "USTEC"})
    T.feed(atom, "_on_decision", {**T.decision("buy"), "symbol": "USTEC"})
    return bus.of("execution.order.requested"), bus.of("execution.entry.state")


def test_law_21_no_time_enough_check_any_more_a_morning_order_goes_out():
    # until 2026-10-25 a target beyond the measured movement before the close was refused here; that check is gone
    orders, _ = nasdaq_run(NY_MORNING)
    assert len(orders) == 1


def test_law_21_the_last_hour_of_the_window_refuses_new_entries():
    orders, states = nasdaq_run(NY_LAST_HOUR)
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_LAST_HOUR, states[-1]

def test_general_window_is_closed_on_the_weekend_bitcoin_too():
    """١٧/١٠ (المالك يوم السبت: «كيف الدهب يعمل واليوم عطلة؟»): النافذة العامّة لا تُفتح يوم سبتٍ أو أحدٍ بسيدني.
    ٢٣/١٠ (القانون 23): والبتكوين معها — كان وحده يتداول في العطلة."""
    from datetime import datetime, timezone
    from shared import red_lines as rl, market_context as mc
    saturday = datetime(2026, 10, 17, 17, 45, tzinfo=timezone.utc).timestamp()
    monday = datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc).timestamp()
    assert rl.session_state(saturday, "XAUUSD")[0] is False and rl.session_state(saturday, "BTCUSD")[0] is False
    assert rl.session_state(monday, "XAUUSD")[0] is True and rl.session_state(monday, "BTCUSD")[0] is True
    gold = next(r for r in mc.asset_schedule(saturday) if r["symbol"] == "XAUUSD")
    assert gold["open"] is False and gold["seconds_to_open"] > 24 * 3600
