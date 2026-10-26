# -*- coding: utf-8 -*-
"""أحمر فوركس فاكتوري للدولار — كم يمشي الناسداك مع الخبر قبل أن ينعكس؟ النسخة الثانية (ختم المالك «nq» ٢٠٢٦-١٠-١٣)

ما تغيّر عن الأولى (بأمر المالك وصوره): الأخبار = أحمر فوركس فاكتوري وحده (لا قوّة ميتاتريدر 3 التي أدخلت أيه دي بي وغيره) ·
الجهة بطريقتين: مقابل المتوقّع (كما قرأ السوق نفقات الاستهلاك 30-09) ومقابل السابق · الأخبار الكبيرة وحدها ثمّ كلّها ·
انعكاسٌ حتّى 1٪ وبكسر البنية (لا يقطع تراجعٌ صغير حركةً أكملت بعده، كيوم الاثنين بعد وظائف 10-02).

التصميم ثابتٌ قبل النتائج:
- «مقابل المتوقّع»: مكوّنات events.json (قياس ١٠-٠٩: تقويم ناسداك 2014–2024 + الجسر سنتان) لأنواع الأحمر التي لها إجماع:
  الوظائف · البطالة (معكوسة) · التضخّم والأساسيّ · المنتجين والأساسيّ · التجزئة والأساسيّة · نفقات الاستهلاك الأساسيّة · الناتج · الفائدة.
  المفاجأة s > 0 = إيجابيّ للدولار = سلبيّ للناسداك. «كبير» = |z| ≥ 1 لأيّ مكوّن في المجموعة.
- «مقابل السابق»: ميتاتريدر (الوقت = الخادم − 3 س): الأنواع نفسها + الأجر بالساعة + التضخّم السنويّ، الفعليّ مقابل السابق المعدَّل إن وُجد.
  «كبير» = |التغيّر| ≥ انحرافه المعياريّ على 2014–2019 لذلك النوع.
- بلا رقم (بيان الفيدراليّ · مؤتمره · محضره · توقّعاته · خطاب الرئيس): حجم الحركة وحده.
- الأخبار في الدقيقة نفسها تُجمع إشاراتها، والغالبة جهتها؛ التعادل يُترك.
- الدخول +15 د. المشي = أبعد تقدّمٍ في الجهة قبل الانعكاس، حتّى 10 أيّام تداول. الانعكاس: رجوع 0.25٪ · 0.5٪ · 1٪ من أبعد نقطة،
  و«البنية» = إغلاق ساعةٍ وراء أدنى/أعلى الساعات الثلاث قبلها (ومنها ثلاث ساعات قبل الدخول).
- المقارنة: مع الخبر − ضدّه من الدخول نفسه، واحتمال الحظّ بقلب الإشارة 2000 مرّة؛ ومرجعٌ بلا خبر (الساعة نفسها قبل أسبوع).
- الحكم الرئيس (قبل النتائج): «مقابل المتوقّع» · كلّ الأحمر · رجوع 0.5٪ — «يمشي مع الخبر» إن كان الفرق موجبًا بحظٍّ < 0.05 في
  2020–2024 وموجبًا في 2025–2026؛ وإلّا «لا يمشي مع الخبر أكثر من الصدفة». الباقي ثانويّ (مقارناتٌ كثيرة).
قياسٌ فقط. NEWS_RED2_QUICK=1 تجربةٌ قصيرة.
"""
import collections
import importlib.util
import json
import os
import sqlite3
import sys
import time

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["NEWS_RED_QUICK"] = os.environ.get("NEWS_RED2_QUICK", "")
_spec = importlib.util.spec_from_file_location("nr", os.path.join(HERE, "..", "news_red_2026-10-12", "news_red.py"))
nr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nr)
QUICK = nr.QUICK
EVENTS = os.path.join(HERE, "..", "news_surprise_2026-10-09", "events.json")
EXPECTED = {"Nonfarm Payrolls": 1, "Unemployment Rate": -1, "CPI": 1, "Core CPI": 1, "PPI": 1, "Core PPI": 1,
            "Retail Sales": 1, "Core Retail Sales": 1, "Core PCE Price Index": 1, "GDP": 1, "Fed Interest Rate Decision": 1}
