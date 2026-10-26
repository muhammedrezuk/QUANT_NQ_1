# -*- coding: utf-8 -*-
"""ملخّص مضغوط من results_two.json / results_five.json للقراءة."""
import sys
import os
import json

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
which = sys.argv[1] if len(sys.argv) > 1 else "two"
R = json.load(open(os.path.join(HERE, "results_%s.json" % which), encoding="utf-8"))


def short(s):
    if not s or not s.get("n"):
        return "n=0"
    return "n=%d R=%s R/ص=%s معامل=%s فوز=%s%% سحب=%s" % (s["n"], s["R"], s["R/صفقة"], s["معامل"], s["فوز%"], s["سحب_R"])


for lname in ("نيويورك", "لندن", "كلاهما"):
    res = R[lname]
    print("=" * 20, lname)
    if which == "two":
        print("ثبات:", res["ثبات_الشبكة"])
        rows = res["التركيبات"]
        for r in rows:
            tag = "" if r["في_الشبكة"] else " [ضابط]"
            print("  ي=%d م=%.2f %-6s %-6s ج=%.1f | تعلّم %s | اختبار %s | أنصاف=%s%s" % (
                r["ي"], r["م"], r["الوقف"], r["السياق"], r["ج"], short(r["تعلّم"]), short(r["اختبار"]),
                r["معيار_المالك"]["أنصاف_موجبة"], tag))
        sel = res.get("المختارة")
        if sel:
            print("المختارة:", {k: sel[k] for k in ("ي", "م", "الوقف", "السياق", "ج")})
            for k in ("تعلّم", "اختبار", "كلّه", "لندن", "نيويورك", "شراء", "بيع"):
                print("  %-7s %s %s" % (k, short(sel[k]), sel[k].get("أنصاف", "")))
            print("  صفقات/يوم:", sel["صفقات/يوم"], sel["صفقات/يوم_تعلّم"], sel["صفقات/يوم_اختبار"],
                  "· مدّة وسيط د:", sel["مدّة_الصفقة_د_وسيط"], "· مصدر الهدف:", sel["مصدر_الهدف"])
            print("  عدّاد:", sel["عدّاد"])
            print("  معيار:", sel["معيار_المالك"])
            print("  تدقيق:", sel["تدقيق_التسريب"])
            for name, v in res["أدوات_الورقة_للعلم"].items():
                if "تعلّم" in v:
                    print("  [ورقة] %-70s | كلّه %s | تعلّم R/ص=%s | اختبار R/ص=%s | أنصاف=%s" % (
                        name, short(v["كلّه"]), v["تعلّم"].get("R/صفقة"), v["اختبار"].get("R/صفقة"), v["كلّه"].get("أنصاف")))
    else:
        sel = res.get("المختارة_بلا_تعديل")
        if sel:
            print("المختارة:", {k: sel[k] for k in ("ي", "م", "الوقف", "السياق", "ج")})
            for k in ("كلّه", "لندن", "نيويورك", "شراء", "بيع"):
                print("  %-7s %s" % (k, short(sel[k])))
            print("  أنصاف 6 أشهر:", sel["كلّه"]["أنصاف_6أشهر"])
            print("  أنصاف تقويميّة:", sel["كلّه"]["أنصاف"])
            print("  صفقات/يوم:", sel["صفقات/يوم"], "· مصدر الهدف:", sel["مصدر_الهدف"])
            print("  عدّاد:", sel["عدّاد"])
            print("  معيار:", sel["معيار_المالك"])
            print("  تدقيق:", sel["تدقيق_التسريب"])
            for name, v in res["أدوات_الورقة_للعلم"].items():
                print("  [ورقة] %-70s | %s | أنصاف6=%s" % (name, short(v["كلّه"]), v["كلّه"].get("أنصاف_6أشهر")))
        print("ثبات الشبكة على الخمس:", res["ثبات_الشبكة"])
        for r in res["الشبكة_للعلم"]:
            print("  ي=%d م=%.2f %-6s %-6s ج=%.1f | %s | أنصاف6 موجبة=%s" % (
                r["ي"], r["م"], r["الوقف"], r["السياق"], r["ج"], short(r["كلّه"]), r["معيار_المالك"]["أنصاف_موجبة"]))
