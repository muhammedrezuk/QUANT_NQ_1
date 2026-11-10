"""Day levels and movement (owner's plan 2026-10-17, stage 3, steps 16, 18 and 19).

Keeps the quarter-hour and day candles of every symbol (live and the history replayed at boot), and on every live quarter-hour
close publishes the asset's map: the six levels the owner approved as "the place" (yesterday's session, the pre-market --
from the broker's futures-following contract, not the stocks --, the night, the open and its first quarter hour, the gap,
the week and the month with the previous ones), each one's distance in pips from the last price, and the movement
(today's and yesterday's range, the previous five days, the week, the month). The computing lives in `shared.day_levels`.
"""
from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, HealthState, HealthStatus
from shared import day_levels

ATOM_VERSION = "1.0.0"
EVENT_CANDLE = "market_data.candle_closed"
EVENT_OUT = "knowledge.levels.state"
FRAME_M15 = "15m"
FRAME_D1 = "1d"
M15_S = 15 * 60
DEFAULT_MAX_M15 = 1600          # ~16 trading days of quarter hours
DEFAULT_MAX_D1 = 140            # ~6 months of days


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context = None
        self._running = False
        self._symbols: set[str] | None = None
        self._max_m15 = DEFAULT_MAX_M15
        self._max_d1 = DEFAULT_MAX_D1
        self._m15: dict[str, dict[float, tuple]] = {}
        self._d1: dict[str, dict[float, tuple]] = {}
        self._published = 0
        self._failed = 0
        self._dropped = 0
        self._last_error = ""

    async def initialize(self, context: Any) -> None:
        self._context = context
        cfg = context.config or {}
        syms = cfg.get("symbols")
        self._symbols = {str(s).upper() for s in syms} if isinstance(syms, list) and syms else None
        self._max_m15 = int(cfg.get("max_m15", DEFAULT_MAX_M15))
        self._max_d1 = int(cfg.get("max_d1", DEFAULT_MAX_D1))
        context.subscribe(EVENT_CANDLE, self._on_candle)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    @staticmethod
    def _keep(store: dict[float, tuple], start: float, row: tuple, cap: int) -> None:
        store[start] = row
        if len(store) > cap:
            for old in sorted(store)[: len(store) - cap]:
                store.pop(old, None)

    async def _on_candle(self, payload: Any) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "").upper()
        frame = str(payload.get("timeframe") or "")
        start = _num(payload.get("period_start"))
        values = [_num(payload.get(k)) for k in ("open", "high", "low", "close")]
        if frame not in (FRAME_M15, FRAME_D1) or (self._symbols and symbol not in self._symbols):
            return                                                    # other frames and symbols are not ours
        if not symbol or start is None or None in values:
            self._dropped += 1                                        # malformed candle: counted, shown in health
            return
        row = (start, *values)
        if frame == FRAME_D1:
            self._keep(self._d1.setdefault(symbol, {}), start, row, self._max_d1)
            return
        self._keep(self._m15.setdefault(symbol, {}), start, row, self._max_m15)
        if payload.get("history"):
            return
        try:
            body = day_levels.levels(symbol, start + M15_S, list(self._m15[symbol].values()),
                                     list(self._d1.get(symbol, {}).values()))
        except Exception as exc:  # noqa: BLE001 -- a bad candle set must not stop the feed; counted and shown
            self._failed += 1
            self._last_error = "%s %s: %s" % (symbol, type(exc).__name__, exc)
            return
        await self._context.publish(EVENT_OUT, {"id": "day_levels", "symbol": symbol, "account_id": payload.get("account_id"),
                                                "broker": payload.get("broker"), "timeframe": FRAME_M15,
                                                "period_start": start, **body})
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
        held = " ".join("%s:%d/%d" % (s, len(self._m15.get(s, {})), len(self._d1.get(s, {})))
                        for s in sorted(set(self._m15) | set(self._d1))) or "-"
        return HealthStatus(state=HealthState.HEALTHY, message="published=%d failed=%d dropped=%d candles(m15/d1) %s %s" % (
            self._published, self._failed, self._dropped, held, self._last_error))