PREVIOUS = {"قوائم الرواتب غير الزراعية": 1, "معدل البطالة": -1, "متوسط الدخل بالساعة على أساس أساس شهري": 1,
            "مؤشر اسعار المستهلك على أساس شهري": 1, "مؤشر أسعار المستهلك على أساس سنوي": 1,
            "مؤشر أسعار المستهلك الأساسي على أساس شهري": 1, "مؤشر أسعار المنتجين على أساس شهري": 1,
            "مؤشر أسعار المنتجين الأساسيين على أساس شهري": 1, "مبيعات التجزئة على أساس شهري": 1,
            "مبيعات التجزئة الأساسية على أساس شهري": 1, "مؤشر سعر نفقات الاستهلاك الشخصي الأساسي على أساس شهري": 1,
            "الناتج الإجمالي المحلي على أساس ربع سنوي": 1, "قرار سعر فائدة بنك الإحتياطي الفيدرالي": 1}
NO_NUMBER = {"بيان اللجنة الفيدرالية للسوق المفتوحة", "المؤتمر الصحفي للجنة السوق الفيدرالية المفتوحة",
             "محضر اجتماع اللجنة الفيدرالية للسوق المفتوحة", "التوقعات الاقتصادية للجنة الفيدرالية للسوق المفتوحة",
             "خطاب بويل رئيس مجلس بنك الاحتياطي الفيدرالي", "خطاب يلين رئيس بنك الإحتياطي الفيدرالي"}
BIG_Z = 1.0
RS = (0.0025, 0.005, 0.01, "بنية")
MAIN = ("مقابل المتوقّع", "كلّ الأحمر", 0.005)
STRUCT_HOURS = 3
H = 60
LEARN_END = nr.PERIODS[1][1]


def expected_groups():
    ev = json.load(open(EVENTS, encoding="utf-8"))
    g = collections.defaultdict(lambda: {"votes": [], "names": set(), "big": False})
    for c in ev["components"]:
        sign = EXPECTED.get(c.get("comp"))
        if sign is None or c.get("s") is None:
            continue
        x = g[float(c["T"])]
        x["names"].add(c["comp"])
        if c["s"] == 0:
            continue
        x["votes"].append(-sign * (1 if c["s"] > 0 else -1))
        if c.get("z") is not None and abs(c["z"]) >= BIG_Z:
            x["big"] = True
    return g


def previous_groups():
    con = sqlite3.connect(nr.CAL, uri=True)
    rows = con.execute("select event_name, time_server, actual, prev, revised_prev from calendar_history "
                       "where currency='USD'").fetchall()
    con.close()
    deltas = collections.defaultdict(list)
    for name, ts, act, prev, rprev in rows:
        ref = rprev if rprev is not None else prev
        name = name.strip()
        if name in PREVIOUS and act is not None and ref is not None and ts - nr.CAL_OFFSET_S < LEARN_END:
            deltas[name].append(act - ref)
    scale = {n: float(np.std(v)) for n, v in deltas.items() if len(v) >= 8}
    g = collections.defaultdict(lambda: {"votes": [], "names": set(), "big": False, "speech": False})
    for name, ts, act, prev, rprev in rows:
        name = name.strip()
        t = float(ts) - nr.CAL_OFFSET_S
        if name in NO_NUMBER:
            g[t]["speech"] = True
            g[t]["names"].add(name)
            continue
        sign = PREVIOUS.get(name)
        ref = rprev if rprev is not None else prev
        if sign is None or act is None:
            continue
        x = g[t]
        x["names"].add(name)
        if ref is None or act == ref:
            continue
        x["votes"].append(-sign * (1 if act > ref else -1))
        if scale.get(name) and abs(act - ref) >= scale[name]:
            x["big"] = True
    return g


def walk_struct(hi, lo, cl, i, d):
    """أبعد تقدّمٍ قبل إغلاق ساعةٍ وراء أدنى (للشراء) الساعات الثلاث قبلها؛ تبدأ البنية بثلاث ساعاتٍ قبل الدخول."""
    a = i + 1 - STRUCT_HOURS * H
    b = min(len(cl), i + 1 + nr.HOLD_BARS)
    if a < 0:
        return None
    n = (b - a) // H
    if n <= STRUCT_HOURS:
        return None
    hh = hi[a:a + n * H].reshape(n, H).max(1)
    ll = lo[a:a + n * H].reshape(n, H).min(1)
    hc = cl[a:a + n * H].reshape(n, H)[:, -1]
    p0 = float(cl[i])
    if d < 0:
        hh, ll, hc, p0 = -ll, -hh, -hc, -p0
    for k in range(STRUCT_HOURS, n):
        if hc[k] < ll[k - STRUCT_HOURS:k].min():
            return (max(p0, float(hh[STRUCT_HOURS:k + 1].max())) - p0) / abs(p0) * 1e4, (k - STRUCT_HOURS + 1) * H
    return (max(p0, float(hh[STRUCT_HOURS:].max())) - p0) / abs(p0) * 1e4, (n - STRUCT_HOURS) * H


