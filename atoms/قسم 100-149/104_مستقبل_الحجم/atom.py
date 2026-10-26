from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "2.2.0"

EVENT_IN = "market.volume"
EVENT_OUT = "market_data.volume_received"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_DATA = "NO_VOLUME_YET"


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self.received_count = 0
        self.dropped_count = 0
        self._source_has_volume = True

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        # ٢٠٢٦-٠٩-٢٤ (ختم المالك «Nq كل إصلاحات») — ما يعلنه المالك عن مصدره.
        # غيابُ المفتاح = السلوك السابق حرفًا (المصدر يُنتظر منه حجم).
        self._source_has_volume = bool(context.config.get("source_has_volume", True))
        context.subscribe(EVENT_IN, self._on_volume)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_volume(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        if not symbol:
            # ٢٠٢٦-٠٩-٠٧ — كان صامتًا: بلا رمز لا يُعرف حجم أيّ سوق، لكنّ
            # العجز يُحصى ويُعلن بدل أن يُترك للتخمين.
            self.dropped_count += 1
            return
        out: dict[str, Any] = {"symbol": symbol, "volume": _to_float(payload.get("volume"))}
        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)):
            out["timestamp"] = ts
        provider = payload.get("provider")
        if provider is not None:
            out["provider"] = provider
        self.received_count += 1
        await self._context.publish(EVENT_OUT, out)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"received": self.received_count, "dropped": self.dropped_count,
                   "source_has_volume": self._source_has_volume}
        # 🔴 ٢٠٢٦-٠٩-٢٤ (ختم المالك «Nq كل إصلاحات») — مصدرٌ لا يرسل حجمًا ليس علّة.
        #
        # كانت الشارة صفراء دائمًا بـ`NO_VOLUME_YET` على أنّها «علّةٌ فوقنا». والمقيس
        # أنّها ليست علّة بل طبيعة المصدر: حقل الحجم فارغٌ في كلّ تِكّة سي‑تريدر
        # (13,146 مرفوضة و2,000 مقبولة، ثلاث ساعات)، و613 لا ينشر `market.volume`
        # إلّا حين تحمل الحمولة حجمًا، و103 أغلق 277,627 شمعة بحجم صفر ويعدّ التِكّات.
        # فالمالك يعلن في الإعداد `source_has_volume: false` — والإعلان يُحاسَب:
        # إن وصل حجمٌ رغمه صار الإعلان قديمًا فتصفرّ الشارة، ولا يُخفى المرميّ بلا رمز.
        if (self.received_count == 0 and not self.dropped_count
                and not self._source_has_volume):
            return HealthStatus(
                state=HealthState.HEALTHY, details=details,
                message="المصدر بلا حجم — معلَن في الإعداد · received=0 dropped=0")
        if self.received_count and not self._source_has_volume:
            return HealthStatus(
                state=HealthState.DEGRADED, details=details,
                message="يصل حجمٌ (received=%d) والإعداد يعلن المصدر بلا حجم — "
                        "يُراجَع الإعلان" % self.received_count)
        if self.received_count == 0:
            # ٢٠٢٦-٠٩-١٦ — `NO_VOLUME_YET` وحدها كانت تكتم خبرًا مختلفًا
            # تمامًا: أن حمولات حجمٍ **تصل فعلًا** وتُرمى لأنّها بلا رمز.
            # الحالتان تبدوان واحدة على اللوحة وهما ليستا كذلك: الأولى
            # «التغذية لا ترسل حجمًا» (علّة فوقنا)، والثانية «ترسله
            # مشوّهًا» (علّة في شكل الحمولة). كشفه اختبار طفرات.
            message = REASON_NO_DATA
            if self.dropped_count:
                message += " · مرميّ بلا رمز=%d (يصل حجمٌ ولا يُقبل)" % (
                    self.dropped_count)
            return HealthStatus(state=HealthState.DEGRADED, message=message,
                                details=details)
        return HealthStatus(
            state=HealthState.HEALTHY, details=details,
            message="received=%d dropped=%d" % (self.received_count,
                                                self.dropped_count))
