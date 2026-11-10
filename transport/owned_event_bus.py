"""Executable Event Ownership transport for the production runner.

The frozen ``core.event_bus.EventBus`` remains the compatibility implementation.
This adapter keeps its public contract while moving delivery into owned worker
lanes:

* ingress normalizes and copies a payload once;
* default consumers receive one recursively read-only object by reference;
* every Account×Symbol partition has one stable worker owner, preserving FIFO
  ordering for that state;
* unscoped legacy handlers have one stable worker owner;
* worker mailboxes are bounded, fair, coalescing for state events, and visible;
* handler errors/timeouts remain isolated by the original core delivery code;
* the Account×Symbol ownership map is deterministic across restarts;
* explicit ``isolate_payload=True`` remains available for a private consumer.

This is a transport/runtime change only. Event names, atom code, and trading
rules are not changed.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
import uuid
from collections import Counter
from typing import Any, Callable

from clock import now as official_now
from core.event_bus import _LIGHT_BUDGET_S, EventBus, _fast_copy, _is_replayable
from core.logger import current_event, current_event_id, current_trace_id
from .latency_probe import LatencyProbe
from .ownership import OwnershipRuntime, default_worker_count
from .readonly import freeze_payload

_log = logging.getLogger("quant_nq.transport.owned_event_bus")


class OwnedEventBus(EventBus):
    """EventBus-compatible transport with owned execution lanes."""

    def __init__(
        self,
        *,
        payload_mode: str = "shared_readonly",
        # صفر = اكتشف من موارد الجهاز (§٨). كان الافتراض ٤ مثبّتًا في الكود،
        # و§٣٣ تمنع «تثبيت عدد العمليات على الجهاز الحالي».
        worker_count: int = 0,
        mailbox_max_events: int = 1024,
        cold_sections: Any = None,
        partitioned_ownership: bool = True,
        # §١٤ — تقسيم النطاق إلى مجموعات. الواحد = بلا تقسيم، وهو الافتراض:
        # لا يتبدّل مسارٌ واحد ما لم يُعلَن العدد في الإعداد.
        scope_groups: int = 1,
        # أحداث المال: تُسمّى دائمًا حين تُسقَط أو تُدمَج، بلا قصّ (§٢٤).
        critical_prefixes: Any = (),
        **kwargs: Any,
    ) -> None:
        mode = str(payload_mode).strip().lower()
        if mode not in {"shared_readonly", "isolated"}:
            raise ValueError("payload_mode must be 'shared_readonly' or 'isolated'")
        super().__init__(mailbox_max_events=mailbox_max_events, **kwargs)
        self.payload_mode = mode
        requested = int(worker_count)
        self.worker_count = requested if requested > 0 else default_worker_count()
        self._cold_handlers: set[int] = set()
        #: نطاقات المشترِكين الذين يُثبَّتون على المسار البارد.
        #:
        #: ⛔ **العطب المقيس ٢٠٢٦-٠٩-١٠:** المخازن تشترك بـ`subscribe` فتجلس
        #: على مسارات السوق. و`707` حجب مساره **2,230 مرّة، أسوأها 5.64 ثانية**،
        #: و`712` كان ينادي `VACUUM` **داخل معالج الحدث** — دورة قِيست بـ252
        #: ثانية. ومسار الملكية يسلّم بالتتابع، فمن يحجب مساره يحجب كلّ ما خلفه.
        #:
        #: العزل **لا يجعل المخزن أسرع** — يمنعه من تعطيل طريق السوق.
        #: وثمنه معلَن: المسار البارد **واحد**، فالمخازن تتزاحم فيما بينها.
        #: وهذا مقصود: التِكّة قبل السجلّ.
        self._cold_sections = tuple(
            (int(low), int(high)) for low, high in (cold_sections or ()))
        #: مشترِكون عامّون اختاروا المسار الساخن صراحةً بنطاقٍ معلَن.
        #: القائمة تُبنى من نداءات `subscribe_all(hot_scope=…)` لا من إعداد.
        self._declared_hot_globals: dict[str, str] = {}
        self._published_total = 0
        #: مسبار `تِكّة ← قرار` — يقرأ مرور الأحداث ولا يضيف حقلًا لحمولة.
        self.latency = LatencyProbe()
        # §٢٤ — التجاوز **باسم المشترِك**. النواة تعدّه باسم الحدث، وحدثٌ
        # واحد قد يبطئه مشترِكٌ واحد من خمسة: العدّاد باسم الحدث يتّهم
        # الحدث، والعدّاد باسم المشترِك يسمّي البطيء نفسه.
        self._overrun_by_subscriber: Counter[str] = Counter()
        self._overrun_worst_by_subscriber: dict[str, float] = {}
        self._shared_published = 0
        self._shared_deliveries = 0
        self._private_deliveries = 0
        self._runtime = OwnershipRuntime(
            worker_count=self.worker_count,
            mailbox_max_events=mailbox_max_events,
            dispatch=self._dispatch_owned,
            is_active=self._handler_is_active,
            partitioned=partitioned_ownership,
            scope_groups=scope_groups,
            critical_prefixes=critical_prefixes,
        )

    def _is_cold_subscriber(self, subscriber: str) -> bool:
        """هل يُثبَّت هذا المشترِك على المسار البارد؟

        ثلاثة أبواب: بادئة `cold:` صريحة · الأسماء المعروفة (اللوحة والقياس)
        · ورقم ذرّة داخل نطاق معلَن في الإعداد. والنطاق **من الإعداد** لا من
        الكود — §٤٣ تمنع تثبيت أرقام الأقسام في الطبقة التحتيّة.
        """
        name = str(subscriber or "")
        if name.startswith("cold:") or name in {"core.api", "dashboard", "telemetry"}:
            return True
        if not self._cold_sections or not name.isdigit():
            return False
        number = int(name)
        return any(low <= number <= high for low, high in self._cold_sections)

    def _enqueue(self, handler_id: int, item: tuple[Any, ...], event_name: str) -> None:
        """Route one reference into an owned worker mailbox.

        ``EventBus.subscribe`` and ``subscribe_all`` call this method for state
        replay too, so late consumers use the same ordering and supervision
        path as live events.
        """
        if item and item[0] == "sub":
            sub = item[3]
            subscriber = str(getattr(sub, "subscriber", ""))
        else:
            extra = item[3]
            subscriber = str(extra[1]) if len(extra) > 1 else ""
        self._runtime.enqueue(
            handler_id,
            subscriber,
            item[2] if len(item) > 2 else None,
            item,
            event_name,
            cold=handler_id in self._cold_handlers,
        )

    async def _dispatch_owned(self, _handler_id: int, item: tuple[Any, ...]) -> None:
        """Use the original core timeout/error isolation after routing.

        ويُقاس هنا **زمن التسليم باسم المشترِك** بالميزانية نفسها التي
        تستعملها النواة (`_LIGHT_BUDGET_S`)، فيكون الرقمان قابلين للمقارنة:
        النواة تقول «أيّ حدثٍ تجاوز» وهذا يقول «أيّ مشترِكٍ أبطأه».
        """
        kind, event_name, payload, extra = item
        if kind == "sub":
            subscriber = str(getattr(extra, "subscriber", "") or "؟")
        else:
            subscriber = str(extra[1] or "؟")
        started = time.perf_counter()
        try:
            if kind == "sub":
                await self._deliver(extra, event_name, payload)
            else:
                handler, _name, is_coro = extra
                await self._deliver_global(handler, subscriber, is_coro,
                                           event_name, payload)
        finally:
            elapsed = time.perf_counter() - started
            if elapsed > _LIGHT_BUDGET_S:
                self._overrun_by_subscriber[subscriber] += 1
                if elapsed > self._overrun_worst_by_subscriber.get(subscriber, 0.0):
                    self._overrun_worst_by_subscriber[subscriber] = elapsed

    def subscribe(
        self,
        event_name: str,
        handler: Callable[..., Any],
        *,
        subscriber: str = "",
        isolate_payload: bool | None = None,
    ) -> None:
        if isolate_payload is None:
            isolate_payload = self.payload_mode != "shared_readonly"
        if self._is_cold_subscriber(subscriber):
            # يُثبَّت على المسار البارد قبل أوّل تسليم — لا بعد أن يحجب.
            self._cold_handlers.add(id(handler))
        super().subscribe(
            event_name,
            handler,
            subscriber=subscriber,
            isolate_payload=bool(isolate_payload),
        )

    def subscribe_all(
        self,
        handler: Callable[..., Any],
        *,
        subscriber: str = "",
        isolate_payload: bool | None = None,
        hot_scope: str | None = None,
    ) -> None:
        """اشتراكٌ عامّ — **باردٌ افتراضًا** (§٤ من ورقة المالك ٢٠٢٦-٠٩-١٠).

        «أي مشترك يستخدم `subscribe_all` ولا يملك نطاقًا محددًا:
        DEFAULT = COLD. لا يجوز لمشترك عام أن يدخل المسار الساخن.»

        ⛔ **والقياس الذي فرض القاعدة:** ثلاثة مشترِكين عامّين ابتلعوا
        **76% من كلّ الإسقاط** على النواة الحيّة:

            الذرّة 1        806.5 إسقاطًا/ث
            الذرّة 810      803.7/ث
            api.websocket   801.5/ث
            ────────────────────────────
                            2,412 من 3,160/ث

        ومشترِكٌ عامّ يرى **كلّ** حدث (2,703/ث) ولا يلحق، فيفيض صندوقه
        ويُسقط — وهو جالسٌ على مسار السوق يزاحم التِكّة.

        والقاعدة **بنيويّة لا قائمة أسماء** (§٨): مَن لا يملك نطاقًا لا
        مكان له على مسار مملوك. ومن يحتاج المسار الساخن يعلن نطاقه في
        `hot_scope` — إعلانٌ يظهر في التشخيص ويُسأل عنه.
        """
        if isolate_payload is None:
            isolate_payload = self.payload_mode != "shared_readonly"
        if hot_scope is None:
            self._cold_handlers.add(id(handler))
        else:
            self._declared_hot_globals[str(subscriber or "؟")] = str(hot_scope)
        super().subscribe_all(
            handler,
            subscriber=subscriber,
            isolate_payload=bool(isolate_payload),
        )

    async def publish(
        self,
        event_name: str,
        payload: dict[str, Any] | None = None,
        *,
        publisher: str = "",
    ) -> None:
        if self.payload_mode == "isolated":
            # The parent implementation still routes through our _enqueue
            # override, so this mode retains worker lanes with legacy copies.
            self._published_total += 1
            return await super().publish(event_name, payload, publisher=publisher)

        # ٢٠٢٦-٠٩-١٠ — إزالة **النسخة المزدوجة** (ورقة المالك §٢٨).
        #
        # كان هنا `_fast_copy` = `pickle.dumps` + `pickle.loads`: مرورٌ عميق
        # كامل على الشجرة. ثمّ `freeze_payload` أدناه تمرّ عليها **مرّة
        # ثانية** وتبني حاويات جديدة بالكامل. أي مسحان لبناء لقطة واحدة.
        #
        # المقيس (٢٠٬٠٠٠ نشرة، حمولة سوق واقعية بثلاثين مستوى عمق):
        #     _fast_copy + freeze : 1.9120 ث   ⟵ 10.5 ألف/ث
        #     dict()     + freeze : 1.5941 ث   ⟵ 12.5 ألف/ث   (−16.6%)
        # و`_fast_copy` وحدها 15.3% من زمن النشر، و8.0% من معالج النواة كلّه
        # في ملمح ٦٠ ثانية على العملية الحيّة.
        #
        # ولماذا `dict()` السطحيّة كافية: الإضافات أدناه كلّها مفاتيح **مستوى
        # أوّل** (`setdefault`)، فنسخةٌ سطحيّة تمنع تلويث قاموس الناشر تمامًا؛
        # والعزل العميق يبقى مضمونًا لأنّ `freeze_payload` تُستدعى **فورًا
        # وتزامنيًّا** هنا فتبني الشجرة كلّها من جديد — لقطة لحظة النشر، لا
        # إشارة إلى شجرة الناشر.
        #
        # ⛔ ولا تجعلها تجميدًا كسولًا: سقف الوفر مغرٍ (152×) لكنّ الشجرة تبقى
        # مشتركة مع الناشر حتى أوّل قراءة، والطوابير المقيسة بلغت 21,616 رسالة
        # و238.9 ثانية — فنافذة التسريب دقائق. سرعةٌ تشتري قرارًا ببيانات
        # تبدّلت بعد لحظته ليست سرعة.
        raw_base: dict[str, Any] = dict(payload) if payload else {}
        raw_base.setdefault("source", publisher)
        raw_base.setdefault("event_id", str(uuid.uuid4()))
        raw_base.setdefault("trace_id", current_trace_id.get() or str(uuid.uuid4()))
        raw_base.setdefault("parent_event_id", current_event_id.get())
        raw_base.setdefault("parent_event", current_event.get())
        # ٢٠٢٦-٠٨-٣١: لم يعد للناقل ساعة — `EventBus.now()` أُلغيت لأنها كانت
        # مالكًا ثانيًا للوقت. الختم الزمنيّ من السلطة المركزيّة `clock` مباشرة.
        raw_base.setdefault("timestamp", official_now())
        readonly_base = freeze_payload(raw_base)

        self._published_total += 1
        self._published[event_name] += 1
        self._shared_published += 1
        self.latency.observe(event_name, raw_base)

        if _is_replayable(event_name):
            # تُخزَّن **المجمَّدة** لا `raw_base`: بعد النسخة السطحيّة صارت
            # حاويات `raw_base` الداخلية إشاراتٍ إلى شجرة الناشر، فتخزينها
            # يجعل مشترِكًا متأخّرًا يقرأ حالةً تبدّلت بعد النشر. المجمَّدة
            # لقطةٌ مستقلّة، والمشترك المتأخّر يأخذ نسخته منها كما كان.
            self._last_event[event_name] = readonly_base

        subs = list(self._subscribers.get(event_name, ()))
        _log.debug(
            "نشر owned '%s' من '%s' إلى %d مشترك(ين) (trace_id: %s)",
            event_name,
            publisher or "؟",
            len(subs),
            raw_base["trace_id"],
        )

        def private_copy() -> Any:
            self._private_deliveries += 1
            try:
                return _fast_copy(raw_base)
            except Exception:  # pragma: no cover - _fast_copy has its fallback
                return copy.deepcopy(raw_base)

        for handler, subscriber, isolate, is_coro in self._global_subscribers:
            if isolate:
                body = private_copy()
            else:
                body = readonly_base
                self._shared_deliveries += 1
            self._enqueue(
                id(handler),
                ("global", event_name, body, (handler, subscriber, is_coro)),
                event_name,
            )

        if not subs:
            self._no_subscribers[event_name] += 1
            await self._maybe_yield()
            return

        for sub in subs:
            if sub.isolate:
                body = private_copy()
            else:
                body = readonly_base
                self._shared_deliveries += 1
            self._enqueue(
                id(sub.handler),
                ("sub", event_name, body, sub),
                event_name,
            )
        await self._maybe_yield()

    async def drain(self, timeout_s: float | None = None) -> bool:
        return await self._runtime.drain(timeout_s=timeout_s)

    async def close(self) -> None:
        """يغلق مسارات الملكية **ثمّ بِركتَي الخيوط** التي بناها الأب.

        ⛔ **العطب الذي يعالجه:** `EventBus.close()` **متزامنة** وتُغلق
        `_realtime_executor` و`_handler_executor`. وهذا التجاوز كان
        `async def` ولا ينادي الأب أبدًا، فكلّ ناقل يُبنى يترك بِركتَي
        خيوطٍ حيّتين إلى نهاية العملية.

        وثمنه قِسته: مجموعة الاختبارات صارت **٣ فشل بدل ٢** بعد إضافة
        اختباراتٍ تبني نواقل، والساقط `test_ctrader_622_contract…` يمرّ
        وحده. خيوطٌ متراكمة تُزعزع اختبارًا حسّاسًا للزمن.

        والأب متزامن، فيُنادى بلا `await` — وفي `finally` كي لا يمنع خطأٌ
        في مسارات الملكية إغلاق ما بعده.
        """
        try:
            await self._runtime.close()
        finally:
            EventBus.close(self)

    async def aclose(self) -> None:
        await self.close()

    def transport_stats(self) -> dict[str, Any]:
        """Raw transport counters and worker/ownership health."""
        return {
            "payload_mode": self.payload_mode,
            "cold_sections": [list(pair) for pair in self._cold_sections],
            "cold_handlers": len(self._cold_handlers),
            # §٤ — المشترِكون العامّون الذين طلبوا المسار الساخن بنطاقٍ معلَن.
            # فارغةٌ دائمًا = لا استثناء صامت.
            "declared_hot_globals": dict(self._declared_hot_globals),
            "published": self._published_total,
            "shared_publishes": self._shared_published,
            "shared_deliveries": self._shared_deliveries,
            "private_deliveries": self._private_deliveries,
            "runtime": self._runtime.stats(),
            # طلب المالك: مئينات `تِكّة ← قرار` **مع عيّنتها وعتبتها**.
            "latency": self.latency.snapshot(),
            # مِرقاب تجمّد الحلقة — يظهر فقط حين يكون مركّبًا (متغيّر بيئة).
            "loop_stalls": (getattr(self, "loop_watchdog", None).report()
                            if getattr(self, "loop_watchdog", None) is not None else None),
            # §٢٤ — أبطأ خمسة مشترِكين بالاسم وأسوأ مدّة لكلٍّ.
            "overrun_by_subscriber": dict(self._overrun_by_subscriber.most_common(5)),
            "overrun_worst_by_subscriber": {
                name: round(value, 4) for name, value in
                sorted(self._overrun_worst_by_subscriber.items(),
                       key=lambda pair: pair[1], reverse=True)[:5]},
            "overrun_budget_s": _LIGHT_BUDGET_S,
            # §25 — «أهمّ سطر: COMPUTE CPU BY PROCESS». يُعرض من هنا كي
            # تصل أرقام المزرعة إلى `/api/transport-stats` **بلا لمس النواة
            # المختومة**: النقطة قائمة، وهذا الحقل يملؤها.
            "analysis_farm": (farm.stats()
                              if (farm := getattr(self, "analysis_farm", None)) is not None
                              else None),
        }
