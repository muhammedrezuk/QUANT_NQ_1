from __future__ import annotations

import pytest

from transport.owned_event_bus import OwnedEventBus
from transport.ownership import OwnershipKey


@pytest.mark.asyncio
async def test_shared_readonly_payload_is_one_object_for_default_consumers() -> None:
    bus = OwnedEventBus(payload_mode="shared_readonly")
    seen: list[int] = []
    identities: list[int] = []

    async def first(payload: dict) -> None:
        identities.append(id(payload))
        seen.append(payload["nested"]["value"])

    async def second(payload: dict) -> None:
        identities.append(id(payload))
        seen.append(payload["nested"]["value"])

    bus.subscribe("market.tick", first, subscriber="one")
    bus.subscribe("market.tick", second, subscriber="two")
    await bus.publish("market.tick", {"nested": {"value": 7}})
    assert await bus.drain(timeout_s=2.0)

    assert seen == [7, 7]
    assert identities[0] == identities[1]
    assert bus.transport_stats()["shared_deliveries"] == 2
    assert bus.transport_stats()["private_deliveries"] == 0


@pytest.mark.asyncio
async def test_shared_payload_rejects_mutation_instead_of_cross_consumer_corruption() -> None:
    bus = OwnedEventBus(payload_mode="shared_readonly")
    errors: list[type[BaseException]] = []
    seen: list[int] = []

    async def writer(payload: dict) -> None:
        with pytest.raises(TypeError) as caught:
            payload["nested"]["value"] = 0
        errors.append(type(caught.value))

    async def reader(payload: dict) -> None:
        seen.append(payload["nested"]["value"])

    bus.subscribe("e", writer, subscriber="writer")
    bus.subscribe("e", reader, subscriber="reader")
    await bus.publish("e", {"nested": {"value": 9}})
    assert await bus.drain(timeout_s=2.0)

    assert errors == [TypeError]
    assert seen == [9]


@pytest.mark.asyncio
async def test_explicit_private_subscription_keeps_legacy_isolation() -> None:
    bus = OwnedEventBus(payload_mode="shared_readonly")
    seen: list[int] = []

    async def writer(payload: dict) -> None:
        payload["nested"]["value"] = 0

    async def reader(payload: dict) -> None:
        seen.append(payload["nested"]["value"])

    bus.subscribe("e", writer, subscriber="writer", isolate_payload=True)
    bus.subscribe("e", reader, subscriber="reader")
    await bus.publish("e", {"nested": {"value": 9}})
    assert await bus.drain(timeout_s=2.0)

    assert seen == [9]
    assert bus.transport_stats()["private_deliveries"] == 1

@pytest.mark.asyncio
async def test_account_symbol_events_keep_order_on_one_owner_lane() -> None:
    bus = OwnedEventBus(worker_count=4)
    seen: list[int] = []

    async def reader(payload: dict) -> None:
        seen.append(payload["sequence"])

    bus.subscribe("market.tick", reader, subscriber="partition-reader")
    for sequence in range(20):
        await bus.publish(
            "market.tick",
            {"account_id": "A", "symbol": "NQ", "sequence": sequence},
        )
    assert await bus.drain(timeout_s=2.0)

    assert seen == list(range(20))
    runtime = bus.transport_stats()["runtime"]
    # المفتاح يُشتقّ من مصدره لا يُكتب حرفيًّا: كان `A×NQ` مثبَّتًا هنا،
    # فكسره تغييرُ الفاصل إلى ASCII (وصل اللوحة `52992818ÃUSTEC` مشوّهًا).
    # اختبارٌ يكرّر ثابتًا يوثّق نسخةً منه لا يحرسه.
    owner_key = OwnershipKey("A", "NQ").text
    assert runtime["ownership"] == {owner_key: runtime["ownership"][owner_key]}
    assert sum(row["processed"] for row in runtime["workers"]) == 20
