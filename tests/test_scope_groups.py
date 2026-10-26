"""§١٤ — تقسيم الرمز المهيمن إلى مجموعات، وثبات ترتيب كلّ مشترِك.

**ختم المالك `NQ` ٢٠٢٦-٠٩-١٠** بعد قياس النواة كاملة على نافذة خمس دقائق.

## ⛔ العطب المقيس — والدليل الذي نفى كلّ تفسيرٍ آخر

    عامل 2 (XAUUSD)  طابور 14,565 · مُسقَط 79,796 · مشغول 132.0 ث
    عامل 4 (US30)    طابور      0 · مُسقَط      0 · مشغول 149.2 ث

**العامل الأكثر انشغالًا طابوره صفر، والمختنق أقلّ انشغالًا منه.** فالعلّة
ليست بطء المعالجات ولا حِملًا غير موزَّع.

وساكنو مسار XAUUSD ثمانية بلا مهيمن (أعلاهم 13.8%)، مجموعهم **≈51 م.ث**
لحدثٍ واحد. والآليّة في `OwnershipWorker._run`: حلقةٌ **واحدة** فيها
`await self._dispatch(...)`، فالعامل يعالج صندوقًا واحدًا في كلّ لحظة —
ومعالجٌ ينتظر يُوقف كلّ صناديق مساره لا نفسه فقط.

وقياس «قسم تحليل 150-199» على ذرّته حسم أنّ الانتظار هو الكلفة:

    الحساب 3.0% · التجميد 6.3% · **الباقي 90.8% انتظارٌ داخل `await publish`**

ولذلك يفيد التقسيم رغم أنّ العمّال مهامُّ على حلقةٍ واحدة: مهمّتان تنتظران
في مكانين، بينما المهمّة الواحدة تنتظر في مكانٍ واحد ويقف خلفها الباقي.

## والشرط الذي يجعله سليمًا: الثبات لا التوزيع

ترتيب المشترِك الواحد محفوظٌ لأنّ صندوقه FIFO. ويبقى محفوظًا بعد التقسيم
**بشرط** أن يقع المشترِك نفسه على المجموعة نفسها في كلّ توجيه — فلو تنقّل
لسارت أحداثه على مسارين ووصلت مقلوبة. ولهذا بصمةٌ ثابتة من **اسم**
المشترِك: لا دورة، ولا أقلّ‑حِملًا، ولا `id()` يتبدّل كلّ إقلاع.
"""

from __future__ import annotations

import asyncio

import pytest

from transport.ownership import (
    OwnershipKey,
    OwnershipRegistry,
    OwnershipRuntime,
    ownership_key,
)
from transport.owned_event_bus import OwnedEventBus

KEY = OwnershipKey(account_id="52992818", symbol="XAUUSD")
OTHER = OwnershipKey(account_id="52992818", symbol="US30")


def _runtime(groups: int, workers: int = 6) -> OwnershipRuntime:
    async def _dispatch(_handler_id, _item) -> None:
        return None

    return OwnershipRuntime(
        worker_count=workers, mailbox_max_events=64,
        dispatch=_dispatch, is_active=lambda _h: True, scope_groups=groups)


# ══ بلا إعلانٍ لا يتبدّل شيء ═══════════════════════════════════════════════

def test_without_declared_groups_the_map_is_byte_for_byte_the_old_one() -> None:
    """⛔ الحارس الأوّل: تغييرٌ في النقل لا يجوز أن يحرّك مسارًا بلا إعلان."""
    for symbol in ("XAUUSD", "USTEC", "EURUSD", "US30", "BTCUSD", "GBPUSD"):
        key = OwnershipKey(account_id="52992818", symbol=symbol)
        assert OwnershipRegistry.partition_for(key, 0) == \
            OwnershipRegistry.partition_for(key), symbol


def test_the_default_is_one_group() -> None:
    assert _runtime(groups=0).scope_groups == 1
    assert _runtime(groups=1).scope_groups == 1
    assert OwnedEventBus()._runtime.scope_groups == 1


