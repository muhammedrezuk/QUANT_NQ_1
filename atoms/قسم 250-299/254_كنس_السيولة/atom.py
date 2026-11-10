from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.section_contract import section_atom
from shared.cycle_identity import cycle_key_of

ATOM_VERSION = "1.3.0"

EVENT_BUY = "liquidity.buyside.state"
EVENT_SELL = "liquidity.sellside.state"
EVENT_CANDLE = "market_data.candle_closed"
EVENT_TICK = "market.tick.validated"
_FRAME_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _frame_seconds(label: str) -> int:
    try:
        return int(label[:-1]) * _FRAME_UNITS[label[-1]]
    except (KeyError, ValueError, IndexError):
        return 0
EVENT_OUT = "liquidity.sweep.state"

METHOD = "tick_takes_and_returns"  # ١٠-١٢: كان wick_takes_pool
ID_SWEEP = "sweep"

SIGNAL_BUYSIDE = "buyside"
SIGNAL_SELLSIDE = "sellside"

SIGNAL_SWEEP = "sweep"
SIGNAL_NONE = "none"

DIR_BUY = "buy_side"
DIR_SELL = "sell_side"

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"
QUALITY_GOOD = "good"
QUALITY_LOW = "low"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_INPUT = "NO_CANDLE_INPUT_YET"

WARN_NO_POOLS = "insufficient_pools"
WARN_NO_RANGE = "insufficient_candle"


_POOL_CAP = 64
_PRICE_DP = 4
_DEPTH_DP = 6


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _round(value: Any) -> Any:
    return round(value, _PRICE_DP) if value is not None else None


