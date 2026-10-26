# -*- coding: utf-8 -*-
"""⛔ **معطَّل — هذه الأداة تُفسد ما تقيسه. لا تُستعمَل.**

## القياس الذي أدانها

نفسُ السكربت، نفسُ العدّاد، مرّتان، والفرقُ تركيبُ هذا المشرّح وحده:

    بلا مشرّح:    1.03 اتّصال/دورة  ·  **صفر** بعد الدورة 60
    مع المشرّح:  31.28 اتّصال/دورة  ·  ثابتة، لا تنتهي

ثلاثون ضعفًا. وأسوأ: يظهر معه مسارٌ لا يظهر بدونه —

    525 نداءً:  _publish_invalid ← _config ← get ← _connect

و`_publish_invalid` تُنادى حين **تُحكَم التِكّةُ باطلة**. فالمشرّح لا
يُبطئ الذرّات فحسب — **يُغيّر ما تقرّره**.

## وكلُّ ما أنتجته مسحوب

نسبُ «قاعدة/حساب»، وتقسيمُ `فتح/براغما/استعلام`، وترتيبُ الذرّات
بالزمن، و«العشرون الأوائل = ٨٧٪». **كلُّها.**

## الدرس

    ⛔ أداةُ قياسٍ لا تُصدَّق قبل أن تُقارَن **مع/بلا** على عدّادٍ مستقلّ.

وكتبتُ في حينها تحفّظًا: «المشرّح يُضخّم، النِّسَبُ صالحةٌ والإجماليُّ لا».
وكان نصفَ الحقيقة — النِّسَبُ لم تكن صالحةً أيضًا. **تحفّظٌ يُطمئن على
الجزء الخطأ أسوأُ من غيابه.**

## إن أُعيدت يومًا

تُصلَح العلّة أوّلًا (‏الأرجح أنّ `_TimedConnection`/`_TimedCursor` يكسر
عقدًا في `sqlite3`)، ثمّ **يُثبَت بمقارنة مع/بلا** أنّ العدّادات المستقلّة
لا تتحرّك، **ثمّ** يُقرأ منها رقم. وبهذا الترتيب لا غيره.

---

الوصفُ الأصليّ (للسجلّ):

§5 — تشريحُ داخل الذرّة (ختم `NQ — OPEN ATOM INTERNAL PROFILE`).

## السؤال

    11 م.ث لكلّ دورة، موزَّعةٌ على ١٦٣ ذرّةً بلا مهيمن.
    **من أين تذهب المِلّي ثانية داخل الذرّة الواحدة؟**

## لماذا لا يُقاس بزمن المعالج

`time.process_time` و`time.thread_time` على ويندوز يُشتقّان من
`GetProcessTimes`/`GetThreadTimes`، وحبيبتُهما ‏١٥٫٦ م.ث. ومعالجُ ذرّةٍ
يكلّف أجزاءَ مِلّي ثانية — فالفرقُ بين المعالج والجدار **لا يُقاس** بها.

فالتشريح يقع على **المنافذ نفسها**: كلُّ مخرجٍ يخرج من الذرّة يمرّ بدالّةٍ
نعرفها ونلفّها بمؤقّت. وما بقي بعد طرحها هو الحسابُ الخالص.

    inclusive  زمنُ المعالج كاملًا من أوّله إلى آخره
    − نشر − قاعدة − ملفّ − خيط − نوم
    = exclusive  حسابٌ خالصٌ داخل بايثون

⛔ ولا يُقدَّر «الانتظار» بطرحٍ أعمى: كلُّ بندٍ مطروحٍ **مقيسٌ بعينه**،
   وما لا يُقاس لا يُطرَح.
"""
from __future__ import annotations

import time
from collections import Counter
from typing import Any

#: أبوابُ الخروج من الذرّة — كلٌّ منها يُقاس على حدة.
#:
#: ⛔ والقاعدةُ تُفصَل إلى ثلاثة، لأنّ الفصل هو ما يختار العلاج:
#:
#:      connect يغلب  ⟶ تعميرُ الاتّصال هو العلاج
#:      pragma يغلب   ⟶ حذفُ البراغما الزائدة يكفي (‏WAL مخزَّنٌ في الملفّ)
#:      query يغلب    ⟶ بصمةُ الحداثة هي العلاج (‏نمطُ `approved_value`)
#:
#: وجمعُها في «قاعدة» واحدةٍ يُخفي أيَّ الثلاثة هو الثقيل.
GATES = ("publish", "connect", "pragma", "query", "fs", "thread", "sleep")


