# -*- coding: utf-8 -*-
"""(أ) هل للمفاجأة جهةٌ ثابتة؟ — عائد الناسداك بعد الإصدار مقابل z لكلّ فئة: التعلّم · الاختبار · الفترة الأقدم.

الجهة المتعلَّمة لكلّ فئة = إشارة انحدار عائد +15 على z في التعلّم وحده (≥ 8 مشاهدات). المخرج: results_a.json.
"""
import calendar
import json
import math
import os
import sqlite3
import sys
import time

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
START = calendar.timegm(time.strptime("2024-10-01", "%Y-%m-%d"))          # = card_replay.START
END = sqlite3.connect(HIST, uri=True).execute(
    "select max(period_start) from candles_history where symbol='USTEC' and period='M1'").fetchone()[0]   # = card_replay.END
SPLIT = START + 0.7 * (END - START)
HS = ("15", "60", "240", "15-60", "15-240")
CATS = ("تضخّم", "وظائف", "مطالبات", "تجزئة", "منتجين", "ناتج", "نفقات", "مصانع", "خدمات", "فائدة")
MIN_LEARN = 8


def period_of(c):
    if c["src"] == "أقدم":
        return "أقدم"
    return "تعلّم" if c["T"] < SPLIT else ("اختبار" if c["T"] <= END else None)


def ranks(x):
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    xs = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


Z_CLIP = 4.0


def describe(z, y):
    z = np.clip(z, -Z_CLIP, Z_CLIP)          # جائحة 2020: z حتّى 259 — القصّ للارتباط والانحدار (سبيرمان بالرتب لا يتغيّر)
    n = len(z)
    if n < 5 or np.std(z) == 0 or np.std(y) == 0:
        return {"n": n}
    r = float(np.corrcoef(z, y)[0, 1])
    rho = float(np.corrcoef(ranks(z), ranks(y))[0, 1])
    zc = z - z.mean()
    slope = float((zc * (y - y.mean())).sum() / (zc * zc).sum())
    resid = y - y.mean() - slope * zc
    se = math.sqrt((resid ** 2).sum() / max(1, n - 2) / (zc * zc).sum())
    big = np.abs(z) >= 1.0
    al = (np.sign(z[big]) * y[big]) if big.any() else np.array([])
    return {"n": n, "ارتباط": round(r, 3), "سبيرمان": round(rho, 3), "انحدار_ن.أ/z": round(slope, 2),
            "t": round(slope / se, 2) if se > 0 else None,
            "|z|≥1": {"n": int(big.sum()),
                      "متوسّط_في_جهة_z_ن.أ": round(float(al.mean()), 2) if len(al) else None,
                      "نسبة_في_جهة_z": round(float((al > 0).mean()), 2) if len(al) else None}}


