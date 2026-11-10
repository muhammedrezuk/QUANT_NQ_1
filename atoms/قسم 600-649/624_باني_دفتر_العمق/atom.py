"""باني دفتر العمق (624) — من تحديثات المستويات إلى سلّم.

المصدر 622 يُسلّم تحديثات المستويات كما وردت من سي‑تريدر (`W` لقطة و`X`
تزايديّ) ولا يبني شيئًا: بناء الدفتر ليس عمل مصدر، وحملُه كان يؤخّر تفريغ
المقبس فيتراكم المخزن.

هذه الذرّة تملك الدفتر وحده. تُطبّق كل تحديث على سلّم رمزه، وتنشر السلّم
على `market.depth` — العقد نفسه الذي كان 622 ينشره، فلم يتغيّر حرف عند 106
خلفها. والقمّة تخرج معه، فيشتقّ منها 623 التِكّة بلا أن يبني دفترًا ثانيًا.

**لا تحكم على صلاحية سعر.** السلّم يخرج كما بُني — ناقصًا أو مقلوبًا أو
خاليًا — ومن يملك الحكم هو 106 و112، وكلاهما يُعلن سببه.
"""
from __future__ import annotations

import heapq
import time
from typing import Any

import shared.fix_session as fx
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.11.0"
# v1.4.0 (٢٠٢٦-٠٩-٠٩، أمر المالك «حط حد ينظفها · رجع سقف»): سقف على الدفتر
# نفسه (`max_book_levels`) لا على المنشور وحده. سي‑تريدر لا يحذف ما هجره،
# فالسلّم بلغ 1,767 عرضًا و357 طلبًا، ثمّ 1,724 مستوًى في دقائق حين ضاعف
# تدفّقٌ خاطئ القيود — والطرف المتضخّم يتقاطع فيُرفض كلّ شيء (الرفض ٢٦٪).
# التقليم يُسقط الأبعد عن القمّة، والقمّة آخر ما يُمسّ. التفصيل في `_trim_book`.
# v1.3.0 (٢٠٢٦-٠٩-٠٩): **العمق المنشور صار مقلَّمًا — والقياس هو السبب.**
# قِيس حيًّا على القناة: رسالة `market.depth` واحدة لـBTCUSD = **57,487 بايتًا**
# فيها 1,767 عرضًا و357 طلبًا، تُنشر 1.7 مرّة في الثانية وتُنسخ لكلّ مشترك.
# ومن يقرؤها اثنان لا غير: 106 يأخذ `max_levels: 10` من كلّ طرف ويرمي الباقي،
# و623 لا يمسّ السلّم أصلًا — `best_bid`/`best_ask` وحدهما. أي أنّ **٩٩.٥٪ من
# الحمولة تُبنى وتُسلسَل وتُبثّ ثمّ تُرمى**. وثمنها مقيس: النواة 72% من نواة
# معالج، وقفزات ذاكرة 2.2 جيجا في عشرين ثانية على جهاز حرّه 992 ميغا، وتوقّفات
# تُفوّت نبضة سي‑تريدر — 337 إعادة اتصال في يوم — واللوحة تقرأ «مقطوع» بينما
# التِكّة تُصنع فعلًا (623 يُصدر 1.7/ث ووصل المشترك 1 كلّ 90 ثانية).
# **الدفتر لم يُمسّ:** يبقى كاملًا في الذاكرة، والقمّة تُقرأ منه كاملًا، والقصّ
# عرضٌ فقط. والعدد المقصوص يُعلَن في الحمولة (`bid_levels_total`) فلا يُرمى
# شيء بصمت. العيار بيد المالك، وصفر يُعيد السلوك الأوّل حرفيًّا.
# v1.2.0 (٢٠٢٦-٠٩-٠٩، ختم المالك `NQ`): عمر هجر المستوى صار **عيارًا** يُقرأ
# من المانيفست بدل ثابتٍ في `shared/fix_session`. سببه مقيس: سي‑تريدر لا
# يرسل لقطة `W` في التشغيل المستقرّ (صفر لقطة على 200 ثانية) ولا يحذف إلا
# قيدًا عمره ≤ 0.4 ثانية — فمن 502 قيدٍ وُلد بقي 474 حيًّا، وبلغ السلّم 278
# مستوًى فتقاطع الطرفان ورفض 112 سبعةً وثمانين بالمئة. والعتبة القديمة (30ث)
# كانت أبطأ من هجر السعر نفسه. **بيد المالك الآن يضبطها بلا لمس كود.**

