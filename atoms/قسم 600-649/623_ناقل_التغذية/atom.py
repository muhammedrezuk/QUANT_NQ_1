"""صانع التِكّة (623) — من قمّة الدفتر إلى تِكّة.

سي‑تريدر لا يرسل تِكّات: يرسل تحديثات مستويات. التِكّة تُشتقّ من **قمّة**
الدفتر بعد تطبيق التحديث. فمن يبني الدفتر (624) ينشره على `market.depth`،
وهذه الذرّة تقرأ قمّته وتنشر `feed.ctrader.tick` — العقد نفسه الذي يسمعه
613 و621 و116 و521 و582، فلم يتغيّر حرف عند أيّ منهم.

**لا حكم على صلاحية سعر.** القمّة تخرج كما بُنيت — ناقصة أو مقلوبة أو
خالية — ومعها `top_changed` و`book_empty` كحقلَي معلومة لا فلتر. من يملك
الحكم هو 112 خلف الموزّع، ويُعلن سببه على `market_data.validation_failed`.

**كل تحديث دفتر ينتج تِكّة.** قمّة لم تتغيّر ليست سببًا للكتم: الحجم تحتها
قد تبدّل، وذلك شأن ذرّات السيولة لا شأن التغذية.
"""
from __future__ import annotations

import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "2.3.0"

EVENT_IN = "market.depth"
EVENT_OUT = "feed.ctrader.tick"
EVENT_STATE = "feed.relay.state"

REASON_NOT_STARTED = "NOT_STARTED"

