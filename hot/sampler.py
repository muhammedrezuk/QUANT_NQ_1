# -*- coding: utf-8 -*-
"""⛔ **معطَّل — منحازٌ بنيويًّا. نجح في اختبارٍ ورسب في آخر.**

## ما اجتازه

لا يلفّ كائنًا ولا يمرّ من الأداة نداءٌ تُنفّذه الذرّة. والعدّاداتُ
المستقلّة لم تتحرّك (‏اتّصالات 30=30 · نشرات فرق 0.14٪ · أخطاء 0=0)،
وكلفتُه على الزمن ‏+3.4٪. **فهو لا يُغيّر ما يقيسه** — وذلك ما رسب فيه
سلفُه `hot/profiler.py`.

## وما رسب فيه

قال إنّ `455` تُنفق **45.3٪** من الدورة في `parameter_registry.py:get`
(‏4.38 م.ث/دورة). وعدٌّ محضٌ — زيادةُ عددٍ صحيحٍ لا مؤقّت — قال:

    registry.get   10.0 نداءً/دورة  ×  9.1 µs  =  0.091 م.ث/دورة

**فرقُ ثمانيةٍ وأربعين ضعفًا.**

## والسبب منهجيٌّ لا يُصلَح بضبط

خيطُ العيّنة لا يعمل إلّا حين **يُفلت الخيطُ الرئيس قفلَ المفسّر (GIL)**.
والمفسّرُ يُفلته عند نداءات C — وأوّلُها `sqlite3`. فالعيّنةُ تلتقط
بانتظامٍ اللحظاتِ التي يكون فيها الخيطُ داخل قاعدةٍ أو ملفّ، وتُهمل
الحسابَ البايثونيَّ الخالص الذي **يُمسك** القفل.

    ⛔ مشرّحُ عيّنةٍ بخيطٍ تحت GIL منحازٌ إلى نقاط إفلات القفل.
       ولا يُصلَح بترددٍ أعلى ولا بعيّناتٍ أكثر — الانحيازُ في الآليّة.

## ما يصلح بدلًا منه

    عدّادٌ (زيادةُ عددٍ صحيح)          ✅ صدق
    مؤقّتٌ حول المعالج لا شيءَ داخله  ✅ صدق — وهو ما يفعله `cycle_audit`
    لفُّ كائنٍ تستعمله الذرّة          ⛔ يُغيّر السلوك
    عيّنةُ خيطٍ تحت GIL                ⛔ منحازة

⚠️ وإن أُعيد يومًا فبمشرّحٍ من خارج العمليّة (‏`py-spy` وأمثاله) يقرأ
   الذاكرة بلا خيطٍ داخليٍّ ينتظر القفل. وهو ما استُعمل فعلًا في
   `shared/parameter_registry.py` (‏قياس ٢٠٢٦-٠٩-١٠) وأعطى رقمًا صمد.

---

الوصفُ الأصليّ (للسجلّ):

مشرّحٌ بالعيّنة — يقرأ ولا يلمس.

## لماذا هذا ولا ذاك

المشرّحُ السابق (`hot/profiler.py`) كان يلفّ ما تستعمله الذرّة: اتّصالَ
قاعدةٍ وملفًّا ودالّةَ نشر. فبدّل الكائناتِ نفسَها، فبدّل السلوك:

    بلا مشرّح   1.03 اتّصال/دورة · صفر بعد الدورة 60
    مع مشرّح   31.28 اتّصال/دورة · وتِكّاتٌ سليمةٌ تُحكَم باطلة

وهذا لا يُصلَح بتحسينِ اللفّ. يُصلَح بألّا يُلَفّ شيء.

**فالعيّنةُ تقرأ المكدّس من خيطٍ جانبيّ ولا تستبدل كائنًا واحدًا.** لا
تعرف الذرّةُ أنّها مُراقَبة، ولا يمرّ من الأداة أيُّ نداءٍ تُنفّذه.

    ⛔ والثمن: الرقم **إحصائيّ** لا حسابيّ. عيّنةٌ كلَّ مِلّي ثانيةٍ تقول
       «هنا كان المفسّر أكثرَ ما كان»، لا «هذه الدالّة كلّفت ٠٫١٣٣٤».
       وهذا كافٍ لسؤال «أين تذهب المِلّي ثانية»، وغيرُ كافٍ لغيره.

## ولا يُصدَّق قبل أن يُثبت نفسَه

`tools/atom_sample.py` يشترط مقارنةً **مع/بلا** على عدّاداتٍ مستقلّةٍ لا
تملكها الأداة (‏اتّصالاتٌ · نشراتٌ · أخطاء). فإن تحرّك عدّادٌ منها، يُرفَض
التقرير ولا يُطبَع رقم.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_SELF = str(_ROOT / "hot")


class StackSampler:
    """يلتقط مكدّس الخيط الرئيس على فتراتٍ ثابتة. قراءةٌ محضة."""

    def __init__(self, *, interval_s: float = 0.001,
                 owner_of: Any = None,
                 i_know_it_is_gil_biased: bool = False) -> None:
        # ⛔ بابٌ مقفول: هذا المشرّح صادقُ المنهج ومنحازُ النتيجة. لا يُقرأ
        #    منه رقمُ نسبةٍ — يُقرأ منه «أيُّ الذرّات تلمس C» إن لزم.
        if not i_know_it_is_gil_biased:
            raise RuntimeError(
                "⛔ عيّنةُ خيطٍ تحت GIL تلتقط نقاط إفلات القفل: قالت 45.3٪ "
                "لموضعٍ قال العدّادُ إنّه 0.8٪ (48×). اقرأ رأس الملفّ.")
        self.interval_s = float(interval_s)
        #: دالّةٌ تُعيد «مَن الذرّة الجارية» — تُقرأ ولا تُكتب.
        self.owner_of = owner_of
        self.samples = 0
        self.missed = 0
        #: `(ذرّة، ملفّ:دالّة) ⟶ عدد` للإطار **الأعمق** داخل المشروع.
        self.leaf: Counter[tuple[str, str]] = Counter()
        #: كلُّ إطارٍ في المكدّس — يقيس «داخل مَن كنّا» لا «مَن كان يعمل».
        self.stack: Counter[tuple[str, str]] = Counter()
        self.by_owner: Counter[str] = Counter()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._target = threading.get_ident()

    # ── الحياة ───────────────────────────────────────────────────────────

    def start(self) -> None:
        self._target = threading.get_ident()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="nq-sampler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def __enter__(self) -> "StackSampler":
        self.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.stop()

    # ── الالتقاط ─────────────────────────────────────────────────────────

    def _loop(self) -> None:
        # ⛔ بلا رفع دقّة المؤقّت يبتلع ويندوز أكثرَ العيّنات: قِيس ٥٢٢ من
        #    ٣٬٥٠٠ متوقَّعة، فصارت العيّنةُ ٦٫٧٦ م.ث بدل ١٫٠ والتوزيعُ خشن.
        #    والرفعُ محلّيٌّ للعمليّة ويُعاد ضبطه عند الانتهاء.
        try:
            import ctypes
            winmm = ctypes.WinDLL("winmm")
            winmm.timeBeginPeriod(1)
        except Exception:                                      # noqa: BLE001
            winmm = None
        next_at = time.perf_counter()
        while not self._stop.is_set():
            next_at += self.interval_s
            gap = next_at - time.perf_counter()
            if gap > 0:
                self._stop.wait(gap)
            else:
                self.missed += 1
                next_at = time.perf_counter()
            if self._stop.is_set():
                break
            try:
                frame = sys._current_frames().get(self._target)
            except Exception:                                  # noqa: BLE001
                continue
            if frame is None:
                continue
            self._record(frame)
        if winmm is not None:
            try:
                winmm.timeEndPeriod(1)
            except Exception:                                  # noqa: BLE001
                pass

    def _record(self, frame: Any) -> None:
        owner = "?"
        if self.owner_of is not None:
            try:
                owner = str(self.owner_of())
            except Exception:                                  # noqa: BLE001
                owner = "?"
        self.samples += 1
        self.by_owner[owner] += 1
        leaf_done = False
        seen: set[tuple[str, str]] = set()
        while frame is not None:
            code = frame.f_code
            name = code.co_filename
            # ⛔ إطاراتُ الأداة نفسها لا تُحسَب: وإلّا قاست نفسها.
            if not name.startswith(_SELF):
                spot = (Path(name).name, code.co_name)
                key = (owner, "%s:%s" % spot)
                if not leaf_done:
                    self.leaf[key] += 1
                    leaf_done = True
                if key not in seen:          # الإطارُ العوديّ يُعدّ مرّةً
                    seen.add(key)
                    self.stack[key] += 1
            frame = frame.f_back

    # ── التقرير ──────────────────────────────────────────────────────────

    def report(self, cycles: int, wall_s: float) -> dict[str, Any]:
        total = self.samples or 1
        ms_each = (wall_s * 1000.0) / total
        def rows(counter: Counter) -> list[dict[str, Any]]:
            return [{"owner": owner, "spot": spot, "samples": count,
                     "pct": 100.0 * count / total,
                     "ms_per_cycle": count * ms_each / max(cycles, 1)}
                    for (owner, spot), count in counter.most_common(30)]
        return {
            "samples": self.samples, "missed": self.missed,
            "interval_ms": self.interval_s * 1000.0,
            "ms_per_sample": ms_each,
            "wall_s": wall_s, "cycles": cycles,
            "by_owner": [
                {"owner": owner, "samples": count,
                 "pct": 100.0 * count / total,
                 "ms_per_cycle": count * ms_each / max(cycles, 1)}
                for owner, count in self.by_owner.most_common(25)],
            "leaf": rows(self.leaf),
            "stack": rows(self.stack),
        }
