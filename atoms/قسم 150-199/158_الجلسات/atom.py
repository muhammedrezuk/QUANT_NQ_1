"""الجلسات (158) — أيّ الجلسات مفتوحة عند بداية كلّ شمعة: حقيقة خام بلا حكم (عقد الحقائق ١٠-٠٧).

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): ختم المالك «نعتمد ذرّة الوقت، ونصحّح محلّل الجلسات ليقرأ
التوقيت الصحيح». كانت هذه الذرّة تعدّ ساعة غرينتش في نوافذ ثابتة من بيانها (آسيا 0–9 · لندن 7–16 · نيويورك 12–21
· فرق صفر) بلا توقيتٍ صيفيّ ولا عطلة أسبوع ولا عطلة سوق — فتخطئ ساعةً نصف السنة وتعارض الذرّة 117. صارت تقرأ
`shared/market_clock.market_sessions` — التعريف الواحد الذي تقرؤه 117 نفسها: طوكيو 09:00–15:00 بتوقيتها · لندن
08:00–16:30 بتوقيتها · نيويورك النقديّة 09:30–16:00 بتوقيتها (وإغلاقها المبكّر وعطل البورصة بقواعدها) · التداخل ·
جدول عقد الناسداك الأسبوعيّ. ولا رقم ساعةٍ في البيان بعد اليوم.

وما لا تعرفه هنا: عطل لندن وطوكيو وما لا تعرفه القواعد الأمريكيّة يأتي من تقويم ميتاتريدر الذي تقرؤه 117 وحدها
— فتُعلن هذه الذرّة مصدر تقويمها (`trading_calendar_source = nyse_rules`) ولا تدّعي غيره.

مفردة `signal` باقية كما يقرؤها 506 (asia · london · new_york · overlap · closed) ومعها رمزا الساعة الدائمة
(round_clock_24h · open)؛ وجديدها `nq_globex`: عقد الناسداك وحده مفتوح — كانت تُقال «closed» والسوق يتداول.
"""
from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared import market_clock as mc
from shared.live_analysis import live_analyzer
from shared.section_contract import section_atom
from shared.cycle_identity import cycle_key_of

ATOM_VERSION = "2.5.0"

EVENT_IN = "market_data.candle_closed"
EVENT_OUT = "analysis.session.state"

METHOD = "market_clock"

SESSION_ASIA = "asia"
SESSION_LONDON = "london"
SESSION_NY = "new_york"
SESSION_OVERLAP = "overlap"
SESSION_CLOSED = "closed"
SESSION_GLOBEX_ONLY = mc.SESSION_GLOBEX
# ٢٠٢٦-٠٩-٠٧ (تصحيح المالك): «BTCUSD هاد لا فوركس CFD». الاسم القديم
# `crypto_symbols`/`crypto_24h` كان يوحي بسوق كريبتو، وهو ليس كذلك:
# BTCUSD عقد فروقات عبر وسيط الفوركس. المعنى المقصود **زمنيّ** لا
# سوقيّ — رمز يتداول على مدار الساعة خارج جلسات لندن ونيويورك وطوكيو.
SESSION_ROUND_CLOCK = "round_clock_24h"
SESSION_OPEN = "open"

# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): أسماء الساعة المشتركة ⟵ مفردات هذه الذرّة القديمة.
#: الجلسة «الآن» عند الساعة المشتركة ⟵ مفردة `signal`.
SIGNAL_OF = {mc.SESSION_OVERLAP: SESSION_OVERLAP, mc.SESSION_NY_CASH: SESSION_NY,
             mc.SESSION_LONDON: SESSION_LONDON, mc.SESSION_ASIA: SESSION_ASIA}
#: الجلسات المسمّاة الثلاث ⟵ `metadata.active` (بترتيبها القديم: آسيا · لندن · نيويورك).
ACTIVE_OF = {mc.SESSION_ASIA: SESSION_ASIA, mc.SESSION_LONDON: SESSION_LONDON, mc.SESSION_NY_CASH: SESSION_NY}

STATUS_OK = "ok"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_CANDLES = "NO_CANDLES_YET"

_SECONDS_PER_HOUR = 3600.0
_HOURS_PER_DAY = 24


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def session_facts(ts: float) -> tuple[str, dict[str, Any]]:
    """(مفردة الجلسة الآن، حقائقها) عند لحظةٍ بغرينتش — دالّة خالصة من الساعة المشتركة وحدها."""
    now = mc.market_sessions(ts)
    offsets = mc.clock_offsets(ts)
    return SIGNAL_OF.get(now.session_now, ""), {
        "hour_utc": int(ts // _SECONDS_PER_HOUR) % _HOURS_PER_DAY,
        "session_now": now.session_now,
        "cash_open": now.cash_open,
        "utc_offset_new_york_h": offsets["utc_offset_new_york_h"],
        "utc_offset_london_h": offsets["utc_offset_london_h"],
        "trading_calendar_source": mc.SOURCE_RULES,
        "active": [ACTIVE_OF[name] for name in now.sessions_open if name in ACTIVE_OF],
        "sessions_open": list(now.sessions_open),
    }


@section_atom("150", "158")
@live_analyzer("session", EVENT_OUT)
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._round_clock: set[str] = set()
        self._always_open: set[str] = set()
        self._candles_seen = 0
        self._emitted = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._round_clock = {str(s).upper() for s in cfg["round_clock_symbols"]}
        self._always_open = {str(s).upper() for s in cfg["always_open_symbols"]}
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
    # timestamp and the symbol lists from config; nothing here accumulates
    # across candles, so `_candles_seen`/`_emitted` are diagnostic counters
    # only and do not gate readiness (there is no insufficient_data state at
    # all). No snapshot()/restore() added: inventing a save for state that
    # does not exist would just add a place for the next defect to hide.

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        ts = _to_float(payload.get("period_start", payload.get("timestamp")))
        if not symbol or ts is None:
            return
        symbol = str(symbol)
        timeframe = str(payload.get("timeframe", ""))
        period_start = payload.get("period_start", payload.get("timestamp", ""))
        cycle_id = cycle_key_of(payload, symbol=symbol, timeframe=timeframe, period_start=period_start)
        self._candles_seen += 1
        await self._emit(symbol, timeframe, cycle_id, ts)

    def _signal(self, named: str, session_now: str, symbol: str) -> str:
        if named:
            return named
        su = symbol.upper()
        if su in self._round_clock:
            return SESSION_ROUND_CLOCK
        if su in self._always_open:
            return SESSION_OPEN
        return SESSION_GLOBEX_ONLY if session_now == mc.SESSION_GLOBEX else SESSION_CLOSED

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str, ts: float) -> None:
        if self._context is None:
            return
        named, facts = session_facts(ts)
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): نُزعت «درجة/ثقة/جودة» من الحمولة نفسها — حكمٌ
        # كان عقد الحقائق ينزعه عند الختم، ويتسرّب منه رقمٌ إلى `metadata.pattern_score` عبر التوأم.
        await self._context.publish(EVENT_OUT, {
            "symbol": symbol, "id": "session", "cycle_id": cycle_id,
            "timeframe": timeframe, "status": STATUS_OK,
            "signal": self._signal(named, facts["session_now"], symbol), "warnings": [],
            "metadata": {"method": METHOD, "timeframe": timeframe, **facts}})
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
