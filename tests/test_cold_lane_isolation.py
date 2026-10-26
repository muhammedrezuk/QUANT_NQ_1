"""عزل المخازن على المسار البارد — التِكّة قبل السجلّ.

**قرار المالك ٢٠٢٦-٠٩-١٠:** «اعزل المخازن على المسار البارد أولًا، ولا
تغيّر أكثر من ذلك قبل قياس النتيجة».

## ⛔ العطب المقيس على النواة الحيّة

    707 حجب مساره **2,230 مرّة** · أسوأ تجاوز **5.6428 ث**
    712 نادى `VACUUM` **داخل معالج الحدث** — دورة قِيست بـ**252 ثانية**
    P99 تِكّة ← قرار: 24.2 ث (USTEC) · 29.8 ث (XAUUSD) · العتبة 0.1000

ومسار الملكية يسلّم **بالتتابع** على مسار العامل الواحد. فمشترِكٌ يحجب
خمس ثوانٍ **يحجب كلّ ما خلفه على مساره** — لا يتأخّر وحده.

## وما لا يفعله هذا العزل

**لا يجعل المخزن أسرع.** كلفة `VACUUM` تبقى كما هي؛ الذي يتغيّر أنّها لم
تعد على طريق السوق. وثمنه معلَن: المسار البارد **واحد**، فالمخازن تتزاحم
فيما بينها. وهذا مقصود — التِكّة قبل السجلّ.

## ولماذا النطاق من الإعداد لا من الكود

§٤٣ تمنع تثبيت أرقام الأقسام في الطبقة التحتيّة. الناقل لا يعرف أنّ
«700-749 مخازن» — يعرف أنّ الإعداد أعلن نطاقًا باردًا.
"""

from __future__ import annotations

import asyncio

import pytest

from transport.owned_event_bus import OwnedEventBus

STORAGE = [[700, 749]]


def _bus(**kwargs) -> OwnedEventBus:  # noqa: ANN003
    return OwnedEventBus(**kwargs)


# ── مَن يُعدّ باردًا ─────────────────────────────────────────────────────

def test_a_subscriber_inside_a_declared_cold_section_is_cold() -> None:
    bus = _bus(cold_sections=STORAGE)
    assert bus._is_cold_subscriber("707") is True
    assert bus._is_cold_subscriber("712") is True
    assert bus._is_cold_subscriber("749") is True, "الحدّ الأعلى داخل النطاق"
    assert bus._is_cold_subscriber("700") is True, "الحدّ الأدنى داخل النطاق"


def test_a_market_subscriber_stays_hot() -> None:
    """⛔ الأخطر عكسًا: تبريد ذرّة سوق يضعها خلف المخازن."""
    bus = _bus(cold_sections=STORAGE)
    for name in ("101", "151", "467", "622", "699", "750"):
        assert bus._is_cold_subscriber(name) is False, name


def test_the_known_cold_names_stay_cold_without_any_section() -> None:
    """اللوحة والقياس باردان بالاسم — لا يعتمدان على إعداد."""
    bus = _bus()
    for name in ("cold:anything", "core.api", "dashboard", "telemetry"):
        assert bus._is_cold_subscriber(name) is True, name


def test_without_declared_sections_no_atom_is_cold() -> None:
    """بلا إعلان لا تبريد — لا افتراض في الطبقة التحتيّة (§٤٣)."""
    bus = _bus()
    assert bus._is_cold_subscriber("707") is False


def test_a_non_numeric_subscriber_never_matches_a_section() -> None:
    bus = _bus(cold_sections=STORAGE)
    assert bus._is_cold_subscriber("") is False
    assert bus._is_cold_subscriber("707_مخزن") is False
    assert bus._is_cold_subscriber("feed") is False


# ── الأثر على التوجيه ───────────────────────────────────────────────────

def test_subscribing_a_storage_atom_marks_it_cold_before_first_delivery() -> None:
    """يُثبَّت قبل أوّل تسليم — لا بعد أن يحجب."""
    bus = _bus(cold_sections=STORAGE)

    async def store(_payload: dict) -> None:
        return None

    bus.subscribe("decision.cycle.record", store, subscriber="707")
    assert id(store) in bus._cold_handlers