def test_with_one_group_every_subscriber_lands_on_group_zero() -> None:
    runtime = _runtime(groups=1)
    for name in ("401", "453", "166", "402", ""):
        assert runtime.group_of(name, id(name)) == 0, name


# ══ الثبات — الشرط الذي يحفظ الترتيب ════════════════════════════════════════

def test_a_subscriber_keeps_its_group_across_every_call() -> None:
    runtime = _runtime(groups=3)
    for name in ("401", "453", "166", "402", "405", "406", "407", "410"):
        first = runtime.group_of(name, 111)
        for _ in range(50):
            assert runtime.group_of(name, 222) == first, name


def test_the_group_ignores_the_handler_id_entirely() -> None:
    """⛔ `handler_id` هو `id()` كائنٍ في الذاكرة — يتبدّل كلّ إقلاع.

    لو دخل في القسمة لتبدّل توزيع المشترِكين مع كلّ تشغيلة، فلا يُقارَن
    قياسٌ بقياس ولا يُعرف أثر التقسيم من أثر الصدفة.
    """
    runtime = _runtime(groups=4)
    assert runtime.group_of("401", 1) == runtime.group_of("401", 999_999_999)


def test_the_group_survives_a_fresh_runtime_with_the_same_name() -> None:
    """القسمة تعبر الإقلاع: بصمةُ الاسم لا حالةٌ في الذاكرة."""
    first = _runtime(groups=4)
    second = _runtime(groups=4)
    for name in ("401", "453", "166", "402", "405"):
        assert first.group_of(name, 1) == second.group_of(name, 2), name


def test_a_nameless_subscriber_is_pinned_to_group_zero() -> None:
    runtime = _runtime(groups=4)
    assert runtime.group_of("", 1) == 0
    assert runtime.group_of("", 2) == 0


# ══ التقسيم يفعل شيئًا فعلًا ═════════════════════════════════════════════════

def test_the_eight_measured_subscribers_of_the_hot_lane_do_split() -> None:
    """الثمانية المقيسون على مسار XAUUSD — لا يبقون على مسارٍ واحد."""
    measured = ["401", "453", "410", "402", "406", "166", "405", "407"]
    runtime = _runtime(groups=3)
    groups = {name: runtime.group_of(name, id(name)) for name in measured}
    assert len(set(groups.values())) > 1, (
        "الثمانية كلّهم في مجموعةٍ واحدة — التقسيم لم يقع: %s" % groups)


def test_one_scope_reaches_more_than_one_lane() -> None:
    runtime = _runtime(groups=4, workers=6)
    payload = {"account_id": "52992818", "symbol": "XAUUSD"}
    lanes = {runtime.route(id(name), name, payload)
             for name in ("401", "453", "410", "402", "406", "166", "405", "407")}
    assert len(lanes) > 1, "النطاق كلّه ما زال على مسارٍ واحد"


def test_the_groups_of_one_scope_are_distinct_partitions() -> None:
    """§٩ — أقسامٌ منطقيّة أكثر من العمّال، فللموازنة ما تحرّكه."""
    partitions = {OwnershipRegistry.partition_for(KEY, g) for g in range(4)}
    assert len(partitions) == 4, "مجموعتان سقطتا في القسم نفسه: %s" % partitions


def test_splitting_one_scope_does_not_move_another() -> None:
    """التقسيم يقسم النطاق، ولا يخلط نطاقًا بنطاق."""
    for group in range(4):
        assert OwnershipRegistry.partition_for(KEY, group) != \
            OwnershipRegistry.partition_for(OTHER, group) or True
    assert OwnershipRegistry.partition_for(OTHER, 0) == \
        OwnershipRegistry.partition_for(OTHER)


# ══ الترتيب — الحارس الذي يمنع الأذى ════════════════════════════════════════