class Profiler:
    """يعدّ ويوقّت بالبوّابة وبالذرّة. يُشغَّل في تشخيصٍ ولا يدخل قياسَ سعة."""

    __slots__ = ("current", "ns", "hits", "inclusive", "samples", "enabled")

    def __init__(self, *, i_measured_it_does_not_perturb: bool = False) -> None:
        # ⛔ بابٌ مقفول: لا يُركَّب هذا المشرّح إلّا لمن أثبت بالقياس أنّه
        #    لا يُحرّك عدّادًا مستقلًّا. والاسمُ طويلٌ عمدًا — كي لا يُمرَّر سهوًا.
        if not i_measured_it_does_not_perturb:
            raise RuntimeError(
                "⛔ هذا المشرّح يُفسد ما يقيسه: 1.03 ⟵ 31.28 اتّصال/دورة، "
                "ويقلب تِكّاتٍ سليمةً إلى باطلة. اقرأ رأس الملفّ.")
        self.current = "?"
        self.enabled = False
        #: `(ذرّة، بوّابة) ⟶ نانو ثانية`
        self.ns: Counter[tuple[str, str]] = Counter()
        self.hits: Counter[tuple[str, str]] = Counter()
        self.inclusive: Counter[str] = Counter()
        #: عيّناتُ كلّ نداءٍ لكلّ ذرّة — أساسُ المئينات.
        self.samples: dict[str, list[float]] = {}

    def charge(self, gate: str, spent_ns: int) -> None:
        if not self.enabled:
            return
        self.ns[(self.current, gate)] += spent_ns
        self.hits[(self.current, gate)] += 1

    def call(self, atom_id: str, spent_ns: int) -> None:
        self.inclusive[atom_id] += spent_ns
        self.samples.setdefault(atom_id, []).append(spent_ns / 1e6)

    # ── ملفّاتٌ ملفوفة ────────────────────────────────────────────────────

    def wrap_file(self, handle: Any) -> Any:
        return _TimedFile(handle, self)

    def wrap_connection(self, connection: Any) -> Any:
        return _TimedConnection(connection, self)

    def report(self, cycles: int) -> dict[str, Any]:
        atoms = sorted(self.inclusive, key=lambda a: -self.inclusive[a])
        rows = []
        for atom_id in atoms:
            values = sorted(self.samples.get(atom_id, ()))

            def pick(fraction: float) -> float:
                if not values:
                    return 0.0
                index = min(len(values) - 1,
                            max(0, int(round(fraction * (len(values) - 1)))))
                return values[index]

            gates = {g: self.ns[(atom_id, g)] / 1e6 for g in GATES}
            inclusive = self.inclusive[atom_id] / 1e6
            rows.append({
                "atom": atom_id,
                "calls": len(values),
                "calls_per_cycle": len(values) / max(cycles, 1),
                "inclusive_ms": inclusive,
                "inclusive_per_cycle": inclusive / max(cycles, 1),
                "exclusive_ms": inclusive - sum(gates.values()),
                "gates_ms": gates,
                "gate_hits": {g: self.hits[(atom_id, g)] for g in GATES},
                "p50": pick(0.50), "p95": pick(0.95), "p99": pick(0.99),
                "max": values[-1] if values else 0.0,
            })
        return {"per_atom": rows}


class _TimedFile:
    """ملفٌّ يوقّت قراءتَه وكتابتَه — ولا يغيّر سلوكَه."""

    def __init__(self, handle: Any, profiler: Profiler) -> None:
        object.__setattr__(self, "_handle", handle)
        object.__setattr__(self, "_profiler", profiler)

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._handle, name)
        if name in ("read", "readline", "readlines", "write", "writelines",
                    "flush", "close", "seek"):
            def timed(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter_ns()
                try:
                    return value(*args, **kwargs)
                finally:
                    self._profiler.charge("fs", time.perf_counter_ns() - start)
            return timed
        return value

    def __enter__(self) -> Any:
        self._handle.__enter__()
        return self

    def __exit__(self, *exc: Any) -> Any:
        return self._handle.__exit__(*exc)

    def __iter__(self) -> Any:
        return iter(self._handle)


def _gate_of(args: Any) -> str:
    """براغما أم استعلام؟ — يُقرأ من نصّ الـSQL نفسه لا من اسم الدالّة."""
    if args and isinstance(args[0], str):
        return "pragma" if args[0].lstrip()[:6].upper() == "PRAGMA" else "query"
    return "query"


class _TimedCursor:
    def __init__(self, cursor: Any, profiler: Profiler) -> None:
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_profiler", profiler)

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._cursor, name)
        if name.startswith(("execute", "fetch")):
            def timed(*args: Any, **kwargs: Any) -> Any:
                gate = _gate_of(args)
                start = time.perf_counter_ns()
                try:
                    result = value(*args, **kwargs)
                finally:
                    self._profiler.charge(gate,
                                          time.perf_counter_ns() - start)
                return self if result is self._cursor else result
            return timed
        return value

    def __iter__(self) -> Any:
        return iter(self._cursor)


class _TimedConnection:
    """اتّصالٌ يوقّت استعلامَه والتزامَه — ولا يمسّ نتيجتَه."""

    def __init__(self, connection: Any, profiler: Profiler) -> None:
        object.__setattr__(self, "_conn", connection)
        object.__setattr__(self, "_profiler", profiler)

    def cursor(self, *args: Any, **kwargs: Any) -> Any:
        return _TimedCursor(self._conn.cursor(*args, **kwargs), self._profiler)

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._conn, name)
        if name.startswith("execute") or name in ("commit", "rollback"):
            def timed(*args: Any, **kwargs: Any) -> Any:
                gate = "query" if name in ("commit", "rollback") else _gate_of(args)
                start = time.perf_counter_ns()
                try:
                    result = value(*args, **kwargs)
                finally:
                    self._profiler.charge(gate,
                                          time.perf_counter_ns() - start)
                if hasattr(result, "fetchone"):
                    return _TimedCursor(result, self._profiler)
                return result
            return timed
        return value

    def __enter__(self) -> Any:
        self._conn.__enter__()
        return self

    def __exit__(self, *exc: Any) -> Any:
        return self._conn.__exit__(*exc)
