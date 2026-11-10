# -*- coding: utf-8 -*-
"""حارس المدخل المباشر — المجدول خارج مسار التِكّة، والملكيّة محفوظة.

المقيس ٢٠٢٦-٠٩-١٨: السلسلة داخل المحرّك تنتهي في 20–30 مِلّي ثانية، وp99
تِكّة←قرار = 1.0189 ث. فالفارق انتظارُ النطاق دوره في `ScopeScheduler`، لا
حسابٌ ولا نقل. وهو تأخيرٌ لا يظهر بوصفه `backlog`: الطابور صفرٌ عند العيّنة.
"""
from __future__ import annotations

import asyncio

import pytest

from engine import NQEngine
from transport.owned_event_bus import OwnedEventBus


def _engine(**kw) -> NQEngine:
    return NQEngine(cold_bus=OwnedEventBus(worker_count=1), **kw)


@pytest.mark.asyncio
async def test_a_tick_runs_inside_publish_not_after_it() -> None:
    """الدليل المباشر: المشترِك يكون قد عمل قبل أن يعود `publish`."""
    engine = _engine(hot_direct=True)
    seen: list[int] = []

    async def handler(payload: dict) -> None:
        seen.append(payload["n"])

    engine.subscribe("market.tick", handler, subscriber="613")
    await engine.publish("market.tick", {"symbol": "XAUUSD", "n": 1}, publisher="613")
    assert seen == [1], "الدورة لم تُدَر داخل النشر — ما زال المجدول في الطريق"
    stats = engine.transport_stats()["engine"]
    assert stats["direct_cycles"] == 1
    assert stats["queued_because_busy"] == 0
    await engine.close()


@pytest.mark.asyncio
async def test_the_scheduler_path_is_the_previous_behaviour_letter_for_letter() -> None:
    engine = _engine(hot_direct=False)
    seen: list[int] = []

    async def handler(payload: dict) -> None:
        seen.append(payload["n"])

    engine.subscribe("market.tick", handler, subscriber="613")
    await engine.publish("market.tick", {"symbol": "XAUUSD", "n": 1}, publisher="613")
    assert seen == [], "بلا المدخل المباشر لا تُدار الدورة داخل النشر"
    await engine.drain()
    assert seen == [1]
    assert engine.transport_stats()["engine"]["direct_cycles"] == 0
    await engine.close()


@pytest.mark.asyncio
async def test_one_owner_per_scope_two_cycles_never_overlap() -> None:
    """§٣ ملكيّة واحدة: تِكّتان لرمزٍ واحد لا تتداخل دورتاهما."""
    engine = _engine(hot_direct=True)
    inside = 0
    overlap = 0
    order: list[int] = []

    async def handler(payload: dict) -> None:
        nonlocal inside, overlap
        inside += 1
        if inside > 1:
            overlap += 1
        await asyncio.sleep(0.01)
        order.append(payload["n"])
        inside -= 1

    engine.subscribe("market.tick", handler, subscriber="613")
    await asyncio.gather(*[
        engine.publish("market.tick", {"symbol": "XAUUSD", "n": n}, publisher="613")
        for n in range(5)])
    await engine.drain()
    assert overlap == 0, "دورتان تداخلتا على النطاق نفسه"
    assert sorted(order) == [0, 1, 2, 3, 4], order
    assert order == sorted(order), "الترتيب داخل النطاق انكسر: %s" % order
    stats = engine.transport_stats()["engine"]
    assert stats["queued_because_busy"] >= 1, "لم يُودَع شيءٌ رغم انشغال النطاق"
    await engine.close()


@pytest.mark.asyncio
async def test_two_symbols_do_not_block_each_other() -> None:
    engine = _engine(hot_direct=True)
    seen: list[str] = []

    async def handler(payload: dict) -> None:
        await asyncio.sleep(0.01)
        seen.append(payload["symbol"])

    engine.subscribe("market.tick", handler, subscriber="613")
    await asyncio.gather(
        engine.publish("market.tick", {"symbol": "XAUUSD", "n": 1}, publisher="613"),
        engine.publish("market.tick", {"symbol": "BTCUSD", "n": 1}, publisher="613"))
    assert sorted(seen) == ["BTCUSD", "XAUUSD"]
    assert engine.transport_stats()["engine"]["direct_cycles"] == 2
    await engine.close()


@pytest.mark.asyncio
async def test_a_downstream_publish_still_joins_the_running_cycle() -> None:
    """المدخل المباشر لا يكسر الدورة: ما يُنشَر داخلها يبقى فيها."""
    engine = _engine(hot_direct=True)
    depth: list[str] = []

    async def first(payload: dict) -> None:
        depth.append("first")
        await engine.publish("analysis.x.state",
                             {"symbol": payload.get("symbol")}, publisher="101")

    async def second(payload: dict) -> None:
        depth.append("second")

    engine.subscribe("market.tick", first, subscriber="101")
    # مشترِكٌ خارج نطاق الإيقاع (١٥٠–٤٩٩): وإلّا أجّله المحرّك إلى حزمة
    # الإيقاع — وهو سلوكٌ سابقٌ صحيح لا علاقة له بالمدخل المباشر.
    engine.subscribe("analysis.x.state", second, subscriber="601")
    await engine.publish("market.tick", {"symbol": "XAUUSD"}, publisher="613")
    assert depth == ["first", "second"], depth
    assert engine.transport_stats()["engine"]["direct_cycles"] == 1, "ولّد دورةً ثانية"
    await engine.close()


@pytest.mark.asyncio
async def test_direct_entry_never_coalesces_money() -> None:
    """المدخل المباشر يجمع أحداثًا أكثر في الدورة الواحدة — فيزيد الدمج على
    الحالات (وهو العقد §١٦: الأحدث يكفي). وهذا الحارس يثبت أنّ الفعل الماليّ
    خارج ذلك: أمرٌ مكرّرٌ حرفيًّا يصل مرّتين ولا يُدمَج أبدًا."""
    engine = _engine(hot_direct=True)
    orders: list[dict] = []
    states: list[int] = []

    async def on_order(payload: dict) -> None:
        orders.append(dict(payload))

    async def on_state(payload: dict) -> None:
        states.append(payload["n"])

    engine.subscribe("execution.order.built", on_order, subscriber="601")
    engine.subscribe("analysis.x.state", on_state, subscriber="601")

    async def burst(payload: dict) -> None:
        for n in range(3):
            await engine.publish("execution.order.built",
                                 {"symbol": "XAUUSD", "lot": 0.5}, publisher="552")
            await engine.publish("analysis.x.state",
                                 {"symbol": "XAUUSD", "n": n}, publisher="101")

    engine.subscribe("market.tick", burst, subscriber="613")
    await engine.publish("market.tick", {"symbol": "XAUUSD"}, publisher="613")
    await engine.drain()

    assert len(orders) == 3, "أمرٌ ابتُلع بالدمج — عطلٌ ماليّ: %d" % len(orders)
    assert states and states[-1] == 2, states
    await engine.close()
