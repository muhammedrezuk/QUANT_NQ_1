import sys
import time
from pathlib import Path

import pytest

from shared.learning_model import (FEATURE_NAMES, FEATURE_SCHEMA_VERSION,
                                   schema_hash)
from tests.learning_test_support import make_atom, manifest_config

# ٢٠٢٦-١٠-٠١ (v1.8.1): `atom.py` صار يستورد وحدتيه الشقيقتين باسمهما المجرّد. المُقلِع
# يضع مجلّد الذرّة على المسار أثناء تحميلها، و`load_atom` في عُدّة الاختبار المشتركة لا
# يضعه — فيضعه هذا الاختبار بنفسه كما يفعل اختبار ٥٥٢.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ─────────────────────────────────────────────────────────────────────────────
# حمولات هذا الملف مبنيّة من كود الناشرين الفعليّين، لا من المخيّلة.
#
# الاختبار السابق كان أخضر وهو يستدعي `_on_decision` بحمولة فيها
# `model_evidence` — حمولةٌ لا ينشرها أيّ ناشر في النظام. فبقي أخضر بينما
# الذرّة ميتة حيًّا: قِيس ٢٠٢٦-٠٩-٠٩ أنّ ٠ من ٢٩٩٬٤٦٤ قرارًا مخزّنًا حمل
# دليلًا. (نفس فخّ ٥٥٥.)
#
# لذلك تُبنى الحمولات هنا من عقد `shared.learning_model` نفسه الذي يستعمله
# ٣٦٧ و٣٦٢ — فأيّ تغيير في العقد يكسر هذا الملف بدل أن يمرّ صامتًا.
# ─────────────────────────────────────────────────────────────────────────────

ACCOUNT = "52992818"
BROKER = "Raw Trading Ltd"
SYMBOL = "BTCUSD"


def cycle(index: int) -> str:
    """صيغة `cycle_id` كما تظهر في المخزن الحيّ (decisions.db و لقطة ٣٦٠)."""
    return "%s|%s|%s|tick|%d" % (ACCOUNT, BROKER, SYMBOL, index)


def evidence_from_367(direction: str = "buy", version: str | None = None) -> dict:
    """حرفيًّا حقول `learning.model.evidence` كما ينشرها ٣٦٧.

    ملاحظة مقيسة: `model_version` يساوي None في وضع الظل (لا نموذج نشط)،
    والمتّجه يُنشر رغم ذلك — فالسلسلة تُقلع من الصفر بلا نموذج سابق.
    """
    probs = {"p_buy": 0.6, "p_sell": 0.3, "p_neutral": 0.1}
    return {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "timeframe": "tick", "cycle_id": cycle(1), "period_start": 1788959584.0,
        "model_version": version, "direction": direction, **probs,
        "confidence": 0.6, "mode": "shadow", "state": "NOT_READY",
        "influence_weight": 0.0,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_schema_hash": schema_hash(),
        "feature_names": list(FEATURE_NAMES),
        "feature_vector": [(i + 1) / 100.0 for i in range(len(FEATURE_NAMES))],
        "source": "learning_model",
        # ظرف النقل الذي تضيفه النواة قبل أن يصل الحدث — مقيس ٢٠٢٦-٠٩-١٠ من
        # لقطة ٣٦٠ الحيّة، و`unified` وحده ٥٨٠ بايت في كل سجل.
        "unified": {"symbol": SYMBOL, "bid": 4410.5, "ask": 4410.7,
                    "price": 4410.6, "volume": 12, "timeframe": "tick",
                    "timestamp": 1788959584.0, "provider": "CTRADER"},
        "event_id": "evt-367-1", "trace_id": "trace-1",
        "parent_event_id": "evt-parent-1", "parent_event": "market.tick.validated",
        "atom_id": 367, "section_id": "350",
    }


