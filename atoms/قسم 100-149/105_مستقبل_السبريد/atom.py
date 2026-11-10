from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "2.1.0"

EVENT_IN = "market.tick.validated"
EVENT_OUT = "market_data.spread_updated"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_DATA = "NO_TICKS_YET"


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self.updates_count = 0
        self.dropped_count = 0
        self.last_spread: float | None = None
        # ٢٠٢٦-٠٩-١٠ (ختم NQ) — `last_spread` وحده كان يُدهس مع كلّ تِكّة
        # من أيّ رمز، ويظهر في رسالة الصحّة كأنّه مقياس السوق. مقيس في
        # قراءتين متتاليتين: `0.00001` (يورو) ثمّ `5.0` (بتكوين) — رقم
        # صادق لحظتَه وكاذب في دلالته. صار لكلّ رمز سبريده، ويُعلَن باسمه.
        self.last_spread_by_symbol: dict[str, float] = {}
        self.last_symbol: str | None = None

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
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
        bid = _to_float(payload.get("bid"))
        ask = _to_float(payload.get("ask"))
        if not symbol or bid is None or ask is None:
            # ٢٠٢٦-٠٩-٠٧ — كان يُسقط صامتًا بلا عدّاد. السبريد يُبنى من
            # الطرفين، فبلا أحدهما لا يُحسب — لكن العجز يُحصى ويُعلن، ولا
            # يُترك للمالك أن يخمّن لماذا توقّف العدّ.
            self.dropped_count += 1
            return
        spread = ask - bid
        self.last_spread = spread
        self.last_spread_by_symbol[str(symbol)] = spread
        self.last_symbol = str(symbol)
        self.updates_count += 1
        out: dict[str, Any] = {"symbol": symbol, "spread": spread,
                               "account_id": payload.get("account_id"),
                               "broker": payload.get("broker"),
                               "provider": payload.get("provider")}
        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)):
            out["timestamp"] = ts
        await self._context.publish(EVENT_OUT, out)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"updates": self.updates_count, "dropped": self.dropped_count,
                   "last_spread": self.last_spread,
                   "last_symbol": self.last_symbol,
                   "spread_by_symbol": dict(self.last_spread_by_symbol)}
        if self.updates_count == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_DATA,
                                details=details)
        # كلّ سبريد باسم رمزه في `message`: النواة تحذف `details`، ورقم
        # بلا رمز يُقرأ على أنّه حال السوق كلّه.
        per_symbol = " ".join(
            "%s=%g" % (symbol, value)
            for symbol, value in sorted(self.last_spread_by_symbol.items()))
        return HealthStatus(
            state=HealthState.HEALTHY, details=details,
            message="updates=%d dropped=%d رموز=%d · %s" % (
                self.updates_count, self.dropped_count,
                len(self.last_spread_by_symbol), per_symbol))
