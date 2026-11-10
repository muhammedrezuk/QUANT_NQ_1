from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta

import clock
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

try:
    from zoneinfo import ZoneInfo
except ImportError:  # noqa: BLE001
    ZoneInfo = None

ATOM_VERSION = "3.0.2"
SOURCE_LOCAL = "LOCAL_CLOCK"
SOURCE_NTP = "NTP_SYNCED"
_SECOND_S = 1.0
_MINUTE_S = 60.0
_HOUR_S = 3600.0
_DAY_S = 86400.0
_DRIFT_WARNING_THRESHOLD_S = 1.0
_MIN_SLEEP_S = 0.001
_CADENCES = {"SYS_SECOND": _SECOND_S, "SYS_5MIN": 5 * _MINUTE_S,
             "SYS_15MIN": 15 * _MINUTE_S, "SYS_HOUR": _HOUR_S,
             "SYS_DAY": _DAY_S}
# 2026-10-17 (owner seal): the funder's trading day starts at 00:00 on the owner's clock (Turkey), while SYS_DAY rolls at
# UTC midnight (03:00 Turkey). SYS_MARKET_DAY rolls at a configured local hour in a configured zone, from the time-zone
# database -- no fixed offset. Without the database it falls back to UTC midnight (SYS_DAY's boundary) and says so.
EVENT_MARKET_DAY = "SYS_MARKET_DAY"
DEFAULT_MARKET_DAY_ZONE = "Europe/Istanbul"
DEFAULT_MARKET_DAY_HOUR = 0
_KNOWN_PULSES = frozenset(_CADENCES) | {EVENT_MARKET_DAY}

