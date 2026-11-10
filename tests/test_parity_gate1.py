# -*- coding: utf-8 -*-
"""حرّاس GATE 1 — مرجع تكافؤ القرار.

الحارس الأهمّ ليس «هل يسجّل» بل **«هل يكشف اختلافًا لو وقع»**. مرجعٌ يقول
«متطابق» على سجلّين مختلفين أسوأ من غياب المرجع، لأنّه يمنح إذنًا بالمرور.
"""
from __future__ import annotations

import json
import os

import pytest

from pathlib import Path

from hot import parity

_ROOT = Path(__file__).resolve().parents[1]


def _tick(sequence: int, symbol: str = "XAUUSD", account: str = "52992818",
          broker: str = "Raw Trading Ltd", **over) -> dict:
    row = {"account_id": account, "broker": broker, "symbol": symbol,
           "sequence": sequence, "bid": 2650.10, "ask": 2650.40,
           "price": 2650.25, "timestamp": 1789728431.422, "sequence_gap": 0,
           "out_of_order": False, "provider": "CTRADER", "trace_id": "t-%d" % sequence}
    row.update(over)
    return row


def _cycle_id(sequence: int, symbol: str = "XAUUSD", account: str = "52992818",
              broker: str = "Raw Trading Ltd") -> str:
    return "%s|%s|%s|tick|%d" % (account, broker, symbol, sequence)


def _room(sequence: int, **over) -> dict:
    """⛔ **بلا `cycle_id` وبلا `sequence`** — هكذا ينشره ٤٥١ فعلًا.

    مقيسٌ من لقطةٍ حيّة ٢٠٢٦-٠٩-١٨. والصيغة الأولى من هذا الحارس وضعت
    `cycle_id` هنا من عندها، فمرّت ٢٣ اختبارًا خضراء بينما حقول القرار
    كلّها `null` في التشغيل الحقيقيّ. **حمولة الاختبار تُبنى من الناشر.**
    """
    row = {"account_id": "52992818", "broker": "Raw Trading Ltd",
           "symbol": "XAUUSD", "id": "decision_aggregator", "source": "451",
           "signal": "up", "direction": 12.6047, "confidence": 61.5958,
           "strength": 26.391, "ratio": 59.3496, "readiness_pct": 88.76,
           "room": True, "status": "ok",
           "sections_present": ["150", "200", "250", "300", "350", "400"],
           "trace_id": "trace-%d" % sequence}
    row.update(over)
    return row


def _approved(sequence: int, *, approved: bool = True, **over) -> dict:
    """يحمل `decision_id` **و**`trace_id` الغرفة نفسه — وهو رابطهما."""
    row = {"decision_id": "dec:" + _cycle_id(sequence), "account_id": "52992818",
           "broker": "Raw Trading Ltd", "symbol": "XAUUSD", "timeframe": "tick",
           "approved": approved, "decision_side": "buy", "score": 50.17,
           "barriers": [], "warnings": [], "rejection": None,
           "trace_id": "trace-%d" % sequence}
    row.update(over)
    return row


def _dispatch(sequence: int, **over) -> dict:
    row = {"cycle_id": _cycle_id(sequence), "account_id": "52992818",
           "symbol": "XAUUSD", "executable": True, "side": "BUY",
           "request_id": "dec:%s:req1" % _cycle_id(sequence), "approved": True}
    row.update(over)
    return row


def _run(recorder: parity.ParityRecorder, sequence: int, **over) -> None:
    recorder.observe(parity.TICK_EVENT, _tick(sequence))
    recorder.observe(parity.ROOM_EVENT, _room(sequence, **over.get("room", {})))
    recorder.observe(parity.APPROVED_EVENT,
                     _approved(sequence, **over.get("approved", {})))
    recorder.observe(parity.DISPATCH_EVENT,
                     _dispatch(sequence, **over.get("dispatch", {})))
    recorder.observe(parity.GATE_PASSED_EVENT,
                     {"cycle_id": _cycle_id(sequence), "barriers": []})


# ── التسجيل ──────────────────────────────────────────────────────────────

def test_a_full_cycle_becomes_one_record(tmp_path):
    rec = parity.ParityRecorder(str(tmp_path / "a.jsonl"), grace_s=0.0)
    _run(rec, 7292233)
    assert rec.flush() == 1
    rows = parity.load(str(tmp_path / "a.jsonl"))
    assert list(rows) == [_cycle_id(7292233)]
    row = rows[_cycle_id(7292233)]
    assert row["symbol"] == "XAUUSD"
    assert row["sequence"] == "7292233"
    assert row["signal"] == "up"
    assert row["approved"] is True
    assert row["gate_outcome"] == "passed"
    assert row["saw"] == ["approved", "dispatch", "gate", "room"]


def test_the_tick_is_joined_to_its_decision_by_sequence(tmp_path):
    """التِكّة لا `cycle_id` لها — الربط بالتسلسل، وهو عقد المفتاح كلّه."""
    rec = parity.ParityRecorder(str(tmp_path / "b.jsonl"), grace_s=0.0)
    _run(rec, 7292233)
    rec.flush()
    row = parity.load(str(tmp_path / "b.jsonl"))[_cycle_id(7292233)]
    assert row["tick_bid"] == 2650.10
    assert row["tick_ask"] == 2650.40
    assert row["tick_provider"] == "CTRADER"


def test_a_rejected_decision_names_its_barrier_and_its_stage(tmp_path):
    """والرفض **لا يُنهي** الدورة: البوّابة تليه بالمفتاح نفسه."""
    rec = parity.ParityRecorder(str(tmp_path / "c.jsonl"), grace_s=0.0)
    rec.observe(parity.TICK_EVENT, _tick(7295842))
    rec.observe(parity.ROOM_EVENT, _room(7295842))
    rec.observe(parity.APPROVED_EVENT, _approved(
        7295842, approved=False, decision_side="sell",
        barriers=[{"name": "asset_filter", "value": False,
                   "reason": "FILTER_FAILED"}],
        rejection={"reason": "FILTER_FAILED", "stage": "454"},
        warnings=["BLOCKED_UPSTREAM"]))
    assert rec.flush() == 1
    row = parity.load(str(tmp_path / "c.jsonl"))[_cycle_id(7295842)]
    assert row["approved"] is False
    assert row["rejection_reason"] == "FILTER_FAILED"
    assert row["rejection_stage"] == "454"
    assert row["barrier_names"] == ["asset_filter:FILTER_FAILED"]
    assert row["warnings"] == ["BLOCKED_UPSTREAM"]
    assert row["fate"] == "rejected", "الرفض مصيرٌ نهائيّ لا نقص"
    assert row.get("incomplete") is None


