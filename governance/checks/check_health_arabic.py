#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""حارس عربيّة رسائل الصحّة — السطر الذي يقرؤه المالك فعلًا.

لماذا حارسٌ ثانٍ للعربيّة
========================
`check_arabic_ui.py` قائمٌ ويعضّ — لكنّه يفحص **أسماء العيارات والمُعامِلات**
في `Settings.tsx` وحدها. ورسائل صحّة الذرّات — وهي التي تملأ «التنفيذ»
و«التحليل» و«الرئيسيّة» — لم تكن تحت أيّ حارس.

فقِيست يوم ٢٠٢٦-٠٩-١٦ على الـ٢٢٨ ذرّة الحيّة: **١٨٢ اسم حقل و٢٨ قيمة بلا
ترجمة**. وكانت تُعرَض للمالك عبارةً واحدة مكرّرة: «حقل تقني=قيمة تقنية» —
نصٌّ يشبه المعلومة ولا يحمل شيئًا. وحارس العربيّة أخضر طوال الوقت، لأنّه
ينظر إلى السطح الخطأ. وهذه هي شكوى المالك نفسها في ٢٠٢٦-٠٩-٠٤ («ثلاثين بطاقة
بأسمائها الإنكليزيّة الخام») تتكرّر في مكانٍ آخر.

ما يفعله
========
يقرأ رسائل الصحّة الحيّة من `/gov/atoms`، ويحاكي منطق `arabicHealth` بحرفيّته،
ويعدّ ما لا يجد له ترجمة. رموز الأدوات (`EURUSD` · `^GSPC` · `DXY_U6`) ليست
لغةً أجنبيّة بل أسماء أعلام تُكتب لاتينيّةً في كل منصّة — تُستثنى بنمطها لا
بقائمة تُحدَّث يدويًّا.

ولأنّ الذيل طويل ويُعالَج على دفعات، فالعتبة معلَنة بالرقم لا مخفيّة: يسقط
الفحص إذا زاد غير المترجَم عن `MAX_UNKNOWN`. تُخفَّض كلّما عُولجت دفعة —
وخفضُها هو التقدّم المقيس. ولا يُرفع السقف ليمرّ الفحص.

⚠️ يحتاج النواة واللوحة شغّالتين: يقرأ الحيّ لا الورق.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

ARABIC_TS = ROOT / "governance" / "ui" / "src" / "core" / "arabic.ts"
BASE = os.environ.get("NQ_GOV_URL", "http://127.0.0.1:8090").rstrip("/")

# رمز أداة أو مؤشّر — اسم عَلَم لا لغة. نفس النمط المستعمل في `arabic.ts`.
SYMBOLISH = re.compile(r"^\^?[A-Z][A-Z0-9]{2,}(?:[_.][A-Z0-9]+)?$")

# ٢٠٢٦-٠٩-١٦ — درسٌ من الحارس نفسه: ثبّتُّ السقف على القياس بالضبط (١٠٨)
# فسقط الفحص في التشغيل التالي بـ١٠٩. والسبب أنّ رسائل الصحّة **حيّة**: تحمل
# عدّادات وأسبابًا أخيرة تتبدّل كل ثانية، فيظهر ويختفي فيها حطامٌ مثل
# `(mt5=0.0` و`'SYS_5MIN'` و`1843.0000000007567/50+unmeasurable=8`.
#
# وحارسٌ يسقط عشوائيًّا يُعلَّم تجاهله — وهو الداء الذي أُصلحه اليوم كلّه.
# فالعلاج ليس رفع السقف بل **تثبيت المقياس**: ما يُعَدّ هو الكلمة القابلة
# للترجمة أصلًا (حروف وشُرَط سفليّة فقط). أمّا ما فيه قوس أو اقتباس أو كسر
# أو رقم فليس مفردةً في قاموس، بل قيمةٌ أو حطام تنسيق — يُستثنى من العدّ
# ويبقى مرئيًّا في تقرير «الأكثر ورودًا» كي لا يختفي.
WORDLIKE = re.compile(r"^[A-Za-z][A-Za-z_]*$")

