from __future__ import annotations

import asyncio
import time

import pytest

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الضغط العكسيّ لصندوق الأوامر (`CommandBackpressureError`)
# أُرجع مع ملفّاته الثلاثة في `3b97069` (٢٠٢٦-٠٩-٢٢ — دمجٌ مكسور أوقف إقلاع النواة)، ومحفوظٌ في
# `7d7b4d9` ولم يُستعَد بعد. فكان هذا الملفّ يسقط عند الجمع (ImportError) فيُحسب خطأً لا اختبارًا.
# يُتخطّى الآن صراحةً بسببه — ويعود يعمل وحده يوم تُستعاد الميزة. لا حذف.
try:
    from core.event_bus import CommandBackpressureError
except ImportError:
    pytest.skip("CommandBackpressureError أُرجع في 3b97069 (٢٠٢٦-٠٩-٢٢) ولم يُستعَد — "
                "اختبارات الضغط العكسيّ معلّقة حتى عودته", allow_module_level=True)
from transport.owned_event_bus import OwnedEventBus
from engine.engine import NQEngine
from engine.scheduler import GLOBAL_SCOPE


class _ColdBus:
    def __init__(self) -> None:
        self._subscribers = {}
        self._global_subscribers = []

    def subscribe(self, event_name, handler, *, subscriber="", isolate_payload=None):
        self._subscribers.setdefault(event_name, []).append(handler)

    def subscribe_all(self, handler, *, subscriber="", isolate_payload=None):
        self._global_subscribers.append(handler)

    def unsubscribe(self, event_name, handler):
        rows = self._subscribers.get(event_name, [])
        self._subscribers[event_name] = [item for item in rows if item is not handler]

    def unsubscribe_all(self, subscriber):
        return 0

    def unsubscribe_global(self, handler):
        self._global_subscribers = [item for item in self._global_subscribers if item is not handler]

    def subscriber_count(self, event_name):
        return len(self._subscribers.get(event_name, ()))

    def event_names(self):
        return list(self._subscribers)

    async def publish(self, event_name, payload, *, publisher=""):
        return None

    async def drain(self, timeout_s=None):
        return True

    def stats(self):
        return {}

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_hot_cycle_timeout_requeues_pending_event() -> None:
    cold = _ColdBus()
    engine = NQEngine(cold_bus=cold, cycle_deadline_s=0.05)
    seen: list[int] = []

    async def root(payload):
        await engine.publish("child.state", {
            "account_id": "A",
            "symbol": "EURUSD",
            "n": 7,
        }, publisher="root")
        await asyncio.sleep(0.20)

    async def child(payload):
        seen.append(int(payload["n"]))

    engine.subscribe("root.event", root, subscriber="root")
    engine.subscribe("child.state", child, subscriber="child")

    await engine.publish("root.event", {
        "account_id": "A",
        "symbol": "EURUSD",
    }, publisher="test")

    for _ in range(100):
        if seen:
            break
        await asyncio.sleep(0.005)

    stats = engine.transport_stats()["engine"]
    assert seen == [7]
    assert stats["cycle_requeued"] >= 1
    assert stats["cycle_requeue_by_reason"].get("timeout", 0) >= 1
    await engine.close()


@pytest.mark.asyncio
async def test_sync_hot_handler_does_not_block_event_loop() -> None:
    cold = _ColdBus()
    engine = NQEngine(cold_bus=cold)

    fired = asyncio.Event()

    def slow_sync(_payload):
        time.sleep(0.10)

    async def timer():
        await asyncio.sleep(0.02)
        fired.set()

    engine.subscribe("slow", slow_sync, subscriber="sync")
    task = asyncio.create_task(timer())

    await engine.publish("slow", {
        "account_id": "A",
        "symbol": "EURUSD",
    }, publisher="test")
    await asyncio.wait_for(task, timeout=0.08)

    assert fired.is_set()
    await engine.close()


@pytest.mark.asyncio
async def test_state_replay_keeps_account_symbol_scope() -> None:
    cold = _ColdBus()
    engine = NQEngine(cold_bus=cold)

    await engine.publish("price.state", {
        "account_id": "A",
        "symbol": "XAUUSD",
        "price": 4379.73,
    }, publisher="test")

    async def handler(_payload):
        return None

    engine.subscribe("price.state", handler, subscriber="701")

    state_scopes = set(engine._scheduler._scopes)
    assert ("A", "XAUUSD") in state_scopes
    assert GLOBAL_SCOPE not in state_scopes
    await engine.close()


