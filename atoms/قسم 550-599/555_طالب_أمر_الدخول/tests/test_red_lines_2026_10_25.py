"""2026-10-25 (owner seal «nq», laws 17 and 21): «قاعدة وقت يكفي خليها تشتغل اخر ساعة بس ما تفتح صفقات جديدة بس هيك» and, for
gold and bitcoin, «نافذة لا 23:00». In Turkey's clock today: the US indices 16:30-23:00 (nothing new after 22:00), the euro and
the pound 10:00-18:30 (nothing new after 17:30), gold and bitcoin 02:00-23:00 (nothing new after 22:00)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_atom as T  # noqa: E402
from shared import market_context, red_lines  # noqa: E402

REAL_SESSION_STATE = red_lines.session_state   # read at import, before any fixture holds the window open
REAL_IN_LAST_HOUR = red_lines.in_last_hour


def at(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def _real_window(monkeypatch):
    monkeypatch.setattr(red_lines, "session_state", REAL_SESSION_STATE)
    monkeypatch.setattr(red_lines, "in_last_hour", REAL_IN_LAST_HOUR)
    monkeypatch.setattr(T._sizing, "min_stop_pips", lambda symbol: 1.0)   # toy prices, as in test_atom


def run(moment: float, symbol: str):
    atom, bus = T.build()
    T.feed(atom, "_on_pulse", {"official_time": moment})
    T.feed(atom, "_on_size", {**T.size(), "symbol": symbol})
    T.feed(atom, "_on_decision", {**T.decision("buy"), "symbol": symbol})
    return bus.of("execution.order.requested"), bus.of("execution.entry.state")


# Thursday 2026-10-22, New York on summer time (UTC-4), London on summer time (UTC+1); Turkey is UTC+3 all year.
@pytest.mark.parametrize("symbol, before_last_hour, in_last_hour, closed", [
    ("USTEC", "2026-10-22T18:55", "2026-10-22T19:05", "2026-10-22T20:00"),    # 21:55 / 22:05 / 23:00 Turkey
    ("EURUSD", "2026-10-22T14:25", "2026-10-22T14:35", "2026-10-22T15:30"),   # 17:25 / 17:35 / 18:30 Turkey
    ("XAUUSD", "2026-10-22T18:55", "2026-10-22T19:05", "2026-10-22T20:00"),   # 21:55 / 22:05 / 23:00 Turkey
    ("BTCUSD", "2026-10-22T18:55", "2026-10-22T19:05", "2026-10-22T20:00"),
])
def test_nothing_new_in_the_last_hour_and_the_window_ends_where_the_owner_set_it(symbol, before_last_hour, in_last_hour, closed):
    assert len(run(at(before_last_hour), symbol)[0]) == 1
    orders, states = run(at(in_last_hour), symbol)
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_LAST_HOUR, (symbol, states[-1])
    orders, states = run(at(closed), symbol)
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_WINDOW, (symbol, states[-1])


def test_the_general_window_now_runs_to_16_new_york_an_hour_longer():
    # 15:30 New York: inside the general window since 2026-10-25 (it closed at 15:00 until then), and in its last hour
    t = at("2026-10-22T19:30")
    assert red_lines.session_state(t, "XAUUSD")[0] is True and red_lines.in_last_hour(t, "XAUUSD")
    assert red_lines.seconds_to_window_close(t, "XAUUSD") == 30 * 60


def test_the_panel_schedule_shows_the_last_hour():
    t = at("2026-10-22T19:30")                  # 22:30 Turkey
    rows = {r["symbol"]: r for r in market_context.asset_schedule(t)}
    for symbol in ("USTEC", "XAUUSD", "BTCUSD"):
        assert rows[symbol]["open"] and rows[symbol]["last_hour"], rows[symbol]
        assert rows[symbol]["close_owner"] == "23:00" and rows[symbol]["no_new_owner"] == "22:00", rows[symbol]
    assert rows["EURUSD"]["open"] is False
