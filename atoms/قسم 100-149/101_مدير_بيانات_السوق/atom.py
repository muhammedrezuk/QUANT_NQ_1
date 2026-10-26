from __future__ import annotations

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus


ATOM_VERSION = "2.2.0"

# ٢٠٢٦-٠٩-١٦ (بتفويض المالك: «إذا بيلزمك وبتحسّنو شغّلهم») — هذه الذرّة
# **تبقى**، ويُقطع نزيفها.
#
# ما هي: الوحيدة في المنصّة التي تشترك في أحداث البيانات العشرة مجتمعة
# وتبني منها صورةً واحدة لكل رمز — السعر والسبريد والعمق والشمعة والحجم
# والأخبار والتقويم والمرجع في كائن واحد. لا بديل لها: من أراد «كلّ ما
# نعرفه عن هذا الرمز الآن» لا يجده إلّا هنا.
#
# وما كان: تنشر الصورة **الكاملة** مع كلّ حدث وارد. مقيس ٢٠٢٦-٠٩-١٦:
# 2,240 نشرة في 45 ثانية (2,987/دقيقة)، و`no_subscribers` يساوي عدد
# النشرات كلّها — أي نسخةٌ كاملة من حالة الرمز تُبنى وتُجمَّد وتُبثّ
# ثلاثة آلاف مرّة في الدقيقة إلى لا أحد.
#
# والعلاج ليس الإزالة — «بلا مشترك» وصفُ حالةٍ لا حكمُ قيمة، وقارئها لم
# يُبنَ بعد. العلاج أن يُنظَّم **البثّ** دون أن يُمسّ **الجمع**: الحالة
# تُحدَّث مع كلّ حدث كما كانت بالضبط، والنشر بإيقاع معلن في المانيفست.
# فإذا وُصِّلت بقارئٍ يومًا وجد الصورة كاملة لا ناقصة.
#
# والإيقاع بالزمن لا بالعدد: عتبةٌ بالعدد صنعت حلقة مغلقة في هذا المشروع
# من قبل (ليلة ٢٠٢٦-٠٩-٠٩)، فالعدّاد لا ينضج حين يهدأ السوق.

def _ts_from(payload: dict) -> dict:
    ts = payload.get("timestamp")
    return {"timestamp": ts} if isinstance(ts, (int, float)) else {}


_SOURCE_EVENTS = {
    "market.tick.validated": "tick",
    "market_data.price_received": "price",
    "market_data.candle_closed": "candle",
    "market_data.volume_received": "volume",
    "market_data.spread_updated": "spread",
    "market_data.depth_updated": "depth",
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «nq»): «trade_tape» خرج — 107 أُرشف، لا شريط صفقات عند الوسيط.
    "market_data.news_received": "news",
    "market_data.calendar_event": "calendar",
    "market_data.reference_index_updated": "reference_index",
}

_UNIFIED_EVENT = "market_data.state"


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._state: dict[str, dict[str, dict]] = {}
        self.unified_published_count = 0
        self.suppressed_count = 0
        self._publish_interval_s = 0.0
        self._last_publish: dict[str, float] = {}

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._publish_interval_s = float(context.config["publish_interval_s"])
        for event_name, field_key in _SOURCE_EVENTS.items():
            context.subscribe(event_name, self._make_collector(field_key))
        context.logger.info("101 initialized: %d source events", len(_SOURCE_EVENTS))

    def _due(self, symbol: str, stamp: float | None) -> bool:
        """هل حان بثّ الصورة لهذا الرمز؟

        تُنشر أوّل صورةٍ لكلّ رمز فورًا مهما كان الإيقاع — فمن يشترك
        لاحقًا يجد صورةً لا فراغًا. وحمولةٌ بلا طابع زمنيّ تُنشر كما
        كانت: لا تُكتم معلومةٌ لأنّ مصدرها لم يختم وقتها.

        والزمن من الحمولة لا من ساعة الجهاز — الوقت في هذه المنصّة
        يأتي من السوق أو من الساعة الرسميّة، لا من `time.time()`.
        """
        # اختصار أداءٍ لا منطق: بإيقاع صفر يعود ما تحته `True` في كل
        # مسارٍ منه (أوّل مرّة · طابع غائب · تراجُع · و`فرق >= 0`). ولذلك
        # تبديل `<=` بـ`<` هنا **طفرة مكافئة** لا يقتلها اختبار — وُثّقت
        # كي لا يطاردها من يعيد اختبار الطفرات ظنًّا أنّها ثغرة حراسة.
        if self._publish_interval_s <= 0:
            return True
        last = self._last_publish.get(symbol)
        if last is None or stamp is None:
            return True
        if stamp < last:
            # تراجُع الزمن: مصدرٌ أُعيد ضبطه أو لقطة جديدة — تُبثّ ولا تُبتلع.
            return True
        return stamp - last >= self._publish_interval_s

    async def start(self) -> None:
        self._running = True
        if self._context is not None:
            self._context.logger.info("101 started")

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        pass

    async def health_check(self) -> HealthStatus:
        if not self._running: return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        # الإيقاع والمكتوم في `message`: النواة تحذف `details` قبل اللوحة،
        # ورقمُ نشرٍ بلا رقم كتمٍ يخفي أنّ الذرّة تعمل أكثر ممّا تبثّ.
        collected = self.unified_published_count + self.suppressed_count
        ratio = (100.0 * self.suppressed_count / collected) if collected else 0.0
        return HealthStatus(
            state=HealthState.HEALTHY,
            message=("symbols=%d unified_published=%d مكتوم=%d (%.0f%%) "
                     "إيقاع=%gث" % (len(self._state), self.unified_published_count,
                                    self.suppressed_count, ratio,
                                    self._publish_interval_s)),
            details={"symbols": len(self._state),
                     "published": self.unified_published_count,
                     "suppressed": self.suppressed_count,
                     "collected": collected,
                     "publish_interval_s": self._publish_interval_s},
        )

    def _make_collector(self, field_key: str):
        async def handler(payload: dict) -> None:
            if not self._running or self._context is None:
                return
            symbol = str(payload.get("symbol", "_global"))
            symbol_state = self._state.setdefault(symbol, {})
            # الجمع أوّلًا ودائمًا — الإيقاع ينظّم البثّ لا المعرفة.
            symbol_state[field_key] = payload
            stamp = payload.get("timestamp")
            stamp = float(stamp) if isinstance(stamp, (int, float)) else None
            if not self._due(symbol, stamp):
                self.suppressed_count += 1
                return
            if stamp is not None:
                self._last_publish[symbol] = stamp
            self.unified_published_count += 1
            await self._context.publish(
                _UNIFIED_EVENT,
                {
                    "symbol": symbol,
                    "updated_field": field_key,
                    "state": dict(symbol_state),
                    **_ts_from(payload),
                },
            )

        return handler
