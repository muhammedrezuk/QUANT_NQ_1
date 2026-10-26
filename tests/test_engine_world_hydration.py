# -*- coding: utf-8 -*-
"""حارس ترطيب الحالة — عمليّةٌ تُقلع متأخّرةً تأخذ صورة العالم، بلا أوامر.

٢٠٢٦-٠٩-١٨ (المقيس على النواة الحيّة): محرّكٌ يُقلع لا يعرف شيئًا عمّا مضى،
فيحكم على عالمٍ فارغ. عيّنة NTP لم تصله ⟵ 153 أمرًا مرفوضًا بـ
`CLOCK_NOT_SYNCED`؛ و`platform.terminal_state` لم تصله — لا نقطة قبل
`state` فليست قابلة للإعادة بحكم النواة — فبقيت `_alive` فارغةً في الذرّة
519 ⟵ `system_alive=False` ⟵ 171 حجبًا بـ`SYSTEM_NOT_ALIVE`.
"""
from __future__ import annotations

import pytest

from engine import NQEngine
from transport.owned_event_bus import OwnedEventBus


class _Router:
    """موجّهٌ صوريّ: يقبل كلّ شيء ويعدّه — يكفي لاختبار ما يُحفظ."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, dict]] = []
        self.engines = [object()]

    def dispatch(self, event_name: str, body):  # noqa: ANN001
        self.seen.append((event_name, body))
        return True

    def stats(self):
        return {"routed": len(self.seen)}


@pytest.mark.asyncio
async def test_world_keeps_the_newest_payload_per_event() -> None:
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1))
    engine.symbol_router = _Router()
    await engine.publish("platform.terminal_state",
                         {"account_id": "A", "connected": False}, publisher="619")
    await engine.publish("platform.terminal_state",
                         {"account_id": "A", "connected": True}, publisher="619")
    await engine.drain()
    world = dict(engine.world_snapshot())
    assert world["platform.terminal_state"]["connected"] is True, "بقيت الحمولة القديمة"
    await engine.close()


@pytest.mark.asyncio
async def test_a_non_replayable_state_is_still_kept() -> None:
    """هذا هو بيت القصيد: `terminal_state` لا تنتهي بـ`.state` بنقطة."""
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1))
    engine.symbol_router = _Router()
    await engine.publish("platform.terminal_state", {"account_id": "A"}, publisher="619")
    await engine.drain()
    names = {name for name, _ in engine.world_snapshot()}
    assert "platform.terminal_state" in names
    # ولا تظهر في `last_states` — فالفرق بين الاثنتين هو سبب وجود الصورة
    assert "platform.terminal_state" not in dict(engine.last_states())
    await engine.close()


@pytest.mark.asyncio
async def test_commands_are_never_kept_nor_replayed() -> None:
    """إعادة أمرٍ على عمليّةٍ تُقلع = تنفيذٌ مكرّر. الحدّ من النواة لا من قائمة."""
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1))
    engine.symbol_router = _Router()
    for name in ("execution.order.built", "trading.final_decision",
                 "risk.asset.command", "execution.order.submit.state",
                 "decision.buy.state", "bridge.send.state"):
        await engine.publish(name, {"symbol": "XAUUSD"}, publisher="552")
    await engine.publish("platform.account.state", {"balance": 1000.0}, publisher="619")
    await engine.drain()
    names = {n for n, _ in engine.world_snapshot()}
    assert names == {"platform.account.state"}, names
    await engine.close()


@pytest.mark.asyncio
async def test_the_world_is_bounded() -> None:
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1))
    engine.symbol_router = _Router()
    engine.world_max = 16
    for index in range(200):
        await engine.publish("e%d.state" % index, {"n": index}, publisher="101")
    await engine.drain()
    assert len(engine.world_snapshot()) <= 16
    await engine.close()


@pytest.mark.asyncio
async def test_nothing_is_kept_when_no_router_exists() -> None:
    """بلا محرّكات لا صورة — ولا كلفة على النواة المفردة."""
    engine = NQEngine(cold_bus=OwnedEventBus(worker_count=1))
    await engine.publish("platform.account.state", {"balance": 1.0}, publisher="619")
    await engine.drain()
    assert engine.world_snapshot() == []
    await engine.close()
