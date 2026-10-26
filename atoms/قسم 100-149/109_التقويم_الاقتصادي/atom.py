from __future__ import annotations

import math
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

# 2026-10-17 (owner seal "NQ"): our own reference of the USD news colors (ForexFactory's colors, MetaTrader's Arabic names
# mapped to them) decides the impact, whichever source sent the item. Guarded: a running process that has not loaded the
# new shared module keeps the source's impact and says so in its health line.
try:
    from shared.news_colors import impact_of as _reference_impact
except ImportError:  # noqa: BLE001
    _reference_impact = None

ATOM_VERSION = "3.12.0"

EVENT_TIME = "SYS_SECOND"
EVENT_UPCOMING = "market_data.calendar_event"
EVENT_WINDOW = "market_data.calendar_window"
EVENT_STATE = "market_data.calendar.state"
NEXT_BLOCKING_SHOWN = 5
UNREFERENCED_SHOWN = 5
COLOR_FROM_REFERENCE = "reference"
COLOR_FROM_SOURCE = "source"
REFERENCE_CURRENCY = "USD"   # the only currency our color reference (shared.news_colors) names

IMPACT_HIGH = "HIGH"
IMPACT_MEDIUM = "MEDIUM"
IMPACT_LOW = "LOW"
IMPACT_UNKNOWN = "UNKNOWN"
_ORDER = {IMPACT_LOW: 1, IMPACT_MEDIUM: 2, IMPACT_HIGH: 3}

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_SOURCE = "UNAVAILABLE_NO_CALENDAR_SOURCE"
REASON_NO_TIME = "NO_TIME_INPUT"

BAD_SHAPE = "shape"
BAD_TIME = "bad_scheduled_at"
DUPLICATE = "duplicate"

