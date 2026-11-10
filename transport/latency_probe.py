"""مسبار زمن `تِكّة ← قرار` على الناقل الحيّ — بلا لمس النواة المختومة.

**طلب المالك (ختمه ٢٠٢٦-٠٩-١٠): «لوحات يعني نظّارة بشوف فيها نظام. إذا
نظّارتك بتكذب…»** — فالمطلوب مئينات حقيقيّة، ومعها **ما يجعلها قابلة
للتصديق**: العتبة، وحجم العيّنة، ونافذتها الزمنيّة. مئينٌ بلا عيّنته
تخمينٌ بلباس رقم.

## كيف يُقاس بلا وسمِ الحمولات

كلّ نشرةٍ على الناقل تحمل `trace_id` يورَّث من الأب إلى الابن (ورقة ٠٤).
فالتِكّة تفتح أثرًا، والقرار المولود منها يحمل الأثر نفسه:

    market_data.cleaned   trace=T  ⟵ يُفتح الأثر عند t0
        …
    decision.dispatch.state trace=T  ⟵ يُغلق، والفرق هو تِكّة ← قرار

لا حقل يُضاف إلى حمولة، ولا سطر في `core/`.

## ⛔ ما لا يفعله هذا المسبار

**لا يخمّن.** أثرٌ بلا بداية معروفة **لا يُحسب** (`orphan_decisions`)،
وتِكّةٌ لم تبلغ قرارًا **لا تُحسب** — تُنسى بالعمر وتُعدّ (`expired`).
وحدود الذاكرة معلنة: خريطة الآثار مسقوفة، وتجاوزُها يُعدّ لا يُبتلع.

والعيّنة **نافذة متحرّكة**: مئينٌ على تاريخٍ من الإقلاع يصف ماضيًا ميتًا،
وهو الخطأ الذي دفعتُ ثمنه في موازنة الأحمال قبل هذا اليوم.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from typing import Any

#: ⛔ حدث التِكّة القانونيّ — **اسمٌ كامل واحد** لا بادئة (ختم المالك
#: ٢٠٢٦-٠٩-١٨). البادئة `market_data.` تفتح على اثني عشر حدثًا، منها حالاتٌ
#: دوريّة لا تِكّات (`quality.state` · `feed.state` · `calendar.state`)، فكان
#: تعريف «تِكّة ← قرار» غير مقيَّدٍ بما يكفي ليكون دليلًا معماريًّا.
DEFAULT_TICK_EVENTS = ("market_data.price_received",)

#: بادئات تُفتح بها الآثار حين لا يُعطى اسمٌ كامل. تبقى للتوافق، ولا تُستعمل
#: متى أُعطي `tick_events` — فالاسم الكامل يغلب البادئة دائمًا.
DEFAULT_TICK_PREFIXES = ()

#: أسماء تُغلقه.
DEFAULT_DECISION_PREFIXES = ("decision.dispatch.", "decision.room.")

#: العتبة التي يُحكم عليها — من ورقة القبول: `Tick → Decision ≤ 0.1000 s`.
DEFAULT_LIMIT_S = 0.1000

#: سقف الآثار المفتوحة. بلا سقف تصير الخريطة تسريبًا صامتًا في عملية
#: تعمل أيامًا. والتجاوز يُعدّ في `overflow` — يُعلَن لا يُبتلع.
DEFAULT_MAX_OPEN = 20_000

#: سقف العيّنات لكلّ رمز. النافذة متحرّكة عمدًا (`deque(maxlen=…)`).
DEFAULT_SAMPLE_CAP = 4096

#: عمر الأثر الأقصى قبل أن يُنسى. تِكّة لم تبلغ قرارًا خلاله لن تبلغه.
DEFAULT_EXPIRY_S = 30.0


def percentile(ordered: list[float], fraction: float) -> float:
    """المئين بالاستيفاء الخطّيّ على قائمة **مرتّبة سلفًا**."""
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class LatencyProbe:
    """يقيس `تِكّة ← قرار` من مرور الأحداث نفسها."""

    def __init__(
        self,
        *,
        tick_events: tuple[str, ...] = DEFAULT_TICK_EVENTS,
        tick_prefixes: tuple[str, ...] = DEFAULT_TICK_PREFIXES,
        decision_prefixes: tuple[str, ...] = DEFAULT_DECISION_PREFIXES,
        limit_s: float = DEFAULT_LIMIT_S,
        max_open: int = DEFAULT_MAX_OPEN,
        sample_cap: int = DEFAULT_SAMPLE_CAP,
        expiry_s: float = DEFAULT_EXPIRY_S,
    ) -> None:
        self.tick_events = frozenset(str(e) for e in tick_events if e)
        self.tick_prefixes = tuple(p for p in tick_prefixes if p)
        #: أسوأ العيّنات بهويّتها الكاملة — لا يُحكم على ذيلٍ بلا عيّنته.
        self.worst_cap = 12
        self._worst: list[dict] = []
        #: مسار كلّ أثرٍ مفتوح: (اسم الحدث، عمره) — يُحفظ للبطيء وحده.
        self.path_cap = 400
        self._path: dict[str, list] = {}
        self.decision_prefixes = tuple(decision_prefixes)
        self.limit_s = float(limit_s)
        self.max_open = int(max_open)
        self.sample_cap = int(sample_cap)
        self.expiry_s = float(expiry_s)

        #: trace_id ← (لحظة الفتح، الرمز)
        self._open: dict[str, tuple[float, str]] = {}
        #: الرمز ← صندوقٌ متحرّك من `(لحظة العيّنة، الزمن المنقضي)`.
        #: الزمن يُحفظ **مع** العيّنة كي تُقرأ النافذة من أقدم عيّنةٍ باقية.
        self._samples: dict[str, deque[tuple[float, float]]] = {}

        self.opened = 0
        self.closed = 0
        self.orphan_decisions = 0     # قرارٌ بلا تِكّة معروفة — لا يُحسب
        self.expired = 0              # تِكّة لم تبلغ قرارًا — تُنسى معدودة
        self.overflow = 0             # تجاوز سقف الآثار المفتوحة
        self.over_limit: Counter[str] = Counter()
        #: عيّنات مصنّفةً بالحدث الذي فتح الأثر — يُقرأ لا يُفسَّر.
        self._by_opener: dict[str, deque[float]] = {}
        self._last_sweep = 0.0
        #: ── شلّال المراحل ────────────────────────────────────────────────
        #: عمر كلّ حدثٍ منذ التِكّة التي ولّدته، باسم الحدث. المقيس
        #: ٢٠٢٦-٠٩-١٧: الطابور صفر والمعالج نزل والرقم لم يتحرّك — فالتأخير
        #: ليس ازدحامًا بل طول السلسلة. وهذا يسمّي كلّ حلقةٍ فيها بعمرها.
        #: صفر = مطفأ بلا كلفة.
        self.stage_cap = 0
        self._stages: dict[str, deque[float]] = {}
        self.staged = 0

    # ── التقاط ───────────────────────────────────────────────────────────

    def observe(self, event_name: str, payload: Any, *, at: float | None = None) -> None:
        """يُنادى مع كلّ نشرة. رخيصٌ عمدًا: بادئتان ومعجم."""
        if not isinstance(payload, dict):
            return
        name = str(event_name)
        now = time.perf_counter() if at is None else float(at)

        if name.startswith(self.decision_prefixes):
            self._close(payload, now, name)
            return
        if name in self.tick_events or (self.tick_prefixes
                                        and name.startswith(self.tick_prefixes)):
            self._open_trace(payload, now, name)
            return
        if self.stage_cap > 0:
            self._stage(name, payload, now)
        if self.path_cap:
            trace = payload.get("trace_id")
            row = self._path.get(str(trace)) if trace else None
            if row is not None and len(row) < self.path_cap:
                entry = self._open.get(str(trace))
                if entry is not None:
                    row.append((name, round(now - entry[0], 4)))

    def _stage(self, name: str, payload: dict, now: float) -> None:
        """يسجّل عمر هذا الحدث منذ تِكّته — ولا يغلق أثرًا ولا يفتحه."""
        trace = payload.get("trace_id")
        if not trace:
            return
        entry = self._open.get(str(trace))
        if entry is None:
            return
        age = now - entry[0]
        if age < 0:
            return
        bucket = self._stages.get(name)
        if bucket is None:
            if len(self._stages) >= 400:
                return
            bucket = self._stages[name] = deque(maxlen=self.stage_cap)
        bucket.append(age)
        self.staged += 1

    def _remember_worst(self, sample: dict) -> None:
        """يحتفظ بأسوأ العيّنات كاملةً — الذيل يُفحَص بعيّنته لا بمئينه."""
        self._worst.append(sample)
        self._worst.sort(key=lambda row: -row["elapsed_s"])
        del self._worst[self.worst_cap:]

    def worst_samples(self) -> list[dict]:
        return [dict(row) for row in self._worst]

    def by_opener(self) -> list[dict]:
        """لكلّ حدثٍ فاتح: كم أثرًا أغلقه ومئيناته. يفصل التِكّة عن الدوريّ."""
        rows = []
        for name, bucket in self._by_opener.items():
            if len(bucket) < 8:
                continue
            ordered = sorted(bucket)
            rows.append({
                "opener": name, "n": len(ordered),
                "p50_s": round(percentile(ordered, 0.50), 4),
                "p95_s": round(percentile(ordered, 0.95), 4),
                "p99_s": round(percentile(ordered, 0.99), 4),
            })
        rows.sort(key=lambda r: -r["n"])
        return rows

    def stage_waterfall(self, top: int = 24) -> list[dict]:
        """المراحل مرتّبةً بعمرها الوسيط — الشلّال من التِكّة إلى القرار."""
        rows = []
        for name, bucket in self._stages.items():
            if len(bucket) < 12:
                continue
            ordered = sorted(bucket)
            rows.append({
                "event": name, "n": len(ordered),
                "p50_s": round(percentile(ordered, 0.50), 4),
                "p95_s": round(percentile(ordered, 0.95), 4),
            })
        rows.sort(key=lambda r: r["p50_s"])
        if not top or len(rows) <= top:
            return rows
        # الرأس والذيل معًا: أوّل المراحل وآخرها — فالذيل هو الذي يبتلع الزمن.
        half = max(1, top // 2)
        return rows[:half] + rows[-half:]

    def _open_trace(self, payload: dict, now: float, name: str = "؟") -> None:
        trace = payload.get("trace_id")
        if not trace:
            return
        trace = str(trace)
        if trace in self._open:
            return                                  # أوّل تِكّة هي البداية
        if len(self._open) >= self.max_open:
            self._sweep(now)
            if len(self._open) >= self.max_open:
                self.overflow += 1
                return
        # ٢٠٢٦-٠٩-١٨: البادئة `market_data.` تفتح على اثني عشر حدثًا، منها
        # حالاتٌ دوريّة لا تِكّات (`quality.state` · `feed.state` ·
        # `calendar.state`). وأثرٌ يفتحه حدثٌ دوريّ ويغلقه القرار يقيس
        # **انتظارًا** لا معالجة — وهو ما يفسّر سقفًا موحّدًا عند ثانيةٍ عبر
        # الرموز كلّها بلا علاقةٍ بمعدّل كلّ رمز. فيُسمّى الفاتح ليُعرَف
        # ما يقيسه كلّ رقم، ولا يُخفى بمتوسّط.
        self._open[trace] = (now, str(payload.get("symbol") or "؟"), name)
        if self.path_cap:
            self._path[trace] = [(name, 0.0)]
        self.opened += 1
        if now - self._last_sweep > 1.0:
            self._sweep(now)

    def _close(self, payload: dict, now: float, name: str = "decision.*") -> None:
        trace = payload.get("trace_id")
        entry = self._open.pop(str(trace), None) if trace else None
        if entry is None:
            # ⛔ لا يُحسب صفرًا ولا يُقدَّر: قرارٌ لا نعرف متى بدأ لا يُقاس.
            self.orphan_decisions += 1
            return
        started, symbol = entry[0], entry[1]
        opener = entry[2] if len(entry) > 2 else "؟"
        bucket = self._by_opener.get(opener)
        if bucket is None:
            bucket = self._by_opener[opener] = deque(maxlen=self.sample_cap)
        elapsed_here = now - started
        bucket.append(elapsed_here)
        self._remember_worst({
            "trace_id": str(trace), "symbol": symbol,
            "open_event": opener, "open_t": round(started, 6),
            "decision_event": name,
            "decision_t": round(now, 6),
            "elapsed_s": round(elapsed_here, 4),
            # مسار الأثر البطيء: أين وقف الزمن بالضبط.
            "path": self._path.pop(str(trace), None) if elapsed_here >= self.limit_s else None,
        })
        self._path.pop(str(trace), None)
        elapsed = now - started
        if elapsed < 0:
            return
        bucket = self._samples.get(symbol)
        if bucket is None:
            bucket = self._samples[symbol] = deque(maxlen=self.sample_cap)
        # ⛔ العطب المقيس ٢٠٢٦-٠٩-١٠: كان يُحفظ `_window_start` مرّةً عند أوّل
        # عيّنة، ثمّ يُحدَّث بـ`now - self._span(symbol)` حين يمتلئ الصندوق —
        # و`_span` هو `now - _window_start` نفسه، فالسطر يُسند القيمة إلى
        # ذاتها. **عمليّةٌ لاغية.** فتبقى النافذة تنمو أبدًا وتساوي عمر
        # التشغيلة، بينما الصندوق `deque(maxlen=…)` لا يحمل إلّا آخر
        # `sample_cap` عيّنة.
        #
        # وثمنه أنّ الأداة تكذب في **حجم** ما تقيسه لا في قيمته: قرأتُ
        # `window_s = 3,633` فحسبتُ المئين على ساعةٍ كاملة، وهو في الحقيقة
        # على آخر ~400 ثانية. ورقمٌ صادق في قيمته كاذبٌ في مداه يُرسل
        # القارئ إلى حكمٍ خاطئ — وهذا ما وقع لي.
        #
        # الآن يُحفظ **زمن كلّ عيّنة معها**، فتُقرأ النافذة من أقدم عيّنةٍ
        # **باقية**: تتقدّم وحدها كلّما أُزيحت عيّنة، بلا حسابٍ جانبيّ.
        bucket.append((now, elapsed))
        self.closed += 1
        if elapsed > self.limit_s:
            self.over_limit[symbol] += 1

    def _sweep(self, now: float) -> None:
        """ينسى الآثار التي لن تُغلق — بلا هذا تتضخّم الخريطة أبدًا."""
        self._last_sweep = now
        cutoff = now - self.expiry_s
        stale = [trace for trace, entry in self._open.items() if entry[0] < cutoff]
        for trace in stale:
            self._path.pop(trace, None)
        for trace in stale:
            self._open.pop(trace, None)
            self.expired += 1

    # ── العرض ────────────────────────────────────────────────────────────

    def snapshot(self, *, at: float | None = None) -> dict[str, Any]:
        """المئينات **ومعها ما يجعلها قابلة للتصديق**.

        لكلّ رمز: `p50` و`p95` و`p99` و`max`، ومعها **العتبة** و**حجم
        العيّنة** و**نافذتها بالثواني** وعدد ما تجاوز العتبة. رقمٌ بلا
        عيّنته لا يُعرض — و`samples: 0` تعني «لا أعرف» صراحةً، لا صفرًا.
        """
        # ⛔ `at` يُحقن للاختبار وحده. بدونه كانت النافذة **غير قابلة للفحص**:
        # `observe` يقبل زمنًا محقونًا و`snapshot` يقرأ الساعة الحقيقيّة، فلا
        # يلتقيان. ولهذا مرّ عطب النافذة تحت سبعة عشر اختبارًا خضراء — أقربها
        # فحص `"window_s" in snap` ولم يفحص **قيمتها** قطّ.
        now = time.perf_counter() if at is None else float(at)
        symbols: dict[str, Any] = {}
        for symbol, bucket in self._samples.items():
            if not bucket:
                continue
            ordered = sorted(value for _at, value in bucket)
            # النافذة = من أقدم عيّنةٍ **باقية** إلى الآن. تتقدّم وحدها كلّما
            # أُزيحت عيّنة من الصندوق، فتصف ما في اليد لا ما مضى.
            window = max(now - bucket[0][0], 0.0)
            symbols[symbol] = {
                "samples": len(ordered),
                "window_s": round(window, 1),
                "p50_s": round(percentile(ordered, 0.50), 4),
                "p95_s": round(percentile(ordered, 0.95), 4),
                "p99_s": round(percentile(ordered, 0.99), 4),
                "max_s": round(ordered[-1], 4) if ordered else 0.0,
                "limit_s": self.limit_s,
                # ⛔ عدّادان بمرجعين مختلفين، ويجب أن يُسمَّيا:
                # `over_limit` تراكميّ منذ الإقلاع، و`samples` نافذة. فقراءتهما
                # معًا أعطتني «40,060 من 32,126 = 124.7%» — نسبةٌ مستحيلة
                # ولّدها اختلاف المرجع لا خطأٌ في العدّ.
                # و`over_limit_window` يُحسب من العيّنات الباقية نفسها، فهو
                # وحده ما يُقسَم على `samples`.
                "over_limit": int(self.over_limit.get(symbol, 0)),
                "over_limit_window": sum(1 for v in ordered if v > self.limit_s),
            }
        return {
            "limit_s": self.limit_s,
            "tick_prefixes": list(self.tick_prefixes),
            "decision_prefixes": list(self.decision_prefixes),
            "symbols": symbols,
            "opened": self.opened,
            "closed": self.closed,
            "open_now": len(self._open),
            # ⚠️ هذه الثلاثة تُقرأ مع المئين لا بعده: مئينٌ من عيّنةٍ صغيرة
            # بينما `orphan_decisions` كبير يعني أنّنا نقيس جزءًا لا الكلّ.
            "orphan_decisions": self.orphan_decisions,
            "expired": self.expired,
            "overflow": self.overflow,
            # ⚠️ تشخيصٌ يُقرأ ولا يُفسَّر: أسوأ العيّنات **بمسارها**، والفاتح،
            # والشلّال. يخرج فارغًا حين تكون الأغطية صفرًا — فلا كلفة عند الإطفاء.
            "by_opener": self.by_opener(),
            "worst": self.worst_samples()[:12],
            "waterfall": self.stage_waterfall(),
        }
