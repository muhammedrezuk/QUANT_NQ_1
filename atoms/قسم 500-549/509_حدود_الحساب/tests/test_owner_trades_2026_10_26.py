"""2026-10-26 (owner's law and answer, seal "NQ": "the daily drawdown is 5%, I put 4 for you and 1 for me"): every limit is
the system's own -- a pair's daily limit, the global daily limit and the total drawdown read the system's positions and
trade events only; the owner's positions never lock anything and are never closed. A book kept from before the rule is
reviewed once: a pair or daily lock the system's own loss did not reach is released; a total stop never is."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_t509_owner", Path(__file__).resolve().parent / "test_atom.py")
T = importlib.util.module_from_spec(_spec)
sys.modules["_t509_owner"] = T
_spec.loader.exec_module(T)
al, mod = T.al, T.mod
OURS, OWNER = 20260801, 0


def _trade(atom, kind, symbol, profit, row, at, **costs):
    asyncio.run(atom._on_trade({"event_type": kind, "account_id": "ACC", "symbol": symbol, "profit": profit,
                                "source_row_id": row, "timestamp": at, **costs}))


def test_the_owners_floating_loss_never_locks_a_pair_or_the_day_nor_is_closed():
    atom, bus = T.build()
    T.figures(atom, 10000.0, 10000.0, T.MORNING)
    T.pulse(atom, T.MORNING)
    T.positions(atom, (2036216648, "USTEC", -610.0, OWNER), (5, "XAUUSD", -10.0, OURS))
    T.figures(atom, 10000.0, 9380.0, T.MORNING + 40)                   # the account 620 down -- the owner's 610
    T.pulse(atom, T.MORNING + 40)                                      # the state is republished every 30 s
    view = T.state(bus)["accounts"]["ACC"]
    assert view["blocked_pairs"] == [] and view["daily_blocked"] is False and view["day_loss"] == 10.0
    assert "USTEC" not in view["pair_loss"] and T.closed(bus) == []
    assert al.entry_block(T.state(bus), "ACC", "USTEC", T.MORNING + 40) == ("", {})


def test_the_systems_own_loss_still_locks_beside_the_owners_gain():
    atom, bus = T.build()
    T.figures(atom, 10000.0, 10000.0, T.MORNING)
    T.pulse(atom, T.MORNING)
    _trade(atom, "OPENED", "USTEC", 0.0, 1, T.MORNING + 1, commission=-3.0)
    _trade(atom, "CLOSED", "USTEC", -300.0, 2, T.MORNING + 2, commission=-3.0)
    T.positions(atom, (3, "EURUSD", -100.0, OURS), (9, "EURUSD", 900.0, OWNER))   # the owner's gain offsets nothing
    T.figures(atom, 9694.0, 10494.0, T.MORNING + 5)
    T.pulse(atom, T.MORNING + 5)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["day_loss"] == 406.0 and view["daily_blocked"] is True and T.closed(bus) == [(3, al.REASON_DAILY)]
    assert view["pair_loss"]["USTEC"] == 306.0                         # the entry commission is in the pair's result


def test_the_total_drawdown_is_the_systems_own_equity():
    atom, bus = T.build()
    T.figures(atom, 9300.0, 9300.0, T.MORNING)                         # floor 9,200
    T.pulse(atom, T.MORNING)
    T.positions(atom, (9, "USTEC", -500.0, OWNER))
    T.figures(atom, 9300.0, 8800.0, T.MORNING + 5)                     # the account under the floor -- by the owner
    T.pulse(atom, T.MORNING + 5)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["total_blocked"] is False and view["system_equity"] == 9300.0
    T.positions(atom)
    T.figures(atom, 10300.0, 10300.0, T.MORNING + 10)                  # the owner closes +1,000
    _trade(atom, "CLOSED", "XAUUSD", -150.0, 4, T.MORNING + 11)        # the system loses 150
    T.positions(atom, (6, "BTCUSD", -100.0, OURS))
    T.figures(atom, 10150.0, 10050.0, T.MORNING + 12)
    T.pulse(atom, T.MORNING + 12)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["system_balance"] == 9150.0 and view["system_equity"] == 9050.0 and view["total_blocked"] is True
    assert T.closed(bus) == [(6, al.REASON_TOTAL)]                     # the owner's +1,000 did not hide the system's fall


def _old_book(realized, daily=True):
    """A 1.1.0 snapshot (no `rule`): USTEC and XAUUSD locked, and the day too, like 2026-10-26 17:4x."""
    atom, _ = T.build()
    T.figures(atom, 9056.86, 9056.86, T.MORNING)
    T.pulse(atom, T.MORNING)
    snap = json.loads(json.dumps(asyncio.run(atom.snapshot())))
    book = snap["books"]["ACC"]
    book.update({"pairs": ["USTEC", "XAUUSD"], "realized": realized, "daily": daily, "base": 9056.86, "total": False})
    for key in ("rule", "review", "review_daily", "system_balance", "seed"):
        book.pop(key, None)
    snap["version"] = "1.1.0"
    snap["settings"]["initial_balance"] = 9000.0                       # the owner's own figure: 360 a day, floor 8,280
    return snap


def test_todays_old_locks_are_reviewed_once_on_the_systems_figures():
    snap = _old_book({"BTCUSD": {"2743": 19.89, "2744": -2.69}, "XAUUSD": {"2746": 11.63, "2747": -0.66, "2749": -43.95}})
    atom, bus = T.build()
    asyncio.run(atom.restore(snap))
    atom._started_at -= mod.REVIEW_AFTER_S + 1                         # past the start's grace
    T.figures(atom, 9700.0, 9700.0, T.MORNING + 10)                    # the owner closed his Nasdaq at a profit
    T.pulse(atom, T.MORNING + 10)                                      # positions not seen yet: nothing released
    assert T.state(bus)["accounts"]["ACC"]["daily_blocked"] is True
    T.positions(atom)
    T.pulse(atom, T.MORNING + 11)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["daily_blocked"] is False and view["blocked_pairs"] == ["XAUUSD"] and view["day_loss"] == 15.78
    assert sorted(atom._released) == ["ACC:DAILY", "ACC:USTEC"]
    assert view["system_balance"] == round(9056.86 - 15.78, 2)         # the owner's +643 stays out of the system's
    assert al.entry_block(T.state(bus), "ACC", "USTEC", T.MORNING + 11) == ("", {})
    again = json.loads(json.dumps(asyncio.run(atom.snapshot())))       # the review does not run twice
    fresh, _ = T.build()
    asyncio.run(fresh.restore(again))
    book = fresh._books["ACC"]
    assert book["review"] == [] and book["review_daily"] is False and book["rule"] == mod.LIMITS_RULE
    assert book["system_balance"] == round(9056.86 - 15.78, 6)


def test_an_old_daily_lock_the_systems_loss_reached_stays():
    snap = _old_book({"XAUUSD": {"1": -400.0}})
    atom, bus = T.build()
    asyncio.run(atom.restore(snap))
    atom._started_at -= mod.REVIEW_AFTER_S + 1                         # past the start's grace
    T.figures(atom, 8656.86, 8656.86, T.MORNING + 10)
    T.positions(atom)
    T.pulse(atom, T.MORNING + 10)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["daily_blocked"] is True and "XAUUSD" in view["blocked_pairs"] and atom._released == ["ACC:USTEC"]


def test_an_old_total_stop_is_never_released_here():
    snap = _old_book({}, daily=False)
    snap["books"]["ACC"]["total"] = True
    atom, bus = T.build()
    asyncio.run(atom.restore(snap))
    atom._started_at -= mod.REVIEW_AFTER_S + 1                         # past the start's grace
    T.figures(atom, 9900.0, 9900.0, T.MORNING + 10)
    T.positions(atom)
    T.pulse(atom, T.MORNING + 10)
    assert T.state(bus)["accounts"]["ACC"]["total_blocked"] is True


def test_the_systems_balance_crosses_midnight():
    atom, bus = T.build()
    T.figures(atom, 9500.0, 9500.0, T.EVENING)
    T.pulse(atom, T.EVENING)
    _trade(atom, "CLOSED", "XAUUSD", -50.0, 7, T.EVENING + 1)
    T.figures(atom, 9450.0, 9450.0, T.NEXT_DAY)
    T.pulse(atom, T.NEXT_DAY)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["system_balance"] == 9450.0 and view["day_loss"] == 0.0


def test_the_review_waits_for_the_starts_grace():
    """Review 2026-10-26: a close already on its way from 611 lands in the book before anything is released."""
    snap = _old_book({})
    atom, bus = T.build()
    asyncio.run(atom.restore(snap))
    T.figures(atom, 9700.0, 9700.0, T.MORNING + 10)
    T.positions(atom)
    T.pulse(atom, T.MORNING + 10)
    assert T.state(bus)["accounts"]["ACC"]["daily_blocked"] is True and atom._released == []
    _trade(atom, "CLOSED", "USTEC", -200.0, 33, T.MORNING + 11)      # the system's own close, arriving late
    atom._started_at -= mod.REVIEW_AFTER_S + 1
    T.pulse(atom, T.MORNING + 12)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["blocked_pairs"] == ["USTEC"] and atom._released == ["ACC:XAUUSD", "ACC:DAILY"]


def test_a_position_crossing_midnight_counts_once_in_the_new_day():
    """Review 2026-10-26, round two: from 2026-11-01 the windows end at 00:00 Turkey, so a position of the system is closed
    just after midnight. Its profit was already in the day's base: it gives the new day no room over the limit."""
    atom, bus = T.build()
    T.figures(atom, 10000.0, 10000.0, T.EVENING)
    T.pulse(atom, T.EVENING)
    T.positions(atom, (21, "XAUUSD", 240.0, OURS))                    # open at a profit across midnight
    T.figures(atom, 10000.0, 10240.0, T.NEXT_DAY)
    T.pulse(atom, T.NEXT_DAY)                                         # the new day begins with it open
    T.positions(atom)
    _trade(atom, "CLOSED", "XAUUSD", 240.0, 22, T.NEXT_DAY + 1)       # closed a second later
    _trade(atom, "CLOSED", "USTEC", -400.0, 23, T.NEXT_DAY + 600)     # then the system loses 400
    T.figures(atom, 9840.0, 9840.0, T.NEXT_DAY + 601)
    T.pulse(atom, T.NEXT_DAY + 601)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["system_day_base"] == 10240.0 and view["day_loss"] == 400.0 and view["daily_blocked"] is True