# ٢٠٢٦-٠٩-١٦ — **حكمان فُصلا بعد تجربتين فاشلتين**، والفصل هو الدرس:
#
# (أ) **الحكم القاطع** هو `raw_renders()`: موضعٌ يعرض رسالة صحّة بلا تمرير على
#     `arabicHealth`. هذا **تسريبٌ فعليّ** يراه المالك، وهو **حتميّ** — يُقرأ
#     من الكود لا من حالةٍ حيّة، فلا يتبدّل بين تشغيلين. يُسقط الفحص دائمًا.
#
# (ب) **وعدّ الكلمات غير المترجَمة مقياس تغطية لا تسريب**: بعد إصلاح العرض،
#     ما لا تُعرف ترجمته **يُحذف من النصّ** ولا يصل الشاشة. فهو دَينٌ يُسدَّد
#     على دفعات لا جرحٌ مفتوح.
#
# **والعدّاد كان الأداة الخطأ — ثلاث محاولات أثبتت ذلك، وهذا هو الدرس:**
#   ١٠٨ ⟵ سقط بـ١٠٩ · ٧٧ ⟵ سقط بـ٧٩ · ٩٥ ⟵ سقط ثمّ نجح في الدقيقة نفسها.
#
# وظننتُه ضجيجًا عشوائيًّا فوسّعتُ الهامش مرّتين — وكان تشخيصي خاطئًا. القياس
# الصحيح: العدد **يتراكم مع زمن التشغيل ويصفّر عند الإقلاع**، لأنّ الحقول
# الشرطيّة تظهر تباعًا كلّما وقعت أحداثها (`dropped_sell` عند أوّل بيع مرفوض).
# فأيّ سقفٍ رقميّ **سيُتجاوَز حتمًا** كلّما طال التشغيل — أي أنّ توسيع الهامش
# كان يؤجّل الكذبة لا يمنعها.
#
# فالمقياس صار **بالأسماء لا بالعدد**: قائمةٌ لما هو معروفٌ أنّه بلا ترجمة
# اليوم. الكلمة التي فيها دَينٌ مؤجَّل، والكلمة التي ليست فيها **حقلٌ جديد
# دخل النظام بلا ترجمة** فيسقط الفحص عندها وحدها. فلا يصرخ على تراكمٍ معروف،
# ولا يسكت على جديدٍ مجهول. وكلّما تُرجمت كلمة تُحذف من هنا ومن الدَّين معًا.
#
# ٢٠٢٦-١٠-٠٥ (ختم المالك «ترجم nq»): سُدِّد الدَّين كلُّه — ٨٠ كلمةً من ٨١ تُرجمت في
# `arabic.ts` من كود ذرّاتها، ومعها ثمانٍ جديدة؛ و`hard_stops_computed` حُذفت لأنّها
# لم تعد في أيّ كود (لا ذرّة تنشرها). فالقائمة فارغة: أيّ كلمةٍ بلا ترجمة بعد اليوم
# جديدةٌ ويسقط الفحص عندها. ولا تُملأ ثانيةً ليمرّ — تُترجَم.
KNOWN_UNTRANSLATED: frozenset[str] = frozenset()


def dict_keys(name: str, src: str) -> set[str]:
    """مفاتيح قاموس في `arabic.ts` — تُقرأ من الملفّ لا تُكرَّر هنا."""
    m = re.search(rf"(?:const|export const)\s+{name}\s*:\s*Record<string, string>\s*=\s*\{{", src)
    if not m:
        return set()
    i, depth, body = m.end(), 1, []
    while i < len(src) and depth:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if not depth:
                break
        body.append(ch)
        i += 1
    text = "".join(body)
    keys = set(re.findall(r"(?:^|[,{\n])\s*([A-Za-z_]\w*)\s*:", text))
    keys |= set(re.findall(r"(?:^|[,{\n])\s*['\"]([^'\"]+)['\"]\s*:", text))
    return keys


