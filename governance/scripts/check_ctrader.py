#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""فحص تغذية سي-تريدر — قراءة فقط، بلا أمر وبلا كتابة.

لماذا أُعيد كتابته
==================
كان هنا فحصٌ يقرأ ملفّ جسر JSONL يكتبه cBot:
``…\\cTrader\\User Files\\quant_nq_bridge\\ctrader_bridge.jsonl``
وحُذف الملفّ ضمن فصل السوق الثاني (``0a576b9``، ختم ``NQ``). **وبقي زرّه على
لوحة المالك** («فحوصات الحوكمة» ← «فحص تغذية سي-تريدر») يشير إلى ملفٍّ غير
موجود، ووصفه يَعِد بأنّه «يتأكّد أنّ قارئ سي-تريدر عم يكتب تكّات وعمق فعليًا».

فكان الزرّ يكذب من ثلاث جهات: يوجد، ويصف معماريّةً ماتت، ولا يعمل.

ولا تصحّ إعادة القديم: الذرّة صارت ``622_تغذية_FIX_سي_تريدر`` وتتّصل عبر
``shared/fix_session`` — لا ملفّ JSONL يُكتَب أصلًا (قِيس: المسار غير موجود).
ففحصُ ملفٍّ لا يكتبه أحد كذبٌ جديد مكان القديم.

ما يفعله الآن
=============
يقرأ مصدرين حيّين عبر خادم الحوكمة (نفس ما تقرؤه اللوحة، بلا مقبس على النواة):

* ``/gov/atoms``     — حالة ٦٢١ (مرجع سي-تريدر) و٦٢٢ (تغذية FIX) ورسالة صحّتهما.
* ``/gov/bus-stats`` — عدّادات النشر لأحداث التغذية.

وعدّادات النشر **تراكميّة من الإقلاع**، فالرقم وحده لا يقول إن كانت التغذية
حيّة الآن أم ماتت قبل ساعة. لذلك تُؤخذ عيّنتان بينهما فاصل، ويُحكَم بالفارق:
الحركة بين العيّنتين هي الدليل، لا المجموع.

وما لا يستطيع هذا الفحص معرفته يقوله صراحةً ولا يخمّنه.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

BASE = os.environ.get("NQ_GOV_URL", "http://127.0.0.1:8090").rstrip("/")
GAP_S = 6.0

# أحداث التغذية ومعناها بالعربي — لا يُعرَض رمزٌ خام للمالك.
FEED_EVENTS = {
    "feed.ctrader.raw": "الوارد الخام من الجلسة",
    "feed.ctrader.tick": "تِكّة سي-تريدر",
    "feed.ctrader.state": "حالة التغذية",
    "market.tick": "تِكّة السوق",
    "market.depth": "عمق السوق",
    "market.ctrader.symbol_specs": "مواصفات الرموز",
}
ATOMS = {621: "مرجع سي-تريدر", 622: "تغذية FIX سي-تريدر"}


def _get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _published(stats) -> dict:
    pub = stats.get("published") if isinstance(stats, dict) else None
    return pub if isinstance(pub, dict) else {}


def main() -> int:
    print("فحص تغذية سي-تريدر — قراءة فقط، ولا أمر يُرسَل")
    print(f"المصدر: {BASE}  ·  الذرّة ٦٢٢ تتّصل بـFIX لا بملفّ جسر")
    print("=" * 70)

    try:
        atoms = _get("/gov/atoms")
        first = _published(_get("/gov/bus-stats"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"❌ تعذّرت القراءة من خادم الحوكمة: {exc}")
        print("   شغّل «غرفة القيادة» أوّلًا — هذا الفحص لا يقرأ من مكان آخر.")
        return 2

    rows = atoms.get("atoms") if isinstance(atoms, dict) else atoms
    by_id = {int(a.get("id")): a for a in (rows or []) if str(a.get("id", "")).isdigit()}

    print("حالة الذرّتين الآن:")
    missing = []
    for atom_id, name in ATOMS.items():
        rec = by_id.get(atom_id)
        if not rec:
            missing.append(atom_id)
            print(f"  ❌ {atom_id} {name}: غير موجودة في قائمة النواة")
            continue
        health = rec.get("health") or {}
        print(f"  · {atom_id} {name}: {rec.get('state')} · "
              f"{health.get('state')} · {health.get('message') or 'بلا رسالة'}")

    print()
    print(f"عدّادات النشر — عيّنتان بينهما {GAP_S:.0f} ثوانٍ (الفارق هو الدليل لا المجموع):")
    time.sleep(GAP_S)
    try:
        second = _published(_get("/gov/bus-stats"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"❌ تعذّرت العيّنة الثانية: {exc}")
        return 2

    moving = 0
    for event, label in FEED_EVENTS.items():
        a = first.get(event)
        b = second.get(event)
        if a is None and b is None:
            print(f"  · {label:<22} لم يُنشَر قط منذ الإقلاع")
            continue
        delta = (b or 0) - (a or 0)
        moving += 1 if delta > 0 else 0
        mark = "✓" if delta > 0 else "·"
        rate = delta / GAP_S
        print(f"  {mark} {label:<22} المجموع {b or 0:>9,}   ·   "
              f"الجديد {delta:>5,}   ·   {rate:6.1f}/ث")

    print()
    print("=" * 70)
    if missing:
        print("❌ ذرّة التغذية غير محمَّلة بالنواة — لا معنى لقراءة العدّادات.")
        return 1
    if moving == 0:
        print("❌ صفر حدث تغذية جديد خلال النافذة — التغذية واقفة الآن.")
        print("   (المجموع قد يكون كبيرًا: ذاك تاريخٌ، لا حياة.)")
        return 1
    print(f"✅ التغذية حيّة: {moving} من {len(FEED_EVENTS)} أحداث تحرّكت خلال النافذة.")
    print("   وما لا يعرفه هذا الفحص: جودة الأسعار وصحّة الرموز — تلك على")
    print("   صفحتَي «السوق والاتصال» و«التحليل»، لا هنا.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
