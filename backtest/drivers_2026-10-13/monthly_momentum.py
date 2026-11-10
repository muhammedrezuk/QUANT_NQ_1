# -*- coding: utf-8 -*-
"""زخم الأشهر على ناسداك 100 — **المحاولة الخامسة لفكرة الزخم** (①–④: آفاقٌ من دقائق إلى أيّام على 2014–2026 — لا زخم يُستغلّ). المالك ١٠-١٣: «نزّل».
الأفق هنا لم يُلمس قطّ (أشهر)، وأغلب البيانات (1986–2013) لم يدخل أيّ قياس ⟸ جزءٌ معزول نظيف.

البيانات: مؤشّر ناسداك 100 اليوميّ من الاحتياطيّ الفيدراليّ (fed/NASDAQ100.csv، 1986-01 ⟵ 2026-10)، إغلاق آخر يوم تداول في كلّ شهر.
الفرضيّة الموثّقة في أبحاث الأسواق (لا تُتعلَّم من بياناتنا): ما صعد في الأشهر الماضية يميل إلى الاستمرار الشهر التالي.
الاختبارات (عددها مُعلَن: 4 نوافذ × 2 صيغة = 8):
  النافذة L = 1 · 3 · 6 · 12 شهرًا؛ الإشارة = جهة عائد آخر L أشهر؛ الاحتفاظ شهرٌ واحد.
  صيغة «شراء/بيع» (مع الإشارة) وصيغة «شراء/نقد» (شراءٌ إن كانت موجبة وإلّا خارج السوق)، مقارنةً بالشراء الدائم.
الفترات للثبات: 1986–2004 · 2005–2013 · 2014–2026.
التكلفة: سبريد نقطة عند كلّ تغيير جهة (ضئيلة شهريًّا). **تمويل الليالي غير محسوب** للصيغ كلّها ولا للشراء الدائم (المقارنة نسبيّة).
الحكم الرئيس (مكتوبٌ قبل النتائج): النافذة 12 بصيغة «شراء/بيع» — «يصمد» إن كان ارتباط عائد الـ12 شهرًا بالشهر التالي **موجبًا وخارج الصدفة (±2/√ن)
على الأربعين سنة**، و**متوسّط الصيغة موجبًا في الفترات الثلاث كلٍّ على حدة**؛ وإلّا «لا يصمد». والباقي ثانويّ (مقارناتٌ كثيرة). قياسٌ فقط.
"""
import csv
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run_monthly.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
LOOKBACKS = (1, 3, 6, 12)
MAIN_L = 12
SPREAD_PTS = 1.0
PERIODS = (("1986–2004", "1986", "2005"), ("2005–2013", "2005", "2014"), ("2014–2026", "2014", "2100"))


def monthly():
    last = {}
    with open(os.path.join(HERE, "fed", "NASDAQ100.csv"), encoding="utf-8") as f:
        r = csv.reader(f)
        next(r)
        for d, v in r:
            try:
                last[d[:7]] = (d, float(v))
            except ValueError:
                continue
    months = sorted(last)
    return [(m, last[m][1]) for m in months[:-1]]          # الشهر الأخير غير مكتمل


def stats(x):
    x = np.asarray(x, float)
    if len(x) < 12:
        return {"أشهر": int(len(x))}
    eq = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    return {"أشهر": int(len(x)), "متوسّط_شهريّ_٪": round(float(x.mean()), 3), "انحراف_٪": round(float(x.std()), 2),
            "نسبة_العائد_للمخاطرة_سنويًّا": round(float(x.mean() / x.std() * math.sqrt(12)), 2) if x.std() > 0 else None,
            "أشهر_رابحة_٪": round(float(np.mean(x > 0)) * 100, 1), "أقصى_تراجع_٪": round(dd, 1)}


