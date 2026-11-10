# -*- coding: utf-8 -*-
"""الأخبار الحمراء للدولار — كم يمشي الناسداك في جهة الخبر قبل أن ينعكس؟ (المالك ٢٠٢٦-١٠-١٢: «كم يمشي قبل ما يعاكس، إذا مشى ·
كلّ الأخبار المرتبطة بالدولار عالية التأثير · كلّ أخبار لونها أحمر» — ختم «nq»)

التصميم ثابتٌ قبل النتائج:
- الأخبار: تقويم ميتاتريدر المصدَّر، الدولار بالقوّة 3 (الأحمر)، من 2014. الوقت = وقت الخادم − 3 ساعات (تُحقِّق: الوظائف 12:30 صيفًا
  و13:30 شتاءً بغرينتش). يُستبعد مخزون النفط (صلته بالدولار غير واضحة).
- جهة الخبر بمضمونه (قاعدة المالك، لا تُتعلَّم): الفعليّ مقابل السابق (المعدَّل إن وُجد) — أعلى = إيجابيّ للدولار = سلبيّ للناسداك؛
  معكوسة في معدّل البطالة ومطالبات البطالة؛ مساوٍ = بلا جهة. الأخبار في الدقيقة نفسها تُجمع إشاراتها، والغالبة جهتها؛ التعادل «مختلطة».
- بلا رقم (الخطابات والشهادات والمؤتمر الصحفيّ): بلا جهة — يُقاس حجم الحركة وحده.
- الدخول بعد +15 د (شرط المموِّل). المشي: من الدخول، أبعد نقطةٍ في جهة الخبر قبل أن يرجع السعر عنها بمقدار R (0.1٪ · 0.25٪ · 0.5٪
  من سعر الدخول)، بشموع الدقيقة (قمّة/قاع)، حتّى 10 أيّام تداول. «لم يمشِ» = رجع R قبل أيّ تقدّم.
- المقارنة: المشيُ نفسه في الجهة المعاكسة من الدخول نفسه (مزدوجة لكلّ خبر) — الفرق = مشي جهة الخبر − مشي المعاكسة؛ واحتمال الحظّ
  بقلب إشارة الفرق عشوائيًّا 2000 مرّة. ومرجعٌ بلا خبر: الساعة نفسها قبل أسبوع إن خلت من خبرٍ أحمر ±12 ساعة.
- الفترات: 2014-07⟵2019 · 2020⟵2024 · 2025⟵2026، وسنةً سنة. لا شيء يُتعلَّم، فالفترات للثبات.
- الحكم (مكتوبٌ قبل النتائج): عند R = 0.25٪ — «يمشي مع الخبر» إن كان الفرق موجبًا واحتمال الحظّ < 0.05 في 2020–2024، وموجبًا في
  2025–2026؛ وإلّا «لا يمشي مع الخبر أكثر من الصدفة». جدول الأنواع استكشافيّ (مقارناتٌ كثيرة).
قياسٌ فقط: لا يمسّ الحيّ. NEWS_RED_QUICK=1 تجربةٌ قصيرة (2019⟵2021، 50 خلطة).
"""
import calendar
import collections
import json
import os
import sqlite3
import sys
import time

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CAL_OFFSET_S = 3 * 3600
RED = 3
EXCLUDE = {"التغيير في مخزون النفط الخام لإدارة معلومات الطاقة"}
INVERSE = {"معدل البطالة", "مطالبات البطالة الأولية"}
MIN, DAY = 60.0, 86400.0
ENTRY_DELAY = 15 * MIN
HOLD_BARS = 10 * 24 * 60
RS = (0.001, 0.0025, 0.005)
MAIN_R = 0.0025
STALE = 4 * DAY
QUICK = os.environ.get("NEWS_RED_QUICK") == "1"
PERMS = 50 if QUICK else 2000
PERIODS = (("2014–2019", 0, calendar.timegm((2020, 1, 1, 0, 0, 0))),
           ("2020–2024", calendar.timegm((2020, 1, 1, 0, 0, 0)), calendar.timegm((2025, 1, 1, 0, 0, 0))),
           ("2025–2026", calendar.timegm((2025, 1, 1, 0, 0, 0)), 1e12))


def load_prices():
    con = sqlite3.connect(HIST, uri=True)
    sql = "select period_start, high, low, close from candles_history where symbol='USTEC' and period='M1'"
    if QUICK:
        sql += " and period_start between %d and %d" % (calendar.timegm((2019, 1, 1, 0, 0, 0)),
                                                         calendar.timegm((2022, 1, 15, 0, 0, 0)))
    a = np.array(con.execute(sql + " order by period_start").fetchall(), dtype=float)
    con.close()
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def load_news(t_lo, t_hi):
    con = sqlite3.connect(CAL, uri=True)
    rows = con.execute("select event_name, time_server, actual, prev, revised_prev from calendar_history "
                       "where currency='USD' and importance=?", (RED,)).fetchall()
    con.close()
    groups = collections.defaultdict(lambda: {"votes": [], "names": set(), "speech": False})
    for name, ts, act, prev, rprev in rows:
        t = float(ts) - CAL_OFFSET_S
        if name in EXCLUDE or not (t_lo <= t <= t_hi):
            continue
        g = groups[t]
        g["names"].add(name)
        if act is None:
            g["speech"] = True
            continue
        ref = rprev if rprev is not None else prev
        if ref is None or act == ref:
            continue
        usd = 1 if act > ref else -1
        if name in INVERSE:
            usd = -usd
        g["votes"].append((name, -usd))
    return groups