def evaluated_from_452(index: int, evidence: dict | None) -> dict:
    """حمولة `decision.evaluated.state` كما ينشرها ٤٥٢.

    ٤٥٢ لا ينشر `decision_id` — فقط `cycle_id`. وهو **الحدث الوحيد** الذي
    يحمل `model_evidence`. وقيم signal/score/confidence عنده None عمدًا.
    """
    return {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "timeframe": "tick", "cycle_id": cycle(index), "id": "452",
        "status": "ok", "cycle_status": "complete", "complete": True,
        "signal": None, "score": None, "confidence": None,
        "quality": "good", "warnings": [], "identity_missing": False,
        "evidence": [], "eligible_count": 1, "evidence_count": 1,
        "model_evidence": evidence,
        "metadata": {"min_confidence": 0.0},
    }


def scored_from_453(index: int, direction: str = "buy") -> dict:
    """حمولة `decision.scored.state` كما ينشرها ٤٥٣ — **بلا `model_evidence`**.

    هذا هو الإسقاط الذي قطع سلسلة التعلّم: ٤٥٣ يستهلك حمولة ٤٥٢ ولا يعيد
    نشر الدليل، و٣٦٠ كان يسمع هذه المرحلة وحدها.
    """
    return {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "timeframe": "tick", "cycle_id": cycle(index), "id": "453",
        "status": "ok", "cycle_status": "complete", "complete": True,
        "signal": direction, "direction": direction, "direction_value": 1,
        "score": 0.75, "confidence": 0.62, "participation": 0.5,
        "strength": 0.8, "quality": "good", "warnings": [],
        "evidence": [], "contributions": [],
        "metadata": {"directional_weight": 1.0},
    }


def resolved_from_458(index: int, direction: str = "buy") -> dict:
    """`decision.resolved.state` — يحمل `decision_id` بالبادئة، وبلا دليل."""
    payload = scored_from_453(index, direction)
    payload.update({"id": "458", "decision_id": "dec:" + cycle(index)})
    return payload


def outcome_from_563(index: int, profit: float, ticket: int = 7) -> dict:
    """`market.outcome.realized` — ٥٦٣ يعيد ربط `decision_id` من دفتره."""
    return {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "decision_id": "dec:" + cycle(index), "gate_request_id": None,
        "ticket": ticket, "event_id": "evt-%d" % ticket, "profit": profit,
        "timestamp": 1788959600.0, "reason": "CLOSED",
    }


def assert_evidence_contract(module, record, evidence, note=""):
    """الدليل يُحفَظ بعقده كاملًا، وظرف النقل لا يُخزَّن.

    v1.4.0: `model_evidence` كان يُحفظ بحمولته كما وصلت — وفيها `unified`
    (نسخة كاملة من التِكّة، ٥٨٠ بايت) و`trace_id`/`parent_event` وغيرها،
    وهي ظرف تضيفه النواة ولا يقرأه مستهلك واحد. مقيس: `model_evidence`
    كان ٨٥٫٧٪ من لقطة ٣٣٫٥٨ م.ب.
    """
    kept = record["model_evidence"]
    for name in ("feature_vector", "feature_names",
                 "feature_schema_version", "feature_schema_hash"):
        assert kept.get(name) == evidence[name], (note or "") + " :" + name
    assert kept.get("direction") == evidence["direction"]
    assert set(kept) <= set(module._EVIDENCE_KEEP), "ظرف النقل تسرّب إلى المخزَّن"
    for envelope in ("unified", "trace_id", "parent_event", "event_id",
                     "p_buy", "mode", "state"):
        assert envelope not in kept, "حقل ظرف بقي مخزَّنًا: " + envelope


async def collector(**overrides):
    config = manifest_config(360)
    config.update(overrides)
    return await make_atom(360, config)


# ── فكّ الأقسام عن القرار (٢٠٢٦-١٠-٠٧، ختم «NQ») ─────────────────────────────

