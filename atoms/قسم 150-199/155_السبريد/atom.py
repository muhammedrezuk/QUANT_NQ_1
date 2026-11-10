from __future__ import annotations

from collections import deque
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.live_analysis import live_analyzer
from shared.pips import to_pips
from shared.section_contract import section_atom
from shared.cycle_identity import cycle_key_of

ATOM_VERSION = "2.6.0"

# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): النوافذ أرقام المانيفست حرفيًّا — كانت
# تُضرب في 50/السرعة (الحيّ ×1.32: الأساس 24⟵32 · القصير 5⟵7 · الطويل 20⟵26 · أقلّ الشموع 16⟵21)،
# والذاكرة `الأساس` بعد أن كانت `الأساس×5` (القصير والطويل يُقرآن من نافذة الأساس نفسها).

EVENT_IN = "market_data.candle_closed"
EVENT_TICK = "market.tick.validated"
#: دلاء السبريد بالدقيقة تُحفظ يومًا ونصفًا — تكفي أطول شمعة (اليوم).
_BUCKET_KEEP_MIN = 2160
_FRAME_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _frame_seconds(label: str) -> int:
    try:
        return int(label[:-1]) * _FRAME_UNITS[label[-1]]
    except (KeyError, ValueError, IndexError):
        return 0
EVENT_OUT = "analysis.spread.state"

METHOD = "tick_spread"  # ١٠-١٢: كان range_expansion (أعلى − أدنى)

SIGNAL_EXPANSION = "expansion"
SIGNAL_CONTRACTION = "contraction"
SIGNAL_STABLE = "stable"

SIZE_WIDE = "wide"
SIZE_NARROW = "narrow"
SIZE_NORMAL = "normal"

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"

QUALITY_GOOD = "good"
QUALITY_LOW = "low"

WARN_INSUFFICIENT = "insufficient_candles"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_CANDLES = "NO_CANDLES_YET"

_SCORE_MAX = 100.0
_EXPANSION_SCALE = 100.0


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


