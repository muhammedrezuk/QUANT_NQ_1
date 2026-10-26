# -*- coding: utf-8 -*-
"""الزخم والتسارع على الناسداك — **المحاولة الثالثة لفكرة الزخم** (الأولى: 408 الحيّة على السنة −165 وحدة؛ الثانية: شبكة النوافذ، +0.005 ≈ صفر).
بأمر المالك ١٠-١٣ «قيسهم» بعد مقترحٍ من جهةٍ أخرى. القانون: الجزء المعزول = 2014-07 ⟵ 2024 لم يُلمس في أيّ قياسٍ للزخم على الشموع؛ وعدد
الاختبارات مُعلَن: 4 أطر × (١ + ١ + ٤ حالات) = 24.

البيانات: شموع دقيقة الناسداك (مخزن سي‑تريدر) مجمّعة في حاويات 5 د · 15 د · ساعة · 4 س (متّصلة فقط). النافذة **ثابتة مسبقًا** N = 10 شمعات
(لا مطاردة نوافذ)، والأفق H = 5 شمعات، والعيّنات لا تتداخل (كلّ H).
  الزخم M = عائد آخر 10 شمعات · التسارع A = عائد آخر 5 − عائد الـ5 قبلها · الهدف = عائد الـ5 التالية (نقطة أساس).
  الحال: تقلّب آخر 10 شمعات (عالٍ/منخفض عن وسيط فترة البناء) · الكفاءة = |صافي الحركة| ÷ مجموع الحركات في آخر 10 (اتّجاه/تذبذب عن الوسيط).
الاختبارات لكلّ إطار:
  ① هل يتنبّأ الزخم بعد التكلفة؟ ارتباط M بالهدف، ومحاكاة «اتّبع إشارة M» (أو عكسها إن كانت إشارة البناء سالبة) بتكلفة سبريد نقطة.
  ② هل يضيف التسارع فوق الزخم؟ الارتباط الجزئيّ لـ A بالهدف بعد إزالة M من الاثنين.
  ③ هل يفيد في حالٍ معيّنة فقط؟ ① داخل كلّ حال من الأربع (تقلّب عالٍ/منخفض · اتّجاه/تذبذب).
  مرجع «بلا زخم»: متوسّط الهدف نفسه (الانجراف) — والمحاكاة تُقارَن به.
الفترات: بناء 2014-07 ⟵ 2019 (منه الإشارة والوسيطات) · امتحان 2020 ⟵ 2024 (الحكم) · 2025–2026 «ملموسة» تُعرض للاطّلاع فقط.
الحكم (مكتوبٌ قبل النتائج): الزخم «يضيف» على إطار إن كان في الامتحان بإشارة البناء وخارج الصدفة (±2/√ن) **ومحاكاته موجبة بعد التكلفة**؛ والتسارع
«يضيف» إن كان جزئيّه في الامتحان بإشارة البناء وخارج الصدفة؛ والحال «تفيد» إن تحقّق شرط الزخم داخلها. وإلّا «لا يضيف». قياسٌ فقط.
"""
import calendar
import json
import math
import os
import sqlite3
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run_momentum.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
FRAMES = (("5 د", 5), ("15 د", 15), ("ساعة", 60), ("4 س", 240))
N, HALF, H = 10, 5, 5
SPREAD_PTS = 1.0
PERIODS = (("بناء", 0, calendar.timegm((2020, 1, 1, 0, 0, 0))),
           ("امتحان", calendar.timegm((2020, 1, 1, 0, 0, 0)), calendar.timegm((2025, 1, 1, 0, 0, 0))),
           ("ملموسة", calendar.timegm((2025, 1, 1, 0, 0, 0)), 1e12))


def load():
    con = sqlite3.connect(HIST, uri=True)
    a = np.array(con.execute("select period_start, close from candles_history where symbol='USTEC' and period='M1' "
                             "order by period_start").fetchall(), dtype=float)
    con.close()
    return a[:, 0], a[:, 1]


def bucket(ts, cl, minutes):
    b = np.floor(ts / (minutes * 60)).astype(np.int64)
    last = np.r_[np.nonzero(np.diff(b))[0], len(b) - 1]
    return b[last], ts[last], cl[last]


def samples(B, T, C):
    rows = []
    i = N
    while i + H < len(C):
        if B[i + H] - B[i - N] == N + H:
            lr = np.diff(np.log(C[i - N:i + 1]))
            M = math.log(C[i] / C[i - N]) * 1e4
            A = (math.log(C[i] / C[i - HALF]) - math.log(C[i - HALF] / C[i - N])) * 1e4
            fwd = math.log(C[i + H] / C[i]) * 1e4
            vol = float(lr.std()) * 1e4
            eff = abs(lr.sum()) / float(np.abs(lr).sum()) if np.abs(lr).sum() > 0 else 0.0
            rows.append((T[i], M, A, fwd, vol, eff, SPREAD_PTS / C[i] * 1e4))
            i += H
        else:
            i += 1
    return np.array(rows)


def corr(x, y):
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 30 and x.std() > 0 and y.std() > 0 else None


def partial(a, m, y):
    if len(a) < 30:
        return None
    X = np.c_[np.ones(len(m)), m]
    ra = a - X @ np.linalg.lstsq(X, a, rcond=None)[0]
    ry = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
    return corr(ra, ry)