@pytest.mark.asyncio
async def test_no_subscription_to_archived_decision_stages():
    """ناشرو المراحل الثلاث أُرشفوا — فلا اشتراك فيها، والنتائج والتأكيد باقية."""
    _module, _atom, bus = await collector()
    for dropped in ("decision.evaluated.state", "decision.scored.state",
                    "decision.resolved.state"):
        assert dropped not in bus.handlers, dropped
    for kept in ("trading.final_decision", "market.outcome.realized",
                 "execution.command.ack", "execution.manage.intent",
                 "market.tick.validated"):
        assert kept in bus.handlers, kept


# ── الوصلة المقطوعة ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evidence_arrives_on_evaluated_stage():
    """٣٦٠ يلتقط الدليل من المرحلة الوحيدة التي تحمله.

    ولماذا تمرّ السلسلة كاملة هنا: ٤٥٢ ينشر `cycle_id` عاريًا ولا ينشر
    `decision_id`، بينما ٥٦٣ يعيد ربط `dec:`+نفسه على النتيجة. الجسر بين
    الصيغتين هو مرحلة تحمل الاثنين — `decision.resolved.state` (٤٥٨) وهي
    ٩٩٫٩٪ ممّا يصل مقيسًا، أو `trading.final_decision`. القفز فوقها في
    اختبار سابق أعطى فشلًا كاذبًا؛ الواقع أنّها تصل دائمًا.
    """
    module, atom, bus = await collector()
    evidence = evidence_from_367()
    await atom._on_evaluated(evaluated_from_452(1, evidence))
    await atom._on_decision(resolved_from_458(1))
    await atom._on_outcome(outcome_from_563(1, profit=10.0))

    record = bus.payloads(module.EVENT_OUT)[-1]
    assert_evidence_contract(module, record, evidence)
    assert record["decision_missing"] is False
    assert record["training_eligible"] is True


@pytest.mark.asyncio
async def test_scored_stage_cannot_blank_the_evidence():
    """المرحلة اللاحقة تفوز على القيم العدديّة ولا تمحو الدليل أبدًا.

    هذا هو السطر الذي كان سيقتل الإصلاح: `existing.update(...)` القديم كان
    يمرّر `{}` لأنّه ليس None ولا "" — فيدهس ما أثبتته المرحلة الأسبق.
    """
    module, atom, bus = await collector()
    evidence = evidence_from_367()
    await atom._on_evaluated(evaluated_from_452(2, evidence))
    await atom._on_scored(scored_from_453(2))
    await atom._on_decision(resolved_from_458(2))
    await atom._on_outcome(outcome_from_563(2, profit=-5.0))

    record = bus.payloads(module.EVENT_OUT)[-1]
    assert_evidence_contract(module, record, evidence,
                             note="الدليل مُحي بمرحلة لاحقة فارغة")
    assert record["direction"] == "buy"
    assert record["score"] == 0.75, "المرحلة اللاحقة يجب أن تفوز على العدديّات"
    assert record["outcome"] == "sell", "خسارة على شراء ⇒ التسمية المعاكسة"


@pytest.mark.asyncio
async def test_recorded_outcome_is_accepted_by_362():
    """تكامل داخل القسم: ما ينشره ٣٦٠ يجب أن يقبله ٣٦١ ثم ٣٦٢ فعليًّا.

    هذا الاختبار وحده يمنع عودة العلّة: لا يكفي أن ٣٦٠ «يحفظ» الدليل، بل
    يجب أن يعبر البوّابة التي رفضت ٨٠ من ٨٠.
    """
    module360, atom360, bus360 = await collector()
    await atom360._on_evaluated(evaluated_from_452(3, evidence_from_367()))
    await atom360._on_scored(scored_from_453(3))
    await atom360._on_decision(resolved_from_458(3))
    await atom360._on_outcome(outcome_from_563(3, profit=12.0))
    recorded = bus360.payloads(module360.EVENT_OUT)[-1]

    module361, atom361, bus361 = await make_atom(361, manifest_config(361))
    await atom361._on_record(recorded)
    samples = bus361.payloads(module361.EVENT_OUT)
    assert len(samples) == 1, "٣٦١ رفض سجلًّا صالحًا"

    module362, atom362, bus362 = await make_atom(362, manifest_config(362))
    await atom362._on_sample(samples[0])
    features = bus362.payloads(module362.EVENT_OUT)
    assert len(features) == 1, "٣٦٢ ما زال يرفض — الوصلة لم تُصلح"
    assert features[0]["feature_vector"] == evidence_from_367()["feature_vector"]
    assert features[0]["label"] == "buy"
    assert (await atom362.snapshot())["rejected"] == 0


