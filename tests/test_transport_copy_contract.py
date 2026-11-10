"""عقد النسخ في مسار النشر الحيّ — لقطةٌ واحدة، لا مسحان.

**العطب المقيس ٢٠٢٦-٠٩-١٠ (ورقة المالك §٢٨):** كان النشر يمرّ على الحمولة
**مرّتين** — `_fast_copy` (pickle ذهابًا وإيابًا) ثمّ `freeze_payload` التي
تبني الحاويات من جديد أصلًا. مسحان لبناء لقطة واحدة.

    ملمح ٦٠ ثانية على النواة الحيّة: `_fast_copy` = 8.0% من المعالج كلّه
    مقياس ٢٠٬٠٠٠ نشرة: 1.9120 ث ⟵ 0.9422 ث  =  2.03× (−50.7%)

وهذه الاختبارات تحرس **ما لا يجوز أن يُشترى بتلك السرعة**: العزل.
"""

from __future__ import annotations

import asyncio

import pytest

import transport.owned_event_bus as bus_module
import transport.readonly as readonly
from transport.owned_event_bus import OwnedEventBus
from transport.readonly import ReadOnlyDict, freeze_payload


def _payload() -> dict:
    return {
        "symbol": "USTEC",
        "levels": [{"price": 100.0 + i, "size": i} for i in range(5)],
        "meta": {"session": "NY", "flags": ["live"]},
    }


# ── لا مسح مزدوج ────────────────────────────────────────────────────────

def test_publishing_does_not_deep_copy_the_payload_twice() -> None:
    """`_fast_copy` **لا** تُستدعى في المسار المشترك — `freeze_payload` تكفي."""
    calls = []
    original = bus_module._fast_copy
    bus_module._fast_copy = lambda value: (calls.append(1), original(value))[1]
    try:
        bus = OwnedEventBus()

        async def reader(_payload: dict) -> None:
            return None

        bus.subscribe("market.tick", reader, subscriber="s")

        async def run() -> None:
            await bus.publish("market.tick", _payload(), publisher="t")
            await bus.drain(timeout_s=5.0)
            await bus.close()

        asyncio.run(run())
    finally:
        bus_module._fast_copy = original
    assert calls == [], "عادت النسخة العميقة إلى مسار النشر: %d استدعاء" % len(calls)


# ── ما لا يجوز أن يُشترى بالسرعة ────────────────────────────────────────

def test_publish_never_touches_the_publisher_dict() -> None:
    """`setdefault` تكتب في نسختنا لا في قاموس الناشر."""
    bus = OwnedEventBus()
    mine = _payload()
    before = dict(mine)

    async def run() -> None:
        await bus.publish("market.tick", mine, publisher="t")
        await bus.close()

    asyncio.run(run())
    assert mine == before, "لُوِّث قاموس الناشر: %s" % (set(mine) - set(before))


def test_a_subscriber_never_sees_a_mutation_made_after_publish() -> None:
    """⛔ **الحارس الأهمّ.** اللقطة تُؤخذ تزامنيًّا لحظةَ النشر.

    هذا ما يمنع «التجميد الكسول»: سقف وفره 152× لكنّ الشجرة تبقى مشتركة مع
    الناشر حتى أوّل قراءة. والطوابير المقيسة بلغت 21,616 رسالة و238.9 ثانية،
    فالمشترك قد يقرأ بعد دقائق — ويقرأ حينها حالةً غير حالة لحظته.
    """
    bus = OwnedEventBus()
    seen: list = []

    async def reader(payload: dict) -> None:
        seen.append((payload["levels"][0]["price"], list(payload["meta"]["flags"])))

    bus.subscribe("market.tick", reader, subscriber="s")
    mine = _payload()

    async def run() -> None:
        await bus.publish("market.tick", mine, publisher="t")
        mine["levels"][0]["price"] = 999.0        # الناشر يعدّل بعد النشر
        mine["meta"]["flags"].append("MUTATED")
        await bus.drain(timeout_s=5.0)
        await bus.close()

    asyncio.run(run())
    assert seen == [(100.0, ["live"])], "تسرّب تعديلُ ما بعد النشر: %s" % seen