# ٢٠٢٦-٠٩-١٦ — نسخةٌ من عيارَي المالك المختومين، افتراضيّةً في الكود.
#
# **المانيفست هو المرجع** ويحكم متى وصل. لكنّ المقيس اليوم من مصدرين:
# `atom.py` يُعاد تحميله ساخنًا فور حفظه، و**`config` من المانيفست لا
# يصل بلا إقلاع**. فبقيت الذرّة تحجب بكلّ أخبار الدولار (78 من 241)
# بينما المالك ختم أن يحجب الفيدراليّ وحده — أمرٌ نُفِّذ على القرص ولم
# يبلغ السوق.
#
# فهذه النسخة تجعل حكمه ساريًا في اللحظة، ولا تُسكِت شيئًا: رسالة
# الصحّة تقول صراحةً «(افتراضيّ)» متى عملت الذرّة بها بدل `config` —
# فلا يُقرأ الحكم منفَّذًا من مصدرٍ لم يُقصد.
#
# ومتى أُقلعت المنصّة حكم المانيفست وسقطت هذه النسخة عن العمل.
_DEFAULT_BLOCKING_CURRENCIES = ("USD",)
_DEFAULT_BLOCKING_TITLES = (
    "قرار سعر فائدة",
    "بيان اللجنة الفيدرالية",
    "التوقعات الاقتصادية للجنة",
    "المؤتمر الصحفي للجنة",
    "Federal Funds Rate",
    "FOMC Statement",
    "FOMC Economic Projections",
    "FOMC Press Conference",
)
# ٢٠٢٦-٠٩-١٩ (ختم NQ) — انقضاءُ الأفق يُترجَم `UNKNOWN` فيوقف 454 الدخول.
# نسخةٌ في الكود لأنّ `config` قد لا يبلغ الذرّة بلا إقلاع — وحكمٌ يوقف
# التداول لا يجوز أن يبقى على القرص بينما السوق يعمل بغيره.
_DEFAULT_REQUIRE_FORWARD_HORIZON = True


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _impact(value: Any) -> str:
    if not isinstance(value, str):
        return IMPACT_UNKNOWN
    upper = value.strip().upper()
    if upper in (IMPACT_HIGH, "3", "H"):
        return IMPACT_HIGH
    if upper in (IMPACT_MEDIUM, "MED", "2", "M"):
        return IMPACT_MEDIUM
    # 2026-10-17: ForexFactory marks holidays and non-economic items "NONE" -- not red; before this they read UNKNOWN and an
    # unknown USD impact blocks (by design, for an unclassified red), so a holiday would have closed every position.
    if upper in (IMPACT_LOW, "1", "L", "NONE", "HOLIDAY", "NON-ECONOMIC"):
        return IMPACT_LOW
    return IMPACT_UNKNOWN


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._source_event = ""
        self._alert_before_s = 0.0
        self._keep_past_s = 0.0
        self._min_impact = ""
        self._events: dict[str, dict[str, Any]] = {}
        self._announced: set[str] = set()
        self._now_utc = 0.0
        self._in_window = False
        self._received = 0
        self._valid_received = 0
        self._published = 0
        self._last_state: tuple[bool, bool] | None = None
        self._rejected: dict[str, int] = {}
        self._restore_error = ""
        self._restored_pending_prune = False
        self._state_heartbeat_s = 0.0
        self._last_heartbeat: float | None = None
        self.heartbeats_sent = 0
        # ٢٠٢٦-٠٩-١٦ — حكم المالك بنصّه: «خبرٌ برازيليّ نحن ششو دخلنا —
        # نحن نشتغل على اخبار usd. دهب وناسدك وبتكوين عملة usd».
        #
        # الحجب كان بكلّ عملات العالم. مقيس من لقطة هذه الذرّة: 138 حدثًا
        # متتبّعًا، **52 منها USD و86 من ستّ عشرة عملة أخرى** (EUR 25 ·
        # JPY 9 · GBP 9 · NZD 9 · CAD 9 · CHF 4 · MXN 4 · BRL 3 · …).
        # وخبرٌ برازيليّ `LOW` كان يمنع الذهب والناسداك والبتكوين ساعةً
        # كاملة — وكلّها مقوَّمة بالدولار.
        #
        # والفصل هنا بين **المعرفة** و**الحكم**: كلّ حدثٍ يبقى متتبَّعًا
        # ويُعلَن في `calendar_event` (فالمالك يرى ما يجري في العالم)،
        # لكنّ ما يُغلق باب الدخول هو ما تحمل عملته الحاجبة وحده.
        #
        # وقائمة فارغة = كلّ العملات، أي السلوك قبل 3.4.0 — باب رجعةٍ
        # بكلمة في المانيفست بلا تعديل كود.
        self._blocking_currencies: frozenset[str] = frozenset()
        self._blocking_min_impact = ""
        self._blocking_titles: tuple[str, ...] = ()
        self._using_default_currencies = False
        self._using_default_titles = False
        # ٢٠٢٦-٠٩-١٨ — «أعرفُ» كانت تعني «وصلني صفٌّ يومًا ما».
        #
        # `known = self._valid_received > 0` عدّادٌ **تراكميّ** يُستعاد من
        # اللقطة (مقيس: 104,921). فلو مات جسر الأخبار الآن لبقيت الذرّة
        # تقول `CLEAR` و`allow_new_entries: true` إلى الأبد — بثقةٍ كاملة
        # وهي لا تعرف شيئًا. وهو عين ما وقع في 115 بشارتها العالقة.
        #
        # والمقياس الصادق هو **الأفق**: أبعد موعدٍ نعرفه. مقيس الآن من
        # لقطة الذرّة: 422 حدثًا استُقبلت منذ آخر استعادة، وواحدٌ فقط
        # أمامنا (ECOFIN — 09-19 10:15). فمعرفتنا تنتهي بعد ست عشرة ساعة،
        # وبعدها نحن عميان ولا شيء يقول ذلك.
        #
        # ٢٠٢٦-٠٩-١٩ (ختم NQ) — **العيار صار يعمل.**
        #
        # عُرض على المالك مطفأً يوم كُتب، لأنّ إعلان `UNKNOWN` يوقف الدخول
        # عند 454 وذاك حكمُ مالكٍ لا اجتهاد. ثمّ أثبتَه الحيُّ بعد تسع عشرة
        # ساعة: لقطة ٢٠٢٦-٠٩-١٩ ١٢:٥٤ت.ع `events=0` — التقويم فارغٌ تمامًا،
        # والذرّة قبل v3.9.0 كانت ستقول `CLEAR` بثقةٍ كاملة. فختمه.
        #
        # ومعناه صريحًا: **حين ينضب التقويم يُغلق باب الدخول** حتى يعود
        # المصدر. وهو المقصود — لا نتداول عميانًا عن الأخبار.
        self._require_forward_horizon = _DEFAULT_REQUIRE_FORWARD_HORIZON
        self._using_default_horizon = False
        self.blocking_tracked = 0
        self.non_blocking_tracked = 0
        self.unknown_currency_tracked = 0
        self.reference_hits = 0
        self.unreferenced_blocking_currency = 0
        self._unreferenced_titles: list[str] = []

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._source_event = str(cfg["source_event"])
        self._alert_before_s = float(cfg["alert_before_seconds"])
        self._keep_past_s = float(cfg["keep_past_seconds"])
        self._min_impact = str(cfg["min_impact"]).upper()
        self._state_heartbeat_s = float(cfg.get("state_heartbeat_s", 30.0))
        # `in cfg` لا `.get(...) or` — فقائمةٌ فارغة قرارُ مالكٍ صريح
        # («احجب بكلّ العملات») ولا يجوز أن تُدهس بالافتراضيّ.
        self._using_default_currencies = "blocking_currencies" not in cfg
        raw_currencies = (_DEFAULT_BLOCKING_CURRENCIES
                          if self._using_default_currencies
                          else (cfg.get("blocking_currencies") or []))
        self._blocking_currencies = frozenset(
            str(c).strip().upper() for c in raw_currencies if str(c).strip())
        self._blocking_min_impact = str(cfg.get("blocking_min_impact") or "").upper()
        self._using_default_titles = "blocking_titles" not in cfg
        raw_titles = (_DEFAULT_BLOCKING_TITLES if self._using_default_titles
                      else (cfg.get("blocking_titles") or []))
        self._blocking_titles = tuple(
            str(t).strip() for t in raw_titles if str(t).strip())
        # `in cfg` لا `.get(..., افتراضيّ)`: `false` صريحة قرارُ مالكٍ
        # («تداولْ ولو نضب التقويم») ولا يجوز أن تُدهس بالافتراضيّ.
        self._using_default_horizon = "require_forward_horizon" not in cfg
        self._require_forward_horizon = (
            _DEFAULT_REQUIRE_FORWARD_HORIZON if self._using_default_horizon
            else bool(cfg.get("require_forward_horizon")))
        context.subscribe(self._source_event, self._on_calendar)
        context.subscribe(EVENT_TIME, self._on_time)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _reject(self, reason: str) -> None:
        self._rejected[reason] = self._rejected.get(reason, 0) + 1

    def _heartbeat_due(self, now: float) -> bool:
        """هل حان نبض إعادة بثّ الحالة؟ (بالساعة الرسميّة لا بساعة الجهاز)"""
        if self._state_heartbeat_s <= 0:
            return False
        last = self._last_heartbeat
        if last is None or now < last:
            self._last_heartbeat = now
            return True
        if now - last >= self._state_heartbeat_s:
            self._last_heartbeat = now
            return True
        return False

    def _horizon(self) -> float | None:
        """أبعد موعدٍ نعرفه — من الأحداث المتتبَّعة الآن لا من عدّادٍ تراكميّ.

        يعود `None` حين لا حدث بتاتًا، وهي حالةٌ أصدق من صفرٍ يُقرأ
        «الآن». والحساب من `_events` مقصود: التقليم يُخرج الماضي، فما
        بقي هو ما نعرفه فعلًا في هذه اللحظة.
        """
        if not self._events:
            return None
        return max(event["scheduled_at"] for event in self._events.values())

    def _blocks_entry(self, event: dict[str, Any]) -> bool:
        """هل يُغلق هذا الحدث باب الدخول؟ — عملةً وأثرًا معًا.

        حكم المالك ٢٠٢٦-٠٩-١٦ في أمرين: «نحن نشتغل على اخبار usd» ثمّ
        «بعدها بس اخبارة قوية الحمراء». فالحاجز عملةٌ **و**أثر.

        وكلاهما عيار في المانيفست: قائمة عملات فارغة = كلّ العملات،
        و`blocking_min_impact` فارغ = كلّ الآثار — أي السلوك قبل 3.4.0
        بكلمةٍ بلا تعديل كود.

        وحدثٌ بلا عملة **لا يحجب** ويُعدّ: إغلاق السوق على مجهول أسوأ
        من تفويته، والعدّاد يكشفه إن صار كثيرًا. أمّا أثرٌ مجهول فيحجب
        إن كانت عملته حاجبة — لأنّ `UNKNOWN` قد يكون أحمر لم يُصنَّف،
        وهنا الكتم أخطر من الحجب.
        """
        # 2026-10-23 (owner's sealed red lines, law 24): every currency's red news blocks the assets holding that currency, so
        # the list is empty (= every currency); an item without a currency still blocks nothing, as before.
        if not self._currency_blocks(event.get("currency")):
            return False
        # ٢٠٢٦-٠٩-١٦ (ختم NQ) — الأسماء تحلّ محلّ التصنيف، لا تُضاف إليه.
        #
        # اعتراض المالك: «مبيعات تجزئة متوسّط وليس عالي تأثير» و«مخزن
        # نفط خام على النفط مو على ناسدك». وقياس قسم القرار على تقويم
        # ForexFactory الرسميّ كشف أنّ العيب أوسع: **خمسة من سبعة
        # تصنيفات مختلفة، واثنان مقلوبان تمامًا**:
        #
        #   مخزون النفط     مصدرنا HIGH   ·  ForexFactory Low
        #   بيان اللجنة     مصدرنا MEDIUM ·  ForexFactory High
        #   التوقّعات        مصدرنا MEDIUM ·  ForexFactory High
        #
        # ومصدرنا تقويم ميتاتريدر المدمج يكتبه الإكسبرت — لا ForexFactory.
        # فالتصنيف عندنا لا يصلح أساسًا للحجب حتى يُبدَّل المصدر.
        #
        # ولو طُبّق الاثنان معًا (اسم **و** تصنيف) لسقط «بيان اللجنة»
        # و«التوقّعات» لأنّهما MEDIUM عندنا — وهما من أعنف ما يحرّك
        # الذهب وناسداك. لذلك الأسماء **بديل** لا إضافة.
        #
        # مقيس على لقطة هذه الذرّة (52 حدث USD): كلّ نمطٍ يلتقط حدثًا
        # واحدًا بالضبط، و**صفر** من أحداث فيلادلفيا الستّة التي تحمل
        # «الاحتياطي الفيدرالي» في اسمها. فالمطابقة بالاحتواء آمنة هنا.
        if self._blocking_titles:
            title = str(event.get("title") or "")
            return any(pattern in title for pattern in self._blocking_titles)
        if self._blocking_min_impact:
            impact = str(event.get("impact_level") or IMPACT_UNKNOWN)
            if impact != IMPACT_UNKNOWN:
                if _ORDER.get(impact, 0) < _ORDER.get(self._blocking_min_impact, 0):
                    return False
        return True

    def _currency_blocks(self, currency: Any) -> bool:
        """A known currency inside the blocking list (an empty list = every currency)."""
        name = str(currency or "").strip().upper()
        return bool(name) and (not self._blocking_currencies or name in self._blocking_currencies)

    @staticmethod
    def _reference(title: Any, currency: Any) -> str | None:
        return _reference_impact(title, currency) if _reference_impact is not None else None

    def _count_color(self, event: dict[str, Any]) -> None:
        """Counted once per accepted item: how many took our reference's color, and which blocking-currency titles it lacks
        (they keep the source's impact -- shown, so a missing red is seen and added to the reference)."""
        if event.get("color_from") == COLOR_FROM_REFERENCE:
            self.reference_hits += 1
            return
        # 2026-10-23: our reference holds USD names only; another currency's color is its source's, not a gap in the reference.
        currency = str(event.get("currency") or "").strip().upper()
        if currency == REFERENCE_CURRENCY and self._currency_blocks(currency):
            self.unreferenced_blocking_currency += 1
            if event["title"] not in self._unreferenced_titles:
                self._unreferenced_titles = (self._unreferenced_titles + [event["title"]])[-UNREFERENCED_SHOWN:]

    def _passes_impact(self, impact: str) -> bool:
        if impact == IMPACT_UNKNOWN:
            return True
        return _ORDER.get(impact, 3) >= _ORDER.get(self._min_impact, 1)

    async def _on_calendar(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        self._received += 1
        title = payload.get("title") or payload.get("event")
        scheduled_at = _to_float(payload.get("scheduled_at"))
        if not isinstance(title, str) or not title.strip():
            self._reject(BAD_SHAPE)
            return
        if scheduled_at is None or scheduled_at <= 0:
            self._reject(BAD_TIME)
            return
        source_impact = _impact(payload.get("impact_level"))
        reference = self._reference(title, payload.get("currency"))
        impact = reference or source_impact
        if not self._passes_impact(impact):
            return
        key = str(payload.get("id") or "%s|%d" % (title.strip()[:80], int(scheduled_at)))
        if key in self._events:
            self._reject(DUPLICATE)
            return
        self._valid_received += 1
        self._events[key] = {
            "id": key, "title": title.strip(), "country": payload.get("country"),
            "currency": payload.get("currency"), "impact_level": impact,
            "source_impact_level": source_impact,
            "color_from": COLOR_FROM_REFERENCE if reference else COLOR_FROM_SOURCE,
            "scheduled_at": scheduled_at}
        self._count_color(self._events[key])
        # يُصنَّف عند الاستقبال مرّة، لا مع كل نبضة ثانية
        if self._blocks_entry(self._events[key]):
            self.blocking_tracked += 1
        else:
            self.non_blocking_tracked += 1
        if not str(payload.get("currency") or "").strip():
            self.unknown_currency_tracked += 1

    async def _on_time(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        now = _to_float(payload.get("official_time"))
        if now is None:
            return
        self._now_utc = now
        # ٢٠٢٦-٠٩-١٠ (ختم NQ) — كان `cutoff = 0.0` ثابتًا، بينما
        # `keep_past_seconds` معلَن في المانيفست (3600) ومقروء في
        # `initialize` ولا يُستعمل: عيار في يد المالك بلا أثر، والحدث
        # يُنسى لحظة مروره. فإن أعاد المصدر إرساله بعد دقيقة عاد يُعلَن
        # من جديد لأنّ مفتاحه خرج من `_announced` معه.
        # الأثر على الحجب: صفر — النافذة تُحسب بـ`0 <= remaining`،
        # والحدث الماضي `remaining` سالب فلا يدخلها.
        cutoff = self._keep_past_s
        for key in [k for k, e in self._events.items()
                    if now - e["scheduled_at"] > cutoff]:
            self._events.pop(key, None)
            self._announced.discard(key)
        self._restored_pending_prune = False
        for key, event in sorted(self._events.items(),
                                 key=lambda kv: kv[1]["scheduled_at"]):
            remaining = event["scheduled_at"] - now
            if 0 <= remaining <= self._alert_before_s and key not in self._announced:
                self._announced.add(key)
                self._published += 1
                await self._context.publish(
                    EVENT_UPCOMING, {**event, "seconds_until": round(remaining, 1)})
        # ٢٠٢٦-٠٩-١٦ — حكم المالك: «15 دقيقة **قبل** خبر **وبعد** خبر».
        #
        # كان الشرط `0 <= remaining` — أي الحجب يمتدّ قبل الحدث فقط
        # وينتهي **في لحظة وقوعه**. و`keep_past_seconds` كان يُبقي الحدث
        # في الذاكرة (فلا يُعاد إعلانه) ولا يحجب به. فنصف أمر المالك لم
        # يكن منفَّذًا، ولا شيء يكشفه: الذرّة تعمل والعدّادات ترتفع.
        #
        # كشفه اختبار حدٍّ كتبتُه لغرضٍ آخر: `t = scheduled + 899` أعطى
        # `CLEAR` بينما المقصود `BLOCKED`.
        #
        # والنافذة الآن مغلقة الطرفين: من `-keep_past` إلى `+alert_before`
        # حول موعد الحدث. وأعنف لحظات السوق هي الدقائق التي **تلي** الخبر
        # لا التي تسبقه — فهذا هو النصف الأهمّ.
        # والحدّ الخلفيّ مكتوب صريحًا وإن كان التقليم أعلاه يضمنه: الحدث
        # يُحذف عند `now - scheduled > keep_past`، أي أنّ كلّ حدثٍ باقٍ
        # يحقّق `scheduled - now >= -keep_past` أصلًا. فتبديل العيار هنا
        # **طفرة مكافئة** لا يقتلها اختبار — وقد جرّبتُها وسجّلتها.
        # يبقى الشرط لأنّه يوثّق النيّة ويحمي لو تغيّر منطق التقليم يومًا.
        # 2026-10-23 (law 24): which currencies are inside their window now -- the red line blocks an asset only by its own
        # currencies (USD blocks every symbol), so the state names them instead of one yes/no for all.
        blocked = sorted({str(e.get("currency")).strip().upper() for e in self._events.values()
                          if -self._keep_past_s <= (e["scheduled_at"] - now) <= self._alert_before_s
                          and self._blocks_entry(e)})
        inside = bool(blocked)
        # ٢٠٢٦-٠٩-١٨ — الأفق يُحسب دائمًا ويُنشر دائمًا؛ وهل يُسكِت
        # `known` أم لا فعيارٌ في يد المالك (مطفأ افتراضيًّا).
        horizon = self._horizon()
        horizon_seconds = (horizon - now) if horizon is not None else None
        known = self._valid_received > 0
        if self._require_forward_horizon:
            known = known and horizon_seconds is not None and horizon_seconds > 0
        state = (known, tuple(blocked))
        changed = state != self._last_state
        # ٢٠٢٦-٠٩-١٦ — نبض إعادة بثّ الحالة.
        #
        # `market_data.calendar.state` حدثُ **حالة** كان يُنشر عند التغيّر
        # وحده: `published=4` مقابل `duplicate=1088` في تشغيلة كاملة. فمن
        # يفقد الحالة ينتظر التغيّر التالي وقد يكون بعد ساعات — ووقع ذلك
        # اليوم: 454 (فلتر القرار) أُعيد تحميله ساخنًا فحجب **1,199 قرارًا
        # من 1,199** بسبب `calendar_unknown`، وحجبه صحيح تصميمًا.
        #
        # والفرق الدلاليّ محفوظ: `EVENT_WINDOW` حدثُ **حدوث** (دخلنا نافذة
        # أو خرجنا) فلا يُعاد — إعادته تكذب بأنّ شيئًا وقع. و`EVENT_STATE`
        # حالةٌ راهنة فتُعاد، وهي تحمل `utc` الآن فيُرى عمرها.
        heartbeat = self._heartbeat_due(now)
        if changed or heartbeat:
            self._last_state = state
            self._in_window = inside
            self._published += 1
            if not changed:
                self.heartbeats_sent += 1
            body = {"known": known, "in_event_window": inside, "blocked_currencies": blocked,
                "status": "BLOCKED" if inside else "CLEAR" if known else "UNKNOWN",
                "allow_new_entries": known and not inside,
                "alert_before_seconds": self._alert_before_s, "utc": now,
                # مَن يقرأ الحجب يرى بأيّ قاعدةٍ حُجب — لا رقمًا بلا سبب
                "blocking_currencies": sorted(self._blocking_currencies),
                "blocking_min_impact": self._blocking_min_impact or None,
                # مَن يقرأ `CLEAR` يرى إلى أيّ مدًى تمتدّ معرفتنا: صفاءٌ
                # لساعةٍ ليس صفاءً ليوم، والفرق لا يُقرأ من الحالة وحدها.
                "horizon_utc": horizon,
                "horizon_seconds": (round(horizon_seconds, 1)
                                    if horizon_seconds is not None else None),
                "tracked": len(self._events),
                # 2026-10-17 (owner seal, step 14): the coming blocking news and the time left to each -- the red
                # line and the "enough time before it" rule read them; the panel shows them.
                "next_blocking": self._next_blocking(now)}
            if changed:
                await self._context.publish(EVENT_WINDOW, dict(body))
            await self._context.publish(EVENT_STATE, dict(body))

    def _next_blocking(self, now: float, limit: int = NEXT_BLOCKING_SHOWN) -> list[dict[str, Any]]:
        ordered = sorted((e for e in self._events.values()
                          if e["scheduled_at"] - now > -self._keep_past_s and self._blocks_entry(e)),
                         key=lambda e: e["scheduled_at"])
        # 2026-10-23 (law 24): with every currency blocking, the first few could all be foreign to an asset and push its own
        # next red line out of the list -- so each currency's nearest one is always kept beside the first `limit`.
        coming = ordered[:limit]
        shown = {str(e.get("currency")).strip().upper() for e in coming}
        for event in ordered[limit:]:
            name = str(event.get("currency")).strip().upper()
            if name not in shown:
                shown.add(name)
                coming.append(event)
        return [{"title": e["title"], "currency": e.get("currency"), "impact_level": e.get("impact_level"),
                 "source_impact_level": e.get("source_impact_level"), "color_from": e.get("color_from"),
                 "scheduled_at": e["scheduled_at"], "seconds_until": round(e["scheduled_at"] - now, 1),
                 "red_line_from": e["scheduled_at"] - self._alert_before_s,
                 "red_line_until": e["scheduled_at"] + self._keep_past_s} for e in coming]

    async def snapshot(self) -> dict[str, Any]:
        return {
            "version": ATOM_VERSION,
            "events": [dict(event) for event in self._events.values()],
            "announced": sorted(self._announced),
            "source_seen": self._received > 0,
            "valid_received": self._valid_received,
            "now_utc": self._now_utc,
        }

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict) or not isinstance(state.get("events"), list):
            self._events = {}
            self._announced = set()
            self._valid_received = 0
            self._restore_error = "CALENDAR_RESTORE_FAILED_UNKNOWN"
            raise ValueError(self._restore_error)
        restored: dict[str, dict[str, Any]] = {}
        for raw in state["events"]:
            if not isinstance(raw, dict):
                self._restore_error = "CALENDAR_RESTORE_FAILED_UNKNOWN"
                raise ValueError(self._restore_error)
            key = str(raw.get("id") or "").strip()
            title = str(raw.get("title") or "").strip()
            scheduled = _to_float(raw.get("scheduled_at"))
            if not key or not title or scheduled is None or scheduled <= 0:
                self._restore_error = "CALENDAR_RESTORE_FAILED_UNKNOWN"
                raise ValueError(self._restore_error)
            # A snapshot from before 3.11.0 holds the source's impact: our reference recolors it on the way back in.
            source_impact = _impact(raw.get("source_impact_level") or raw.get("impact_level"))
            reference = self._reference(title, raw.get("currency"))
            restored[key] = {**raw, "id": key, "title": title,
                             "scheduled_at": scheduled,
                             "impact_level": reference or source_impact,
                             "source_impact_level": source_impact,
                             "color_from": COLOR_FROM_REFERENCE if reference else COLOR_FROM_SOURCE}
        self._events = restored
        announced = state.get("announced")
        self._announced = ({str(x) for x in announced if str(x) in restored}
                           if isinstance(announced, list) else set())
        source_seen = state.get("source_seen") is True
        self._received = max(self._received, 1 if source_seen else 0)
        self._valid_received = max(len(restored), int(state.get("valid_received") or 0))
        self._now_utc = _to_float(state.get("now_utc")) or 0.0
        self._last_state = None
        self._restore_error = ""
        self._restored_pending_prune = True
        # ٢٠٢٦-٠٩-١٦ — تُعاد قسمة الحاجب/غير الحاجب بعد الاستعادة.
        #
        # العدّادات تُحسب في `_on_calendar`، والاستعادة تتجاوزه فتملأ
        # `_events` مباشرة. فبعد أوّل تحميل ساخن كانت الرسالة تقول
        # `tracked=138 · يحجب USD/HIGH (0 من 0)` — عدّادٌ يناقض جاره على
        # السطر نفسه. مقيس حيًّا لحظة نشر 3.4.0.
        self.blocking_tracked = 0
        self.non_blocking_tracked = 0
        self.unknown_currency_tracked = 0
        self.reference_hits = 0
        self.unreferenced_blocking_currency = 0
        self._unreferenced_titles = []
        for event in self._events.values():
            self._count_color(event)
            if self._blocks_entry(event):
                self.blocking_tracked += 1
            else:
                self.non_blocking_tracked += 1
            if not str(event.get("currency") or "").strip():
                self.unknown_currency_tracked += 1

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"received": self._received, "published": self._published,
                   "restore_error": self._restore_error,
                   "tracked": len(self._events), "in_window": self._in_window,
                   "rejected": {k: v for k, v in self._rejected.items() if v}}
        if not self._now_utc:
            return HealthStatus(
                state=HealthState.DEGRADED, message=REASON_NO_TIME, details=details)
        if self._received == 0:
            return HealthStatus(
                state=HealthState.DEGRADED, message=REASON_NO_SOURCE, details=details)
        # أسباب الرفض في `message`: النواة تحذف `details` قبل اللوحة.
        message = "tracked=%d published=%d" % (len(self._events), self._published)
        # ٢٠٢٦-٠٩-١٨ — الأفق: إلى أين تمتدّ معرفتنا من هذه اللحظة.
        #
        # وهو الرقم الذي كان غائبًا تمامًا: الذرّة تقول `CLEAR` بثقة
        # سواءٌ عرفت أسبوعًا قادمًا أو لم يبقَ أمامها شيء.
        horizon = self._horizon()
        blind = horizon is None or horizon <= self._now_utc
        if horizon is None:
            message += " · أفق: لا حدث أمامنا"
        else:
            ahead = horizon - self._now_utc
            message += " · أفق=%.1f ساعة" % (ahead / 3600.0)
        # ٢٠٢٦-٠٩-١٩ — أثرُ العيار معلَنٌ في السطر نفسه: من يرى «انتهى الأفق»
        # يجب أن يرى هل أُغلق الباب أم بقي مفتوحًا، لا أن يذهب يفتّش.
        if self._require_forward_horizon:
            message += " (يوقف الدخول عند انقضائه)"
            if self._using_default_horizon:
                message += " [افتراضيّ]"
        else:
            message += " (لا يحجب — بقرارٍ صريح)"
        # قاعدة الحجب معلنة: من يرى «دخول ممنوع» يرى بأيّ حكمٍ مُنع
        if self._blocking_currencies or self._blocking_min_impact or self._blocking_titles:
            rule = "+".join(sorted(self._blocking_currencies)) or "كل العملات"
            if self._blocking_titles:
                rule += "/أسماء(%d)" % len(self._blocking_titles)
            elif self._blocking_min_impact:
                rule += "/" + self._blocking_min_impact
            if self._using_default_titles or self._using_default_currencies:
                # لا يُقرأ حكمٌ منفَّذًا من مصدرٍ لم يُقصد: العيار افتراضيّ
                # الكود لأنّ `config` لم يبلغ الذرّة (يحتاج إقلاعًا).
                rule += " [افتراضيّ]"
            # ٢٠٢٦-٠٩-١٨ — تُعدّ من `_events` لا من العدّادين التراكميّين.
            #
            # `blocking_tracked` يرتفع مع كلّ حدثٍ **يُقبل**، والمصدر يعيد
            # إرسال تقويمه كاملًا فيُقبل الماضي ثمّ يُقلَّم في الثانية
            # التالية. فكانت الرسالة تقول `(16 من 422)` بينما المتتبَّع
            # حدثٌ واحد — رقمٌ عن دورةٍ ماضية يُقرأ حالةً راهنة.
            blocking = sum(1 for e in self._events.values() if self._blocks_entry(e))
            message += " · يحجب %s (%d من %d)" % (
                rule, blocking, len(self._events))
        unknown_currency = sum(1 for e in self._events.values()
                               if not str(e.get("currency") or "").strip())
        if unknown_currency:
            message += " · بلا عملة=%d (لا تحجب)" % unknown_currency
        # 2026-10-17: which color decided -- ours, or the source's (a title our reference lacks, or the reference not loaded).
        if _reference_impact is None:
            message += " · مرجع الألوان غير محمّل (تصنيف المصدر)"
        else:
            message += " · لون المرجع=%d · خارج المرجع=%d" % (self.reference_hits, self.unreferenced_blocking_currency)
        details["reference_loaded"] = _reference_impact is not None
        details["unreferenced_titles"] = list(self._unreferenced_titles)
        rejected = {k: v for k, v in self._rejected.items() if v}
        if rejected:
            message += " · مرفوض " + " ".join(
                "%s=%d" % (name, count)
                for name, count in sorted(rejected.items(), key=lambda kv: -kv[1]))
        if self._in_window:
            message += " · نافذة حدث: دخول ممنوع"
        details["horizon_utc"] = horizon
        details["blind"] = blind
        if blind:
            # الشارة تصفرّ قبل أن يؤذي العمى: التقويم انتهى ونحن ما زلنا
            # نعلن حالةً عنه. ومن أوقف الحجب بالأفق يرى هنا ثمن قراره.
            return HealthStatus(
                state=HealthState.DEGRADED,
                message="أفق التقويم انتهى — " + message, details=details)
        return HealthStatus(state=HealthState.HEALTHY, message=message, details=details)
