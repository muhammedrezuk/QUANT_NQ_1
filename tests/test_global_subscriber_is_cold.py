"""المشترِك العامّ باردٌ بالبنية · والفقد يُصنَّف بالمسار (§٤ · §٦ · §٨).

**ورقة المالك ٢٠٢٦-٠٩-١٠:**

    §٤ «أي مشترك يستخدم `subscribe_all` ولا يملك نطاقًا محددًا:
        DEFAULT = COLD. لا يجوز لمشترك عام أن يدخل المسار الساخن.»

    §٦ «نقسم العدادات… لا يوجد عداد شامل يخفي نوع الفقد.»

    §٨ «القاعدة لا تكون `if atom_id in [1, 810]` بل
        `subscriber role = monitoring/supervision → cold`.»

## ⛔ القياس الذي فرض القاعدة

ثلاثة مشترِكين عامّين ابتلعوا **76% من كلّ الإسقاط** على النواة الحيّة:

    الذرّة 1        806.5 إسقاطًا/ث
    الذرّة 810      803.7/ث
    api.websocket   801.5/ث
    ─────────────────────────────
                    2,412 من 3,160/ث

ومشترِكٌ عامّ يرى **كلّ** حدث (2,703/ث) ولا يلحق، فيفيض صندوقه ويُسقط —
وهو جالسٌ على مسار السوق يزاحم التِكّة.

## والتصنيف بالبنية لا بقائمة

الفقد يُنسب **بالمسار**: ما سقط على مسارٍ ساخن فقدُ سوق، وما سقط على
البارد فقدُ لوحةٍ أو قياسٍ أو تخزين. لا اسم في الكود ولا نطاق مفترض.
"""

from __future__ import annotations

import asyncio

import pytest

from transport.owned_event_bus import OwnedEventBus


async def _noop(*_args) -> None:  # noqa: ANN002
    return None


# ── §٤ · §٨ — العامّ باردٌ افتراضًا ─────────────────────────────────────

def test_a_global_subscriber_is_cold_without_naming_it() -> None:
    """لا `if atom_id in [1, 810]` — القاعدة بنيويّة."""
    bus = OwnedEventBus()

    async def supervisor(_name: str, _payload: dict) -> None:
        return None

    bus.subscribe_all(supervisor, subscriber="810")
    assert id(supervisor) in bus._cold_handlers, (
        "مشترِكٌ عامّ بقي على المسار الساخن")


@pytest.mark.parametrize("subscriber", ["1", "810", "api.websocket", "", "أيّ-شيء"])
def test_every_global_subscriber_is_cold_regardless_of_name(subscriber: str) -> None:
    bus = OwnedEventBus()

    async def watcher(_name: str, _payload: dict) -> None:
        return None

    bus.subscribe_all(watcher, subscriber=subscriber)
    assert id(watcher) in bus._cold_handlers, subscriber


def test_a_declared_hot_scope_is_the_only_way_back_to_the_hot_lane() -> None:
    """من يحتاج المسار الساخن يعلن نطاقه — ولا استثناء صامت."""
    bus = OwnedEventBus()

    async def special(_name: str, _payload: dict) -> None:
        return None

    bus.subscribe_all(special, subscriber="خاصّة", hot_scope="52992818|USTEC")
    assert id(special) not in bus._cold_handlers
    assert bus.transport_stats()["declared_hot_globals"] == {
        "خاصّة": "52992818|USTEC"}


def test_no_declared_exception_by_default() -> None:
    """القائمة فارغة دائمًا ما لم يُعلن أحد — فارغةٌ = لا استثناء."""
    assert OwnedEventBus().transport_stats()["declared_hot_globals"] == {}


def test_a_scoped_subscribe_stays_hot() -> None:
    """§٤ تخصّ العامّ وحده — المشترِك المحدّد النطاق يبقى ساخنًا."""
    bus = OwnedEventBus()

    async def analyser(_payload: dict) -> None:
        return None

    bus.subscribe("market_data.cleaned", analyser, subscriber="151")
    assert id(analyser) not in bus._cold_handlers


# ── §٦ — الفقد مصنَّف بالمسار ───────────────────────────────────────────

def test_loss_counters_are_split_by_lane_not_by_a_name_list() -> None:
    async def run() -> dict:
        bus = OwnedEventBus(worker_count=3)

        async def watcher(_name: str, _payload: dict) -> None:
            return None

        async def analyser(_payload: dict) -> None:
            return None

        bus.subscribe_all(watcher, subscriber="810")
        bus.subscribe("market_data.cleaned", analyser, subscriber="151")
        await bus.publish("market_data.cleaned", {"symbol": "USTEC"}, publisher="t")
        await bus.drain(timeout_s=10.0)
        stats = bus.transport_stats()["runtime"]
        await bus.close()
        return stats

    runtime = asyncio.run(run())
    for field in ("market_dropped", "cold_dropped",
                  "market_coalesced", "cold_coalesced"):
        assert field in runtime, field
    assert runtime["market_dropped"] == 0
    assert runtime["cold_dropped"] == 0


def test_every_worker_declares_its_lane() -> None:
    """المسار يُعلَن في كلّ عامل — التصنيف يُقرأ لا يُستنتج."""
    async def run() -> list:
        bus = OwnedEventBus(worker_count=4)
        stats = bus.transport_stats()["runtime"]["workers"]
        await bus.close()
        return stats

    workers = asyncio.run(run())
    lanes = [w["lane"] for w in workers]
    assert lanes.count("cold") == 1, "المسار البارد ليس واحدًا: %s" % lanes
    assert lanes.count("hot") == len(workers) - 1
    assert lanes[-1] == "cold", "المسار البارد ليس الأخير"


def test_the_drop_split_never_double_counts() -> None:
    """المجموع المصنَّف = المجموع الخام. تصنيفٌ يزيد أو ينقص يكذب."""
    async def run() -> tuple[int, int, int]:
        bus = OwnedEventBus(worker_count=3)
        runtime = bus.transport_stats()["runtime"]
        total = sum(int(w["dropped"]) for w in runtime["workers"])
        await bus.close()
        return total, runtime["market_dropped"], runtime["cold_dropped"]

    total, market, cold = asyncio.run(run())
    assert market + cold == total


def test_the_subscriber_breakdown_survives_aggregation() -> None:
    """§٦ — الاسم يبقى مع الرقم، وإلّا صار الفقد مجهول الصاحب."""
    async def run() -> dict:
        bus = OwnedEventBus(worker_count=3)
        runtime = bus.transport_stats()["runtime"]
        await bus.close()
        return runtime

    assert "dropped_by_subscriber" in asyncio.run(run())
