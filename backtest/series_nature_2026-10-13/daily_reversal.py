# -*- coding: utf-8 -*-
"""فحص ثبات «ارتداد اليوم التالي» على الناسداك — المحاولة الثانية لهذه الفكرة (الأولى: الوصف في series_nature.py، ارتباطٌ سالب
−0.051 / −0.082 / −0.218 في الحقب الثلاث). قانون «لا خداع بالأرقام» ١٠-١٣: العدد مُعلَن، والحكم مكتوبٌ هنا قبل النتائج.

الفحوص (شموع دقيقة الناسداك 2014-07 ⟵ اليوم):
أ) الارتباط بالترتيب (لا بالقيم) — لا تصنعه أيّامٌ شاذّة.
ب) الارتباط بعد قصّ أطراف 1٪ من كلّ جهة.
ج) حدّا يومٍ مختلفان: منتصف ليل غرينتش، و21:00 غرينتش (قرب إغلاق نيويورك).
د) سنةً سنة: كم سنةً الارتباط فيها سالب.
هـ) محاكاة صفقات: عند إغلاق اليوم، عكس جهته لليوم التالي (صاعد ⟸ بيع، هابط ⟸ شراء)، من إغلاقٍ إلى إغلاق، بتكلفة سبريد 1.5 نقطة؛
   أربع صيغ: كلّ الأيّام / بعد يومٍ «كبير» فقط (|عائده| > انحراف آخر 20 يومًا) × بلا وقف / بوقفٍ = انحراف آخر 20 يومًا (من شموع الدقيقة،
   ومن أوّل سعرٍ إن فتح اليوم وراء الوقف). تمويل الليلة **غير محسوب** (لا رقم مؤكَّد عندنا).

الحكم: «يصمد» إن كان: (أ) سالبًا في الحقب الثلاث · و(ب) سالبًا في الحقب الثلاث · و(ج) سالبًا بالحدّين في الحقب الثلاث · و(هـ) صيغة «بوقف»
لكلّ الأيّام **أو** للكبيرة موجبةَ المتوسّط بعد التكلفة في 2020–2024 وفي 2025–2026. وإلّا «لا يصمد». قياسٌ فقط.
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
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
DAY = 86400
BOUNDS = (("منتصف ليل غرينتش", 0), ("21:00 غرينتش", 3 * 3600))
ERAS = (("2014–2019", 0, calendar.timegm((2020, 1, 1, 0, 0, 0))),
        ("2020–2024", calendar.timegm((2020, 1, 1, 0, 0, 0)), calendar.timegm((2025, 1, 1, 0, 0, 0))),
        ("2025–2026", calendar.timegm((2025, 1, 1, 0, 0, 0)), 1e12))
SPREAD_PTS = 1.5
VOL_DAYS = 20
TRIM = 0.01


def load():
    con = sqlite3.connect(HIST, uri=True)
    a = np.array(con.execute("select period_start, high, low, close from candles_history where symbol='USTEC' and period='M1' "
                             "order by period_start").fetchall(), dtype=float)
    con.close()
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def days(ts, hi, lo, cl, shift):
    d = np.floor((ts + shift) / DAY).astype(np.int64)
    edges = np.r_[0, np.nonzero(np.diff(d))[0] + 1, len(d)]
    T = ts[edges[:-1]]
    C = cl[edges[1:] - 1]
    H = np.maximum.reduceat(hi, edges[:-1])
    L = np.minimum.reduceat(lo, edges[:-1])
    F = cl[edges[:-1]]                       # أوّل سعرٍ في اليوم
    return T, C, H, L, F


def ranks(x):
    o = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[o] = np.arange(len(x))
    return r


def corr(a, b):
    return float(np.corrcoef(a, b)[0, 1]) if len(a) > 30 else None


def sim(T, C, H, L, F, big_only, stop):
    r = np.log(C[1:] / C[:-1]) * 1e4            # r[i] = عائد اليوم i+1
    out = []
    for i in range(VOL_DAYS + 1, len(r)):
        prev = r[i - 1]
        sd = float(np.std(r[i - 1 - VOL_DAYS:i - 1]))
        if prev == 0 or sd == 0 or (big_only and abs(prev) <= sd):
            continue
        side = -1 if prev > 0 else 1
        entry = C[i]
        cost = SPREAD_PTS / entry * 1e4
        pnl = side * r[i]
        if stop:
            dist = entry * sd / 1e4
            day = i + 1
            first, low, high = F[day], L[day], H[day]
            if side > 0 and (first <= entry - dist or low <= entry - dist):
                pnl = (min(first, entry - dist) / entry - 1) * 1e4
            elif side < 0 and (first >= entry + dist or high >= entry + dist):
                pnl = -(max(first, entry + dist) / entry - 1) * 1e4
        out.append((T[i + 1], pnl - cost))
    return out


def summarize(trades, a, b):
    x = np.array([p for t, p in trades if a <= t < b])
    if len(x) < 20:
        return {"صفقات": int(len(x))}
    eq = np.cumsum(x)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    years = {}
    for t, p in trades:
        if a <= t < b:
            years.setdefault(time.gmtime(t).tm_year, []).append(p)
    pos = sum(1 for v in years.values() if sum(v) > 0)
    return {"صفقات": int(len(x)), "متوسّط_بعد_التكلفة": round(float(x.mean()), 2), "إصابة": round(float(np.mean(x > 0)), 3),
            "المجموع": round(float(x.sum()), 0), "أقصى_تراجع": round(dd, 0), "سنوات_رابحة": "%d/%d" % (pos, len(years))}


def main():
    t0 = time.time()
    ts, hi, lo, cl = load()
    out = {"التصميم": __doc__, "الحدود": {}}
    verdict = {"أ": True, "ب": True, "ج": True, "هـ": False}
    for bname, shift in BOUNDS:
        T, C, H, L, F = days(ts, hi, lo, cl, shift)
        r = np.log(C[1:] / C[:-1]) * 1e4
        Tr = T[1:]
        res = {"الارتباطات": {}, "سنةً_سنة": {}, "المحاكاة": {}}
        for era, a, b in ERAS:
            m = (Tr[1:] >= a) & (Tr[1:] < b)
            x, y = r[:-1][m], r[1:][m]
            lo_q, hi_q = np.quantile(r, [TRIM, 1 - TRIM])
            k = (x > lo_q) & (x < hi_q) & (y > lo_q) & (y < hi_q)
            c = {"عدد": int(m.sum()), "بالقيم": corr(x, y), "بالترتيب": corr(ranks(x), ranks(y)), "بعد_قصّ_1٪": corr(x[k], y[k]),
                 "نطاق_الصدفة": round(2 / math.sqrt(max(1, m.sum())), 3)}
            res["الارتباطات"][era] = {kk: (round(v, 3) if isinstance(v, float) else v) for kk, v in c.items()}
            for key, flag in (("بالترتيب", "أ"), ("بعد_قصّ_1٪", "ب"), ("بالقيم", "ج")):
                if not (c[key] is not None and c[key] < 0):
                    verdict[flag] = False
        yrs = {}
        for i in range(1, len(r)):
            yrs.setdefault(time.gmtime(Tr[i]).tm_year, []).append((r[i - 1], r[i]))
        for y, pts in sorted(yrs.items()):
            if len(pts) > 30:
                res["سنةً_سنة"][y] = round(corr(np.array([p[0] for p in pts]), np.array([p[1] for p in pts])), 3)
        for name, big, stop in (("كلّ الأيّام بلا وقف", False, False), ("كلّ الأيّام بوقف", False, True),
                                ("بعد اليوم الكبير بلا وقف", True, False), ("بعد اليوم الكبير بوقف", True, True)):
            trades = sim(T, C, H, L, F, big, stop)
            res["المحاكاة"][name] = {era: summarize(trades, a, b) for era, a, b in ERAS}
            if stop and shift == 0:
                e2, e3 = res["المحاكاة"][name]["2020–2024"], res["المحاكاة"][name]["2025–2026"]
                if e2.get("متوسّط_بعد_التكلفة", -1) > 0 and e3.get("متوسّط_بعد_التكلفة", -1) > 0:
                    verdict["هـ"] = True
        out["الحدود"][bname] = res
    out["الشروط"] = verdict
    out["الحكم"] = "يصمد" if all(verdict.values()) else "لا يصمد"
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "daily_reversal.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report(out)
    print("الحكم:", out["الحكم"], out["الشروط"], "|", out["المدّة_ث"], "ث", flush=True)


def report(out):
    L = ["# ارتداد اليوم التالي — فحص الثبات (المحاولة الثانية لهذه الفكرة، ١٠-١٣)", "",
         "**الحكم: %s.** الشروط: %s" % (out["الحكم"], " · ".join("%s %s" % (k, "✅" if v else "⛔") for k, v in out["الشروط"].items())), "",
         "أ = بالترتيب سالبٌ في الحقب الثلاث · ب = بعد قصّ الأطراف · ج = بحدّي اليوم · هـ = المحاكاة بوقف موجبةٌ في 2020–2024 و2025–2026."
         " الأرباح بنقطة الأساس (100 = 1٪) لكلّ صفقة بعد السبريد، بلا تمويل الليلة.", ""]
    for bname, res in out["الحدود"].items():
        L += ["## حدّ اليوم: %s" % bname, "", "| الحقبة | أيّام | بالقيم | بالترتيب | بعد قصّ 1٪ | نطاق الصدفة |", "|---|---|---|---|---|---|"]
        for era, c in res["الارتباطات"].items():
            L.append("| %s | %s | %s | %s | %s | ±%s |" % (era, c["عدد"], c["بالقيم"], c["بالترتيب"], c["بعد_قصّ_1٪"], c["نطاق_الصدفة"]))
        L += ["", "سنةً سنة (بالقيم): " + " · ".join("%s: %s" % kv for kv in res["سنةً_سنة"].items()), "",
              "| الصيغة | الحقبة | صفقات | متوسّط بعد التكلفة | إصابة | المجموع | أقصى تراجع | سنوات رابحة |", "|---|---|---|---|---|---|---|---|"]
        for name, eras in res["المحاكاة"].items():
            for era, s in eras.items():
                L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (name, era, s["صفقات"], s.get("متوسّط_بعد_التكلفة", "—"),
                                                                    s.get("إصابة", "—"), s.get("المجموع", "—"), s.get("أقصى_تراجع", "—"),
                                                                    s.get("سنوات_رابحة", "—")))
        L.append("")
    L.append("المدّة: %s ث." % out["المدّة_ث"])
    open(os.path.join(HERE, "ارتداد اليوم التالي.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
