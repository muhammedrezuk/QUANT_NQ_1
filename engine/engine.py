"""NQ ENGINE — التصريف المباشر داخل دورة التِكّة، والمسار البارد خارجها.

**الفكرة كلّها في سطر:** الذرّة لا تُلمس؛ ما يتبدّل هو مَن يناديها.

    اليوم :  EventBus → enqueue → mailbox → worker lane → invoke → atom
    الآن  :  Engine  → دورة التِكّة → نداءٌ مباشر بالترتيب → atom

الحدث الذي يُنشر **أثناء** دورةٍ يُعالَج داخلها (طابورٌ في الذاكرة، بالترتيب
الذي نُشر به)، فتكتمل السلسلة تِكّة ← تحليل ← قرار ← مخاطر ← تنفيذ في رحلةٍ
واحدة بلا صناديق ولا تسليمٍ بين مهامّ. والحدث الذي يُنشر من **خارج** أيّ
دورة (مهمّة تغذية، ساعة، واجهة) بابُه المدخل (`scheduler.py`).

**ما لا يمرّ من هنا:** اللوحة والقياس والمخازن — مشترِكون باردون على الناقل
القديم (`OwnedEventBus`) بصناديقه، ولا يشاركون الدورة الساخنة. وكلّ حدثٍ
ساخن يُمرَّر إليهم إيداعًا لا انتظارًا.

**ثلاثة حرّاس على السلسلة المباشرة — كلٌّ بعدّاده:**

    مهلة الدورة   — `await` يعلّق داخل سلسلة مباشرة يجمّد المحرّك كلّه،
                    فتُلغى الدورة كلّها عند المهلة وتُسمّى الذرّة
    سقف القفزات   — دورةُ أحداث (ذرّة تنشر ما تستهلكه عبر سلسلة) تُوقَف
                    وتُعلَن؛ والمزرعة عاشت تضخيم ×١٨ من تغذيةٍ راجعة
    عزل الخطأ     — استثناء معالجٍ يُعدّ باسمه ولا يمسّ مَن بعده
"""
from __future__ import annotations

import os

import asyncio
import contextvars
import inspect
import logging
import time
import uuid
from collections import Counter, OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from clock import now as official_now
from core.event_bus import (_LIGHT_BUDGET_S, _coalesce_key, _is_command,
                            _is_replayable)
from core.logger import current_event, current_event_id, current_trace_id
from transport.latency_probe import LatencyProbe
from transport.readonly import freeze_payload

from .cutoff import VERDICT_CUT, CutoffLedger
from .graph import HotGraph, HotSubscription
from .scheduler import GLOBAL_SCOPE, CadenceItem, ScopeKey, ScopeScheduler, scope_of

_log = logging.getLogger("quant_nq.core.engine")

#: الدورة الجارية في هذه المهمّة — بها يعرف `publish` أنّه داخل دورة.
_CYCLE: contextvars.ContextVar["_Cycle | None"] = contextvars.ContextVar(
    "nq_engine_cycle", default=None)

#: مشترِكون باردون بالاسم لا بالرقم: الواجهة واللوحة والقياس وإعادة التحميل.
#: `core.hot_reload` بارد لأنّ فحصه يمسح القرص في خيط — لا مكان له في دورة.
DEFAULT_COLD_NAMES = ("core.api", "dashboard", "telemetry", "core.hot_reload")

#: أحداثٌ لا تُدمَج أبدًا وإن كان مشترِكها بإيقاع: كلّ شمعةٍ تُغلق تُحسب.
DEFAULT_NEVER_COALESCE = ("market_data.candle_closed",)

MODE_EVERY = "every"
MODE_CADENCE = "cadence"


@dataclass(slots=True)
class _Cycle:
    task: asyncio.Task | None
    mode: str
    #: حوامل `[الحدث، الحمولة، مشترِكٌ وحيد أو None، جذر حزمة إيقاع؟، العمق]`.
    #: حوامل لا صفوف: الدمج يستبدل الحمولة في مكانها بلا معرفة الموضع.
    queue: deque[list[Any]] = field(default_factory=deque)
    #: مفتاح الدمج ⟶ الحامل المعلَّق (لأحداث الحالة وحدها) — «آخر حالة تكفي»
    #: داخل الدورة كما في صناديق الناقل القديم، وإلّا تضاعف الشغل ٤٧٪ (مقيس).
    index: dict[tuple[Any, ...], list[Any]] = field(default_factory=dict)
    processed: int = 0
    started: float = 0.0
    current_subscriber: str = ""
    current_event: str = ""
    #: المعلِّق لحظة الإلغاء — `finally` في `_invoke` يمسح `current_*` وهو
    #: يفكّ الإلغاء، فكانت المهلة تُعلن «المعلِّق ؟ على ؟» دائمًا (٢٠٢٦-٠٩-٢٣).
    cancelled_subscriber: str = ""
    cancelled_event: str = ""
    current_depth: int = 0
    depth_exceeded: int = 0
    #: الحدث الذي تُسلَّم نسخُه الآن ومشترِكوه المباشرون بالترتيب — كي يُعاد
    #: إدراج ما لم يُسلَّم منه إن أُلغيت الدورة في منتصفه (٢٠٢٦-٠٩-٢٤).
    dispatch_event: str = ""
    dispatch_body: Any = None
    dispatch_direct: list[Any] = field(default_factory=list)
    dispatch_index: int = -1
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): أبطأ معالجٍ في الدورة — به تُسمّى
    # الدورة التي تجاوزت مهلتها ولم تُقطع (المهلة لا تقطع كودًا لا يتنازل).
    slowest_s: float = 0.0
    slowest_subscriber: str = ""
    slowest_event: str = ""
    sync_overrun_seen: bool = False


def _in_ranges(number: int, ranges: Iterable[tuple[int, int]]) -> bool:
    return any(low <= number <= high for low, high in ranges)


