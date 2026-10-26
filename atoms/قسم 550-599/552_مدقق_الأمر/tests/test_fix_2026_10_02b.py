"""إصلاح ٢٠٢٦-١٠-٠٢ (ب) في 552 (ختم المالك «صلح كامل nq») — ملفٌّ جديد، والقديم لا يُمسّ.

(١) حالات المطابقة (520) والمرجع (521) والتعرّض (508) كانت تُحفظ بلا عمر وتُقرأ بلا فحص،
    فإن صمت ناشرها بقيت آخر حالةٍ «صالحة» إلى الأبد (تدقيق م-5 وع٢). الآن تُختم لحظة
    الاستلام، وما تجاوز عمره عمرَ صورة المراكز في 609 (`stale_after_s = 10`) يُعامَل مجهولًا
    لأوامر الفتح.
(٢) `WAITING_FOR_ACTUAL` («لا لقطة وسيط لهذا النطاق بعد») كانت تُقبل مطابقةً — غيابُ المعرفة
    يُعامل معاملة المطابقة. الآن تُرفض للفتح (يفشل مغلقًا)، والخروج لا يتأثّر.
كلّ اختبارٍ هنا يسقط على 5.16.0 وينجح على 5.17.0 (عدا الحرّاس المسمّاة «حارس»).
"""
from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "clock", FOLDER):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
import clock  # noqa: E402

