"""إصلاحات ٢٠٢٦-١٠-٠٢ في 552 (ختم المالك «صلح كامل nq») — ملفٌّ جديد، والقديم لا يُمسّ.

ثلاثة أبواب كانت مفتوحة على آخر بوّابة قبل الجسر:
  (١) لا سقف تعرّض قبل الإرسال: 508 يحسب بعد التنفيذ (تدقيق ح-2: USTEC 31.2 لوت ≈ 945k$).
  (٢) تجميد الأصل (519) ونفاد ميزانيّته (518) لا يحجبان طلب 555 (تدقيق ح-3).
  (٣) الصحّة `HEALTHY` والبوّابة مقفلة أو موقوفة (تدقيق ع1).
كلّ اختبارٍ هنا يسقط على الكود السابق (5.15.1) وينجح على 5.16.0.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "clock", FOLDER):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
import clock  # noqa: E402

_spec = importlib.util.spec_from_file_location("_t552_fix", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t552_fix"] = m
_spec.loader.exec_module(m)

ACC, BR, SYM = "A", "BR", "NQ"


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.e = []

    def subscribe(self, *a):
        pass

    async def publish(self, name, payload=None):
        self.e.append((name, payload or {}))

    def of(self, name):
        return [p for n, p in self.e if n == name]


def _sync_clock():
    clock.reset_for_tests()
    clock.configure(max_accepted_offset_s=5, max_sample_age_s=30, stale_after_s=900,
                    max_slew_per_second=.05)
    clock.accept_sample({"median_offset_s": .1, "measured_at": time.time(), "quorum": True},
                        writer="003")


def _run(coro):
    return asyncio.run(coro)


def build(*, enabled=True, asset_gate=True, exposure_cap=True, gross=0.0, equity=1000.0,
          limit=5000.0, contract_size=100.0, step=0.01, vmin=0.01, state="NORMAL",
          breached=False, u=0.1, portfolio=True, exposure_numbers=True):
    """بوّابة جاهزة بكلّ تراخيصها القديمة، ومعها مدخلا البوّابتين الجديدتين."""
    _sync_clock()
    bus = _Bus()
    atom = m.Atom()
    cfg = {"enabled": enabled, "max_spread_points": 0,
           "asset_freeze_gate": asset_gate, "pre_trade_exposure_cap": exposure_cap}
    _run(atom.initialize(m.AtomContext(552, cfg, _Log(), bus.publish, bus.subscribe)))
    _run(atom.start())
    _run(atom._on_account({"account_id": ACC, "broker": BR}))
    _run(atom._on_whitelist({"allowed_by_account": {ACC: [SYM, "USTEC"]}}))
    _run(atom._on_reconcile({"account_id": ACC, "broker": BR, "symbol": "*",
                             "status": "MATCH_EMPTY_ACCOUNT"}))
    for name in (SYM, "USTEC"):
        _run(atom._on_reference({"symbol": name, "state": "HEALTHY"}))
    exposure = {"account_id": ACC, "broker": BR, "usable_for_new_exposure": True}
    if exposure_numbers:
        exposure.update({"gross_exposure": gross, "equity": equity,
                         "max_exposure_pct": limit, "timestamp": time.time()})
    _run(atom._on_exposure(exposure))
    _run(atom._on_specs({"account_id": ACC, "broker": BR, "symbols": [
        {"symbol": SYM, "contract_size": contract_size, "volume_step": step,
         "volume_min": vmin, "tick_value": 1.0, "tick_size": 0.01, "point": 0.01},
        {"symbol": "USTEC", "contract_size": 1.0, "volume_step": 0.1, "volume_min": 0.1,
         "tick_value": 0.01, "tick_size": 0.01, "point": 0.01}]}))
    # صفّ 519 كما ينشره (`519/atom.py:307-328`): الحالة، ومعها حكمُ دفتر 518 منقولًا.
    rows = [{"account_id": ACC, "broker": BR, "symbol": s, "asset_canonical": s,
             "state": state, "paused": False, "breached": breached, "u": u}
            for s in (SYM, "USTEC")]
    if portfolio:
        _run(atom._on_portfolio({"portfolios": rows, "count": len(rows),
                                 "halted_accounts": []}))
    return atom, bus


def order(request_id="r1", **over):
    body = {"magic": 20260801, "account_id": ACC, "broker": BR, "request_id": request_id,
            "action": "OPEN", "symbol": SYM, "side": "BUY", "volume": 3.0,
            "reference_price": 100.0, "stop_loss": 99.0, "take_profit": 104.0,
            "decision_id": "D1", "gate_request_id": "G1"}
    body.update(over)
    return body


def send(atom, bus, body):
    _run(atom._on_margin_verdict({"account_id": ACC, "request_id": body["request_id"],
                                  "approved": True}))
    _run(atom._on_built(dict(body)))
    finals, rejected = bus.of(m.EVENT_FINAL), bus.of(m.EVENT_REJECTED)
    return (finals[-1] if finals else None), (rejected[-1] if rejected else None)


# ── (١) سقف التعرّض قبل الإرسال ─────────────────────────────────────────────

def test_order_under_the_cap_passes_untouched():
    atom, bus = build()                       # الحدّ 5000٪ × 1000$ = 50,000$
    final, _ = send(atom, bus, order(volume=3.0))   # 3 × 100 × 100 = 30,000$
    assert final is not None and final["volume"] == 3.0, final
    assert final["exposure_projected_pct"] == 3000.0 and "volume_before_exposure_cap" not in final


def test_order_over_the_cap_is_cut_down_to_fit_below_it():
    """8 لوت = 80,000$ ⟸ يُقصّ إلى الأدنى: 5.00 يساوي الحدّ (والمساواة خرقٌ عند 508) ⟸ 4.99."""
    atom, bus = build()
    final, _ = send(atom, bus, order(volume=8.0))
    assert final is not None, bus.of(m.EVENT_REJECTED)
    assert final["volume"] == 4.99 and final["volume_before_exposure_cap"] == 8.0, final
    assert final["exposure_projected_pct"] < 5000.0
    assert atom._exposure_reduced == 1


def test_audit_case_ustec_31_lots_never_reaches_the_broker_whole():
    """حالة التدقيق: USTEC 31.2 لوت على 30,300 بحقوق 800$ (≈118,000٪) ⟸ 1.3 لوت (≈4,924٪)."""
    atom, bus = build(equity=800.0)
    final, _ = send(atom, bus, order(symbol="USTEC", volume=31.2, reference_price=30300.0,
                                     stop_loss=30200.0, take_profit=30700.0))
    assert final is not None, bus.of(m.EVENT_REJECTED)
    assert final["volume"] == 1.3 and final["volume_before_exposure_cap"] == 31.2, final
    assert final["exposure_projected_pct"] < 5000.0


def test_no_headroom_below_min_lot_is_refused():
    atom, bus = build(gross=49_990.0)          # يبقى 10$ ⟸ 0.001 لوت < 0.01
    final, rejected = send(atom, bus, order(volume=1.0))
    assert final is None and rejected["reason"] == "EXPOSURE_CAP_BELOW_MIN_LOT", rejected


def test_stale_exposure_state_fails_closed_for_open():
    atom, bus = build()
    atom._exposure[(ACC, BR)]["_received_mono"] -= 11.0   # أقدم من 10 ث
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "EXPOSURE_STATE_STALE", rejected


def test_exposure_state_without_numbers_fails_closed_for_open():
    atom, bus = build(exposure_numbers=False)
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "EXPOSURE_PROJECTION_UNKNOWN", rejected


def test_zero_limit_means_no_cap_like_508():
    atom, bus = build(limit=0.0)
    final, _ = send(atom, bus, order(volume=50.0))
    assert final is not None and final["volume"] == 50.0, final


def test_exits_never_touch_the_cap_or_the_asset_gate():
    atom, bus = build(exposure_numbers=False, state="FROZEN", breached=True)
    atom._exposure[(ACC, BR)]["_received_mono"] -= 999.0
    final, _ = send(atom, bus, order(action="CLOSE_PARTIAL", ticket=7, stop_loss=None,
                                     take_profit=None))
    assert final is not None and final["action"] == "CLOSE_PARTIAL", bus.of(m.EVENT_REJECTED)


# ── (٢) تجميد الأصل وميزانيّته ───────────────────────────────────────────────

def test_frozen_asset_refuses_open():
    atom, bus = build(state="FROZEN")
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "ASSET_FROZEN", rejected
    assert atom._asset_blocked == 1


def test_paused_asset_refuses_open():
    atom, bus = build(state="PAUSED")
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "ASSET_FROZEN", rejected


def test_exhausted_budget_refuses_open_even_when_519_says_hedging():
    """519 يُبقي `HEDGING` على حاله وإن نفدت الميزانيّة — فحكمُ 518 المنقول في الصفّ يُقرأ."""
    atom, bus = build(state="HEDGING", breached=True, u=1.22)
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "ASSET_BUDGET_EXHAUSTED", rejected
    assert rejected["barrier"]["value"] == 1.22 and rejected["barrier"]["threshold"] == 1.0
    atom, bus = build(state="NORMAL", breached=False, u=1.0)   # u = 1 بلا علامة ⟸ نفادٌ أيضًا
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "ASSET_BUDGET_EXHAUSTED", rejected


def test_unknown_asset_state_fails_closed():
    atom, bus = build(portfolio=False)
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "ASSET_STATE_UNKNOWN", rejected
    atom, bus = build()                                         # صفٌّ لرمزٍ آخر لا يكفي
    final, rejected = send(atom, bus, order(symbol="USTEC", reference_price=30300.0,
                                            stop_loss=30200.0, take_profit=30700.0,
                                            volume=0.1))
    assert final is not None, rejected
    atom._portfolios.pop((ACC, "USTEC"))
    final2, rejected = send(atom, bus, order(request_id="r2", symbol="USTEC",
                                             reference_price=30300.0, stop_loss=30200.0,
                                             take_profit=30700.0, volume=0.1))
    assert rejected["reason"] == "ASSET_STATE_UNKNOWN", rejected


def test_normal_asset_with_budget_left_passes():
    atom, bus = build(state="WARNING", u=0.96)   # التحذير ليس تجميدًا (581 يوازن ولا يحجب)
    final, _ = send(atom, bus, order())
    assert final is not None


# ── (٣) الصحّة ──────────────────────────────────────────────────────────────

def _health(atom):
    return _run(atom.health_check())


def test_disabled_gate_is_degraded_even_before_the_first_order():
    atom, _ = build(enabled=False)
    status = _health(atom)
    assert atom._seen == 0 and status.state.name == "DEGRADED", status
    assert "enabled=false" in status.message


def test_halted_gate_is_degraded():
    atom, _ = build()
    _run(atom._on_halt({"account_id": ACC, "reason": "RISK_HALT"}))
    assert _health(atom).state.name == "DEGRADED"
    atom2, _ = build()
    _run(atom2._on_halt({"scope": "SYSTEM"}))
    assert _health(atom2).state.name == "DEGRADED"


def test_switched_off_new_gate_is_degraded_and_announced():
    atom, _ = build(asset_gate=False)
    status = _health(atom)
    assert status.state.name == "DEGRADED" and "مطفأ" in status.message


def test_open_live_gate_is_healthy():
    atom, bus = build()
    assert _health(atom).state.name == "HEALTHY"
    send(atom, bus, order())
    status = _health(atom)
    assert status.state.name == "HEALTHY", status.message


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_"):
            _fn()
            print("OK", _name)
    print("552 fix 2026-10-02: كلّ الاختبارات خضراء")