def test_a_hot_atom_is_not_marked() -> None:
    bus = _bus(cold_sections=STORAGE)

    async def analyse(_payload: dict) -> None:
        return None

    bus.subscribe("market_data.cleaned", analyse, subscriber="151")
    assert id(analyse) not in bus._cold_handlers


def test_cold_and_hot_land_on_different_lanes() -> None:
    """§ الملكية — العزل يعني مسارًا آخر، لا مجرّد وسمٍ في مجموعة."""
    async def run() -> tuple[int, int]:
        bus = _bus(cold_sections=STORAGE, worker_count=3)

        async def store(_payload: dict) -> None:
            return None

        async def analyse(_payload: dict) -> None:
            return None

        bus.subscribe("decision.cycle.record", store, subscriber="707")
        bus.subscribe("market_data.cleaned", analyse, subscriber="151")
        await bus.publish("decision.cycle.record", {"symbol": "USTEC"}, publisher="t")
        await bus.publish("market_data.cleaned", {"symbol": "USTEC"}, publisher="t")
        await bus.drain(timeout_s=10.0)
        runtime = bus._runtime
        cold_worker = runtime._handler_workers[id(store)]
        hot_worker = runtime._handler_workers[id(analyse)]
        await bus.close()
        return cold_worker, hot_worker

    cold_worker, hot_worker = asyncio.run(run())
    assert cold_worker != hot_worker, (
        "المخزن والمحلّل على مسارٍ واحد — العزل لم يقع")


@pytest.mark.parametrize("subscriber", ["701", "707", "712", "749"])
def test_every_storage_atom_shares_the_one_cold_lane(subscriber: str) -> None:
    """الثمن المعلَن: المسار البارد **واحد**، فالمخازن تتزاحم فيما بينها.

    هذا مقصود لا سهو: التِكّة قبل السجلّ. ويُختبر كي لا يُقرأ لاحقًا
    مفاجأةً حين يبطئ مخزنٌ مخزنًا.
    """
    async def run() -> tuple[int, int]:
        bus = _bus(cold_sections=STORAGE, worker_count=4)

        async def first(_payload: dict) -> None:
            return None

        async def second(_payload: dict) -> None:
            return None

        bus.subscribe("a.state", first, subscriber="707")
        bus.subscribe("b.state", second, subscriber=subscriber)
        await bus.publish("a.state", {"symbol": "X"}, publisher="t")
        await bus.publish("b.state", {"symbol": "X"}, publisher="t")
        await bus.drain(timeout_s=10.0)
        runtime = bus._runtime
        lanes = (runtime._handler_workers[id(first)],
                 runtime._handler_workers[id(second)])
        await bus.close()
        return lanes

    first_lane, second_lane = asyncio.run(run())
    assert first_lane == second_lane


# ── الإعلان ─────────────────────────────────────────────────────────────

def test_stats_declare_the_cold_contract() -> None:
    """عزلٌ لا يُرى لا يُصدَّق — يُعلَن في التشخيص."""
    async def run() -> dict:
        bus = _bus(cold_sections=STORAGE)

        async def store(_payload: dict) -> None:
            return None

        bus.subscribe("x.state", store, subscriber="707")
        stats = bus.transport_stats()
        await bus.close()
        return stats

    stats = asyncio.run(run())
    assert stats["cold_sections"] == [[700, 749]]
    assert stats["cold_handlers"] >= 1


# ══ ⛔ المسار البارد صار يحمل السوق — مقيس على النواة الحيّة ٢٠٢٦-٠٩-١٦ ═══
#
# العزل بُني ليُبعد المخازن عن طريق السوق. لكنّ العامل البارد بقي عاملًا
# عاديًّا في نظر **خريطة النطاقات**، فأُسندت إليه نطاقات سوق:
#
#     العامل البارد 5 يملك 52992818|XAUUSD · US500 · USTEC#1 · GBPUSD#1
#     وعليه ذرّات تحليل بطوابير: 407=453 · 412=455 · 166=206
#     خلف 707 (53 م.ث/حدث) · 714 (89) · 712 (طابور 1024)
#     وطابور المسار كلّه 20,558 · وإسقاطه 1,105,977
#
# فالمسار الذي يحمي السوق من التخزين **صار يحمل السوق خلف التخزين**.
#
# وضاعفت الموازنة الأذى بعد إصلاحها: تقيس الحِمل بعدد الورود لا بزمن
# الانشغال، فيبدو البارد «خفيفًا» (أحداثه قليلة وبطيئة) فتُرسل إليه المزيد —
# عقوبةٌ على البطء بمزيدٍ من العمل.
#
# **ولماذا عاش:** كلّ اختبارات هذا الملفّ تسأل «هل المخزن على مسارٍ غير
# مسار المحلّل؟» ولا يسأل واحدٌ منها **«هل يملك المسار البارد نطاق سوق؟»**
# — وهو السؤال الذي يصف الغرض لا الآليّة.


