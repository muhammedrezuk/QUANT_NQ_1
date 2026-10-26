# -*- coding: utf-8 -*-
"""فحصٌ بعديّ لصفقات المختارة: المتوسّط والانحراف وإحصاء t للتعلّم والاختبار، ومدد الصفقات، وتداخلها."""
import json
import math
import os
from datetime import datetime, timezone

OUT = os.path.dirname(os.path.abspath(__file__))
res = json.load(open(os.path.join(OUT, "results.json"), encoding="utf-8"))
tr = json.load(open(os.path.join(OUT, "trades_best.json"), encoding="utf-8"))
split = datetime.strptime(res["الفاصل"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()


def desc(rs):
    n = len(rs); m = sum(rs) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in rs) / (n - 1))
    return {"n": n, "متوسّط": round(m, 3), "انحراف": round(sd, 3), "t": round(m / (sd / math.sqrt(n)), 2)}


learn = [x[2] for x in tr if x[0] < split]; test = [x[2] for x in tr if x[0] >= split]
print("تعلّم", desc(learn)); print("اختبار", desc(test)); print("كلّه", desc(learn + test))
dur = sorted((x[1] - x[0]) / 60 for x in tr)
print("مدّة الصفقة بالدقائق: وسيط %.0f · المئين 90 %.0f · الأقصى %.0f" % (dur[len(dur) // 2], dur[int(0.9 * len(dur))], dur[-1]))
over = sum(1 for a, b in zip(tr, tr[1:]) if b[0] < a[1])
print("تداخل صفقات متتالية (يجب 0):", over)
buckets = {"وقف كامل (≈−1)": 0, "تعادل تقريبًا": 0, "ربح جزئيّ": 0, "هدف كامل (≥2.5)": 0}
for x in tr:
    r = x[2]
    if r <= -0.9: buckets["وقف كامل (≈−1)"] += 1
    elif r < 0.15: buckets["تعادل تقريبًا"] += 1
    elif r < 2.5: buckets["ربح جزئيّ"] += 1
    else: buckets["هدف كامل (≥2.5)"] += 1
print("توزيع النتائج:", buckets)
buys = [x[2] for x in tr if x[4]]; sells = [x[2] for x in tr if not x[4]]
print("شراء", desc(buys), "· بيع", desc(sells))
# أفضل تركيبةٍ في كلّ عائلة سياق (للعلم: الاختيار على التعلّم وحده)
fam = {}
for i, r in enumerate(res["تركيبات"]):
    fam.setdefault(r["السياق"], []).append((r["اختبار"].get("R/صفقة"), r["تعلّم"].get("R/صفقة")))
for k, v in fam.items():
    te = [a for a, _ in v]; le = [b for _, b in v]
    print("عائلة %s: التعلّم من %s إلى %s · الاختبار من %s إلى %s" % (k, min(le), max(le), min(te), max(te)))
print("تركيبات تجتاز معيار المالك:", sum(r["يجتاز_معيار_المالك"] for r in res["تركيبات"]), "من", len(res["تركيبات"]))