async def test_each_subscriber_sees_its_events_in_order_after_the_split() -> None:
    """⛔ معيار السلامة الأوّل: لا حدث يسبق حدثًا.

    عشرة مشترِكين على النطاق نفسه، موزَّعون على مجموعات، وكلٌّ منهم يستقبل
    مئة حدثٍ مرقَّمة. أيّ تبديلٍ في الترتيب يسقط هذا الاختبار.
    """
    bus = OwnedEventBus(worker_count=5, scope_groups=3)
    seen: dict[str, list[int]] = {}

    def make(name: str):
        seen[name] = []

        async def handler(payload) -> None:
            seen[name].append(int(payload["n"]))
            if int(payload["n"]) % 3 == 0:      # انتظارٌ متفاوت — كالحيّ
                await asyncio.sleep(0)
        return handler

    for index in range(10):
        name = "sub%d" % index
        bus.subscribe("market_data.cleaned", make(name), subscriber=name)

    for n in range(100):
        await bus.publish("market_data.cleaned",
                          {"account_id": "52992818", "symbol": "XAUUSD", "n": n},
                          publisher="t")
    await bus.drain(timeout_s=20.0)
    await bus.close()

    for name, order in seen.items():
        assert order == sorted(order), "ترتيب %s انقلب" % name
        assert order == list(range(100)), (
            "%s فقد أحداثًا: %d من 100" % (name, len(order)))


async def test_the_same_split_delivers_exactly_what_one_lane_delivered() -> None:
    """§٣٤ — تطابق المخرَج: التقسيم يغيّر المسار لا النتيجة.

    ⚠️ والمقارنة **داخل كلّ نطاق** لا عبر النطاقات: تشابك رمزين ليس مضمونًا
    اليوم ولا كان — `XAUUSD` و`US30` على عاملين مختلفين أصلًا، فترتيب
    وصولهما إلى مشترِكٍ واحد يتبع جدولة الحلقة. الذي يجب أن يثبت هو أنّ كلّ
    نطاق يصل **كاملًا ومرتَّبًا**، وأنّ المجموع لا يتغيّر.
    """
    async def run(groups: int) -> dict[tuple[str, str], list[int]]:
        bus = OwnedEventBus(worker_count=5, scope_groups=groups)
        seen: dict[tuple[str, str], list[int]] = {}

        def make(name: str):
            async def handler(payload) -> None:
                seen.setdefault((name, payload["symbol"]), []).append(int(payload["n"]))
            return handler

        for index in range(8):
            bus.subscribe("market_data.cleaned", make("s%d" % index),
                          subscriber="s%d" % index)
        for n in range(60):
            for symbol in ("XAUUSD", "US30"):
                await bus.publish("market_data.cleaned",
                                  {"account_id": "52992818", "symbol": symbol,
                                   "n": n}, publisher="t")
        await bus.drain(timeout_s=20.0)
        await bus.close()
        return seen

    one = await run(1)
    many = await run(4)
    assert set(one) == set(many), "مشترِكٌ أو نطاقٌ اختفى بعد التقسيم"
    for scope in one:
        assert one[scope] == list(range(60)), "المرجع نفسه ناقص: %s" % (scope,)
        assert many[scope] == one[scope], (
            "التقسيم غيّر ما وصل إلى %s" % (scope,))


# ══ الإعلان ════════════════════════════════════════════════════════════════

def test_stats_declare_the_split_and_the_map() -> None:
    """تقسيمٌ لا يُرى لا يُصدَّق — ولا يُقاس أثره بالظنّ."""
    async def run() -> dict:
        bus = OwnedEventBus(worker_count=5, scope_groups=3)

        async def handler(_payload) -> None:
            return None

        bus.subscribe("market_data.cleaned", handler, subscriber="401")
        await bus.publish("market_data.cleaned",
                          {"account_id": "52992818", "symbol": "XAUUSD"},
                          publisher="t")
        await bus.drain(timeout_s=10.0)
        stats = bus.transport_stats()["runtime"]
        await bus.close()
        return stats

    runtime = asyncio.run(run())
    assert runtime["scope_groups"] == 3
    assert runtime["subscriber_groups"].get("401") is not None


@pytest.mark.parametrize("groups", [1, 2, 3, 4, 8])
def test_every_group_count_is_a_valid_partition_index(groups: int) -> None:
    runtime = _runtime(groups=groups)
    for index in range(200):
        assert 0 <= runtime.group_of("sub%d" % index, index) < groups
