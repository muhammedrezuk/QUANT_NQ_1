"""مدخل المحرّك — لكلّ `Account×Symbol` بابٌ واحد، والحمل مسقوفٌ بعدد الرموز.

**لماذا:** رسمٌ مُصرَّف بلا صناديق بريد يعني أنّ التِكّات تتراكم عند المدخل
حين يفوق إيقاعها زمنَ السلسلة. والمقيس على هذه الشجرة: `feed.mt5.tick`
يتذبذب **٧٫٤×** بين أهدأ نافذة وأشدّها — أي خبرٌ واحد. فبلا سياسة ضغطٍ عكسيّ
معلَنة يعود `p99` ليصعد، لكن عند الباب لا داخل الناقل.

**السياسة (ورقة المحرّك + §١٦ من ورقة المصنع):** مرحلتان لكلّ نطاق:

    كلّ تِكّة   — البنية والساعة والتنفيذ: تُعالَج كلّها بالترتيب، لا تُدمَج
    إيقاع      — التحليل والقرار: حزمةٌ واحدة معلّقة، والأحدث يحلّ محلّ
                 المعلّق ويُعدّ `coalesced` **لا** `dropped`

فمهما ارتفع إيقاع التِكّات يبقى عدد دورات التحليل في الثانية محدودًا بزمن
السلسلة، ويرى التحليل دائمًا **الأحدث** — لا عيّنةً عشوائيّة كما كان يفعل
الإخلاء من رأس الصندوق (`ownership.py:enqueue`).

**الإنصاف:** النطاقات تتناوب دورةً دورة، فرمزٌ صاخب لا يُجوّع غيره — والنطاق
العامّ (بلا رمز: الساعة، الحساب، الأوامر) يتقدّم الصفّ دائمًا.
"""
from __future__ import annotations

import asyncio
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

ScopeKey = tuple[str, str]
GLOBAL_SCOPE: ScopeKey = ("", "")

#: عنصر «كلّ تِكّة»: (الحدث، الحمولة، مشترِكٌ وحيد أو None، لحظة الإيداع، العمق)
#: ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العمق يُحمَل — صفرٌ للجذر، وعمقُه الأصليّ
#: لما أُعيد بعد مهلة، كي لا تفلت التغذية الراجعة من `max_depth` بإعادة.
EveryItem = tuple[str, Any, Any, float, int]
#: عنصر الحزمة: (الحدث، الحمولة، لحظة أوّل إيداعٍ للمفتاح)
CadenceItem = tuple[str, Any, float]


def scope_of(payload: Any) -> ScopeKey:
    """نطاق الحمولة `(account_id, symbol)` — كما يقرؤه الناقل نفسه."""
    if not isinstance(payload, dict):
        return GLOBAL_SCOPE
    symbol = str(payload.get("symbol") or "")
    if not symbol:
        return GLOBAL_SCOPE
    return (str(payload.get("account_id") or ""), symbol)


@dataclass(slots=True)
class _ScopeState:
    every: deque[EveryItem] = field(default_factory=deque)
    #: لحظة آخر دورة إيقاعٍ لهذا النطاق — بها تُقاس الأرضيّة.
    last_cadence: float = 0.0
    #: مؤجَّلٌ بانتظار الأرضيّة، فلا يُجدوَل مرّتين.
    deferred: bool = False
    #: المفتاح ⟶ (الحدث، الحمولة، لحظة أوّل إيداع). الترتيب ترتيبُ أوّل ظهور
    #: للمفتاح، والحمولة أحدثُ ما وصل — «آخر حالة تكفي».
    cadence: dict[tuple[Any, ...], CadenceItem] = field(default_factory=dict)
    queued: bool = False


