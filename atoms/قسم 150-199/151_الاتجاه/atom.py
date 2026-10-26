from __future__ import annotations

import asyncio

from collections import deque
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.live_analysis import live_analyzer
from shared.section_contract import section_atom
from shared.cycle_identity import cycle_key_of

ATOM_VERSION = "2.5.0"

# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): النوافذ أرقام المانيفست حرفيًّا — كانت
# تُضرب في 50/السرعة (الحيّ ×1.32: أقلّ الشموع 20⟵26 · ميل البطيء 3⟵4). المتوسّطان نفساهما (10/20) لم
# يمسّهما المفتاح يومًا، فـ«متوسّط 20» الذي تقرؤه البطاقة 414 لا يتغيّر.

EVENT_IN = "market_data.candle_closed"
#: الأطر التي تُعاد حقيقتها المحفوظة عند الإقلاع (٢٠٢٦-١٠-٠٨) — تُغلق شمعتها كلّ ساعة فأكثر.
#: مهلة إعادة النشر بعد البدء — بعد اكتمال الإقلاع كلّه (٢٠٢٦-١٠-٠٨).
BOOT_REPUBLISH_DELAY_S = 30.0
_REPUBLISH_AT_BOOT = ("1h", "4h")
EVENT_OUT = "analysis.trend.state"

METHOD = "ema_slope"

SIGNAL_UP = "up"
SIGNAL_DOWN = "down"
SIGNAL_NEUTRAL = "sideways"

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"

PHASE_NONE = "none"
PHASE_EMERGING = "emerging"
PHASE_ESTABLISHED = "established"
PHASE_WEAKENING = "weakening"

STRENGTH_WEAK = "weak"
STRENGTH_MODERATE = "moderate"
STRENGTH_STRONG = "strong"

POS_ABOVE = "above_fast"
POS_BELOW = "below_fast"
POS_AT = "at_fast"

QUALITY_GOOD = "good"
QUALITY_LOW = "low"

WARN_INSUFFICIENT = "insufficient_candles"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_CANDLES = "NO_CANDLES_YET"

_PERCENT = 100.0
_SCORE_MAX = 100.0
_DISTANCE_SCALE = 30.0
_SLOPE_SCALE = 60.0
_CONFIRM_CONDITIONS = 3.0
_EMA_MULTIPLIER = 2.0


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


