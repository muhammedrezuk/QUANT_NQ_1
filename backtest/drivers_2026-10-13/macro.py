# -*- coding: utf-8 -*-
"""ما يحرّك الناسداك يومًا بيوم — الفائدة · الدولار · الخوف · الشركات الكبرى (المالك ١٠-١٣: «كمّل»).
المحاولة الأولى للعائد والدولار والخوف، والثانية للشركات الكبرى (الأولى: 5 دقائق، لا تقود). عدد الاختبارات مُعلَن: 5 × 2 = 10.

البيانات: الناسداك والشركات يوميًّا من ميتاتريدر (mt5_bars.db، إغلاق يوم الخادم ≈ 17:00 نيويورك) · عائد العشر سنين ومؤشّر الدولار الواسع
ومؤشّر الخوف من الاحتياطيّ الفيدراليّ (fed/). المحاذاة بالتاريخ؛ المؤشّر معلومٌ عند إغلاق يوم t، والهدف بعده (لا نظر إلى المستقبل).
المؤشّرات (تغيّر يوم t): ① العائد (نقطة أساس) ② الدولار (٪) ③ الخوف (نقاط) ④ سلّة الشركات (متوسّط عوائد أبل · مايكروسوفت · إنفيديا ·
أمازون · جوجل · برودكوم · تسلا المتوفّرة) ⑤ فجوة السلّة − الناسداك.
الأهداف: عائد الناسداك غدًا (t ⟵ t+1)، وأسبوعيًّا (تغيّر الأسبوع ⟵ الأسبوع التالي، بلا تداخل).
الفترات: بناء 2012-08 ⟵ 2021 · امتحان 2022 ⟵ 2024 · معزول 2025 ⟵ 2026.
الحكم (مكتوبٌ قبل النتائج): لكلّ مؤشّرٍ وأفق تُؤخذ **إشارة الارتباط من البناء وحده**؛ «يصمد» إن كان في الامتحان **بالإشارة نفسها وخارج
الصدفة** (±2/√ن)، وفي المعزول بالإشارة نفسها. ومعه للاطّلاع: محاكاة «اتّبع الإشارة» يومًا بيوم بتكلفة سبريد نقطة (بلا تمويل الليلة). قياسٌ فقط.
"""
import calendar
import csv
import json
import math
import os
import sqlite3
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run_macro.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
STOCKS = ("AAPL.NAS", "MSFT.NAS", "NVDA.NAS", "AMZN.NAS", "GOOG.NAS", "AVGO.NAS", "TSLA.NAS")
PERIODS = (("بناء", "2012-08-01", "2022-01-01"), ("امتحان", "2022-01-01", "2025-01-01"), ("معزول", "2025-01-01", "2099-01-01"))
SPREAD_PTS = 1.0


def mt5_daily(con, s):
    out = {}
    for t, c in con.execute("select t, close from daily where symbol=? order by t", (s,)):
        out[time.strftime("%Y-%m-%d", time.gmtime(t))] = c
    return out


def fed(name):
    out = {}
    with open(os.path.join(HERE, "fed", name + ".csv"), encoding="utf-8") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            try:
                out[row[0]] = float(row[1])
            except (ValueError, IndexError):
                continue
    return out


def corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 30 or x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def main():
    t0 = time.time()
    con = sqlite3.connect(os.path.join(HERE, "mt5_bars.db"))
    nq = mt5_daily(con, "USTEC")
    stocks = {s: mt5_daily(con, s) for s in STOCKS}
    y10, usd, vix = fed("DGS10"), fed("DTWEXBGS"), fed("VIXCLS")
    days = sorted(nq)
    rows = []                      # (التاريخ، المؤشّرات الخمسة، عائد الناسداك اليوم، عائد الغد)
    for i in range(1, len(days) - 1):
        d0, d1, d2 = days[i - 1], days[i], days[i + 1]
        r_now = math.log(nq[d1] / nq[d0]) * 1e4
        r_next = math.log(nq[d2] / nq[d1]) * 1e4
        def chg(series, scale, log=False):
            if d1 in series and d0 in series:
                return (math.log(series[d1] / series[d0]) if log else series[d1] - series[d0]) * scale
            return None
        sr = [math.log(st[d1] / st[d0]) * 1e4 for st in stocks.values() if d1 in st and d0 in st]
        basket = float(np.mean(sr)) if len(sr) >= 4 else None
        rows.append((d1, chg(y10, 100), chg(usd, 100, True), chg(vix, 1), basket,
                     None if basket is None else basket - r_now, r_now, r_next, nq[d1]))
    names = ("العائد", "الدولار", "الخوف", "السلّة", "فجوة السلّة")
    out = {"التصميم": __doc__, "أيّام": len(rows), "من": rows[0][0], "إلى": rows[-1][0], "النتائج": {}}
    # أسبوعيّ: تجميع الأيّام في أسابيع (سنة-أسبوع ISO)، المؤشّر مجموع الأسبوع، الهدف عائد الأسبوع التالي.
    weeks = {}
    for row in rows:
        y, w, _ = time.strptime(row[0], "%Y-%m-%d").tm_year, None, None
        import datetime as _dt
        iso = _dt.date.fromisoformat(row[0]).isocalendar()
        weeks.setdefault((iso[0], iso[1]), []).append(row)
    wk = sorted(weeks)
    wrows = []
    for a, b in zip(wk[:-1], wk[1:]):
        A, B = weeks[a], weeks[b]
        feats = []
        for j in range(1, 6):
            v = [r[j] for r in A if r[j] is not None]
            feats.append(sum(v) if len(v) >= 3 else None)
        wrows.append((A[-1][0], *feats, sum(r[6] for r in A), sum(r[6] for r in B), A[-1][8]))
    for horizon, data in (("الغد", rows), ("الأسبوع التالي", wrows)):
        res = {}
        for j, name in enumerate(names, start=1):
            per = {}
            sign = None
            for pname, a, b in PERIODS:
                pts = [(r[j], r[7]) for r in data if a <= r[0] < b and r[j] is not None]
                c = corr([p[0] for p in pts], [p[1] for p in pts])
                n = len(pts)
                per[pname] = {"عدد": n, "ارتباط": None if c is None else round(c, 4), "نطاق": round(2 / math.sqrt(n), 4) if n else None}
                if pname == "بناء" and c is not None:
                    sign = 1 if c > 0 else -1
                if sign and c is not None and n:      # محاكاة اتّباع الإشارة
                    cost = [SPREAD_PTS / r[8] * 1e4 for r in data if a <= r[0] < b and r[j] is not None]
                    pnl = np.array([sign * np.sign(p[0]) * p[1] for p in pts]) - np.array(cost)
                    per[pname]["محاكاة_متوسّط_ن.أ"] = round(float(pnl.mean()), 2)
                    per[pname]["محاكاة_المجموع_ن.أ"] = round(float(pnl.sum()), 0)
            t, h = per["امتحان"], per["معزول"]
            holds = (sign is not None and t["ارتباط"] is not None and h["ارتباط"] is not None and
                     sign * t["ارتباط"] > t["نطاق"] and sign * h["ارتباط"] > 0)
            per["إشارة_البناء"] = sign
            per["الحكم"] = "يصمد" if holds else "لا يصمد"
            res[name] = per
        ctrl = {}
        for pname, a, b in PERIODS:
            pts = [(r[6], r[7]) for r in data if a <= r[0] < b]
            ctrl[pname] = corr([p[0] for p in pts], [p[1] for p in pts])
        res["مرجع: الناسداك بماضيه"] = {k: (round(v, 4) if v is not None else None) for k, v in ctrl.items()}
        out["النتائج"][horizon] = res
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "macro.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# ما يحرّك الناسداك يومًا بيوم — الفائدة · الدولار · الخوف · الشركات (١٠-١٣)", "",
         "أيّام %d من %s إلى %s. الحكم لكلّ مؤشّر: إشارته من البناء، ويصمد إن تكرّرت في الامتحان خارج الصدفة وفي المعزول. "
         "المحاكاة: اتّباع الإشارة بتكلفة سبريد، بنقطة الأساس لكلّ صفقة (بلا تمويل الليلة)." % (out["أيّام"], out["من"], out["إلى"]), ""]
    for horizon, res in out["النتائج"].items():
        L += ["## %s" % horizon, "", "| المؤشّر | إشارة البناء | بناء | امتحان (نطاق) | معزول | محاكاة امتحان / معزول | الحكم |", "|---|---|---|---|---|---|---|"]
        for name in names:
            p = res[name]
            L.append("| %s | %s | %s | %s (±%s) | %s | %s / %s | %s |" % (
                name, p["إشارة_البناء"], p["بناء"]["ارتباط"], p["امتحان"]["ارتباط"], p["امتحان"]["نطاق"], p["معزول"]["ارتباط"],
                p["امتحان"].get("محاكاة_متوسّط_ن.أ"), p["معزول"].get("محاكاة_متوسّط_ن.أ"), p["الحكم"]))
        L += ["", "مرجع — الناسداك بماضيه: " + json.dumps(res["مرجع: الناسداك بماضيه"], ensure_ascii=False), ""]
    L.append("المدّة: %s ث." % out["المدّة_ث"])
    open(os.path.join(HERE, "ما يحرّك الناسداك.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("انتهى", out["المدّة_ث"], "ث", flush=True)


if __name__ == "__main__":
    main()
