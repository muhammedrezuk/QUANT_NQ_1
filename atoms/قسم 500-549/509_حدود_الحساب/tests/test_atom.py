"""509 account limits (owner's sealed red lines 2026-10-23, laws 7-10), on the owner's first values: initial 10,000 ·
pair trade risk 0.50% · pair daily 1.5% (150) · global daily 4% (400) · total drawdown 8% (floor 9,200)."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("atom_509", HERE / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

from shared import account_limits as al  # noqa: E402

CFG = yaml.safe_load((HERE / "manifest.yaml").read_text(encoding="utf-8"))["config"]


def at(iso: str) -> float:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()


MORNING = at("2026-10-16T07:00")    # Friday 10:00 Turkey
EVENING = at("2026-10-16T18:00")    # Friday 21:00 Turkey -- the same Turkish day
NEXT_DAY = at("2026-10-16T21:30")   # Saturday 00:30 Turkey -- a new day


class Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, name: str, payload: dict | None = None) -> None:
        self.events.append((name, payload or {}))

    def subscribe(self, name, handler) -> None:
        pass

    def of(self, name: str) -> list[dict]:
        return [p for n, p in self.events if n == name]


def build(atom=None):
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = atom or mod.Atom()
    asyncio.run(atom.initialize(AtomContext(atom_id=509, config=dict(CFG), logger=None, publish=bus.publish,
                                            subscribe=bus.subscribe, subscribe_all=lambda h: None)))
    asyncio.run(atom.start())
    return atom, bus


def figures(atom, balance, equity, at):
    """2026-10-26: the figures carry the moment they were measured (619 -> 653/654); an unstamped or old one is unknown."""
    asyncio.run(atom._on_truth_balance({"account_id": "ACC", "balance": balance, "measured_at": at}))
    asyncio.run(atom._on_truth_equity({"account_id": "ACC", "equity": equity, "measured_at": at}))


def positions(atom, *rows):
    asyncio.run(atom._on_positions({"account_id": "ACC", "positions": [
        {"account_id": "ACC", "ticket": t, "symbol": s, "side": "BUY", "profit": p, "magic": m} for t, s, p, m in rows]}))


def pulse(atom, moment):
    asyncio.run(atom._on_pulse({"official_time": moment}))


def state(bus):
    return bus.of("risk.account_limits.state")[-1]


def closed(bus):
    return sorted((i["ticket"], i["reason"]) for i in bus.of("execution.manage.intent"))


def test_the_owners_first_values_and_the_fixed_trade_risk():
    atom, bus = build()
    figures(atom, 10000.0, 10000.0, MORNING)
    pulse(atom, MORNING)
    body = state(bus)
    assert body["trade_risk"]["USTEC"] == 50.0 and body["accounts"]["ACC"]["daily_limit"] == 400.0
    assert body["accounts"]["ACC"]["floor"] == 9200.0 and body["accounts"]["ACC"]["day_base"] == 10000.0
    assert al.entry_block(body, "ACC", "USTEC", MORNING) == ("", {})


def test_global_daily_limit_closes_ours_and_refuses_until_midnight():
    atom, bus = build()
    figures(atom, 10000.0, 10000.0, MORNING)
    pulse(atom, MORNING)
    # 2026-10-26 (owner's answer, seal "NQ"): the system's own loss -- 410 on its Nasdaq; the owner's gold (magic 0) is out.
    positions(atom, (1, "USTEC", -410.0, 20260801), (2, "XAUUSD", -110.0, 0))
    figures(atom, 10000.0, 9480.0, EVENING)
    pulse(atom, EVENING)
    assert closed(bus) == [(1, al.REASON_DAILY)]
    assert al.entry_block(state(bus), "ACC", "EURUSD", EVENING)[0] == al.REASON_DAILY
    positions(atom)
    figures(atom, 9590.0, 9590.0, NEXT_DAY)
    pulse(atom, NEXT_DAY)
    assert state(bus)["accounts"]["ACC"]["day_base"] == 9590.0
    assert al.entry_block(state(bus), "ACC", "EURUSD", NEXT_DAY) == ("", {})


def test_a_pairs_daily_limit_counts_realized_and_open_and_closes_that_pair_only():
    atom, bus = build()
    figures(atom, 10000.0, 10000.0, MORNING)
    pulse(atom, MORNING)
    asyncio.run(atom._on_trade({"event_type": "PARTIAL", "account_id": "ACC", "symbol": "EURUSD", "profit": -95.0,
                                "commission": -5.0, "source_row_id": 7, "timestamp": MORNING + 60}))
    positions(atom, (3, "EURUSD", -60.0, 20260801), (4, "USTEC", 20.0, 20260801))
    figures(atom, 9900.0, 9860.0, EVENING)
    pulse(atom, EVENING)
    assert closed(bus) == [(3, al.REASON_PAIR)]
    body = state(bus)
    assert body["accounts"]["ACC"]["pair_loss"]["EURUSD"] == 160.0 and body["accounts"]["ACC"]["blocked_pairs"] == ["EURUSD"]
    assert al.entry_block(body, "ACC", "EURUSD", EVENING)[0] == al.REASON_PAIR
    assert al.entry_block(body, "ACC", "USTEC", EVENING) == ("", {})


def test_total_drawdown_stops_across_midnight_and_restarts_until_the_owner_releases_it():
    atom, bus = build()
    figures(atom, 9200.0, 9200.0, MORNING)
    pulse(atom, MORNING)
    assert al.entry_block(state(bus), "ACC", "USTEC", MORNING)[0] == al.REASON_TOTAL
    pulse(atom, NEXT_DAY)
    snap = asyncio.run(atom.snapshot())
    fresh, bus2 = build()
    asyncio.run(fresh.restore(snap))
    figures(fresh, 9200.0, 9200.0, NEXT_DAY + 60)
    pulse(fresh, NEXT_DAY + 60)
    assert al.entry_block(state(bus2), "ACC", "USTEC", NEXT_DAY + 60)[0] == al.REASON_TOTAL
    # released while the equity is still at the floor: it stops again on the next pulse
    asyncio.run(fresh._on_command({"command": "RELEASE_TOTAL"}))
    pulse(fresh, NEXT_DAY + 61)
    assert state(bus2)["accounts"]["ACC"]["total_blocked"] is True
    # the owner writes the real starting balance, then releases: the floor moves and trading may resume
    asyncio.run(fresh._on_command({"command": "SET", "settings": {"initial_balance": 9031.78}}))
    asyncio.run(fresh._on_command({"command": "RELEASE_TOTAL"}))
    pulse(fresh, NEXT_DAY + 62)
    body = state(bus2)
    assert body["accounts"]["ACC"]["total_blocked"] is False and body["accounts"]["ACC"]["floor"] == 8309.24


def test_a_bad_value_is_refused_and_the_old_settings_stay():
    atom, bus = build()
    asyncio.run(atom._on_command({"command": "SET", "settings": {"daily_pct": 3.0, "total_pct": 0}}))
    assert atom._settings[al.DAILY_PCT] == 4.0 and state(bus)["applied"]["reason"] == "BAD_TOTAL_PCT"
    asyncio.run(atom._on_command({"command": "SET", "settings": {"pairs": {"ustec": {"risk_pct": 1.0}}}}))
    assert al.trade_risk(atom._settings, "USTEC") == 100.0 and al.trade_risk(atom._settings, "US30") == 50.0


def test_unknown_or_stale_figures_refuse_entry():
    atom, bus = build()
    pulse(atom, MORNING)
    assert al.entry_block(None, "ACC", "USTEC", MORNING)[0] == al.REASON_UNKNOWN
    figures(atom, 10000.0, 10000.0, MORNING + 1)
    pulse(atom, MORNING + 1)
    assert al.entry_block(state(bus), "ACC", "USTEC", MORNING + 600)[0] == al.REASON_UNKNOWN   # ten minutes old
    assert al.entry_block(state(bus), "OTHER", "USTEC", MORNING + 1)[0] == al.REASON_UNKNOWN


def test_the_backtest_counts_how_often_the_account_would_fall():
    day = at("2026-10-14T07:00")
    trades = [(day + i * 600, "USTEC", -1.0) for i in range(40)]           # 40 straight losses of 50 in one day
    result = al.simulate(trades)
    assert result["taken"] == 3 and result["pair_stops"] == 1 and result["account_falls"] == 0
    # four pairs losing together: 400 a day stops the day (4%); the second such day reaches 9,200 -- a fall, and a new account
    many_days = [(day + d * 86400 + i * 600, sym, -1.0) for d in range(20) for i in range(3)
                 for sym in ("USTEC", "US30", "US500", "XAUUSD")]
    result = al.simulate(many_days)
    assert result["daily_stops"] == 10 and result["account_falls"] == 10 and len(result["fall_days"]) == 10

# --- 2026-10-26 (owner seal "nq", after the project audit): a guard that does not know must refuse ---------------------

def test_figures_older_than_a_minute_are_unknown_and_refuse_entry():
    """The expert stamps the account row every second; a minute of silence is a frozen reader, not a quiet market."""
    atom, bus = build()
    figures(atom, 10000.0, 10000.0, MORNING)
    pulse(atom, MORNING + 60)
    assert state(bus)["accounts"]["ACC"]["known"] is True
    pulse(atom, MORNING + 61)
    view = state(bus)["accounts"]["ACC"]
    assert view["known"] is False and view["why"] == mod.WHY_STALE and view["truth_age_s"] == 61.0
    assert al.entry_block(state(bus), "ACC", "USTEC", MORNING + 61)[0] == al.REASON_UNKNOWN
    health = asyncio.run(atom.health_check())
    assert health.state.name == "DEGRADED" and "TRUTH_UNKNOWN ACC" in health.message
    figures(atom, 10000.0, 10000.0, MORNING + 62)
    pulse(atom, MORNING + 62)
    assert al.entry_block(state(bus), "ACC", "USTEC", MORNING + 62) == ("", {})


def test_unstamped_figures_are_unknown():
    atom, bus = build()
    asyncio.run(atom._on_truth_balance({"account_id": "ACC", "balance": 10000.0}))
    asyncio.run(atom._on_truth_equity({"account_id": "ACC", "equity": 10000.0}))
    pulse(atom, MORNING)
    view = state(bus)["accounts"]["ACC"]
    assert view["known"] is False and view["why"] == mod.WHY_MISSING
    assert al.entry_block(state(bus), "ACC", "USTEC", MORNING)[0] == al.REASON_UNKNOWN


def test_a_limit_reached_stays_reached_when_the_figures_go_stale():
    atom, bus = build()
    figures(atom, 9200.0, 9200.0, MORNING)
    pulse(atom, MORNING)
    assert state(bus)["accounts"]["ACC"]["total_blocked"] is True
    pulse(atom, MORNING + 120)
    view = state(bus)["accounts"]["ACC"]
    assert view["known"] is False and view["total_blocked"] is True


def test_a_silent_806_pulse_hands_the_limits_to_the_003_heartbeat():
    atom, bus = build()
    figures(atom, 10000.0, 10000.0, MORNING)
    pulse(atom, MORNING)
    positions(atom, (1, "USTEC", -500.0, 20260801))
    figures(atom, 10000.0, 9500.0, MORNING + 5)
    asyncio.run(atom._on_backup_pulse({"official_time": MORNING + 5}))   # 806 is fresh: the heartbeat does nothing
    assert closed(bus) == [] and atom._backup_judged == 0
    atom._pulse_seen_at -= mod.PULSE_MAX_AGE_S + 1                       # 806 silent past the limit
    asyncio.run(atom._on_backup_pulse({"official_time": MORNING + 15}))
    assert closed(bus) == [(1, al.REASON_DAILY)] and atom._backup_judged == 1
    health = asyncio.run(atom.health_check())
    assert health.state.name == "DEGRADED" and health.message.startswith(mod.PULSE_STALE)
    pulse(atom, MORNING + 16)                                            # 806 is back
    assert mod.PULSE_STALE not in asyncio.run(atom.health_check()).message