def main():
    ev = json.load(open(os.path.join(HERE, "events.json"), encoding="utf-8"))
    cl = ev["clusters"]
    out = {"حدّ_التعلّم": time.strftime("%Y-%m-%d %H:%M", time.gmtime(SPLIT)), "الفئات": {}, "الجهات_المتعلَّمة": {}}
    counts = {}
    for cat in CATS:
        rows = [c for c in cl if cat in c["cats"]]
        res = {}
        for per in ("تعلّم", "اختبار", "أقدم"):
            sub = [c for c in rows if period_of(c) == per]
            res[per] = {"إصدارات_بـz": len(sub)}
            for h in HS:
                pts = [(c["cats"][cat], c["ret"].get(h)) for c in sub if c["ret"].get(h) is not None]
                if pts:
                    z = np.array([p[0] for p in pts]); y = np.array([p[1] for p in pts])
                    res[per][h] = describe(z, y)
        out["الفئات"][cat] = res
        L = res["تعلّم"].get("15", {})
        sign = None
        if L.get("n", 0) >= MIN_LEARN and L.get("انحدار_ن.أ/z") not in (None, 0):
            sign = 1 if L["انحدار_ن.أ/z"] > 0 else -1
        out["الجهات_المتعلَّمة"][cat] = sign
    # عددٌ لكلّ فئة ومصدر (بإجماع / بـz)
    comps = ev["components"]
    tab = {}
    for c in comps:
        k = (c["cat"], "أقدم" if c["src"] == "أقدم" else "سنتان")
        t = tab.setdefault("%s|%s" % k, {"مكوّنات_بإجماع": 0, "مكوّنات_بـz": 0})
        t["مكوّنات_بإجماع"] += 1
        t["مكوّنات_بـz"] += c["z"] is not None
    out["الأعداد"] = tab
    # تجميع: الجهة المتعلَّمة × z لكلّ الفئات معًا — هل تعمّم خارج التعلّم؟
    pooled = {}
    for per in ("تعلّم", "اختبار", "أقدم"):
        pooled[per] = {}
        for h in HS:
            zs, ys = [], []
            for c in cl:
                if period_of(c) != per or c["ret"].get(h) is None:
                    continue
                for cat, zc in c["cats"].items():
                    s = out["الجهات_المتعلَّمة"].get(cat)
                    if s:
                        zs.append(s * zc); ys.append(c["ret"][h])
            if zs:
                pooled[per][h] = describe(np.array(zs), np.array(ys))
    out["مجمّع_بالجهة_المتعلَّمة"] = pooled
    # ثبات الجهة سنةً سنة: إشارة انحدار عائد +15 و(+15⟶+60) على z لكلّ فئة في كلّ سنة (≥ 6 إصدارات)
    years = {}
    for cat in CATS:
        s = out["الجهات_المتعلَّمة"].get(cat)
        per_year = {}
        for c in cl:
            if cat in c["cats"] and period_of(c) is not None:
                y = time.gmtime(c["T"]).tm_year
                per_year.setdefault(y, []).append((c["cats"][cat], c["ret"].get("15"), c["ret"].get("15-60")))
        tab = {}
        agree15 = agree_post = tot = 0
        for y, pts in sorted(per_year.items()):
            pts = [p for p in pts if p[1] is not None and p[2] is not None]
            if len(pts) < 6:
                continue
            z = np.array([p[0] for p in pts])
            d15 = describe(z, np.array([p[1] for p in pts]))
            dp = describe(z, np.array([p[2] for p in pts]))
            b15, bp = d15.get("انحدار_ن.أ/z"), dp.get("انحدار_ن.أ/z")
            tab[y] = {"n": len(pts), "انحدار_15": b15, "انحدار_15⟶60": bp}
            if s and b15 is not None and bp is not None:
                tot += 1
                agree15 += (b15 > 0) == (s > 0)
                agree_post += (bp > 0) == (s > 0)
        years[cat] = {"سنوات": tab, "سنوات_بجهة_متعلَّمة_عند_15": "%d/%d" % (agree15, tot),
                      "سنوات_تستمرّ_فيها_الجهة_15⟶60": "%d/%d" % (agree_post, tot)}
    out["ثبات_الجهة_سنويًّا"] = years
    # استمرار الحركة الأولى: هل يستمرّ ما بعد +15 في جهة الدقائق الخمس عشرة الأولى؟ (كلّ إصدارٍ بـz، أيًّا كانت z)
    cont = {}
    for per in ("تعلّم", "اختبار", "أقدم"):
        cont[per] = {}
        for h in ("15-60", "15-240"):
            v = [math.copysign(1, c["ret"]["15"]) * c["ret"][h] for c in cl if period_of(c) == per and c["cats"]
                 and c["ret"].get("15") and c["ret"].get(h) is not None]
            if v:
                cont[per][h] = {"n": len(v), "متوسّط_ن.أ_في_جهة_الأولى": round(float(np.mean(v)), 2),
                                "نسبة_الاستمرار": round(float(np.mean([x > 0 for x in v])), 3)}
    out["استمرار_الحركة_الأولى"] = cont
    json.dump(out, open(os.path.join(HERE, "results_a.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # ملخّص مطبوع
    for cat in CATS:
        r = out["الفئات"][cat]
        line = []
        for per in ("تعلّم", "اختبار", "أقدم"):
            seg = []
            for h in ("15", "60", "15-60", "15-240"):
                d = r[per].get(h, {})
                seg.append("%s:%s/%s" % (h, d.get("ارتباط"), d.get("انحدار_ن.أ/z")))
            line.append("%s n=%s [%s]" % (per, r[per]["إصدارات_بـz"], " ".join(seg)))
        print("%-8s جهة=%s | %s" % (cat, out["الجهات_المتعلَّمة"][cat], " | ".join(line)), flush=True)
    print(json.dumps(pooled, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