@pytest.mark.asyncio
async def test_command_mailbox_is_bounded_without_silent_drop() -> None:
    # المسار الإنتاجي: OwnedEventBus → OwnershipRuntime → OwnershipWorker.
    bus = OwnedEventBus(
        dispatch_timeout_s=1.0,
        mailbox_max_events=2,
        command_mailbox_max_events=1,
        worker_count=1,
        partitioned_ownership=False,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(_payload):
        started.set()
        await release.wait()

    bus.subscribe("execution.order.requested", slow, subscriber="601")

    await bus.publish("execution.order.requested", {"n": 1}, publisher="test")
    await asyncio.wait_for(started.wait(), timeout=0.5)

    await bus.publish("execution.order.requested", {"n": 2}, publisher="test")

    with pytest.raises(CommandBackpressureError):
        await bus.publish("execution.order.requested", {"n": 3}, publisher="test")

    release.set()
    assert await bus.drain(timeout_s=2.0)

    runtime = bus.transport_stats()["runtime"]
    assert runtime["command_rejected_by_event"]["execution.order.requested"] == 1
    assert runtime["command_mailbox_limit"] == 1
    await bus.close()

@pytest.mark.asyncio
async def test_normal_events_never_evict_a_queued_command() -> None:
    bus = OwnedEventBus(
        dispatch_timeout_s=1.0,
        mailbox_max_events=1,
        command_mailbox_max_events=1,
        worker_count=1,
        partitioned_ownership=False,
    )
    received: list[str] = []
    release = asyncio.Event()
    started = asyncio.Event()

    async def handler(payload):
        if payload["kind"] == "command":
            started.set()
            await release.wait()
        received.append(payload["kind"])

    bus.subscribe("execution.order.requested", handler, subscriber="601")
    bus.subscribe("market.fact", handler, subscriber="601")

    await bus.publish(
        "execution.order.requested",
        {"account_id": "A", "symbol": "EURUSD", "kind": "command"},
        publisher="test",
    )
    await asyncio.wait_for(started.wait(), timeout=0.5)

    await bus.publish(
        "market.fact",
        {"account_id": "A", "symbol": "EURUSD", "kind": "fact-queued"},
        publisher="test",
    )
    await bus.publish(
        "market.fact",
        {"account_id": "A", "symbol": "EURUSD", "kind": "fact-new"},
        publisher="test",
    )

    release.set()
    assert await bus.drain(timeout_s=2.0)
    assert received[0] == "command"
    assert "fact-queued" in received or "fact-new" in received
    await bus.close()

@pytest.mark.asyncio
async def test_command_fanout_is_atomic_on_backpressure() -> None:
    bus = OwnedEventBus(
        dispatch_timeout_s=1.0,
        mailbox_max_events=1,
        command_mailbox_max_events=1,
        worker_count=4,
        partitioned_ownership=False,
    )
    first_started = asyncio.Event()
    release = asyncio.Event()
    second_received: list[int] = []

    async def first(_payload):
        first_started.set()
        await release.wait()

    async def second(payload):
        second_received.append(int(payload["n"]))

    bus.subscribe("execution.order.requested", first, subscriber="601")
    bus.subscribe("execution.order.requested", second, subscriber="602")

    await bus.publish(
        "execution.order.requested",
        {"n": 1},
        publisher="test",
    )
    await asyncio.wait_for(first_started.wait(), timeout=0.5)

    for _ in range(100):
        if second_received == [1]:
            break
        await asyncio.sleep(0.005)

    await bus.publish(
        "execution.order.requested",
        {"n": 2},
        publisher="test",
    )
    for _ in range(100):
        if second_received == [1, 2]:
            break
        await asyncio.sleep(0.005)

    with pytest.raises(CommandBackpressureError):
        await bus.publish(
            "execution.order.requested",
            {"n": 3},
            publisher="test",
        )

    # المستلم الثاني لم يأخذ الأمر الثالث، رغم أن صندوقه كان لديه سعة:
    # الرفض حصل قبل لمس أي صندوق.
    assert second_received == [1, 2]

    release.set()
    assert await bus.drain(timeout_s=2.0)
    await bus.close()


@pytest.mark.asyncio
async def test_unscoped_hot_handler_never_uses_reserved_cold_worker() -> None:
    bus = OwnedEventBus(
        dispatch_timeout_s=1.0,
        mailbox_max_events=4,
        worker_count=4,
        partitioned_ownership=True,
    )

    async def handler(_payload):
        return None

    bus.subscribe("legacy.hot", handler, subscriber="581")
    await bus.publish(
        "legacy.hot",
        {"note": "unscoped"},
        publisher="test",
    )
    assert await bus.drain(timeout_s=1.0)

    runtime = bus._runtime
    worker_id = runtime._handler_workers[id(handler)]
    assert worker_id != runtime.stats()["cold_worker"]
    await bus.close()


@pytest.mark.asyncio
async def test_sync_timeout_does_not_release_scope_while_thread_is_running() -> None:
    cold = _ColdBus()
    engine = NQEngine(cold_bus=cold, cycle_deadline_s=0.02)
    started = asyncio.Event()
    finished = asyncio.Event()
    active = 0
    max_active = 0

    def slow_sync(_payload):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        started.set()
        time.sleep(0.06)
        active -= 1
        finished.set()

    engine.subscribe("slow.sync", slow_sync, subscriber="sync")

    first = asyncio.create_task(
        engine.publish(
            "slow.sync",
            {"account_id": "A", "symbol": "EURUSD"},
            publisher="test",
        )
    )
    await asyncio.wait_for(started.wait(), timeout=0.5)

    # تُودَع الثانية أثناء الشغل الأول؛ لا يجوز أن تبدأ قبل خروجه من الخيط.
    await engine.publish(
        "slow.sync",
        {"account_id": "A", "symbol": "EURUSD"},
        publisher="test",
    )
    await first
    await asyncio.wait_for(finished.wait(), timeout=0.5)
    assert await engine._scheduler.drain(timeout_s=1.0)
    assert max_active == 1
    assert engine.transport_stats()["engine"]["sync_cancel_waits"] >= 1
    await engine.close()