_spec = importlib.util.spec_from_file_location("_t552_fix_b", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t552_fix_b"] = m
_spec.loader.exec_module(m)
import order_gates  # noqa: E402  (شقيقُ الذرّة نفسه — مسارها في sys.path أعلاه)

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


def _run(coro):
    return asyncio.run(coro)


def build(*, reconcile_symbol="*", reconcile_status="MATCH_EMPTY_ACCOUNT", exposure_cap=False):
    clock.reset_for_tests()
    clock.configure(max_accepted_offset_s=5, max_sample_age_s=30, stale_after_s=900,
                    max_slew_per_second=.05)
    clock.accept_sample({"median_offset_s": .1, "measured_at": time.time(), "quorum": True},
                        writer="003")
    bus = _Bus()
    atom = m.Atom()
    cfg = {"enabled": True, "max_spread_points": 0,
           "asset_freeze_gate": False, "pre_trade_exposure_cap": exposure_cap}
    _run(atom.initialize(m.AtomContext(552, cfg, _Log(), bus.publish, bus.subscribe)))
    _run(atom.start())
    _run(atom._on_account({"account_id": ACC, "broker": BR}))
    _run(atom._on_whitelist({"allowed_by_account": {ACC: [SYM]}}))
    _run(atom._on_reconcile({"account_id": ACC, "broker": BR, "symbol": reconcile_symbol,
                             "status": reconcile_status}))
    _run(atom._on_reference({"symbol": SYM, "state": "HEALTHY"}))
    _run(atom._on_exposure({"account_id": ACC, "broker": BR, "usable_for_new_exposure": True,
                            "gross_exposure": 0.0, "equity": 1000.0, "max_exposure_pct": 5000.0,
                            "timestamp": time.time()}))
    _run(atom._on_specs({"account_id": ACC, "broker": BR, "symbols": [
        {"symbol": SYM, "contract_size": 1.0, "volume_step": 0.01, "volume_min": 0.01,
         "tick_value": 1.0, "tick_size": 0.01, "point": 0.01}]}))
    return atom, bus


def order(request_id="r1", **over):
    body = {"magic": 20260801, "account_id": ACC, "broker": BR, "request_id": request_id,
            "action": "OPEN", "symbol": SYM, "side": "BUY", "volume": 1.0,
            "reference_price": 100.0, "stop_loss": 99.0, "take_profit": 104.0,
            "decision_id": "D1", "gate_request_id": "G1"}
    body.update(over)
    return body


def send(atom, bus, body):
    _run(atom._on_margin_verdict({"account_id": ACC, "request_id": body["request_id"],
                                  "approved": True}))
    before = len(bus.of(m.EVENT_FINAL)), len(bus.of(m.EVENT_REJECTED))
    _run(atom._on_built(dict(body)))
    finals, rejected = bus.of(m.EVENT_FINAL), bus.of(m.EVENT_REJECTED)
    return (finals[-1] if len(finals) > before[0] else None,
            rejected[-1] if len(rejected) > before[1] else None)


def _age(atom, registry, key, seconds):
    getattr(atom, registry)[key] -= seconds


def test_fresh_states_pass():
    """حارس: حالاتٌ طازجة كلّها ⟸ الأمر يمرّ كما كان."""
    atom, bus = build()
    final, rejected = send(atom, bus, order())
    assert final is not None, rejected


def test_waiting_for_actual_is_not_reconciliation_for_open():
    atom, bus = build(reconcile_symbol=SYM, reconcile_status="WAITING_FOR_ACTUAL")
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "RECONCILIATION_NOT_MATCHED", rejected
    assert rejected["barrier"]["value"] == "WAITING_FOR_ACTUAL", rejected["barrier"]


def test_waiting_for_actual_never_blocks_an_exit():
    """حارس: الخروج والحماية لا يمرّان بهذه البوّابة أصلًا."""
    atom, bus = build(reconcile_symbol=SYM, reconcile_status="WAITING_FOR_ACTUAL")
    for key in list(atom._reconcile_at):
        _age(atom, "_reconcile_at", key, 999.0)
    final, rejected = send(atom, bus, order(action="CLOSE_PARTIAL", ticket=7,
                                            stop_loss=None, take_profit=None))
    assert final is not None and final["action"] == "CLOSE_PARTIAL", rejected


def test_silent_reconciliation_is_unknown_for_open():
    atom, bus = build()
    _age(atom, "_reconcile_at", (ACC, BR), order_gates.STATE_MAX_AGE_S + 1.0)
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "RECONCILIATION_STALE", rejected


def test_silent_reference_is_unknown_for_open():
    atom, bus = build()
    _age(atom, "_reference_at", SYM, order_gates.STATE_MAX_AGE_S + 1.0)
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "REFERENCE_STALE", rejected


def test_silent_exposure_is_unknown_even_with_the_cap_switched_off():
    """سقف التعرّض (5.16.0) يفحص العمر إن كان يحكم؛ وبإطفائه كانت الحالة بلا عمر تمرّ."""
    atom, bus = build(exposure_cap=False)
    atom._exposure[(ACC, BR)]["_received_mono"] -= order_gates.STATE_MAX_AGE_S + 1.0
    final, rejected = send(atom, bus, order())
    assert final is None and rejected["reason"] == "EXPOSURE_STATE_STALE", rejected


def test_a_fresh_publish_revives_the_gate():
    """حارس: العمر من لحظة الاستلام — نشرٌ جديد يعيد الحالة صالحة."""
    atom, bus = build()
    _age(atom, "_reconcile_at", (ACC, BR), 999.0)
    assert send(atom, bus, order("r1"))[0] is None
    _run(atom._on_reconcile({"account_id": ACC, "broker": BR, "symbol": "*",
                             "status": "MATCH_EMPTY_ACCOUNT"}))
    final, rejected = send(atom, bus, order("r2"))
    assert final is not None, rejected


def test_max_age_is_the_positions_picture_staleness_of_609():
    """لا رقم مخترَع: العمر الأقصى هو `stale_after_s` في إعداد 609 نفسه."""
    manifest = (ROOT / "atoms" / "قسم 600-649" / "609_مزامنة_المراكز" / "manifest.yaml")
    found = re.search(r"^\s*stale_after_s:\s*([0-9.]+)\s*$",
                      manifest.read_text(encoding="utf-8"), re.M)
    assert found and float(found.group(1)) == order_gates.STATE_MAX_AGE_S == 10.0, found


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_"):
            _fn()
            print("OK", _name)
    print("552 fix 2026-10-02b: كلّ الاختبارات خضراء")