# ── المطابقة بالهويّة وحدها ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_blind_fallback_to_oldest_decision():
    """نتيجة بلا هويّة مطابِقة تُدقَّق ولا تُدرَّب — ولا تختطف قرارًا قديمًا.

    الاحتياطي القديم كان يُرجع `bucket[0]`، أقدم قرار معلّق (بلغ عمره ٤٫٦
    يوم مقيسًا)، فيُلصق ربحُ صفقةٍ بقرار لم ينتجها ويُبقي `unmatched` صفرًا
    كاذبًا.
    """
    module, atom, bus = await collector()
    await atom._on_evaluated(evaluated_from_452(10, evidence_from_367()))
    await atom._on_evaluated(evaluated_from_452(11, evidence_from_367()))

    stranger = outcome_from_563(999, profit=3.0)
    await atom._on_outcome(stranger)

    record = bus.payloads(module.EVENT_OUT)[-1]
    assert record["decision_missing"] is True
    assert record["training_eligible"] is False
    # v1.4.0: السبب مصنَّف — هنا الهويّة جاءت ولم تُوجد (قرارٌ لم يُخزَّن أو قُلّم)
    assert record["missing_reason"] == "IDENTITY_NOT_FOUND"
    assert (await atom.snapshot())["unmatched_not_found"] == 1
    assert (await atom.snapshot())["unmatched_no_identity"] == 0
    assert (await atom.snapshot())["unmatched"] == 1
    # والقراران المعلّقان باقيان بلا مساس
    assert sum(len(v) for v in (await atom.snapshot())["decisions"].values()) == 2


@pytest.mark.asyncio
async def test_outcome_matches_on_cycle_id_when_prefix_differs():
    """٤٥٢ ينشر `cycle_id` عاريًا و٥٦٣ يعيد `dec:`+نفسه — كلاهما يجب أن يطابق."""
    module, atom, bus = await collector()
    await atom._on_evaluated(evaluated_from_452(12, evidence_from_367()))
    await atom._on_decision(resolved_from_458(12))
    await atom._on_outcome({"account_id": ACCOUNT, "symbol": SYMBOL,
                            "cycle_id": cycle(12), "profit": 4.0,
                            "ticket": 21, "event_id": "evt-21"})
    record = bus.payloads(module.EVENT_OUT)[-1]
    assert record["decision_missing"] is False
    assert record["model_evidence"]["feature_vector"]


@pytest.mark.asyncio
async def test_unmatched_outcome_is_audited_not_trained():
    module, atom, bus = await collector()
    await atom._on_outcome({"account_id": "A", "symbol": "NQ",
                            "ticket": 7, "side": "buy", "profit": 2})
    record = bus.payloads(module.EVENT_OUT)[-1]
    assert record["decision_missing"] is True
    assert record["training_eligible"] is False


# ── التقليم: الذاكرة لا تنمو بلا حدّ ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_pending_is_capped_per_scope():
    """قِيس ٢٩٩٬٤٦٤ قرارًا معلّقًا (لقطة ١٧٩ ميغابايت) بلا أيّ تقليم."""
    module, atom, _bus = await collector(max_pending_per_scope=50)
    for index in range(200):
        await atom._on_evaluated(evaluated_from_452(index, evidence_from_367()))
    state = await atom.snapshot()
    pending = sum(len(v) for v in state["decisions"].values())
    assert pending == 50
    assert state["pruned_cap"] == 150
    # الأحدث هو الباقي، لأنّ النتيجة تلحق قرارها القريب لا البعيد
    kept = list(state["decisions"].values())[0]
    assert kept[-1]["cycle_id"] == cycle(199)


