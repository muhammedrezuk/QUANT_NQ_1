# -*- coding: utf-8 -*-
"""حال الأخبار — هل يسعّر الناسداك نفسه مع جهة الخبر على مدى أيّام حتّى يصدر خبرٌ معاكس؟
(رأي المالك ٢٠٢٦-١٠-١٢: «بعد الصدور: هل السوق يسعّر نفسه مع اتّجاه الخبر على مدى … حتّى يصدر خبرٌ معاكس» — ختم «قيس nq»)

التصميم ثابتٌ قبل النتائج:
- الأحداث: events.json من قياس ١٠-٠٩ (تجمّعات الإصدار بوقتها و z كلّ فئة). الأسعار: دقيقة الناسداك (USTEC M1) من 2014-07-17.
- جهة كلّ فئة تُتعلَّم على 2014-07⟵2019 وحدها: إشارة انحدار العائد على z (≥ 8 مشاهدات). نسختان:
  «فوريّة» (من قبل الإصدار إلى +15 د — جهة ردّ السوق، مثل «تضخّم أسخن ⟸ ناسداك أدنى») و«يوميّة» (من +15 د إلى +1 يوم).
- درجة الخبر = Σ جهة الفئة × z (مقصوصة ±4). معتبرٌ إن |الدرجة| ≥ 1. «الحال» = إشارة آخر خبرٍ معتبر، يبقى حتّى معتبرٍ معاكس.
- الدخول بعد +15 د من الإصدار (شرط المموِّل). الآفاق من الدخول: يوم · 3 أيّام · أسبوع، و«حتّى المعاكس» لكلّ مقطع حال (سقف 30 يومًا).
- المقارنة: متوسّط عائد الناسداك في حال «صاعد» ناقص متوسّطه في حال «هابط» — لا بالصفر (الناسداك يصعد في المتوسّط) —
  واحتمال الحظّ بخلط الجهات 2000 مرّة داخل الفترة نفسها (من جهةٍ واحدة: الفرق ≥ المقيس).
- الفترات: تعلّم (2014-07⟵2019) · اختبار (2020⟵2024-10) · السنتان (قاعدة الجسر).
- الحكم الرئيس (مكتوبٌ قبل النتائج): النسخة «الفوريّة» على أفق «حتّى المعاكس» — «يصمد» إن كان الفرق في الاختبار موجبًا واحتمال
  الحظّ < 0.05، وفي السنتين موجبًا أيضًا؛ وإلّا «لا يصمد». الباقي ثانويّ.
قياسٌ فقط: لا يمسّ الحيّ. NEWS_STATE_QUICK=1 تجربةٌ قصيرة (2018⟵2021، 50 خلطة) للتأكّد أنّ البرنامج يعمل.
"""
import calendar
import json
import os
import sqlite3
import sys
import time

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS = os.path.join(HERE, "..", "news_surprise_2026-10-09", "events.json")
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CATS = ("تضخّم", "وظائف", "مطالبات", "تجزئة", "منتجين", "ناتج", "نفقات", "مصانع", "خدمات", "فائدة")
Z_CLIP, MIN_LEARN, SIG = 4.0, 8, 1.0
MIN, DAY = 60.0, 86400.0
ENTRY_DELAY = 15 * MIN
HORIZONS = (("يوم", DAY), ("3 أيّام", 3 * DAY), ("أسبوع", 7 * DAY))
UNTIL = "حتّى المعاكس"
CAP = 30 * DAY
STALE = 4 * DAY
QUICK = os.environ.get("NEWS_STATE_QUICK") == "1"
PERMS = 50 if QUICK else 2000
LEARN_END = calendar.timegm((2020, 1, 1, 0, 0, 0))
PERIODS = ("تعلّم", "اختبار", "السنتان")
VARIANTS = ("فوريّة", "يوميّة")


def load_prices():
    con = sqlite3.connect(HIST, uri=True)
    sql = "select period_start, close from candles_history where symbol='USTEC' and period='M1'"
    if QUICK:
        sql += " and period_start between %d and %d" % (calendar.timegm((2018, 1, 1, 0, 0, 0)),
                                                         calendar.timegm((2022, 2, 1, 0, 0, 0)))
    a = np.array(con.execute(sql + " order by period_start").fetchall(), dtype=float)
    con.close()
    return a[:, 0], a[:, 1]


def price_at(ts, cl, t):
    """إغلاق آخر دقيقةٍ انتهت عند t أو قبلها؛ لا شيء إن كانت أقدم من أربعة أيّام."""
    i = int(np.searchsorted(ts, t - MIN, side="right")) - 1
    if i < 0 or t - (ts[i] + MIN) > STALE:
        return None
    return float(cl[i])


