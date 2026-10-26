"""Time and sessions context (owner's plan 2026-10-17, stage 3, steps 12, 13 and 21).

Once a minute, on the official clock pulse, publishes where the moment sits in time on the owner's clock (Turkey): year,
quarter, half, month, the week of the month in seven-day weeks, the month's shape, the countdowns to the day, week, month,
quarter and year closes; every exchange's session (open or not, time to open or close, its hours on the owner's clock) and
which of them overlap; the day's schedule of the traded assets; and the previous and next US holiday.
Pure facts -- the computing lives in `shared.market_context`; atom 117 keeps its own fields.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from core.contracts.atom import AtomBase, HealthState, HealthStatus
from shared import market_clock, market_context

ATOM_VERSION = "1.0.0"
EVENT_PULSE = "SYS_SECOND"
EVENT_OUT = "knowledge.context.state"
DEFAULT_EVERY_S = 60.0
HOLIDAY_LOOKBACK_YEARS = 1


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def holidays_around(today: date) -> dict[str, Any]:
    """The previous and the next no-trade day (exchange and US bank holidays), with their names."""
    table: dict[date, str] = {}
    for year in range(today.year - HOLIDAY_LOOKBACK_YEARS, today.year + 2):
        table.update(market_clock.nyse_holidays(year))
        table.update(market_clock.bank_only_holidays(year))
    past = [d for d in table if d < today]
    future = [d for d in table if d > today]
    prev_day = max(past) if past else None
    next_day = min(future) if future else None
    return {"today_holiday": table.get(today),
            "previous_holiday": None if prev_day is None else {"date": prev_day.isoformat(), "name": table[prev_day],
                                                               "days_ago": (today - prev_day).days},
            "next_holiday": None if next_day is None else {"date": next_day.isoformat(), "name": table[next_day],
                                                           "days_left": (next_day - today).days}}


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context = None
        self._running = False
        self._every_s = DEFAULT_EVERY_S
        self._last_at = 0.0
        self._published = 0
        self._failed = 0
        self._last_error = ""
        self._last_summary = ""

    async def initialize(self, context: Any) -> None:
        self._context = context
        self._every_s = float((context.config or {}).get("publish_every_s", DEFAULT_EVERY_S))
        context.subscribe(EVENT_PULSE, self._on_pulse)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_pulse(self, payload: Any) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        now = _num(payload.get("official_time"))
        if now is None or now <= 0 or now - self._last_at < self._every_s:
            return
        self._last_at = now
        try:
            body = market_context.context(now)
            if body.get("available"):
                body["holidays"] = holidays_around(market_context.owner_date(now))
                t = body["time"]
                self._last_summary = "Q%d W%d/%d open=%s" % (t["quarter"], t["week_of_month"], t["weeks_in_month"],
                                                              ",".join(body["sessions"]["open_now"]) or "-")
        except Exception as exc:  # noqa: BLE001 -- a bad moment must not stop the pulse; it is counted and shown
            self._failed += 1
            self._last_error = "%s: %s" % (type(exc).__name__, exc)
            return
        await self._context.publish(EVENT_OUT, {"id": "time_context", "official_time": now, **body})
        self._published += 1

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "published": self._published, "failed": self._failed}

    async def restore(self, state: Any) -> None:
        if isinstance(state, dict):
            self._published = int(_num(state.get("published")) or 0)
            self._failed = int(_num(state.get("failed")) or 0)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        if not market_context.available():
            return HealthStatus(state=HealthState.DEGRADED, message="TIME_ZONE_DATABASE_MISSING")
        state = HealthState.DEGRADED if self._failed and not self._published else HealthState.HEALTHY
        return HealthStatus(state=state, message="published=%d failed=%d %s %s" % (
            self._published, self._failed, self._last_summary or "-", self._last_error or ""))
