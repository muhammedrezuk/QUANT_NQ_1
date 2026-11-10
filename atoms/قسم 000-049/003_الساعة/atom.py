from __future__ import annotations

import asyncio
import math
from typing import Awaitable, Callable

import clock
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "3.2.0"
EVENT_SAMPLE = "time.ntp.samples.state"
EVENT_SYNCED = "time.utc.synced"
EVENT_DRIFT = "time.utc.drift"
EVENT_QUALITY = "time.clock.quality.state"
EVENT_SYS_TICK = "kernel.clock.sys_tick"
EVENT_HEARTBEAT = "kernel.clock.heartbeat"
EVENT_MINUTE = "kernel.clock.minute_elapsed"
SOURCE_LOCAL = "LOCAL_CLOCK"
SOURCE_NTP = "NTP_SYNCED"
_MINUTE_S = 60.0
_DRIFT_WARNING_THRESHOLD_S = 1.0
_MIN_SLEEP_S = 0.001
_DEFAULT_SYS_TICK_S = 0.1
_DEFAULT_HEARTBEAT_S = 1.0

class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None; self._running = False
        self._accept_samples = False
        self._sys_tick_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._minute_task: asyncio.Task | None = None
        self._sys_tick_interval_s = _DEFAULT_SYS_TICK_S
        self._heartbeat_interval_s = _DEFAULT_HEARTBEAT_S
        self._drift_alert_s = 1.0; self._last_quality = clock.LOCAL_FALLBACK
        self.sys_tick_count = self.heartbeat_count = self.minute_count = 0
        self.accepted_samples = self.rejected_samples = 0
        self._max_observed_drift_s = 0.0
        self._pending_sync: tuple[dict, float] | None = None

    async def initialize(self, context: AtomContext) -> None:
        self._context = context; self._accept_samples = True; cfg = context.config
        self._sys_tick_interval_s = float(cfg["sys_tick_interval_s"])
        self._heartbeat_interval_s = float(cfg["heartbeat_interval_s"])
        self._drift_alert_s = float(cfg["drift_alert_s"])
        clock.configure(max_accepted_offset_s=float(cfg["max_accepted_offset_s"]),
            max_sample_age_s=float(cfg["max_sample_age_s"]),
            stale_after_s=float(cfg["stale_after_s"]),
            max_slew_per_second=float(cfg["max_slew_per_second"]))
        context.subscribe(EVENT_SAMPLE, self._on_sample)

    async def start(self) -> None:
        if self._running or self._context is None: return
        self._running = True; self._accept_samples = True
        self._sys_tick_task = asyncio.create_task(self._scheduled_loop(
            self._sys_tick_interval_s, self._on_sys_tick))
        self._heartbeat_task = asyncio.create_task(self._scheduled_loop(
            self._heartbeat_interval_s, self._on_heartbeat))
        self._minute_task = asyncio.create_task(self._scheduled_loop(
            _MINUTE_S, self._on_minute_elapsed, align_to_official=True))
        if self._pending_sync is not None:
            body, approved_offset = self._pending_sync; self._pending_sync = None
            await self._publish_approved(body, approved_offset)

    async def stop(self) -> None:
        self._running = False; self._accept_samples = False
        tasks = tuple(task for task in (self._sys_tick_task, self._heartbeat_task, self._minute_task)
                      if task is not None)
        for task in tasks: task.cancel()
        for task in tasks:
            try: await task
            except asyncio.CancelledError: pass
        self._sys_tick_task = self._heartbeat_task = self._minute_task = None

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_sample(self, payload: dict) -> None:
        if (self._context is None or not self._accept_samples
                or not isinstance(payload, dict)):
            return
        accepted, reason = clock.accept_sample(payload, writer="003")
        if not accepted:
            if reason != "DUPLICATE_SAMPLE": self.rejected_samples += 1
            self._context.logger.warning("clock sample rejected: %s", reason)
            return
        self.accepted_samples += 1; approved_offset = float(payload["median_offset_s"])
        body = {"offset_s": approved_offset, "measured_at": payload.get("measured_at"),
            "sample_id": payload.get("sample_id")}
        if not self._running:
            self._pending_sync = (body, approved_offset); return
        await self._publish_approved(body, approved_offset)

    async def _publish_approved(self, body: dict, approved_offset: float) -> None:
        if self._context is None: return
        state = clock.state(); body = {**body, "clock_quality": state["quality"],
            "sequence": state["sequence"], "clock_sequence": state["sequence"],
            "sync_age_s": state["sync_age_s"],
            "effective_offset_s": state["offset_s"], "target_offset_s": state["target_offset_s"]}
        await self._context.publish(EVENT_SYNCED, body)
        await self._publish_quality(state)
        if abs(approved_offset) >= self._drift_alert_s:
            await self._context.publish(EVENT_DRIFT, {**body, "threshold_s": self._drift_alert_s})

    async def _publish_quality(self, state: dict | None = None) -> None:
        if self._context is None: return
        state = state or clock.state(); quality = str(state["quality"])
        if quality == self._last_quality and self.heartbeat_count > 0: return
        self._last_quality = quality
        await self._context.publish(EVENT_QUALITY, {**state, "official_time": clock.now()})

    def _official_now(self) -> float:
        return clock.now()

    async def _scheduled_loop(self, interval_s: float,
                              on_tick: Callable[[], Awaitable[None]],
                              align_to_official: bool = False) -> None:
        loop = asyncio.get_running_loop()
        delay = interval_s - (clock.now() % interval_s) if align_to_official else interval_s
        deadline = loop.time() + max(delay, _MIN_SLEEP_S)
        try:
            while self._running:
                await asyncio.sleep(max(0.0, deadline - loop.time()))
                lateness = max(0.0, loop.time() - deadline)
                self._max_observed_drift_s = max(self._max_observed_drift_s, lateness)
                try: await on_tick()
                except Exception as exc:
                    if self._context is not None: self._context.logger.error("clock tick failed: %s", exc)
                if align_to_official:
                    deadline = loop.time() + max(interval_s - clock.now() % interval_s, _MIN_SLEEP_S)
                else:
                    deadline += interval_s
                    if deadline <= loop.time(): deadline = loop.time() + interval_s
        except asyncio.CancelledError: pass

    def _tick_body(self, count_name: str, count: int) -> dict:
        state = clock.state()
        return {count_name: count, "official_time": clock.now(),
            "monotonic_time": clock.mono(), "time_source": SOURCE_NTP if state["quality"] == clock.SYNCED else SOURCE_LOCAL,
            "clock_quality": state["quality"], "sync_age_s": state["sync_age_s"],
            "offset_s": state["offset_s"], "sequence": state["sequence"],
            "clock_sequence": state["sequence"]}

    async def _on_sys_tick(self) -> None:
        if not self._running or self._context is None: return
        self.sys_tick_count += 1
        await self._context.publish(EVENT_SYS_TICK, self._tick_body("tick", self.sys_tick_count))

    async def _on_heartbeat(self) -> None:
        if not self._running or self._context is None: return
        self.heartbeat_count += 1
        await self._context.publish(EVENT_HEARTBEAT, self._tick_body("beat", self.heartbeat_count))
        await self._publish_quality()

    async def _on_minute_elapsed(self) -> None:
        if not self._running or self._context is None: return
        self.minute_count += 1
        await self._context.publish(EVENT_MINUTE, self._tick_body("minute", self.minute_count))

    async def health_check(self) -> HealthStatus:
        if not self._running or any(task is None or task.done() for task in
                (self._sys_tick_task, self._heartbeat_task, self._minute_task)):
            return HealthStatus(state=HealthState.UNHEALTHY, message="clock loop stopped")
        state = clock.state(); quality = state["quality"]
        health = HealthState.HEALTHY if quality == clock.SYNCED else HealthState.DEGRADED
        # ⛔ **`quality=INVALID` بلا سببٍ يُقرأ شيخوخةً وهو ليس كذلك** —
        # مقيس ٢٠٢٦-٠٩-١٦ على النواة الحيّة:
        #
        #     18:21:56  quality=INVALID  sync_age=230ث   (والعتبة 900)
        #     18:22:36  quality=SYNCED   sync_age=25.7ث  ⟵ وصلت عيّنة فانقشع
        #
        # عمرٌ دون العتبة بكثير، فالحالة ليست شيخوخة. و`INVALID` في
        # `clock/clock.py:78` لا تأتي من العمر أصلًا — مسارها الوحيد
        # `BACKWARD_WALL_CLOCK` أو `NON_FINITE_WALL_CLOCK`، و`_last_rejection`
        # **لا يُمسح إلّا بـ`accept_sample`**. فخطوةٌ واحدة إلى الوراء في ساعة
        # ويندوز تُبقي الحالة `INVALID` حتّى العيّنة التالية (دورة ٦٠٨ = ٣٠٠ث)،
        # وفيها يرفض ٥٥٢ كلّ أمرٍ بـ`CLOCK_NOT_SYNCED` — **677 رفضًا مسجَّلًا،
        # ثاني أكبر سببٍ للرفض بعد المرجع**.
        #
        # والسبب كان محفوظًا في `clock.state()` طوال الوقت — لكنّه في
        # `details`, و`details` تُقصّ عند حدود النواة (`core/api/app.py`).
        # فالحقل موجودٌ وغيرُ مرئيّ، وذلك أسوأ من غيابه: يُظنّ أنّه فُحص.
        #
        # ⚠️ وهذا **تشخيصٌ لا علاج**: السلوك لم يتغيّر بحرف. أمّا هل يجوز أن
        # يبقى الرفض معلّقًا خمس دقائق بعد قفزةٍ واحدة — فقرار مالٍ لا
        # يقرّره مَن يعرض الرقم.
        reason = state.get("last_rejection") or ""
        clamps = state.get("backward_clamps") or 0
        cause = f" سبب={reason}" if reason else ""
        # نوبات الحجب — مدّةً لا عددًا. العدّاد التراكميّ لا يقول «كم دام
        # الحجب»، وسجلّ الصفقات لا يرى النوبة التي لم يقع فيها أمر.
        episodes = state.get("episodes") or []
        if episodes:
            spans = [float(row.get("duration_s") or 0.0) for row in episodes]
            cause += (f" نوبات={len(spans)} أطولها={max(spans):.0f}ث"
                      f" مجموعها={sum(spans):.0f}ث")
        open_age = state.get("open_episode_age_s")
        if open_age is not None:
            cause += f" نوبة_جارية={open_age:.0f}ث"
        return HealthStatus(state=health,
            message=f"quality={quality} max_drift_ever={self._max_observed_drift_s:.3f}s "
                    f"sync_age={state.get('sync_age_s')} ارتداد={clamps}{cause}",
            details={**state, "sys_tick": self.sys_tick_count, "heartbeat": self.heartbeat_count,
                "minute": self.minute_count, "accepted_samples": self.accepted_samples,
                "rejected_samples": self.rejected_samples,
                "max_observed_drift_s": self._max_observed_drift_s})