def test_an_unfinished_cycle_is_written_declared_not_forgotten(tmp_path):
    """دورةٌ بلا قرار تُسجَّل `incomplete: true` — الصمت ليس خيارًا."""
    rec = parity.ParityRecorder(str(tmp_path / "d.jsonl"), close_after_s=0.0, grace_s=0.0)
    rec.observe(parity.TICK_EVENT, _tick(7295900))
    rec.observe(parity.ROOM_EVENT, _room(7295900))
    # الإرسال يفتح الدورة ولا يُنهيها — فتبقى ناقصةً حتّى الإغلاق.
    rec.observe(parity.DISPATCH_EVENT, _dispatch(7295900))
    assert rec.close() == 1
    row = parity.load(str(tmp_path / "d.jsonl"))[_cycle_id(7295900)]
    assert row["incomplete"] is True
    assert row["approved"] is None


def test_the_sweep_writes_the_stale_cycle_it_does_not_drop_it(tmp_path):
    """⛔ هذا الحارس وُلد من طفرةٍ **نجت**: كان الاختبار يفحص `close()` وحدها،
    و`_sweep` هو ما يعمل فعلًا كلّ ثانية في التشغيل. فأُسقطت الدورة الناقصة
    في المكنسة صامتةً وبقيت الحرّاس خضراء — وهو بالضبط الإذن الكاذب.
    """
    import time as _time
    rec = parity.ParityRecorder(str(tmp_path / "d2.jsonl"), close_after_s=0.01, grace_s=0.0)
    rec.observe(parity.TICK_EVENT, _tick(7295901))
    rec.observe(parity.ROOM_EVENT, _room(7295901))
    rec.observe(parity.DISPATCH_EVENT, _dispatch(7295901))
    assert len(rec._open) == 1
    _time.sleep(0.02)
    rec._sweep(_time.time())
    assert rec._open == {}, "المكنسة أسقطت الدورة بلا تسجيل"
    assert rec.flush() == 1
    row = parity.load(str(tmp_path / "d2.jsonl"))[_cycle_id(7295901)]
    assert row["incomplete"] is True
    assert row["side"] == "BUY"           # ما وصل يُحفظ، والناقص يُعلَن
    # ⚠️ والغرفة **لا** تُضمّ هنا: `decision.dispatch.state` يحمل أثرًا غير
    #    أثر الغرفة (مقيسٌ حيًّا). الضمّ يقع عبر `decision.approved.state`
    #    وحده، وهذا حدٌّ معلومٌ يُقاس بـ`room_coverage` لا يُخفى.
    assert row["signal"] is None


def test_a_room_held_too_long_is_swept_and_does_not_leak(tmp_path):
    """الغرفة المحفوظة بأثرها لا تتراكم أبدًا — لها مكنستها أيضًا."""
    import time as _time
    rec = parity.ParityRecorder(str(tmp_path / "d4.jsonl"), close_after_s=0.01, grace_s=0.0)
    rec.observe(parity.ROOM_EVENT, _room(7295903))
    assert len(rec._room_by_trace) == 1
    _time.sleep(0.02)
    rec._sweep(_time.time())
    assert rec._room_by_trace == {}, "غرفةٌ محفوظةٌ تسرّبت"


def test_the_sweep_is_actually_reachable_from_observe(tmp_path):
    """وحارسٌ ثانٍ: المكنسة موصولةٌ بالمسار، لا دالّةٌ لا يناديها أحد."""
    rec = parity.ParityRecorder(str(tmp_path / "d3.jsonl"), grace_s=0.0)
    assert rec._last_sweep == 0.0
    rec.observe(parity.ROOM_EVENT, _room(7295902))
    assert rec._last_sweep > 0.0, "`observe` لا يبلغ المكنسة"


def test_events_outside_the_six_are_ignored_cheaply(tmp_path):
    rec = parity.ParityRecorder(str(tmp_path / "e.jsonl"), grace_s=0.0)
    for _ in range(500):
        rec.observe("analysis.trend.state", {"cycle_id": "x", "symbol": "XAUUSD"})
    assert rec.observed == 0
    assert rec.flush() == 0


def test_a_payload_without_identity_is_counted_not_swallowed(tmp_path):
    rec = parity.ParityRecorder(str(tmp_path / "f.jsonl"), grace_s=0.0)
    rec.observe(parity.ROOM_EVENT, {"signal": "up"})      # ولا `trace_id`
    assert rec.dropped_no_key == 1
    assert rec.flush() == 0


def test_the_room_is_joined_to_its_cycle_by_trace_id(tmp_path):
    """⛔ الحارس الذي وُلد من التشغيل الحيّ لا من الورق.

    `decision.room.state` بلا `cycle_id`؛ رابطه الوحيد `trace_id` المشترك مع
    `decision.approved.state`. ولولا هذا لبقيت حقول القرار كلّها `null` —
    وهي أخطر ما تُقارَن عليه بوّابة التكافؤ.
    """
    rec = parity.ParityRecorder(str(tmp_path / "f2.jsonl"), grace_s=0.0)
    rec.observe(parity.ROOM_EVENT, _room(7300001))        # يصل أوّلًا، ويُحفظ
    assert rec.rooms_held == 1
    assert rec.dropped_no_key == 0
    rec.observe(parity.APPROVED_EVENT, _approved(7300001, approved=False))
    assert rec.rooms_joined == 1
    assert rec.close() == 1
    row = parity.load(str(tmp_path / "f2.jsonl"))[_cycle_id(7300001)]
    assert row["signal"] == "up"
    assert row["confidence"] == 61.5958
    assert row["strength"] == 26.391
    assert row["sections_present"] == ["150", "200", "250", "300", "350", "400"]
    assert row["room_joined_by"] == "trace_id"


def test_decision_fields_are_never_silently_null_in_a_complete_cycle(tmp_path):
    """حارسُ العمى: دورةٌ كاملةٌ وحقولُ قرارها `null` = مرجعٌ يمنح إذنًا كاذبًا."""
    rec = parity.ParityRecorder(str(tmp_path / "f3.jsonl"), grace_s=0.0)
    _run(rec, 7300002)
    rec.flush()
    row = parity.load(str(tmp_path / "f3.jsonl"))[_cycle_id(7300002)]
    empty = [f for f in parity.DECISION_FIELDS if row.get(f) is None]
    assert not empty, "حقول قرارٍ فارغة في دورةٍ كاملة: %s" % empty


# ── المقارنة — وهي سبب وجود البوّابة ─────────────────────────────────────

def _two_runs(tmp_path, mutate: dict | None = None):
    left = parity.ParityRecorder(str(tmp_path / "L.jsonl"), runtime="legacy", grace_s=0.0)
    right = parity.ParityRecorder(str(tmp_path / "R.jsonl"), runtime="hot", grace_s=0.0)
    for seq in (1001, 1002, 1003):
        _run(left, seq)
        _run(right, seq, **(mutate or {}))
    left.flush()
    right.flush()
    return (parity.load(str(tmp_path / "L.jsonl")),
            parity.load(str(tmp_path / "R.jsonl")))