def test_the_day_base_is_set_on_the_first_pulse_while_the_figures_are_unknown():
    """Review 2026-10-26, round three: the account's figures frozen around 00:00 must not let a loss crossing midnight
    fall out of every day."""
    atom, bus = T.build()
    T.figures(atom, 10000.0, 10000.0, T.EVENING)
    T.pulse(atom, T.EVENING)
    T.positions(atom, (41, "XAUUSD", -300.0, OURS))                   # open at a loss across midnight
    T.pulse(atom, T.NEXT_DAY)                                         # the figures are hours old: unknown
    assert atom._books["ACC"]["sys_base"] == 10000.0
    T.positions(atom)
    _trade(atom, "CLOSED", "XAUUSD", -300.0, 42, T.NEXT_DAY + 1)
    T.figures(atom, 9700.0, 9700.0, T.NEXT_DAY + 40)
    T.pulse(atom, T.NEXT_DAY + 40)
    assert T.state(bus)["accounts"]["ACC"]["day_loss"] == 300.0


def test_a_new_books_row_published_again_after_its_start_counts_once():
    """Review 2026-10-26, round three: a row seen before the book's start is in the balance; published again, it moves the
    system's balance by its difference only."""
    atom, bus = T.build()
    T.pulse(atom, T.MORNING)                                          # no figures yet
    _trade(atom, "CLOSED", "XAUUSD", -100.0, 51, T.MORNING + 1)
    T.figures(atom, 9900.0, 9900.0, T.MORNING + 2)
    T.pulse(atom, T.MORNING + 2)                                      # the book starts from the balance (9,900)
    _trade(atom, "CLOSED", "XAUUSD", -100.0, 51, T.MORNING + 1, commission=-3.5)   # again, with its cost
    T.figures(atom, 9896.5, 9896.5, T.MORNING + 40)
    T.pulse(atom, T.MORNING + 40)
    assert T.state(bus)["accounts"]["ACC"]["system_balance"] == 9896.5


