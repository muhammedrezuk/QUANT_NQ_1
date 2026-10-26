"""Contract guard for item 21 — one canonical run path, and no wrapper that lies.

Owner's ruling: `governance\\scripts` is canonical; the `scripts\\` wrappers are
kept (never deleted) but they must NOT be a second source of truth.

What item 64 proved the hard way: `scripts\\run_core.py` forwarded with
`from governance.scripts.run_core import main`, but running it as
`python scripts/run_core.py` puts `scripts/` on sys.path -- not the project root
-- so the import raised ModuleNotFoundError and the process died before opening
a port. From the outside that read as "the core did not boot", and it killed the
only two tests that run the core as a real process for four days.

Every other wrapper in `scripts\\` is four lines with the SAME shape and the
SAME defect: they are forwarders that cannot forward.

  أ) لا منطق مكرَّر -- a wrapper carries no implementation: it bootstraps the
     path, imports the canonical module, and calls it. Nothing else.
  ب) وتُشغَّل فعلًا -- each wrapper is RUN as a real subprocess. A forwarder that
     dies on import is not a forwarder; it is a trap. This is the barrier the
     four-line shape cannot pass.

Exit 1 on any divergence.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

WRAPPERS = ROOT / "scripts"
CANONICAL = ROOT / "governance"
MAX_WRAPPER_LINES = 24
# ٢٠٢٦-٠٩-١٦ — كان `ROOT/venv/Scripts/python.exe`، **وهو مسارٌ لا وجود له**
# (قِيس: `venv` غير موجودة، والمفسّر الحيّ في `vendor/python/runtime`). فكان
# الفحص يرمي `FileNotFoundError` عند أوّل غلاف، أي أنّ الجزء (ب) — وهو الجزء
# الذي كُتب **بسبب** عطلٍ دام أربعة أيّام — **لم يُشغَّل مرّة واحدة** منذ تبدّل
# المفسّر. حارسُ مسارِ الإقلاع كان هو نفسه معطَّلًا.
#
# الصواب أن يُجرَّب بالمفسّر الذي يُشغَّل به المشروع فعلًا: `sys.executable`
# هو مفسّر هذا الفحص نفسه، ومعه مرشّحان معروفان احتياطًا. وإن لم يوجد أيّ
# مفسّر صالح فالفحص **يُعلن ذلك خرقًا** ولا يمرّ صامتًا.
def _interpreter() -> Path | None:
    candidates = [
        Path(sys.executable) if sys.executable else None,
        ROOT / "vendor" / "python" / "runtime" / "python.exe",
        ROOT / "venv" / "Scripts" / "python.exe",
    ]
    for cand in candidates:
        if cand and cand.is_file():
            return cand
    return None


PY = _interpreter()
IMPORT_ERROR = "ModuleNotFoundError"


def wrappers() -> list:
    return [p for p in sorted(WRAPPERS.glob("*.py")) if p.name != "__init__.py"]


def structural() -> int:
    print("=" * 86)
    print("أ) الأغلفة لا تحمل منطقًا — المسار الأصل هو governance")
    print("=" * 86)
    bad = 0
    for path in wrappers():
        src = path.read_text(encoding="utf-8")
        lines = len(src.splitlines())
        forwards = re.search(r"^from\s+governance[.\s]", src, re.M) is not None
        defs = len(re.findall(r"^\s*(def|class)\s+", src, re.M))
        ok = forwards and lines <= MAX_WRAPPER_LINES and defs == 0
        bad += 0 if ok else 1
        print("      %-30s %3d سطر · يحوّل=%-4s · تعريفات=%d %s"
              % (path.name, lines, "نعم" if forwards else "لا", defs,
                 "✓" if ok else "✗"))
    return bad


def behavioural() -> int:
    print("\n" + "=" * 86)
    print("ب) وكلّ غلاف يُشغَّل فعلًا — لا استيراد ينهار")
    print("=" * 86)
    bad = 0
    # The 601/609 lesson again: a polluted environment lies to the check. With
    # PYTHONPATH pointing at the project the wrappers import fine and the defect
    # is invisible -- but the owner's dashboard and a plain double-click do not
    # set it. The child is run with PYTHONPATH REMOVED, which is the real case.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    if PY is None:
        print("      ✗ لا مفسّر بايثون صالح — الجزء (ب) لم يُشغَّل، وهذا خرقٌ لا تجاوز")
        return 1
    for path in wrappers():
        # ٢٠٢٦-٠٩-١٦: `TimeoutExpired` كان يُسقط الفحص كلّه عند أوّل غلاف يعلق
        # (`product_gate_20point.py --help` علق ٩٠ ثانية)، فتضيع نتائج ما بعده.
        # والتعليق **هو بعينه** ما يحرسه هذا العقد: غلافٌ يُشغّل العمل كلّه بدل
        # أن يعرض مساعدته ليس محوِّلًا بل فخّ. فصار يُسجَّل خرقًا ويُكمَّل الدور.
        #
        # ٢٠٢٦-٠٩-٢٣ (ختم nq «صلح كامل»): وكان `--help` نفسُه هو الفخّ. قِيس:
        # `scripts/stop_all.py` لا يقرأ `sys.argv` إطلاقًا، فـ`stop_all.py --help`
        # **يطفئ المنافذ الثمانية كلّها** — والفحص يُشغَّل ليلًا مع كلّ
        # `check_*.py` من `night_audit.py:207`. فحارسُ مسار الإقلاع كان زرَّ إطفاءٍ
        # مخفيًّا للمنصّة الحيّة. والعطل الذي كُتب الجزء (ب) له عطلُ **استيراد**
        # (`ModuleNotFoundError` عند أوّل سطر)، وهذا يُرى بتنفيذ رأس الغلاف كما
        # يُنفَّذ حقًّا — `sys.path[0]` = مجلّد `scripts` لا جذر المشروع — مع
        # `run_name` غير `__main__`، فتجري الاستيرادات كلّها ولا يجري العمل.
        # (كلّ الأغلفة الـ52 محروسة بـ`if __name__ == "__main__"` — قِيس اليوم.)
        probe = ("import os, runpy, sys; p = sys.argv[1]; "
                 "sys.path[0] = os.path.dirname(p); "
                 "runpy.run_path(p, run_name='__nq_import_probe__')")
        try:
            proc = subprocess.run([str(PY), "-c", probe, str(path)], cwd=str(ROOT),
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=90, env=env)
        except subprocess.TimeoutExpired:
            bad += 1
            print("      %-30s ✗ علّق ٩٠ ثانية عند الاستيراد (رأسُه يعمل بدل أن يحوّل)" % path.name)
            continue
        broken = IMPORT_ERROR in (proc.stderr or "")
        bad += 1 if broken else 0
        print("      %-30s %s" % (path.name,
                                  "✗ %s" % IMPORT_ERROR if broken else "✓ يستورد"))
    return bad


def main() -> int:
    bad = structural() + behavioural()
    print("\n" + "=" * 86)
    print("الاختلافات = %d" % bad)
    if bad == 0:
        print("سليم: مسار أصل واحد · والأغلفة تحوّل فعلًا ولا تكون مصدر حقيقة ثانيًا.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