def test_identical_runs_report_full_parity(tmp_path):
    result = parity.compare(*_two_runs(tmp_path))
    assert result["parity"] is True
    assert result["identical"] == 3
    assert result["differing"] == 0
    assert result["by_field"] == {}


@pytest.mark.parametrize("field,group,mutation", [
    ("signal", "القرار", {"room": {"signal": "down"}}),
    ("confidence", "القرار", {"room": {"confidence": 12.0}}),
    ("approved", "الموافقة", {"approved": {"approved": False}}),
    ("decision_side", "الموافقة", {"approved": {"decision_side": "sell"}}),
    ("score", "الموافقة", {"approved": {"score": 99.9}}),
    ("side", "نيّة الأمر", {"dispatch": {"side": "SELL"}}),
    ("executable", "نيّة الأمر", {"dispatch": {"executable": False}}),
])
def test_every_meaningful_difference_is_caught_and_classified(
        tmp_path, field, group, mutation):
    """سبع طفراتٍ تمسّ المال — ولا واحدةٌ تمرّ بصمت."""
    result = parity.compare(*_two_runs(tmp_path, mutation))
    assert result["parity"] is False, "اختلاف %s مرّ بصمت" % field
    assert field in result["by_field"], "لم يُسمَّ الحقل %s" % field
    assert result["by_field"][field]["group"] == group
    assert result["by_field"][field]["count"] == 3
    assert result["by_field"][field]["example"]["cycle_id"]


def test_a_missing_cycle_on_either_side_breaks_parity(tmp_path):
    left, right = _two_runs(tmp_path)
    right.pop(next(iter(right)))
    result = parity.compare(left, right)
    assert result["parity"] is False
    assert result["only_left_count"] == 1


def test_parity_is_false_on_two_empty_logs(tmp_path):
    """⛔ فراغٌ ليس تكافؤًا — وإلّا مرّت بوّابةٌ لم تُشغَّل أصلًا."""
    assert parity.compare({}, {})["parity"] is False


def test_the_report_names_the_field_and_shows_an_example(tmp_path):
    result = parity.compare(*_two_runs(tmp_path, {"room": {"signal": "down"}}))
    text = parity.format_report(result)
    assert "لا تكافؤ" in text
    assert "signal" in text
    assert "القرار" in text


def test_install_is_off_without_the_environment_variable(monkeypatch):
    monkeypatch.delenv("NQ_PARITY", raising=False)

    class _Bus:
        def subscribe_all(self, *a, **k):
            raise AssertionError("رُكّب بلا طلب")

    assert parity.install(_Bus()) is None


def test_a_bus_without_named_subscribe_falls_back_and_says_so(tmp_path):
    """⛔ العقد انقلب: القناة المسمّاة هي الأصل، والعامّة تراجعٌ **معلَن**.

    كان هذا الحارس يمنع `subscribe` بالاسم. والمقيس بعده أنّ المشترِك
    العامّ يُدمَج (`latest(name, symbol)` كلّ ثانية) فيبتلع الغرف. فصار
    التراجع مسموحًا لناقلٍ لا يملك `subscribe` — لكنّه **يُسمّي نفسه**
    `مدموج` في `channel` فلا يُظنّ كاملًا.
    """
    seen = {}

    class _OldBus:
        def subscribe_all(self, handler, *, subscriber="", isolate_payload=True):
            seen["handler"] = handler
            seen["subscriber"] = subscriber

    rec = parity.install(_OldBus(), path=str(tmp_path / "g.jsonl"))
    assert rec is not None
    assert rec.channel == "cold:global(مدموج)"
    assert "مدموج" in rec.stats()["channel"]
    seen["handler"](parity.TICK_EVENT, _tick(2001))
    assert rec.observed == 1


def test_the_handler_never_raises_into_the_bus(tmp_path):
    """مسجّلٌ يُسقط النواة أسوأ من مسجّلٍ صامت — يُعدّ ولا يرفع."""
    seen = {}

    class _Bus:
        def subscribe_all(self, handler, **k):
            seen["handler"] = handler

    parity.install(_Bus(), path=str(tmp_path / "h.jsonl"))

    class _Evil(dict):
        def get(self, *a, **k):
            raise RuntimeError("حمولةٌ خبيثة")

    seen["handler"](parity.ROOM_EVENT, _Evil())       # لا يرفع


def test_rounding_is_stable_and_not_a_tolerance(tmp_path):
    """التدوير ثابتٌ عند ستّ خانات — واختلافٌ فوقها يبقى اختلافًا."""
    assert parity._num(1.0000001) == 1.0
    assert parity._num(1.0000011) == 1.000001
    assert parity._num(1.1) != parity._num(1.2)
    assert parity._num(True) is True
    assert parity._num(None) is None
    assert parity._num("up") == "up"


def test_coverage_exposes_blind_cycles(tmp_path):
    """التغطية تُظهر العمى بدل أن تُخفيه خلف «تكافؤ»."""
    rec = parity.ParityRecorder(str(tmp_path / "cov.jsonl"), close_after_s=0.0, grace_s=0.0)
    _run(rec, 8001)                                   # دورةٌ كاملة
    rec.observe(parity.DISPATCH_EVENT, _dispatch(8002))   # بلا غرفةٍ ولا قرار
    rec.close()
    cov = parity.coverage(parity.load(str(tmp_path / "cov.jsonl")))
    assert cov["cycles"] == 2
    # الإرسال بلا موافقةٍ دورةُ بوّابة — فلا يُحسب عمًى في مسار القرار.
    assert cov["decision_cycles"] == 1
    assert cov["decision_room_coverage"] == 1.0
    assert cov["blind_decision_cycles"] == 0
    assert cov["gate_cycles"] == 1
    assert cov["gate_only"] == 0          # رأت إرسالًا لا بوّابةً وحدها
    # الإرسال ليس مصيرًا نهائيًّا، فتُغلقها المكنسة ناقصةً **معلَنة**.
    assert cov["incomplete"] == 1


def test_full_coverage_reads_one(tmp_path):
    rec = parity.ParityRecorder(str(tmp_path / "cov2.jsonl"), grace_s=0.0)
    for seq in (8101, 8102, 8103):
        _run(rec, seq)
    rec.flush()
    cov = parity.coverage(parity.load(str(tmp_path / "cov2.jsonl")))
    assert cov["decision_cycles"] == 3
    assert cov["decision_room_coverage"] == 1.0
    assert cov["approval_coverage"] == 1.0
    assert cov["tick_coverage"] == 1.0
    assert cov["blind_decision_cycles"] == 0
    assert cov["gate_cycles"] == 0


