"""أثر الوقت (159) — موضع الشمعة في يوم السوق وأسبوعه وشهره: حقيقة خام بلا حكم (عقد الحقائق ١٠-٠٧).

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): كانت تعدّ اليوم والأسبوع والشهر بساعة غرينتش (فرق صفر من
بيانها)، والاثنين والجمعة رقمين ثابتين في البيان، ونهاية الشهر بالتقويم لا بأيّام التداول. صارت تقرأ
`shared/market_clock` وحدها، ولا رقم في بيانها:

  اليوم = يوم الوسيط (يُغلق مع إغلاق نيويورك 17:00؛ ساعة الخادم = نيويورك + 7) لا يوم نيويورك ولا غرينتش، بالدليل:
  (١) الذرّة 103 تبني شموع الأربع ساعات واليوم على يوم الوسيط، فشمعة الاثنين اليوميّة تبدأ الأحد 17:00 نيويورك —
      بغرينتش أو بنيويورك تُنسب إلى الأحد («عطلة»)، وبيوم الوسيط إلى الاثنين. مقيس على 103 نفسها: غرينتش «يصنع
      يوم أحدٍ من ساعتين»؛ (٢) عليه قيست البطاقة 414 وعليه شارت المالك؛ (٣) جلسة عقد الناسداك تُفتح الأحد 18:00
      نيويورك (جدول 117 الأسبوعيّ) فمساء الأحد أوّل أسبوع التداول لا آخر عطلته.
  وموضع الأسبوع والشهر بأيّام التداول (قواعد البورصة) — تعريف 117 نفسه: افتتاح الأسبوع أوّل يوم تداولٍ فيه
  وإغلاقه آخره، ونهاية الشهر آخر يوم تداولٍ فيه، ويوم عطلة السوق في أيّام العمل `market_holiday`.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared import market_clock as mc
from shared.live_analysis import live_analyzer
from shared.section_contract import section_atom
from shared.cycle_identity import cycle_key_of

ATOM_VERSION = "2.5.0"

EVENT_IN = "market_data.candle_closed"
EVENT_OUT = "analysis.time.state"

METHOD = "broker_day_calendar"

PHASE_WEEK_OPEN = "week_open"
PHASE_WEEK_CLOSE = "week_close"
PHASE_MID_WEEK = "mid_week"
PHASE_WEEKEND = "weekend"
PHASE_HOLIDAY = "market_holiday"

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_CANDLES = "NO_CANDLES_YET"

_MONTHS_PER_QUARTER = 3
_WEEKDAY_NAMES = tuple(name.lower() for name in mc.WEEKDAY_NAMES)


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _phase(day: date, market: mc.MarketDay) -> str:
    if day.weekday() >= mc.SATURDAY:
        return PHASE_WEEKEND
    if not market.is_trading_day:
        return PHASE_HOLIDAY
    if market.is_week_start:
        return PHASE_WEEK_OPEN
    if market.is_week_end:
        return PHASE_WEEK_CLOSE
    return PHASE_MID_WEEK


def time_facts(ts: float) -> tuple[str, dict[str, Any]]:
    """(طور الأسبوع، الحقائق) عند لحظةٍ بغرينتش — على يوم الوسيط وأيّام التداول بقواعد البورصة."""
    broker = mc.broker_day(ts)
    day = broker.day
    market = mc.market_day(day, mc.rule_holidays((day.year - 1, day.year, day.year + 1)))
    return _phase(day, market), {
        "hour": broker.hour,
        "weekday": day.weekday(),
        "weekday_name": _WEEKDAY_NAMES[day.weekday()],
        "month": day.month,
        "quarter": (day.month - 1) // _MONTHS_PER_QUARTER + 1,
        "day_of_month": day.day,
        "is_month_start": market.is_month_start,
        "is_month_end": market.is_month_end,
        "is_quarter_end": market.is_month_end and day.month in mc.QUARTER_MONTHS,
        "broker_day_date": day.isoformat(),
        "is_trading_day": market.is_trading_day,
    }


@section_atom("150", "159")
@live_analyzer("time", EVENT_OUT)
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._candles_seen = 0
        self._emitted = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        context.subscribe(EVENT_IN, self._on_candle)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    # Owner stamp 2026-08-21: audited for the candle-memory-loss defect that
    # hit the other analyzers in this section (151-165) -- this one has none
    # to lose. Every emission is a pure function of the incoming candle's own
    # timestamp; nothing here accumulates across candles. The only
    # insufficient_data path is a missing timestamp on the CURRENT candle,
    # not a warm-up window, so `_candles_seen`/`_emitted` are diagnostic
    # counters only and do not gate readiness. No snapshot()/restore() added:
    # inventing a save for state that does not exist would just add a place
    # for the next defect to hide.

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        if not symbol:
            return
        symbol = str(symbol)
        timeframe = str(payload.get("timeframe", ""))
        period_start = payload.get("period_start", payload.get("timestamp", ""))
        cycle_id = cycle_key_of(payload, symbol=symbol, timeframe=timeframe, period_start=period_start)
        self._candles_seen += 1
        ts = _to_float(payload.get("period_start", payload.get("timestamp")))
        if ts is None:
            await self._emit_insufficient(symbol, timeframe, cycle_id)
            return
        await self._emit(symbol, timeframe, cycle_id, ts)

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str,
                    ts: float) -> None:
        if self._context is None:
            return
        phase, facts = time_facts(ts)
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): نُزعت «درجة/ثقة/جودة» (100 · 60 · 40) — حكمٌ كان
        # عقد الحقائق ينزعه عند الختم، ويتسرّب منه رقمٌ إلى `metadata.pattern_score` عبر التوأم.
        await self._context.publish(EVENT_OUT, {
            "symbol": symbol, "id": "time", "cycle_id": cycle_id,
            "timeframe": timeframe, "status": STATUS_OK, "signal": phase, "warnings": [],
            "metadata": {"method": METHOD, "timeframe": timeframe, **facts}})
        self._emitted += 1

    async def _emit_insufficient(self, symbol: str, timeframe: str,
                                 cycle_id: str) -> None:
        if self._context is None:
            return
        await self._context.publish(EVENT_OUT, {
            "symbol": symbol, "id": "time", "cycle_id": cycle_id,
            "timeframe": timeframe,
            "status": STATUS_INSUFFICIENT, "signal": PHASE_MID_WEEK, "warnings": ["no_timestamp"],
            "metadata": {"method": METHOD, "timeframe": timeframe}})
        self._emitted += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._candles_seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_CANDLES)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="candles=%d emitted=%d" % (self._candles_seen, self._emitted),
            details={"candles": self._candles_seen, "emitted": self._emitted})