def walk(hi, lo, p0, d, r):
    """أبعد تقدّمٍ (ن.أ) في الجهة d قبل رجوعٍ بمقدار r من أبعد نقطة، ودقائقه، وهل انعكس."""
    if d < 0:
        hi, lo, p0 = -lo, -hi, -p0
    prev_best = np.maximum(p0, np.concatenate(([p0], np.maximum.accumulate(hi)[:-1])))
    hit = np.nonzero(lo <= prev_best - r * abs(p0))[0]
    if len(hit):
        i = int(hit[0])
        return (prev_best[i] - p0) / abs(p0) * 1e4, i, True
    return (max(p0, float(hi.max())) - p0) / abs(p0) * 1e4, len(hi), False


def at_index(ts, t):
    i = int(np.searchsorted(ts, t - MIN, side="right")) - 1
    return None if i < 0 or t - (ts[i] + MIN) > STALE else i


def sign_flip_p(diffs, rng):
    obs = float(np.mean(diffs))
    hits = 0
    for _ in range(PERMS):
        hits += float(np.mean(diffs * rng.choice((-1.0, 1.0), len(diffs)))) >= obs
    return (hits + 1) / (PERMS + 1)


def period_of(t):
    for name, a, b in PERIODS:
        if a <= t < b:
            return name
    return None


def main():
    t0 = time.time()
    ts, hi, lo, cl = load_prices()
    groups = load_news(ts[0], ts[-1])
    news_times = np.array(sorted(groups))
    rng = np.random.default_rng(7)
    rows, speeches, mixed = [], [], 0
    for t, g in sorted(groups.items()):
        i = at_index(ts, t + ENTRY_DELAY)
        if i is None or i + 2 >= len(ts):
            continue
        sl = slice(i + 1, min(len(ts), i + 1 + HOLD_BARS))
        p0 = float(cl[i])
        net = sum(v for _, v in g["votes"])
        if not g["votes"]:
            if g["speech"]:
                speeches.append({r: max(walk(hi[sl], lo[sl], p0, 1, r)[0], walk(hi[sl], lo[sl], p0, -1, r)[0]) for r in RS})
            continue
        if net == 0:
            mixed += 1
            continue
        d = 1 if net > 0 else -1
        row = {"t": t, "per": period_of(t), "year": time.gmtime(t).tm_year, "d": d, "names": sorted(g["names"])}
        for r in RS:
            w, mins, rev = walk(hi[sl], lo[sl], p0, d, r)
            o = walk(hi[sl], lo[sl], p0, -d, r)[0]
            row[r] = {"مع": w, "ضد": o, "دقائق": mins, "انعكس": rev}
        tb = t - 7 * DAY
        k = int(np.searchsorted(news_times, tb - DAY / 2))
        if not (k < len(news_times) and news_times[k] <= tb + DAY / 2):
            j = at_index(ts, tb + ENTRY_DELAY)
            if j is not None and j + 2 < len(ts):
                bs = slice(j + 1, min(len(ts), j + 1 + HOLD_BARS))
                row["مرجع"] = {r: (walk(hi[bs], lo[bs], float(cl[j]), 1, r)[0] + walk(hi[bs], lo[bs], float(cl[j]), -1, r)[0]) / 2
                              for r in RS}
        rows.append(row)
    out = {"التصميم": __doc__, "مجموعات_بجهة": len(rows), "مختلطة": mixed, "خطابات": len(speeches), "النتائج": {}}
    for r in RS:
        res = {}
        for per, _, _ in PERIODS + (("الكلّ", 0, 0),):
            sub = [x for x in rows if per == "الكلّ" or x["per"] == per]
            if len(sub) < 10:
                res[per] = {"n": len(sub)}
                continue
            w = np.array([x[r]["مع"] for x in sub])
            o = np.array([x[r]["ضد"] for x in sub])
            base = [x["مرجع"][r] for x in sub if "مرجع" in x]
            res[per] = {"n": len(sub), "مشي_مع_الخبر": round(float(w.mean()), 1), "مشي_ضدّه": round(float(o.mean()), 1),
                        "الفرق": round(float((w - o).mean()), 1), "احتمال_الحظّ": round(sign_flip_p(w - o, rng), 4),
                        "مع_أبعد_من_ضدّ": round(float(np.mean(w > o)), 3),
                        "لم_يمشِ": round(float(np.mean(w < r * 1e4)), 3),
                        "وسيط_دقائق_المشي": int(np.median([x[r]["دقائق"] for x in sub])),
                        "مرجع_بلا_خبر": round(float(np.mean(base)), 1) if base else None, "مرجع_n": len(base)}
        years = collections.defaultdict(list)
        for x in rows:
            years[x["year"]].append(x[r]["مع"] - x[r]["ضد"])
        res["سنةً_سنة"] = {y: round(float(np.mean(v)), 1) for y, v in sorted(years.items()) if len(v) >= 10}
        out["النتائج"]["%g%%" % (r * 100)] = res
    types = collections.defaultdict(list)
    for x in rows:
        for nm in x["names"]:
            types[nm].append(x[MAIN_R]["مع"] - x[MAIN_R]["ضد"])
    out["الأنواع_عند_0.25%"] = {nm: {"n": len(v), "الفرق": round(float(np.mean(v)), 1),
                                     "مع_أبعد": round(float(np.mean(np.array(v) > 0)), 3)}
                                for nm, v in sorted(types.items(), key=lambda kv: -len(kv[1]))}
    out["الخطابات"] = {"%g%%" % (r * 100): round(float(np.mean([s[r] for s in speeches])), 1) if speeches else None for r in RS}
    main = out["النتائج"]["%g%%" % (MAIN_R * 100)]
    test, recent = main.get("2020–2024", {}), main.get("2025–2026", {})
    holds = test.get("الفرق", 0) > 0 and test.get("احتمال_الحظّ", 1) < 0.05 and recent.get("الفرق", 0) > 0
    out["الحكم"] = "يمشي مع الخبر" if holds else "لا يمشي مع الخبر أكثر من الصدفة"
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "results_quick.json" if QUICK else "results.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    if not QUICK:
        write_report(out)
    print("الحكم:", out["الحكم"], "| مجموعات:", len(rows), "| مختلطة:", mixed, "| خطابات:", len(speeches),
          "| المدّة:", out["المدّة_ث"], flush=True)