@pytest.mark.asyncio
async def test_pending_ages_out_on_local_arrival_clock():
    """العمر يُقاس بساعة الاستلام المحليّة لا بطابع الحمولة (+٣ ساعات وسيط)."""
    module, atom, _bus = await collector(max_pending_age_s=60)
    await atom._on_evaluated(evaluated_from_452(30, evidence_from_367()))
    scope = list(atom._decisions)[0]
    atom._decisions[scope][0][module.FIELD_RECEIVED] = time.time() - 600.0

    await atom._on_evaluated(evaluated_from_452(31, evidence_from_367()))
    state = await atom.snapshot()
    assert state["pruned_age"] == 1
    remaining = list(state["decisions"].values())[0]
    assert len(remaining) == 1 and remaining[0]["cycle_id"] == cycle(31)


@pytest.mark.asyncio
async def test_pruned_decision_leaves_no_index_entry():
    """التقليم ينزع السجل من الفهرس أيضًا، وإلّا تسرّبت الذاكرة من الباب الآخر."""
    module, atom, _bus = await collector(max_pending_per_scope=5)
    for index in range(40):
        await atom._on_evaluated(evaluated_from_452(index, evidence_from_367()))
    entries = sum(len(index) for index in atom._identity.values())
    pending = sum(len(v) for v in atom._decisions.values())
    assert pending == 5
    assert entries <= pending * 3, "الفهرس ينمو بعد تقليم القوائم"


# ── اللقطة والاستعادة ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restore_prunes_legacy_snapshot_and_rebuilds_index():
    """لقطة ما قبل v1.3.0 بلا طوابع وصول وبلا سقف — تُقلَّم عند الاستعادة."""
    module, atom, _bus = await collector(max_pending_per_scope=10)
    legacy = {
        "snapshot_version": module.SNAPSHOT_VERSION,
        "decisions": {"A\x1fBTCUSD": [
            {"decision_id": "dec:%d" % i, "account_id": "A", "symbol": SYMBOL,
             "cycle_id": str(i), "source_rank": 3, "model_evidence": {},
             "training_eligible": True, "decision_missing": False}
            for i in range(500)
        ]},
        "prices": {SYMBOL: 4400.0},
        "records": 80, "decisions_seen": 299464, "unmatched": 0,
    }
    await atom.restore(legacy)

    state = await atom.snapshot()
    pending = sum(len(v) for v in state["decisions"].values())
    assert pending == 10, "اللقطة القديمة استُعيدت بكامل تراكمها"
    assert state["pruned_cap"] == 490
    assert state["records"] == 80
    # الفهرس أُعيد بناؤه فالمطابقة تعمل فورًا بعد الإقلاع
    assert atom._identity["A\x1fBTCUSD"]["dec:499"] is atom._decisions["A\x1fBTCUSD"][-1]


@pytest.mark.asyncio
async def test_snapshot_round_trip_keeps_counters():
    module, atom, bus = await collector()
    await atom._on_evaluated(evaluated_from_452(40, evidence_from_367()))
    await atom._on_outcome(outcome_from_563(40, profit=10.0))
    state = await atom.snapshot()

    _module, restored, _bus = await collector()
    await restored.restore(state)
    assert (await restored.snapshot())["records"] == 1


@pytest.mark.asyncio
async def test_arrival_stamp_never_reaches_the_learner():
    """`pending_received_at` مسك دفاتر داخليّ — لا يُنشر ولا يلوّث بصمة العيّنة."""
    module, atom, bus = await collector()
    await atom._on_evaluated(evaluated_from_452(50, evidence_from_367()))
    await atom._on_outcome(outcome_from_563(50, profit=1.0))
    record = bus.payloads(module.EVENT_OUT)[-1]
    assert module.FIELD_RECEIVED not in record


