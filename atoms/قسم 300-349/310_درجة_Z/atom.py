from __future__ import annotations

import math
from collections import deque
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.section_contract import section_atom
from shared.cycle_identity import cycle_key_of
from shared.atom_evidence import window_evidence

WEIGHT = 5.882353
ATOM_VERSION = "1.5.0"
EVENT_IN = "market_data.candle_closed"
EVENT_OUT = "stats.zscore.state"

METHOD = "rolling_zscore"
ID_ZSCORE = "zscore"

SIGNAL_EXTREME = "extreme"
SIGNAL_NORMAL = "normal"

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"

QUALITY_GOOD = "good"
QUALITY_LOW = "low"

WARN_INSUFFICIENT = "insufficient_data_points"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_TICKS = "NO_TICKS_YET"

_MIN_POINTS = 2
_VALUE_DP = 6
# مقياس |z| المقيس في المشروع (405 v2.5.0، ٢٠٢٦-٠٩-١٩): 99.9٪ من |z| دون خمسة على أربعة
# رموز × ١٢٠ ألف تِكّة ⟸ |z| = 5 هو كامل الاتّجاه (±100). لا عيارٌ جديد يُخترع هنا.
_Z_FULL_SCALE = 5.0
_DIRECTION_FULL = 100.0


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


@section_atom("300", "310")
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._window_size = 20
        self._z_threshold = 2.0
        self._state: dict[tuple, deque] = {}
        self._ticks_seen = 0
        self._extremes = 0
        self._emitted = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._window_size = int(context.config["window_size"])
        self._z_threshold = float(context.config["z_threshold"])
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
        # ⛔ المفتاح كان `(symbol, timeframe)` — بلا حساب ولا وسيط. هو العطب
        # نفسه الذي أفسد ٤٠٥ يومًا كاملًا (نافذةٌ واحدة تخلط حسابين فتخرج
        # `|z|` بالمليارات). كامنٌ اليوم لأنّ الحساب واحد، ويستيقظ صامتًا
        # لحظة وصول حسابٍ ثانٍ — فأُغلق بالهوية الكاملة لا بالتعليق.
        key = (str(payload.get("account_id") or ""),
               str(payload.get("broker") or ""), symbol, timeframe)
        window = self._state.get(key)
        if window is None:
            window = deque(maxlen=self._window_size)
            self._state[key] = window
        window.append(price)
        self._ticks_seen += 1
        await self._emit(symbol, timeframe, cycle_id, window)

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str,
                    window: deque) -> None:
        if self._context is None:
            return
        count = len(window)
        base = {"symbol": symbol, "id": ID_ZSCORE, "cycle_id": cycle_id,
                "timeframe": timeframe}
        meta = {"method": METHOD, "timeframe": timeframe, "window": self._window_size,
                "count": count, "threshold": self._z_threshold}
        if count < _MIN_POINTS:
            await self._context.publish(EVENT_OUT, {
                **window_evidence(have=len(window), need=self._window_size),
                **base, "status": STATUS_INSUFFICIENT, "signal": SIGNAL_NORMAL,
                "score": 0, "confidence": 0.0, "quality": QUALITY_LOW,
                "warnings": [WARN_INSUFFICIENT], "metadata": meta})
            self._emitted += 1
            return
        mean = sum(window) / count
        variance = sum((x - mean) ** 2 for x in window) / (count - 1)
        std = math.sqrt(variance)
        z = (window[-1] - mean) / std if std > 0 else 0.0
        signal = SIGNAL_EXTREME if abs(z) >= self._z_threshold else SIGNAL_NORMAL
        if signal == SIGNAL_EXTREME:
            self._extremes += 1
        meta["value"] = round(z, _VALUE_DP)
        meta["mean"] = round(mean, _VALUE_DP)
        meta["std"] = round(std, _VALUE_DP)
        # ٢٠٢٦-١٠-٠٥ (ختم المالك «ما بدي ولا قسم ما يشارك ل صفقة nq»): `z` نفسه اتّجاهٌ مقيس —
        # موضع السعر من متوسّط نافذته (موجبٌ فوقه). كان يُنشر «normal/extreme» بلا اتّجاه فيُختم
        # مجهولًا ⟸ `NOT_READY` لوحدةٍ إلزاميّة ⟸ قسم الإحصاء كلّه خارج وزن القرار.
        direction = max(-_DIRECTION_FULL, min(_DIRECTION_FULL, z / _Z_FULL_SCALE * _DIRECTION_FULL))
        await self._context.publish(EVENT_OUT, {
            **window_evidence(have=len(window), need=self._window_size),
            "direction": round(direction, 4),
            **base, "status": STATUS_OK, "signal": signal, "score": 0,
            "confidence": 1.0, "quality": QUALITY_GOOD, "weight": WEIGHT,
            "analysis_state": "READY", "ready": True, "warnings": [], "metadata": meta})
        self._emitted += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._ticks_seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_TICKS,
                                details={"tracked": len(self._state)})
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="ticks=%d extremes=%d emitted=%d tracked=%d" % (
                self._ticks_seen, self._extremes, self._emitted, len(self._state)),
            details={"ticks": self._ticks_seen, "extremes": self._extremes,
                     "emitted": self._emitted, "tracked": len(self._state)})