def test_a_gate_arriving_after_the_rejection_stays_in_the_same_record(tmp_path):
    """⛔ حارسٌ وُلد من التشغيل الحيّ: كان الرفض يُغلق الدورة، فتصل البوّابة
    بعده بالمفتاح نفسه وتفتح **سجلًّا ثانيًا أعمى**، و`load` تفهرس بآخر سطر
    فيدهس الأعمى الكامل. المقيس: تغطية 40٪ و٦٠ دورةً بلا حقول قرار.
    """
    import time as _time
    rec = parity.ParityRecorder(str(tmp_path / "g2.jsonl"), grace_s=0.05)
    rec.observe(parity.TICK_EVENT, _tick(7300582))
    rec.observe(parity.ROOM_EVENT, _room(7300582))
    rec.observe(parity.APPROVED_EVENT, _approved(7300582, approved=False))
    rec.observe(parity.GATE_BLOCKED_EVENT, {
        "cycle_id": _cycle_id(7300582),
        "barriers": [{"name": "asset_filter", "value": False,
                      "reason": "FILTER_FAILED"}]})
    _time.sleep(0.06)
    rec._sweep(_time.time())
    assert rec.flush() == 1, "الدورة الواحدة صارت سجلّين"
    rows = parity.load(str(tmp_path / "g2.jsonl"))
    assert len(rows) == 1
    row = rows[_cycle_id(7300582)]
    assert row["saw"] == ["approved", "gate", "room"]
    assert row["signal"] == "up"            # لم يُدهَس
    assert row["approved"] is False
    assert row["gate_outcome"] == "blocked"
    assert row["fate"] == "blocked", "البوّابة تعلو الرفض في وصف المصير"
    assert row["tick_bid"] == 2650.10


def test_a_rejection_without_a_gate_is_a_fate_not_a_gap(tmp_path):
    """⛔ رفضٌ لا بوّابة له **مصيرٌ نهائيّ لا نقص**.

    سلسلة المالك: room ⟶ approved/rejected ⟶ gate ⟶ send/no-send. فالرفض
    ينهي الدورة بذاته. وكان يُوصَف `incomplete` ظلمًا — ١٠٧ دورةً من ٢٩٠
    على النواة الحيّة وُسمت نقصًا وهي تامّة المصير.
    """
    rec = parity.ParityRecorder(str(tmp_path / "g3.jsonl"), grace_s=0.0)
    rec.observe(parity.ROOM_EVENT, _room(7300583))
    rec.observe(parity.APPROVED_EVENT, _approved(7300583, approved=False))
    assert rec.flush() == 1
    row = parity.load(str(tmp_path / "g3.jsonl"))[_cycle_id(7300583)]
    assert row.get("incomplete") is None, "مصيرٌ تامٌّ وُصف نقصًا"
    assert row["fate"] == "rejected"
    assert row["approved"] is False
    assert row["signal"] == "up"


# ── ملكيّة الدورة: تُغلق مرّةً واحدة ولا تُفتح ثانيةً ──────────────────────

def test_a_closed_cycle_is_never_reopened_by_a_late_event(tmp_path):
    """أمر المالك: «لا يجوز لأيّ حدثٍ لاحق أن يفتح سجلّ دورةٍ بالمفتاح نفسه»."""
    rec = parity.ParityRecorder(str(tmp_path / "own.jsonl"), grace_s=0.0)
    _run(rec, 9001)
    assert rec.flush() == 1
    rec.observe(parity.GATE_BLOCKED_EVENT, {"cycle_id": _cycle_id(9001)})
    rec.observe(parity.DISPATCH_EVENT, _dispatch(9001))
    assert rec.late_after_close == 2
    assert rec._open == {}
    assert rec.flush() == 0, "حدثٌ متأخّر فتح سجلًّا ثانيًا"
    report: dict = {}
    parity.load(str(tmp_path / "own.jsonl"), report=report)
    assert report["duplicate_cycle_ids"] == 0
    assert report["lines"] == report["unique"] == 1


def test_the_grace_period_lets_a_late_gate_land_in_the_same_record(tmp_path):
    """المهلة سببُ وجودها: النهاية لا تُغلق فورًا كي يلحق المتأخّر."""
    import time as _time
    rec = parity.ParityRecorder(str(tmp_path / "gr.jsonl"), grace_s=0.05)
    rec.observe(parity.TICK_EVENT, _tick(9002))
    rec.observe(parity.ROOM_EVENT, _room(9002))
    rec.observe(parity.APPROVED_EVENT, _approved(9002))
    rec.observe(parity.GATE_PASSED_EVENT, {"cycle_id": _cycle_id(9002)})
    assert rec.flush() == 0, "أُغلقت قبل انقضاء المهلة"
    rec.observe(parity.DISPATCH_EVENT, _dispatch(9002))    # لحق
    _time.sleep(0.06)
    rec._sweep(_time.time())
    assert rec.flush() == 1
    row = parity.load(str(tmp_path / "gr.jsonl"))[_cycle_id(9002)]
    assert row["saw"] == ["approved", "dispatch", "gate", "room"]
    assert row.get("incomplete") is None, "مكتملةٌ وُصفت ناقصة"


def test_a_room_arriving_after_its_decision_still_joins(tmp_path):
    """الترتيب غير مضمون — والغرفة المتأخّرة تجد دورتها بفهرس الأثر."""
    rec = parity.ParityRecorder(str(tmp_path / "late.jsonl"), grace_s=0.0)
    rec.observe(parity.TICK_EVENT, _tick(9003))
    rec.observe(parity.APPROVED_EVENT, _approved(9003))    # القرار أوّلًا
    rec.observe(parity.ROOM_EVENT, _room(9003))            # الغرفة بعده
    assert rec.rooms_late_joined == 1
    assert rec.close() == 1
    row = parity.load(str(tmp_path / "late.jsonl"))[_cycle_id(9003)]
    assert row["signal"] == "up"
    assert row["room_joined_by"] == "trace_id:late"


def test_a_gate_only_cycle_is_not_blind_because_the_gate_carries_approval(tmp_path):
    """⛔ مقيسٌ حيًّا: `decision.gate.blocked` مصدره ٤٦٦ ويحمل الموافقة كاملةً.

    ثلاثٌ وثلاثون دورةً عُدَّت «عمياء» وهي ليست كذلك — المسجّل لم يقرأ.
    """
    rec = parity.ParityRecorder(str(tmp_path / "go.jsonl"), grace_s=0.0)
    rec.observe(parity.GATE_BLOCKED_EVENT, {
        "cycle_id": _cycle_id(9004), "account_id": "52992818",
        "broker": "Raw Trading Ltd", "symbol": "US500", "timeframe": "tick",
        "approved": False, "decision_side": "sell", "score": 100.0,
        "signal": "none", "gate_state": "BLOCKED",
        "barriers": [{"name": "asset_filter", "value": False,
                      "reason": "FILTER_FAILED"}],
        "rejection": {"reason": "FILTER_FAILED", "stage": "454"}})
    assert rec.flush() == 1
    row = parity.load(str(tmp_path / "go.jsonl"))[_cycle_id(9004)]
    assert row["approved"] is False
    assert row["decision_side"] == "sell"
    assert row["score"] == 100.0
    assert row["rejection_reason"] == "FILTER_FAILED"
    assert row["rejection_stage"] == "454"
    assert row["gate_state"] == "BLOCKED"
    assert row["gate_outcome"] == "blocked"