class NQEngine:
    """محرّك المسار الساخن بواجهة الناقل — يُمرَّر إلى النواة مكان `OwnedEventBus`."""

    def __init__(
        self,
        *,
        cold_bus: Any,
        cadence_sections: Any = ((150, 499),),
        cold_sections: Any = ((700, 749),),
        cold_names: Iterable[str] = DEFAULT_COLD_NAMES,
        never_coalesce_events: Iterable[str] = DEFAULT_NEVER_COALESCE,
        cold_bus_throttle_s: float = 0.0,
        cycle_deadline_s: float = 5.0,
        max_depth: int = 64,
        max_events_per_cycle: int = 50_000,
        every_backlog_alarm: int = 2000,
        cadence_min_interval_s: float = 0.0,
        light_budget_s: float = _LIGHT_BUDGET_S,
        latency_limit_s: float = 0.1,
        #: سقف عيّنات شلّال المراحل. صفر = مطفأ بلا كلفة.
        latency_stage_cap: int = 0,
        #: حدث التِكّة القانونيّ — اسمٌ كامل لا بادئة (ختم §٢٩).
        latency_tick_events: Iterable[str] = (),
        cutoff_mode: str = "shadow",
        cutoff_max_keys: int = 200_000,
        cutoff_max_hold_s: float = 0.0,
        hot_direct: bool = True,
        cutoff_probe_digits: Iterable[int] = (),
        cutoff_probe_sample: int = 1,
    ) -> None:
        self._cold = cold_bus
        self._cadence_sections = tuple((int(a), int(b)) for a, b in (cadence_sections or ()))
        self._cold_sections = tuple((int(a), int(b)) for a, b in (cold_sections or ()))
        self._cold_names = frozenset(str(n) for n in cold_names)
        self._never_coalesce = frozenset(str(n) for n in never_coalesce_events)
        #: سقف العرض على الناقل البارد الداخليّ (اللوحة والقياس العامّ). صفر =
        #: بلا سقف = السلوك السابق حرفًا.
        self.cold_bus_throttle_s = float(cold_bus_throttle_s)
        self.cycle_deadline_s = float(cycle_deadline_s)
        #: عمق السلسلة: تِكّة ⟶ تحقّق ⟶ تحليل ⟶ دمج ⟶ قرار ⟶ تنفيذ نحو ١٥؛
        #: وحدها الدورة (ذرّة تنشر ما تستهلكه) تنمو بلا سقف — فالعمق حارسها،
        #: لا عدد الأحداث: التِكّة الواحدة تولّد ألفًا وأكثر بالتفرّع الطبيعيّ.
        self.max_depth = max(1, int(max_depth))
        self.max_events_per_cycle = max(1, int(max_events_per_cycle))
        self.light_budget_s = float(light_budget_s)
        self.payload_mode = "engine"

        #: القطع المبكّر — ظِلٌّ افتراضًا: يحكم ويعدّ ولا يمنع. (`engine/cutoff.py`)
        self._cutoff = CutoffLedger(mode=cutoff_mode, max_keys=cutoff_max_keys,
                                    max_hold_s=cutoff_max_hold_s)
        self._cut_suppressed = 0
        #: مسابير قياسٍ بحتة — لا تمنع شيئًا أبدًا مهما كان الوضع. غايتها سؤال
        #: واحد: كم يصير القطع لو أنّ فرقًا في الرقم المعنويّ العاشر لا يُعدّ
        #: تغيّرًا؟ (Jane Street: حيث تتغيّر النتيجة كلّ مرّة لا يعمل القطع.)
        self._cut_probes = [CutoffLedger(mode="shadow", max_keys=cutoff_max_keys, digits=int(n))
                            for n in (cutoff_probe_digits or ())]
        self._probe_sample = max(1, int(cutoff_probe_sample))
        self._probe_seen = 0

        # ── المدخل المباشر ───────────────────────────────────────────────
        # المقيس ٢٠٢٦-٠٩-١٨: السلسلة داخل المحرّك تنتهي في 20–30 مِلّي ثانية،
        # وp99 تِكّة←قرار = 1.0189 ث. فالفارق ليس حسابًا ولا نقلًا — هو
        # **انتظار النطاق دوره في المجدول** قبل أن تبدأ الدورة أصلًا.
        #
        # و`ScopeScheduler` يعطي `every` أولويّةً على `cadence` داخل النطاق
        # الواحد، فتيّارُ تِكّاتٍ متّصل يؤخّر حزمة التحليل والقرار — تأخيرٌ
        # لا يظهر بوصفه `backlog` ثابتًا: الطابور صفرٌ عند العيّنة، والتِكّة
        # تنتظر دورها ثمّ تُنفَّذ.
        #
        # فالتِكّة تدخل الرسم **مباشرةً** حين يكون نطاقها خاليًا، ويبقى
        # المجدول لما وُجد له: الإيقاع والخلفيّة والحالة البطيئة. وحين يكون
        # النطاق مشغولًا يُودَع كما كان — فالترتيب داخل النطاق محفوظ ولا
        # تتداخل دورتان على `Account×Symbol` واحد (§٣ ملكيّة واحدة).
        self.hot_direct = bool(hot_direct)
        self._direct_cycles = 0
        self._queued_because_busy = 0

        self._graph = HotGraph()
        self._scheduler = ScopeScheduler(
            run_every=self._run_every,
            run_cadence=self._run_cadence,
            every_backlog_alarm=every_backlog_alarm,
            cadence_min_interval_s=cadence_min_interval_s,
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_event: dict[str, Any] = {}
        self._never_seq = 0
        #: مسبار `تِكّة ← قرار` — الأداة نفسها التي كان يقرؤها الناقل القديم.
        _ticks = tuple(str(e) for e in (latency_tick_events or ()) if e)
        self.latency = (LatencyProbe(limit_s=latency_limit_s, tick_events=_ticks)
                        if _ticks else LatencyProbe(limit_s=latency_limit_s))
        self.latency.stage_cap = max(0, int(latency_stage_cap))

        # عدّادات باسم الحدث — الشكل نفسه الذي تعرضه `/api/bus-stats`.
        self._published: dict[str, int] = defaultdict(int)
        self._delivered: dict[str, int] = defaultdict(int)
        self._no_subscribers: dict[str, int] = defaultdict(int)
        self._timeout: dict[str, int] = defaultdict(int)
        self._error: dict[str, int] = defaultdict(int)
        self._replayed: dict[str, int] = defaultdict(int)
        self._overrun: dict[str, int] = defaultdict(int)
        self._overrun_worst_s: dict[str, float] = {}
        # وباسم المشترِك — العدّاد باسم الحدث يتّهم الحدث، وهذا يسمّي البطيء.
        self._overrun_by_subscriber: Counter[str] = Counter()
        #: زمن كلّ (حدث، مشترِك) بالثواني — بلا عتبة. العتبة تُخفي ما دونها،
        #: و54.46 م.ث لنبضة SYS_SECOND موزّعةٌ على 65 مشتركًا كلٌّ دون العتبة.
        self._time_by_pair: Counter[tuple[str, str]] = Counter()
        self._calls_by_pair: Counter[tuple[str, str]] = Counter()
        self._overrun_worst_by_subscriber: dict[str, float] = {}
        self._error_by_subscriber: Counter[str] = Counter()
        #: آخر استثناءٍ لكلّ مشترِك — نصًّا لا عدًّا: العدّاد يقول «يفشل»
        #: وهذا يقول «لماذا»، ويُقرأ من `/api/transport-stats` بلا سجلّ.
        self._last_error_by_subscriber: dict[str, str] = {}
        self._cycles = 0
        self._cycle_timeouts = 0
        #: المهلات باسم المعلِّق — كانت تُعدّ باسم الحدث وحده.
        self._timeout_by_subscriber: Counter[str] = Counter()
        #: ما أُعيد إدراجه بعد مهلة: أحداثٌ بقيت في الطابور · وتسليماتٌ لمشترِكين
        #: بعد المعلِّق على حدثه. كانت تُرمى (٢٠٢٦-٠٩-٢٤).
        self._timeout_requeued = 0
        self._timeout_requeued_deliveries = 0
        self._depth_exceeded = 0
        self._budget_exceeded = 0
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ما يُسقطه المحرّك فعلًا، باسم الحدث —
        # قطع العمق، ومسح طابور الدورة عند الميزانيّة، ورفض صندوق العمليّة الباردة.
        # كانت `/api/bus-stats` تعلن `dropped: {}` ثابتًا وهذه الثلاثة تُسقط (صفرٌ مصنوع).
        self._dropped_by_event: Counter[str] = Counter()
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): معالجٌ حجز الحلقة فوق مهلة الدورة ولم
        # تقطعه. المهلة (`asyncio.timeout`) لا تقطع كودًا لا يتنازل — متزامنًا (`def`)
        # أو غير متزامن يحسب بلا `await` — فكانت `cycle_timeouts = 0` ودورةٌ حيّة
        # 11.33 ث (455 وحده 11.30 ث). العدّ عند عودة المعالج سالمًا بزمنٍ فوق المهلة:
        # لو تنازل بعد المهلة لأُلغي، فعودته سالمًا دليل أنّه حجز الحلقة.
        self._sync_overruns = 0
        self._sync_overrun_by_subscriber: Counter[str] = Counter()
        self._sync_overrun_by_event: Counter[str] = Counter()
        self._sync_overrun_worst_by_subscriber: dict[str, float] = {}
        self._sync_overrun_last = ""
        #: دوراتٌ تجاوزت مهلتها كلّها ولم تُقطع (مجموع معالجاتٍ كلٌّ دون المهلة).
        self._cycle_overdeadline = 0
        self._cycle_overdeadline_worst_s = 0.0
        self._cycle_overdeadline_worst_root = ""
        #: ما أُعيد إلى **رأس** طابور نطاقه بعد مهلة، وما سبقه أحدثُ منه فلم يُعَد.
        self._timeout_requeue_superseded = 0
        self._coalesced_in_cycle: Counter[str] = Counter()
        self._cycle_total_s = 0.0
        self._cycle_worst_s = 0.0
        self._cycle_worst_root = ""
        #: محاسبة الزمن — «أين يذهب المعالج؟» بالرقم لا بالتشريح:
        #: زمن المعالجات نفسها مقابل زمن الدورة كلّها (الفرق = نقلٌ وتجميد ومرآة
        #: باردة)، ولكلّ نوع دورة (كلّ تِكّة / إيقاع)، ولكلّ جذرٍ باسمه.
        self._handler_total_s = 0.0
        self._handler_calls = 0
        self._mode_total_s: Counter[str] = Counter()
        self._mode_cycles: Counter[str] = Counter()
        self._mode_worst_s: dict[str, float] = {}
        self._root_total_s: Counter[str] = Counter()
        self._root_cycles: Counter[str] = Counter()
        self._cold_mirrored = 0
        self._cold_skipped = 0
        #: ما ينتظر البثّ: `(اسم، رمز) ⟶ (الحدث، الحمولة، الناشر)` — الأحدث يحلّ
        #: محلّ سابقه. يُفرَّغ بمهمّة دوريّة، ولا يحبس دورة تِكّة أبدًا.
        self._display_pending: dict[tuple[str, str], tuple[str, Any, str]] = {}
        self._display_coalesced = 0
        self._display_flushed = 0
        self._display_flusher: Any = None
        self._cold_subscriptions = 0
        self._global_subscriptions = 0
        self._threadsafe_publishes = 0
        #: خطّاف العمليّة الباردة (المرحلة F): إيداعٌ بلا انتظار لكلّ حدثٍ يُنشر.
        #: `None` = لا عمليّة باردة، والمسار البارد كلّه داخل هذه العمليّة.
        self.cold_sink: Callable[[str, Any], bool] | None = None
        self.cold_process: Any = None
        #: موجّه محرّكات الرموز (النواة الموزّعة). None = محرّكٌ واحد يحمل كلّ
        #: شيء، وهو السلوك السابق حرفًا.
        self.symbol_router: Any = None
        self._routed_out = 0
        self._router_skipped_inbound = 0
        #: آخر حمولةٍ لكلّ حدثٍ عابر للرموز — صورةُ العالم التي يأخذها محرّكٌ
        #: يُقلع متأخّرًا. `_last_event` لا تكفي: هي للأحداث القابلة للإعادة
        #: وحدها (`.state`/`.synced`/`.snapshot`)، و`platform.terminal_state`
        #: ليس منها — لا نقطة قبل `state` — فلم يصل المحرّكات قطّ، فبقيت
        #: `_alive` فارغةً في الذرّة 519 ⟵ `system_alive=False` ⟵ 171 حجبًا
        #: بـ`SYSTEM_NOT_ALIVE` (مقيس ٢٠٢٦-٠٩-١٨).
        #:
        #: ⛔ الأوامر لا تُحفظ ولا تُعاد: إعادة أمرٍ على عمليّةٍ تُقلع تعني
        #: تنفيذًا مكرّرًا. الحدّ مشتقٌّ من النواة (`_is_command`) لا من قائمة.
        self._world: "OrderedDict[str, Any]" = OrderedDict()
        self.world_max = 4096
        #: هويّات ما عاد من محرّكات الرموز — لا يُرسَل إليها ثانيةً.
        self._router_inbound_ids: dict = OrderedDict()
        self._cold_sent = 0
        self._cold_send_dropped = 0
        self._cold_skipped_inbound = 0
        #: هويّات ما وصل **من** العمليّة الباردة — لا يُعاد إليها (كشف الصدى).
        self._cold_inbound_ids: "OrderedDict[str, None]" = OrderedDict()

    # ── التصنيف ──────────────────────────────────────────────────────────

    @staticmethod
    def _section_of(subscriber: str) -> int | None:
        name = str(subscriber or "")
        return int(name) if name.isdigit() else None

    def _is_cold_subscriber(self, subscriber: str) -> bool:
        name = str(subscriber or "")
        if name.startswith("cold:") or name in self._cold_names:
            return True
        number = self._section_of(name)
        return number is not None and _in_ranges(number, self._cold_sections)

    def _is_cadence_subscriber(self, subscriber: str) -> bool:
        number = self._section_of(subscriber)
        return number is not None and _in_ranges(number, self._cadence_sections)

    # ── الاشتراك ─────────────────────────────────────────────────────────

    def subscribe(
        self,
        event_name: str,
        handler: Callable[..., Any],
        *,
        subscriber: str = "",
        isolate_payload: bool | None = None,
    ) -> None:
        if self._is_cold_subscriber(subscriber):
            self._cold.subscribe(event_name, handler, subscriber=subscriber,
                                 isolate_payload=isolate_payload)
            self._cold_subscriptions += 1
            return
        sub = HotSubscription(
            handler=handler,
            subscriber=str(subscriber or ""),
            is_coro=inspect.iscoroutinefunction(handler),
            cadence=self._is_cadence_subscriber(subscriber),
        )
        self._graph.add(event_name, sub)
        last = self._last_event.get(event_name)
        if last is not None:
            # ٠٣ الحالة عند الاشتراك: المتأخّر لا يفوته آخر واقع — يُسلَّم له
            # وحده، لا لكلّ مشترِكي الحدث.
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): في نطاق حمولتها لا في العامّ — كانت
            # تُدار على `('', '')` فتجتمع دورتان على `Account×Symbol` واحد (§٣).
            self._replayed[event_name] += 1
            self._scheduler.admit_every(scope_of(last), event_name, last, sub)

    def subscribe_all(
        self,
        handler: Callable[..., Any],
        *,
        subscriber: str = "",
        isolate_payload: bool | None = None,
        hot_scope: str | None = None,
    ) -> None:
        # مشترِكٌ عامّ = بارد دائمًا (§٤ من ورقة المالك ٢٠٢٦-٠٩-١٠): مَن يرى
        # كلّ حدث لا مكان له داخل دورة تِكّة.
        self._global_subscriptions += 1
        self._cold.subscribe_all(handler, subscriber=subscriber,
                                 isolate_payload=isolate_payload)

    def unsubscribe(self, event_name: str, handler: Callable[..., Any]) -> None:
        self._graph.remove_handler(event_name, handler)
        self._cold.unsubscribe(event_name, handler)

    def unsubscribe_all(self, subscriber: str) -> int:
        removed = self._graph.remove_subscriber(str(subscriber))
        removed += int(self._cold.unsubscribe_all(subscriber) or 0)
        return removed

    def unsubscribe_global(self, handler: Callable[..., Any]) -> None:
        self._cold.unsubscribe_global(handler)

    # ── النشر ────────────────────────────────────────────────────────────

    async def publish(
        self,
        event_name: str,
        payload: dict[str, Any] | None = None,
        *,
        publisher: str = "",
    ) -> None:
        caller = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = caller
        elif caller is not self._loop:
            # ناشرٌ من حلقةٍ أخرى (خيط): يُسلَّم إلى حلقة المحرّك كما كان
            # يفعل الناقل القديم — لا خلط حلقتين.
            self._threadsafe_publishes += 1
            future = asyncio.run_coroutine_threadsafe(
                self._publish_core(event_name, payload, publisher), self._loop)
            await asyncio.wrap_future(future)
            return
        await self._publish_core(event_name, payload, publisher)

    async def _publish_core(self, event_name: str, payload: Any, publisher: str) -> None:
        raw: dict[str, Any] = dict(payload) if payload else {}
        raw.setdefault("source", publisher)
        raw.setdefault("event_id", str(uuid.uuid4()))
        raw.setdefault("trace_id", current_trace_id.get() or str(uuid.uuid4()))
        raw.setdefault("parent_event_id", current_event_id.get())
        raw.setdefault("parent_event", current_event.get())
        raw.setdefault("timestamp", official_now())
        # لقطةٌ واحدة للقراءة فقط — تُبنى مرّةً وتُشارَك بالإشارة (§٢٣).
        body = freeze_payload(raw)

        # ── القطع المبكّر ────────────────────────────────────────────────
        # القيمة المشتقّة التي ساوت سابقتها لا توقظ أحدًا. والحكم يُحسب دائمًا
        # حين يكون السجلّ مفتوحًا — أمّا المنع فلا يقع إلّا في وضع `enforce`.
        # فيُعرَف المكسب بالرقم قبل أن يُلمس سلوك.
        if self._cut_probes:
            self._probe_seen += 1
            if self._probe_seen % self._probe_sample == 0:
                for probe in self._cut_probes:
                    probe.evaluate(event_name, body)
        if self._cutoff.enabled:
            verdict = self._cutoff.evaluate(event_name, body)
            if verdict == VERDICT_CUT and self._cutoff.enforcing:
                self._published[event_name] += 1
                self._cut_suppressed += 1
                return

        self._published[event_name] += 1
        self.latency.observe(event_name, raw)
        if _is_replayable(event_name):
            self._last_event[event_name] = body

        # النواة الموزّعة: الحدث ذو الرمز يُودع في محرّك رمزه — إيداعٌ بلا
        # انتظار، فالجذر يحمل التغذية والتنفيذ ولا يُحبس لأحد.
        router = self.symbol_router
        if router is not None:
            rid = body.get('event_id') if isinstance(body, dict) else None
            if rid is not None and str(rid) in self._router_inbound_ids:
                self._router_skipped_inbound += 1
            elif router.dispatch(event_name, body):
                self._routed_out += 1
                if not _is_command(event_name):
                    self._world[event_name] = body
                    self._world.move_to_end(event_name)
                    if len(self._world) > self.world_max:
                        self._world.popitem(last=False)

        cycle = _CYCLE.get()
        if cycle is not None and cycle.task is asyncio.current_task():
            # داخل دورة: يُعالَج فيها بالترتيب. ولا يُقبل من مهمّةٍ فرعيّة
            # ورثت السياق — تلك تدخل من الباب كجذر.
            if cycle.current_subscriber:
                self._graph.observe_production(
                    cycle.current_subscriber, cycle.current_event, event_name)
            self._enqueue_in_cycle(cycle, event_name, body)
        else:
            if (self._graph.sealed and not self._graph.is_known(event_name)
                    and self._cold.subscriber_count(event_name) == 0):
                self._graph.unknown_events[event_name] += 1
            self._graph.observe_root(event_name)
            scope = scope_of(body)
            if self.hot_direct and self._scheduler.try_acquire(scope):
                # نطاقٌ خالٍ: الدورة تُدار هنا بلا مرورٍ بالطابور. والحجز من
                # المجدول نفسه، فلا تُفتَح دورةٌ ثانية على النطاق من جهته.
                self._direct_cycles += 1
                try:
                    await self._run_every(event_name, body, None)
                finally:
                    self._scheduler.release(scope)
            else:
                self._queued_because_busy += 1
                self._scheduler.admit_every(scope, event_name, body, None)

        await self._mirror_cold(event_name, body, publisher)

    def _enqueue_in_cycle(self, cycle: _Cycle, event_name: str, body: Any) -> None:
        depth = cycle.current_depth + 1
        if depth > self.max_depth:
            # سلسلةٌ أعمق من أيّ مسارٍ مشروع = تغذية راجعة. تُقطع هنا وتُعدّ،
            # ولا تُبتلع: تُسمّى في السجلّ مرّةً لكلّ دورة.
            self._depth_exceeded += 1
            self._dropped_by_event[event_name] += 1
            if cycle.depth_exceeded == 0:
                _log.error("⛔ عمق السلسلة تجاوز %d — %s ينشر %s على عمق %d: تغذية راجعة؟ قُطعت.",
                           self.max_depth, cycle.current_subscriber or "؟", event_name, depth)
            cycle.depth_exceeded += 1
            return
        key = _coalesce_key(event_name, body) if _is_replayable(event_name) else None
        if key is not None:
            pending = cycle.index.get(key)
            if pending is not None:
                pending[1] = body          # الأحدث يحلّ محلّ المعلَّق في مكانه
                self._coalesced_in_cycle[event_name] += 1
                return
        holder = [event_name, body, None, False, depth]
        cycle.queue.append(holder)
        if key is not None:
            cycle.index[key] = holder

    def mark_router_inbound(self, event_id: str) -> None:
        """يسجّل هويّة حدثٍ عاد من محرّك رموز كي لا يُعاد إليه."""
        self._router_inbound_ids[event_id] = None
        if len(self._router_inbound_ids) > 200_000:
            self._router_inbound_ids.popitem(last=False)

    def mark_cold_inbound(self, event_id: str) -> None:
        """يسجّل هويّة حدثٍ جاء من العمليّة الباردة كي لا يُعاد إليها."""
        self._cold_inbound_ids[event_id] = None
        if len(self._cold_inbound_ids) > 200_000:
            self._cold_inbound_ids.popitem(last=False)

    def start_display_flusher(self) -> None:
        """يُشغّل تفريغ سقف العرض — يُنادى بعد بناء المحرّك على حلقته."""
        if self.cold_bus_throttle_s <= 0:
            return

        async def _run() -> None:
            while True:
                await asyncio.sleep(self.cold_bus_throttle_s)
                if not self._display_pending:
                    continue
                batch = list(self._display_pending.values())
                self._display_pending.clear()
                for name, payload, pub in batch:
                    self._display_flushed += 1
                    try:
                        await self._cold.publish(name, payload, publisher=pub)
                    except Exception as exc:  # noqa: BLE001 — بثُّ عرضٍ لا يُسقط نواة
                        _log.error("تعذّر بثّ %s إلى المسار البارد: %s", name, exc)

        self._display_flusher = asyncio.get_running_loop().create_task(
            _run(), name="nq-engine-display-flusher")

    def stop_display_flusher(self) -> None:
        if self._display_flusher is not None:
            self._display_flusher.cancel()
            self._display_flusher = None

    async def _mirror_cold(self, event_name: str, body: Any, publisher: str) -> None:
        """إيداعٌ للمسار البارد — لا انتظار لأحد فيه."""
        sink = self.cold_sink
        if sink is not None:
            event_id = body.get("event_id") if isinstance(body, dict) else None
            if event_id is not None and str(event_id) in self._cold_inbound_ids:
                self._cold_skipped_inbound += 1
            elif sink(event_name, body):
                self._cold_sent += 1
            else:
                self._cold_send_dropped += 1
                self._dropped_by_event[event_name] += 1
        cold = self._cold
        try:
            has_global = bool(getattr(cold, "_global_subscribers", ()))
            has_subs = cold.subscriber_count(event_name) > 0
        except Exception:  # noqa: BLE001 — ناقلٌ بارد بلا هذه الواجهة يُعامَل كأنّ له مشترِكين
            has_global, has_subs = True, True
        if not has_global and not has_subs:
            self._cold_skipped += 1
            return
        self._cold_mirrored += 1
        # سقف العرض: حدثٌ لا يقصده إلّا مشترِكٌ عامّ (لوحة/قياس) يُجمَّع بالأحدث
        # لكلّ (اسم، رمز) ويُبثّ بإيقاع النافذة. وما له مشترِكٌ محدّد يمرّ فورًا.
        if self.cold_bus_throttle_s > 0 and has_global and not has_subs:
            symbol = str(body.get("symbol") or "") if isinstance(body, dict) else ""
            key = (event_name, symbol)
            if key in self._display_pending:
                self._display_coalesced += 1
            self._display_pending[key] = (event_name, body, publisher)
            return
        await cold.publish(event_name, body, publisher=publisher)

    # ── الدورات ──────────────────────────────────────────────────────────

    async def _run_every(self, event_name: str, body: Any, only: Any, depth: int = 0) -> None:
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العمق يُحمَل مع ما أُعيد إدراجه بعد مهلة —
        # كان يعود صفرًا، فتفلت حلقة التغذية الراجعة من `max_depth` بإعادةٍ واحدة.
        await self._run_cycle([[event_name, body, only, False, int(depth)]], MODE_EVERY, event_name)

    async def _run_cadence(self, scope: ScopeKey, batch: list[CadenceItem]) -> None:
        items = [[name, body, None, True, 0] for name, body, _at in batch]
        root = batch[0][0] if batch else "؟"
        await self._run_cycle(items, MODE_CADENCE, "%s@%s" % (root, scope[1] or "؟"))

    async def _run_cycle(self, items: list[list[Any]], mode: str, root_label: str) -> None:
        cycle = _Cycle(task=asyncio.current_task(), mode=mode, queue=deque(items),
                       started=time.perf_counter())
        token = _CYCLE.set(cycle)
        self._cycles += 1
        timed_out = False
        try:
            async with asyncio.timeout(self.cycle_deadline_s):
                while cycle.queue:
                    holder = cycle.queue.popleft()
                    event_name, body, only, root_cadence, depth = holder
                    if _is_replayable(event_name):
                        key = _coalesce_key(event_name, body)
                        if cycle.index.get(key) is holder:
                            cycle.index.pop(key, None)
                    cycle.current_depth = int(depth)
                    await self._dispatch(cycle, event_name, body, only, root_cadence)
                    cycle.processed += 1
                    if cycle.processed > self.max_events_per_cycle:
                        self._budget_exceeded += 1
                        _log.error(
                            "⛔ دورةٌ تجاوزت ميزانيّتها (%d حدثًا) — الجذر %s · آخر حدث %s "
                            "من %s · بقي %d. أُوقفت.",
                            self.max_events_per_cycle, root_label, event_name,
                            cycle.current_subscriber or "؟", len(cycle.queue))
                        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): المسوح يُعدّ إسقاطًا باسمه.
                        for left in cycle.queue:
                            self._dropped_by_event[left[0]] += 1
                        cycle.queue.clear()
                        break
        except TimeoutError:
            timed_out = True
            self._cycle_timeouts += 1
            culprit = cycle.current_subscriber or cycle.cancelled_subscriber
            culprit_event = cycle.current_event or cycle.cancelled_event
            self._timeout[culprit_event or root_label] += 1
            if culprit:
                self._timeout_by_subscriber[culprit] += 1
            queued, deliveries = self._requeue_cancelled(cycle)
            _log.error(
                "⛔ مهلة الدورة (%.1f ث) — الجذر %s · المعلِّق %s على %s · "
                "أُلغيت الدورة وأُعيد إدراج %d حدثًا بقي فيها و%d تسليمًا بعد المعلِّق",
                self.cycle_deadline_s, root_label, culprit or "؟",
                culprit_event or "؟", queued, deliveries)
        finally:
            elapsed = time.perf_counter() - cycle.started
            self._cycle_total_s += elapsed
            if elapsed > self._cycle_worst_s:
                self._cycle_worst_s = elapsed
                self._cycle_worst_root = root_label
            if not timed_out and elapsed > self.cycle_deadline_s:
                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): دورةٌ فوق مهلتها ولم تُقطع.
                self._cycle_overdeadline += 1
                if elapsed > self._cycle_overdeadline_worst_s:
                    self._cycle_overdeadline_worst_s = elapsed
                    self._cycle_overdeadline_worst_root = root_label
                if not cycle.sync_overrun_seen:
                    # لا معالج وحده فوق المهلة — مجموعُ معالجاتٍ لم تتنازل. يُسمّى أبطؤها.
                    _log.error(
                        "⛔ دورةٌ استغرقت %.2f ث فوق مهلتها (%.1f ث) ولم تُقطع — الجذر %s · "
                        "أبطأ معالجٍ فيها %s على %s (%.3f ث). المعالجات لم تتنازل للحلقة.",
                        elapsed, self.cycle_deadline_s, root_label,
                        cycle.slowest_subscriber or "؟", cycle.slowest_event or "؟",
                        cycle.slowest_s)
            self._mode_total_s[mode] += elapsed
            self._mode_cycles[mode] += 1
            if elapsed > self._mode_worst_s.get(mode, 0.0):
                self._mode_worst_s[mode] = elapsed
            root_name = root_label.split("@", 1)[0]
            self._root_total_s[root_name] += elapsed
            self._root_cycles[root_name] += 1
            _CYCLE.reset(token)

    def _cadence_key(self, event_name: str, body: Any) -> tuple[Any, ...]:
        if event_name in self._never_coalesce:
            self._never_seq += 1
            return (event_name, "#", self._never_seq)
        return _coalesce_key(event_name, body)

    async def _dispatch(self, cycle: _Cycle, event_name: str, body: Any,
                        only: Any, root_cadence: bool) -> None:
        subs = self._graph.consumers(event_name)
        if not subs:
            if only is None and not root_cadence and self._cold.subscriber_count(event_name) == 0 \
                    and not getattr(self._cold, "_global_subscribers", ()):
                self._no_subscribers[event_name] += 1
            return
        scope = scope_of(body)
        # الحدث يُؤجَّل إلى حزمة الإيقاع **مرّةً واحدة** مهما تعدّد مشترِكوه —
        # لا مرّةً لكلّ مشترِك، وإلّا تسلّم كلّ نسخةٍ لكلّ المشترِكين: ٣ شموع
        # × ٣٤ مشترِكًا صارت ١٠٢ تسليمة لكلّ واحد (مقيس على الشريط).
        deferred = False
        direct: list[HotSubscription] = []
        for sub in subs:
            if only is not None and sub is not only:
                continue
            if root_cadence:
                # جذر حزمة الإيقاع: مشترِكو «كلّ تِكّة» أخذوه في دورته الأصليّة.
                if not sub.cadence:
                    continue
            elif (sub.cadence and cycle.mode == MODE_EVERY and only is None
                  and scope != GLOBAL_SCOPE):
                # مشترِك إيقاع في دورة «كلّ تِكّة»: يُؤجَّل إلى حزمة نطاقه،
                # والأحدث يحلّ محلّ المعلّق.
                if not deferred:
                    self._scheduler.admit_cadence(scope, self._cadence_key(event_name, body),
                                                  event_name, body)
                    deferred = True
                continue
            direct.append(sub)
        # ٢٠٢٦-٠٩-٢٤ — يُحفظ من تبقّى على هذا الحدث: إن أُلغيت الدورة عند مشترِكٍ
        # معلِّق، أخذ مَن بعده الحدثَ في دورةٍ لاحقة بدل أن يفوتهم.
        cycle.dispatch_event = event_name
        cycle.dispatch_body = body
        cycle.dispatch_direct = direct
        for index, sub in enumerate(direct):
            cycle.dispatch_index = index
            await self._invoke(cycle, sub, event_name, body)
        cycle.dispatch_direct = []
        cycle.dispatch_index = -1

    def _requeue_cancelled(self, cycle: _Cycle) -> tuple[int, int]:
        """ما لم يُسلَّم في دورةٍ أُلغيت بالمهلة يعود إلى المجدول — لا يُرمى.

        🔴 ٢٠٢٦-٠٩-٢٤ (ختم المالك «Nq على كلهم»). كانت المهلة تلغي الدورة
        وتترك طابورها يسقط مع كائنها: مقيس بعد إقلاع 14:22 — تسع مهلات
        (465×6 · 563×3) بقي فيها 2 · 2 · 58 · 57 · 58 · 34 · 18 · 3 · 3
        أحداث، ومنها دورتا 563 على `trading.final_decision` و`platform.trade_event`.
        وما يُرمى هنا لا يعرفه أحد: لا خطأ عند المستهلك ولا عدّاد.

        فيُعاد كلُّ حدثٍ بقي في الطابور إلى نطاقه بنوعه: جذرُ حزمة الإيقاع إلى
        حزمة الإيقاع (فيندمج مع الأحدث كما يندمج دائمًا)، وغيرُه إلى «كلّ تِكّة»
        بمشترِكه الوحيد إن كان له. ويأخذ مشترِكو الحدث المعلَّق الذين بعد
        المعلِّق نسختَهم بأسمائهم. والمعلِّق نفسُه لا يُعاد إليه حدثُه: رآه وعلِق
        فيه، وإعادتُه قد تعلّقه ثانيةً.

        ولا حلقة بلا نهاية: الحدث الذي تعلق عنده الدورة يُستهلك قبل تسليمه،
        فكلّ دورةٍ تتقدّم بحدثٍ على الأقلّ.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): يُعاد إلى **رأس** طابور نطاقه بترتيبه
        وبعمقه. كان يُلحق بآخره (`admit_every`) بعد أحداثٍ أحدث وصلت خلال المهلة،
        فيُعالَج قرارٌ أقدم بعد أحدث؛ ويعود عمقه صفرًا فتفلت التغذية الراجعة من
        `max_depth`. وجذرُ الإيقاع المُعاد لا يكتب فوق معلَّقٍ أحدثَ منه بمفتاحه
        (كان `admit_cadence` يضع الأقدم مكان الأحدث) — الأحدث يكفي، ويُعدّ.
        """
        # لكلّ نطاق: (عناصر «كلّ تِكّة» بالترتيب، وجذور الإيقاع بالترتيب).
        by_scope: dict[ScopeKey, tuple[list[Any], list[Any]]] = {}
        deliveries = 0
        direct = cycle.dispatch_direct
        if direct and 0 <= cycle.dispatch_index < len(direct):
            scope = scope_of(cycle.dispatch_body)
            every = by_scope.setdefault(scope, ([], []))[0]
            for sub in direct[cycle.dispatch_index + 1:]:
                every.append((cycle.dispatch_event, cycle.dispatch_body, sub, cycle.current_depth))
                deliveries += 1
        cycle.dispatch_direct = []
        cycle.dispatch_index = -1
        queued = 0
        while cycle.queue:
            event_name, body, only, root_cadence, depth = cycle.queue.popleft()
            scope = scope_of(body)
            every, cadence = by_scope.setdefault(scope, ([], []))
            if root_cadence and only is None:
                cadence.append((self._cadence_key(event_name, body), event_name, body))
            else:
                every.append((event_name, body, only, int(depth)))
            queued += 1
        cycle.index.clear()
        for scope, (every, cadence) in by_scope.items():
            self._timeout_requeue_superseded += self._scheduler.requeue_front(
                scope, every, cadence, at=cycle.started)
        self._timeout_requeued += queued
        self._timeout_requeued_deliveries += deliveries
        return queued, deliveries

    async def _invoke(self, cycle: _Cycle, sub: HotSubscription,
                      event_name: str, body: Any) -> None:
        cycle.current_subscriber = sub.subscriber
        cycle.current_event = event_name
        t_trace = current_trace_id.set(body.get("trace_id") if isinstance(body, dict) else None)
        t_eid = current_event_id.set(body.get("event_id") if isinstance(body, dict) else None)
        t_ev = current_event.set(event_name)
        started = time.perf_counter()
        cut = False
        try:
            if sub.is_coro:
                await sub.handler(body)
            else:
                result = sub.handler(body)
                if inspect.isawaitable(result):
                    await result
        except asyncio.CancelledError:
            cut = True
            # يُحفظ الاسم قبل أن يمسحه `finally` — به تُسمّي المهلة المعلِّق.
            cycle.cancelled_subscriber = sub.subscriber or "؟"
            cycle.cancelled_event = event_name
            raise
        except BaseException as error:  # noqa: BLE001 — كود ذرّة خارجيّ: يُعزل ويُسمّى
            self._error[event_name] += 1
            self._error_by_subscriber[sub.subscriber or "؟"] += 1
            self._last_error_by_subscriber[sub.subscriber or "؟"] = (
                "%s: %s: %s" % (event_name, type(error).__name__, str(error)[:300]))
            _log.error("handler error subscriber=%s event=%s error=%s",
                       sub.subscriber, event_name, error, exc_info=error)
        else:
            self._delivered[event_name] += 1
        finally:
            elapsed = time.perf_counter() - started
            self._handler_total_s += elapsed
            self._handler_calls += 1
            pair = (event_name, sub.subscriber or "؟")
            self._time_by_pair[pair] += elapsed
            self._calls_by_pair[pair] += 1
            if elapsed > self.light_budget_s:
                self._overrun[event_name] += 1
                if elapsed > self._overrun_worst_s.get(event_name, 0.0):
                    self._overrun_worst_s[event_name] = elapsed
                name = sub.subscriber or "؟"
                self._overrun_by_subscriber[name] += 1
                if elapsed > self._overrun_worst_by_subscriber.get(name, 0.0):
                    self._overrun_worst_by_subscriber[name] = elapsed
            if elapsed > cycle.slowest_s:
                cycle.slowest_s = elapsed
                cycle.slowest_subscriber = sub.subscriber or "؟"
                cycle.slowest_event = event_name
            if not cut and elapsed > self.cycle_deadline_s:
                self._note_sync_overrun(cycle, sub, event_name, elapsed)
            current_event.reset(t_ev)
            current_event_id.reset(t_eid)
            current_trace_id.reset(t_trace)
            cycle.current_subscriber = ""
            cycle.current_event = ""

    def _note_sync_overrun(self, cycle: _Cycle, sub: HotSubscription,
                           event_name: str, elapsed: float) -> None:
        """٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): معالجٌ واحد حجز الحلقة فوق مهلة الدورة.

        لا يُنقل المعالج إلى خيط ولا يُقطع — يُعدّ ويُسمّى بالمشترِك والحدث والمدّة،
        كي لا تبقى `cycle_timeouts = 0` شاهدةً على تجمّدٍ لم يُرَ."""
        name = sub.subscriber or "؟"
        kind = "غير متزامن بلا تنازل" if sub.is_coro else "متزامن"
        self._sync_overruns += 1
        self._sync_overrun_by_subscriber[name] += 1
        self._sync_overrun_by_event[event_name] += 1
        if elapsed > self._sync_overrun_worst_by_subscriber.get(name, 0.0):
            self._sync_overrun_worst_by_subscriber[name] = elapsed
        self._sync_overrun_last = "%s على %s: %.3f ث (%s)" % (name, event_name, elapsed, kind)
        cycle.sync_overrun_seen = True
        _log.error(
            "⛔ معالجٌ حجز الحلقة %.2f ث فوق مهلة الدورة (%.1f ث) ولم تقطعه — "
            "المشترِك %s على %s (%s). المهلة لا تقطع كودًا لا يتنازل؛ "
            "تجمّدت التغذية والتنفيذ والواجهة طوالها.",
            elapsed, self.cycle_deadline_s, name, event_name, kind)

    # ── الختم ────────────────────────────────────────────────────────────

    def seal(self) -> dict[str, Any]:
        """يختم الرسم بعد الإقلاع ويعلن دوراته إن وُجدت."""
        report = self._graph.seal()
        cycles = report.get("cycles") or []
        if cycles:
            _log.warning("⚠️ رسم الأحداث فيه %d دورة — أوّلها: %s",
                         len(cycles), " ⟶ ".join(cycles[0]))
        else:
            _log.info("رسم الأحداث مختوم: %d حدثًا · %d اشتراكًا · بلا دورات",
                      report.get("events", 0), report.get("subscriptions", 0))
        return report

    @property
    def graph(self) -> HotGraph:
        return self._graph

    # ── التصريف والإغلاق ─────────────────────────────────────────────────

    async def drain(self, timeout_s: float | None = None) -> bool:
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        while True:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            hot_done = await self._scheduler.drain(timeout_s=remaining)
            cold_done = await self._cold.drain(timeout_s=remaining)
            if hot_done and cold_done and not self._scheduler.pending():
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.001)

    async def close(self) -> None:
        self.stop_display_flusher()
        try:
            await self._scheduler.close()
        finally:
            closer = getattr(self._cold, "close", None)
            if closer is not None:
                result = closer()
                if inspect.isawaitable(result):
                    await result

    async def aclose(self) -> None:
        await self.close()

    # ── العرض ────────────────────────────────────────────────────────────

    def last_states(self) -> list[tuple[str, dict[str, Any]]]:
        return list(self._last_event.items())

    def world_snapshot(self) -> list[tuple[str, Any]]:
        """صورة العالم لمحرّكٍ يُقلع: آخر حمولةٍ لكلّ حدثٍ عبر إليه، بلا أوامر.

        الترتيب ترتيبُ آخر ورود — فالأحدث يصل أخيرًا ويحلّ محلّ ما قبله عند
        المستهلك، كما لو أنّه عاش الشريط من بدايته.
        """
        return list(self._world.items())

    def event_names(self) -> list[str]:
        names = list(dict.fromkeys(self._graph.event_names() + list(self._cold.event_names())))
        return names

    def subscriber_count(self, event_name: str) -> int:
        return self._graph.subscriber_count(event_name) + int(self._cold.subscriber_count(event_name))

    def stats(self) -> dict[str, Any]:
        backlog = self._scheduler.backlog()
        return {
            "published": dict(self._published),
            "delivered": dict(self._delivered),
            "no_subscribers": dict(self._no_subscribers),
            "timeout": dict(self._timeout),
            "error": dict(self._error),
            "replayed": dict(self._replayed),
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإسقاط الحقيقيّ باسم الحدث — قطع العمق،
            # ومسح الميزانيّة، ورفض صندوق العمليّة الباردة. كان `{}` ثابتًا يُقرأ «لا فقد».
            # و«الأحدث يكفي» يبقى دمجًا يُعدّ في `coalesced` لا هنا (§١٦).
            "dropped": dict(self._dropped_by_event),
            "coalesced": dict(self._scheduler.coalesced_by_event + self._coalesced_in_cycle),
            "overrun": dict(self._overrun),
            "overrun_worst_s": {k: round(v, 4) for k, v in self._overrun_worst_s.items()},
            # معالجٌ حجز الحلقة فوق مهلة الدورة ولم تقطعه — باسم الحدث، بشكل العقد نفسه.
            "sync_overrun": dict(self._sync_overrun_by_event),
            "pressure": {
                "mailboxes": backlog["scopes"],
                "queued": backlog["every"] + backlog["cadence"],
                "busy_handlers": 1 if backlog["running_cycle"] else 0,
                "oldest_pending_age_s": max(backlog["oldest_every_age_s"],
                                            backlog["oldest_cadence_age_s"]),
                "light_budget_s": self.light_budget_s,
            },
            "cold": self._cold.stats(),
        }

    def dependency_profile(self) -> dict[str, Any]:
        """رسم الاعتماد **ومعه كلفة كلّ عقدة** — قراءةٌ محضة.

        يُقرأ مرّةً عند الطلب فقط، فلا كلفة على المسار الساخن. وبه يُحسب
        «أطول مسار اعتماد» بدل حاصل ضرب العدد في الزمن.
        """
        dump = self._graph.dependency_dump()
        dump["time_by_pair"] = [
            {"event": ev, "subscriber": sb,
             "total_s": round(t, 6),
             "calls": self._calls_by_pair[(ev, sb)],
             "mean_ms": round(t / max(self._calls_by_pair[(ev, sb)], 1) * 1000, 4)}
            for (ev, sb), t in self._time_by_pair.most_common()]
        dump["cycles"] = self._cycles
        return dump

    def transport_stats(self) -> dict[str, Any]:
        cold_stats = self._cold.transport_stats() if hasattr(self._cold, "transport_stats") else {}
        cycles = max(1, self._cycles)
        return {
            "payload_mode": self.payload_mode,
            # رسم الاعتماد الكامل — ثقيلٌ عمدًا، فلا يُحسب إلّا بمتغيّر بيئة
            # (`NQ_DEP_DUMP=1`). مطفأٌ في التشغيل العاديّ بلا كلفة.
            "dependency": (self.dependency_profile()
                           if os.environ.get("NQ_DEP_DUMP") == "1" else None),
            # مِرقاب تجمّد الحلقة — يظهر فقط حين يُركَّب بمتغيّر بيئة.
            "loop_stalls": (self.loop_watchdog.report()
                            if getattr(self, "loop_watchdog", None) is not None else None),
            "engine": {
                "cycles": self._cycles,
                "cycle_timeouts": self._cycle_timeouts,
                "cycle_timeouts_by_subscriber": dict(self._timeout_by_subscriber.most_common(8)),
                "cycle_timeout_requeued": self._timeout_requeued,
                "cycle_timeout_requeued_deliveries": self._timeout_requeued_deliveries,
                "cycle_timeout_requeue_superseded": self._timeout_requeue_superseded,
                "cycle_deadline_s": self.cycle_deadline_s,
                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ما لم تقطعه المهلة يُرى بالرقم.
                "sync_overruns": self._sync_overruns,
                "sync_overrun_by_subscriber": dict(self._sync_overrun_by_subscriber.most_common(8)),
                "sync_overrun_worst_by_subscriber": {
                    name: round(value, 4) for name, value in
                    sorted(self._sync_overrun_worst_by_subscriber.items(),
                           key=lambda pair: pair[1], reverse=True)[:8]},
                "sync_overrun_last": self._sync_overrun_last,
                "cycle_overdeadline": self._cycle_overdeadline,
                "cycle_overdeadline_worst_s": round(self._cycle_overdeadline_worst_s, 4),
                "cycle_overdeadline_worst_root": self._cycle_overdeadline_worst_root,
                "dropped_by_event": dict(self._dropped_by_event.most_common(12)),
                "depth_exceeded": self._depth_exceeded,
                "max_depth": self.max_depth,
                "budget_exceeded": self._budget_exceeded,
                "max_events_per_cycle": self.max_events_per_cycle,
                "coalesced_in_cycle": sum(self._coalesced_in_cycle.values()),
                "coalesced_in_cycle_by_event": dict(self._coalesced_in_cycle.most_common(12)),
                "cycle_mean_s": round(self._cycle_total_s / cycles, 5),
                "cycle_worst_s": round(self._cycle_worst_s, 4),
                "cycle_worst_root": self._cycle_worst_root,
                "cycle_total_s": round(self._cycle_total_s, 3),
                "handler_total_s": round(self._handler_total_s, 3),
                "handler_calls": self._handler_calls,
                "transport_share": round(1.0 - (self._handler_total_s / self._cycle_total_s), 4)
                if self._cycle_total_s > 0 else None,
                "by_mode": {
                    mode: {"cycles": self._mode_cycles[mode],
                           "total_s": round(self._mode_total_s[mode], 3),
                           "mean_s": round(self._mode_total_s[mode] / max(1, self._mode_cycles[mode]), 5),
                           "worst_s": round(self._mode_worst_s.get(mode, 0.0), 4)}
                    for mode in (MODE_EVERY, MODE_CADENCE)},
                "by_root": {
                    name: {"cycles": self._root_cycles[name], "total_s": round(total, 3),
                           "mean_s": round(total / max(1, self._root_cycles[name]), 5)}
                    for name, total in self._root_total_s.most_common(12)},
                "hot_subscriptions": self._graph.subscription_count(),
                "cadence_subscriptions": self._graph.cadence_count(),
                "cold_subscriptions": self._cold_subscriptions,
                "global_subscriptions": self._global_subscriptions,
                "cold_mirrored": self._cold_mirrored,
                "cold_skipped": self._cold_skipped,
                "display_throttle_s": self.cold_bus_throttle_s,
                "display_coalesced": self._display_coalesced,
                "display_flushed": self._display_flushed,
                "display_pending": len(self._display_pending),
                # أغلى (حدث ⟶ مشترِك) بالزمن — هنا يُسمّى الحارق بالاسم.
                "time_by_pair": [
                    {"event": ev, "subscriber": sb, "total_s": round(t, 3),
                     "calls": self._calls_by_pair[(ev, sb)],
                     "mean_ms": round(t / max(self._calls_by_pair[(ev, sb)], 1) * 1000, 3)}
                    for (ev, sb), t in self._time_by_pair.most_common(20)],
                "hot_direct": self.hot_direct,
                "direct_cycles": self._direct_cycles,
                "queued_because_busy": self._queued_because_busy,
                "cutoff": self._cutoff.stats(),
                "cutoff_probes": [p.stats() for p in self._cut_probes],
                "cutoff_suppressed": self._cut_suppressed,
                "routed_to_symbol_engines": self._routed_out,
                "router_echo_skipped": self._router_skipped_inbound,
                "cold_process_sent": self._cold_sent,
                "cold_process_send_dropped": self._cold_send_dropped,
                "cold_process_echo_skipped": self._cold_skipped_inbound,
                "threadsafe_publishes": self._threadsafe_publishes,
                "overrun_budget_s": self.light_budget_s,
                "overrun_by_subscriber": dict(self._overrun_by_subscriber.most_common(8)),
                "overrun_worst_by_subscriber": {
                    name: round(value, 4) for name, value in
                    sorted(self._overrun_worst_by_subscriber.items(),
                           key=lambda pair: pair[1], reverse=True)[:8]},
                "error_by_subscriber": dict(self._error_by_subscriber.most_common(8)),
                "last_error_by_subscriber": {
                    name: self._last_error_by_subscriber.get(name, "")
                    for name, _count in self._error_by_subscriber.most_common(8)},
                "cadence_sections": [list(pair) for pair in self._cadence_sections],
                "cold_sections": [list(pair) for pair in self._cold_sections],
                "never_coalesce_events": sorted(self._never_coalesce),
                "scheduler": self._scheduler.stats(),
                "graph": self._graph.snapshot(),
            },
            "latency": {**self.latency.snapshot(),
                        "stage_waterfall": self.latency.stage_waterfall(),
                        "by_opener": self.latency.by_opener(),
                        "worst_samples": self.latency.worst_samples()},
            "cold": cold_stats,
            # توافقٌ مع أدوات القبول التي تقرأ `runtime` و`analysis_farm`.
            "runtime": cold_stats.get("runtime", {}),
            "analysis_farm": None,
            # المرحلة F — العمليّة الباردة إن وُجدت: من فيها وكم أُودع وكم عاد.
            "symbol_router": (self.symbol_router.stats()
                              if self.symbol_router is not None else None),
            "cold_process": (self.cold_process.stats()
                             if self.cold_process is not None and hasattr(self.cold_process, "stats")
                             else None),
        }