def test_the_cold_lane_never_owns_a_market_scope() -> None:
    """⛔ الحارس الذي كان غائبًا — يصف الغرض لا الآليّة."""
    from transport.ownership import OwnershipKey

    async def run() -> tuple[int, dict]:
        bus = _bus(cold_sections=STORAGE, worker_count=6)
        runtime = bus._runtime
        owners = {}
        for symbol in ("XAUUSD", "USTEC", "EURUSD", "US30", "BTCUSD",
                       "GBPUSD", "US500", "AUDUSD", "DXY_U6"):
            key = OwnershipKey("52992818", symbol)
            for group in range(runtime.scope_groups):
                owners["%s#%d" % (symbol, group)] = \
                    runtime.registry.owner_for(key, group)
        cold = runtime._cold_worker
        await bus.close()
        return cold, owners

    cold, owners = asyncio.run(run())
    trespassers = {unit: worker for unit, worker in owners.items() if worker == cold}
    assert not trespassers, (
        "نطاقات سوق على المسار البارد %d: %s" % (cold, trespassers))


def test_the_cold_lane_is_not_a_rebalance_target() -> None:
    """والموازنة لا تُرسل إليه أيضًا — وإلّا عاد العطب بعد دقائق تشغيل."""
    from transport.ownership import OwnershipKey, OwnershipRegistry

    registry = OwnershipRegistry(6, reserved_workers=(5,))
    for index in range(12):
        key = OwnershipKey("52992818", "S%02d" % index)
        for _ in range(200 if index == 0 else 5):
            registry.owner_for(key)
    for _ in range(20):
        registry.rebalance(max_moves=1)
    assert 5 not in set(registry._partition_map[p]
                        for p in registry._assigned_partitions), (
        "الموازنة نقلت نطاقًا إلى المسار البارد")
    assert 5 not in registry.worker_load(), (
        "المحجوز يظهر في جدول الحِمل فيبدو أخفّ الجميع")


def test_cold_subscribers_still_land_on_the_cold_lane() -> None:
    """⚠️ والحجز **ليس** تعطيلًا للمسار: المخازن تُثبَّت عليه مباشرةً.

    فلو فُهم الحجز «لا أحد على البارد» لانقلب العلاج إلى العلّة الأصليّة —
    المخازن تعود إلى مسارات السوق.
    """
    async def run() -> tuple[int, int]:
        bus = _bus(cold_sections=STORAGE, worker_count=6)

        async def store(_payload: dict) -> None:
            return None

        bus.subscribe("decision.cycle.record", store, subscriber="707")
        await bus.publish("decision.cycle.record",
                          {"account_id": "52992818", "symbol": "XAUUSD"},
                          publisher="t")
        await bus.drain(timeout_s=10.0)
        runtime = bus._runtime
        lane = runtime._handler_workers[id(store)]
        cold = runtime._cold_worker
        await bus.close()
        return lane, cold

    lane, cold = asyncio.run(run())
    assert lane == cold, "المخزن خرج من المسار البارد — انقلب العلاج إلى العلّة"


def test_a_single_worker_core_still_routes() -> None:
    """حدٌّ: عاملٌ واحد لا يُحجَز منه شيء، وإلّا بقي النقل بلا مسار."""
    from transport.ownership import OwnershipKey, OwnershipRegistry

    registry = OwnershipRegistry(1, reserved_workers=(0,))
    assert registry.owner_for(OwnershipKey("52992818", "XAUUSD")) == 0