# ── `null == null` ───────────────────────────────────────────────────────

def test_null_equals_null_on_a_required_field_is_not_a_match(tmp_path):
    """حقلُ قرارٍ فارغٌ على الجانبين = لا شيءَ قُورِن. يُعدّ ويُسقط التكافؤ."""
    # ⚠️ `saw` فيها "approved" — أي **دورةُ قرار**. ودورةُ البوّابة بلا
    #    غرفةٍ بحقٍّ، فلا تُعدّ فراغًا (حكم المالك: لا نخلط المسارين).
    blind = {"cycle_id": "k", "account_id": "a", "broker": "b",
             "symbol": "EURUSD", "timeframe": "tick", "sequence": "1",
             "saw": ["approved"],
             "approved": None, "signal": None, "direction": None}
    result = parity.compare({"k": dict(blind)}, {"k": dict(blind)})
    assert result["vacuous_matches"] > 0
    assert result["vacuous_cycles"] == 1
    # ⚠️ `signal` خرج من `REQUIRED_FIELDS` بختم (ج): قناة الغرفة مدموجة.
    #    و`approved` بقي — يصل بلا دمجٍ فغيابه عمًى حقيقيّ.
    assert "approved" in result["vacuous_by_field"]
    assert "signal" not in result["vacuous_by_field"]
    assert result["parity"] is False, "فراغٌ مُنح تكافؤًا"


def test_a_conditionally_null_field_matching_null_is_a_real_match(tmp_path):
    """وليس كلّ فراغٍ عمًى: `rejection_reason` فارغٌ بحقٍّ عند الموافقة."""
    result = parity.compare(*_two_runs(tmp_path))
    assert result["parity"] is True
    assert result["vacuous_matches"] == 0
    assert "rejection_reason" not in result["vacuous_by_field"]


# ── بوّابة الإغلاق ───────────────────────────────────────────────────────

def _replay_pair(tmp_path, seqs=(7001, 7002, 7003)):
    """إعادتان لنفس الشريط — وهما ما تُحكَم عليه البوّابة، لا سجلٌّ بنفسه."""
    a = parity.ParityRecorder(str(tmp_path / "A.jsonl"), runtime="replay-a",
                              grace_s=0.0)
    b = parity.ParityRecorder(str(tmp_path / "B.jsonl"), runtime="replay-b",
                              grace_s=0.0)
    for seq in seqs:
        _run(a, seq)
        _run(b, seq)
    a.close()
    b.close()
    return (parity.load(str(tmp_path / "A.jsonl")),
            parity.load(str(tmp_path / "B.jsonl")))


def _closure(tmp_path, rows=None, **over):
    left, right = _replay_pair(tmp_path)
    kw = {"load_report": {"duplicate_cycle_ids": 0},
          "replay_result": parity.compare(left, right),
          "mutation_caught": 21, "mutation_total": 21}
    kw.update(over)
    return parity.closure(rows if rows is not None else left, **kw)


def test_closure_passes_when_every_criterion_holds(tmp_path):
    result = _closure(tmp_path)
    assert result["closed"] is True, parity.format_closure(result)
    for key, _label in parity.CLOSURE_CRITERIA:
        assert result["checks"][key][2] is True, key


@pytest.mark.parametrize("over,failing", [
    ({"load_report": {"duplicate_cycle_ids": 3}}, "duplicate_cycle_ids"),
    ({"mutation_caught": 20}, "mutation_guards"),
    ({"replay_result": None}, "replay_identical"),
])
def test_closure_names_the_failing_criterion(tmp_path, over, failing):
    result = _closure(tmp_path, **over)
    assert result["closed"] is False
    assert result["checks"][failing][2] is False
    assert "لا يُفتح §5" in parity.format_closure(result)


def test_a_log_compared_with_itself_cannot_close_the_gate(tmp_path):
    """⛔ أخطر إذنٍ كاذب: بوّابةٌ تُغلق بمقارنةِ سجلٍّ بنفسه."""
    left, _right = _replay_pair(tmp_path)
    result = parity.closure(left, load_report={"duplicate_cycle_ids": 0},
                            replay_result=parity.compare(left, left),
                            mutation_caught=21, mutation_total=21)
    assert result["checks"]["self_comparison"][2] is False
    assert result["closed"] is False


def test_a_drifting_replay_cannot_close_the_gate(tmp_path):
    """وإعادةٌ تخالف إعادةً — ولو بحقلٍ واحد — تُسقط الإغلاق."""
    left, right = _replay_pair(tmp_path)
    key = next(iter(right))
    right[key] = dict(right[key], approved=not right[key]["approved"])
    result = parity.closure(left, load_report={"duplicate_cycle_ids": 0},
                            replay_result=parity.compare(left, right),
                            mutation_caught=21, mutation_total=21)
    assert result["checks"]["replay_identical"][2] is False
    assert result["closed"] is False


def test_a_room_that_never_arrived_no_longer_fails_the_gate(tmp_path):
    """⛔ ختم المالك (ج) ٢٠٢٦-٠٩-١٨: `decision.room.state` قناةُ حالةٍ مدموجة
    لا سجلٌّ لكلّ دورة. مفتاح الدمج في النواة `(event, account, symbol, id)`
    بلا `trace_id`، فالأحدث يحلّ محلّ الأقدم **بالعقد** (مقيس 66.6٪ ثابتة).
    فاشتراطُ غرفةٍ لكلّ دورةٍ ليس ثابتًا صحيحًا — ويبقى الرقم **مقيسًا**.
    """
    left, right = _replay_pair(tmp_path)
    for rows in (left, right):
        key = sorted(rows)[0]
        for field in parity.DECISION_FIELDS:
            rows[key] = dict(rows[key], **{field: None})
    result = parity.closure(left, load_report={"duplicate_cycle_ids": 0},
                            replay_result=parity.compare(left, right),
                            mutation_caught=21, mutation_total=21)
    assert result["closed"] is True, parity.format_closure(result)
    assert result["coverage"]["room_missing"] == 1      # يُقاس ولا يُسقِط
    assert "room_absent" in parity.format_closure(result)


def test_a_missing_approval_still_fails_the_gate(tmp_path):
    """والموافقة تبقى شرطًا: تصل بلا دمج، فغيابها عمًى حقيقيّ."""
    left, right = _replay_pair(tmp_path)
    for rows in (left, right):
        key = sorted(rows)[0]
        rows[key] = dict(rows[key], approved=None)
    result = parity.closure(left, load_report={"duplicate_cycle_ids": 0},
                            replay_result=parity.compare(left, right),
                            mutation_caught=21, mutation_total=21)
    assert result["checks"]["approval_coverage"][2] is False
    assert result["checks"]["vacuous_matches"][2] is False
    assert result["closed"] is False


