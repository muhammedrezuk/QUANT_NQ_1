# -*- coding: utf-8 -*-
"""مِرقاب الحلقة — خيطٌ خارجها يعاين مكدّس الخيط الرئيسيّ على فتراتٍ ثابتة.

لماذا خيطٌ خارجيّ: المقيس ٢٠٢٦-٠٩-١٨ أنّ سلسلة التِكّة ٦٧ خطوة، أربعٌ وستّون
منها 0.0001–0.0007 ث واثنتان 0.19 و 0.12 — أي أنّ الزمن ليس في وحدةٍ بطيئة
بل في **دفعةٍ لا تُقطَع**. وعدّاد المشترِك يقول «كم استغرق المعالج» ولا يقول
**أين** استغرقه، فالمعاينة وحدها تسمّي السطر.

والمعاينة رخيصة عمدًا: لا `extract_stack` ولا قراءة مصدر — مشيٌ على
`f_back` وقراءة `co_filename` و`f_lineno` و`co_name` فقط.

وضعان:
  * `stall`  — يعاين حين يتأخّر نبض الحلقة عن عتبة (يصف الذيل وحده).
  * `always` — يعاين دائمًا (مِرسمة إحصائيّة تصف الزمن كلّه).

⚠️ `os.sep` بدل الشرطة المكتوبة: كُتب هذا الملفّ مرّتين بشرطةٍ حرفيّة،
وفي كلتيهما وصلت محرفًا حقيقيًّا لا شرطة، فانكسر السطر صامتًا.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import Counter

_ROOT = os.path.join("C:", os.sep, "Users", "NQ", "QUANT_NQ")

#: ملفّاتٌ ليست شغلنا — تُتخطّى عند البحث عن «سطرنا» في المكدّس.
_SKIP = (os.sep + "vendor" + os.sep, os.sep + "lib" + os.sep,
         "asyncio" + os.sep, "<frozen", "loop_watchdog.py")


def _short(path: str) -> str:
    if path.startswith(_ROOT):
        return path[len(_ROOT) + 1:]
    return os.path.basename(path)


class LoopWatchdog:
    def __init__(self, *, stall_s: float = 0.060, tick_s: float = 0.005,
                 mode: str = "stall", path: str = "") -> None:
        self.stall_s = float(stall_s)
        self.tick_s = float(tick_s)
        self.mode = str(mode)
        self.path = path
        self.beat = time.perf_counter()
        self.worst = 0.0
        self.stalls = 0
        self.samples = 0
        self.sample_cost_s = 0.0
        #: الورقة — السطر الذي كان ينفَّذ فعلًا. «كلفةٌ ذاتيّة».
        self.leaf: Counter[str] = Counter()
        #: كلّ دالّةٍ في المكدّس مرّةً واحدة. «كلفةٌ تراكميّة».
        self.cumulative: Counter[str] = Counter()
        #: الدالّة المكتبيّة المنفَّذة فعلًا عند المعاينة.
        self.native: Counter[str] = Counter()
        self._main = threading.main_thread().ident
        self._stop = threading.Event()

    # يُنادى من مهمّةٍ داخل الحلقة
    def heartbeat(self) -> None:
        self.beat = time.perf_counter()

    def _sample(self) -> None:
        frame = sys._current_frames().get(self._main)
        if frame is None:
            return
        t0 = time.perf_counter()
        # الإطار الأعلى فعلًا — قد يكون مكتبةً (`pathlib.stat`)، وهو ما
        # يُنفَّذ حقًّا. يُعدّ على حدة كي لا يُنسب إلى كودنا ولا يُخفى.
        top = frame.f_code
        if not top.co_filename.startswith(_ROOT):
            self.native["%s %s" % (os.path.basename(top.co_filename), top.co_name)] += 1
        leaf = ""
        seen: set[str] = set()
        depth = 0
        while frame is not None and depth < 120:
            code = frame.f_code
            name = code.co_filename
            # ⛔ الورقة = أوّل إطارٍ **من كودنا**. نسبُها إلى المكتبة يخفي
            #    السطر الذي نادى، وهو وحده ما نملك تغييره.
            if name.startswith(_ROOT) and "loop_watchdog.py" not in name:
                if not leaf:
                    leaf = "%s:%d %s" % (_short(name), frame.f_lineno, code.co_name)
                seen.add("%s %s" % (_short(name), code.co_name))
            frame = frame.f_back
            depth += 1
        if leaf:
            self.leaf[leaf] += 1
        for fn in seen:
            self.cumulative[fn] += 1
        self.samples += 1
        self.sample_cost_s += time.perf_counter() - t0

    def _run(self) -> None:
        always = self.mode == "always"
        was_stalled = False
        while not self._stop.is_set():
            time.sleep(self.tick_s)
            lag = time.perf_counter() - self.beat
            if lag > self.worst:
                self.worst = lag
            stalled = lag >= self.stall_s
            if stalled and not was_stalled:
                self.stalls += 1
            was_stalled = stalled
            if always or stalled:
                self._sample()

    def start(self) -> None:
        threading.Thread(target=self._run, name="loop-watchdog", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def report(self, top: int = 24) -> dict:
        n = max(1, self.samples)
        return {
            "mode": self.mode,
            "stall_s": self.stall_s,
            "stalls": self.stalls,
            "worst_lag_s": round(self.worst, 4),
            "samples": self.samples,
            "sample_cost_us": round(1e6 * self.sample_cost_s / n, 1),
            "leaf": [{"at": k, "hits": v, "pct": round(100.0 * v / n, 2)}
                     for k, v in self.leaf.most_common(top)],
            "cumulative": [{"fn": k, "hits": v, "pct": round(100.0 * v / n, 2)}
                           for k, v in self.cumulative.most_common(top)],
            "native": [{"fn": k, "hits": v, "pct": round(100.0 * v / n, 2)}
                       for k, v in self.native.most_common(top)],
        }

    def dump(self) -> None:
        if not self.path:
            return
        rep = self.report(top=60)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("وضع=%s · عيّنات=%d · تجمّدات=%d · أسوأ تأخّر=%.4f ث\n\n"
                     % (rep["mode"], rep["samples"], rep["stalls"], rep["worst_lag_s"]))
            fh.write("== الورقة (كلفةٌ ذاتيّة) ==\n")
            for row in rep["leaf"]:
                fh.write("%6.2f%%  %6d  %s\n" % (row["pct"], row["hits"], row["at"]))
            fh.write("\n== المكدّس (كلفةٌ تراكميّة) ==\n")
            for row in rep["cumulative"]:
                fh.write("%6.2f%%  %6d  %s\n" % (row["pct"], row["hits"], row["fn"]))