class ScopeScheduler:
    """يُدير أبواب النطاقات ويشغّل الدورات بالتناوب."""

    def __init__(
        self,
        *,
        run_every: Callable[[str, Any, Any, int], Awaitable[None]],
        run_cadence: Callable[[ScopeKey, list[CadenceItem]], Awaitable[None]],
        every_backlog_alarm: int = 2000,
        cadence_min_interval_s: float = 0.0,
    ) -> None:
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): يُنادى `(الحدث، الحمولة، المشترِك أو None،
        # العمق)` — أُضيف العمق كي يحمله ما أُعيد بعد مهلة.
        self._run_every = run_every
        self._run_cadence = run_cadence
        self.every_backlog_alarm = max(1, int(every_backlog_alarm))
        #: ── أرضيّة الإيقاع ───────────────────────────────────────────────
        #: صفر = السلوك السابق حرفًا: حزمة التحليل تُشغَّل متى جهزت، أي مع كلّ
        #: تِكّة عمليًّا. وأكبر من صفر = لا تُشغَّل حزمةٌ لنطاقٍ قبل مضيّ هذه
        #: المدّة على سابقتها؛ وفي أثنائها يبقى الدمج يعمل فيرى التحليل
        #: **الأحدث** حين يُشغَّل — وهو ما يعنيه «الأحدث يكفي» أصلًا.
        #:
        #: ٢٠٢٦-٠٩-١٧ (المقيس): ١٧٦ ذرّة تستيقظ لكلّ تِكّة × ١١٤٫١ ميكروثانية
        #: للنداء = ٢٠ مِلّي ثانية من المعالج لكلّ تِكّة. فعند ١٢٠ تِكّة/ث
        #: يُطلَب ٢٤٠٪ من نواة — والطابور هو التأخير، لا الكود.
        #:
        #: ولا يمسّ هذا مسار المال: `every` (البنية والساعة والتنفيذ) يبقى
        #: بلا أرضيّة ويتقدّم الصفّ دائمًا.
        self.cadence_min_interval_s = max(0.0, float(cadence_min_interval_s))
        self.cadence_deferred = 0
        #: ── ملكيّة النطاق ────────────────────────────────────────────────
        #: §٣: دورتان لا تجتمعان على `Account×Symbol` واحد. وحين صار للتِكّة
        #: مدخلٌ مباشر (خارج الطابور) لم يعد المجدول وحده يعرف من يعمل —
        #: فصارت الملكيّة هنا، يقرؤها الاثنان. المقيس ٢٠٢٦-٠٩-١٨: بلا هذا
        #: تتداخل دورةٌ مباشرة مع دورةٍ من الطابور على النطاق نفسه.
        self._owned: set = set()
        self.skipped_owned = 0
        self.cadence_wait_total_s = 0.0
        self._scopes: dict[ScopeKey, _ScopeState] = {}
        self._ready: deque[ScopeKey] = deque()
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running_cycle = False
        self._stopping = False
        #: عدّادات — تُقرأ لا تُفسَّر.
        self.every_admitted = 0
        self.cadence_admitted = 0
        self.coalesced = 0
        self.coalesced_by_event: Counter[str] = Counter()
        self.cycles_every = 0
        self.cycles_cadence = 0
        self.every_backlog_alarms = 0
        self.every_backlog_peak = 0
        self.cadence_batch_peak = 0
        self.last_error = ""
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ما أُعيد إلى رأس طابور نطاقه بعد مهلة،
        # وما سبقه أحدثُ منه بمفتاحه فلم يُكتب فوقه.
        self.requeued_front = 0
        self.requeue_superseded = 0

    # ── الإدخال ──────────────────────────────────────────────────────────

    def try_acquire(self, scope: ScopeKey) -> bool:
        """يحجز النطاق لدورةٍ واحدة. `False` = عليه دورةٌ تعمل الآن."""
        if scope in self._owned:
            return False
        self._owned.add(scope)
        return True

    def release(self, scope: ScopeKey) -> None:
        self._owned.discard(scope)
        state = self._scopes.get(scope)
        if state is not None and (state.every or state.cadence):
            # ما وصل أثناء انشغاله لا يبقى نائمًا: يُعاد إدراجه فورًا.
            self._mark_ready(scope, state)

    def is_owned(self, scope: ScopeKey) -> bool:
        return scope in self._owned

    def _state(self, scope: ScopeKey) -> _ScopeState:
        state = self._scopes.get(scope)
        if state is None:
            state = self._scopes[scope] = _ScopeState()
        return state

    def _mark_ready(self, scope: ScopeKey, state: _ScopeState) -> None:
        if not state.queued:
            state.queued = True
            if scope == GLOBAL_SCOPE:
                self._ready.appendleft(scope)
            else:
                self._ready.append(scope)
        self._wakeup.set()
        self._ensure_task()

    def admit_every(self, scope: ScopeKey, event_name: str, body: Any,
                    only: Any = None, depth: int = 0) -> None:
        state = self._state(scope)
        state.every.append((event_name, body, only, time.perf_counter(), int(depth)))
        self.every_admitted += 1
        self._note_every_backlog(len(state.every))
        self._mark_ready(scope, state)

    def _note_every_backlog(self, size: int) -> None:
        if size > self.every_backlog_peak:
            self.every_backlog_peak = size
        if size == self.every_backlog_alarm:
            # يُعلَن مرّةً عند بلوغ العتبة لا مع كلّ عنصرٍ فوقها — ولا يُسقَط
            # شيء: مسار «كلّ تِكّة» لا يُدمَج ولا يُخلى؛ إن تراكم فالمرحلة
            # نفسها في المكان الخطأ، وهذا ما يقوله الرقم.
            self.every_backlog_alarms += 1

    def requeue_front(self, scope: ScopeKey, every: list[tuple[str, Any, Any, int]],
                      cadence: list[tuple[tuple[Any, ...], str, Any]], *,
                      at: float | None = None) -> int:
        """يعيد ما بقي من دورةٍ أُلغيت إلى **رأس** طابور نطاقه، بترتيبه وعمقه.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كانت الإعادة `admit_every`/`admit_cadence`
        فتُلحَق بالآخر بعد أحداثٍ أحدث وصلت خلال المهلة — فيُعالَج الأقدم بعد الأحدث.
        الآن: `every` = `[(الحدث، الحمولة، مشترِكٌ أو None، العمق)…]` بالترتيب يتقدّم
        الطابور؛ و`cadence` = `[(المفتاح، الحدث، الحمولة)…]` يتقدّم الحزمة، إلّا ما
        له معلَّقٌ أحدثُ بمفتاحه: الأحدث يكفي ولا يُكتب الأقدم فوقه. يُرجع عدد ما سُبق.
        """
        if not every and not cadence:
            return 0
        state = self._state(scope)
        stamp = time.perf_counter() if at is None else float(at)
        if every:
            state.every.extendleft(reversed([
                (event_name, body, only, stamp, int(depth))
                for event_name, body, only, depth in every]))
            self.every_admitted += len(every)
            self.requeued_front += len(every)
            self._note_every_backlog(len(state.every))
        superseded = 0
        if cadence:
            front: dict[tuple[Any, ...], CadenceItem] = {}
            for key, event_name, body in cadence:
                if key in state.cadence:
                    # معلَّقٌ أحدث بالمفتاح نفسه وصل خلال المهلة: هو الباقي،
                    # والأقدم المُعاد يُعدّ دمجًا ولا يُكتب فوقه.
                    superseded += 1
                    self.coalesced += 1
                    self.coalesced_by_event[event_name] += 1
                    continue
                if key in front:
                    # داخل المُعاد نفسه: اللاحق أحدث فيحلّ محلّ السابق في مكانه.
                    self.coalesced += 1
                    self.coalesced_by_event[event_name] += 1
                front[key] = (event_name, body, stamp)
            if front:
                self.cadence_admitted += len(front)
                self.requeued_front += len(front)
                front.update(state.cadence)
                state.cadence = front
                size = len(state.cadence)
                if size > self.cadence_batch_peak:
                    self.cadence_batch_peak = size
            self.requeue_superseded += superseded
        self._mark_ready(scope, state)
        return superseded

    def admit_cadence(self, scope: ScopeKey, key: tuple[Any, ...],
                      event_name: str, body: Any) -> None:
        state = self._state(scope)
        pending = state.cadence.get(key)
        if pending is not None:
            # الأحدث يحلّ محلّ المعلّق ويرث لحظة إيداعه — كي لا يخفي الدمج
            # عمر الانتظار الحقيقيّ (درس `event_bus._enqueue`).
            state.cadence[key] = (event_name, body, pending[2])
            self.coalesced += 1
            self.coalesced_by_event[event_name] += 1
        else:
            state.cadence[key] = (event_name, body, time.perf_counter())
            self.cadence_admitted += 1
            size = len(state.cadence)
            if size > self.cadence_batch_peak:
                self.cadence_batch_peak = size
        self._mark_ready(scope, state)

    # ── التشغيل ──────────────────────────────────────────────────────────

    def _ensure_task(self) -> None:
        if self._stopping:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._loop is None:
            self._loop = loop
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._run(), name="nq-engine-scheduler")

    def _defer(self, scope: ScopeKey, state: _ScopeState, wait: float) -> None:
        """يعيد إدراج النطاق بعد `wait` — مرّةً واحدة مهما تكرّر النداء."""
        if state.deferred:
            return
        loop = self._loop or asyncio.get_running_loop()
        state.deferred = True
        self.cadence_deferred += 1
        self.cadence_wait_total_s += wait

        def _wake() -> None:
            state.deferred = False
            if state.cadence or state.every:
                self._mark_ready(scope, state)

        loop.call_later(wait, _wake)

    async def _run(self) -> None:
        try:
            while not self._stopping:
                if not self._ready:
                    self._wakeup.clear()
                    await self._wakeup.wait()
                    continue
                scope = self._ready.popleft()
                state = self._scopes.get(scope)
                if state is None:
                    continue
                state.queued = False
                if scope in self._owned:
                    # عليه دورةٌ مباشرة تعمل الآن — لا تُفتَح ثانية. و`release`
                    # هي التي تعيد إدراجه حين تنتهي.
                    self.skipped_owned += 1
                    continue
                self._owned.add(scope)
                self._running_cycle = True
                try:
                    if state.every:
                        event_name, body, only, _at, depth = state.every.popleft()
                        self.cycles_every += 1
                        await self._run_every(event_name, body, only, depth)
                    elif state.cadence:
                        floor_s = self.cadence_min_interval_s
                        now = time.perf_counter()
                        wait = floor_s - (now - state.last_cadence) if floor_s > 0 else 0.0
                        if wait > 0:
                            # لم تحن أرضيّته: يُترك الدمج يعمل ويُعاد إدراجه
                            # لاحقًا. لا يُسقَط شيء — الأحدث ينتظر مكانه.
                            self._defer(scope, state, wait)
                            self._running_cycle = False
                            continue
                        state.last_cadence = now
                        batch = list(state.cadence.values())
                        state.cadence.clear()
                        self.cycles_cadence += 1
                        await self._run_cadence(scope, batch)
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:  # noqa: BLE001 — دورةٌ معطوبة لا تُسقط المدخل
                    self.last_error = "%s: %s" % (type(exc).__name__, exc)
                finally:
                    self._owned.discard(scope)
                    self._running_cycle = False
                if state.every or state.cadence:
                    self._mark_ready(scope, state)
                # تنازلٌ بعد كلّ دورة: مهامّ التغذية والواجهة تشارك الحلقة.
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            return

    # ── الحالة ───────────────────────────────────────────────────────────

    def backlog(self) -> dict[str, Any]:
        now = time.perf_counter()
        every = 0
        cadence = 0
        oldest_every = 0.0
        oldest_cadence = 0.0
        for state in self._scopes.values():
            every += len(state.every)
            cadence += len(state.cadence)
            if state.every:
                age = now - state.every[0][3]
                if age > oldest_every:
                    oldest_every = age
            for _name, _body, at in state.cadence.values():
                age = now - at
                if age > oldest_cadence:
                    oldest_cadence = age
        return {
            "scopes": len(self._scopes),
            "ready": len(self._ready),
            "every": every,
            "cadence": cadence,
            "oldest_every_age_s": round(oldest_every, 4),
            "oldest_cadence_age_s": round(oldest_cadence, 4),
            "running_cycle": self._running_cycle,
        }

    def stats(self) -> dict[str, Any]:
        return {
            "every_admitted": self.every_admitted,
            "cadence_admitted": self.cadence_admitted,
            "coalesced": self.coalesced,
            "cadence_min_interval_s": self.cadence_min_interval_s,
            "cadence_deferred": self.cadence_deferred,
            "skipped_owned": self.skipped_owned,
            "coalesced_by_event": dict(self.coalesced_by_event.most_common(20)),
            "cycles_every": self.cycles_every,
            "cycles_cadence": self.cycles_cadence,
            "every_backlog_alarm": self.every_backlog_alarm,
            "every_backlog_alarms": self.every_backlog_alarms,
            "every_backlog_peak": self.every_backlog_peak,
            "cadence_batch_peak": self.cadence_batch_peak,
            "requeued_front": self.requeued_front,
            "requeue_superseded": self.requeue_superseded,
            "last_error": self.last_error,
            "backlog": self.backlog(),
        }

    def pending(self) -> bool:
        if self._running_cycle:
            return True
        return any(state.every or state.cadence for state in self._scopes.values())

    async def drain(self, timeout_s: float | None = None) -> bool:
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        while self.pending():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.001)
        return True

    async def close(self) -> None:
        self._stopping = True
        self._wakeup.set()
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._scopes.clear()
        self._ready.clear()