def write_report(out):
    L = ["# الأخبار الحمراء للدولار — كم يمشي الناسداك مع الخبر قبل أن ينعكس؟ (قياسٌ على الجهاز، ختم «nq» ٢٠٢٦-١٠-١٢)", "",
         "**الحكم (عند رجوع 0.25٪): %s.**" % out["الحكم"], "",
         "جهة الخبر بقاعدة المالك (إيجابيّ للدولار = سلبيّ للناسداك، الفعليّ مقابل السابق). الدخول بعد ربع ساعة. «المشي» = أبعد ما وصله"
         " السعر قبل أن يرجع بالمقدار المذكور، بنقطة الأساس (100 = 1٪). «الفرق» = المشي مع جهة الخبر − المشي ضدّها من الدخول نفسه:"
         " موجبٌ يعني أنّ السعر يمشي مع الخبر أبعد. «احتمال الحظّ» < 0.05 يعني ليس صدفة. «المرجع» = متوسّط المشي في يومٍ بلا خبر"
         " في الساعة نفسها.", "",
         "مجموعات أخبار بجهة: %d · مختلطة (جهات متعادلة): %d · خطابات بلا رقم: %d" % (out["مجموعات_بجهة"], out["مختلطة"], out["خطابات"]), ""]
    for rk, res in out["النتائج"].items():
        L += ["## الرجوع %s" % rk, "",
              "| الفترة | أخبار | مشي مع الخبر | مشي ضدّه | الفرق | احتمال الحظّ | مع أبعد من ضدّ | لم يمشِ | وسيط الدقائق | مرجع بلا خبر |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for per, r in res.items():
            if per == "سنةً_سنة":
                continue
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                per, r["n"], r.get("مشي_مع_الخبر", "—"), r.get("مشي_ضدّه", "—"), r.get("الفرق", "—"),
                r.get("احتمال_الحظّ", "—"), r.get("مع_أبعد_من_ضدّ", "—"), r.get("لم_يمشِ", "—"),
                r.get("وسيط_دقائق_المشي", "—"), r.get("مرجع_بلا_خبر", "—")))
        L += ["", "الفرق سنةً سنة: " + " · ".join("%s: %s" % kv for kv in res["سنةً_سنة"].items()), ""]
    L += ["## الأنواع عند رجوع 0.25٪ (استكشافيّ)", "", "| الخبر | عدد | الفرق | مع أبعد |", "|---|---|---|---|"]
    for nm, r in out["الأنواع_عند_0.25%"].items():
        L.append("| %s | %d | %s | %s |" % (nm, r["n"], r["الفرق"], r["مع_أبعد"]))
    L += ["", "## الخطابات بلا رقم — متوسّط أكبر مشيٍ في أيّ جهة: " + json.dumps(out["الخطابات"], ensure_ascii=False), "",
          "المدّة: %s ث. الأرقام الكاملة في results.json." % out["المدّة_ث"]]
    open(os.path.join(HERE, "التقرير.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