def test_a_duplicated_cycle_id_in_the_file_is_counted(tmp_path):
    """⛔ وُلد من طفرةٍ نجت: كان الحارس يفحص العدّاد على ملفٍّ بلا ازدواج،
    فيُعطى صفرًا سواءٌ عُدَّ أم لم يُعدّ. الازدواج يُزرَع ليُقاس.
    """
    path = tmp_path / "dup.jsonl"
    row = {"cycle_id": "X|b|EURUSD|tick|1", "symbol": "EURUSD", "signal": "up"}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.write(json.dumps(dict(row, signal="down")) + "\n")   # المفتاح نفسه
        fh.write(json.dumps(dict(row, cycle_id="X|b|GBPUSD|tick|2")) + "\n")
    report: dict = {}
    rows = parity.load(str(path), report=report)
    assert report["lines"] == 3
    assert report["unique"] == 2
    assert report["duplicate_cycle_ids"] == 1, "ازدواجٌ لم يُعدّ"
    assert report["duplicate_examples"][0][0] == "X|b|EURUSD|tick|1"
    assert rows["X|b|EURUSD|tick|1"]["signal"] == "down"    # آخر سطرٍ يفوز
    result = parity.closure(rows, load_report=report,
                            replay_result=parity.compare(rows, rows),
                            mutation_caught=21, mutation_total=21)
    assert result["closed"] is False
    assert result["checks"]["duplicate_cycle_ids"][2] is False


def test_two_cycles_sharing_one_trace_both_get_the_room(tmp_path):
    """⛔ كانت الغرفة تُنتزَع، فيبتلعها أوّل ضامٍّ وتبقى الأخرى عمياء.

    مقيسٌ حيًّا: ٨٠ دورةً من ٢٩٠ بلا حقول قرار لهذا السبب وحده. والغرفة
    حالةُ تِكّةٍ لا ملكَ دورةٍ واحدة — فتُنسَخ وتُترك للمكنسة.
    """
    rec = parity.ParityRecorder(str(tmp_path / "share.jsonl"), grace_s=0.0)
    rec.observe(parity.ROOM_EVENT, _room(9500))
    rec.observe(parity.APPROVED_EVENT, _approved(9500, approved=False))
    rec.observe(parity.APPROVED_EVENT, dict(
        _approved(9501, approved=False), trace_id="trace-9500"))
    assert rec.flush() == 2
    rows = parity.load(str(tmp_path / "share.jsonl"))
    assert len(rows) == 2
    for key in (_cycle_id(9500), _cycle_id(9501)):
        assert rows[key]["signal"] == "up", "دورةٌ حُرمت غرفتها"
        assert rows[key]["confidence"] == 61.5958


def test_a_room_that_joins_late_is_still_kept_for_later_cycles(tmp_path):
    """⛔ كانت الغرفة اللاحقة تُفيَّض في دورتها ثمّ **تُنسى**، فالبوّابة التي
    تشارك الأثر نفسه بعدها لا تجد غرفة. المقيس: ٧٤ دورةً بلا حقول قرار،
    أكثرها بوّابةٌ وحدها. تُحفَظ الآن دائمًا ولو لحقت.
    """
    rec = parity.ParityRecorder(str(tmp_path / "keep.jsonl"), grace_s=0.0)
    rec.observe(parity.APPROVED_EVENT, _approved(9600))       # يفتح الدورة
    rec.observe(parity.ROOM_EVENT, _room(9600))               # يلحق بها
    assert rec.rooms_late_joined == 1
    assert rec._room_by_trace, "الغرفة لم تُحفَظ بعد اللحاق"
    rec.observe(parity.GATE_BLOCKED_EVENT, dict(
        _approved(9601, approved=False), trace_id="trace-9600"))
    rec.close()
    rows = parity.load(str(tmp_path / "keep.jsonl"))
    assert rows[_cycle_id(9601)]["signal"] == "up", "بوّابةٌ حُرمت غرفتها"


# ── تصنيف المسارين (حكم المالك ٢٠٢٦-٠٩-١٨) ──────────────────────────────

def test_a_cycle_without_an_approved_event_is_a_gate_cycle(tmp_path):
    """البوّابة قد تكون إعادة تقييمٍ لاحقة — فلا تُشترط لها غرفة."""
    rec = parity.ParityRecorder(str(tmp_path / "kind.jsonl"), grace_s=0.0)
    _run(rec, 9700)                                   # دورة قرارٍ كاملة
    rec.observe(parity.GATE_BLOCKED_EVENT, {
        "cycle_id": _cycle_id(9701), "approved": False,
        "decision_side": "sell", "score": 1.0, "barriers": []})
    rec.close()
    rows = parity.load(str(tmp_path / "kind.jsonl"))
    assert parity.cycle_kind(rows[_cycle_id(9700)]) == parity.KIND_DECISION
    assert parity.cycle_kind(rows[_cycle_id(9701)]) == parity.KIND_GATE
    cov = parity.coverage(rows)
    assert cov["decision_cycles"] == 1
    assert cov["gate_cycles"] == 1
    assert cov["decision_room_coverage"] == 1.0
    assert cov["blind_decision_cycles"] == 0
    assert cov["gate_only"] == 1




def test_the_tape_records_inputs_in_arrival_order(tmp_path):
    tape = tmp_path / "t.jsonl"
    rec = parity.ParityRecorder(str(tmp_path / "r.jsonl"), grace_s=0.0,
                                tape_path=str(tape))
    _run(rec, 9800)
    rec.close()
    rows = [json.loads(ln) for ln in tape.read_text(encoding="utf-8").splitlines() if ln]
    assert [r["i"] for r in rows] == list(range(len(rows)))
    assert [r["name"] for r in rows] == [
        parity.TICK_EVENT, parity.ROOM_EVENT, parity.APPROVED_EVENT,
        parity.DISPATCH_EVENT, parity.GATE_PASSED_EVENT]


def test_the_tape_is_off_without_a_path(tmp_path):
    rec = parity.ParityRecorder(str(tmp_path / "r2.jsonl"), grace_s=0.0)
    _run(rec, 9801)
    rec.close()
    assert rec.taped == 0
    assert not list(tmp_path.glob("*t*.jsonl"))


