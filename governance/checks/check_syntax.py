#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""فحص نحوٍ لا يكتب بايتًا واحدًا على القرص.

ليلة ٢٠٢٦-٠٩-٢٢ سقطت المنصّة بسطرٍ نحويٍّ مكسور في النواة، ولم يظهر في
سجلٍّ لأنّ الموت يقع عند الاستيراد قبل تهيئة المسجّل. فكان الكاشف مسحًا
بـ`py_compile` — وهو يكتب بايتكود. ثمّ وُجد على الشجرة ‎3,072‎ ملفّ
`*.pyc.tmp` **كسرت أختام قسمين مجمّدين** بلا أن تغيّر حرفًا من الكود،
ونُسبت إلى جلستين ثمّ سُحبت النسبة عنهما.

وحكمُ المالك ٢٠٢٦-٠٩-٢٣: «مو مهم فاعل الآن، مهم الإصلاح». فالإصلاح أن
تكون **أداةُ الفحص نفسها عاجزةً عن التلويث**، لا أن تُنظّف بعدها:

    compile(source, path, "exec")   ⟵ في الذاكرة، ولا مسارَ كتابةٍ أصلًا

ولا `py_compile` ولا `compileall` ولا `import` — ثلاثتُها تكتب. وأيّ
تنظيفٍ في `finally` يبقى وعدًا يُخلَف عند الانقطاع.

⚠️ وحدُّ هذه الأداة معلَنٌ لا مكتوم: **تجد المكسور نحويًّا ولا تجد
المكسور تعاقديًّا.** ليلةَ ٢٠٢٦-٠٩-٢٢ كان العقد خمسةَ ملفّات: ثلاثةٌ
مكسورةٌ نحويًّا **واثنان يُترجَمان** ويُسقطان النواة بـ`TypeError` لأنّ
واجهتهما تغيّرت. فمن أرجع الثلاثة وحدها أسقط النواة مرّةً ثانية.
فالخضراء هنا تعني «كلُّ ملفّ يُقرأ» لا «النظام يقلع».
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# الطرفيّة هنا cp1256 فتُسقط الرموز وتُفجّر الحارس قبل أن يعرض ما وجد.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parents[2]

# ما يُمسح: كودُ المشروع نفسه. و`vendor` مستثنًى — مكتباتٌ خارجيّة لا
# نحكم على نحوها، وهي التي بلغت ‎2,077‎ ملفًّا في حطام ٢٠:٤٤.
SCOPES = ("atoms", "core", "engine", "transport", "shared", "hot",
          "governance", "scripts", "tools")
SKIP_PARTS = {"__pycache__", ".pytest_cache", "vendor", "node_modules",
              "built", ".git"}


def sources() -> list[Path]:
    out: list[Path] = []
    for scope in SCOPES:
        base = ROOT / scope
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if SKIP_PARTS.isdisjoint(path.parts):
                out.append(path)
    return sorted(out)


def main() -> int:
    broken: list[tuple[Path, int, str, str]] = []
    unreadable: list[tuple[Path, str]] = []
    files = sources()
    for path in files:
        try:
            # `utf-8-sig` لأنّ بعض ملفّات المشروع تحمل BOM، و`compile`
            # يرفضه خطأً نحويًّا فيُبلَّغ عن كسرٍ لا وجود له.
            text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            unreadable.append((path, type(exc).__name__))
            continue
        try:
            compile(text, str(path), "exec")
        except SyntaxError as exc:
            broken.append((path, exc.lineno or 0,
                           (exc.text or "").strip()[:120], exc.msg))
        except ValueError as exc:      # مثل: null byte في المصدر
            broken.append((path, 0, "", str(exc)))

    print("فحص النحو — ترجمةٌ في الذاكرة، صفرُ كتابةٍ على القرص")
    print("ملفّات مفحوصة: %d · نطاقات: %s" % (len(files), " · ".join(SCOPES)))
    print()

    if unreadable:
        print("تعذّرت قراءتها (%d) — ليست كسرًا نحويًّا:" % len(unreadable))
        for path, why in unreadable:
            print("  ؟ %s — %s" % (path.relative_to(ROOT).as_posix(), why))
        print()

    if broken:
        print("❌ ملفّات لا تُترجَم (%d) — الاستيراد يموت عندها:" % len(broken))
        for path, line, src, msg in broken:
            print("  ❌ %s:%d — %s" % (path.relative_to(ROOT).as_posix(), line, msg))
            if src:
                print("       %s" % src)
        print()
        print("SYNTAX_SCAN=BROKEN files=%d" % len(broken))
        return 1

    print("✅ كلّ ملفّ يُترجَم. SYNTAX_SCAN=CLEAN files=%d" % len(files))
    print("⚠️ وهذا لا يعني أنّ النظام يقلع: ملفٌّ يُترجَم وواجهتُه متغيّرة")
    print("   يُسقط النواة بـTypeError، وهذا الفحص لا يراه.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
