from __future__ import annotations

import math
import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "2.5.0"

#: ٢٠٢٦-٠٩-١٦ — مقيس: ٢٬٢٩٩٬٢٧٤ نشرة في سبعين دقيقة لتسعة نطاقات، وكل
#: واحدة تُنسخ لأربعة مشتركين (٥١٣ · ٥٢٦ · ٥٧٣ · ٥٨١). والحالة المنشورة **لا
#: تحمل طابعًا زمنيًّا**، فنشرةٌ مطابقة لسابقتها بايتًا ببايت صفر خبر —
#: تكلفة نقل خالصة على جدار العمّال المقيس (٢٢٪ تُرمى، ٢٠٢٦-٠٩-٠٩).
#: تُكبح المتطابقة، ويبقى نبضٌ دوريّ لمن يقيس الطزاجة بوصول الحدث.
_REPUBLISH_AFTER_S = 30.0
BAD_DECIMALS = "BAD_PRICE_DECIMALS"
EVENT_LEDGER = "risk.asset_ledger.state"
EVENT_OUT = "risk.asset_stop.state"
EVENT_LEGACY = "risk.structure_stop.state"


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._last: dict[str, dict[str, Any]] = {}
        self._published_at: dict[str, float] = {}
        self._seen = 0
        self._published = 0
        self._suppressed = 0
        self._price_dp: int | None = None
        self._config_error = ""

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        declared = context.config["price_decimals"]
        usable = isinstance(declared, int) and not isinstance(declared, bool) and declared >= 0
        self._price_dp = declared if usable else None
        self._config_error = "" if usable else BAD_DECIMALS
        context.subscribe(EVENT_LEDGER, self._on_ledger)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    @staticmethod
    def _key(payload: dict[str, Any]) -> str:
        return "%s\x1f%s" % (payload.get("account_id", "__unknown__"),
                              payload.get("asset_canonical", payload.get("symbol", "")))

    async def _on_ledger(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        ledgers = payload.get("ledgers")
        if isinstance(ledgers, list):
            for ledger in ledgers:
                if isinstance(ledger, dict):
                    await self._on_ledger(ledger)
            return
        self._seen += 1
        account = str(payload.get("account_id", "__unknown__"))
        symbol = str(payload.get("asset_canonical", payload.get("symbol", "")))
        budget = number(payload.get("risk_budget", payload.get("R")))
        credit = number(payload.get("K")); cost = number(payload.get("cost"))
        net_volume = number(payload.get("v_net")); weight = number(payload.get("w"))
        vpu = number(payload.get("vpu"))
        warnings = list(payload.get("warnings", [])) if isinstance(payload.get("warnings"), list) else []
        state: dict[str, Any] = {"account_id": account, "asset_canonical": symbol, "symbol": symbol,
                                 "status": "UNSUPPORTED", "stop_price": None, "room": None,
                                 "delta_price": None, "average_entry": None, "warnings": warnings}
        if self._config_error:
            state["warnings"].append(self._config_error)
        elif None in (budget, credit, cost, net_volume, weight):
            state["warnings"].append("INCOMPLETE_LEDGER")
        elif abs(net_volume) <= 0.0:
            # 2026-10-23 (law 13): was {"status": "HEDGED", "target_net": -budget} -- the neutral-pair era named a flat asset
            # "hedged" and aimed its net at the opposite side; no net position is simply FLAT, with no target.
            state.update({"status": "FLAT"})
        elif vpu is None or vpu <= 0.0:
            state["warnings"].append("MISSING_VPU")
        else:
            room = budget + credit - cost
            average = weight / net_volume
            if room <= 0.0:
                state.update({"status": "FROZEN", "room": room, "average_entry": average})
                state["warnings"].append("NO_POSITIVE_STOP_ROOM")
            else:
                delta = room / (vpu * abs(net_volume))
                stop = average - delta if net_volume > 0.0 else average + delta
                dp = self._price_dp
                state.update({"status": "READY", "room": round(room, dp),
                              "delta_price": round(delta, dp),
                              "average_entry": round(average, dp),
                              "stop_price": round(stop, dp), "vpu": vpu})
        state["warnings"] = sorted(set(str(item) for item in state["warnings"]))
        key = self._key(payload)
        # الكبح يقع بعد الحساب لا قبله: الحالة تُحدَّث دائمًا فتبقى `ready`
        # و`state()` صادقتين، ويُمنع النقل وحده.
        previous = self._last.get(key)
        now = time.monotonic()
        self._last[key] = state
        if previous == state and now - self._published_at.get(key, 0.0) < _REPUBLISH_AFTER_S:
            self._suppressed += 1
            return
        self._published_at[key] = now
        await self._context.publish(EVENT_OUT, state)
        direction = net_volume
        legacy = dict(state)
        legacy.update({"id": "asset_dollar_stop",
                       "signal": "structure_stop" if state["stop_price"] is not None else "none",
                       "metadata": {"method": "asset_dollar_stop",
                                    "buy_stop": state["stop_price"] if direction is not None and direction > 0 else None,
                                    "sell_stop": state["stop_price"] if direction is not None and direction < 0 else None}})
        await self._context.publish(EVENT_LEGACY, legacy)
        self._published += 1

    def state(self, key: str) -> dict[str, Any] | None:
        return self._last.get(key)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        ready = sum(1 for state in self._last.values() if state.get("stop_price") is not None)
        details = {"seen": self._seen, "published": self._published, "scopes": len(self._last), "ready": ready,
                   "suppressed": self._suppressed,
                   "price_decimals": self._price_dp, "config_error": self._config_error}
        if self._config_error:
            return HealthStatus(state=HealthState.UNHEALTHY, message=self._config_error,
                                details=details)
        if not self._seen:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_AWAITING_FIRST_ASSET_LEDGER | seen=0", details=details)
        # «stop_targets_ready» كانت تخرج بمجرّد `_seen>0` ولا تنظر إلى
        # `stop_price` قطّ — شارة خضراء لا تقيس ما تدّعيه.  الرسالة الآن تحمل
        # الرقم: كم نطاقًا له وقف محسوب فعلًا.  والحالة تبقى سليمة لأنّ
        # `ready=0` مشروع تمامًا حين لا مركز مفتوحًا (مقيس ٢٠٢٦-٠٩-٠٩:
        # `FLAT` (كان `HEDGED`) هو الحال الطبيعي لثمانية رموز من تسعة).
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="scopes=%d ready=%d published=%d suppressed=%d" % (
                len(self._last), ready, self._published, self._suppressed),
            details=details)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "seen": self._seen,
                "published": self._published, "suppressed": self._suppressed,
                "last": {key: dict(value) for key, value in self._last.items()}}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise ValueError("INVALID_ASSET_STOP_STATE")
        last = state.get("last") or {}
        if not isinstance(last, dict):
            raise ValueError("INVALID_ASSET_STOP_STATE")
        loaded = {str(key): dict(value) for key, value in last.items()
                  if isinstance(value, dict)}
        # تعديل في مكانه لا استبدال — درس ٥٠٠ ٢٠٢٦-٠٩-٠٩.
        self._last.clear()
        self._last.update(loaded)
        for name in ("seen", "published", "suppressed"):
            value = state.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                setattr(self, "_" + name, value)