@section_atom("250", "254")
class Atom(AtomBase):
    def __init__(self) -> None:
        # Campaign 1-449 batch B: dropped inputs are counted, never silent.
        self._dropped = {"buyside": 0, "sellside": 0}
        self._context: AtomContext | None = None
        self._running = False
        self._state: dict[tuple, dict[str, Any]] = {}
        self._candles_seen = 0
        self._sweeps = 0
        self._emitted = 0
        self._taken: dict[tuple, float] = {}
        self._ticks_seen = 0
        self._breaks = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        context.subscribe(EVENT_BUY, self._on_buyside)
        context.subscribe(EVENT_SELL, self._on_sellside)
        context.subscribe(EVENT_CANDLE, self._on_candle)
        context.subscribe(EVENT_TICK, self._on_tick)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _get(self, key: tuple) -> dict[str, Any]:
        st = self._state.get(key)
        if st is None:
            st = {"buy": [], "sell": []}
            self._state[key] = st
        return st

    def _add(self, pools: list, price: float) -> None:
        pools.append(price)
        if len(pools) > _POOL_CAP:
            del pools[0]

    async def _on_buyside(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        if payload.get("signal") != SIGNAL_BUYSIDE:
            return
        symbol = payload.get("symbol")
        if not symbol:
            self._dropped["buyside"] += 1
            return
        meta = payload.get("metadata") or {}
        price = _to_float(meta.get("price"))
        if price is None:
            self._dropped["buyside"] += 1
            return
        st = self._get((str(symbol), str(meta.get("timeframe", ""))))
        self._add(st["buy"], price)

    async def _on_sellside(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        if payload.get("signal") != SIGNAL_SELLSIDE:
            return
        symbol = payload.get("symbol")
        if not symbol:
            self._dropped["sellside"] += 1
            return
        meta = payload.get("metadata") or {}
        price = _to_float(meta.get("price"))
        if price is None:
            self._dropped["sellside"] += 1
            return
        st = self._get((str(symbol), str(meta.get("timeframe", ""))))
        self._add(st["sell"], price)

    # ═══ ٢٠٢٦-١٠-١٢ (تفويض المالك الكامل «NQ» — نقاش ١٠-١٢ البند 9: «قسم السيولة بدّه تِكّ»): الكنس على التِّكّ ═══════════
    # كان «كنسًا» كلُّ شمعةٍ يلمس ذيلها مجمّعًا — بلا شرط عودة، فالكسر المستمرّ يُسمّى كنسًا، ويُرى بعد إغلاق الشمعة.
    # الآن: السعر يتجاوز المجمّع (يأخذ السيولة) ⟸ يُحفظ «مأخوذًا» بزمنه؛ ثمّ يعود عبره قبل أن تمضي مدّة شمعة إطاره ⟸ **كنسٌ
    # يُعلن لحظتها** بإطار المجمّع؛ وإن بقي خلفه أطول ⟸ كسرٌ لا كنس، يُرفع المجمّع بلا إعلان. الشمعة صارت نبضًا لا كاشفًا.
    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "")
        bid, ask = _to_float(payload.get("bid")), _to_float(payload.get("ask"))
        price = _to_float(payload.get("price"))
        if price is None and bid is not None and ask is not None:
            price = (bid + ask) / 2.0
        stamp = _to_float(payload.get("source_timestamp", payload.get("timestamp")))
        if not symbol or price is None or stamp is None:
            return
        self._ticks_seen += 1
        for (sym, timeframe), st in list(self._state.items()):
            if sym != symbol:
                continue
            for level in [p for p in st["buy"] if price > p]:
                st["buy"].remove(level)
                self._taken[(sym, timeframe, DIR_BUY, level)] = stamp
            for level in [p for p in st["sell"] if price < p]:
                st["sell"].remove(level)
                self._taken[(sym, timeframe, DIR_SELL, level)] = stamp
        for key, taken_at in list(self._taken.items()):
            sym, timeframe, side, level = key
            if sym != symbol:
                continue
            back = price < level if side == DIR_BUY else price > level
            if back:
                del self._taken[key]
                await self._emit_tick_sweep(sym, timeframe, side, level, taken_at, stamp, price)
            elif stamp - taken_at > (_frame_seconds(timeframe) or 60):
                del self._taken[key]                      # كسرٌ ثبت خلف المستوى — لا كنس
                self._breaks += 1

    async def _emit_tick_sweep(self, symbol: str, timeframe: str, side: str, level: float,
                               taken_at: float, stamp: float, price: float) -> None:
        if self._context is None:
            return
        self._sweeps += 1
        meta = {"method": METHOD, "timeframe": timeframe, "direction": side, "price": _round(level),
                "taken_at": taken_at, "returned_at": stamp, "seconds_beyond": round(stamp - taken_at, 3),
                "return_price": _round(price), "detected": "tick"}
        await self._context.publish(EVENT_OUT, {
            "symbol": symbol, "id": ID_SWEEP, "cycle_id": "%s|%s|%s|%s" % (symbol, timeframe, side, level),
            "timeframe": timeframe, "status": STATUS_OK, "signal": SIGNAL_SWEEP, "confidence": 1.0,
            "quality": QUALITY_GOOD, "warnings": [], "metadata": meta, "timestamp": stamp})
        self._emitted += 1

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        if not symbol:
            return
        symbol = str(symbol)
        self._candles_seen += 1
        high = _to_float(payload.get("high"))
        low = _to_float(payload.get("low"))
        timeframe = str(payload.get("timeframe", ""))
        period_start = payload.get("period_start", payload.get("timestamp", ""))
        cycle_id = cycle_key_of(payload, symbol=symbol, timeframe=timeframe, period_start=period_start)
        st = self._get((symbol, timeframe))
        if high is None or low is None or high <= low:
            await self._gap(symbol, timeframe, cycle_id, WARN_NO_RANGE, high, low)
            return
        if not (st["buy"] or st["sell"]):
            await self._gap(symbol, timeframe, cycle_id, WARN_NO_POOLS, high, low)
            return
        await self._emit(symbol, timeframe, cycle_id, None, None, high, low)

    def _depth(self, direction: Any, level: Any, high: float, low: float) -> Any:
        span = high - low
        if span <= 0 or level is None:
            return None
        reach = (high - level) if direction == DIR_BUY else (level - low)
        if reach < 0:
            reach = 0.0
        ratio = reach / span
        return 1.0 if ratio > 1.0 else round(ratio, _DEPTH_DP)

    async def _gap(self, symbol: str, timeframe: str, cycle_id: str, warning: str,
                   high: Any, low: Any) -> None:
        if self._context is None:
            return
        meta = {"method": METHOD, "timeframe": timeframe, "direction": None,
                "price": None, "high": high, "low": low}
        await self._context.publish(EVENT_OUT, {
            "symbol": symbol, "id": ID_SWEEP, "cycle_id": cycle_id,
            "timeframe": timeframe,
            "status": STATUS_INSUFFICIENT, "signal": SIGNAL_NONE,
            "score": None, "confidence": 0.0,
            "quality": QUALITY_LOW, "warnings": [warning], "metadata": meta})
        self._emitted += 1

    async def _emit(self, symbol: str, timeframe: str, cycle_id: str, direction: Any,
                    level: Any, high: Any, low: Any) -> None:
        if self._context is None:
            return
        swept = direction is not None
        confidence = self._depth(direction, level, high, low) if swept else 0.0
        if swept and confidence is None:
            await self._gap(symbol, timeframe, cycle_id, WARN_NO_RANGE, high, low)
            return
        if swept:
            self._sweeps += 1
        meta = {"method": METHOD, "timeframe": timeframe, "direction": direction,
                "price": _round(level), "high": high, "low": low}
        await self._context.publish(EVENT_OUT, {
            "symbol": symbol, "id": ID_SWEEP, "cycle_id": cycle_id,
            "timeframe": timeframe,
            "status": STATUS_OK, "signal": SIGNAL_SWEEP if swept else SIGNAL_NONE,
            "confidence": confidence,
            "quality": QUALITY_GOOD, "warnings": [], "metadata": meta})
        self._emitted += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        if self._candles_seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_INPUT,
                                details={"tracked": len(self._state)})
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="ticks=%d candles=%d sweeps=%d breaks=%d taken=%d tracked=%d dropped_buy=%d dropped_sell=%d" % (self._ticks_seen,
                self._candles_seen, self._sweeps, self._breaks, len(self._taken), len(self._state),
                self._dropped["buyside"], self._dropped["sellside"]),
            details={"candles": self._candles_seen, "sweeps": self._sweeps,
                     "tracked": len(self._state),
                     "dropped_buyside": self._dropped["buyside"],
                     "dropped_sellside": self._dropped["sellside"]})