_PASSTHROUGH = ("account_id", "broker", "provider", "build", "sequence",
                "sequence_gap", "out_of_order", "fabric_gap",
                "exchange_timestamp", "received_at", "timestamp")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._state_every = 1000
        self._last_top: dict[str, tuple] = {}
        self._received = 0
        self._emitted = 0
        self._malformed = 0
        # مقياس العمر — يُقرأ عند **الوصول** لا عند النشر. `received_at`
        # ختمُ ٦٢٢ لحظة المقبس، فالفرق هنا هو ما أنفقناه نحن حتى بلغت
        # الذرّة: لا يخلطه طابع الوسيط ولا بطء المشترِك الذي يقرأ بعدنا.
        self._age_last = 0.0
        self._age_ewma = 0.0
        self._age_max = 0.0
        self._age_n = 0
        # كلفة النشر وحدها — من قبل `await publish` إلى بعده. النشر في هذه
        # المنصّة ينسخ الحمولة لكل مشترِك، فعدد المشتركين يصير زمنًا. هذا
        # الرقم يفصل «الذرّة بطيئة» عن «التوزيع خلفها بطيء».
        self._pub_ewma = 0.0
        self._pub_max = 0.0
        # الحدث الذي تحت اليد الآن. `_received` يزيد عند الدخول و`_emitted`
        # بعد `await publish`، فبينهما نقطةُ تنازلٍ للحلقة. أيّ `health_check`
        # يقع في تلك النقطة كان يقرأ فارقًا قدره واحد ويُعلن `TICK_GAP`
        # **غير صحّيّ** — شارةٌ حمراء على ذرّة سليمة. مقيس حيًّا ٢٠٢٦-٠٩-١٦:
        # `received=3080198 emitted=3080197` و`malformed=0`. الفقد الحقيقيّ
        # يبقى معلَنًا: ما زاد عن المعلَّق هو ضياع، والمعلَّق ليس ضياعًا.
        self._in_flight = 0
        self._last_symbol = ""

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._state_every = int(context.config["state_every"])
        context.subscribe(EVENT_IN, self._on_depth)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _gauge_age(self, payload: dict[str, Any]) -> None:
        received = payload.get("received_at")
        if not isinstance(received, (int, float)) or received <= 0:
            return
        age = time.time() - float(received)
        if age < 0.0:
            age = 0.0
        self._age_last = age
        self._age_n += 1
        # متوسّط أُسّيّ لا تراكميّ: على ملايين الرسائل يبتلع التراكميُّ
        # أيَّ تدهورٍ جديد، والمطلوب ما يجري الآن لا معدّل العمر كلّه.
        self._age_ewma = age if self._age_n == 1 else (self._age_ewma * 0.99 + age * 0.01)
        if age > self._age_max:
            self._age_max = age

    async def _on_depth(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        if not isinstance(payload, dict):
            self._malformed += 1
            return
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            # بلا رمز لا تُعرف التِكّة لأيّ سوق. عجزٌ عن الاشتقاق، لا حكم.
            self._malformed += 1
            return
        self._received += 1
        self._gauge_age(payload)

        best_bid = _number(payload.get("best_bid"))
        best_ask = _number(payload.get("best_ask"))
        top, prev = (best_bid, best_ask), self._last_top.get(symbol)
        self._last_top[symbol] = top
        mid = ((best_bid + best_ask) / 2.0
               if best_bid is not None and best_ask is not None else None)

        tick = {key: payload.get(key) for key in _PASSTHROUGH if key in payload}
        tick.update({"symbol": symbol, "bid": best_bid, "ask": best_ask,
                     "price": mid, "top_changed": (top != prev),
                     "book_empty": (best_bid is None and best_ask is None)})
        _t0 = time.perf_counter()
        self._in_flight += 1
        try:
            await self._context.publish(EVENT_OUT, tick)
        finally:
            self._in_flight -= 1
        _dt = time.perf_counter() - _t0
        self._pub_ewma = _dt if not self._pub_ewma else (self._pub_ewma * 0.99 + _dt * 0.01)
        if _dt > self._pub_max:
            self._pub_max = _dt
        self._emitted += 1
        self._last_symbol = symbol
        if self._state_every and self._emitted % self._state_every == 0:
            await self._context.publish(EVENT_STATE, {
                "received": self._received, "emitted": self._emitted,
                "malformed": self._malformed, "symbols": len(self._last_top),
                "last_symbol": self._last_symbol})

    async def health_check(self) -> HealthStatus:
        details = {"received": self._received, "emitted": self._emitted,
                   "malformed": self._malformed, "symbols": len(self._last_top),
                   "last_symbol": self._last_symbol,
                   "age_last_s": round(self._age_last, 3),
                   "age_ewma_s": round(self._age_ewma, 3),
                   "age_max_s": round(self._age_max, 3),
                   "publish_ewma_ms": round(self._pub_ewma * 1000.0, 3),
                   "publish_max_ms": round(self._pub_max * 1000.0, 3),
                   "in_flight": self._in_flight}
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY,
                                message=REASON_NOT_STARTED, details=details)
        gap = self._received - self._emitted - self._in_flight
        if gap:
            # كل تحديث دفتر تِكّة. اختلاف العددين فقدٌ في طريق لا يحقّ له
            # الفقد، فيُعلن عجزًا لا تعثّرًا.
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                message="TICK_GAP received=%d emitted=%d malformed=%d معلَّق=%d" % (
                    self._received, self._emitted, self._malformed, self._in_flight),
                details=details)
        if self._emitted == 0:
            return HealthStatus(
                state=HealthState.HEALTHY,
                message="READY_AWAITING_FIRST_BOOK_TOP | emitted=0",
                details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            # العمر في الرسالة لا في `details` وحدها: `details` تُقصّ
            # عند النواة فلا تبلغ لوحةً ولا API.
            message=("emitted=%d symbols=%d last=%s malformed=%d "
                     "age=%.2f/%.2f/%.2fث pub=%.2f/%.0fم.ث" % (
                self._emitted, len(self._last_top), self._last_symbol,
                self._malformed, self._age_last, self._age_ewma, self._age_max,
                self._pub_ewma * 1000.0, self._pub_max * 1000.0)),
            details=details)

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "received": self._received,
                "emitted": self._emitted, "malformed": self._malformed}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self._received = int(state.get("received") or 0)
        self._emitted = int(state.get("emitted") or 0)
        self._malformed = int(state.get("malformed") or 0)