def bps(p0, p1):
    return None if p0 is None or p1 is None or p0 <= 0 else (p1 / p0 - 1.0) * 1e4


def period_of(c):
    if c["src"] == "سنتان":
        return "السنتان"
    return "تعلّم" if c["T"] < LEARN_END else "اختبار"


def clip(z):
    return max(-Z_CLIP, min(Z_CLIP, float(z)))


def slope_sign(pts):
    if len(pts) < MIN_LEARN:
        return None
    z = np.array([p[0] for p in pts])
    y = np.array([p[1] for p in pts])
    if np.std(z) == 0:
        return None
    s = float(((z - z.mean()) * (y - y.mean())).sum())
    return 1 if s > 0 else -1 if s < 0 else None


def learn_dirs(clusters, ts, cl):
    dirs = {v: {} for v in VARIANTS}
    for cat in CATS:
        inst, day = [], []
        for c in clusters:
            if c["per"] != "تعلّم" or cat not in c["cats"]:
                continue
            z = clip(c["cats"][cat])
            p0, p15 = price_at(ts, cl, c["T"]), price_at(ts, cl, c["T"] + ENTRY_DELAY)
            p1d = price_at(ts, cl, c["T"] + ENTRY_DELAY + DAY)
            r_i, r_d = bps(p0, p15), bps(p15, p1d)
            if r_i is not None:
                inst.append((z, r_i))
            if r_d is not None:
                day.append((z, r_d))
        dirs["فوريّة"][cat] = slope_sign(inst)
        dirs["يوميّة"][cat] = slope_sign(day)
    return dirs


def scored(clusters, d):
    out = []
    for c in clusters:
        s = sum(d[cat] * clip(z) for cat, z in c["cats"].items() if d.get(cat))
        if abs(s) >= SIG:
            out.append((c, 1 if s > 0 else -1, s))
    return out


def fixed_items(sig, ts, cl):
    items = {h: [] for h, _ in HORIZONS}
    for c, side, _ in sig:
        e = c["T"] + ENTRY_DELAY
        p0 = price_at(ts, cl, e)
        for h, dt in HORIZONS:
            r = bps(p0, price_at(ts, cl, e + dt))
            if r is not None:
                items[h].append((c["per"], side, r, time.gmtime(c["T"]).tm_year, dt / DAY))
    return items


def segments(sig, ts, cl):
    """مقاطع الحال: من أوّل خبرٍ معتبر يقلب الحال (+15 د) حتّى قبيل المعتبر المعاكس، بسقف 30 يومًا."""
    out, cur, capped = [], None, 0
    for c, side, _ in sig:
        if cur is not None and side != cur[1]:
            start, end = cur[0]["T"] + ENTRY_DELAY, c["T"]
            if end - start > CAP:
                end, capped = start + CAP, capped + 1
            r = bps(price_at(ts, cl, start), price_at(ts, cl, end))
            if r is not None and end > start:
                out.append((cur[0]["per"], cur[1], r, time.gmtime(cur[0]["T"]).tm_year, (end - start) / DAY))
        if cur is None or side != cur[1]:
            cur = (c, side)
    return out, capped


def compare(items, seed=7):
    up = np.array([r for _, s, r, _, _ in items if s > 0])
    dn = np.array([r for _, s, r, _, _ in items if s < 0])
    res = {"صاعد": int(len(up)), "هابط": int(len(dn))}
    if len(up) < 3 or len(dn) < 3:
        return res
    diff = float(up.mean() - dn.mean())
    sides = np.array([s for _, s, _, _, _ in items])
    rets = np.array([r for _, _, r, _, _ in items])
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(PERMS):
        p = rng.permutation(sides)
        hits += (rets[p > 0].mean() - rets[p < 0].mean()) >= diff
    days = np.array([dd for _, _, _, _, dd in items])
    res.update({"متوسّط_صاعد": round(float(up.mean()), 1), "متوسّط_هابط": round(float(dn.mean()), 1),
                "الفرق": round(diff, 1), "احتمال_الحظّ": round((hits + 1) / (PERMS + 1), 4),
                "إصابة_الجهة": round(float(np.mean(sides * rets > 0)), 3),
                "متوسّط_الأيّام": round(float(days.mean()), 2)})
    return res


def by_year(items):
    years = {}
    for _, s, r, y, _ in items:
        years.setdefault(y, []).append((s, r))
    out, pos, tot = {}, 0, 0
    for y, pts in sorted(years.items()):
        up = [r for s, r in pts if s > 0]
        dn = [r for s, r in pts if s < 0]
        if len(up) >= 3 and len(dn) >= 3:
            d = float(np.mean(up) - np.mean(dn))
            out[y] = round(d, 1)
            tot += 1
            pos += d > 0
    return out, "%d/%d" % (pos, tot)


