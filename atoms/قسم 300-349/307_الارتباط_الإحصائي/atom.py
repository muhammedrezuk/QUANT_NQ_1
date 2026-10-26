from __future__ import annotations

import math
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.section_contract import section_atom
from shared.atom_evidence import window_evidence
from shared.cycle_identity import cycle_key_of

WEIGHT = 5.882353
ATOM_VERSION = "1.7.0"
EVENT_IN = "market_data.candle_closed"
EVENT_OUT = "stats.correlation.state"

METHOD = "rolling_pearson_returns"
ID_CORRELATION = "correlation"

SIGNAL_STRONG = "strong"
SIGNAL_MODERATE = "moderate"
SIGNAL_WEAK = "weak"
SIGNAL_REFERENCE = "reference"

DIRECTION_POSITIVE = "positive"
DIRECTION_INVERSE = "inverse"
DIRECTION_NONE = "none"

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"

QUALITY_GOOD = "good"
QUALITY_LOW = "low"

WARN_INSUFFICIENT = "insufficient_overlap"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_TICKS = "NO_TICKS_YET"

_PERCENT = 100.0
_MIN_OVERLAP = 10

# ٢٠٢٦-٠٩-١٦ — سلّة المزاوجة الزمنية. كانت السلسلتان تُزاوَجان على
# `period_start` وهو `sequence`: عدّادٌ **فريد لكل تِكّة على مستوى الحساب**،
# فتِكّتا رمزين لا تحملان الرقم نفسه أبدًا ⇒ التداخل صفر دائمًا ⇒ الذرّة
# لم تحسب ارتباطًا واحدًا قطّ (مقيس: `insufficient_overlap` بعد 16 زوجًا،
# و`status=insufficient_data · weight=None` في لقطة الإنتاج). المزاوجة
# الآن على الطابع الزمني للمصدر مُسلَّلًا: قِيس على الجسر الحيّ أنّ الرموز
# السبعة تصل خلال 1.948 ثانية وأنّ خمسة منها تقع في سلّة الثانية الواحدة.
# ⛔ هذا إصلاح عطل لا تغيير عيار: العتبات (`strong`/`moderate`/`window`)
#    كما اعتمدها المالك، ولم تُمسّ.
_PAIR_BUCKET_S = 1.0
_DP = 4


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _pearson(xs: list, ys: list) -> float:
    n = len(xs)
    if n == 0:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = 0.0
    var_x = 0.0
    var_y = 0.0
    for x, y in zip(xs, ys):
        dx = x - mean_x
        dy = y - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy
    denom = math.sqrt(var_x * var_y)
    return cov / denom if denom > 0.0 else 0.0


