"""إصلاحات ٢٠٢٦-١٠-٠٢ في 555 (ختم المالك «صلح كامل nq») — ملفٌّ جديد، والقديم لا يُمسّ.

  (١) حكم 1:3 بعد السبريد والوقف ≥ 10 ن.أ **عند الإرسال** على أسعار الأمر نفسه
      (تدقيق: 298 صفقة منفّذة دون 1:3، و4 أوامر بوقف 6.0–9.7 ن.أ).
  (٢) الإيقاف لكلّ حساب — كان عامًّا يفكّه إفراجُ أيّ حساب (تدقيق م2).
  (٣) الموقوفة `DEGRADED` لا `HEALTHY` (تدقيق ع1).
الحمولات بشكل ناشريها: الحجم كما ينشره 513 (تحت `metadata`)، والمستويات مختومةً على
القرار كما يختمها 466 (`invalidation_price`/`target_price`/`setup_id`/`invalidation_source`).
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for extra in (ROOT, FOLDER):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

_spec = importlib.util.spec_from_file_location("atom_555_fix", FOLDER / "atom.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

CFG = {"size_stale_after_s": 30.0, "target_stale_after_s": 30.0,
       "max_open_per_symbol": 0, "inflight_ttl_s": 90.0, "min_reward_multiple": 3.0}


class Bus:
    def __init__(self):
        self.events = []

    async def publish(self, name, payload=None):
        self.events.append((name, payload or {}))

    def subscribe(self, name, handler):
        pass

    def of(self, name):
        return [p for n, p in self.events if n == name]


def feed(atom, handler, payload):
    asyncio.run(getattr(atom, handler)(payload))


def build(accounts=("ACC",)):
    from core.contracts.atom import AtomContext
    bus = Bus()
    atom = mod.Atom()
    ctx = AtomContext(atom_id=555, config=dict(CFG), logger=None, publish=bus.publish,
                      subscribe=bus.subscribe, subscribe_all=lambda h: None)
    asyncio.run(atom.initialize(ctx))
    asyncio.run(atom.start())
    for account in accounts:
        feed(atom, "_on_account", {"account_id": account, "broker": "BR"})
    feed(atom, "_on_positions", {"positions": []})
    return atom, bus


def size_513(account="ACC", symbol="BTCUSD", price=50000.0, spread=5.0):
    """حمولة 513 كما تُنشر (`513/atom.py:318-346`) — مواصفة بتكوين: قيمة النقطة 0.01/0.01."""
    return {"account_id": account, "broker": "BR", "symbol": symbol,
            "id": "position_sizing", "status": "OK", "approved": True,
            "metadata": {"lot": 0.3, "risk_amount": 100.0, "price": price,
                         "stop_distance": price * 0.005, "tick_value": 0.01,
                         "tick_size": 0.01, "spread": spread, "commission_per_lot": 0.0,
                         "max_trade_loss": 100.0, "volume_step": 0.01,
                         "volume_min": 0.01, "volume_max": 50.0}}


def decision(stop, target, side="buy", account="ACC", symbol="BTCUSD", n=1):
    return {"account_id": account, "broker": "BR", "symbol": symbol,
            "decision_side": side, "decision_id": "D%d" % n, "gate_request_id": "G%d" % n,
            "invalidation_price": stop, "target_price": target,
            "setup_id": "405:MEAN_REVERSION:%s:1" % symbol,
            "invalidation_source": "201:15m:swing_low"}


def requests(bus):
    return bus.of("execution.order.requested")


def last_state(bus):
    return bus.of("execution.entry.state")[-1]


# ── (١) حكما الإرسال ─────────────────────────────────────────────────────────

def test_gross_3_1_but_net_below_3_after_spread_is_declined():
    """مخاطرة 100 وعائد 310 (3.1 إجماليًّا) بسبريد 5 ⟸ (310−5)÷(100+5) = 2.905 < 3 ⟸ رفض."""
    atom, bus = build()
    feed(atom, "_on_size", size_513())
    feed(atom, "_on_decision", decision(stop=49900.0, target=50310.0))
    assert requests(bus) == [], "خرج أمرٌ صافيه دون 1:3"
    state = last_state(bus)
    assert state["reason"] == "RR_BELOW_MIN_AT_SEND", state
    assert abs(state["net_ratio"] - 2.9048) < 1e-3 and state["spread"] == 5.0, state


def test_net_at_least_3_after_spread_is_sent_with_its_own_levels():
    """عائد 330 ⟸ (330−5)÷105 = 3.095 ⟸ يخرج بمستوييه كما هما."""
    atom, bus = build()
    feed(atom, "_on_size", size_513())
    feed(atom, "_on_decision", decision(stop=49900.0, target=50330.0))
    out = requests(bus)
    assert len(out) == 1, last_state(bus)
    assert out[0]["stop_loss"] == 49900.0 and out[0]["take_profit"] == 50330.0


def test_owner_us30_trade_with_inverted_ratio_is_declined():
    """صفقة المالك 16:03 UTC: مرجع 51357.15 · وقف 51271.28 (85.87) · هدف 51359.25 (2.10)."""
    atom, bus = build()
    feed(atom, "_on_size", size_513(symbol="US30", price=51357.15, spread=2.0))
    feed(atom, "_on_decision", decision(stop=51271.28232256, target=51359.250729,
                                        symbol="US30"))
    assert requests(bus) == []
    state = last_state(bus)
    assert state["reason"] == "RR_BELOW_MIN_AT_SEND" and state["net_ratio"] < 0.1, state


def test_stop_tighter_than_min_bps_at_send_price_is_declined():
    """ناسداك 30,000 ووقف 6 نقاط = 6 بِب < 9 (ختم ١٠-١٧: البِب بدل نقاط الأساس) — والنسبة وحدها كانت تمرّ."""
    atom, bus = build()
    feed(atom, "_on_size", size_513(symbol="USTEC", price=30000.0, spread=1.0))
    feed(atom, "_on_decision", decision(stop=29994.0, target=30300.0, symbol="USTEC"))
    assert requests(bus) == []
    state = last_state(bus)
    assert state["reason"] == "STOP_BELOW_10BPS_AT_SEND", state
    assert abs(state["stop_pips"] - 6.0) < 1e-3


def test_dow_stop_of_4bps_is_still_declined_floor_10_outside_nasdaq():
    """ختم المالك ١٠-١٧ «nq» «10 للداو جونز»: الداو حدّه 10 بِب — داو 51,534 ووقف 8 نقاط يُردّ، ووقف 20 نقطة (كان يُردّ بحدّ 52) يمرّ."""
    atom, bus = build()
    feed(atom, "_on_size", size_513(symbol="US30", price=51534.0, spread=2.0))
    feed(atom, "_on_decision", decision(stop=51526.0, target=51800.0, symbol="US30"))
    assert requests(bus) == []
    state = last_state(bus)
    assert state["reason"] == "STOP_BELOW_10BPS_AT_SEND" and state["min_stop_pips"] == 10.0, state
    atom, bus = build()
    feed(atom, "_on_size", size_513(symbol="US30", price=51534.0, spread=2.0))
    feed(atom, "_on_decision", decision(stop=51514.0, target=51800.0, symbol="US30"))
    assert len(requests(bus)) == 1, last_state(bus)


def test_stop_of_8bps_is_sent_since_owner_lowered_floor_to_3():
    """ختم المالك ٢٠٢٦-١٠-٠٦ «نقاط أساس خليها 3 مو 10 NQ»: وقف 25 نقطة على 30,000 = 8.33 ن.أ يمرّ."""
    atom, bus = build()
    feed(atom, "_on_size", size_513(symbol="USTEC", price=30000.0, spread=1.0))
    feed(atom, "_on_decision", decision(stop=29975.0, target=30300.0, symbol="USTEC"))
    assert len(requests(bus)) == 1, last_state(bus)


def test_sell_side_is_measured_on_its_own_direction():
    atom, bus = build()
    feed(atom, "_on_size", size_513())
    feed(atom, "_on_decision", decision(stop=50100.0, target=49690.0, side="sell"))
    assert requests(bus) == [] and last_state(bus)["reason"] == "RR_BELOW_MIN_AT_SEND"
    atom, bus = build()
    feed(atom, "_on_size", size_513())
    feed(atom, "_on_decision", decision(stop=50100.0, target=49670.0, side="sell"))
    assert len(requests(bus)) == 1, last_state(bus)


def test_declined_at_send_does_not_start_the_cooldown_or_in_flight():
    atom, bus = build()
    feed(atom, "_on_size", size_513())
    feed(atom, "_on_decision", decision(stop=49900.0, target=50200.0))
    assert atom._inflight == {} and atom._last_request_at == {}
    feed(atom, "_on_decision", decision(stop=49900.0, target=50400.0, n=2))
    assert len(requests(bus)) == 1, last_state(bus)


# ── (٢) الإيقاف لكلّ حساب ─────────────────────────────────────────────────────

def _try(atom, bus, account, symbol, n):
    before = len(requests(bus))
    feed(atom, "_on_size", size_513(account=account, symbol=symbol))
    feed(atom, "_on_decision", decision(49900.0, 50400.0, account=account, symbol=symbol, n=n))
    return len(requests(bus)) > before, last_state(bus)["reason"]


def test_account_halt_stops_that_account_only():
    atom, bus = build(accounts=("A", "B"))
    feed(atom, "_on_halt", {"account_id": "A", "reason": "RISK_HALT"})
    assert _try(atom, bus, "A", "S1", 1) == (False, "EMERGENCY_HALT")
    assert _try(atom, bus, "B", "S2", 2) == (True, "REQUESTED")


def test_release_of_another_account_does_not_free_the_halted_one():
    """محاذاة إقلاع 516 لحساب B (`BOOT_ALIGN`) كانت تفكّ إيقاف A."""
    atom, bus = build(accounts=("A", "B"))
    feed(atom, "_on_halt", {"account_id": "A"})
    feed(atom, "_on_reset", {"account_id": "B", "reason": "BOOT_ALIGN"})
    assert _try(atom, bus, "A", "S1", 1) == (False, "EMERGENCY_HALT")
    feed(atom, "_on_reset", {"account_id": "A", "reason": "OWNER_RELEASE"})
    assert _try(atom, bus, "A", "S3", 3) == (True, "REQUESTED")


def test_system_halt_covers_every_account_until_a_release_without_account():
    atom, bus = build(accounts=("A", "B"))
    feed(atom, "_on_halt", {"scope": "SYSTEM", "reason": "OWNER"})
    assert _try(atom, bus, "A", "S1", 1)[0] is False
    assert _try(atom, bus, "C", "S2", 2)[0] is False, "حسابٌ جديد بعد الإيقاف العامّ"
    feed(atom, "_on_reset", {"account_id": "A", "reason": "BOOT_ALIGN"})
    assert _try(atom, bus, "A", "S3", 3)[0] is False, "إفراجُ حسابٍ لا يرفع الإيقاف العامّ"
    feed(atom, "_on_reset", {"reason": "OWNER_RELEASE"})
    assert _try(atom, bus, "A", "S4", 4) == (True, "REQUESTED")


def test_halt_without_account_is_system_wide():
    atom, bus = build(accounts=("A",))
    feed(atom, "_on_halt", {"reason": "owner"})
    assert atom._halt_all is True
    assert _try(atom, bus, "A", "S1", 1) == (False, "EMERGENCY_HALT")


def test_halt_survives_snapshot_per_account_and_legacy_snapshot_fails_closed():
    atom, _ = build(accounts=("A", "B"))
    feed(atom, "_on_halt", {"account_id": "A"})
    snap = asyncio.run(atom.snapshot())
    again, _ = build()
    asyncio.run(again.restore(snap))
    assert again._halted_accounts == {"A"} and again._halt_all is False
    # ٢٠٢٦-١٠-٠٢ v1.25.1: اللقطة القديمة تبقى مغلقة (موقوفة لكلّ حساب)، لكنّ إيقافها «موروث» يفكّه
    # أيّ تحرير — مقيس حيًّا بعد إقلاع 15:10: إيقافٌ عامّ صارم منها بقي بعد أن حرّر 516 الحساب.
    legacy, _ = build()
    entry_request_inputs = mod.entry_request_inputs
    asyncio.run(legacy.restore({"seen": 1, "emitted": 0, "blocked": 1, "halted": True}))
    assert legacy._halt_legacy is True and legacy._halt_all is False
    assert entry_request_inputs.halted_for(legacy, "A") is True
    feed(legacy, "_on_reset", {"account_id": "A", "reason": "AUTO_REARM:MAX_EXPOSURE"})
    assert entry_request_inputs.halted_for(legacy, "A") is False
    stamped, _ = build()
    asyncio.run(stamped.restore({"version": "1.25.0", "halted": True, "halt_all": True, "halted_accounts": []}))
    assert stamped._halt_legacy is True and stamped._halt_all is False


# ── (٣) الصحّة ──────────────────────────────────────────────────────────────

def test_halted_requester_is_degraded_not_healthy():
    atom, bus = build()
    assert asyncio.run(atom.health_check()).state.name == "HEALTHY"
    feed(atom, "_on_halt", {"account_id": "ACC"})
    status = asyncio.run(atom.health_check())
    assert status.state.name == "DEGRADED" and "موقوف" in status.message, status
    feed(atom, "_on_size", size_513())
    feed(atom, "_on_decision", decision(49900.0, 50400.0))
    assert asyncio.run(atom.health_check()).state.name == "DEGRADED"
    feed(atom, "_on_reset", {"account_id": "ACC"})
    assert asyncio.run(atom.health_check()).state.name == "HEALTHY"


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_"):
            _fn()
            print("OK", _name)
    print("555 fix 2026-10-02: كلّ الاختبارات خضراء")