def walks(hi, lo, cl, i, d):
    sl = slice(i + 1, min(len(cl), i + 1 + nr.HOLD_BARS))
    p0 = float(cl[i])
    out = {}
    for r in RS:
        if r == "بنية":
            w, o = walk_struct(hi, lo, cl, i, d), walk_struct(hi, lo, cl, i, -d)
            if w is None or o is None:
                return None
            out[r] = (w[0], o[0], w[1])
        else:
            w = nr.walk(hi[sl], lo[sl], p0, d, r)
            out[r] = (w[0], nr.walk(hi[sl], lo[sl], p0, -d, r)[0], w[1])
    return out


def build(groups, ts, hi, lo, cl, news_times):
    rows, speeches, mixed = [], [], 0
    for t, g in sorted(groups.items()):
        if not (ts[0] <= t <= ts[-1]):
            continue
        i = nr.at_index(ts, t + nr.ENTRY_DELAY)
        if i is None or i + 2 >= len(ts):
            continue
        net = sum(g["votes"])
        if not g["votes"]:
            if g.get("speech"):
                w = walks(hi, lo, cl, i, 1)
                if w:
                    speeches.append({r: max(w[r][0], w[r][1]) for r in RS})
            continue
        if net == 0:
            mixed += 1
            continue
        d = 1 if net > 0 else -1
        w = walks(hi, lo, cl, i, d)
        if w is None:
            continue
        row = {"t": t, "per": nr.period_of(t), "year": time.gmtime(t).tm_year, "big": g["big"],
               "names": sorted(g["names"]), "w": w}
        tb = t - 7 * nr.DAY
        k = int(np.searchsorted(news_times, tb - nr.DAY / 2))
        if not (k < len(news_times) and news_times[k] <= tb + nr.DAY / 2):
            j = nr.at_index(ts, tb + nr.ENTRY_DELAY)
            if j is not None and j + 2 < len(ts):
                b = walks(hi, lo, cl, j, 1)
                if b:
                    row["base"] = {r: (b[r][0] + b[r][1]) / 2 for r in RS}
        rows.append(row)
    return rows, speeches, mixed


def stats(sub, r, rng):
    if len(sub) < 10:
        return {"n": len(sub)}
    w = np.array([x["w"][r][0] for x in sub])
    o = np.array([x["w"][r][1] for x in sub])
    base = [x["base"][r] for x in sub if "base" in x]
    return {"n": len(sub), "مع": round(float(w.mean()), 1), "ضدّ": round(float(o.mean()), 1),
            "الفرق": round(float((w - o).mean()), 1), "الحظّ": round(nr.sign_flip_p(w - o, rng), 4),
            "مع_أبعد": round(float(np.mean(w > o)), 3), "دقائق": int(np.median([x["w"][r][2] for x in sub])),
            "مرجع": round(float(np.mean(base)), 1) if base else None}


