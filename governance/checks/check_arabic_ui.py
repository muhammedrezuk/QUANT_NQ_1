#!/usr/bin/env python3
"""فحص عربيّة اللوحة — يمنع ظهور رمز إنكليزيّ خام أمام المالك.

سبب وجوده (٢٠٢٦-٠٩-٠٤، مقيس):
    صفحة الإعدادات كانت تعرض ستّ بطاقات من ستّ وثلاثين، فبقيت ثلاثون قيمة
    يعمل بها النظام مخفيّة عن المالك. ولمّا كُشفت، ظهرت بأسمائها الخام
    (`DECISION_MIN_STRENGTH` · `NEWS_HIGH_WINDOW_BEFORE_MIN` …) وبشروحٍ
    تحمل مفاتيح إعداد إنكليزيّة (`analysis_speed` · `fast_required_depth`)
    على شاشة مالكٍ **لا يقرأ الإنكليزيّة** — خرقٌ لدستوره:
    «عربيّ ١٠٠٪ في كل ما يُعرض للمالك». وبحكمه حرفيًّا: «ما بدي ولا شي
    انكليزي او خام».

    الأخطر أنّ العين وحدها كشفته، لا فحص. وعينُ المالك ليست جهاز إنذار:
    عيارٌ جديد يُضاف غدًا بلا اسم عربيّ يمرّ صامتًا كما مرّ هؤلاء.

ما يفحصه — ثلاثة عقود:
    أ) **التغطية**: كل عيار قرار (`DIALS`) وكل مُعامِل معلن (`DECLARED`) له
       اسم عربيّ في `DIAL_AR` أو `PARAM_AR` بملفّ `Settings.tsx`.
    ب) **جودة الاسم**: كل اسم معروض فيه حرف عربيّ فعلًا، وليس معرِّفًا خامًا.
    ج) **مواضع العرض**: العنوان يمرّ بدالّة البحث الموحَّدة، والشرح يمرّ
       بمنقّي العربيّة، ولا يُطبع `param.name`/`dial.name` نصًّا ظاهرًا.

⛔ ما لا يفعله: لا يفتح قاعدة حيّة، ولا يشغّل ذرّة، ولا يعدّل ملفًّا.
   الأرقام اللاتينيّة مسموحة ومطلوبة (`60.0` لا `٦٠٫٠`) فلا يمسّها.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SETTINGS = ROOT / "governance" / "ui" / "src" / "sections" / "Settings.tsx"

#: حرف عربيّ واحد على الأقل = الاسم مترجَم فعلًا لا منسوخ.
ARABIC = re.compile(r"[؀-ۿ]")
#: معرِّف خام بأسلوب المشروع: حروف كبيرة وشرطات سفليّة.
RAW_ID = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")


def _labels(source: str, const_name: str) -> dict[str, str]:
    """مفاتيح خريطة عربيّة وقيمها من نصّ TypeScript، بلا تنفيذ."""
    block = re.search(
        r"const\s+%s\s*:\s*Record<string,\s*string>\s*=\s*\{(.*?)\n\}" % const_name,
        source, re.S)
    if not block:
        return {}
    out: dict[str, str] = {}
    for key, value in re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*:\s*'([^']*)'",
                                 block.group(1), re.M):
        out[key] = value
    return out


def main() -> int:
    from shared.decision_dials import DIALS
    from shared.parameter_registry import DECLARED

    problems: list[str] = []

    if not SETTINGS.is_file():
        print("FAIL ملفّ الإعدادات غير موجود: %s" % SETTINGS)
        return 1
    source = SETTINGS.read_text(encoding="utf-8")

    dial_ar = _labels(source, "DIAL_AR")
    param_ar = _labels(source, "PARAM_AR")
    if not dial_ar and not param_ar:
        problems.append("تعذّر قراءة خرائط الأسماء العربيّة من Settings.tsx "
                        "— تغيّر شكلها؟ الفحص لا يصحّ بلا قراءتها")
    known = {**dial_ar, **param_ar}

    # ── أ) التغطية: لا اسم يُعرض خامًا ────────────────────────────────
    for name in sorted(set(DIALS) | set(DECLARED)):
        if name not in known:
            problems.append("%s: لا اسم عربيّ — سيُعرض خامًا على شاشة المالك"
                            % name)

    # ── ب) جودة الاسم: عربيّ فعلًا، لا معرِّف منسوخ ────────────────────
    for name, label in sorted(known.items()):
        if not ARABIC.search(label):
            problems.append("%s: الاسم المعروض بلا حرف عربيّ (%r)" % (name, label))
        raw = RAW_ID.search(label)
        if raw:
            problems.append("%s: الاسم المعروض يحمل معرِّفًا خامًا (%s)"
                            % (name, raw.group(0)))

    # ── ج) مواضع العرض: حراسة ضدّ الارتداد ───────────────────────────
    # العنوانان يمرّان بالبحث الموحَّد، والشرح بمنقّي العربيّة.
    for needle, why in (
            ("const paramAr", "دالّة البحث الموحَّدة عن الاسم العربيّ"),
            ("const arabicOnly", "منقّي العربيّة للشروح"),
            ("{paramAr(param.name)}", "عنوان بطاقة المُعامِل"),
            ("{paramAr(dial.name)}", "عنوان بطاقة العيار"),
            ("{arabicOnly(dial.where)}", "شرح بطاقة العيار"),
    ):
        if needle not in source:
            problems.append("غاب %s (%s) — عاد العرض الخام؟" % (needle, why))

    # الاسم الخام لا يُطبع نصًّا ظاهرًا؛ مكانه تلميح الفأرة وحده.
    for bare in ("{param.name}</span>", "{dial.name}</span>",
                 "?? param.name}</div>", "?? dial.name}</div>"):
        if bare in source:
            problems.append("يُعرض الاسم الخام نصًّا ظاهرًا: %s" % bare)

    print("فحص عربيّة اللوحة — Settings.tsx")
    print("عيارات=%d · مُعامِلات معلنة=%d · أسماء عربيّة=%d"
          % (len(DIALS), len(DECLARED), len(known)))
    if problems:
        for problem in problems:
            print("FAIL " + problem)
        return 1
    print("OK كل اسم يُعرض للمالك عربيّ، والخام في تلميح الفأرة وحده")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