EVENT_IN = "feed.ctrader.raw"
EVENT_DEPTH = "market.depth"
EVENT_STATE = "market.book.state"

REASON_NOT_STARTED = "NOT_STARTED"

_PASSTHROUGH = ("account_id", "broker", "provider", "build", "sequence",
                "sequence_gap", "out_of_order", "fabric_gap",
                "exchange_timestamp", "received_at", "timestamp")


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._state_every = 1000
        self._crossed_stale_after_s = 0.0   # 0 = خُذ افتراضيّ الدفتر المعلَن
        self._publish_levels = 0            # 0 = انشر السلّم كاملًا (السلوك الأوّل)
        self._max_book_levels = 0           # 0 = بلا سقف (السلوك الأوّل)
        self._trimmed = 0
        self._min_publish_interval_s = 0.0  # 0 = انشر كل تحديث (السلوك الأوّل)
        self._stale_level_after_s = 0.0     # 0 = لا إسقاط بالعمر (السلوك الأوّل)
        self._stale_dropped = 0
        self._last_publish_at: dict[str, float] = {}
        self._coalesced = 0
        # ٢٠٢٦-٠٩-٠٩: قِيس على الناقل أنّ 622 ينشر 15.15 رسالة/ث وهذه الذرّة
        # تُخرج 3.09 — أي **خُمس** ما يَرِد. ولم يكن في الذرّة عدّادٌ يفصل
        # «لم تصلني» عن «وصلتني ورميتُها»: `malformed` و`coalesced` صفر،
        # وباب الخروج الأوّل (`not self._running`) كان يرجع **بلا أثر**.
        # هذه العدّادات هي الفصل، وغيابها هو ما جعلني أدّعي مواكبةً كاذبة.
        self._received = 0          # كل استدعاء وصل المعالج
        self._skipped_stopped = 0   # وصل والذرّة موقوفة أو بلا سياق
        self._books: dict[str, fx.Book] = {}
        self._applied = 0
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
        self._published = 0
        self._snapshots = 0
        self._malformed = 0
        self._last_symbol = ""

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._state_every = int(context.config["state_every"])
        self._crossed_stale_after_s = float(
            context.config.get("crossed_stale_after_s", 0.0))
        self._publish_levels = int(context.config.get("publish_levels", 0) or 0)
        self._max_book_levels = int(context.config.get("max_book_levels", 0) or 0)
        self._stale_level_after_s = float(
            context.config.get("stale_level_after_s", 0.0) or 0.0)
        self._min_publish_interval_s = float(
            context.config.get("min_publish_interval_s", 0.0) or 0.0)
        context.subscribe(EVENT_IN, self._on_raw)

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

    async def _on_raw(self, payload: dict[str, Any]) -> None:
        self._received += 1
        if not self._running or self._context is None:
            # نسخةٌ موقوفة ما زالت مشتركة تبتلع الحدث بصمت — هذا الباب كان
            # بلا عدّاد، وهو أوّل ما يجب أن يُرى عند اختلال المرور.
            self._skipped_stopped += 1
            return
        if not isinstance(payload, dict):
            self._malformed += 1
            return
        symbol = str(payload.get("symbol") or "").strip()
        entries = payload.get("entries")
        if not symbol or not isinstance(entries, list):
            # بلا رمز لا يُعرف الدفتر، وبلا قائمة مستويات لا شيء يُطبَّق.
            # هذا عجز عن البناء لا حكم على السعر.
            self._malformed += 1
            return

        self._gauge_age(payload)
        book = self._books.get(symbol)
        if book is None:
            book = self._books[symbol] = fx.Book(
                stale_after_s=self._crossed_stale_after_s)
        is_snapshot = payload.get("is_snapshot") is True
        if is_snapshot:
            book.clear()
            self._snapshots += 1
        for row in entries:
            if not isinstance(row, dict):
                self._malformed += 1
                continue
            entry_id = row.get("entry_id")
            if not entry_id:
                continue
            book.apply(row.get("entry_type"), str(entry_id), row.get("price"),
                       row.get("size"), row.get("action"))
            self._applied += 1

        self._drop_stale_levels(book)
        self._trim_book(book)
        # ── مُواءمة المعدّل: الدفتر يُبنى كاملًا، والنشر بمعدّل تهضمه السلسلة.
        # قِيس ٢٠٢٦-٠٩-٠٩: الوسيط يبعث 10 رسائل/ث، وما خلف 624 يهضم 3.5/ث،
        # فالفارق يتراكم بلا سقف — عمر الطابع عند المصدر 13–25 ثانية وعند
        # التِكّة 211–262. **لا مستوى يضيع**: كل تحديث طُبِّق أعلاه على الدفتر،
        # وما يُسقَط هو نشرةٌ وسيطة أعقبتها أحدثُ منها لنفس الرمز. واللقطة
        # لا تُدمج أبدًا — هي إعادة بناء، لا خطوة وسيطة.
        if (self._min_publish_interval_s > 0 and not is_snapshot
                and self._context is not None):
            now_mono = time.monotonic()
            last = self._last_publish_at.get(symbol)
            if last is not None and (now_mono - last) < self._min_publish_interval_s:
                self._coalesced += 1
                return
        bids, asks = book.ladder()
        if self._publish_levels > 0:
            # القصّ هنا لا في `Book.ladder`: التحميل الساخن يطهّر وحدات الذرّة
            # وحدها (`core/hot_reload_service.py:453`) ويبقي `shared/` مخبّأً في
            # `sys.modules`، فاستدعاء توقيع جديد هناك كان سيرمي `TypeError` على
            # الطريق الحيّ عند أوّل `rescan`. الذرّة تقصّ ما تنشره بنفسها.
            bids, asks = bids[:self._publish_levels], asks[:self._publish_levels]
        # القمّة من الدفتر الكامل لا من المقصوص — القصّ عرضٌ لا يغيّر سعرًا.
        best_bid, best_ask = book.top()
        self._last_symbol = symbol
        out = {key: payload.get(key) for key in _PASSTHROUGH if key in payload}
        out.update({"symbol": symbol, "bids": bids, "asks": asks,
                    "best_bid": best_bid, "best_ask": best_ask,
                    "is_snapshot": is_snapshot,
                    # ما قُصّ يُعلَن: القارئ يعرف أنّه يرى طرفًا لا كلًّا،
                    # ويعرف كم كان الكلّ. الرمي بصمت كذبةٌ صغيرة.
                    "bid_levels_total": len(book.bids),
                    "ask_levels_total": len(book.asks),
                    "publish_levels": self._publish_levels,
                    "book_empty": (best_bid is None and best_ask is None)})
        _t0 = time.perf_counter()
        await self._context.publish(EVENT_DEPTH, out)
        _dt = time.perf_counter() - _t0
        self._pub_ewma = _dt if not self._pub_ewma else (self._pub_ewma * 0.99 + _dt * 0.01)
        if _dt > self._pub_max:
            self._pub_max = _dt
        # النافذة تُفتح بكل نشرة — واللقطة منها: هي أيضًا وصلت المشتركين،
        # فبدؤها النافذةَ هو ما يمنع تزايديًّا يتلوها من المرور مجّانًا.
        self._last_publish_at[symbol] = time.monotonic()
        self._published += 1
        if self._state_every and self._published % self._state_every == 0:
            await self._context.publish(EVENT_STATE, {
                "symbols": len(self._books), "applied": self._applied,
                "published": self._published, "snapshots": self._snapshots,
                "malformed": self._malformed,
                "orphan_updates": sum(b.orphan_updates for b in self._books.values()),
                "publish_levels": self._publish_levels,
                "max_book_levels": self._max_book_levels,
                "trimmed": self._trimmed,
                "stale_dropped": self._stale_dropped,
                "coalesced": self._coalesced,
                "received": self._received,
                "skipped_stopped": self._skipped_stopped,
                "deepest_ladder": self._deepest_ladder(),
                "last_symbol": self._last_symbol})

    def _drop_stale_levels(self, book: "fx.Book") -> None:
        """يُسقط كل مستوًى لم يلمسه الوسيط منذ العتبة — متقاطعًا كان أو لا.

        ٢٠٢٦-٠٩-١٠ — القياس الذي أوجبه: على أربع عشرة دقيقة بعد إقلاع نظيف
        نما السلّم **14 ⟵ 600** بلا أن يستقرّ (≈42 مستوًى في الدقيقة)، وهبط
        قبول 112 من **٩٨.١٪ إلى ٨٦.٥٪** في النافذة نفسها. أي أنّه **لا يوجد
        «عمق طبيعيّ»** يُشتقّ منه سقف: أيّ سقف يُضرَب، وأيّ رقم يُختار يَبطل.

        والسبب أنّ حارس التقاطع يُسقط المهجور **حين يتقاطع فقط**، والمهجور
        الذي لم يتقاطع بعدُ يتراكم بلا حدّ حتى يبلغ القمّة فيفسدها. فالعلاج
        في موضع العلّة: سي‑تريدر لا يحذف ما هجره (دورة حذفه المقيسة 0.4
        ثانية تطال القيد النشط وحده)، فنُسقط نحن ما توقّف عن لمسه.

        **لا يحكم على سعر:** لا ينظر إلى قيمة ولا إلى تقاطع — ينظر إلى صمت
        الوسيط عن قيدٍ بعينه. والمستوى الحيّ يُلمس في أجزاء من الثانية، فلا
        تبلغه عتبةٌ بالثواني. و`_touched` يُقرأ بـ`getattr` فنسخةٌ من
        `shared` لا تعرفه لا تُسقط الطريق الحيّ.
        """
        after = self._stale_level_after_s
        if after <= 0:
            return
        touched = getattr(book, "_touched", None)
        if not isinstance(touched, dict) or not touched:
            return
        clock = getattr(book, "_clock", None)
        now = clock() if callable(clock) else None
        if now is None:
            return
        seen = getattr(book, "_seen", None)
        for entry_id in [k for k, at in touched.items() if (now - at) >= after]:
            gone = book.bids.pop(entry_id, None) is not None
            gone = (book.asks.pop(entry_id, None) is not None) or gone
            touched.pop(entry_id, None)
            if isinstance(seen, dict):
                seen.pop(entry_id, None)
            if gone:
                self._stale_dropped += 1

    def _trim_book(self, book: "fx.Book") -> None:
        """سقف على الدفتر نفسه — يُسقط الأبعد عن القمّة، ولا يمسّ القمّة أبدًا.

        ٢٠٢٦-٠٩-٠٩ (أمر المالك: «حط حد ينظفها · رجع سقف») — العلّة المقيسة:
        سي‑تريدر لا يحذف المستوى الذي هجره، فالسلّم ينمو بلا سقف. قِيس اليوم
        1,767 عرضًا و357 طلبًا على BTCUSD، ثمّ 1,724 مستوًى في دقائق حين
        ضاعف تدفّقٌ خاطئ القيود. والنموّ ليس عبئًا فقط: الطرف المتضخّم يتجاوزه
        السعر فيتقاطع الطرفان، فيرفض 106 و112 كلّ تِكّة (قِيس الرفض ٢٦٪).

        **لا يحكم على سعر.** يبقي الأقرب إلى القمّة ويُسقط الأبعد — وهو ما
        لا يقرؤه أحد أصلًا: مستهلك السلّم الوحيد (106) سقفه عشرة مستويات،
        و623 يقرأ القمّة وحدها. والقمّة هي آخر ما يُسقط، لا أوّله.

        ويُنظِّف خلفه: `_seen` و`_touched` عند الدفتر يُبنيان مع كل قيد، فلو
        أُسقط القيد وحده لنمَوَا خلفه بلا حدّ — تسريبة صامتة مكان تسريبة
        مرئيّة. وكلاهما يُلمس عبر `getattr` فنسخةُ `shared` التي لا تعرفهما
        لا تُسقط الطريق الحيّ (درس ٢٠٢٦-٠٩-٠٩: التحميل الحارّ يُبقي `shared`
        مخبّأً، وتوقيعٌ مفقود هناك كان يرمي على كل رسالة).
        """
        cap = self._max_book_levels
        if cap <= 0:
            return
        seen = getattr(book, "_seen", None)
        touched = getattr(book, "_touched", None)
        for side, keep_highest in ((book.bids, True), (book.asks, False)):
            extra = len(side) - cap
            if extra <= 0:
                continue
            pick = heapq.nsmallest if keep_highest else heapq.nlargest
            # الأسوأ سعرًا = الأبعد عن القمّة: أدنى عرضٍ وأعلى طلب.
            for entry_id in pick(extra, side, key=lambda k: side[k][0]):
                side.pop(entry_id, None)
                if isinstance(seen, dict):
                    seen.pop(entry_id, None)
                if isinstance(touched, dict):
                    touched.pop(entry_id, None)
                self._trimmed += 1

    def _deepest_ladder(self) -> int:
        """أعرض سلّم محفوظ الآن — مقياس التضخّم الذي كان يُبثّ كاملًا."""
        return max((len(b.bids) + len(b.asks) for b in self._books.values()),
                   default=0)

    async def health_check(self) -> HealthStatus:
        orphans = sum(b.orphan_updates for b in self._books.values())
        # ٢٠٢٦-٠٩-٠٩ (ختم المالك `NQ`): مستوًى هجره الوسيط يبقى في السلّم حتى
        # يتجاوزه السوق فيتقاطع الطرفان، و`Book._drop_crossed` يُسقط الأقدم.
        # يُعلَن في الرسالة لا في `details` وحدها: `details` تُحذف عند
        # `core/api/app.py:93` فلا تصل لوحةً ولا API — وما لا يُقرأ لا يُعدّ
        # معلنًا (قانون المالك: ما يُرمى بصمت لا يُرى).
        crossed = sum(b.crossed_dropped for b in self._books.values())
        deepest = self._deepest_ladder()
        details = {"symbols": len(self._books), "applied": self._applied,
                   "published": self._published, "snapshots": self._snapshots,
                   "malformed": self._malformed, "orphan_updates": orphans,
                   "crossed_dropped": crossed, "publish_levels": self._publish_levels,
                   "max_book_levels": self._max_book_levels, "trimmed": self._trimmed,
                   "stale_dropped": self._stale_dropped,
                   "coalesced": self._coalesced, "received": self._received,
                   "skipped_stopped": self._skipped_stopped,
                   "deepest_ladder": deepest, "last_symbol": self._last_symbol,
                   "age_last_s": round(self._age_last, 3),
                   "age_ewma_s": round(self._age_ewma, 3),
                   "age_max_s": round(self._age_max, 3),
                   "publish_ewma_ms": round(self._pub_ewma * 1000.0, 3),
                   "publish_max_ms": round(self._pub_max * 1000.0, 3)}
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY,
                                message=REASON_NOT_STARTED, details=details)
        if self._published == 0:
            return HealthStatus(
                state=HealthState.HEALTHY,
                message="READY_AWAITING_FIRST_RAW_UPDATE | published=0",
                details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message=("books=%d applied=%d published=%d orphans=%d crossed=%d "
                     "malformed=%d deepest=%d cut=%d cap=%d trimmed=%d stale=%d coalesced=%d "
                     # العمر في الرسالة لا في `details` وحدها: `details`
                     # تُقصّ عند النواة فلا تبلغ لوحةً ولا API.
                     "rcv=%d stopped=%d age=%.2f/%.2f/%.2fث pub=%.2f/%.0fم.ث" % (
                         len(self._books), self._applied, self._published, orphans,
                         crossed, self._malformed, deepest, self._publish_levels,
                         self._max_book_levels, self._trimmed, self._stale_dropped, self._coalesced,
                         self._received, self._skipped_stopped,
                         self._age_last, self._age_ewma, self._age_max,
                         self._pub_ewma * 1000.0, self._pub_max * 1000.0)),
            details=details)

    async def snapshot(self) -> dict[str, Any]:
        # الدفتر نفسه لا يُحفظ: سلّم مُعاد من لقطة قديمة سلّمٌ يكذب. تُحفظ
        # العدّادات وحدها، ويُعاد البناء من أوّل لقطة `W` يرسلها المصدر.
        return {"version": ATOM_VERSION, "applied": self._applied,
                "published": self._published, "snapshots": self._snapshots,
                "malformed": self._malformed}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self._applied = int(state.get("applied") or 0)
        self._published = int(state.get("published") or 0)
        self._snapshots = int(state.get("snapshots") or 0)
        self._malformed = int(state.get("malformed") or 0)