def test_the_payload_reaching_an_atom_cannot_be_mutated() -> None:
    bus = OwnedEventBus()
    errors: list = []

    async def reader(payload: dict) -> None:
        try:
            payload["injected"] = True
            errors.append("قُبل التعديل")
        except TypeError:
            pass
        try:
            payload["levels"][0]["price"] = 1.0
            errors.append("قُبل تعديل عميق")
        except TypeError:
            pass

    bus.subscribe("market.tick", reader, subscriber="s")

    async def run() -> None:
        await bus.publish("market.tick", _payload(), publisher="t")
        await bus.drain(timeout_s=5.0)
        await bus.close()

    asyncio.run(run())
    assert errors == [], errors


def test_the_replay_snapshot_is_frozen_not_a_live_reference() -> None:
    """مشتركٌ متأخّر يقرأ لقطة لحظة النشر لا شجرةً تبدّلت بعدها."""
    bus = OwnedEventBus()
    mine = _payload()
    late: list = []

    async def latecomer(payload: dict) -> None:
        late.append(payload["levels"][0]["price"])

    async def run() -> None:
        await bus.publish("market.tick", mine, publisher="t")
        mine["levels"][0]["price"] = 777.0
        bus.subscribe("market.tick", latecomer, subscriber="late")
        await bus.drain(timeout_s=5.0)
        await bus.close()

    asyncio.run(run())
    if late:                       # يُعاد التشغيل فقط لأحداث قابلة لذلك
        assert late == [100.0], "المشترك المتأخّر قرأ تعديلًا بعد اللقطة: %s" % late


# ── عزل الكائن التطبيقيّ ────────────────────────────────────────────────

class _Live:
    """كائن تطبيقيّ متغيّر — ما كانت `_fast_copy` تنسخه ضمنًا."""

    def __init__(self) -> None:
        self.value = 1


def test_an_application_object_is_isolated_and_counted() -> None:
    before = readonly.isolated_objects
    live = _Live()
    frozen = freeze_payload({"handle": live})
    assert readonly.isolated_objects == before + 1, "مرّ الكائن بلا عزل ولا عدّ"
    frozen["handle"].value = 2
    assert live.value == 1, "الناشر والمشترِك يتقاسمان كائنًا حيًّا"


def test_an_uncopyable_object_passes_through_instead_of_raising() -> None:
    """كائن لا يُنسخ يمرّ كما كان — لا يُسقِط النشر."""
    import threading
    lock = threading.Lock()
    assert freeze_payload({"lock": lock})["lock"] is lock


@pytest.mark.parametrize("value", [1, 1.5, "x", True, None, b"b"])
def test_plain_leaves_pass_through_untouched(value) -> None:  # noqa: ANN001
    before = readonly.isolated_objects
    assert freeze_payload(value) is value
    assert readonly.isolated_objects == before, "عُزلت ورقة عادية"


def test_immutable_leaves_are_not_copied() -> None:
    import datetime, decimal, uuid
    before = readonly.isolated_objects
    for value in (datetime.datetime(2026, 9, 10), datetime.date(2026, 9, 10),
                  decimal.Decimal("1.5"), uuid.uuid4(), frozenset({1})):
        assert freeze_payload(value) is value
    assert readonly.isolated_objects == before


def test_nested_containers_are_still_frozen_all_the_way_down() -> None:
    frozen = freeze_payload({"a": {"b": [{"c": 1}]}})
    assert isinstance(frozen, ReadOnlyDict)
    with pytest.raises(TypeError):
        frozen["a"]["b"][0]["c"] = 2


