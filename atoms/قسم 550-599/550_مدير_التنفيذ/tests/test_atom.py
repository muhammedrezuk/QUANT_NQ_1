"""٥٥٠ مدير التنفيذ — دورة حياة صادقة، وسجلٌّ لا ينمو بلا حدّ.

**حكم المالك ٢٠٢٦-٠٩-١٠:** «نفّذ التقليم على 550 الآن… لكن التنفيذ ليس
احذف orders».

## ⛔ العطب المقيس على النواة الحيّة

    orders = 5,557 أمرًا  ⟵  نشرة 1.77 م.ب  ⟵  38.83 م.ث لكلّ نشرة
    (بناء 1.85 · تجميد 20.67 · ترميز بثّ 16.31)
    × 1.15 نشرة/ث  =  **4.5% من زمن حلقة النواة** في ذرّةٍ واحدة

ونموّه مقيس: **0.57 أمر/ث** ⟵ 20.1% من الحلقة عند 25,000 أمر، و80.4%
عند 100,000. نموٌّ غير محدود داخل المسار الساخن.

## والحارس ثلاثة شروط لا شرطٌ واحد

    مرحلة نهائيّة  ≠  التزام استعادة  ≠  انتقال طائر

فـ`FILLED_OPEN` مركزٌ مفتوح، و`QUEUED_TO_BRIDGE` أمرٌ في الطريق: كلاهما
رتبةٌ لا تُقلَّم مهما طال الزمن.

## ومعيار النجاح الذي فرضه المالك

    السلوك قبل/بعد = مطابق · الاستعادة = PASS · تقدّم المرحلة = PASS
    لا تراجع مرحلة = PASS · لا أمر ضائع = PASS

ولهذا لا يكفي أن يصغر الحِمل: كلّ بندٍ منها حارسٌ مستقلٌّ أدناه، وأقواها
`test_pruning_changes_nothing_that_anyone_can_observe` — يُمرّر السلسلة
نفسها على ذرّةٍ تُقلّم وأخرى لا تُقلّم أبدًا، ثمّ يقارن كلّ ما يُرى.
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
from pathlib import Path as _Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom550", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom550"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom

KEY_SEP = "\x1f"
ACC = "52992818"


class _Logger:
    def __getattr__(self, name):  # noqa: ANN001
        return lambda *a, **k: None


class _Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def subscribe(self, *_args) -> None:  # noqa: ANN002
        return None

    async def publish(self, name: str, payload: dict) -> None:
        self.events.append((name, payload))


class _Clock:
    """ساعةٌ تُقاد ولا تُنتظر."""

    def __init__(self, start: float = 10_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def _make(clock: _Clock | None = None) -> tuple[Atom, _Bus, _Clock]:
    bus, atom = _Bus(), Atom()
    clock = clock or _Clock()
    atom._clock = clock
    atom._last_prune = clock() - _mod._PRUNE_EVERY_S
    await atom.initialize(AtomContext(550, {}, _Logger(), bus.publish, bus.subscribe))
    await atom.start()
    return atom, bus, clock


def _order(request_id: str, **extra) -> dict:  # noqa: ANN003
    return {"account_id": ACC, "request_id": request_id, "symbol": "USTEC",
            "side": "BUY", "volume": 1.0, **extra}


def _key(request_id: str) -> str:
    return ACC + KEY_SEP + request_id


def _nodes(value) -> int:  # noqa: ANN001
    """عدد عقد الحاويات — هو ما يدفعه التجميد، لا عدد المفاتيح."""
    if isinstance(value, dict):
        return 1 + sum(_nodes(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return 1 + sum(_nodes(v) for v in value)
    return 0


async def _full_lifecycle(atom: Atom, request_id: str) -> None:
    payload = _order(request_id)
    await atom._on_final(payload)
    await atom._on_bridge_written(payload)
    await atom._on_ack(payload)
    await atom._on_trade({**payload, "event_type": "OPENED"})
    await atom._on_trade({**payload, "event_type": "CLOSED"})


# ══ العقد نفسه ═════════════════════════════════════════════════════════════

def test_the_stage_classification_is_a_complete_partition() -> None:
    """⛔ الحارس الذي يمنع الانزلاق الصامت.

    مرحلةٌ تُضاف غدًا ولا تُصنَّف ستقع افتراضًا في جانبٍ ما. فالتصنيف
    قِسمةٌ كاملة تُفحص عند الاستيراد، لا قائمةَ استثناء.
    """
    _mod._assert_stage_partition()
    assert _mod._TERMINAL_STAGES | _mod._LIVE_STAGES == set(_mod._STAGE_RANK)
    assert not (_mod._TERMINAL_STAGES & _mod._LIVE_STAGES)


def test_an_open_position_is_classified_live_not_terminal() -> None:
    """§ التزام الاستعادة: تذكرةٌ مفتوحة عند الوسيط تحتاج معرفتَها بعد الإقلاع."""
    for stage in (_mod.STAGE_FILLED_OPEN, _mod.STAGE_FILLED_PARTIAL):
        assert stage in _mod._LIVE_STAGES, stage
        assert stage not in _mod._TERMINAL_STAGES, stage


def test_an_order_in_flight_is_classified_live_not_terminal() -> None:
    """§ الانتقال الطائر: أمرٌ في الطريق مصيره لم يُعرف بعد."""
    for stage in (_mod.STAGE_BUILT, _mod.STAGE_FINALIZED,
                  _mod.STAGE_QUEUED, _mod.STAGE_ACK):
        assert stage in _mod._LIVE_STAGES, stage


def test_the_two_windows_are_ordered_and_long_enough() -> None:
    assert _mod._RETENTION_S > 0 and _mod._TOMBSTONE_S > _mod._RETENTION_S
    assert _mod._RETENTION_S + _mod._TOMBSTONE_S >= 1200.0, (
        "نافذة الحماية الكلّيّة أقصر من عشرين دقيقة")


# ══ ما لا يُقلَّم أبدًا ══════════════════════════════════════════════════════

async def test_a_live_order_is_never_pruned_however_long_it_waits() -> None:
    atom, _bus, clock = await _make()
    await atom._on_ack(_order("live-1"))
    clock.advance(_mod._RETENTION_S + _mod._TOMBSTONE_S + 10_000.0)
    await atom._on_ack(_order("live-2"))
    assert _key("live-1") in atom._orders, "أمرٌ طائر قُلِّم"
    assert atom._orders[_key("live-1")]["stage"] == _mod.STAGE_ACK


async def test_an_open_position_is_never_pruned() -> None:
    """المركز المفتوح التزام استعادة — لا يخرج مهما طال."""
    atom, _bus, clock = await _make()
    await atom._on_trade({**_order("open-1"), "event_type": "OPENED"})
    await atom._on_trade({**_order("part-1"), "event_type": "PARTIAL"})
    clock.advance(_mod._RETENTION_S * 100)
    await atom._on_ack(_order("tick"))
    assert atom._orders[_key("open-1")]["stage"] == _mod.STAGE_FILLED_OPEN
    assert atom._orders[_key("part-1")]["stage"] == _mod.STAGE_FILLED_PARTIAL


# ══ النافذتان ══════════════════════════════════════════════════════════════

async def test_a_terminal_order_keeps_its_detail_inside_the_window() -> None:
    atom, _bus, clock = await _make()
    await _full_lifecycle(atom, "done-1")
    clock.advance(_mod._RETENTION_S - 1.0)
    await atom._on_ack(_order("tick"))
    assert _key("done-1") in atom._orders, "التفصيل أُزيل قبل نافذة الأمان"
    assert atom._pruned == 0


async def test_the_detail_leaves_after_the_window_and_the_trace_stays() -> None:
    atom, _bus, clock = await _make()
    await _full_lifecycle(atom, "done-1")
    clock.advance(_mod._RETENTION_S + 1.0)
    await atom._on_ack(_order("tick"))
    assert _key("done-1") not in atom._orders, "التفصيل بقي بعد النافذة"
    assert atom._retired[_key("done-1")] == _mod._STAGE_RANK[_mod.STAGE_FILLED_CLOSED]
    assert atom._pruned == 1


async def test_the_trace_is_forgotten_after_the_second_window() -> None:
    atom, _bus, clock = await _make()
    await _full_lifecycle(atom, "done-1")
    clock.advance(_mod._RETENTION_S + 1.0)
    await atom._on_ack(_order("tick"))
    clock.advance(_mod._TOMBSTONE_S + 1.0)
    await atom._on_ack(_order("tick2"))
    assert _key("done-1") not in atom._retired
    assert atom._forgotten == 1


async def test_pruning_runs_at_most_once_per_second() -> None:
    """التقليم مسحٌ على السجلّ — لا يُدفع مع كلّ حدث على المسار الساخن."""
    atom, _bus, clock = await _make()
    await _full_lifecycle(atom, "done-1")
    clock.advance(_mod._RETENTION_S + 1.0)
    stamp = atom._last_prune
    await atom._on_ack(_order("a"))
    assert atom._last_prune != stamp
    stamp = atom._last_prune
    clock.advance(_mod._PRUNE_EVERY_S / 2)
    await atom._on_ack(_order("b"))
    assert atom._last_prune == stamp, "التقليم تكرّر داخل الثانية نفسها"


# ══ لا تراجع مرحلة — الحارس الأهمّ ══════════════════════════════════════════

async def test_a_late_lower_stage_is_refused_after_the_detail_is_gone() -> None:
    """⛔ هذا هو الخطر الحقيقيّ للحذف.

    لو أُزيل السجلّ بلا أثر لعاد الحدث المتأخّر ينشئه من جديد **برتبةٍ
    أدنى** — تراجعُ مرحلةٍ صامت. الأثر يمنعه.
    """
    atom, _bus, clock = await _make()
    await _full_lifecycle(atom, "done-1")
    clock.advance(_mod._RETENTION_S + 1.0)
    await atom._on_ack(_order("tick"))
    assert _key("done-1") not in atom._orders

    await atom._on_final(_order("done-1"))        # رتبة 2 بعد رتبة 6
    assert _key("done-1") not in atom._orders, "تراجعت المرحلة بعد التقليم"
    assert atom._retired[_key("done-1")] == 6
    assert atom._regression_blocked >= 1


async def test_the_refusal_matches_the_one_the_record_used_to_give() -> None:
    """السلوك مطابق: الرفض نفسه يقع والسجلّ حاضر."""
    atom, _bus, _clock = await _make()
    await _full_lifecycle(atom, "done-1")
    await atom._on_final(_order("done-1"))
    assert atom._orders[_key("done-1")]["stage"] == _mod.STAGE_FILLED_CLOSED


async def test_an_equal_or_higher_stage_still_passes_after_pruning() -> None:
    """`>=` عقدٌ قائم: انتقالٌ بين رتبتين متساويتين كان يمرّ ويبقى يمرّ."""
    atom, _bus, clock = await _make()
    await atom._on_trade({**_order("t-1"), "event_type": "CLOSED"})
    clock.advance(_mod._RETENTION_S + 1.0)
    await atom._on_ack(_order("tick"))
    assert _key("t-1") not in atom._orders

    await atom._on_trade({**_order("t-1"), "event_type": "OPENED"})
    assert atom._orders[_key("t-1")]["stage"] == _mod.STAGE_FILLED_OPEN
    assert atom._resurrected == 1
    assert _key("t-1") not in atom._retired, "الأثر بقي بعد بعث السجلّ"


async def test_a_resurrected_live_order_is_not_pruned_again() -> None:
    atom, _bus, clock = await _make()
    await atom._on_trade({**_order("t-1"), "event_type": "CLOSED"})
    clock.advance(_mod._RETENTION_S + 1.0)
    await atom._on_ack(_order("tick"))
    await atom._on_trade({**_order("t-1"), "event_type": "OPENED"})
    clock.advance(_mod._RETENTION_S * 10)
    await atom._on_ack(_order("tick2"))
    assert atom._orders[_key("t-1")]["stage"] == _mod.STAGE_FILLED_OPEN


# ══ السلوك قبل/بعد = مطابق ═════════════════════════════════════════════════

async def test_pruning_changes_nothing_that_anyone_can_observe() -> None:
    """⛔ معيار المالك الأوّل — يُقاس بالمقارنة لا بالوعد.

    السلسلة نفسها تُمرَّر على ذرّةٍ تُقلّم وأخرى نافذتها لا تنتهي، ثمّ
    يُقارن كلّ ما يخرج من الذرّة: العدّادات، والأسباب، والإيقاف، وآخر
    نتيجة، و**المرحلة النهائيّة لكلّ أمر** — سواء بقي تفصيلها أم صار أثرًا.
    """
    async def run(retention: float) -> tuple[dict, dict]:
        clock = _Clock()
        atom, _bus, _c = await _make(clock)
        original = _mod._RETENTION_S
        _mod._RETENTION_S = retention
        try:
            for index in range(40):
                request = "r%d" % index
                await atom._on_final(_order(request))
                await atom._on_bridge_written(_order(request))
                if index % 4 == 0:
                    await atom._on_rejected(_order(request, reason="disabled"))
                elif index % 4 == 1:
                    await atom._on_ack(_order(request))
                    await atom._on_trade({**_order(request), "event_type": "OPENED"})
                elif index % 4 == 2:
                    await atom._on_ack(_order(request))
                    await atom._on_trade({**_order(request), "event_type": "CLOSED"})
                else:
                    await atom._on_skipped(_order(request, reason="NO_SIZE_YET"))
                # 40 × 20 ث = 800 ث — كلّها داخل نافذة الحماية (1200 ث)،
                # فالمقارنة تقع على ما يُفترض حفظه لا على النسيان المقصود.
                clock.advance(20.0)
                # أحداثٌ متأخّرة برتبةٍ أدنى — الفخّ الذي يكشف التراجع
                if index >= 4:
                    await atom._on_final(_order("r%d" % (index - 4)))
            await atom._on_outcome({"account_id": ACC, "symbol": "USTEC",
                                    "profit": 12.5, "result": "WIN"})
            await atom._on_halt({"account_id": ACC, "reason": "OWNER"})
        finally:
            _mod._RETENTION_S = original
        observable = {
            "counts": dict(atom._counts),
            "counts_by_account": {a: dict(v) for a, v in atom._counts_by_account.items()},
            "halted_accounts": dict(atom._halted_accounts),
            "reject_reasons": dict(atom._reject_reasons),
            "skip_reasons": dict(atom._skip_reasons),
            "last_outcome_by_account": {a: dict(v) for a, v
                                        in atom._last_outcome_by_account.items()},
        }
        ranks = {key: _mod._STAGE_RANK.get(str(record.get("stage")), 0)
                 for key, record in atom._orders.items()}
        ranks.update(atom._retired)
        return observable, ranks

    pruning, pruning_ranks = await run(300.0)
    never, never_ranks = await run(10.0 ** 9)

    assert pruning == never, "التقليم غيّر ما يُرى"
    assert pruning_ranks == never_ranks, "مرحلةٌ نهائيّة اختلفت بين الحالتين"


async def test_no_order_is_lost_from_the_counts() -> None:
    """«لا أمر ضائع»: العدّ لا يمسّه التقليم إطلاقًا — هو خارج `_orders`."""
    atom, _bus, clock = await _make()
    for index in range(60):
        await _full_lifecycle(atom, "r%d" % index)
        clock.advance(20.0)
    assert atom._counts["decision_finalized"] == 60
    assert atom._counts["queued_to_bridge"] == 60
    assert atom._counts["broker_acknowledged"] == 60
    assert atom._counts["filled_open"] == 60
    assert atom._counts["filled_closed"] == 60
    assert atom._counts_by_account[ACC]["filled_closed"] == 60


async def test_the_dashboard_contract_fields_survive_untouched() -> None:
    """المستهلك الوحيد يقرأ هذه الحقول — قِيست في `store.ts:335`."""
    atom, _bus, clock = await _make()
    await atom._on_rejected(_order("r1", reason="disabled"))
    await atom._on_skipped(_order("s1", reason="NO_SIZE_YET"))
    await atom._on_outcome({"account_id": ACC, "symbol": "USTEC", "profit": 3.0})
    await atom._on_halt({"account_id": ACC, "reason": "OWNER"})
    clock.advance(_mod._RETENTION_S + _mod._TOMBSTONE_S + 10.0)
    await atom._on_ack(_order("tick"))

    state = atom._state()
    for field in ("counts", "counts_by_account", "halted_accounts",
                  "reject_reasons", "skip_reasons", "last_outcome_by_account"):
        assert field in state, field
    assert state["reject_reasons"] == {"disabled": 1}
    assert state["skip_reasons"] == {"NO_SIZE_YET": 1}
    assert state["halted_accounts"] == {ACC: "OWNER"}
    assert state["last_outcome_by_account"][ACC]["profit"] == 3.0


# ══ لا نموّ مستمرّ ═══════════════════════════════════════════════════════════

async def test_the_order_book_stops_growing_under_a_steady_stream() -> None:
    """⛔ معيار النجاح الأوّل: `orders size → لا نمو مستمر`.

    ألف أمرٍ كاملة الدورة بإيقاعٍ أسرع من الحيّ. قبل التقليم كان السجلّ
    يبلغ ألفًا؛ وبعده يستقرّ عند ما تسعه نافذة الأمان وحدها.
    """
    atom, _bus, clock = await _make()
    marks = []
    for index in range(1000):
        await _full_lifecycle(atom, "r%d" % index)
        clock.advance(1.0)
        # النافذة تمتلئ أوّلًا (300 ث)؛ ما قبلها تعبئةٌ لا نموّ.
        if index > _mod._RETENTION_S + 50 and index % 150 == 0:
            marks.append(len(atom._orders))

    assert len(atom._orders) <= _mod._RETENTION_S + 5, (
        "السجلّ ما زال ينمو: %d" % len(atom._orders))
    assert len(marks) >= 3, "لم تُؤخذ قياساتٌ كافية بعد امتلاء النافذة"
    assert max(marks) - min(marks) <= 5, "الحجم لم يستقرّ: %s" % marks
    assert len(atom._retired) <= _mod._TOMBSTONE_S + 5


async def test_the_published_payload_collapses() -> None:
    """الكلفة تُدفع بعدد عقد الحاويات — والقياس عليها لا على عدد المفاتيح."""
    atom, _bus, clock = await _make()
    for index in range(600):
        await _full_lifecycle(atom, "r%d" % index)
        clock.advance(1.0)

    state = atom._state()
    orders_nodes = _nodes(state["orders"])
    trace_nodes = _nodes(state["retired_stages"])
    assert orders_nodes < 600, "سجلّ الأوامر ما زال يحمل عقدةً لكلّ أمر"
    assert trace_nodes == 1, (
        "الأثر ليس مسطّحًا — صار عقدةً لكلّ سجلّ بدل عقدةٍ واحدة")


# ══ الاستعادة ══════════════════════════════════════════════════════════════

async def test_restore_keeps_every_live_order_in_full() -> None:
    """الاستعادة تحتاج الطائر والمفتوح — وهما وحدهما ما يبقى كاملًا."""
    atom, _bus, clock = await _make()
    await atom._on_ack(_order("flying"))
    await atom._on_trade({**_order("open"), "event_type": "OPENED"})
    await _full_lifecycle(atom, "closed")
    snapshot = await atom.snapshot()

    fresh = Atom()
    fresh._clock = _Clock(clock() + 5.0)
    await fresh.restore(snapshot)
    assert fresh._orders[_key("flying")]["stage"] == _mod.STAGE_ACK
    assert fresh._orders[_key("open")]["stage"] == _mod.STAGE_FILLED_OPEN


async def test_restore_drains_a_terminal_backlog_on_the_first_prune() -> None:
    """الركام الموروث (5,557 سجلًّا حيًّا) يُصرَّف فور الإقلاع لا بعد النافذة."""
    atom, _bus, _clock = await _make()
    for index in range(50):
        await _full_lifecycle(atom, "r%d" % index)
    snapshot = await atom.snapshot()
    assert len(snapshot["orders"]) == 50

    fresh, bus, _c = await _make(_Clock(50_000.0))
    await fresh.restore(snapshot)
    assert len(fresh._orders) == 50, "الاستعادة نفسها حذفت — والتقليم وظيفة التقليم"
    await fresh._on_ack(_order("tick"))
    assert len(fresh._orders) == 1, "الركام الموروث لم يُصرَّف"
    assert len(fresh._retired) == 50, "صُرِف الركام بلا أثر يحرسه"


async def test_restore_reinstates_the_regression_guard() -> None:
    """⛔ الأثر يعبر الإقلاع — وإلّا عاد التراجع ممكنًا بعد كلّ إعادة تشغيل."""
    atom, _bus, clock = await _make()
    await _full_lifecycle(atom, "done")
    clock.advance(_mod._RETENTION_S + 1.0)
    await atom._on_ack(_order("tick"))
    snapshot = await atom.snapshot()
    assert snapshot["retired_stages"][_key("done")] == 6

    fresh, _bus2, _c = await _make(_Clock(90_000.0))
    await fresh.restore(snapshot)
    await fresh._on_final(_order("done"))
    assert _key("done") not in fresh._orders, "تراجعت المرحلة بعد الاستعادة"
    assert fresh._regression_blocked == 1


async def test_restore_survives_a_state_written_before_the_trace_existed() -> None:
    """حالةٌ من إصدارٍ سابق لا تحمل `retired_stages` — لا تُسقط الاستعادة."""
    legacy = {"counts": {key: 0 for key in _mod._COUNT_KEYS},
              "counts_by_account": {}, "orders": {}, "halted_accounts": {},
              "last_outcome_by_account": {}}
    fresh = Atom()
    fresh._clock = _Clock()
    await fresh.restore(legacy)
    assert fresh._retired == {}
    assert fresh._restore_error == ""


async def test_a_broken_state_still_fails_closed() -> None:
    atom, _bus, _clock = await _make()
    await atom._rehydrate({"counts": "ليست قاموسًا"})
    assert atom._restore_error == "RESTORE_FAILED_FAIL_CLOSED"


async def test_rehydrate_runs_once_and_the_atom_never_loops_in_its_own_output() -> None:
    """عقد التحميل الساخن: الذرّة تشترك بمخرَجها — فلا بدّ من حارس دورة.

    الترميم يدهس الحالة عمدًا: هو أوّل `execution.unified.state` تراه عند
    الإقلاع، أي حالتها هي قبل السقوط. والمحروس أنّه يقع **مرّةً واحدة**؛
    فنشرتها التالية تعود إليها ولا تدهس ما بنته بعد الإقلاع.
    """
    atom, _bus, _clock = await _make()
    empty = {"counts": {key: 0 for key in _mod._COUNT_KEYS},
             "counts_by_account": {}, "orders": {}, "halted_accounts": {},
             "last_outcome_by_account": {}}
    await atom._rehydrate({**empty, "orders": {
        _key("was_flying"): {"stage": _mod.STAGE_ACK, "account_id": ACC}}})
    assert atom._orders[_key("was_flying")]["stage"] == _mod.STAGE_ACK
    assert atom._rehydrated is True

    await atom._on_ack(_order("after_boot"))
    await atom._rehydrate(empty)          # نشرتها هي، عائدةً إليها
    assert _key("after_boot") in atom._orders, "الذرّة دارت في مخرَجها ودهست نفسها"


# ══ الدورة الأصليّة — لا تسقط بندًا كان محروسًا ══════════════════════════════

async def test_the_lifecycle_still_walks_forward_stage_by_stage() -> None:
    atom, _bus, _clock = await _make()
    payload = _order("r")
    await atom._on_final(payload)
    assert atom._orders[_key("r")]["stage"] == _mod.STAGE_FINALIZED
    assert "sent" not in atom._counts
    await atom._on_bridge_written(payload)
    assert atom._orders[_key("r")]["stage"] == _mod.STAGE_QUEUED
    await atom._on_ack(payload)
    assert atom._orders[_key("r")]["stage"] == _mod.STAGE_ACK
    await atom._on_trade({**payload, "event_type": "OPENED"})
    assert atom._orders[_key("r")]["stage"] == _mod.STAGE_FILLED_OPEN
    await atom._on_halt({"account_id": ACC, "reason": "RISK"})
    assert atom._halted_accounts == {ACC: "RISK"}

    snapshot = await atom.snapshot()
    fresh = Atom()
    fresh._clock = _Clock()
    await fresh.restore(snapshot)
    assert fresh._counts["decision_finalized"] == 1


async def test_skip_and_reject_reasons_are_broken_down_and_survive() -> None:
    """٥٥١ (`order.skipped`) و٥٥٢ (`order.rejected`) تُعدّان بأسبابهما."""
    atom, _bus, _clock = await _make()
    await atom._on_skipped(_order("s1", reason="NO_SIZE_YET"))
    await atom._on_rejected(_order("r1", reason="disabled"))
    assert atom._counts["order_skipped"] == 1 and atom._counts["rejected"] == 1
    assert atom._skip_reasons == {"NO_SIZE_YET": 1}
    assert atom._reject_reasons == {"disabled": 1}

    snapshot = await atom.snapshot()
    fresh = Atom()
    fresh._clock = _Clock()
    await fresh.restore(snapshot)
    assert fresh._skip_reasons == {"NO_SIZE_YET": 1}
    assert fresh._reject_reasons == {"disabled": 1}


async def test_an_event_without_identity_is_counted_not_swallowed() -> None:
    atom, _bus, _clock = await _make()
    await atom._on_ack({"symbol": "USTEC"})
    assert atom._identity_dropped == 1
    health = await atom.health_check()
    assert health.state is HealthState.DEGRADED


async def test_health_declares_the_pruning() -> None:
    """تقليمٌ لا يُرى لا يُصدَّق."""
    atom, _bus, clock = await _make()
    await _full_lifecycle(atom, "done")
    clock.advance(_mod._RETENTION_S + 1.0)
    await atom._on_ack(_order("live"))
    details = (await atom.health_check()).details
    for field in ("live_orders", "awaiting_prune", "retired_stages", "pruned",
                  "forgotten", "regression_blocked", "resurrected"):
        assert field in details, field
    assert details["pruned"] == 1
    assert details["live_orders"] == 1