def main():
    t0 = time.time()
    M = monthly()
    names = [m for m, _ in M]
    C = np.array([c for _, c in M])
    r = np.r_[np.nan, np.diff(np.log(C))] * 100          # عائد الشهر بالنسبة المئويّة (لوغاريتميّ)
    out = {"التصميم": __doc__, "من": names[0], "إلى": names[-1], "أشهر": len(M), "النوافذ": {}}
    for L in LOOKBACKS:
        rows = []
        for t in range(L, len(C) - 1):
            past = math.log(C[t] / C[t - L]) * 100
            nxt = r[t + 1]
            sig = 1 if past > 0 else -1 if past < 0 else 0
            cost = SPREAD_PTS / C[t] * 100
            rows.append((names[t + 1], past, nxt, sig, cost))
        res = {}
        prev_ls = prev_lf = 0
        ls, lf, bh = [], [], []
        for m, past, nxt, sig, cost in rows:
            ls.append((m, sig * nxt - (cost if sig != prev_ls else 0)))
            pos = 1 if sig > 0 else 0
            lf.append((m, pos * nxt - (cost if pos != prev_lf else 0)))
            bh.append((m, nxt))
            prev_ls, prev_lf = sig, pos
        allp = [p[1] for p in rows]
        alln = [p[2] for p in rows]
        c = float(np.corrcoef(allp, alln)[0, 1])
        res["الكلّ"] = {"ارتباط": round(c, 4), "نطاق": round(2 / math.sqrt(len(rows)), 4),
                        "شراء_بيع": stats([v for _, v in ls]), "شراء_نقد": stats([v for _, v in lf]), "شراء_دائم": stats([v for _, v in bh])}
        for pname, a, b in PERIODS:
            sel = [i for i, (m, *_rest) in enumerate(rows) if a <= m < b]
            if not sel:
                continue
            pp = [rows[i][1] for i in sel]
            nn = [rows[i][2] for i in sel]
            cc = float(np.corrcoef(pp, nn)[0, 1]) if len(sel) > 12 else None
            res[pname] = {"ارتباط": None if cc is None else round(cc, 4), "نطاق": round(2 / math.sqrt(len(sel)), 4),
                          "شراء_بيع": stats([ls[i][1] for i in sel]), "شراء_نقد": stats([lf[i][1] for i in sel]),
                          "شراء_دائم": stats([bh[i][1] for i in sel])}
        out["النوافذ"][L] = res
    main_r = out["النوافذ"][MAIN_L]
    holds = (main_r["الكلّ"]["ارتباط"] > main_r["الكلّ"]["نطاق"] and
             all(main_r[p]["شراء_بيع"].get("متوسّط_شهريّ_٪", -1) > 0 for p, _, _ in PERIODS))
    out["الحكم"] = "يصمد" if holds else "لا يصمد"
    out["المدّة_ث"] = round(time.time() - t0, 2)
    json.dump(out, open(os.path.join(HERE, "monthly_momentum.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L_ = ["# زخم الأشهر على ناسداك 100 — المحاولة الخامسة لفكرة الزخم (8 اختبارات مُعلَنة، ١٠-١٣)", "",
          "**الحكم الرئيس (12 شهرًا · شراء/بيع): %s.**" % out["الحكم"], "",
          "البيانات %s ⟵ %s (%d شهرًا). العوائد شهريّة بالنسبة المئويّة؛ «نسبة العائد للمخاطرة» سنويّة؛ تمويل الليالي غير محسوب لأيّ صيغة." % (
              out["من"], out["إلى"], out["أشهر"]), ""]
    for L, res in out["النوافذ"].items():
        L_ += ["## النافذة %s شهرًا" % L, "", "| الفترة | ارتباط (نطاق) | الصيغة | متوسّط شهريّ ٪ | نسبة العائد للمخاطرة | أشهر رابحة ٪ | أقصى تراجع ٪ |",
               "|---|---|---|---|---|---|---|"]
        for p, v in res.items():
            for key in ("شراء_بيع", "شراء_نقد", "شراء_دائم"):
                s = v[key]
                L_.append("| %s | %s (±%s) | %s | %s | %s | %s | %s |" % (p, v["ارتباط"], v["نطاق"], key.replace("_", "/"), s.get("متوسّط_شهريّ_٪"),
                                                                     s.get("نسبة_العائد_للمخاطرة_سنويًّا"), s.get("أشهر_رابحة_٪"), s.get("أقصى_تراجع_٪")))
        L_.append("")
    open(os.path.join(HERE, "زخم الأشهر.md"), "w", encoding="utf-8").write("\n".join(L_) + "\n")
    print("الحكم:", out["الحكم"], flush=True)


if __name__ == "__main__":
    main()