import pytest  # noqa: E402


@pytest.mark.parametrize("profit", [200.0, -200.0])
@pytest.mark.parametrize("still_in_picture", [True, False])
def test_a_close_in_the_last_second_before_midnight_is_no_loss_of_the_new_day(profit, still_in_picture):
    """Review 2026-10-26, round four: closed just before 00:00, its event stamped yesterday arriving after the day began,
    with 609's picture still holding the position at the day's first pulse or not -- the new day's loss is nothing."""
    atom, bus = T.build()
    T.figures(atom, 10000.0, 10000.0, T.EVENING)
    T.pulse(atom, T.EVENING)
    T.positions(atom, *([(61, "XAUUSD", profit, OURS)] if still_in_picture else []))
    T.pulse(atom, T.NEXT_DAY)                                         # the day begins
    T.positions(atom)
    asyncio.run(atom._on_trade({"event_type": "CLOSED", "account_id": "ACC", "symbol": "XAUUSD", "profit": profit,
                                "ticket": 61, "source_row_id": 63, "timestamp": T.NEXT_DAY - 1801}))   # 23:59:59, late
    T.figures(atom, 10000.0 + profit, 10000.0 + profit, T.NEXT_DAY + 40)
    T.pulse(atom, T.NEXT_DAY + 40)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["day_loss"] == 0.0 and view["system_balance"] == 10000.0 + profit, view