def main():
    t0 = time.time()
    ev = json.load(open(EVENTS, encoding="utf-8"))
    ts, cl = load_prices()
    clusters = []
    for c in ev["clusters"]:
        if c.get("cats") and ts[0] <= c["T"] <= ts[-1]:
            c["per"] = period_of(c)
            clusters.append(c)
    clusters.sort(key=lambda c: c["T"])
    dirs = learn_dirs(clusters, ts, cl)
    out = {"التصميم": __doc__, "الجهات_المتعلَّمة": dirs, "النسخ": {}}
    for v in VARIANTS:
        sig = scored(clusters, dirs[v])
        items = fixed_items(sig, ts, cl)
        segs, capped = segments(sig, ts, cl)
        items[UNTIL] = segs
        res = {"أخبار_معتبرة": len(sig), "مقاطع": len(segs), "مقاطع_بلغت_السقف": capped, "الآفاق": {}}
        for h, rows in items.items():
            res["الآفاق"][h] = {per: compare([x for x in rows if x[0] == per]) for per in PERIODS}
            res["الآفاق"][h]["سنةً_سنة"] = by_year([x for x in rows if x[0] != "تعلّم"])
        out["النسخ"][v] = res
    main_res = out["النسخ"]["فوريّة"]["الآفاق"][UNTIL]
    test, recent = main_res["اختبار"], main_res["السنتان"]
    holds = (test.get("الفرق", 0) > 0 and test.get("احتمال_الحظّ", 1) < 0.05 and recent.get("الفرق", 0) > 0)
    out["الحكم"] = "يصمد" if holds else "لا يصمد"
    out["المدّة_ث"] = round(time.time() - t0, 1)
    name = "results_quick.json" if QUICK else "results.json"
    json.dump(out, open(os.path.join(HERE, name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not QUICK:
        write_report(out)
    print("الحكم:", out["الحكم"], "| المدّة:", out["المدّة_ث"], "ث | معتبرة:",
          {v: out["النسخ"][v]["أخبار_معتبرة"] for v in VARIANTS}, flush=True)


def write_report(out):
    L = ["# حال الأخبار — التقرير (قياسٌ على الجهاز، ختم المالك «قيس nq» ٢٠٢٦-١٠-١٢)", "",
         "**الحكم الرئيس (النسخة الفوريّة، أفق «حتّى المعاكس»): %s.**" % out["الحكم"], "",
         "السؤال: بعد صدور خبرٍ له جهة (مثل تضخّمٍ أسخن ⟸ دولارٌ أقوى ⟸ ناسداك أدنى)، هل يمشي الناسداك في جهته أيّامًا حتّى يصدر"
         " خبرٌ معاكس؟ الدخول بعد ربع ساعة من الخبر. «الفرق» = متوسّط حركة الناسداك (نقطة أساس، 100 = 1٪) حين الحال صاعد"
         " ناقص متوسّطها حين الحال هابط — موجبٌ يعني أنّ الخبر يوجّه السوق. «احتمال الحظّ» صغيرٌ (< 0.05) يعني أنّه ليس صدفة.", "",
         "الجهات المتعلَّمة على 2014–2019: " + json.dumps(out["الجهات_المتعلَّمة"], ensure_ascii=False), ""]
    for v, res in out["النسخ"].items():
        L += ["## النسخة «%s» — أخبار معتبرة %d · مقاطع حال %d (بلغ السقف %d)" % (
            v, res["أخبار_معتبرة"], res["مقاطع"], res["مقاطع_بلغت_السقف"]), "",
            "| الأفق | الفترة | صاعد/هابط | متوسّط صاعد | متوسّط هابط | الفرق | احتمال الحظّ | إصابة الجهة | أيّام |",
            "|---|---|---|---|---|---|---|---|---|"]
        for h, per_res in res["الآفاق"].items():
            for per in PERIODS:
                r = per_res[per]
                L.append("| %s | %s | %s/%s | %s | %s | %s | %s | %s | %s |" % (
                    h, per, r["صاعد"], r["هابط"], r.get("متوسّط_صاعد", "—"), r.get("متوسّط_هابط", "—"),
                    r.get("الفرق", "—"), r.get("احتمال_الحظّ", "—"), r.get("إصابة_الجهة", "—"), r.get("متوسّط_الأيّام", "—")))
            yrs, frac = per_res["سنةً_سنة"]
            L.append("| %s | سنةً سنة (بعد 2019) | الفرق موجبٌ في %s | %s | | | | | |" % (
                h, frac, " · ".join("%s: %s" % kv for kv in yrs.items())))
        L.append("")
    L.append("المدّة: %s ث. الأرقام الكاملة في results.json." % out["المدّة_ث"])
    open(os.path.join(HERE, "التقرير.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
