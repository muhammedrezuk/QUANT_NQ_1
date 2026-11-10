# -*- coding: utf-8 -*-
"""احتمال نجاح البطاقة — فحوص مساندة على ملفّ الخصائص (لا تحميل بيانات):
  ١) جدول البطاقة لكلّ نافذة بمراحل الأثلاث كاملة (وقفٌ كامل · الأوّل · الثاني · النهائيّ) ومتوسّط R لكلّ مرحلة.
  ٢) هل فرق «بلوغ النهائيّ» بين لندن ونيويورك صدفة؟ (اختبار فيشر الدقيق، جهتان) — تعلّم · اختبار · كلّه.
  ٣) فرق R/صفقة لندن − نيويورك بالتبديل العشوائيّ (جهتان).
  ٤) الخاصّة الأثبت جهةً في الفحص (نسبة الهدف إلى الخطر): احتمالها بالتبديل في الاختبار — مع تذكير التعدّد.
"""
import json
import math

import numpy as np

D = json.load(open("card_prob_trades.json", encoding="utf-8"))
T = sorted(D["trades"], key=lambda x: x["t"])
SPLIT = D["meta"]["split"]
train = [x for x in T if x["t"] < SPLIT]; test = [x for x in T if x["t"] >= SPLIT]
RNG = np.random.default_rng(7)
out = {}


def card_table(rows):
    n = len(rows)
    st = {s: [x for x in rows if x["stage"] == s] for s in range(4)}
    return {"n": n,
            "وقفٌ_كامل%": round(100 * len(st[0]) / n, 1),
            "بلغ_الأوّل%": round(100 * sum(x["stage"] >= 1 for x in rows) / n, 1),
            "بلغ_الثاني%": round(100 * sum(x["stage"] >= 2 for x in rows) / n, 1),
            "بلغ_النهائيّ%": round(100 * len(st[3]) / n, 1),
            "متوسّط_R_لكلّ_مرحلة": {s: (round(sum(x["r"] for x in v) / len(v), 3) if v else None) for s, v in st.items()},
            "R/صفقة": round(sum(x["r"] for x in rows) / n, 3),
            "نسبة_الهدف_إلى_الخطر_الوسيطة": round(sorted(x["rr"] for x in rows)[n // 2], 2),
            "مدّة_الصفقة_الوسيطة_د": round(sorted(x["hold_min"] for x in rows)[n // 2])}


out["جدول_البطاقة"] = {}
for name, key in (("الكلّ", None), ("لندن", "london_peak"), ("نيويورك", "ny_open")):
    out["جدول_البطاقة"][name] = {part: card_table([x for x in rows if key is None or x["window"] == key])
                                 for part, rows in (("كلّه", T), ("تعلّم", train), ("اختبار", test))}


def fisher_two_sided(a, b, c, d):
    """جدول 2×2 [[a,b],[c,d]] — مجموع احتمالات الجداول التي احتمالها ≤ المرصود."""
    n1, n2, k = a + b, c + d, a + c
    def pr(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n1 + n2, k)
    p0 = pr(a)
    return sum(pr(x) for x in range(max(0, k - n2), min(k, n1) + 1) if pr(x) <= p0 * (1 + 1e-9))


out["فيشر_النهائيّ_لندن_مقابل_نيويورك"] = {}
for part, rows in (("تعلّم", train), ("اختبار", test), ("كلّه", T)):
    L = [x for x in rows if x["window"] == "london_peak"]; N = [x for x in rows if x["window"] == "ny_open"]
    a = sum(x["hit_final"] for x in L); c = sum(x["hit_final"] for x in N)
    out["فيشر_النهائيّ_لندن_مقابل_نيويورك"][part] = {"لندن": "%d/%d" % (a, len(L)), "نيويورك": "%d/%d" % (c, len(N)),
                                                     "احتمال_الصدفة": round(fisher_two_sided(a, len(L) - a, c, len(N) - c), 4)}


def perm_two_sided(r_a, r_b, n=20000):
    r = np.array(r_a + r_b); na = len(r_a)
    obs = abs(np.mean(r_a) - np.mean(r_b)); cnt = 0
    for _ in range(n):
        q = RNG.permutation(len(r))
        cnt += abs(r[q[:na]].mean() - r[q[na:]].mean()) >= obs - 1e-12
    return round(float(np.mean(r_a) - np.mean(r_b)), 3), round((cnt + 1) / (n + 1), 4)


out["تبديل_R_لندن_مقابل_نيويورك"] = {}
for part, rows in (("تعلّم", train), ("اختبار", test), ("كلّه", T)):
    d, p = perm_two_sided([x["r"] for x in rows if x["window"] == "london_peak"], [x["r"] for x in rows if x["window"] == "ny_open"])
    out["تبديل_R_لندن_مقابل_نيويورك"][part] = {"فرق": d, "احتمال_الصدفة": p}

# نسبة الهدف إلى الخطر: فوق وسيط التعلّم مقابل تحته — في الاختبار (جهةٌ واحدة، الجهة من التعلّم)
med = sorted(x["rr"] for x in train)[len(train) // 2]
hi = [x["r"] for x in test if x["rr"] > med]; lo = [x["r"] for x in test if x["rr"] <= med]
r = np.array(hi + lo); obs = np.mean(hi) - np.mean(lo); cnt = 0
for _ in range(20000):
    q = RNG.permutation(len(r))
    cnt += (r[q[:len(hi)]].mean() - r[q[len(hi):]].mean()) >= obs - 1e-12
out["نسبة_الهدف_إلى_الخطر"] = {"وسيط_التعلّم": round(med, 3), "اختبار_فوق": [len(hi), round(float(np.mean(hi)), 3)],
                               "اختبار_تحت": [len(lo), round(float(np.mean(lo)), 3)],
                               "احتمال_الصدفة_جهة_واحدة": round((cnt + 1) / 20001, 4),
                               "بعد_تصحيح_التعدّد_21_خاصّة(بونفروني)": round(min(1.0, 21 * (cnt + 1) / 20001), 3)}
# احتمال أن تتّفق 8 خصائص أو أقلّ من 21 في الجهة صدفةً (لو كانت كلّها بلا أثر: كلٌّ 50٪)
out["8_من_21_بالصدفة_أو_أقلّ"] = round(sum(math.comb(21, k) for k in range(0, 9)) / 2 ** 21, 3)

json.dump(out, open("card_prob_checks.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