def test_replaying_the_same_tape_twice_gives_an_identical_reference(tmp_path):
    """حتميّةُ المرجع — شرطٌ سابقٌ لأيّ حكمٍ بالتكافؤ.

    مرجعٌ يختلف عن نفسه لا يحكم على غيره.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "parity_replay", str(_ROOT / "tools" / "parity_replay.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    tape = tmp_path / "t3.jsonl"
    rec = parity.ParityRecorder(str(tmp_path / "r3.jsonl"), grace_s=0.0,
                                tape_path=str(tape))
    for seq in (9810, 9811, 9812):
        _run(rec, seq)
    rec.observe(parity.GATE_BLOCKED_EVENT, {"cycle_id": _cycle_id(9813),
                                            "approved": False, "barriers": []})
    rec.close()

    events = mod.read_tape(str(tape))
    assert len(events) == 16
    a = mod.replay(events, str(tmp_path / "a.jsonl"), runtime="a")
    b = mod.replay(events, str(tmp_path / "b.jsonl"), runtime="b")
    result = parity.compare(a, b, ignore=("runtime",))
    assert result["parity"] is True, parity.format_report(result)
    assert result["vacuous_matches"] == 0
    assert result["differing"] == 0


def test_a_shuffled_tape_is_not_silently_equal(tmp_path):
    """والترتيب جزءٌ من المدخلات: شريطٌ مبعثرٌ يجب ألّا يُعطي المرجع نفسه."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "parity_replay2", str(_ROOT / "tools" / "parity_replay.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    tape = tmp_path / "t4.jsonl"
    rec = parity.ParityRecorder(str(tmp_path / "r4.jsonl"), grace_s=0.0,
                                tape_path=str(tape))
    _run(rec, 9820)
    rec.close()
    events = mod.read_tape(str(tape))
    a = mod.replay(events, str(tmp_path / "a4.jsonl"), runtime="a")
    # البوّابة قبل الغرفة والقرار — ترتيبٌ مستحيلٌ في النواة
    b = mod.replay(list(reversed(events)), str(tmp_path / "b4.jsonl"), runtime="b")
    result = parity.compare(a, b, ignore=("runtime",))
    assert result["parity"] is False, "الترتيب لم يُحدث فرقًا — المقارنة عمياء"




def test_install_uses_a_named_cold_channel_not_a_global_one(tmp_path):
    """⛔ الشرط الحاسم: اشتراكٌ **بالاسم على البارد** يُعفي الحدث من الدمج،
    ولا يدخل المسار الساخن. البادئة `cold:` هي ما يحوّله (`engine.py:287`).
    """
    named: list[tuple[str, str]] = []
    handlers_seen: list = []

    class _Bus:
        def subscribe(self, event_name, handler, *, subscriber="",
                      isolate_payload=True):
            named.append((event_name, subscriber))
            handlers_seen.append(handler)

        def subscribe_all(self, *a, **k):               # pragma: no cover
            raise AssertionError("رجع إلى المشترِك العامّ — يُدمَج")

    rec = parity.install(_Bus(), path=str(tmp_path / "n.jsonl"))
    assert rec is not None
    assert [e for e, _s in named] == list(parity.WATCHED)
    assert {s for _e, s in named} == {"cold:parity"}
    assert all(s.startswith("cold:") for _e, s in named), \
        "اشتراكٌ مسمّى بلا `cold:` يقع على المسار الساخن"
    assert rec.channel.startswith("cold:named")
    # معالجٌ واحدٌ لستّة أسماء ⟵ صندوقُ بريدٍ واحد ⟵ الترتيب محفوظ.
    assert len({id(h) for h in handlers_seen}) == 1, "ستّة صناديق تُعيد الترتيب"


def test_the_named_handler_reads_the_event_name_from_the_bus_context(tmp_path):
    """عقد الناقل البارد: المعالج المسمّى يُنادى **بالحمولة وحدها**، واسم
    الحدث يوضع في `current_event` قبل النداء (`event_bus._invoke`). فمعالجٌ
    واحدٌ يخدم ستّة أسماء يقرأ اسمه من السياق لا من وسيطٍ ممرَّر.
    """
    from core.event_bus import current_event

    handlers: list = []

    class _Bus:
        def subscribe(self, event_name, handler, **k):
            handlers.append(handler)

    rec = parity.install(_Bus(), path=str(tmp_path / "n2.jsonl"))
    handler = handlers[0]
    for name, payload in ((parity.TICK_EVENT, _tick(9950)),
                          (parity.ROOM_EVENT, _room(9950)),
                          (parity.APPROVED_EVENT, _approved(9950, approved=False))):
        token = current_event.set(name)
        try:
            handler(payload)
        finally:
            current_event.reset(token)
    assert rec.observed == 3
    assert rec.rooms_joined == 1


def test_the_handler_ignores_an_event_with_no_context_name(tmp_path):
    """وبلا اسمٍ في السياق لا يُسجَّل شيء — لا يُخترع اسمٌ ولا تُبتلع حمولة."""
    handlers: list = []

    class _Bus:
        def subscribe(self, event_name, handler, **k):
            handlers.append(handler)

    rec = parity.install(_Bus(), path=str(tmp_path / "n3.jsonl"))
    handlers[0](_tick(9951))                       # بلا `current_event`
    assert rec.observed == 0


def test_three_rooms_for_one_symbol_in_one_second_all_survive(tmp_path):
    """⛔ جوهر الختم: A و B و C لرمزٍ واحدٍ داخل الثانية — الثلاثة يبقون.

    الدمج البارد `latest(name, symbol)` كان يُبقي الأحدث وحده. والقناة
    المسمّاة تحتفظ بكلٍّ بهويّته، ولمّا كانت الغرفة بلا `cycle_id` فهويّتها
    `trace_id` — وهو ما قِيس حيًّا: `cycle_id = 0` من `265` غرفة.
    """
    rec = parity.ParityRecorder(str(tmp_path / "three.jsonl"), grace_s=0.0)
    for seq, signal, conf in ((9960, "up", 10.0), (9961, "down", 20.0),
                              (9962, "up", 30.0)):
        rec.observe(parity.ROOM_EVENT, _room(seq, signal=signal,
                                             confidence=conf))
        rec.observe(parity.APPROVED_EVENT, _approved(seq, approved=False))
    rec.close()
    rows = parity.load(str(tmp_path / "three.jsonl"))
    assert len(rows) == 3
    assert [rows[_cycle_id(s)]["confidence"] for s in (9960, 9961, 9962)] \
        == [10.0, 20.0, 30.0], "دُمجت الغرف فبقي الأحدث وحده"
    assert [rows[_cycle_id(s)]["signal"] for s in (9960, 9961, 9962)] \
        == ["up", "down", "up"]
    cov = parity.coverage(rows)
    assert cov["decision_room_coverage"] == 1.0
    assert cov["blind_decision_cycles"] == 0


