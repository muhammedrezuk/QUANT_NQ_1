# -*- coding: utf-8 -*-
"""القطع المبكّر — ما لم تتغيّر قيمته لا يوقظ أحدًا.

المشكلة المقيسة (٢٠٢٦-٠٩-١٧): ١٠٢٬٢٠٢ تِكّة ولّدت ٢٬٧٦٨٬٧٦٤ حدثًا — ٢٧٫١ لكلّ
تِكّة — ومنها `decision.cycle.record` بمعدّل ١٫٠٢ لكلّ تِكّة: دورة قرارٍ كاملة عند
كلّ ورود سعر، تغيّر شيءٌ أم لم يتغيّر.

والعلاج ليس نقل الحدث أسرع، بل ألّا يُنشَر أصلًا. هذا ما تفعله SecDB وAthena
وQuartz وBeacon، وما تسمّيه Jane Street `early cutoff`: تُعاد حسبة العقدة، فإن
ساوى ناتجها ناتجها السابق تَوقّف الانتشار ولم يستيقظ أحد.

## عقد النقاء — مشتقٌّ لا مكتوب باليد

القطع لا يجوز إلّا على **حسابٍ نقيّ** (`input → calculation → value`)، ويُمنع منعًا
على ما له أثرٌ جانبيّ (`order · fill · reject · ack · broker state`). والتمييز
هنا **مشتقٌّ من تصنيف النواة المختومة نفسها** لا من قائمة أسماء:

    `_is_replayable(name)` = الاسم ينتهي بـ`.state`/`.synced`/`.snapshot`
                             **ولا** يحمل علامة أمر
                             (`order`/`.buy`/`.sell`/`.execute`/`.cancel`/
                              `final_decision`/`command`/`.submit`/`.send`)

وهذا بالضبط حدّ النقاء: ما كان «الأحدث يكفي» (replayable) فهو قيمةٌ مشتقّة، وما
حمل علامة أمرٍ فهو فعل. والقطع **أضعف من الدمج** الذي تمارسه النواة أصلًا: الدمج
يرمي قيمةً **تغيّرت**، والقطع لا يمنع إلّا قيمةً **لم تتغيّر**. فما جاز دمجه جاز
قطعه — والعكس ليس صحيحًا.

## استثناءٌ واحد صريح: نبضات الوقت

`SYS_SECOND` وأخواتها `replayable` لكنّ **غايتها الإطلاق لا القيمة**. حمولتها قد
تتطابق والنبضة مطلوبة. فتُعفى صراحةً.

## الوضع الافتراضيّ: ظِلّ

`mode="shadow"` يحسب الحكم ويعدّه **ولا يمنع شيئًا**. فيُعرَف المكسب بالرقم قبل
أن يُلمس سلوك. `mode="enforce"` هو الذي يقطع فعلًا، ولا يُفتح إلّا بختم المالك.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from time import monotonic
from typing import Any

from core.event_bus import _TIME_SIGNAL_EVENTS, _coalesce_key, _is_replayable

#: حقول الهويّة والوقت — تتغيّر في كلّ حدثٍ بطبيعتها، فلا تدخل البصمة.
#: لو دخلت لما تساوت بصمتان أبدًا ولما قُطع شيء.
IDENTITY_FIELDS = frozenset({
    "event_id", "trace_id", "parent_event_id", "parent_event",
    "timestamp", "source", "emitted_at", "published_at", "received_at",
    "updated_at", "generated_at", "ts", "ts_ms", "ts_ns",
    "seq", "sequence", "counter", "tick_id", "cycle_id", "revision",
})

VERDICT_CUT = "cut"          # القيمة نفسها — يُقطع
VERDICT_CHANGED = "changed"  # تغيّرت — يُكمَل
VERDICT_EXEMPT = "exempt"    # خارج عقد النقاء — لا يُمسّ


def is_pure(event_name: str) -> bool:
    """هل هذا الحدث **قيمةٌ مشتقّة** يجوز قطعها؟ — مشتقٌّ من تصنيف النواة."""
    if event_name in _TIME_SIGNAL_EVENTS:
        return False          # نبضةٌ غايتها الإطلاق لا القيمة
    return _is_replayable(event_name)


def fingerprint(payload: Any, digits: int = 0) -> int:
    """بصمةٌ مستقرّة للقيمة وحدها — بلا هويّةٍ ولا وقت.

    `digits` صفرٌ = مطابقةٌ تامّة. وأكبر من صفر = تقريب كلّ عددٍ عشريّ إلى هذا
    العدد من الأرقام **المعنويّة** قبل المقارنة: فرقٌ في الرقم العاشر ليس
    تغيّرًا في السوق، وعدُّه تغيّرًا هو ما يجعل القطع لا يعمل.
    """
    return hash(_canon(payload, 0) if digits <= 0 else _canon_q(payload, 0, int(digits)))


def _quant(value: float, digits: int) -> Any:
    if value != value or value in (_INF, -_INF):
        return _NAN if value != value else repr(value)
    if value == 0.0:
        return 0.0
    # أرقامٌ معنويّة لا منازل عشريّة: 2412.55 و0.00031 يُعامَلان بالعدل نفسه.
    from math import floor, log10
    shift = digits - 1 - int(floor(log10(abs(value))))
    return round(value, shift) if -30 < shift < 30 else value


def _canon_q(value: Any, depth: int, digits: int) -> Any:
    """مثل `_canon` تمامًا — إلّا أنّ الأعداد العشريّة تُحبَّب قبل المقارنة."""
    if isinstance(value, dict):
        if depth > 6:
            return _DEEP
        flat: list[Any] = []
        for key, item in value.items():
            if key in IDENTITY_FIELDS:
                continue
            flat.append(key)
            flat.append(_canon_q(item, depth + 1, digits))
        return tuple(flat)
    if isinstance(value, float):
        return _quant(value, digits)
    if isinstance(value, (str, int, bool, bytes)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        if depth > 6:
            return _DEEP
        return tuple(_canon_q(item, depth + 1, digits) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(repr(item) for item in value))
    return repr(value)


_INF = float("inf")


def _canon(value: Any, depth: int) -> Any:
    """شجرةٌ قابلةٌ للتجزئة من القيمة وحدها.

    **بلا فرزٍ للمفاتيح عمدًا** (٢٠٢٦-٠٩-١٧): الفرز ضاعف كلفة البصمة (10.20 م.ث
    مقابل 5.29). والناشر الواحد يبني حمولته بترتيب مفاتيحٍ ثابت في كلّ مرّة،
    فالفرز يشتري اتّساقًا لا يحتاجه أحد. ولو تبدّل الترتيب يومًا فالنتيجة
    «تغيّرت» — أي **لا يُقطع**، وهو الخطأ الآمن: نحسب زيادةً، ولا نبتلع تغيّرًا.
    """
    if isinstance(value, dict):
        if depth > 6:
            return _DEEP
        flat: list[Any] = []
        for key, item in value.items():
            if key in IDENTITY_FIELDS:
                continue
            flat.append(key)
            flat.append(_canon(item, depth + 1))
        return tuple(flat)
    if isinstance(value, float):
        # NaN لا يساوي نفسه؛ ولولا هذا لظهر كلّ NaN «تغيّرًا» أبديًّا.
        return _NAN if value != value else value
    if isinstance(value, (str, int, bool, bytes)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        if depth > 6:
            return _DEEP
        return tuple(_canon(item, depth + 1) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(repr(item) for item in value))
    return repr(value)


#: علامتان ثابتتان — تُبنيان مرّةً لا في كلّ نداء.
_DEEP = ("…",)
_NAN = ("nan",)


class CutoffLedger:
    """سجلّ آخر بصمةٍ لكلّ `(حدث، نطاق)` — والحكم عليها."""

    __slots__ = ("mode", "max_keys", "digits", "max_hold_s", "_last", "_passed_at",
                 "cut", "changed", "exempt", "held_open", "skipped",
                 "learn_after", "learn_floor", "_skip", "_seen_by_event",
                 "cut_by_event", "changed_by_event", "_first_seen")

    def __init__(self, *, mode: str = "shadow", max_keys: int = 200_000,
                 digits: int = 0, max_hold_s: float = 0.0,
                 learn_after: int = 400, learn_floor: float = 0.02) -> None:
        self.mode = str(mode or "off")
        self.max_keys = int(max_keys)
        #: أرقامٌ معنويّة للمقارنة. صفر = مطابقةٌ تامّة (السلوك الحاسم الوحيد
        #: المسموح؛ التحبيب للقياس في الظِّلّ فقط حتّى يُختَم عقده).
        self.digits = int(digits)
        #: ── سقف الحجب ────────────────────────────────────────────────────
        #: ⛔ الخطر الوحيد الحقيقيّ في القطع ليس الأداء بل **حرّاس الطزاجة**:
        #: `shared/live_analysis.py` يعلن `STATE_STALE` لكلّ نطاقٍ لم يُنشَر
        #: منذ `stale_after` (أدناها 0.5 ث بعد معامل السرعة)، ومنه تصعد
        #: الحالة إلى القسم ⟵ `aggregate_state=STALE` ⟵ 456 يرفض ⟵ صفر أمر.
        #: وهو العطل نفسه الموثّق في ذلك الملفّ بتاريخ ٢٠٢٦-٠٩-٠٧.
        #:
        #: فالقيمة الساكنة تمرّ **مرّةً** كلّما تجاوز حجبُها هذا السقف — لا
        #: تُسكت إلى الأبد. صفر = بلا سقف (الظِّلّ لا يحتاجه).
        self.max_hold_s = max(0.0, float(max_hold_s))
        self._passed_at: dict[tuple[Any, ...], float] = {}
        self.held_open = 0
        # ── التعلّم: لا تدفع ثمن فحصٍ لا يعود بشيء ────────────────────────
        # المقيس ٢٠٢٦-٠٩-١٨ بعد فتح `enforce`: النسبة 1.4–4.0٪ لا 13٪،
        # لأنّ سقف الحجب (حارس الطزاجة) يحرّر أكثر ممّا يقطع. والحكم يكلّف
        # 8.32 ميكروثانية لكلّ قيمةٍ مشتقّة — فدفعه على `analysis.trend.state`
        # (صفر قطعٍ من 19,980) خسارةٌ صافية.
        #
        # فبعد `learn_after` حكمًا على اسمٍ ما، إن كانت نسبة قطعه دون
        # `learn_floor` يُترك نهائيًّا: لا بصمة ولا معجم ولا كلفة. والقرار
        # يُعلَن في `skipped_events` — يُقاس لا يُخفى.
        self.skipped = 0
        self.learn_after = max(0, int(learn_after))
        self.learn_floor = float(learn_floor)
        self._skip: set[str] = set()
        self._seen_by_event: Counter[str] = Counter()
        self._last: "OrderedDict[tuple[Any, ...], int]" = OrderedDict()
        self.cut = 0
        self.changed = 0
        self.exempt = 0
        self._first_seen = 0
        self.cut_by_event: Counter[str] = Counter()
        self.changed_by_event: Counter[str] = Counter()

    @property
    def enabled(self) -> bool:
        return self.mode in ("shadow", "enforce")

    @property
    def enforcing(self) -> bool:
        return self.mode == "enforce"

    def evaluate(self, event_name: str, body: Any) -> str:
        """يحكم على حدثٍ واحد. لا يمنع شيئًا — القرار للمنادي."""
        if not is_pure(event_name):
            self.exempt += 1
            return VERDICT_EXEMPT
        if event_name in self._skip:
            self.skipped += 1
            return VERDICT_CHANGED
        if self.learn_after:
            seen = self._seen_by_event[event_name] = self._seen_by_event[event_name] + 1
            if seen == self.learn_after:
                ratio = self.cut_by_event[event_name] / float(seen)
                if ratio < self.learn_floor:
                    self._skip.add(event_name)
        key = _coalesce_key(event_name, body)
        mark = fingerprint(body, self.digits)
        previous = self._last.get(key, _MISSING)
        if previous is _MISSING:
            self._first_seen += 1
            self._remember(key, mark)
            self._passed_at[key] = monotonic()
            self.changed += 1
            self.changed_by_event[event_name] += 1
            return VERDICT_CHANGED
        if previous == mark:
            self._last.move_to_end(key)
            if self.max_hold_s > 0.0:
                last_pass = self._passed_at.get(key)
                if last_pass is None or (monotonic() - last_pass) >= self.max_hold_s:
                    # طال الحجب: تمرّ مرّةً كي لا يظنّها حارس الطزاجة ميتة.
                    self._passed_at[key] = monotonic()
                    self.held_open += 1
                    self.changed += 1
                    return VERDICT_CHANGED
            self.cut += 1
            self.cut_by_event[event_name] += 1
            return VERDICT_CUT
        self._remember(key, mark)
        self._passed_at[key] = monotonic()
        self.changed += 1
        self.changed_by_event[event_name] += 1
        return VERDICT_CHANGED

    def _remember(self, key: tuple[Any, ...], mark: int) -> None:
        self._last[key] = mark
        self._last.move_to_end(key)
        while len(self._last) > self.max_keys:
            dropped, _ = self._last.popitem(last=False)
            self._passed_at.pop(dropped, None)

    def stats(self) -> dict[str, Any]:
        judged = self.cut + self.changed
        return {
            "mode": self.mode,
            "digits": self.digits,
            "max_hold_s": self.max_hold_s,
            "held_open": self.held_open,
            "skipped": self.skipped,
            "skipped_events": sorted(self._skip)[:25],
            "skipped_count": len(self._skip),
            "cut": self.cut,
            "changed": self.changed,
            "exempt": self.exempt,
            "first_seen": self._first_seen,
            "judged": judged,
            # النسبة التي تحسم مقدار المكسب: كم من القيم المشتقّة لم تتغيّر.
            "cut_ratio": round(self.cut / judged, 4) if judged else None,
            "keys": len(self._last),
            "top_cut": dict(self.cut_by_event.most_common(15)),
            "top_changed": dict(self.changed_by_event.most_common(15)),
        }


class _Missing:
    __slots__ = ()


_MISSING = _Missing()