def sim(rows, sign):
    if not len(rows):
        return None
    pnl = sign * np.sign(rows[:, 1]) * rows[:, 3] - rows[:, 6]
    return round(float(pnl.mean()), 3)


def main():
    t0 = time.time()
    ts, cl = load()
    out = {"التصميم": __doc__, "الأطر": {}}
    for fname, m in FRAMES:
        rows = samples(*bucket(ts, cl, m))
        per = {p: rows[(rows[:, 0] >= a) & (rows[:, 0] < b)] for p, a, b in PERIODS}
        build = per["بناء"]
        sgn_m = 1 if (corr(build[:, 1], build[:, 3]) or 0) >= 0 else -1
        sgn_a = 1 if (partial(build[:, 2], build[:, 1], build[:, 3]) or 0) >= 0 else -1
        vmed, emed = float(np.median(build[:, 4])), float(np.median(build[:, 5]))
        res = {"إشارة_الزخم_من_البناء": sgn_m, "إشارة_التسارع_من_البناء": sgn_a, "الفترات": {}}
        verdict = {}
        for p, r in per.items():
            n = len(r)
            band = 2 / math.sqrt(n) if n else None
            cM, pA = corr(r[:, 1], r[:, 3]), partial(r[:, 2], r[:, 1], r[:, 3])
            cells = {}
            for cname, mask in (("تقلّب عالٍ", r[:, 4] > vmed), ("تقلّب منخفض", r[:, 4] <= vmed),
                                ("اتّجاه", r[:, 5] > emed), ("تذبذب", r[:, 5] <= emed)):
                s = r[mask]
                cs = corr(s[:, 1], s[:, 3])
                cells[cname] = {"عدد": int(len(s)), "ارتباط": None if cs is None else round(cs, 4),
                                "نطاق": round(2 / math.sqrt(len(s)), 4) if len(s) else None, "محاكاة_بعد_التكلفة": sim(s, sgn_m)}
            res["الفترات"][p] = {"عدد": n, "ارتباط_الزخم": None if cM is None else round(cM, 4), "نطاق": None if band is None else round(band, 4),
                                 "جزئيّ_التسارع": None if pA is None else round(pA, 4), "محاكاة_بعد_التكلفة": sim(r, sgn_m),
                                 "الانجراف": round(float(r[:, 3].mean()), 3) if n else None, "التكلفة": round(float(r[:, 6].mean()), 3) if n else None,
                                 "الحالات": cells}
            if p == "امتحان":
                verdict["الزخم"] = bool(cM is not None and sgn_m * cM > band and (sim(r, sgn_m) or -1) > 0)
                verdict["التسارع"] = bool(pA is not None and sgn_a * pA > band)
                for cname, c in cells.items():
                    verdict["الحال: " + cname] = bool(c["ارتباط"] is not None and sgn_m * c["ارتباط"] > c["نطاق"]
                                                      and (c["محاكاة_بعد_التكلفة"] or -1) > 0)
        res["الحكم"] = {k: ("يضيف" if v else "لا يضيف") for k, v in verdict.items()}
        out["الأطر"][fname] = res
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "momentum_tests.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# الزخم والتسارع على الناسداك — المحاولة الثالثة لفكرة الزخم (٢٤ اختبارًا مُعلَنًا، ١٠-١٣)", "",
         "نافذةٌ ثابتة 10 شمعات، أفقٌ 5، بناء 2014–2019 · امتحان 2020–2024 (الحكم) · 2025–2026 ملموسة. المحاكاة والانجراف والتكلفة بنقطة الأساس للصفقة.", ""]
    for fname, res in out["الأطر"].items():
        L += ["## %s — إشارة الزخم من البناء %s · التسارع %s" % (fname, res["إشارة_الزخم_من_البناء"], res["إشارة_التسارع_من_البناء"]), "",
              "**الحكم:** " + " · ".join("%s: %s" % kv for kv in res["الحكم"].items()), "",
              "| الفترة | عدد | ارتباط الزخم (نطاق) | جزئيّ التسارع | محاكاة بعد التكلفة | الانجراف | التكلفة |", "|---|---|---|---|---|---|---|"]
        for p, r in res["الفترات"].items():
            L.append("| %s | %s | %s (±%s) | %s | %s | %s | %s |" % (p, r["عدد"], r["ارتباط_الزخم"], r["نطاق"], r["جزئيّ_التسارع"],
                                                              r["محاكاة_بعد_التكلفة"], r["الانجراف"], r["التكلفة"]))
        L += ["", "| الفترة · الحال | عدد | ارتباط (نطاق) | محاكاة بعد التكلفة |", "|---|---|---|---|"]
        for p, r in res["الفترات"].items():
            for cname, c in r["الحالات"].items():
                L.append("| %s · %s | %s | %s (±%s) | %s |" % (p, cname, c["عدد"], c["ارتباط"], c["نطاق"], c["محاكاة_بعد_التكلفة"]))
        L.append("")
    L.append("المدّة: %s ث." % out["المدّة_ث"])
    open(os.path.join(HERE, "الزخم والتسارع.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("انتهى", out["المدّة_ث"], "ث", flush=True)


if __name__ == "__main__":
    main()