# ── الصحّة تُظهر ما يقيسه المالك على اللوحة ──────────────────────────────────

@pytest.mark.asyncio
async def test_health_reports_pending_and_pruned():
    module, atom, _bus = await collector(max_pending_per_scope=5)
    for index in range(20):
        await atom._on_evaluated(evaluated_from_452(index, evidence_from_367()))
    health = await atom.health_check()
    assert health.details["pending"] == 5
    assert health.details["pruned_by_cap"] == 15
    assert health.details["evaluated_seen"] == 20
    assert "pending=5" in health.message


@pytest.mark.asyncio
async def test_unmatched_is_classified_by_which_door_failed():
    """«غير مطابَق» وحدها لا تُعالَج — البابان علاجهما متضادّان.

    قِيس ٢٠٢٦-٠٩-١٠: ١٧ نتيجة من ١٧ أخفقت مطابقتها، ولم يكن في الذرّة ما
    يقول أيّ الأمرين: هويّة غائبة أصلًا (علّتها عند ناشر النتيجة، تُبلَّغ
    جلسته) أم هويّة جاءت ولم تُوجد (قراري قُلّم، والعلاج عيارٌ عندي).
    """
    module, atom, bus = await collector()

    # (أ) نتيجة بلا أيّ حقل هويّة
    await atom._on_outcome({"account_id": ACCOUNT, "symbol": SYMBOL,
                            "ticket": 91, "side": "buy", "profit": 3.0})
    first = bus.payloads(module.EVENT_OUT)[-1]
    assert first["missing_reason"] == "NO_IDENTITY_ON_OUTCOME"

    # (ب) نتيجة تحمل هويّة لا وجود لها عندي
    await atom._on_outcome(outcome_from_563(777, profit=-2.0, ticket=92))
    second = bus.payloads(module.EVENT_OUT)[-1]
    assert second["missing_reason"] == "IDENTITY_NOT_FOUND"

    state = await atom.snapshot()
    assert state["unmatched"] == 2
    assert state["unmatched_no_identity"] == 1
    assert state["unmatched_not_found"] == 1

    health = await atom.health_check()
    assert "no_id=1" in health.message and "not_found=1" in health.message, health.message


@pytest.mark.asyncio
async def test_health_degrades_when_recent_window_is_all_blind():
    """شارة خضراء فوق عمًى: التراكميّ يخفيه، فالحكم على نافذة الأحدث.

    ٨٠ مطابَقة قديمة مقابل ١٧ إخفاقًا حديثًا أبقت الحالة `HEALTHY` بينما
    لا نتيجةٌ واحدة تعبر إلى التعلّم.
    """
    module, atom, bus = await collector()

    # نتيجة واحدة ناجحة أوّلًا ⇒ النافذة ليست عمياء
    await atom._on_evaluated(evaluated_from_452(60, evidence_from_367()))
    await atom._on_decision(resolved_from_458(60))
    await atom._on_outcome(outcome_from_563(60, profit=5.0, ticket=1))
    assert (await atom.health_check()).state.value == "healthy"

    # ثمّ عمًى متّصل يملأ النافذة
    for index in range(module.MATCH_WINDOW):
        await atom._on_outcome(outcome_from_563(900 + index, profit=1.0,
                                                ticket=100 + index))
    health = await atom.health_check()
    assert health.state.value == "degraded", health.message
    assert "last%d=0" % module.MATCH_WINDOW in health.message, health.message

    # وتعود خضراء بأوّل مطابقة ناجحة
    await atom._on_evaluated(evaluated_from_452(61, evidence_from_367()))
    await atom._on_decision(resolved_from_458(61))
    await atom._on_outcome(outcome_from_563(61, profit=2.0, ticket=200))
    assert (await atom.health_check()).state.value == "healthy"