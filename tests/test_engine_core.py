# -*- coding: utf-8 -*-
"""حرّاس NQ ENGINE — كلّ حارس يثبت سلوكًا واحدًا بالرقم.

الناقل البارد هنا `OwnedEventBus` حقيقيّ (لا محاكاة) كي يُقاس الوصل نفسه
الذي يعمل في التشغيل — درس «فحصتُ المكوّن ولم أفحص الوصل».
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from engine import GLOBAL_SCOPE, NQEngine
from transport.owned_event_bus import OwnedEventBus


def make_engine(**kwargs: Any) -> NQEngine:
    cold = OwnedEventBus(worker_count=2, cold_sections=[[700, 749]])
    defaults = dict(cold_bus=cold, cadence_sections=[[150, 499]],
                    cold_sections=[[700, 749]], cycle_deadline_s=2.0, max_depth=64)
    defaults.update(kwargs)
    return NQEngine(**defaults)


class Recorder:
    def __init__(self) -> None:
        self.seen: list[tuple[str, dict]] = []

    def handler_for(self, name: str):
        async def _on(payload: dict) -> None:
            self.seen.append((name, dict(payload)))
        return _on


@pytest.mark.asyncio
async def test_hot_delivery_in_subscription_order_and_counted() -> None:
    engine = make_engine()
    rec = Recorder()
    engine.subscribe("market.tick", rec.handler_for("a"), subscriber="101")
    engine.subscribe("market.tick", rec.handler_for("b"), subscriber="112")
    await engine.publish("market.tick", {"symbol": "XAUUSD", "bid": 1.0}, publisher="613")
    assert await engine.drain(timeout_s=2.0)
    assert [name for name, _ in rec.seen] == ["a", "b"]
    assert engine.stats()["delivered"]["market.tick"] == 2
    assert engine.stats()["published"]["market.tick"] == 1
    await engine.close()


@pytest.mark.asyncio
async def test_cold_subscriber_receives_via_cold_bus() -> None:
    engine = make_engine()
    rec = Recorder()
    engine.subscribe("market.tick", rec.handler_for("store"), subscriber="707")
    engine.subscribe("market.tick", rec.handler_for("hot"), subscriber="101")
    await engine.publish("market.tick", {"symbol": "XAUUSD"}, publisher="613")
    assert await engine.drain(timeout_s=2.0)
    names = sorted(name for name, _ in rec.seen)
    assert names == ["hot", "store"]
    ts = engine.transport_stats()["engine"]
    assert ts["cold_subscriptions"] == 1 and ts["hot_subscriptions"] == 1
    assert ts["cold_mirrored"] >= 1
    await engine.close()


@pytest.mark.asyncio
async def test_cadence_subscriber_gets_latest_only_and_every_tick_gets_all() -> None:
    engine = make_engine()
    rec = Recorder()
    engine.subscribe("market.tick.validated", rec.handler_for("every"), subscriber="101")
    engine.subscribe("market.tick.validated", rec.handler_for("cadence"), subscriber="151")
    # ثلاث تِكّات للرمز نفسه قبل أن يأخذ المدخل دوره.
    for price in (1.0, 2.0, 3.0):
        await engine.publish("market.tick.validated",
                             {"symbol": "XAUUSD", "account_id": "A", "price": price},
                             publisher="112")
    assert await engine.drain(timeout_s=2.0)
    every = [p["price"] for name, p in rec.seen if name == "every"]
    cadence = [p["price"] for name, p in rec.seen if name == "cadence"]
    assert every == [1.0, 2.0, 3.0]
    assert cadence == [3.0], cadence
    sched = engine.transport_stats()["engine"]["scheduler"]
    assert sched["coalesced"] == 2
    assert sched["coalesced_by_event"]["market.tick.validated"] == 2
    await engine.close()


@pytest.mark.asyncio
async def test_cadence_isolates_symbols_and_never_coalesces_candles() -> None:
    engine = make_engine()
    rec = Recorder()
    engine.subscribe("market.tick.validated", rec.handler_for("c"), subscriber="151")
    engine.subscribe("market_data.candle_closed", rec.handler_for("candle"), subscriber="151")
    await engine.publish("market.tick.validated", {"symbol": "XAUUSD", "price": 1}, publisher="112")
    await engine.publish("market.tick.validated", {"symbol": "EURUSD", "price": 2}, publisher="112")
    await engine.publish("market_data.candle_closed", {"symbol": "XAUUSD", "tf": "M1"}, publisher="103")
    await engine.publish("market_data.candle_closed", {"symbol": "XAUUSD", "tf": "M5"}, publisher="103")
    assert await engine.drain(timeout_s=2.0)
    ticks = sorted(p["symbol"] for name, p in rec.seen if name == "c")
    candles = sorted(p["tf"] for name, p in rec.seen if name == "candle")
    assert ticks == ["EURUSD", "XAUUSD"]
    assert candles == ["M1", "M5"]
    await engine.close()


@pytest.mark.asyncio
async def test_downstream_event_runs_inside_same_cycle_and_inherits_trace() -> None:
    engine = make_engine()
    rec = Recorder()
    order: list[str] = []

    async def validator(payload: dict) -> None:
        order.append("validator")
        # حمولةٌ مشتقّة جديدة — لا نسخة من الوارد بهويّته (كما تفعل الذرّات).
        await engine.publish("market.tick.validated",
                             {"symbol": payload["symbol"], "validated": True}, publisher="112")

    async def consumer(payload: dict) -> None:
        order.append("consumer")
        rec.seen.append(("consumer", dict(payload)))

    engine.subscribe("market.tick", validator, subscriber="112")
    engine.subscribe("market.tick.validated", consumer, subscriber="101")
    await engine.publish("market.tick", {"symbol": "XAUUSD"}, publisher="613")
    assert await engine.drain(timeout_s=2.0)
    assert order == ["validator", "consumer"]
    parent = engine.stats()["published"]
    assert parent["market.tick"] == 1 and parent["market.tick.validated"] == 1
    child = rec.seen[0][1]
    assert child["parent_event"] == "market.tick"
    assert child["trace_id"]
    ts = engine.transport_stats()["engine"]
    assert ts["cycles"] == 1
    await engine.close()


@pytest.mark.asyncio
async def test_event_cycle_is_stopped_by_hop_guard_and_reported() -> None:
    engine = make_engine(max_depth=10)

    async def ping(payload: dict) -> None:
        await engine.publish("pong", {"n": payload.get("n", 0) + 1}, publisher="101")

    async def pong(payload: dict) -> None:
        await engine.publish("ping", {"n": payload.get("n", 0) + 1}, publisher="102")

    engine.subscribe("ping", ping, subscriber="101")
    engine.subscribe("pong", pong, subscriber="102")
    await engine.publish("ping", {"n": 0}, publisher="test")
    assert await engine.drain(timeout_s=2.0)
    ts = engine.transport_stats()["engine"]
    assert ts["depth_exceeded"] >= 1
    cycles = engine.graph.cycles()
    assert cycles and set(cycles[0]) >= {"ping", "pong"}
    await engine.close()


@pytest.mark.asyncio
async def test_hung_handler_is_cancelled_by_cycle_deadline_and_engine_continues() -> None:
    engine = make_engine(cycle_deadline_s=0.05)
    rec = Recorder()

    async def hung(_payload: dict) -> None:
        await asyncio.sleep(5)

    engine.subscribe("slow", hung, subscriber="160")
    engine.subscribe("fast", rec.handler_for("fast"), subscriber="101")
    await engine.publish("slow", {}, publisher="t")
    await engine.publish("fast", {}, publisher="t")
    assert await engine.drain(timeout_s=3.0)
    assert [name for name, _ in rec.seen] == ["fast"]
    assert engine.transport_stats()["engine"]["cycle_timeouts"] == 1
    assert engine.stats()["timeout"]["slow"] == 1
    # ٢٠٢٦-٠٩-٢٣: المهلة تسمّي المعلِّق — كانت `finally` تمسحه قبل الإعلان،
    # فتقول «المعلِّق ؟ على ؟» في كلّ مهلةٍ حيّة (٦٥ من ٦٥).
    assert engine.transport_stats()["engine"]["cycle_timeouts_by_subscriber"] == {"160": 1}
    await engine.close()


@pytest.mark.asyncio
async def test_handler_error_is_isolated_and_named() -> None:
    engine = make_engine()
    rec = Recorder()

    async def broken(_payload: dict) -> None:
        raise ValueError("boom")

    engine.subscribe("x", broken, subscriber="151")
    engine.subscribe("x", rec.handler_for("ok"), subscriber="101")
    await engine.publish("x", {}, publisher="t")
    assert await engine.drain(timeout_s=2.0)
    assert [name for name, _ in rec.seen] == ["ok"]
    assert engine.stats()["error"]["x"] == 1
    assert engine.transport_stats()["engine"]["error_by_subscriber"] == {"151": 1}
    await engine.close()


@pytest.mark.asyncio
async def test_state_is_replayed_to_late_subscriber_only() -> None:
    engine = make_engine()
    early, late = Recorder(), Recorder()
    engine.subscribe("platform.account.state", early.handler_for("early"), subscriber="101")
    await engine.publish("platform.account.state", {"balance": 1}, publisher="619")
    assert await engine.drain(timeout_s=2.0)
    engine.subscribe("platform.account.state", late.handler_for("late"), subscriber="151")
    assert await engine.drain(timeout_s=2.0)
    assert len(early.seen) == 1
    assert len(late.seen) == 1 and late.seen[0][1]["balance"] == 1
    assert engine.stats()["replayed"]["platform.account.state"] == 1
    await engine.close()


@pytest.mark.asyncio
async def test_unsubscribe_all_removes_hot_and_cold() -> None:
    engine = make_engine()
    rec = Recorder()
    engine.subscribe("a", rec.handler_for("a"), subscriber="101")
    engine.subscribe("b", rec.handler_for("b"), subscriber="101")
    engine.subscribe("a", rec.handler_for("store"), subscriber="707")
    assert engine.unsubscribe_all("101") == 2
    assert engine.unsubscribe_all("707") == 1
    await engine.publish("a", {}, publisher="t")
    assert await engine.drain(timeout_s=2.0)
    assert rec.seen == []
    assert engine.subscriber_count("a") == 0
    await engine.close()


@pytest.mark.asyncio
async def test_global_scope_events_are_not_deferred_for_cadence_subscribers() -> None:
    engine = make_engine()
    rec = Recorder()
    engine.subscribe("SYS_SECOND", rec.handler_for("beat"), subscriber="151")
    await engine.publish("SYS_SECOND", {"n": 1}, publisher="806")
    await engine.publish("SYS_SECOND", {"n": 2}, publisher="806")
    assert await engine.drain(timeout_s=2.0)
    assert [p["n"] for _, p in rec.seen] == [1, 2]
    await engine.close()


@pytest.mark.asyncio
async def test_publish_from_spawned_task_becomes_root_not_lost() -> None:
    engine = make_engine()
    rec = Recorder()
    spawned: list[asyncio.Task] = []

    async def later() -> None:
        await asyncio.sleep(0.01)
        await engine.publish("child", {}, publisher="101")

    async def parent(_payload: dict) -> None:
        spawned.append(asyncio.create_task(later()))

    engine.subscribe("parent", parent, subscriber="101")
    engine.subscribe("child", rec.handler_for("child"), subscriber="102")
    await engine.publish("parent", {}, publisher="t")
    await asyncio.gather(*spawned) if spawned else None
    await asyncio.sleep(0.05)
    assert await engine.drain(timeout_s=2.0)
    assert [name for name, _ in rec.seen] == ["child"]
    assert engine.transport_stats()["engine"]["cycles"] == 2
    await engine.close()


@pytest.mark.asyncio
async def test_global_subscriber_is_cold_and_sees_everything() -> None:
    engine = make_engine()
    seen: list[str] = []

    async def firehose(name: str, _payload: dict) -> None:
        seen.append(name)

    engine.subscribe_all(firehose, subscriber="api.websocket", isolate_payload=False)
    engine.subscribe("a", Recorder().handler_for("a"), subscriber="101")
    await engine.publish("a", {}, publisher="t")
    await engine.publish("b", {}, publisher="t")
    assert await engine.drain(timeout_s=2.0)
    assert sorted(seen) == ["a", "b"]
    assert engine.transport_stats()["engine"]["global_subscriptions"] == 1
    await engine.close()


@pytest.mark.asyncio
async def test_stats_shapes_match_bus_contract() -> None:
    engine = make_engine()
    stats = engine.stats()
    for key in ("published", "delivered", "no_subscribers", "timeout", "error",
                "replayed", "dropped", "coalesced", "overrun", "overrun_worst_s", "pressure"):
        assert key in stats
    ts = engine.transport_stats()
    for key in ("payload_mode", "engine", "latency", "runtime", "analysis_farm"):
        assert key in ts
    assert ts["analysis_farm"] is None
    assert "symbols" in ts["latency"]
    assert engine.seal()["sealed"] is True
    await engine.close()


@pytest.mark.asyncio
async def test_state_events_are_coalesced_inside_one_cycle() -> None:
    """آخر حالة تكفي داخل الدورة — كما في صناديق الناقل القديم.

    مُنتِجٌ ينشر ثلاث حالات متلاحقة أثناء تِكّة واحدة؛ المستهلك يرى الأخيرة
    وحدها، ويُعدّ الدمج بالاسم. بلا هذا تضاعف الشغل ٤٧٪ (مقيس على الشريط).
    """
    engine = make_engine()
    rec = Recorder()

    async def producer(_payload: dict) -> None:
        for n in (1, 2, 3):
            await engine.publish("analysis.x.state", {"symbol": "XAUUSD", "n": n}, publisher="101")

    engine.subscribe("market.tick", producer, subscriber="101")
    engine.subscribe("analysis.x.state", rec.handler_for("c"), subscriber="102")
    await engine.publish("market.tick", {"symbol": "XAUUSD"}, publisher="613")
    assert await engine.drain(timeout_s=2.0)
    assert [p["n"] for _, p in rec.seen] == [3]
    ts = engine.transport_stats()["engine"]
    assert ts["coalesced_in_cycle"] == 2
    assert engine.stats()["coalesced"]["analysis.x.state"] == 2
    await engine.close()


@pytest.mark.asyncio
async def test_wide_fanout_is_not_mistaken_for_a_loop() -> None:
    """تفرّعٌ واسع (٣٠٠ حدث من تِكّة واحدة) يمرّ كاملًا — العمق حارس الدورات لا العدد."""
    engine = make_engine(max_depth=8)
    rec = Recorder()

    async def fan(_payload: dict) -> None:
        for n in range(300):
            await engine.publish("leaf.%d" % n, {"n": n}, publisher="101")

    engine.subscribe("root", fan, subscriber="101")
    for n in range(300):
        engine.subscribe("leaf.%d" % n, rec.handler_for("leaf"), subscriber="102")
    await engine.publish("root", {}, publisher="t")
    assert await engine.drain(timeout_s=5.0)
    assert len(rec.seen) == 300
    ts = engine.transport_stats()["engine"]
    assert ts["depth_exceeded"] == 0 and ts["budget_exceeded"] == 0
    await engine.close()


@pytest.mark.asyncio
async def test_deferred_event_reaches_each_cadence_subscriber_exactly_once() -> None:
    """التأجيل مرّةٌ لكلّ حدث لا لكلّ مشترِك — وإلّا تضاعفت التسليمات تربيعيًّا.

    المقيس قبل الإصلاح: ٣ شموع × ٣٤ مشترِكًا = ١٠٢ تسليمة لكلّ مشترِك.
    """
    engine = make_engine()
    recs = [Recorder() for _ in range(3)]
    for index, rec in enumerate(recs):
        engine.subscribe("market_data.candle_closed", rec.handler_for("c%d" % index),
                         subscriber=str(151 + index))
        engine.subscribe("analysis.x.state", rec.handler_for("s%d" % index),
                         subscriber=str(151 + index))
    await engine.publish("market_data.candle_closed", {"symbol": "XAUUSD", "tf": "M1"}, publisher="103")
    await engine.publish("analysis.x.state", {"symbol": "XAUUSD", "n": 1}, publisher="101")
    assert await engine.drain(timeout_s=2.0)
    for rec in recs:
        assert len(rec.seen) == 2, [name for name, _ in rec.seen]
    sched = engine.transport_stats()["engine"]["scheduler"]
    assert sched["coalesced"] == 0
    assert sched["cadence_admitted"] == 2
    await engine.close()


@pytest.mark.asyncio
async def test_time_accounting_splits_handlers_from_transport_and_by_mode() -> None:
    engine = make_engine()

    async def busy(_payload: dict) -> None:
        # شغلٌ حقيقيّ لا نوم: النوم القصير على ويندوز قد يعود قبل أوانه أو
        # يطول تحت الحمل، والدوران على الساعة يضمن ٥ م.ث على الأقلّ حرفًا.
        started = time.perf_counter()
        while time.perf_counter() - started < 0.005:
            pass

    engine.subscribe("market.tick", busy, subscriber="101")            # كلّ تِكّة
    engine.subscribe("market.tick", busy, subscriber="151")            # إيقاع
    await engine.publish("market.tick", {"symbol": "XAUUSD"}, publisher="613")
    assert await engine.drain(timeout_s=2.0)
    ts = engine.transport_stats()["engine"]
    assert ts["handler_calls"] == 2
    # ويندوز يقرّب النوم القصير (دقّة المؤقّت ~15 م.ث) — يكفي أن يُحسب الزمن لا أن يُطابق.
    assert ts["handler_total_s"] >= 0.009
    assert ts["cycle_total_s"] >= ts["handler_total_s"]
    assert 0.0 <= ts["transport_share"] < 0.5
    assert ts["by_mode"]["every"]["cycles"] == 1 and ts["by_mode"]["cadence"]["cycles"] == 1
    assert ts["by_root"]["market.tick"]["cycles"] == 2
    await engine.close()
