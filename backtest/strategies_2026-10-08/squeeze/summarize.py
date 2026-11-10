# -*- coding: utf-8 -*-
"""ملخّص من results.json: المختارة، ثبات الشبكة، ارتباط ترتيب التعلّم بالاختبار، وأثر الانضغاط (الضابط 0.25)."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
D = os.path.dirname(os.path.abspath(__file__))
out = json.load(open(os.path.join(D, "results.json"), encoding="utf-8"))
rows = out["التركيبات"]
sel = out["المختارة"]
print("أيّام عمل:", out["أيّام_عمل"], "حدّ التعلّم:", out["حدّ_التعلّم"], "النهاية:", out["النهاية"])
print("ثبات الشبكة:", out["ثبات_الشبكة"])
for k in ("عدّاد", "صفقات/يوم", "صفقات/يوم_تعلّم", "صفقات/يوم_اختبار", "شراء", "بيع", "مصدر_الهدف",
          "مدّة_الصفقة_د_وسيط", "لندن", "نيويورك", "معيار_المالك"):
    print(k, ":", json.dumps(sel[k], ensure_ascii=False))
g = [r for r in rows if r["في_الشبكة"] and r["تعلّم"].get("n", 0) >= 60 and r["اختبار"].get("n", 0) >= 10]


def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    rk = [0] * len(v)
    for p, i in enumerate(o):
        rk[i] = p
    return rk


L = [r["تعلّم"]["R/صفقة"] for r in g]; T = [r["اختبار"]["R/صفقة"] for r in g]
rl, rt = rank(L), rank(T)
n = len(g)
rho = 1 - 6 * sum((a - b) ** 2 for a, b in zip(rl, rt)) / (n * (n * n - 1))
print("ارتباط ترتيب (سبيرمان) تعلّم⟵اختبار على %d تركيبة: %.2f" % (n, rho))
for ctx in ("أيّ", "اتّفاق"):
    sub = [r for r in rows if r["في_الشبكة"] and r["السياق"] == ctx]
    print("سياق=%s: تعلّم موجب %d/%d · اختبار موجب %d/%d" % (
        ctx, sum(1 for r in sub if (r["تعلّم"].get("R/صفقة") or 0) > 0), len(sub),
        sum(1 for r in sub if (r["اختبار"].get("R/صفقة") or 0) > 0), len(sub)))
top = sorted(g, key=lambda r: -r["تعلّم"]["R/صفقة"])[:6]
for r in top:
    print("أعلى تعلّم: م=%s ق=%s وقف=%s سياق=%s ج=%s | تعلّم %s/%s | اختبار %s/%s معامل %s | أنصاف %s" % (
        r["م"], r["ق"], r["الوقف"], r["السياق"], r["ج"], r["تعلّم"]["n"], r["تعلّم"]["R/صفقة"], r["اختبار"]["n"],
        r["اختبار"]["R/صفقة"], r["اختبار"].get("معامل"), r["معيار_المالك"]["أنصاف_موجبة"]))
passing = [r for r in rows if r["معيار_المالك"]["يجتاز"]]
print("تركيبات تجتاز معيار المالك (للعلم، لا للاختيار): %d" % len(passing))
for r in passing:
    print("  م=%s ق=%s وقف=%s سياق=%s ج=%s في_الشبكة=%s | تعلّم %s/%s | اختبار %s/%s | كلّه R=%s سحب=%s أنصاف=%s" % (
        r["م"], r["ق"], r["الوقف"], r["السياق"], r["ج"], r["في_الشبكة"], r["تعلّم"]["n"], r["تعلّم"]["R/صفقة"],
        r["اختبار"]["n"], r["اختبار"]["R/صفقة"], r["كلّه"]["R"], r["كلّه"]["سحب_R"], r["كلّه"]["أنصاف"]))
