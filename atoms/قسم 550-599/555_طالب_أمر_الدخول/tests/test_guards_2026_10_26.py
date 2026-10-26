"""2026-10-26 (owner seal "nq", after the project audit): the entry gate refuses when it does not know -- an unknown
calendar (laws 24-25: no state, older than two minutes, or 109 saying it does not know), a time and news gate that failed
to import, and a stalled official pulse. An open position is not closed for an unknown calendar alone: that is the owner's
call, not yet made."""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_atom as T  # noqa: E402
import entry_request_lines  # noqa: E402
from shared import red_lines  # noqa: E402

# read at import, before any fixture holds them
REAL_SESSION_STATE = red_lines.session_state
REAL_NEWS_UNKNOWN = red_lines.news_unknown
REAL_PULSE_AGE = entry_request_lines.pulse_age_s


def at(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


FRIDAY = at("2026-10-16T12:00")     # Friday 15:00 Turkey: London and the general window open, neither first nor last hour
SATURDAY = at("2026-10-17T12:00")


@pytest.fixture(autouse=True)
def _real_gate(monkeypatch):
    monkeypatch.setattr(red_lines, "session_state", REAL_SESSION_STATE)
    monkeypatch.setattr(red_lines, "news_unknown", REAL_NEWS_UNKNOWN)
    monkeypatch.setattr(T._sizing, "min_stop_pips", lambda symbol: 1.0)   # toy prices, as in test_atom


def known(*currencies, age=5.0, is_known=True):
    return {"utc": FRIDAY - age, "known": is_known, "status": "BLOCKED" if currencies else "CLEAR",
            "in_event_window": bool(currencies), "blocked_currencies": list(currencies)}


def run(moment=FRIDAY, symbol="BTCUSD", calendar=None, atom_hook=None):
    atom, bus = T.build()
    T.feed(atom, "_on_pulse", {"official_time": moment})
    if calendar is not None:
        T.feed(atom, "_on_calendar", calendar)
    if atom_hook is not None:
        atom_hook(atom)
    T.feed(atom, "_on_size", {**T.size(), "symbol": symbol})
    T.feed(atom, "_on_decision", {**T.decision("buy"), "symbol": symbol})
    return atom, bus.of("execution.order.requested"), bus.of("execution.entry.state")


# --- the calendar --------------------------------------------------------------------------------------------------------

def test_news_unknown_reads_absence_age_and_the_calendars_own_word():
    assert red_lines.news_unknown(None, FRIDAY) is True
    assert red_lines.news_unknown({"known": True}, FRIDAY) is True                       # no stamp
    assert red_lines.news_unknown(known(age=121.0), FRIDAY) is True                       # older than two minutes
    assert red_lines.news_unknown(known(is_known=False), FRIDAY) is True                  # 109: horizon run out
    assert red_lines.news_unknown({"utc": FRIDAY, "blocked_currencies": []}, FRIDAY) is True   # no "known" at all
    assert red_lines.news_unknown(known(), FRIDAY) is False


def test_no_calendar_state_refuses_the_entry():
    _, orders, states = run()
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_NEWS_UNKNOWN, states[-1]


def test_a_stale_or_unknowing_calendar_refuses_the_entry():
    for calendar in (known(age=121.0), known(is_known=False)):
        _, orders, states = run(calendar=calendar)
        assert orders == [] and states[-1]["reason"] == red_lines.REASON_NEWS_UNKNOWN, (calendar, states[-1])


def test_a_fresh_known_clear_calendar_lets_the_entry_through():
    _, orders, _ = run(calendar=known())
    assert len(orders) == 1


def test_a_red_dollar_item_is_still_the_news_line_and_the_window_still_comes_first():
    _, orders, states = run(calendar=known("USD"))
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_NEWS, states[-1]
    _, orders, states = run(moment=SATURDAY)
    assert orders == [] and states[-1]["reason"] == red_lines.REASON_WINDOW, states[-1]


def test_an_unknown_calendar_alone_does_not_close_an_open_position():
    # the red line (565 closes on it) is unchanged: closing on ignorance is the owner's call, not yet made
    assert red_lines.red_line(FRIDAY, None, "BTCUSD") is None
    assert red_lines.entry_block(FRIDAY, None, "BTCUSD") == red_lines.REASON_NEWS_UNKNOWN


# --- the gate module and the pulse ---------------------------------------------------------------------------------------

def test_a_gate_that_failed_to_import_refuses_every_entry_and_says_so():
    def missing(atom):
        atom._gate_missing = True
    atom, orders, states = run(calendar=known(), atom_hook=missing)
    assert orders == [] and states[-1]["reason"] == entry_request_lines.REASON_GATE_MISSING, states[-1]
    health = asyncio.run(atom.health_check())
    assert health.state.name == "UNHEALTHY" and entry_request_lines.REASON_GATE_MISSING in health.message


def test_a_stalled_pulse_refuses_the_entry_and_the_health_says_so(monkeypatch):
    monkeypatch.setattr(entry_request_lines, "pulse_age_s", REAL_PULSE_AGE)

    def stalled(atom):
        atom._pulse_seen_at -= entry_request_lines.PULSE_MAX_AGE_S + 1
    atom, orders, states = run(calendar=known(), atom_hook=stalled)
    assert orders == [] and states[-1]["reason"] == entry_request_lines.REASON_PULSE_STALE, states[-1]
    health = asyncio.run(atom.health_check())
    assert health.state.name == "DEGRADED" and entry_request_lines.REASON_PULSE_STALE in health.message


def test_a_fresh_pulse_lets_the_entry_through(monkeypatch):
    monkeypatch.setattr(entry_request_lines, "pulse_age_s", REAL_PULSE_AGE)
    _, orders, _ = run(calendar=known())
    assert len(orders) == 1


def test_no_pulse_yet_after_a_start_is_stale(monkeypatch):
    monkeypatch.setattr(entry_request_lines, "pulse_age_s", REAL_PULSE_AGE)
    atom, bus = T.build()
    T.feed(atom, "_on_calendar", known())
    T.feed(atom, "_on_size", {**T.size(), "symbol": "BTCUSD"})
    T.feed(atom, "_on_decision", {**T.decision("buy"), "symbol": "BTCUSD"})
    assert bus.of("execution.order.requested") == []
    assert bus.of("execution.entry.state")[-1]["reason"] == entry_request_lines.REASON_PULSE_STALE