@section_atom("150", "155")
@live_analyzer("spread", EVENT_OUT)
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._baseline_window = 50
        self._exp_short = 5
        self._exp_long = 20
        self._exp_mult = 1.3
        self._wide_mult = 1.5
        self._narrow_mult = 0.6
        self._min_candles = 20
        self._ranges: dict[tuple, deque] = {}
        self._spread_buckets: dict[str, dict[int, list]] = {}
        self._last_peak: dict[tuple, float] = {}
        self._last_price: dict[tuple, float | None] = {}
        self._candles_seen = 0
        self._emitted = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._baseline_window = int(cfg["baseline_window"])
        self._exp_short = int(cfg["exp_short"])
        self._exp_long = int(cfg["exp_long"])
        self._exp_mult = float(cfg["exp_mult"])
        self._wide_mult = float(cfg["wide_mult"])
        self._narrow_mult = float(cfg["narrow_mult"])
        self._min_candles = int(cfg["min_candles"])
        context.subscribe(EVENT_IN, self._on_candle)
        context.subscribe(EVENT_TICK, self._on_tick)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    # Owner stamp 2026-08-21: the live wrapper used to REPLACE snapshot/
    # restore outright, wiping this atom's own range history on every
    # restart. Measured effect: `min_candles` (20 by default) closed candles
    # are required before it leaves insufficient_data, so a reboot silenced
    # spread for 20 candles every time. The wrapper now chains both states --
    # "live_analysis" for its own tick memory, "atom" for this history -- so
    # this one survives a restart.
    async def snapshot(self) -> dict[str, Any]:
        return {
            "candles_seen": self._candles_seen,
            "emitted": self._emitted,
            "scopes": [{"symbol": symbol, "timeframe": timeframe,
                        "ranges": list(ranges)}
                       for (symbol, timeframe), ranges in self._ranges.items()],
        }

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self._candles_seen = int(state.get("candles_seen") or 0)
        self._emitted = int(state.get("emitted") or 0)
        self._ranges = {}
        for row in state.get("scopes") or []:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            ranges: deque = deque(maxlen=self._baseline_window)
            for value in row.get("ranges") or []:
                number = _to_float(value)
                if number is not None:
                    ranges.append(number)
            if ranges:
                self._ranges[(symbol, str(row.get("timeframe") or ""))] = ranges

    # ═══ ٢٠٢٦-١٠-١٢ (تفويض المالك الكامل «NQ» — نقاش ١٠-١٢ البند 9): السبريد الحقيقيّ من التِّكّ ═══════════════════
    # كان المقيس «أعلى − أدنى» الشمعة باسم السبريد (مدى السعر لا كلفة العبور). السبريد = الطلب − العرض ولا يوجد إلّا في
    # التِّكّ: كلّ تِكّة تُجمع في دلو دقيقتها، وعند إغلاق شمعة أيّ إطار تُقرأ دلاء مدّتها ⟸ متوسّط السبريد فيها (وأقصاه).
    # النوافذ والمقارنات (القصير/الطويل · الواسع/الضيّق) كما هي، على هذه القيمة. شمعةٌ بلا تِكّة لا تُضاف.
    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "")
        bid, ask = _to_float(payload.get("bid")), _to_float(payload.get("ask"))
        stamp = _to_float(payload.get("source_timestamp", payload.get("timestamp")))
        if not symbol or bid is None or ask is None or stamp is None or ask <= bid or bid <= 0:
            return
        spread = ask - bid
        buckets = self._spread_buckets.setdefault(symbol, {})
        minute = int(stamp // 60)
        row = buckets.get(minute)
        if row is None:
            buckets[minute] = [spread, 1, spread]
            for old in [m for m in buckets if m < minute - _BUCKET_KEEP_MIN]:
                del buckets[old]
        else:
            row[0] += spread
            row[1] += 1
            row[2] = max(row[2], spread)

    def _candle_spread(self, symbol: str, start: float, seconds: float) -> tuple[float, float] | None:
        buckets = self._spread_buckets.get(symbol) or {}
        lo, hi = int(start // 60), int((start + seconds - 1) // 60)
        rows = [buckets[m] for m in range(lo, hi + 1) if m in buckets]
        total, count = sum(r[0] for r in rows), sum(r[1] for r in rows)
        return (total / count, max(r[2] for r in rows)) if count else None

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        start = _to_float(payload.get("period_start"))
        timeframe = str(payload.get("timeframe", ""))
        seconds = _frame_seconds(timeframe)
        if not symbol or start is None or not seconds:
            return
        symbol = str(symbol)
        measured = self._candle_spread(symbol, start, seconds)
        if measured is None:
            return
        avg, peak = measured
        period_start = payload.get("period_start", payload.get("timestamp", ""))
        cycle_id = cycle_key_of(payload, symbol=symbol, timeframe=timeframe, period_start=period_start)
        key = (symbol, timeframe)
        ranges = self._ranges.get(key)
        if ranges is None:
            ranges = deque(maxlen=self._baseline_window)
            self._ranges[key] = ranges
        ranges.append(avg)
        self._last_peak[key] = peak
        self._last_price[key] = _to_float(payload.get("close"))
        self._candles_seen += 1
        await self._emit(symbol, timeframe, cycle_id, ranges)

    def _size(self, current: float, baseline: float) -> str:
        if baseline <= 0:
            return SIZE_NORMAL
        if current > baseline * self._wide_mult:
            return SIZE_WIDE
        if current < baseline * self._narrow_mult:
            return SIZE_NARROW
        return SIZE_NORMAL

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str,
                    ranges: deque) -> None:
        if self._context is None:
            return
        base = {"symbol": symbol, "id": "spread", "cycle_id": cycle_id,
                "timeframe": timeframe}
        meta = {"method": METHOD, "timeframe": timeframe}
        vals = list(ranges)[-self._baseline_window:]
        if len(vals) < self._min_candles:
            await self._context.publish(EVENT_OUT, {
                **base, "status": STATUS_INSUFFICIENT, "signal": SIGNAL_STABLE,
                "score": 0, "confidence": 0.0, "quality": QUALITY_LOW,
                "warnings": [WARN_INSUFFICIENT], "metadata": meta})
            self._emitted += 1
            return
        current = vals[-1]
        short_avg = _mean(vals[-self._exp_short:])
        long_avg = _mean(vals[-self._exp_long:])
        baseline = _mean(vals)
        exp_ratio = short_avg / long_avg if long_avg > 0 else 1.0
        if exp_ratio > self._exp_mult:
            signal = SIGNAL_EXPANSION
        elif exp_ratio < 1.0 / self._exp_mult:
            signal = SIGNAL_CONTRACTION
        else:
            signal = SIGNAL_STABLE
        score = 0 if signal == SIGNAL_STABLE else int(round(
            min(_SCORE_MAX, abs(exp_ratio - 1.0) * _EXPANSION_SCALE)))
        confidence = round(min(1.0, len(vals) / self._baseline_window), 2)
        key = (symbol, timeframe)
        meta.update({"spread": round(current, 5), "baseline_spread": round(baseline, 5),
                     "spread_max": round(self._last_peak.get(key, current), 5),
                     "spread_pips": round(to_pips(current, symbol), 3),   # ١٠-١٧ «nq»: البِب لا نقاط الأساس
                     "expansion_ratio": round(exp_ratio, 2),
                     "size": self._size(current, baseline)})
        await self._context.publish(EVENT_OUT, {
            **base, "status": STATUS_OK, "signal": signal, "score": score,
            "confidence": confidence, "quality": QUALITY_GOOD, "warnings": [],
            "metadata": meta})
        self._emitted += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._candles_seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_CANDLES,
                                details={"tracked": len(self._ranges)})
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="candles=%d emitted=%d tracked=%d" % (
                self._candles_seen, self._emitted, len(self._ranges)),
            details={"candles": self._candles_seen, "emitted": self._emitted,
                     "tracked": len(self._ranges)})