def test_an_approval_that_never_reaches_the_gate_is_not_sent_not_incomplete(tmp_path):
    """⛔ `no-send` مصيرٌ في سلسلة المالك، لا نقصٌ في القراءة.

    المقيس ٢٠٢٦-٠٩-١٨ على ٢٩٣ دورةً بلغت البوّابة: **أقصى ١٫٥٠٦ ث**
    والنافذة ٨ ث. فما لم يبلغها في النافذة لم يبلغها قطّ — وكان يُوسَم
    `incomplete`: ٣١٧ دورةً من ١٬١٩٧.
    """
    import time as _time
    rec = parity.ParityRecorder(str(tmp_path / "ns.jsonl"),
                                close_after_s=0.01, grace_s=0.0)
    rec.observe(parity.ROOM_EVENT, _room(9970))
    rec.observe(parity.APPROVED_EVENT, _approved(9970, approved=True))
    _time.sleep(0.02)
    rec._sweep(_time.time())
    assert rec.flush() == 1
    row = parity.load(str(tmp_path / "ns.jsonl"))[_cycle_id(9970)]
    assert row["fate"] == "not_sent"
    assert row.get("incomplete") is None, "مصيرٌ تامٌّ وُصف نقصًا"
    assert row["approved"] is True
    assert row["signal"] == "up"


def test_a_cycle_with_no_approval_at_all_stays_incomplete(tmp_path):
    """والتصنيف لا يُذيب النقص الحقيقيّ: بلا موافقةٍ يبقى ناقصًا معلَنًا."""
    import time as _time
    rec = parity.ParityRecorder(str(tmp_path / "ns2.jsonl"),
                                close_after_s=0.01, grace_s=0.0)
    rec.observe(parity.DISPATCH_EVENT, _dispatch(9971))
    _time.sleep(0.02)
    rec._sweep(_time.time())
    rec.flush()
    row = parity.load(str(tmp_path / "ns2.jsonl"))[_cycle_id(9971)]
    assert row["incomplete"] is True
    assert row["fate"] is None


def test_one_mailbox_preserves_order_between_room_and_approval(tmp_path):
    """⛔ ستّ معالجاتٍ = ستّة صناديق = ترتيبٌ غير مضمون بين نوعَي الحدث.

    الناقل يودع بـ`_enqueue(id(handler), …)`، فالمعالج هو الصندوق. ومعالجٌ
    واحدٌ مسجَّلٌ تحت ستّة أسماء يجعلها صندوقًا واحدًا — وهو شرط المالك
    «مع الحفاظ على ترتيب الأحداث». المقيس قبله: أربع دورات عمياء من ١٬٠٩٦.
    """
    handlers: list = []

    class _Bus:
        def subscribe(self, event_name, handler, **k):
            handlers.append(handler)

    rec = parity.install(_Bus(), path=str(tmp_path / "one.jsonl"))
    assert len(handlers) == len(parity.WATCHED)
    assert len({id(h) for h in handlers}) == 1, "صناديق متعدّدة"
    assert "صندوقٌ واحد" in rec.channel


# ── §5 / أمانة الشريط: فقدُ مدخلٍ = فشلُ تكافؤ ───────────────────────────

def test_the_tape_index_is_contiguous_under_concurrent_flush(tmp_path):
    """⛔ وُلد من فجوةٍ حقيقيّة: 27,406 واقعة ضاعت بلا خطأٍ مسجَّل.

    `observe` كان يُلحِق بالشريط **خارج** القفل و`flush` يبدّل المرجع تحته:
    فتقرأ الحلقةُ القائمةَ القديمة، ويكتبها التصريف، ثمّ تُلحِق بها بعد
    كتابتها. الحارس يشغّل الاثنين معًا ويطالب باتّصال رقم الوصول.
    """
    import threading as _th

    tape = tmp_path / "race.jsonl"
    rec = parity.ParityRecorder(str(tmp_path / "r.jsonl"), grace_s=0.0,
                                tape_path=str(tape))
    total = 4000
    stop = _th.Event()

    def _flusher():
        while not stop.is_set():
            rec.flush()

    t = _th.Thread(target=_flusher, daemon=True)
    t.start()
    for seq in range(total):
        rec.observe(parity.ROOM_EVENT, _room(seq))
    stop.set()
    t.join(timeout=5)
    rec.flush()

    seen = [json.loads(ln)["i"]
            for ln in tape.read_text(encoding="utf-8").splitlines() if ln]
    assert rec.tape_write_failures == 0
    assert len(seen) == total, "ضاعت %d واقعة" % (total - len(seen))
    assert seen == sorted(seen), "اختلّ ترتيب الوصول"
    assert seen == list(range(total)), "فجوةٌ في رقم الوصول"


def test_a_failed_tape_write_returns_the_ledger_and_is_counted(tmp_path):
    """تعثّرُ القرص لا يُفقد واقعة: الدفتر يعود إلى رأس الطابور بترتيبه."""
    rec = parity.ParityRecorder(str(tmp_path / "r2.jsonl"), grace_s=0.0,
                                tape_path=str(tmp_path / "sub" / "t.jsonl"))
    for seq in (100, 101, 102):
        rec.observe(parity.ROOM_EVENT, _room(seq))
    original = os.makedirs

    def _boom(*a, **k):
        raise OSError("قرصٌ متعثّر")

    os.makedirs = _boom
    try:
        with pytest.raises(OSError):
            rec.flush()
    finally:
        os.makedirs = original
    assert rec.tape_write_failures == 1
    assert len(rec._tape) == 3, "الدفتر لم يعد"
    assert [row[0] for row in rec._tape] == [0, 1, 2], "عاد بترتيبٍ مقلوب"
    rec.flush()
    seen = [json.loads(ln)["i"] for ln in
            (tmp_path / "sub" / "t.jsonl").read_text(encoding="utf-8").splitlines() if ln]
    assert seen == [0, 1, 2]


def test_the_tape_append_happens_under_the_lock(tmp_path):
    """⛔ حارسٌ **بنيويّ** لا احتماليّ: الحارس السابق شغّل خيطين وطالب
    باتّصال الرقم، فنجت طفرةُ «الإلحاق خارج القفل» — نافذة السباق أضيق من
    أن تُصاد بالتكرار. فيُفحَص العقد نفسه: هل القفل مملوكٌ لحظة الإلحاق؟
    """
    rec = parity.ParityRecorder(str(tmp_path / "r3.jsonl"), grace_s=0.0,
                                tape_path=str(tmp_path / "t3.jsonl"))

    class _Watched:
        def __init__(self, inner):
            self._inner = inner
            self.depth = 0

        def __enter__(self):
            self._inner.acquire()
            self.depth += 1
            return self

        def __exit__(self, *exc):
            self.depth -= 1
            self._inner.release()
            return False

        acquire = property(lambda self: self._inner.acquire)
        release = property(lambda self: self._inner.release)

    watched = _Watched(rec._lock)
    rec._lock = watched

    naked: list = []

    class _Guarded(list):
        def append(self, item):
            if watched.depth <= 0:
                naked.append(item)
            list.append(self, item)

    rec._tape = _Guarded()
    rec.observe(parity.ROOM_EVENT, _room(4242))
    assert rec.taped == 1
    assert not naked, "أُلحِقت واقعةٌ بالشريط والقفل غير مملوك"