class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None; self._running = False
        self._tasks: list[asyncio.Task] = []
        self.tick_counts: dict[str, int] = {name: 0 for name in sorted(_KNOWN_PULSES)}
        self._max_observed_drift_s = 0.0
        self._last_bucket: dict[str, int] = {}
        self._market_zone_name = DEFAULT_MARKET_DAY_ZONE
        self._market_day_hour = DEFAULT_MARKET_DAY_HOUR
        self._market_zone = None

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._market_zone_name = str(cfg.get("market_day_zone") or DEFAULT_MARKET_DAY_ZONE)
        self._market_day_hour = int(cfg.get("market_day_hour", DEFAULT_MARKET_DAY_HOUR))
        try:
            self._market_zone = ZoneInfo(self._market_zone_name) if ZoneInfo is not None else None
        except Exception:  # noqa: BLE001 -- missing database or unknown zone: fall back, declared in health
            self._market_zone = None

    def _market_day_start(self, now: float) -> int:
        if self._market_zone is None:
            return int(now // _DAY_S * _DAY_S)
        local = datetime.fromtimestamp(now, self._market_zone)
        start = local.replace(hour=self._market_day_hour, minute=0, second=0, microsecond=0)
        if start > local:
            start -= timedelta(days=1)
        return int(start.timestamp())

    async def start(self) -> None:
        if self._running or self._context is None: return
        self._running = True
        for event_name, interval_s in _CADENCES.items():
            self._last_bucket.setdefault(event_name, int(clock.now() // interval_s))
            self._tasks.append(asyncio.create_task(self._scheduled_loop(event_name, interval_s)))
        # No market-day pulse at boot: a restart mid-day must not clear a daily limit that was breached today.
        self._last_bucket.setdefault(EVENT_MARKET_DAY, self._market_day_start(clock.now()))
        self._tasks.append(asyncio.create_task(self._market_day_loop()))

    async def stop(self) -> None:
        self._running = False; tasks = tuple(self._tasks)
        for task in tasks: task.cancel()
        for task in tasks:
            try: await task
            except asyncio.CancelledError: pass
        self._tasks = []

    async def shutdown(self) -> None: await self.stop()

    async def _emit_bucket(self, event_name: str, interval_s: float,
                           bucket: int, elapsed_intervals: int) -> None:
        if not self._running or self._context is None: return
        await self._publish_pulse(event_name, float(bucket * interval_s), elapsed_intervals)

    async def _publish_pulse(self, event_name: str, bucket_start: float, elapsed_intervals: int,
                             extra: dict | None = None) -> None:
        self.tick_counts[event_name] += 1; state = clock.state()
        missed = 0 if elapsed_intervals <= 1 else elapsed_intervals
        await self._context.publish(event_name, {
            "count": self.tick_counts[event_name], "official_time": clock.now(),
            "monotonic_time": clock.mono(),
            "time_source": SOURCE_NTP if state["quality"] == clock.SYNCED else SOURCE_LOCAL,
            "clock_quality": state["quality"], "sync_age_s": state["sync_age_s"],
            "offset_s": state["offset_s"], "sequence": state["sequence"],
            "clock_sequence": state["sequence"],
            "bucket_start": bucket_start, "pulse_id": f"{event_name}|{int(bucket_start)}",
            "missed_intervals": missed, **(extra or {})})

    async def _emit_market_day(self) -> None:
        if not self._running or self._context is None: return
        start = self._market_day_start(clock.now())
        previous = self._last_bucket.get(EVENT_MARKET_DAY, start)
        if start <= previous: return
        self._last_bucket[EVENT_MARKET_DAY] = start
        days = max(1, int(round((start - previous) / _DAY_S)))
        await self._publish_pulse(EVENT_MARKET_DAY, float(start), days, {
            "market_day_zone": self._market_zone_name if self._market_zone is not None else "UTC",
            "market_day_hour": self._market_day_hour if self._market_zone is not None else 0,
            "zone_fallback": self._market_zone is None})

    async def _market_day_loop(self) -> None:
        try:
            while self._running:
                try: await self._emit_market_day()
                except Exception as exc:
                    if self._context is not None: self._context.logger.error("time pulse %s failed: %s", EVENT_MARKET_DAY, exc)
                await asyncio.sleep(_SECOND_S)
        except asyncio.CancelledError: pass

    async def _emit_tick(self, event_name: str) -> None:
        interval_s = _CADENCES[event_name]; bucket = int(clock.now() // interval_s)
        previous = self._last_bucket.get(event_name, bucket - 1)
        if bucket <= previous: return
        self._last_bucket[event_name] = bucket
        await self._emit_bucket(event_name, interval_s, bucket, bucket - previous)

    async def _scheduled_loop(self, event_name: str, interval_s: float) -> None:
        loop = asyncio.get_running_loop()
        try:
            while self._running:
                now = clock.now(); bucket = int(now // interval_s)
                previous = self._last_bucket.get(event_name, bucket)
                if bucket > previous:
                    lateness = max(0.0, now - bucket * interval_s)
                    self._max_observed_drift_s = max(self._max_observed_drift_s, lateness)
                    self._last_bucket[event_name] = bucket
                    try: await self._emit_bucket(event_name, interval_s, bucket, bucket - previous)
                    except Exception as exc:
                        if self._context is not None: self._context.logger.error("time pulse %s failed: %s", event_name, exc)
                delay = max(_MIN_SLEEP_S, min(1.0, (bucket + 1) * interval_s - clock.now()))
                await asyncio.sleep(delay)
        except asyncio.CancelledError: pass

    async def snapshot(self) -> dict:
        return {"version": ATOM_VERSION, "last_bucket": dict(self._last_bucket),
                "tick_counts": dict(self.tick_counts),
                "max_observed_drift_s": self._max_observed_drift_s}

    async def restore(self, state: dict) -> None:
        buckets = state.get("last_bucket") if isinstance(state, dict) else None
        counts = state.get("tick_counts") if isinstance(state, dict) else None
        if (not isinstance(buckets, dict) or not isinstance(counts, dict)
                or any(name not in _KNOWN_PULSES or isinstance(value, bool)
                       or not isinstance(value, int) for name, value in buckets.items())
                or any(name not in _KNOWN_PULSES or isinstance(value, bool)
                       or not isinstance(value, int) or value < 0
                       for name, value in counts.items())):
            raise ValueError("INVALID_TIME_PULSE_STATE")
        self._last_bucket = {str(name): int(value) for name, value in buckets.items()}
        self.tick_counts.update({str(name): int(value) for name, value in counts.items()})
        drift = state.get("max_observed_drift_s", 0.0)
        if (isinstance(drift, bool) or not isinstance(drift, (int, float))
                or not math.isfinite(float(drift)) or drift < 0):
            raise ValueError("INVALID_TIME_PULSE_STATE")
        self._max_observed_drift_s = float(drift)

    async def health_check(self) -> HealthStatus:
        if not self._running or len(self._tasks) != len(_CADENCES) + 1 or any(task.done() for task in self._tasks):
            return HealthStatus(state=HealthState.UNHEALTHY, message="at least one pulse loop stopped")
        state = clock.state()
        health = HealthState.HEALTHY if state["quality"] == clock.SYNCED and self._market_zone is not None \
            else HealthState.DEGRADED
        market = (f"market_day={self._market_zone_name}@{self._market_day_hour:02d}:00" if self._market_zone is not None
                  else f"market_day=UTC_FALLBACK(zone {self._market_zone_name} unavailable)")
        return HealthStatus(state=health,
            message=f"{state['quality']} {market} {self.tick_counts} max_drift_ever={self._max_observed_drift_s:.3f}s",
            details={**state, "ticks": dict(self.tick_counts),
                     "max_observed_drift_s": self._max_observed_drift_s})