def test_a_close_arriving_before_the_first_pulse_is_kept():
    """Review 2026-10-26, round two: after a start 611 relays what it missed before any pulse reaches this atom."""
    atom, bus = T.build()
    _trade(atom, "CLOSED", "XAUUSD", -200.0, 31, T.MORNING)
    T.figures(atom, 9800.0, 9800.0, T.MORNING)
    T.pulse(atom, T.MORNING)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["pair_loss"]["XAUUSD"] == 200.0 and atom._early == []


def test_a_row_stamped_yesterday_or_published_again_moves_the_systems_balance_once():
    atom, bus = T.build()
    T.figures(atom, 9500.0, 9500.0, T.EVENING)
    T.pulse(atom, T.EVENING)                                         # the system's balance starts: 9,500
    T.pulse(atom, T.NEXT_DAY)                                        # midnight passes
    _trade(atom, "CLOSED", "XAUUSD", -120.0, 8, T.NEXT_DAY - 3600)   # yesterday's close (23:30), arriving after midnight
    _trade(atom, "CLOSED", "XAUUSD", -120.0, 8, T.NEXT_DAY - 3600, commission=-3.0)   # again, with its cost
    T.figures(atom, 9377.0, 9377.0, T.NEXT_DAY + 40)
    T.pulse(atom, T.NEXT_DAY + 40)
    view = T.state(bus)["accounts"]["ACC"]
    assert view["system_balance"] == 9377.0 and view["day_loss"] == 0.0