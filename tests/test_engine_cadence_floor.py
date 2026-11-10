# -*- coding: utf-8 -*-
"""حرّاس أرضيّة الإيقاع — التحليل يبطؤ، والمال لا يبطؤ، ولا شيء يسقط."""
from __future__ import annotations

import asyncio
import time

import pytest

from engine import NQEngine
from transport.owned_event_bus import OwnedEventBus


@pytest.mark.asyncio
async def test_zero_floor_is_the_previous_behaviour_letter_for_letter() -> None:
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1), cadence_min_interval_s=0.0)
    seen: list[int] = []

    async def handler(payload: dict) -> None:
        seen.append(payload["n"])

    engine.subscribe("analysis.x.state", handler, subscriber="301")
    for n in range(5):
        await engine.publish("analysis.x.state", {"symbol": "XAUUSD", "n": n}, publisher="101")
        await engine.drain()
    assert seen == [0, 1, 2, 3, 4]
    sch = engine.transport_stats()["engine"]["scheduler"]
    assert sch["cadence_deferred"] == 0
    await engine.close()


@pytest.mark.asyncio
async def test_floor_coalesces_and_delivers_the_newest_never_the_stale() -> None:
    """الأرضيّة لا تُسقط — تؤجّل. وما يصل هو **الأحدث** لا الأوّل."""
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1), cadence_min_interval_s=0.25)
    seen: list[int] = []

    async def handler(payload: dict) -> None:
        seen.append(payload["n"])

    engine.subscribe("analysis.x.state", handler, subscriber="301")
    for n in range(40):
        await engine.publish("analysis.x.state", {"symbol": "XAUUSD", "n": n}, publisher="101")
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.6)

    assert seen, "لم يصل شيء — الأرضيّة ابتلعت الحزمة"
    # أقلّ بكثيرٍ من أربعين: هذا هو المكسب كلّه
    assert len(seen) <= 6, seen
    # وآخر ما وصل هو آخر ما نُشر — لا قيمةً قديمة
    assert seen[-1] == 39, seen
    assert seen == sorted(seen), "وصل بترتيبٍ مقلوب"
    sch = engine.transport_stats()["engine"]["scheduler"]
    assert sch["cadence_deferred"] > 0
    assert sch["coalesced"] >= 30
    await engine.close()


@pytest.mark.asyncio
async def test_floor_never_slows_the_money_path() -> None:
    """`every` (التنفيذ والبنية والساعة) بلا أرضيّة — يصل كلّه وفورًا."""
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1), cadence_min_interval_s=0.5)
    orders: list[int] = []

    async def on_order(payload: dict) -> None:
        orders.append(payload["n"])

    # مشترِكٌ خارج نطاق الإيقاع ⟵ مسار `every`
    engine.subscribe("execution.order.built", on_order, subscriber="601")
    started = time.perf_counter()
    for n in range(12):
        await engine.publish("execution.order.built",
                             {"symbol": "XAUUSD", "n": n}, publisher="552")
    await engine.drain()
    elapsed = time.perf_counter() - started
    assert orders == list(range(12)), orders
    assert elapsed < 0.4, "مسار المال تأخّر بأرضيّةٍ ليست له: %.3f ث" % elapsed
    await engine.close()


@pytest.mark.asyncio
async def test_money_and_analysis_share_a_scope_without_blocking_each_other() -> None:
    """رمزٌ واحد، مساران: التحليل مؤجَّل والتنفيذ فوريّ في النطاق نفسه."""
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1), cadence_min_interval_s=0.3)
    analysis: list[int] = []
    orders: list[int] = []

    async def on_analysis(payload: dict) -> None:
        analysis.append(payload["n"])

    async def on_order(payload: dict) -> None:
        orders.append(payload["n"])

    engine.subscribe("analysis.x.state", on_analysis, subscriber="301")
    engine.subscribe("execution.order.built", on_order, subscriber="601")
    for n in range(20):
        await engine.publish("analysis.x.state", {"symbol": "XAUUSD", "n": n}, publisher="101")
        await engine.publish("execution.order.built", {"symbol": "XAUUSD", "n": n}, publisher="552")
        await asyncio.sleep(0.005)
    await engine.drain()
    await asyncio.sleep(0.4)
    assert orders == list(range(20)), "أمرٌ ضاع أو تأخّر خلف التحليل"
    assert len(analysis) < 20, analysis
    assert analysis[-1] == 19, analysis
    await engine.close()
