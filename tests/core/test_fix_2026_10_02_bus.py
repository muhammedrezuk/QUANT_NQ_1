# -*- coding: utf-8 -*-
"""٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — إثبات إصلاحات الناقل والمحرّك واللقطة.

كلّ اختبارٍ هنا يسقط على الكود السابق وينجح على الجديد:

١ مفتاح الدمج يحمل الإطار: إطاران يُغلقان في دورة واحدة يصلان كلاهما، وتكرار
  الإطار نفسه للرمز نفسه يبقى مدموجًا.
٢ تصنيف «الأمر» بقطع الاسم الكاملة: من ٣٧٦ اسمًا حيًّا (الخريطة + `/api/bus-stats`)
  لا يتغيّر إلّا الستّة الخاطئة، ولا يفقد أمرٌ حقيقيّ صفته.
٣ المعالج الذي يحجز الحلقة فوق مهلة الدورة يُعدّ ويُسمّى (المهلة لا تقطعه).
٤ ما بقي من دورةٍ أُلغيت يعود إلى رأس طابور نطاقه بترتيبه وعمقه، و`dropped` حقيقيّ.
٥ اللقطة تُختم، والتالفة تُعزل (لا تُحذف) وتُقلع ذرّتها بلا حالة بلا استثناء.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import pytest

import engine.engine as engine_module
from core.contracts.atom import AtomBase
from core.contracts.manifest import AtomManifest
from core.event_bus import (_STATE_SUFFIXES, _TIME_SIGNAL_EVENTS, EventBus, _coalesce_key,
                            _is_command, _is_replayable)
from core import snapshot_engine as snapshot_module
from core.registry import Registry
from core.snapshot_engine import SnapshotEngine
from engine import NQEngine
from engine.engine import _CYCLE
from engine.scheduler import ScopeScheduler
from transport.owned_event_bus import OwnedEventBus

#: يُقرأ بلا استيرادٍ مسمّى كي يُجمَع الملفّ على الكود السابق أيضًا (إثبات قبل/بعد).
INTEGRITY_FIELD = getattr(snapshot_module, "INTEGRITY_FIELD", "_snapshot_sha256")


class _Errors(logging.Handler):
    """يلتقط أسطر الخطأ من مسجِّلٍ بعينه مباشرةً — لا يتّكل على انتشارها إلى الجذر."""

    def __init__(self, logger_name: str) -> None:
        super().__init__(logging.ERROR)
        self.messages: list[str] = []
        self._logger = logging.getLogger(logger_name)
        self._level = self._logger.level

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())

    def __enter__(self) -> "_Errors":
        self._logger.addHandler(self)
        self._logger.setLevel(logging.ERROR)
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._logger.removeHandler(self)
        self._logger.setLevel(self._level)


def make_engine(**kwargs: Any) -> NQEngine:
    cold = OwnedEventBus(worker_count=2, cold_sections=[[700, 749]])
    defaults = dict(cold_bus=cold, cadence_sections=[[150, 499]],
                    cold_sections=[[700, 749]], cycle_deadline_s=2.0, max_depth=64)
    defaults.update(kwargs)
    return NQEngine(**defaults)


def _old_coalesce_key(event_name: str, payload: Any) -> tuple[Any, ...]:
    """المفتاح قبل الإصلاح حرفًا — للضبط المقارن وحده."""
    if not isinstance(payload, dict):
        return (event_name,)
    return (event_name, str(payload.get("account_id") or ""), str(payload.get("symbol") or ""),
            str(payload.get("section_id") or payload.get("analyzer_id")
                or payload.get("strategy_id") or payload.get("id") or ""))


# ════════════════════════════════════════════════ ١ مفتاح الدمج والإطار ══

def test_coalesce_key_separates_timeframes_and_paths_only() -> None:
    base = {"account_id": "A", "symbol": "BTCUSD", "section_id": "150"}
    k10 = _coalesce_key("analysis.trend.state", {**base, "timeframe": "10s"})
    k1h = _coalesce_key("analysis.trend.state", {**base, "timeframe": "1h"})
    k1h_again = _coalesce_key("analysis.trend.state", {**base, "timeframe": "1h", "n": 2})
    assert k10 != k1h
    assert k1h == k1h_again
    assert (_coalesce_key("x.state", {**base, "path": "fast"})
            != _coalesce_key("x.state", {**base, "path": "slow"}))
    # بلا إطار ولا مسار: الدمج كما كان (المفتاح نفسه لحمولتين مختلفتي القيمة).
    assert _coalesce_key("x.state", {**base, "v": 1}) == _coalesce_key("x.state", {**base, "v": 2})
    # والمفتاح القديم كان يجمع الإطارين — هذا هو العيب.
    assert (_old_coalesce_key("analysis.trend.state", {**base, "timeframe": "10s"})
            == _old_coalesce_key("analysis.trend.state", {**base, "timeframe": "1h"}))


async def _two_frames_one_cycle(engine: NQEngine, consumer_id: str) -> list[tuple[str, int]]:
    seen: list[tuple[str, int]] = []

    async def producer(payload: dict) -> None:
        # تِكّةٌ تعبر حدّ الساعة والأربع ساعات: الإطاران يُغلقان معًا، والساعة
        # تُحدَّث مرّتين داخل الدورة (التكرار للإطار نفسه يبقى مدموجًا).
        for frame, n in (("1h", 1), ("4h", 1), ("1h", 2)):
            await engine.publish("analysis.trend.state",
                                 {"account_id": "A", "symbol": "BTCUSD", "section_id": "150",
                                  "timeframe": frame, "n": n}, publisher="151")

    async def consumer(payload: dict) -> None:
        seen.append((payload["timeframe"], payload["n"]))

    engine.subscribe("market.tick.validated", producer, subscriber="112")
    engine.subscribe("analysis.trend.state", consumer, subscriber=consumer_id)
    await engine.publish("market.tick.validated", {"account_id": "A", "symbol": "BTCUSD"},
                         publisher="111")
    assert await engine.drain(timeout_s=3.0)
    return seen


@pytest.mark.asyncio
async def test_two_timeframes_closing_in_one_cycle_both_reach_hot_subscriber() -> None:
    engine = make_engine()
    seen = await _two_frames_one_cycle(engine, "101")      # مشترِك «كلّ تِكّة»
    assert sorted(seen) == [("1h", 2), ("4h", 1)], seen
    assert engine.transport_stats()["engine"]["coalesced_in_cycle_by_event"] == {
        "analysis.trend.state": 1}
    await engine.close()


@pytest.mark.asyncio
async def test_two_timeframes_closing_in_one_cycle_both_reach_cadence_subscriber() -> None:
    # 166 مشترِك إيقاع (150-499): يمرّ بحزمة النطاق — والمفتاح نفسه يحكمها.
    engine = make_engine()
    seen = await _two_frames_one_cycle(engine, "166")
    assert sorted(seen) == [("1h", 2), ("4h", 1)], seen
    await engine.close()


@pytest.mark.asyncio
async def test_old_key_loses_the_first_timeframe(monkeypatch: pytest.MonkeyPatch) -> None:
    """ضبطٌ مقارن: بالمفتاح القديم تضيع نتيجة الساعة عند حدّ الأربع ساعات."""
    monkeypatch.setattr(engine_module, "_coalesce_key", _old_coalesce_key)
    engine = make_engine()
    seen = await _two_frames_one_cycle(engine, "101")
    assert seen == [("1h", 2)], seen   # 4h دُمج في 1h ثمّ حلّت محلّه الساعة الثانية
    await engine.close()


@pytest.mark.asyncio
async def test_bus_mailbox_keeps_both_timeframes_and_coalesces_repeats() -> None:
    bus = EventBus()
    seen: list[tuple[str, int]] = []
    gate = asyncio.Event()

    async def slow(payload: dict) -> None:
        await gate.wait()
        seen.append((payload.get("timeframe", ""), payload.get("n", 0)))

    bus.subscribe("structure.swing.state", slow, subscriber="207")
    await bus.publish("structure.swing.state", {"symbol": "XAUUSD", "id": "swing",
                                                "timeframe": "1m", "n": 0}, publisher="201")
    await asyncio.sleep(0.01)       # الأوّل في يد المعالج؛ ما بعده ينتظر في الصندوق
    for frame, n in (("10s", 1), ("1m", 2), ("10s", 3)):
        await bus.publish("structure.swing.state", {"symbol": "XAUUSD", "id": "swing",
                                                    "timeframe": frame, "n": n}, publisher="201")
    gate.set()
    assert await bus.drain(timeout_s=2.0)
    assert seen == [("1m", 0), ("10s", 3), ("1m", 2)], seen
    assert bus.stats()["coalesced"]["structure.swing.state"] == 1
    bus.close()


# ════════════════════════════════════════════════ ٢ تصنيف الأمر والحالة ══

#: كلّ اسم حدثٍ حيّ — `audit\map_events.csv` (376) ∪ `/api/bus-stats` (292) في
#: 2026-10-02 20:30. الاتّحاد 376 اسمًا.
_LIVE_EVENT_NAMES = """
NQ SYS_10MS SYS_15MIN SYS_5MIN SYS_DAY SYS_HOUR SYS_SECOND adaptation.kill_switch.command
adaptation.kill_switch.state adaptation.limits.state ai.brain.state allowed.symbols.state
analysis.acceleration.state analysis.analysts.state analysis.candle.state
analysis.correlation.state analysis.cycle.collected analysis.fast.state analysis.gap.state
analysis.momentum.state analysis.noise.state analysis.raw.completed
analysis.relative_strength.state analysis.section.live analysis.session.state
analysis.setting.changed analysis.settings.command analysis.slow.state analysis.spread.state
analysis.time.state analysis.trend.state analysis.velocity.state analysis.volatility.state
analysis.volume.state analysis.volume_quality.state asset.extraction.confirmed
asset.extraction.execution_requested asset.extraction.failed asset.extraction.requested
asset.extraction.retry_requested asset.extraction.state asset.full_extraction.requested
asset.portfolio.owner_intent.state asset.portfolio.state audit.trail.state core.atom.failed
core.atom.restart_failed core.atom.restarted core.atom.restarts_exhausted core.atom.started
core.atom.stopped core.atom.unhealthy core.atom.unloaded core.critical_atom.unhealthy
core.integrity.alert core.system.rescan_requested decision.aggregated.state
decision.approved.state decision.behaviour.telemetry decision.card.changed decision.card.closed
decision.card.opened decision.card.reversed decision.card.state decision.cycle.collected
decision.cycle.record decision.dispatch.state decision.eligibility.buy.state
decision.eligibility.sell.state decision.evaluated.state decision.filter.asset.state
decision.filter.conditions.state decision.filter.confidence.state
decision.filter.freshness.state decision.filter.position.state decision.filter.timing.state
decision.filtered.state decision.gate.blocked decision.gate.passed decision.gate.recorded
decision.resolved.state decision.room.state decision.scored.state decision.settings.command
decision.settings.state decision.wait.state dial.command dial.profile.state drift.vector.state
emergency.halt execution.command.ack execution.command.failed execution.confirmation.rejected
execution.desired.state execution.entry.state execution.gate.command execution.gate.state
execution.manage.command execution.manage.intent execution.manage.written execution.order.built
execution.order.legal execution.order.rejected execution.order.requested
execution.order.resolved execution.order.skipped execution.quality.state
execution.reconcile.requested execution.reconcile.state execution.reference_divergence.state
execution.snapshot.state execution.unified.state experiment.state feed.ctrader.heartbeat
feed.ctrader.raw feed.ctrader.state feed.ctrader.tick feed.mt5.tick feed.relay.state
feed.replay.tick financial.truth.shortage horizon.profile.state hot_reload.completed
kernel.clock.heartbeat kernel.clock.minute_elapsed kernel.clock.sys_tick learning.feature.ready
learning.model.active.state learning.model.candidate learning.model.drift.state
learning.model.evidence learning.model.rollback_requested learning.model.selected
learning.model.selection learning.model.validated learning.outcome.recorded
learning.sample.ready liquidity.absorption.state liquidity.buyside.state liquidity.cvd.state
liquidity.cycle.collected liquidity.cycle.validated liquidity.delta.state liquidity.depth.state
liquidity.fvg.state liquidity.microprice.state liquidity.ofi.state liquidity.pool.state
liquidity.price_impact.state liquidity.section.live liquidity.sellside.state
liquidity.sweep.state liquidity.units.state liquidity.validation_failed logs.trades.state
market.book.state market.broker_tick market.calendar market.ctrader.symbol_specs market.depth
market.feed.provider_down market.feed.provider_recovered market.feed.source_rejected
market.liquidity.updated market.news market.outcome.realized market.reference
market.regime.state market.structure.updated market.symbol_specs market.tick
market.tick.validated market.time.drift market.time.synced market.trade market.volume
market_data.calendar.state market_data.calendar_event market_data.calendar_window
market_data.candle_closed market_data.depth_updated market_data.feed.state
market_data.feed_interrupted market_data.feed_recovered market_data.news_received
market_data.price_received market_data.quality.state market_data.quality_alert
market_data.reference_index_updated market_data.spread_updated market_data.state
market_data.trade_tape_updated market_data.validation.state market_data.validation_failed
market_data.volume_received measurement.health.state measurement.latency.state
model.persist_requested model.persisted news.trading_window.state parameter.approve.command
parameter.approved.state perpetual.asset.activate perpetual.asset.deactivate
perpetual.target.state platform.account.state platform.brain_signal.halted
platform.brain_signal.write_failed platform.brain_signal.written platform.position.appeared
platform.position.vanished platform.positions.schema_state platform.positions.state
platform.terminal_state platform.trade_event platform.trade_event.simulated
portfolio.account.state portfolio.account.tracked portfolio.balance.state
portfolio.capital_distribution.state portfolio.comparison.state portfolio.components.state
portfolio.equity.state portfolio.free_margin.state portfolio.loss_limits.state
portfolio.margin.state portfolio.margin_level.state portfolio.open_positions.state
portfolio.overview.state portfolio.performance.state portfolio.pnl.state
portfolio.profit_limits.state portfolio.risk_distribution.state portfolio.summary
probability.breakout.state probability.confidence.state probability.cycle.collected
probability.hurst.state probability.merged.state probability.momentum.state
probability.pullback.state probability.range.state probability.reversal.state
probability.section.live probability.trend.state probability.units.state recalibration.applied
recalibration.proposed reference.health.state replay.session.start replay.session.state
replay.session.stop risk.account.state risk.asset.command risk.asset_budget.state
risk.asset_ledger.reset_requested risk.asset_ledger.state risk.asset_profit.extracted
risk.asset_stop.state risk.audit.state risk.exposure.state risk.halt.requested
risk.kill_switch.reset_requested risk.loss_reported risk.margin.validation.completed
risk.position_size.rejected risk.position_size.state risk.profit_limits.state
risk.release.requested risk.session_limits.state risk.structure_stop.state risk.unified.state
risk.validation.completed sim.execution.state stats.correlation.state stats.cv.state
stats.cycle.collected stats.distribution.state stats.kurtosis.state stats.mean.state
stats.median.state stats.mode.state stats.outlier.state stats.period_compare.state
stats.quality.state stats.r_squared.state stats.range.state stats.regression.state
stats.section.live stats.skewness.state stats.std.state stats.units.state stats.variance.state
stats.zscore.state storage.analysis_saved storage.archived storage.compressed
storage.decisions_saved storage.liquidity_saved storage.market_data_saved
storage.model_saved_confirmed storage.orders_saved storage.persistence.load_requested
storage.persistence.load_response storage.persistence.save_failed storage.portfolio_saved
storage.structure_saved storage.symbol.map.state storage.symbol.resolve_requested
storage.symbol.resolved storage.symbol.unmapped storage.timeline_saved storage.trades_saved
storage.trading_data_cleaned storage.trading_data_integrity_checked strategy.aggregate.state
strategy.breakout.state strategy.cycle.collected strategy.entry_quality.state
strategy.invalidation_quality.state strategy.liquidity.state strategy.momentum.state
strategy.news.state strategy.pullback.state strategy.range.state strategy.reversal.state
strategy.section.live strategy.session.state strategy.setup.proposed strategy.trend.state
strategy.units.state structure.bos.state structure.choch.state structure.cycle.collected
structure.cycle.validated structure.external.state structure.internal.state
structure.levels.state structure.mss.state structure.phase.state structure.section.live
structure.swing.state structure.trend.state structure.units.state structure.validation_failed
symbol.resolve.orphaned symbol.resolve.requested symbol.resolve.result system.alert
system.alert.recovered system.alert.state system.commands.state system.diagnosis.state
telemetry.batch.closed telemetry.carrier.state tilt.rule.command tilt.rules.state tilt.state
time.clock.divergence time.clock.quality.state time.ntp.drift time.ntp.samples.state
time.utc.drift time.utc.stale time.utc.synced tools.backup.completed tools.backup.failed
tools.device_resources.state tools.file_archive.completed tools.file_archive.failed
tools.file_cleanup.completed tools.file_cleanup.failed tools.integrity.violation
tools.storage.low tools.storage.recovered trading.final_decision
""".split()

#: الأوامر الحقيقيّة الثمانية عشر — لا يجوز أن يفقد أيٌّ منها صفته.
_REAL_COMMANDS = {
    "adaptation.kill_switch.command", "analysis.settings.command", "decision.settings.command",
    "dial.command", "execution.command.ack", "execution.command.failed",
    "execution.gate.command", "execution.manage.command", "execution.order.built",
    "execution.order.legal", "execution.order.rejected", "execution.order.requested",
    "execution.order.resolved", "execution.order.skipped", "parameter.approve.command",
    "risk.asset.command", "tilt.rule.command", "trading.final_decision",
}

#: الستّة التي كانت «أوامر» بجزء نصّ (`.buy` في `buyside`، `order` في `orders_saved`،
#: `command` في `commands`) — وأوراق المشروع ٤٢/٤٣/٤٤ تسمّي الخمسة الأولى حالات.
_RECLASSIFIED = {
    "decision.eligibility.buy.state": "state",
    "decision.eligibility.sell.state": "state",
    "liquidity.buyside.state": "state",
    "liquidity.sellside.state": "state",
    "system.commands.state": "state",
    "storage.orders_saved": "event",
}

_OLD_MARKERS = ("order", ".buy", ".sell", ".execute", ".cancel", "final_decision", "command",
                ".submit", ".send")


def _old_class(name: str) -> str:
    if any(marker in name for marker in _OLD_MARKERS):
        return "command"
    if name in _TIME_SIGNAL_EVENTS or name.endswith(_STATE_SUFFIXES):
        return "state"
    return "event"


def _new_class(name: str) -> str:
    if _is_command(name):
        return "command"
    return "state" if _is_replayable(name) else "event"


def test_live_event_names_before_after_classification() -> None:
    names = _LIVE_EVENT_NAMES
    assert len(names) == len(set(names)) == 376
    changed = {name: (_old_class(name), _new_class(name))
               for name in names if _old_class(name) != _new_class(name)}
    assert changed == {name: ("command", after) for name, after in _RECLASSIFIED.items()}, changed
    before_commands = {name for name in names if _old_class(name) == "command"}
    after_commands = {name for name in names if _new_class(name) == "command"}
    assert before_commands == _REAL_COMMANDS | set(_RECLASSIFIED)
    assert after_commands == _REAL_COMMANDS          # لا أمر حقيقيّ فقد صفته، ولا أمر جديد
    assert after_commands <= before_commands


def test_command_guard_contracts_still_hold() -> None:
    # حارس التنفيذ المزدوج (أداة V2.0): أمرٌ بلاحقة حالة لا يُعاد أبدًا.
    assert _is_replayable("x.order.state") is False
    assert _is_command("x.order.state") is True
    assert _is_replayable("x.state") is True
    assert _is_command("trade.buy") and _is_command("trade.sell")       # الجهة فعلًا
    # عقد اختبارات القطع وصورة العالم: قرار الجهة حالةً ما زال فعلًا لا يُعاد.
    assert _is_command("decision.buy.state") and not _is_replayable("decision.sell.state")
    assert _is_command("x.order_intent") and _is_command("x.command_ack")
    assert _is_command("trade.executed") and _is_command("order.cancelled")
    assert not _is_command("liquidity.buyside.swept")                  # buyside وصفٌ لا فعل
    # الاستثناء صريحٌ بالاسم لا مستنتج: حالةٌ أخرى تصف جهةً تبقى أمرًا حتّى تُعلَن.
    assert _is_command("decision.readiness.buy.state")


@pytest.mark.asyncio
async def test_eligibility_state_is_replayed_to_a_late_subscriber() -> None:
    bus = EventBus()
    await bus.publish("decision.eligibility.buy.state",
                      {"symbol": "XAUUSD", "status": "eligible"}, publisher="455")
    late: list[dict] = []

    async def on_late(payload: dict) -> None:
        late.append(payload)

    bus.subscribe("decision.eligibility.buy.state", on_late, subscriber="458")
    assert await bus.drain(timeout_s=2.0)
    assert [p["status"] for p in late] == ["eligible"]
    assert bus.stats()["replayed"]["decision.eligibility.buy.state"] == 1
    bus.close()


# ════════════════════════════════════ ٣ معالجٌ يحجز الحلقة فوق مهلة الدورة ══

def _spin(seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pass


@pytest.mark.asyncio
async def test_sync_handler_over_deadline_is_counted_named_and_logged() -> None:
    engine = make_engine(cycle_deadline_s=0.05)

    def blocking(_payload: dict) -> None:          # `def`: على خيط الحلقة
        _spin(0.15)

    engine.subscribe("market.tick.validated", blocking, subscriber="156")
    with _Errors("quant_nq.core.engine") as errors:
        await engine.publish("market.tick.validated", {"symbol": "USTEC"}, publisher="111")
        assert await engine.drain(timeout_s=3.0)
    ts = engine.transport_stats()["engine"]
    assert ts["cycle_timeouts"] == 0                 # المهلة لم تقطعه — هذا هو العمى
    assert ts["sync_overruns"] == 1
    assert ts["sync_overrun_by_subscriber"] == {"156": 1}
    assert ts["sync_overrun_worst_by_subscriber"]["156"] >= 0.15
    assert ts["cycle_overdeadline"] == 1
    assert engine.stats()["sync_overrun"] == {"market.tick.validated": 1}
    lines = [line for line in errors.messages if "حجز الحلقة" in line]
    assert len(lines) == 1 and "156" in lines[0] and "market.tick.validated" in lines[0]
    # الدورة فوق مهلتها، وسببها معالجٌ واحد سُمّي — لا سطرٌ ثانٍ مكرّر.
    assert not [line for line in errors.messages if "دورةٌ استغرقت" in line]
    await engine.close()


@pytest.mark.asyncio
async def test_async_handler_that_never_yields_is_counted_too() -> None:
    engine = make_engine(cycle_deadline_s=0.05)

    async def computes(_payload: dict) -> None:      # `async def` يحسب بلا `await`
        _spin(0.12)

    engine.subscribe("decision.scored.state", computes, subscriber="455")
    await engine.publish("decision.scored.state", {"symbol": "USTEC"}, publisher="452")
    assert await engine.drain(timeout_s=3.0)
    ts = engine.transport_stats()["engine"]
    assert ts["cycle_timeouts"] == 0 and ts["sync_overruns"] == 1
    assert "455" in ts["sync_overrun_last"]
    await engine.close()


@pytest.mark.asyncio
async def test_handler_that_yields_is_cut_by_deadline_not_counted_as_overrun() -> None:
    engine = make_engine(cycle_deadline_s=0.05)

    async def waits(_payload: dict) -> None:
        await asyncio.sleep(1.0)

    engine.subscribe("slow", waits, subscriber="160")
    await engine.publish("slow", {}, publisher="t")
    assert await engine.drain(timeout_s=3.0)
    ts = engine.transport_stats()["engine"]
    assert ts["cycle_timeouts"] == 1 and ts["sync_overruns"] == 0 and ts["cycle_overdeadline"] == 0
    await engine.close()


@pytest.mark.asyncio
async def test_cycle_over_deadline_from_many_short_handlers_is_counted() -> None:
    engine = make_engine(cycle_deadline_s=0.05)

    def part(_payload: dict) -> None:
        _spin(0.035)

    for sub in ("401", "402", "403"):
        engine.subscribe("market.tick.validated", part, subscriber=sub)
    await engine.publish("market.tick.validated", {"symbol": "USTEC"}, publisher="111")
    assert await engine.drain(timeout_s=3.0)
    ts = engine.transport_stats()["engine"]
    # لا معالج وحده فوق المهلة، والدورة كلّها فوقها — تُعدّ دورةً لا معالجًا.
    assert ts["sync_overruns"] == 0 and ts["cycle_timeouts"] == 0
    assert ts["cycle_overdeadline"] == 1
    assert ts["cycle_overdeadline_worst_s"] >= 0.1
    await engine.close()


# ═══════════════════════════ ٤ الإعادة إلى رأس الطابور بعمقها، والإسقاط الحقيقيّ ══

@pytest.mark.asyncio
async def test_leftovers_of_a_timed_out_cycle_run_before_newer_events_with_their_depth() -> None:
    engine = make_engine(cycle_deadline_s=0.2)
    order: list[tuple[str, int]] = []
    scope = {"account_id": "A", "symbol": "XAUUSD"}

    async def hangs_after_publishing(_payload: dict) -> None:
        await engine.publish("chain.a", dict(scope), publisher="101")
        await engine.publish("chain.b", dict(scope), publisher="101")
        await asyncio.sleep(2.0)                         # يعلق — تُلغى الدورة عند 0.2 ث

    def recorder_for(name: str):
        async def _on(_payload: dict) -> None:
            cycle = _CYCLE.get()
            order.append((name, cycle.current_depth if cycle is not None else -1))
        return _on

    engine.subscribe("tick", hangs_after_publishing, subscriber="101")
    for name in ("chain.a", "chain.b", "late"):
        engine.subscribe(name, recorder_for(name), subscriber="102")

    async def newer_arrives_during_the_hang() -> None:
        await asyncio.sleep(0.05)
        await engine.publish("late", dict(scope), publisher="613")

    newer = asyncio.create_task(newer_arrives_during_the_hang())
    await engine.publish("tick", dict(scope), publisher="613")
    await newer
    assert await engine.drain(timeout_s=3.0)
    assert order == [("chain.a", 1), ("chain.b", 1), ("late", 0)], order
    ts = engine.transport_stats()["engine"]
    assert ts["cycle_timeouts"] == 1 and ts["cycle_timeout_requeued"] == 2
    assert ts["scheduler"]["requeued_front"] == 2
    await engine.close()


def _scheduler() -> ScopeScheduler:
    async def _noop(*_args: Any) -> None:
        return None
    return ScopeScheduler(run_every=_noop, run_cadence=_noop)


def test_requeue_front_keeps_order_depth_and_never_overwrites_newer_cadence() -> None:
    sched = _scheduler()
    scope = ("A", "XAUUSD")
    sched.admit_every(scope, "late", {"n": 9})
    sched.admit_cadence(scope, ("x.state", "A", "XAUUSD"), "x.state", {"n": 2})   # الأحدث
    superseded = sched.requeue_front(
        scope,
        [("a", {"n": 1}, None, 3), ("b", {"n": 2}, None, 3)],
        [(("x.state", "A", "XAUUSD"), "x.state", {"n": 1}),                       # الأقدم
         (("y.state", "A", "XAUUSD"), "y.state", {"n": 1})])
    state = sched._scopes[scope]
    assert [(item[0], item[4]) for item in state.every] == [("a", 3), ("b", 3), ("late", 0)]
    assert list(state.cadence) == [("y.state", "A", "XAUUSD"), ("x.state", "A", "XAUUSD")]
    assert state.cadence[("x.state", "A", "XAUUSD")][1] == {"n": 2}               # لم يُكتب فوقه
    assert superseded == 1 and sched.requeue_superseded == 1 and sched.requeued_front == 3


@pytest.mark.asyncio
async def test_dropped_is_real_for_depth_and_budget() -> None:
    engine = make_engine(max_depth=10)

    async def ping(payload: dict) -> None:
        await engine.publish("pong", {"n": payload.get("n", 0) + 1}, publisher="101")

    async def pong(payload: dict) -> None:
        await engine.publish("ping", {"n": payload.get("n", 0) + 1}, publisher="102")

    engine.subscribe("ping", ping, subscriber="101")
    engine.subscribe("pong", pong, subscriber="102")
    await engine.publish("ping", {"n": 0}, publisher="t")
    assert await engine.drain(timeout_s=2.0)
    dropped = engine.stats()["dropped"]
    assert sum(dropped.values()) == engine.transport_stats()["engine"]["depth_exceeded"] >= 1
    assert set(dropped) <= {"ping", "pong"}
    await engine.close()

    engine = make_engine(max_events_per_cycle=5)

    async def fan(_payload: dict) -> None:
        for n in range(20):
            await engine.publish("leaf", {"n": n, "id": str(n)}, publisher="101")

    async def leaf(_payload: dict) -> None:
        return None

    engine.subscribe("root", fan, subscriber="101")
    engine.subscribe("leaf", leaf, subscriber="102")
    await engine.publish("root", {}, publisher="t")
    assert await engine.drain(timeout_s=2.0)
    assert engine.transport_stats()["engine"]["budget_exceeded"] == 1
    assert engine.stats()["dropped"] == {"leaf": 20 - 5}     # 6 عولجت (الجذر + 5) والباقي مسوح
    await engine.close()


@pytest.mark.asyncio
async def test_late_subscriber_replay_runs_in_the_payload_scope() -> None:
    engine = make_engine()
    await engine.publish("platform.positions.state",
                         {"account_id": "A", "symbol": "XAUUSD", "open": 1}, publisher="619")
    assert await engine.drain(timeout_s=2.0)
    owned: list[bool] = []

    async def late(_payload: dict) -> None:
        owned.append(engine._scheduler.is_owned(("A", "XAUUSD")))

    engine.subscribe("platform.positions.state", late, subscriber="519")
    assert await engine.drain(timeout_s=2.0)
    assert owned == [True]            # كانت تُدار على النطاق العامّ ('', '')
    await engine.close()


# ═════════════════════════════════════════════════════ ٥ ختم اللقطة وعزلها ══

def _manifest(atom_id: int) -> AtomManifest:
    return AtomManifest.model_validate({"id": atom_id, "name": f"a{atom_id}", "version": "1.0.0",
                                        "core_version": ">=1.0.0", "dependencies": []})


class _Stateful(AtomBase):
    def __init__(self, state: Any) -> None:
        self.state = state
        self.restored: Any = None

    async def initialize(self, context) -> None: pass  # noqa: ANN001
    async def start(self) -> None: pass
    async def stop(self) -> None: pass
    async def snapshot(self) -> Any: return self.state
    async def restore(self, state: Any) -> None: self.restored = state


def _engine_with(tmp_path: Path, state: Any) -> tuple[SnapshotEngine, _Stateful]:
    registry = Registry()
    atom = _Stateful(state)
    registry.register(_manifest(1), atom)
    return SnapshotEngine(registry, tmp_path), atom


@pytest.mark.asyncio
async def test_snapshot_is_sealed_and_round_trips_exactly(tmp_path: Path) -> None:
    state = {"tripped": True, "limits": {"daily": -250.5}, "ملاحظة": "قاطع", "keys": [1, 2.5, None]}
    snap, atom = _engine_with(tmp_path, state)
    await snap.snapshot_all()
    on_disk = json.loads((tmp_path / "1.json").read_text(encoding="utf-8"))
    assert len(on_disk.pop(INTEGRITY_FIELD)) == 64
    assert on_disk == state                       # القارئ الخارجيّ يرى المفاتيح نفسها
    assert await snap.restore_one(1) is True
    assert atom.restored == state                 # الذرّة لا ترى حقل الختم
    assert snap.integrity_report() == {"failed": 0, "atoms": {}}
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [{}, [1, 2, 3], {"x": {"y": []}}])
async def test_empty_nested_and_non_dict_states_round_trip(tmp_path: Path, state: Any) -> None:
    snap, atom = _engine_with(tmp_path, state)
    await snap.snapshot_all()
    assert await snap.restore_one(1) is True
    assert atom.restored == state


@pytest.mark.asyncio
async def test_truncated_snapshot_is_quarantined_and_atom_boots_without_state(
        tmp_path: Path) -> None:
    snap, atom = _engine_with(tmp_path, {"tripped": True})
    await snap.snapshot_all()
    path = tmp_path / "1.json"
    raw = path.read_bytes()
    path.write_bytes(raw[: len(raw) // 2])          # انقطاعٌ وسط ملفٍّ نُسخ يدويًّا
    with _Errors("quant_nq.core.snapshot_engine") as errors:
        assert await snap.restore_one(1) is False   # لا استثناء يُسقط الإقلاع
    assert atom.restored is None
    assert not path.exists()
    quarantined = list(tmp_path.glob("1.json.corrupt-*"))
    assert len(quarantined) == 1 and quarantined[0].read_bytes() == raw[: len(raw) // 2]
    report = snap.integrity_report()
    assert report["failed"] == 1 and "JSON" in report["atoms"]["1"]["reason"]
    assert report["atoms"]["1"]["quarantined_to"] == str(quarantined[0])
    assert any("تالفة" in line and "بلا حالتها" in line for line in errors.messages)


@pytest.mark.asyncio
async def test_checksum_mismatch_is_quarantined(tmp_path: Path) -> None:
    snap, atom = _engine_with(tmp_path, {"daily_loss": 100, "tripped": False})
    await snap.snapshot_all()
    path = tmp_path / "1.json"
    tampered = path.read_text(encoding="utf-8").replace('"daily_loss": 100', '"daily_loss": 1')
    path.write_text(tampered, encoding="utf-8")
    json.loads(tampered)                             # ما زال JSON صالحًا — الختم وحده يكشفه
    assert await snap.restore_one(1) is False
    assert atom.restored is None
    assert len(list(tmp_path.glob("1.json.corrupt-*"))) == 1
    assert "ختم" in snap.integrity_report()["atoms"]["1"]["reason"]


@pytest.mark.asyncio
async def test_old_snapshot_without_seal_loads_as_before(tmp_path: Path) -> None:
    snap, atom = _engine_with(tmp_path, None)
    (tmp_path / "1.json").write_text('{"balance": 42, "pairs": {"EURUSD": 1}}', encoding="utf-8")
    assert await snap.restore_one(1) is True
    assert atom.restored == {"balance": 42, "pairs": {"EURUSD": 1}}
    assert snap.integrity_report()["failed"] == 0


@pytest.mark.asyncio
async def test_restore_all_reports_quarantined_as_failed(tmp_path: Path) -> None:
    snap, _atom = _engine_with(tmp_path, {"v": 1})
    (tmp_path / "1.json").write_text('{"v": ', encoding="utf-8")
    report = await snap.restore_all()
    assert report.failed == [1] and report.restored == []
    assert len(list(tmp_path.glob("1.json.corrupt-*"))) == 1