@section_atom("300", "307")
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._reference = "USTEC"
        self._window = 30
        self._strong = 0.7
        self._moderate = 0.4
        self._state: dict[tuple, dict[str, Any]] = {}
        self._ticks_seen = 0
        self._emitted = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._reference = str(cfg["reference_symbol"])
        self._window = int(cfg["window"])
        self._strong = float(cfg["strong_threshold"])
        self._moderate = float(cfg["moderate_threshold"])
        context.subscribe(EVENT_IN, self._on_tick)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        price = _to_float(payload.get("close", payload.get("price")))
        if not symbol or price is None:
            return
        symbol = str(symbol)
        timeframe = str(payload.get("timeframe") or "tick")
        period_start = str(payload.get("period_start", payload.get("sequence")) or "")
        cycle_id = cycle_key_of(payload, symbol=symbol, timeframe=timeframe, period_start=period_start)
        # مفتاح المزاوجة وحده صار زمنيًّا؛ `period_start` يبقى للمعرّف كما هو
        # كي لا تنقطع وصلة الدورة مع ٣٠٠.
        stamp = _to_float(payload.get("exchange_timestamp"))
        if stamp is None:
            stamp = _to_float(payload.get("timestamp"))
        bucket = None if stamp is None else int(stamp // _PAIR_BUCKET_S)
        # ⛔ العطب نفسه الذي أفسد ٤٠٥: مفتاحٌ بلا حساب ولا وسيط. وهنا
        # أخطرُ منه — المرجع يُقرأ بالمفتاح ذاته، فحسابان يقرأ كلٌّ
        # منهما عوائد الآخر مرجعًا. الهوية تُحمل في `scope` وتُستعمل
        # في الكتابة والقراءة معًا.
        scope = (str(payload.get("account_id") or ""),
                 str(payload.get("broker") or ""))
        key = (*scope, symbol, timeframe)
        self._ticks_seen += 1
        st = self._state.get(key)
        if st is None:
            st = {"prev_close": price, "rets": {}}
            self._state[key] = st
            await self._emit_insufficient(symbol, timeframe, cycle_id)
            return
        prev_close = st["prev_close"]
        st["prev_close"] = price
        if not prev_close:
            await self._emit_insufficient(symbol, timeframe, cycle_id)
            return
        ret = (price - prev_close) / prev_close
        # ٢٠٢٦-٠٩-١٦ (تصحيحٌ لإصلاح اليوم نفسه) — النافذة تُعدّ **سلالًا
        # زمنية لا تِكّات**. كانت طابورًا بسقف من الأزواج، فالرمز الكثيف
        # يملأ ثلاثينه من سلالٍ قليلة ويبقى تداخله دون الحدّ أبدًا: قِيس
        # أنّ XAUUSD (خمس دورات مفتوحة) صفرُ `ok` بينما BTCUSD وGBPUSD
        # (دورة واحدة) يبلغان 18–30 نقطة. النافذة الآن ثلاثون **سلّة**
        # لكل رمز بالتساوي، وآخر عائد في السلّة يفوز.
        rets = st["rets"]
        if bucket is not None:
            rets[bucket] = ret
            if len(rets) > self._window:
                rets.pop(next(iter(rets)))
        if symbol == self._reference:
            # المرجع لا يرتبط بنفسه فلا صوت له: `None` تُبقي العقد على
            # `DIRECTION_UNKNOWN` بدل أن يُدسّ صفرٌ يُقرأ حيادًا مقيسًا.
            await self._emit(symbol, timeframe, cycle_id, SIGNAL_REFERENCE,
                             DIRECTION_NONE, int(_PERCENT), 1.0, 1.0,
                             len(st["rets"]), None)
            return
        ref_st = self._state.get((*scope, self._reference, timeframe))
        if ref_st is None:
            await self._emit_insufficient(symbol, timeframe, cycle_id)
            return
        ref_map = ref_st["rets"]
        xs = []
        ys = []
        for period, value in st["rets"].items():
            other = ref_map.get(period)
            if other is not None:
                xs.append(value)
                ys.append(other)
        points = len(xs)
        if points < _MIN_OVERLAP:
            await self._emit_insufficient(symbol, timeframe, cycle_id)
            return
        corr = _pearson(xs, ys)
        mag = abs(corr)
        if mag >= self._strong:
            signal = SIGNAL_STRONG
        elif mag >= self._moderate:
            signal = SIGNAL_MODERATE
        else:
            signal = SIGNAL_WEAK
        if corr > 0.0:
            direction = DIRECTION_POSITIVE
        elif corr < 0.0:
            direction = DIRECTION_INVERSE
        else:
            direction = DIRECTION_NONE
        score = int(round(min(_PERCENT, mag * _PERCENT)))
        confidence = round(min(1.0, points / self._window), 2) if self._window > 0 else 0.0
        # ٢٠٢٦-٠٩-١٨ (ختم `NQ`) — الارتباط صار **يصوّت**. وإشارتُه وحدها
        # ليست اتجاهًا: ارتباطٌ موجب مع المرجع يعني «يتحرّك معه» لا «اشترِ».
        # فالصوت = اتجاه المرجع × إشارة الارتباط، وقوّتُه |الارتباط|:
        #   مرجعٌ صاعد + ارتباطٌ موجب  ⇒ صعود
        #   مرجعٌ صاعد + ارتباطٌ عكسيّ ⇒ هبوط
        # ويُحسب من `ys` (عوائد المرجع المتداخلة) لا من نافذته كلّها، كي
        # يكون الاتجاه من العيّنة التي بُني عليها الارتباط نفسه.
        ref_drift = sum(ys) / len(ys) if ys else 0.0
        if ref_drift > 0.0:
            ref_sign = 1.0
        elif ref_drift < 0.0:
            ref_sign = -1.0
        else:
            ref_sign = 0.0
        vote = max(-_PERCENT, min(_PERCENT, ref_sign * corr * _PERCENT))
        await self._emit(symbol, timeframe, cycle_id, signal, direction, score,
                         confidence, corr, points, vote)

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str, signal: str,
                    direction: str, score: int, confidence: float, corr: float,
                    points: int, vote: float | None) -> None:
        if self._context is None:
            return
        await self._context.publish(EVENT_OUT, {
            "symbol": symbol, "id": ID_CORRELATION, "cycle_id": cycle_id,
            "timeframe": timeframe,
            **window_evidence(have=points, need=self._window),
            **({"direction": round(vote, _DP)} if vote is not None else {}),
            "status": STATUS_OK, "signal": signal, "score": score,
            "confidence": confidence, "quality": QUALITY_GOOD, "weight": WEIGHT,
            "analysis_state": "READY", "ready": True, "warnings": [],
            "metadata": {"method": METHOD, "timeframe": timeframe,
                         "reference": self._reference, "direction": direction,
                         "value": round(corr, _DP), "points": points}})
        self._emitted += 1

    async def _emit_insufficient(self, symbol: str, timeframe: str,
                                 cycle_id: str) -> None:
        if self._context is None:
            return
        await self._context.publish(EVENT_OUT, {
            "symbol": symbol, "id": ID_CORRELATION, "cycle_id": cycle_id,
            "timeframe": timeframe,
            "status": STATUS_INSUFFICIENT, "signal": SIGNAL_WEAK, "score": 0,
            "confidence": 0.0, "quality": QUALITY_LOW, "warnings": [WARN_INSUFFICIENT],
            "metadata": {"method": METHOD, "timeframe": timeframe,
                         "reference": self._reference, "direction": DIRECTION_NONE}})
        self._emitted += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._ticks_seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_TICKS,
                                details={"tracked": len(self._state)})
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="ticks=%d emitted=%d tracked=%d" % (
                self._ticks_seen, self._emitted, len(self._state)),
            details={"ticks": self._ticks_seen, "emitted": self._emitted,
                     "tracked": len(self._state)})