def test_shared_mode_never_makes_a_private_copy_for_a_global_subscriber() -> None:
    """⛔ طفرةٌ نجت: `isolate_payload = payload_mode != "shared_readonly"`.

    (`owned_event_bus.py` سطر 216.) لو انقلب العامل لصار **كلّ** مشترِك
    عامّ يأخذ نسخةً خاصّة في الوضع المشترك — أي ينقلب عقد النقل رأسًا على
    عقب، وهو الذي بُنيت الحملة كلّها عليه. والقياس الحيّ يقول
    `private_deliveries = 0` من 25,951,038 تسليمة.

    ولم يكن يحرسه شيء لأنّ اختباراتي كانت تمرّر `isolate_payload` صراحةً،
    فلا تمسّ فرع الاشتقاق الافتراضيّ أبدًا.
    """
    async def run() -> dict:
        bus = OwnedEventBus(payload_mode="shared_readonly", worker_count=3)

        async def watcher(_name: str, _payload: dict) -> None:
            return None

        bus.subscribe_all(watcher, subscriber="810")   # بلا isolate_payload
        await bus.publish("market_data.cleaned",
                          {"account_id": "52992818", "symbol": "USTEC",
                           "levels": [{"p": 1.0}]}, publisher="t")
        await bus.drain(timeout_s=10.0)
        stats = bus.transport_stats()
        await bus.close()
        return stats

    stats = asyncio.run(run())
    assert stats["private_deliveries"] == 0, (
        "الوضع المشترك صنع نسخةً خاصّة: %d" % stats["private_deliveries"])
    assert stats["shared_deliveries"] >= 1, "لم يُسلَّم شيء أصلًا"


def test_an_explicit_private_subscriber_still_gets_its_own_copy() -> None:
    """والفرع الآخر حيٌّ ويجب أن يبقى: من يطلب العزل صراحةً يأخذه.

    فلو صار كلّ شيء مشتركًا لصمت العدّاد بالطريقة المعاكسة.
    """
    async def run() -> dict:
        bus = OwnedEventBus(payload_mode="shared_readonly", worker_count=3)

        async def private(_name: str, _payload: dict) -> None:
            return None

        bus.subscribe_all(private, subscriber="خاصّة",
                          isolate_payload=True, hot_scope="52992818|USTEC")
        await bus.publish("market_data.cleaned",
                          {"account_id": "52992818", "symbol": "USTEC"},
                          publisher="t")
        await bus.drain(timeout_s=10.0)
        stats = bus.transport_stats()
        await bus.close()
        return stats

    stats = asyncio.run(run())
    assert stats["private_deliveries"] >= 1, "طلب العزل صراحةً ولم يُعزَل"


def test_the_isolated_mode_delegates_and_its_delivery_counters_stay_blind() -> None:
    """⚠️ حدٌّ يجب أن يُكتب لا أن يُكتشَف مرّةً ثانية.

    في `payload_mode="isolated"` يفوّض `publish` إلى النواة الأمّ بالكامل
    (`owned_event_bus.py` سطر 234) — فلا يمرّ بحلقة التسليم عندي، و**عدّادا
    `shared_deliveries` و`private_deliveries` يبقيان صفرًا مهما نُشر**.

    اكتشفتُ هذا حين كتبتُ حارسًا يفترض عكسه فسقط. وهو ليس عطبًا: الوضع
    مسارُ تراجعٍ قديم. لكنّ عدّادًا يقرأ صفرًا حيث يُسلَّم فعلًا يكذب
    بالصمت — فيُثبَّت هنا حتّى لا يُقرأ يومًا «لا تسليم».
    """
    async def run() -> dict:
        bus = OwnedEventBus(payload_mode="isolated", worker_count=3)

        async def watcher(_name: str, _payload: dict) -> None:
            return None

        bus.subscribe_all(watcher, subscriber="810")
        await bus.publish("market_data.cleaned",
                          {"account_id": "52992818", "symbol": "USTEC"},
                          publisher="t")
        await bus.drain(timeout_s=10.0)
        stats = bus.transport_stats()
        await bus.close()
        return stats

    stats = asyncio.run(run())
    assert stats["published"] == 1, "النشر لا يُعدّ في وضع العزل"
    assert stats["shared_deliveries"] == 0 and stats["private_deliveries"] == 0, (
        "تغيّر السلوك: صار وضع العزل يعدّ التسليم — حدِّث هذا الحارس ووثّقه")