@section_atom("150", "151")
@live_analyzer("trend", EVENT_OUT)
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._fast = 20
        self._slow = 50
        self._k = 5
        self._min_candles = 55
        self._flat_slope_pct = 0.02
        self._flat_distance_pct = 0.05
        self._strong_score = 80.0
        self._moderate_score = 45.0
        self._emerging_bars = 3
        self._alpha_fast = 0.0
        self._alpha_slow = 0.0
        self._state: dict[tuple, dict[str, Any]] = {}
        self._candles_seen = 0
        self._emitted = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._fast = int(cfg["ema_fast"])
        self._slow = int(cfg["ema_slow"])
        self._k = int(cfg["slope_lookback"])
        self._min_candles = int(cfg["min_candles"])
        self._flat_slope_pct = float(cfg["flat_slope_pct"])
        self._flat_distance_pct = float(cfg["flat_distance_pct"])
        self._strong_score = float(cfg["strong_score"])
        self._moderate_score = float(cfg["moderate_score"])
        self._emerging_bars = int(cfg["emerging_bars"])
        self._alpha_fast = _EMA_MULTIPLIER / (self._fast + 1.0)
        self._alpha_slow = _EMA_MULTIPLIER / (self._slow + 1.0)
        context.subscribe(EVENT_IN, self._on_candle)

    async def start(self) -> None:
        self._running = True
        # الإقلاع يبدأ الذرّات واحدةً بعد واحدة بترتيب أرقامها — فالنشر فورًا يسبق اشتراك البطاقة 414.
        # يُؤجَّل حتّى يكتمل الإقلاع كلّه (قِيس ~7 ث).
        if any(timeframe in _REPUBLISH_AT_BOOT for (_, timeframe) in self._state):
            self._republish_task = asyncio.ensure_future(self._deferred_republish())

    async def _deferred_republish(self) -> None:
        try:
            await asyncio.sleep(BOOT_REPUBLISH_DELAY_S)
            if self._running:
                await self._republish_restored()
        except asyncio.CancelledError:
            pass

    async def _republish_restored(self) -> None:
        # ٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق): شمعة الأربع ساعات تُغلق كلّ أربع ساعات — فبعد إقلاعٍ تبقى البطاقة 414 بلا
        # اتّجاهها حتّى الإغلاق التالي («حقيقة ناقصة»؛ وإن كان الإقلاع قبيل نافذة المالك ضاعت النافذة). الحالة
        # المحفوظة تحمل المتوسّطين وآخر إغلاق ⟸ تُعاد حقيقتها الخام للأطر الطويلة عند الإقلاع.
        if self._context is None:
            return
        for (symbol, timeframe), st in list(self._state.items()):
            if timeframe not in _REPUBLISH_AT_BOOT or st.get("last_close") is None or st["count"] < self._slow:
                continue
            await self._context.publish(EVENT_OUT, {
                "symbol": symbol, "id": "trend", "timeframe": timeframe,
                "cycle_id": "restored|%s|%s" % (symbol, timeframe), "status": "ok",
                "warnings": ["RESTORED_AT_BOOT"],
                "metadata": {"method": METHOD, "timeframe": timeframe, "restored": True,
                             "close": st["last_close"], "ema_fast_value": st["ema_fast"],
                             "ema_slow_value": st["ema_slow"], "candles": st["count"],
                             "period_start": st.get("last_start")}})
            self._emitted += 1

    async def stop(self) -> None:
        self._running = False
        task = getattr(self, "_republish_task", None)
        if task is not None and not task.done():
            task.cancel()

    async def shutdown(self) -> None:
        await self.stop()

    # Owner stamp 2026-08-21: the candle camp keeps its own memory, and it MUST
    # survive a restart. Measured before this: the atom asks for 55 closed
    # candles and the candle is one minute, so every reboot silenced the slow
    # camp for 55 minutes while it recounted from zero. The live wrapper stores
    # its tick state under "live_analysis"; this state rides beside it as
    # "atom" -- the wrapper chains both, it no longer replaces this one.
    async def snapshot(self) -> dict[str, Any]:
        return {
            "candles_seen": self._candles_seen,
            "emitted": self._emitted,
            # tuple keys and a deque cannot be serialised: the key is split into
            # explicit fields and the slope history becomes a plain list.
            "scopes": [{"symbol": symbol, "timeframe": timeframe,
                        "ema_fast": row["ema_fast"], "ema_slow": row["ema_slow"],
                        "slow_hist": list(row["slow_hist"]),
                        "count": row["count"], "prev_dir": row["prev_dir"],
                        "bars_in_dir": row["bars_in_dir"], "last_close": row.get("last_close"),
                        "last_start": row.get("last_start")}
                       for (symbol, timeframe), row in self._state.items()],
        }

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self._candles_seen = int(state.get("candles_seen") or 0)
        self._emitted = int(state.get("emitted") or 0)
        self._state = {}
        for row in state.get("scopes") or []:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            history = deque(maxlen=self._k + 1)
            for value in row.get("slow_hist") or []:
                number = _to_float(value)
                if number is not None:
                    history.append(number)
            fast = _to_float(row.get("ema_fast"))
            slow = _to_float(row.get("ema_slow"))
            if fast is None or slow is None:
                continue
            self._state[(symbol, str(row.get("timeframe") or ""))] = {
                "ema_fast": fast, "ema_slow": slow, "slow_hist": history,
                "count": int(row.get("count") or 0),
                "prev_dir": str(row.get("prev_dir") or SIGNAL_NEUTRAL),
                "bars_in_dir": int(row.get("bars_in_dir") or 0),
                "last_close": _to_float(row.get("last_close")),
                "last_start": _to_float(row.get("last_start")),
            }

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        close = _to_float(payload.get("close"))
        if not symbol or close is None:
            return
        symbol = str(symbol)
        timeframe = str(payload.get("timeframe", ""))
        period_start = payload.get("period_start", payload.get("timestamp", ""))
        cycle_id = cycle_key_of(payload, symbol=symbol, timeframe=timeframe, period_start=period_start)
        key = (symbol, timeframe)
        st = self._state.get(key)
        if st is None:
            # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): ذاكرة الميل `ميل+1` — كانت
            # `ميل×5+1` لتتّسع لأبطأ سرعة؛ والميل لا يقرأ إلّا آخر `ميل+1` منها.
            st = {"ema_fast": close, "ema_slow": close,
                  "slow_hist": deque(maxlen=self._k + 1), "count": 0,
                  "prev_dir": SIGNAL_NEUTRAL, "bars_in_dir": 0}
            st["slow_hist"].append(close)
            self._state[key] = st
        else:
            st["ema_fast"] = self._alpha_fast * close + (1.0 - self._alpha_fast) * st["ema_fast"]
            st["ema_slow"] = self._alpha_slow * close + (1.0 - self._alpha_slow) * st["ema_slow"]
            st["slow_hist"].append(st["ema_slow"])
        st["count"] += 1
        st["last_close"] = close
        st["last_start"] = _to_float(period_start)
        self._candles_seen += 1
        await self._emit(symbol, timeframe, cycle_id, close, st, _to_float(period_start))

    def _slope_pct(self, st: dict[str, Any], w: int) -> float:
        hist = st["slow_hist"]
        if len(hist) <= w:
            return 0.0
        base = hist[-(w + 1)]
        if base == 0:
            return 0.0
        return (st["ema_slow"] - base) / base * _PERCENT / w

    def _strength(self, score: int, signal: str) -> str:
        if signal == SIGNAL_NEUTRAL or score < self._moderate_score:
            return STRENGTH_WEAK
        if score >= self._strong_score:
            return STRENGTH_STRONG
        return STRENGTH_MODERATE

    def _phase(self, signal: str, direction: str, slope_flat: bool,
               price_confirm: bool, st: dict[str, Any]) -> str:
        if signal == SIGNAL_NEUTRAL:
            return PHASE_NONE
        bars = st["bars_in_dir"] + 1 if direction == st["prev_dir"] else 1
        if bars <= self._emerging_bars:
            return PHASE_EMERGING
        if slope_flat or not price_confirm:
            return PHASE_WEAKENING
        return PHASE_ESTABLISHED

    def _track(self, direction: str, st: dict[str, Any]) -> None:
        if direction == st["prev_dir"]:
            st["bars_in_dir"] += 1
        else:
            st["bars_in_dir"] = 1
            st["prev_dir"] = direction

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str,
                    close: float, st: dict[str, Any],
                    period_start: float | None = None) -> None:
        if self._context is None:
            return
        ema_fast = st["ema_fast"]
        ema_slow = st["ema_slow"]
        base = {"symbol": symbol, "id": "trend", "cycle_id": cycle_id,
                "timeframe": timeframe}
        meta = {"method": METHOD, "timeframe": timeframe,
                "ema_fast": self._fast, "ema_slow": self._slow}
        if st["count"] < self._min_candles or ema_slow == 0:
            await self._context.publish(EVENT_OUT, {
                **base, "status": STATUS_INSUFFICIENT, "signal": SIGNAL_NEUTRAL,
                "score": 0, "confidence": 0.0, "strength": STRENGTH_WEAK,
                "phase": PHASE_NONE, "quality": QUALITY_LOW,
                "warnings": [WARN_INSUFFICIENT], "metadata": meta})
            self._emitted += 1
            return
        distance_pct = (ema_fast - ema_slow) / ema_slow * _PERCENT
        slope_pct = self._slope_pct(st, self._k)
        if ema_fast > ema_slow:
            direction = SIGNAL_UP
        elif ema_fast < ema_slow:
            direction = SIGNAL_DOWN
        else:
            direction = SIGNAL_NEUTRAL
        if close > ema_fast:
            position = POS_ABOVE
        elif close < ema_fast:
            position = POS_BELOW
        else:
            position = POS_AT
        slope_confirm = ((direction == SIGNAL_UP and slope_pct > self._flat_slope_pct) or
                         (direction == SIGNAL_DOWN and slope_pct < -self._flat_slope_pct))
        price_confirm = ((direction == SIGNAL_UP and position == POS_ABOVE) or
                         (direction == SIGNAL_DOWN and position == POS_BELOW))
        entangled = abs(distance_pct) < self._flat_distance_pct
        slope_flat = abs(slope_pct) < self._flat_slope_pct
        confirmations = int(slope_confirm) + int(price_confirm)
        if direction == SIGNAL_NEUTRAL or (entangled and slope_flat) or confirmations == 0:
            signal = SIGNAL_NEUTRAL
            score = 0
        else:
            signal = direction
            score = int(round(min(
                _SCORE_MAX,
                abs(distance_pct) * _DISTANCE_SCALE + abs(slope_pct) * _SLOPE_SCALE)))
        dir_exists = 0 if direction == SIGNAL_NEUTRAL else 1
        confidence = round((dir_exists + int(slope_confirm) + int(price_confirm)) / _CONFIRM_CONDITIONS, 2)
        strength = self._strength(score, signal)
        phase = self._phase(signal, direction, slope_flat, price_confirm, st)
        self._track(direction, st)
        meta.update({"ema_distance": round(distance_pct, 2),
                     "ema_slope": round(slope_pct, 4), "price_position": position,
                     # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): الحقيقة الخام نفسها — الإغلاق وقيمتا المتوسّطين —
                     # كي تقرأها الاستراتيجيّات بدل أن تعيد حسابها (بطاقة 414: الإغلاق مقابل متوسّط 20).
                     "close": close, "ema_fast_value": ema_fast, "ema_slow_value": ema_slow,
                     "candles": st["count"],
                     # ٢٠٢٦-١٠-٠٨ (ختم المالك «صلح NQ»): بداية الشمعة التي حُسبت منها الحقيقة — تعرف بها
                     # البطاقة 414 أنّ حقيقة الساعة/الأربع ساعات هي حقيقة لحظة الزناد لا ما قبلها.
                     "period_start": period_start})
        await self._context.publish(EVENT_OUT, {
            **base, "status": STATUS_OK, "signal": signal, "score": score,
            "confidence": confidence, "strength": strength, "phase": phase,
            "quality": QUALITY_GOOD, "warnings": [], "metadata": meta})
        self._emitted += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._candles_seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_CANDLES,
                                details={"tracked": len(self._state)})
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="candles=%d emitted=%d tracked=%d" % (
                self._candles_seen, self._emitted, len(self._state)),
            details={"candles": self._candles_seen, "emitted": self._emitted,
                     "tracked": len(self._state)})