def main():
    t0 = time.time()
    ts, hi, lo, cl = nr.load_prices()
    rng = np.random.default_rng(7)
    out = {"التصميم": __doc__, "النسخ": {}}
    for vname, groups in (("مقابل المتوقّع", expected_groups()), ("مقابل السابق", previous_groups())):
        news_times = np.array(sorted(groups))
        rows, speeches, mixed = build(groups, ts, hi, lo, cl, news_times)
        v = {"مجموعات": len(rows), "كبيرة": sum(x["big"] for x in rows), "مختلطة": mixed, "بلا_رقم": len(speeches),
             "النتائج": {}}
        for fname, flt in (("كلّ الأحمر", lambda x: True), ("الكبيرة وحدها", lambda x: x["big"])):
            for r in RS:
                key = "%s · %s" % (fname, r if r == "بنية" else "%g%%" % (r * 100))
                res = {per: stats([x for x in rows if flt(x) and x["per"] == per], r, rng) for per, _, _ in nr.PERIODS}
                res["الكلّ"] = stats([x for x in rows if flt(x)], r, rng)
                yrs = collections.defaultdict(list)
                for x in rows:
                    if flt(x):
                        yrs[x["year"]].append(x["w"][r][0] - x["w"][r][1])
                res["سنةً_سنة"] = {y: round(float(np.mean(a)), 1) for y, a in sorted(yrs.items()) if len(a) >= 5}
                v["النتائج"][key] = res
        types = collections.defaultdict(list)
        for x in rows:
            for nm in x["names"]:
                types[nm].append(x["w"][0.005][0] - x["w"][0.005][1])
        v["الأنواع_0.5%"] = {nm: {"n": len(a), "الفرق": round(float(np.mean(a)), 1),
                                  "مع_أبعد": round(float(np.mean(np.array(a) > 0)), 3)}
                             for nm, a in sorted(types.items(), key=lambda kv: -len(kv[1]))}
        v["بلا_رقم_أكبر_مشي"] = {str(r): round(float(np.mean([s[r] for s in speeches])), 1) if speeches else None for r in RS}
        out["النسخ"][vname] = v
    m = out["النسخ"][MAIN[0]]["النتائج"]["%s · %g%%" % (MAIN[1], MAIN[2] * 100)]
    test, recent = m.get("2020–2024", {}), m.get("2025–2026", {})
    holds = test.get("الفرق", 0) > 0 and test.get("الحظّ", 1) < 0.05 and recent.get("الفرق", 0) > 0
    out["الحكم"] = "يمشي مع الخبر" if holds else "لا يمشي مع الخبر أكثر من الصدفة"
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "results_quick.json" if QUICK else "results.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    if not QUICK:
        report(out)
    print("الحكم:", out["الحكم"], "|", {k: (v["مجموعات"], v["كبيرة"], v["بلا_رقم"]) for k, v in out["النسخ"].items()},
          "| المدّة:", out["المدّة_ث"], flush=True)


def report(out):
    L = ["# أحمر فوركس فاكتوري للدولار — كم يمشي الناسداك مع الخبر قبل أن ينعكس؟ (النسخة الثانية، ختم «nq» ١٠-١٣)", "",
         "**الحكم الرئيس (مقابل المتوقّع · كلّ الأحمر · رجوع 0.5٪): %s.**" % out["الحكم"], "",
         "الأرقام بنقطة الأساس (100 = 1٪). «مع/ضدّ» = متوسّط أبعد مشيٍ مع جهة الخبر/ضدّها من الدخول نفسه (+15 د) قبل الانعكاس."
         " «الفرق» موجبٌ = يمشي مع الخبر أبعد. «الحظّ» < 0.05 = ليس صدفة. «مرجع» = يومٌ بلا خبر في الساعة نفسها."
         " «بنية» = إغلاق ساعةٍ وراء أدنى/أعلى الساعات الثلاث قبلها.", ""]
    for vname, v in out["النسخ"].items():
        L += ["## %s — مجموعات بجهة %d · كبيرة %d · مختلطة %d · بلا رقم %d" % (
            vname, v["مجموعات"], v["كبيرة"], v["مختلطة"], v["بلا_رقم"]), "",
            "| الاختيار · الانعكاس | الفترة | عدد | مع | ضدّ | الفرق | الحظّ | مع أبعد | دقائق | مرجع |",
            "|---|---|---|---|---|---|---|---|---|---|"]
        for key, res in v["النتائج"].items():
            for per in [p for p, _, _ in nr.PERIODS] + ["الكلّ"]:
                r = res[per]
                L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                    key, per, r["n"], r.get("مع", "—"), r.get("ضدّ", "—"), r.get("الفرق", "—"), r.get("الحظّ", "—"),
                    r.get("مع_أبعد", "—"), r.get("دقائق", "—"), r.get("مرجع", "—")))
            L.append("| %s | سنةً سنة | %s | | | | | | | |" % (key, " · ".join("%s: %s" % kv for kv in res["سنةً_سنة"].items())))
        L += ["", "**الأنواع عند رجوع 0.5٪ (استكشافيّ):** " + " · ".join(
            "%s (%d): %s / %s" % (nm, r["n"], r["الفرق"], r["مع_أبعد"]) for nm, r in v["الأنواع_0.5%"].items()), "",
            "**بلا رقم — متوسّط أكبر مشيٍ في أيّ جهة:** " + json.dumps(v["بلا_رقم_أكبر_مشي"], ensure_ascii=False), ""]
    L.append("المدّة: %s ث. الأرقام الكاملة في results.json." % out["المدّة_ث"])
    open(os.path.join(HERE, "التقرير.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
