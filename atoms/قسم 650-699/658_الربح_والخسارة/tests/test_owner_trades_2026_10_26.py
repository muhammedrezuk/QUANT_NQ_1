"""2026-10-26 (owner's law, seal "NQ"): the system's profit is the system's alone, and the owner's is recorded apart as «ربح
المالك وخسارته» -- his open positions' floating, and today's realized from the balance less the system's own deals."""
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("_t658_owner", Path(__file__).resolve().parents[1] / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t658_owner"] = m
_spec.loader.exec_module(m)

T0 = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc).timestamp()     # 17:00 Turkey
NEXT = datetime(2026, 10, 26, 21, 30, tzinfo=timezone.utc).timestamp()  # 00:30 Turkey: a new day


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
    await a.initialize(m.AtomContext(658, {}, L(), b.publish, b.subscribe)); await a.start()
    return a, b


def _acc(balance, at):
    return {"account_id": "A", "balance": balance, "equity": balance, "measured_at": at, "stale": False}


async def test_the_floating_is_the_systems_and_the_owners_is_apart():
    a, b = await _new()
    await a._on_positions({"account_id": "A", "positions": [
        {"account_id": "A", "ticket": 1, "symbol": "XAUUSD", "profit": -20.0, "magic": 20260801},
        {"account_id": "A", "ticket": 2036216648, "symbol": "USTEC", "profit": 655.8, "swap": -1.0, "magic": 0}]})
    out = b.last()
    assert out["floating_pnl"] == -20.0 and out["net_pnl"] == -20.0
    owner = out["owner"]
    assert owner["label"] == "ربح المالك وخسارته" and owner["open_count"] == 1 and owner["floating_pnl"] == 654.8
    assert [p["ticket"] for p in owner["positions"]] == [2036216648]
    await a._on_positions({"account_id": "A", "positions": []})          # all closed
    assert b.last()["owner"]["open_count"] == 0 and b.last()["floating_pnl"] == 0.0


async def test_the_owners_realized_is_the_balance_less_the_systems_deals():
    a, b = await _new()
    await a._on_account(_acc(9040.48, T0))                               # the day's first balance this atom sees
    assert b.last()["owner"]["realized_today"] == 0.0 and b.last()["owner"]["since"] == T0
    await a._on_system_deal({"account_id": "A", "event_type": "CLOSED", "profit": -43.56, "commission": -0.39,
                             "source_row_id": 2749, "timestamp": T0 + 60})
    await a._on_account(_acc(9040.48 - 43.95, T0 + 61))                  # the system's loss: not the owner's
    assert b.last()["owner"]["realized_today"] == 0.0
    await a._on_account(_acc(9040.48 - 43.95 + 700.0, T0 + 3600))        # the owner's manual close
    assert b.last()["owner"]["realized_today"] == 700.0
    assert b.last()["realized_pnl"] == 0.0                               # the system's realized is untouched
    await a._on_system_deal({"account_id": "A", "event_type": "CLOSED", "profit": -43.56, "commission": -0.39,
                             "source_row_id": 2749, "timestamp": T0 + 60})   # the same row again: not twice
    assert b.last()["owner"]["realized_today"] == 700.0


async def test_a_row_republished_with_its_costs_moves_by_its_difference():
    """Review 2026-10-26: 611 publishes the same row again when its costs arrive -- the difference is the system's, not
    the owner's."""
    a, b = await _new()
    await a._on_account(_acc(9000.0, T0))
    await a._on_system_deal({"account_id": "A", "profit": -40.0, "source_row_id": 5, "timestamp": T0 + 1})
    await a._on_system_deal({"account_id": "A", "profit": -40.0, "commission": -3.5, "source_row_id": 5, "timestamp": T0 + 2})
    await a._on_account(_acc(8956.5, T0 + 3))
    assert b.last()["owner"]["realized_today"] == 0.0


async def test_the_owners_open_figures_are_unknown_before_the_first_positions():
    a, b = await _new()
    await a._on_account(_acc(9000.0, T0))
    owner = b.last()["owner"]
    assert owner["open_count"] is None and owner["floating_pnl"] is None and owner["net_today"] is None


async def test_a_deal_before_the_first_balance_is_already_in_it():
    a, b = await _new()
    await a._on_system_deal({"account_id": "A", "profit": -10.0, "source_row_id": 1, "timestamp": T0 - 5})
    await a._on_account(_acc(9000.0, T0))
    await a._on_system_deal({"account_id": "A", "profit": -5.0, "source_row_id": 2, "timestamp": T0 - 1})
    await a._on_account(_acc(9000.0, T0 + 1))
    assert b.last()["owner"]["realized_today"] == 0.0


async def test_a_new_day_keeps_yesterdays_record_and_starts_again():
    a, b = await _new()
    await a._on_account(_acc(9000.0, T0))
    await a._on_account(_acc(9655.0, T0 + 100))
    await a._on_account(_acc(9655.0, NEXT))
    owner = b.last()["owner"]
    assert owner["realized_today"] == 0.0 and owner["since"] == NEXT
    assert list(owner["history"].values()) == [{"realized": 655.0, "since": T0}]


async def test_the_owners_record_survives_a_restart():
    a, b = await _new()
    await a._on_account(_acc(9000.0, T0))
    await a._on_system_deal({"account_id": "A", "profit": -5.0, "source_row_id": 9, "timestamp": T0 + 1})
    await a._on_account(_acc(9100.0, T0 + 2))
    state = json.loads(json.dumps(await a.snapshot()))
    c, cb = await _new()
    await c.restore(state)
    await c._on_system_deal({"account_id": "A", "profit": -5.0, "source_row_id": 9, "timestamp": T0 + 1})
    await c._on_account(_acc(9100.0, T0 + 3))
    assert cb.last()["owner"]["realized_today"] == 105.0 and cb.last()["owner"]["since"] == T0


async def test_an_old_snapshot_restores_the_systems_realized():
    a, b = await _new()
    await a.restore({"version": "1.2.0", "realized": {"A": -12.5}})
    await a._on_account(_acc(9000.0, T0))
    assert b.last()["realized_pnl"] == -12.5 and b.last()["owner"]["realized_today"] == 0.0


async def test_a_complete_empty_picture_after_a_start_gives_the_owners_open_figures():
    """2026-10-26, after the hot reload: a flat account's complete picture says the owner has nothing open -- not unknown."""
    a, b = await _new()
    await a._on_positions({"account_id": "A", "positions": [], "complete": True})
    owner = b.last()["owner"]
    assert owner["open_count"] == 0 and owner["floating_pnl"] == 0.0 and b.last()["floating_pnl"] == 0.0