# مواضع تعرض `health.message` بلا تمرير على `arabicHealth` — ثغرةٌ لا يراها
# فحص القاموس: القاموس كامل والموضع لا يمرّ به أصلًا. وقعت مرّتين يوم
# ٢٠٢٦-٠٩-١٦ (`Diag.tsx` عرض `rows=6362 batches=48` و`NQ.tsx` رسالة الحراسة).
RENDER_RE = re.compile(r"\{[^{}]*\b\w+\??\.health\??\.message[^{}]*\}")
SECTIONS_DIR = ROOT / "governance" / "ui" / "src"


def raw_renders() -> list[str]:
    out: list[str] = []
    for path in sorted(SECTIONS_DIR.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        text = re.sub(r"(?<!:)//[^\n]*", " ", text)
        for line_no, line in enumerate(text.split("\n"), 1):
            for hit in RENDER_RE.finditer(line):
                frag = hit.group(0)
                # مسموح: تمرير على المترجم · أو مقارنة منطقيّة لا عرض.
                if "arabicHealth" in frag or "arabicVisible" in frag:
                    continue
                if re.search(r"\.(includes|startsWith|endsWith|match|test)\s*\(", frag):
                    continue
                if "title=" in line:
                    continue
                out.append(f"{path.relative_to(ROOT).as_posix()}:{line_no}  {frag.strip()[:90]}")
    return out


def main() -> int:
    src = ARABIC_TS.read_text(encoding="utf-8", errors="replace")
    reasons, fields = dict_keys("REASONS", src), dict_keys("FIELDS", src)

    try:
        with urllib.request.urlopen(f"{BASE}/gov/atoms", timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"❌ تعذّرت قراءة الذرّات الحيّة: {exc}")
        print("   شغّل «غرفة القيادة» — هذا الحارس يقيس الحيّ لا الورق.")
        return 2

    rows = data.get("atoms") if isinstance(data, dict) else data
    unknown: dict[str, set[int]] = {}
    scanned = 0

    for row in rows or []:
        message = ((row.get("health") or {}).get("message") or "").strip()
        if not message:
            continue
        scanned += 1
        atom_id = row.get("id")
        # ٢٠٢٦-١٠-٠٥ (ختم المالك «ترجم nq»): مرآة الخطوة الأولى في `arabicHealth` —
        # رسالةٌ كاملةٌ مفتاحٌ في `REASONS` تُترجَم جملةً واحدة (`clean.trim()`)، ولا
        # تُقطَّع كلماتٍ. كان الحارس يعدّ `database` و`is` و`locked` كلماتٍ بلا ترجمة
        # والمترجم يترجم الجملة كلّها — نسخةٌ ثانيةٌ انحرفت عن أختها، كما في ٢٠٢٦-٠٩-٢٣.
        if re.sub(r"[\x00-\x08\x0b-\x1f\x7f]+", " · ", message).strip() in reasons:
            continue
        for raw in message.split():
            token = re.sub(r"[،,؛;:]+$", "", raw)
            if not re.search(r"[A-Za-z]", token) or SYMBOLISH.match(token):
                continue
            if token in reasons or token in fields:
                continue
            pair = re.match(r"^([A-Za-z_]+)=(.*)$", token)
            if pair:
                name, value = pair.group(1), pair.group(2)
                # مفتاحٌ اسمه رمز أداة (`BTCUSD=1e-05`) اسم عَلَم لا لغة —
                # يُعرَض كما هو ولا يُعدّ خرقًا (نفس حكم `arabic.ts`).
                #
                # 🔴 ٢٠٢٦-٠٩-٢٣ — كان `name not in fields` وحده، فبقي يبلّغ عن
                # `STOP_BELOW_FLOOR` و`age` و`ack` **بعد أن عرّبتُها فعلًا** —
                # لأنّها في `REASONS` لا في `FIELDS`. أي أنّ حارسي كان يكذب
                # عليّ بعد أن أصلحتُ ما أشار إليه.
                #
                # وعلّتُه أنّ هذا الملفّ **يعيد تنفيذ منطق `arabic.ts`** بلغةٍ
                # أخرى — نسخةٌ ثانية تنحرف عن أختها. أصلحتُ جهةَ الاسم في
                # المترجم (`FIELDS[..] ?? REASONS[..]`) ولم تصل النسخةَ هنا.
                # ⚠️ فمن غيّر منطقَ الأزواج في `arabic.ts` **فليغيّره هنا**:
                # لا سبيلَ لاستيراد تايبسكربت في بايثون، فالمرآةُ عقدٌ يدويّ.
                if name not in fields and name not in reasons \
                        and not SYMBOLISH.match(name):
                    unknown.setdefault(name, set()).add(atom_id)
                # القيمة تُقبل من أيّ القاموسين: الكلمة معناها واحد مفتاحًا
                # كانت أو قيمةً (`sell` حقلٌ في ذرّة وقيمةٌ في أخرى).
                if value and re.search(r"[A-Za-z]", value) \
                        and value not in reasons and value not in fields \
                        and not SYMBOLISH.match(value):
                    unknown.setdefault(value, set()).add(atom_id)
                continue
            unknown.setdefault(token, set()).add(atom_id)

    words = {t: ids for t, ids in unknown.items() if WORDLIKE.match(t)}
    debris = len(unknown) - len(words)
    fresh = {t: ids for t, ids in words.items() if t not in KNOWN_UNTRANSLATED}
    paid = sorted(w for w in KNOWN_UNTRANSLATED if w in fields or w in reasons)

    print("حارس عربيّة رسائل الصحّة — ما يقرؤه المالك على البطاقات")
    print(f"رسائل مفحوصة: {scanned} ذرّة  ·  قاموس: {len(reasons)} سببًا و{len(fields)} حقلًا")
    print(f"دَينٌ معروف: {len(KNOWN_UNTRANSLATED)} كلمة  ·  منها ظاهرٌ الآن: {len(words) - len(fresh)}")
    print(f"(ومعها {debris} قيمةً أو حطام تنسيق لا يُعَدّ — يتبدّل مع كل قراءة)")
    print()

    if paid:
        print(f"✔ سُدِّد من الدَّين ({len(paid)}) — احذفها من `KNOWN_UNTRANSLATED`:")
        print("   " + "، ".join(paid))
        print()

    if words:
        print("الأكثر ورودًا من الدَّين (يُعالَج بالترتيب):")
        ranked = sorted(words.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        for token, ids in ranked[:15]:
            sample = ", ".join(str(i) for i in sorted(ids)[:5])
            print(f"  · {token:<32} ({len(ids)} ذرّة: {sample})")
        if len(ranked) > 15:
            print(f"  … و{len(ranked) - 15} كلمةً أخرى")
        print()

    raw = raw_renders()
    if raw:
        print(f"❌ رسالة صحّة تُعرَض خامًا بلا تعريب ({len(raw)}):")
        for item in raw:
            print(f"   {item}")
        print("   القاموس لا ينفع هنا: الموضع لا يمرّ بـ`arabicHealth` أصلًا.")
        return 1

    if fresh:
        print(f"❌ كلمات جديدة بلا ترجمة ({len(fresh)}) — دخلت النظام بعد آخر جرد:")
        for token, ids in sorted(fresh.items()):
            print(f"   {token:<32} ({len(ids)} ذرّة: {', '.join(str(i) for i in sorted(ids)[:5])})")
        print("   تُترجَم في `core/arabic.ts`، أو تُضاف إلى `KNOWN_UNTRANSLATED` بقرارٍ معلَن.")
        return 1

    print("✅ ما في كلمة جديدة بلا ترجمة، وكل موضع يعرض رسالة صحّة يمرّ بالمترجم.")
    print("   والدَّين المعروف يُسدَّد على دفعات — ولا يُوسَّع ليمرّ الفحص.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
