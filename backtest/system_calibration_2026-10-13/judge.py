# -*- coding: utf-8 -*-
"""حكم معايرة المنظومة — القواعد مكتوبةٌ هنا قبل أيّ نتيجة (٢٠٢٦-١٠-١٣، ختم المالك «Nq»).

الفترات (الناسداك، شموع الدقيقة من المخزن):
  تسخين      2014-07 ⟵ 2015-12   لا يُحكم عليه.
  البناء     2016-01 ⟵ 2020-12   فيه وحده يُختار العيار.
  الامتحان   2021-01 ⟵ 2025-09   لم تُقَس عليه الاستراتيجيّات السبع (404–410) من قبل — يُحكم عليه مرّةً واحدة.
  المرجع     2025-10 ⟵ اليوم     لُمس (المشي إلى الأمام ١٠-١١/١٢ والمعايرة ١٠-١٠) ⟸ يُعرض للعلم ولا يحكم.
ربح المنظومة = مجموع R لكلّ صفقات الاستراتيجيّات السبع على الإطارات الأربعة بقاعدة الحيّ، بعد الكلفة.

الاختيار (البناء وحده):
  أ) كلّ ذرّة نوافذ (151 152 163 165 201 310 315 358): نوافذها كلّها × 0.25 · 0.5 · 2 · 4 مقابل الحيّ — يُختار الأعلى
     ربحًا للمنظومة، ولا يُقبل غير الحيّ إلّا إن غلب الحيَّ في 4 سنواتٍ من 5 على الأقلّ.
  ب) كلّ عتبةٍ (Z · الارتداد · الكفاءة · طرف المدى · مدى الوقف · الخروج · العوامل): القيم المعلنة مقابل الحيّ على
     الاستراتيجيّات التي تمسّها وحدها — بالقاعدة نفسها.
  ج) العيار المجمَّع = كلّ ما اختير معًا، يُشغَّل مرّةً واحدة على المدى كلّه.
الحكم (الامتحان، مرّةً واحدة — المحاولة الأولى لهذه المعايرة على هذا الجزء):
  يُعتمد المجمَّع إن: ربحه أعلى من الحيّ · وأعلى في 3 سنواتٍ من 5 (2021…2024 و2025 حتّى أيلول) · واختبار الحظّ
  (قلب إشارة فرق كلّ يوم 5000 مرّة) أقلّ من 0.05. وإلّا يبقى الحيّ.
  ويُكتب معه بلا تجميل: هل المجمَّع رابحٌ بذاته (R للصفقة · سنواتٌ موجبة · حظّه مقابل الصفر).
عدد المرشّحين في البناء يُعلن مع النتيجة.

معايرة الزخم وحده (أمر المالك ١٠-١٤ فجرًا: «هات زخم بس نعاير اعداداته بشكل منفصل») — مكتوبةٌ قبل نتائجها:
  الإعداد الوحيد من 152 الذي يدخل صفقة: نافذة صافي الحركة (roc_period، الحيّ 25) — تقرؤها 408 الزخم (زنادًا وعاملًا على الإطار
  الأعلى) و404 الاتّجاه (عاملًا). نافذتا الدفعة والاستمرار لا تقرؤهما أيّ استراتيجيّة ⟸ لا ربح يُقاس لهما.
  المرشّحون 6: 6 · 12 · 18 · 37 · 50 · 100 مقابل 25، كلٌّ في تشغيلٍ مقصورٍ على 404 و408 وذرّاتهما. الهدف: مجموع R لـ404 و408.
  الاختيار على البناء بالقاعدة نفسها (4 من 5)، والحكم مرّةً على الامتحان بالشروط الثلاثة نفسها.

الاستعمال: python judge.py build   ⟵ best.json + «اختيار البناء.md»
           python judge.py momentum ⟵ «تقرير معايرة الزخم.md»
           python judge.py final   ⟵ «تقرير معايرة المنظومة.md»
"""
import csv
import json
import pathlib
import sys
from collections import defaultdict

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
WIN_ATOMS = ("151", "152", "163", "165", "201", "310", "315", "358")
MULTS = ("all×0.25", "all×0.5", "all×2", "all×4")
GROUPS = {
    "Z_TH": ("Z_TH=1.0", "Z_TH=2.0", "Z_TH=2.5"), "PULL_MIN": ("PULL_MIN=0", "PULL_MIN=0.0005", "PULL_MIN=0.001"),
    "RANGE_EFF": ("RANGE_EFF=0.25", "RANGE_EFF=0.5"), "EDGE": ("EDGE=0.15", "EDGE=0.35"),
    "STOP": ("STOP=10-30", "STOP=20-60"), "EXIT": ("EXIT=1R", "EXIT=2R", "EXIT=3R"), "FACTORS": ("FACTORS=off",),
}
AFFECTS = {"Z_TH": ("405", "408"), "PULL_MIN": ("407",), "RANGE_EFF": ("408", "409"), "EDGE": ("409",),
           "STOP": None, "EXIT": None, "FACTORS": ("404", "408", "409")}
LIVE_VAL = {"Z_TH": "1.5", "PULL_MIN": "0.0001", "RANGE_EFF": "0.35", "EDGE": "0.25", "STOP": "15-45", "EXIT": "أثلاث",
            "FACTORS": "تعمل"}
BUILD, TEST, REF = ("2016-01-01", "2020-12-31"), ("2021-01-01", "2025-09-30"), ("2025-10-01", "2099-12-31")
BUILD_YEARS = ("2016", "2017", "2018", "2019", "2020")
TEST_YEARS = ("2021", "2022", "2023", "2024", "2025")
STRATS = ("404", "405", "406", "407", "408", "409", "410")
NAMES = {"404": "الاتّجاه", "405": "الانعكاس", "406": "الاختراق", "407": "الارتداد", "408": "الزخم", "409": "المدى",
         "410": "السيولة"}
AR_ATOM = {"151": "الاتّجاه", "152": "الزخم", "163": "التسارع", "165": "الضوضاء", "201": "القمم والقيعان", "310": "درجة Z",
           "315": "المدى", "358": "هيرست"}
FLIPS = 5000


def load(run):
    """(عيار، استراتيجيّة، يوم) ⟵ [صفقات، مجموع R، رابحة] — الإطارات مجموعة."""
    d = defaultdict(lambda: [0, 0.0, 0])
    with open(OUT / (run.replace(":", "_") + ".csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            a = d[(r["variant"], r["strategy"], r["day"])]
            a[0] += int(r["n"])
            a[1] += float(r["sumR"])
            a[2] += int(r["wins"])
    return d


def days_of(d, variant, strats, span):
    out = defaultdict(lambda: [0, 0.0])
    for (v, s, day), (n, r, _) in d.items():
        if v == variant and (strats is None or s in strats) and span[0] <= day <= span[1]:
            out[day][0] += n
            out[day][1] += r
    return out


def by_year(days):
    y = defaultdict(float)
    for day, (_, r) in days.items():
        y[day[:4]] += r
    return y


def total(days):
    return sum(r for _, r in days.values()), sum(n for n, _ in days.values())


def flip_p(diff, rng):
    """قلب إشارة كلّ يوم: نسبة المرّات التي يبلغ فيها المجموع العشوائيّ المجموعَ المشاهد أو يتجاوزه (جهةٌ واحدة)."""
    x = np.asarray(diff, dtype=float)
    if not len(x):
        return 1.0
    obs = x.sum()
    s = (rng.choice((-1.0, 1.0), size=(FLIPS, len(x))) * x).sum(axis=1)
    return float((s >= obs).mean())


def beats(cand, live, years):
    yc, yl = by_year(cand), by_year(live)
    return sum(1 for y in years if yc.get(y, 0.0) > yl.get(y, 0.0))


def build():
    live = load("live")
    rows, best_atoms, best_th, n_cand = [], {}, [], 0
    base = days_of(live, "live", None, BUILD)
    base_r, base_n = total(base)
    for a in WIN_ATOMS:
        cands = [("live", base)]
        for m in MULTS:
            p = OUT / ("%s_%s.csv" % (a, m))
            if p.exists():
                n_cand += 1
                cands.append((m, days_of(load("%s:%s" % (a, m)), "live", None, BUILD)))
        scored = [(total(dd)[0], tag, dd) for tag, dd in cands]
        scored.sort(key=lambda x: -x[0])
        top_r, top_tag, top_dd = scored[0]
        w = beats(top_dd, base, BUILD_YEARS) if top_tag != "live" else 0
        pick = top_tag if top_tag != "live" and w >= 4 else "live"
        best_atoms[a] = pick
        rows.append(("ذرّة %s %s" % (a, AR_ATOM[a]), ["%s %+.0f" % (t if t != "live" else "الحيّ", r) for r, t, _ in
                                                     sorted(scored, key=lambda x: x[1])], top_tag, w, pick))
    for g, names in GROUPS.items():
        strats = AFFECTS[g]
        b = days_of(live, "live", strats, BUILD)
        cands = [("live", b)] + [(nm, days_of(live, nm, strats, BUILD)) for nm in names]
        n_cand += len(names)
        scored = sorted(((total(dd)[0], tag, dd) for tag, dd in cands), key=lambda x: -x[0])
        top_r, top_tag, top_dd = scored[0]
        w = beats(top_dd, b, BUILD_YEARS) if top_tag != "live" else 0
        pick = top_tag if top_tag != "live" and w >= 4 else "live"
        if pick != "live":
            best_th.append(pick)
        rows.append(("عتبة %s (الحيّ %s)" % (g, LIVE_VAL[g]), ["%s %+.0f" % (t if t != "live" else "الحيّ", r)
                                                              for r, t, _ in sorted(scored, key=lambda x: x[1])], top_tag, w, pick))
    best = {"atoms": {a: t for a, t in best_atoms.items() if t != "live"}, "thresholds": best_th, "candidates": n_cand,
            "build_live_R": round(base_r, 1), "build_live_trades": base_n}
    (HERE / "best.json").write_text(json.dumps(best, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# اختيار البناء (2016–2020) — معايرة المنظومة", "",
         "ربح المنظومة في البناء بالعيار الحيّ: %+.1f R على %d صفقة. المرشّحون: %d." % (base_r, base_n, n_cand), "",
         "| المُعايَر | المرشّحون (مجموع R في البناء) | الأعلى | سنواتٌ غلب فيها الحيّ من 5 | المختار |", "|---|---|---|---|---|"]
    for name, cs, top, w, pick in rows:
        L.append("| %s | %s | %s | %s | **%s** |" % (name, " · ".join(cs), "الحيّ" if top == "live" else top,
                                                     "—" if top == "live" else w, "الحيّ" if pick == "live" else pick))
    (HERE / "اختيار البناء.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return best


def table(d, variant, span, years):
    L = []
    for s in STRATS + (None,):
        dd = days_of(d, variant, None if s is None else (s,), span)
        r, n = total(dd)
        y = by_year(dd)
        pos = sum(1 for k in years if y.get(k, 0.0) > 0)
        L.append((s, n, r, r / n if n else 0.0, pos))
    return L


def final():
    rng = np.random.default_rng(20261013)
    best = json.loads((HERE / "best.json").read_text(encoding="utf-8"))
    live = load("live")
    same = not best["atoms"] and not best["thresholds"]
    cstar = live if same else load("best")
    cv = "live" if same else "best"
    L = ["# تقرير معايرة المنظومة — الناسداك 2014–2026 (ختم «Nq» ٢٠٢٦-١٠-١٣)", "",
         "القواعد كُتبت قبل النتائج (رأس أداة الحكم): الاختيار على البناء 2016–2020 وحده، والحكم مرّةً واحدة على الامتحان "
         "2021-01 ⟵ 2025-09 الذي لم تُقَس عليه الاستراتيجيّات السبع قبل اليوم، والمرجع 2025-10 ⟵ اليوم للعلم.",
         "المرشّحون في البناء: **%d** · هذه **المحاولة الأولى** على الامتحان." % best["candidates"], ""]
    if same:
        L += ["## لم يغلب أيُّ عيارٍ العيارَ الحيّ في البناء بالقاعدة (4 سنواتٍ من 5) ⟸ العيار الحيّ يبقى كما هو.", ""]
    else:
        L += ["## العيار المجمَّع المختار في البناء", ""]
        for a, t in best["atoms"].items():
            L.append("- الذرّة %s %s: نوافذها %s" % (a, AR_ATOM[a], t.replace("all", "كلّها ")))
        for t in best["thresholds"]:
            L.append("- عتبة: %s" % t)
        L.append("")
    tl = days_of(live, "live", None, TEST)
    tc = days_of(cstar, cv, None, TEST)
    rl, nl = total(tl)
    rc, nc = total(tc)
    days = sorted(set(tl) | set(tc))
    diff = [tc.get(d, [0, 0.0])[1] - tl.get(d, [0, 0.0])[1] for d in days]
    w = beats(tc, tl, TEST_YEARS)
    p_diff = flip_p(diff, rng) if not same else 1.0
    p_zero = flip_p([tc[d][1] for d in sorted(tc)], rng)
    adopt = (not same) and rc > rl and w >= 3 and p_diff < 0.05
    L += ["## الحكم على الامتحان (2021-01 ⟵ 2025-09)", "",
          "- الحيّ: %+.1f R على %d صفقة (%+.3f للصفقة)" % (rl, nl, rl / nl if nl else 0),
          "- المجمَّع: %+.1f R على %d صفقة (%+.3f للصفقة)" % (rc, nc, rc / nc if nc else 0)]
    if not same:
        L += ["- غلب الحيَّ في %d سنواتٍ من 5 · حظّ الفرق %.3f" % (w, p_diff),
              "", "**الحكم: %s**" % ("يُعتمد العيار المجمَّع (الشروط الثلاثة تحقّقت)" if adopt else
                                     "لا يُعتمد — العيار الحيّ يبقى (لم تتحقّق الشروط الثلاثة)")]
    yc = by_year(tc)
    L += ["", "**هل %s رابحٌ بذاته على الامتحان؟** %+.3f R للصفقة · سنواتٌ موجبة %d من 5 · حظّه مقابل الصفر %.3f" % (
        "المجمَّع" if not same else "الحيّ", rc / nc if nc else 0, sum(1 for y in TEST_YEARS if yc.get(y, 0) > 0), p_zero), ""]
    for title, d, v in (("العيار الحيّ", live, "live"),) + ((("العيار المجمَّع", cstar, cv),) if not same else ()):
        L += ["### %s — لكلّ استراتيجيّة" % title, "",
              "| الاستراتيجيّة | البناء: صفقات · R للصفقة · سنواتٌ موجبة/5 | الامتحان: صفقات · R للصفقة · موجبة/5 | المرجع: صفقات · R للصفقة |",
              "|---|---|---|---|"]
        b, t, r = table(d, v, BUILD, BUILD_YEARS), table(d, v, TEST, TEST_YEARS), table(d, v, REF, ())
        for (s, bn, br, bpt, bpos), (_, tn, tr_, tpt, tpos), (_, rn, rr, rpt, _) in zip(b, t, r):
            L.append("| %s | %d · %+.3f · %d | %d · %+.3f · %d | %d · %+.3f |" % (
                "المنظومة كلّها" if s is None else "%s %s" % (s, NAMES[s]), bn, bpt, bpos, tn, tpt, tpos, rn, rpt))
        L.append("")
    L += ["## الفروق عن الحيّ (معلنة)", "",
          "- كلّ استراتيجيّة وإطار يُحسب وحده (الحيّ يمنع صفقةً ثانية على الرمز نفسه، وفيه حرّاس قسم 500).",
          "- لا تِكّات قبل 2025 ⟸ الكنس (254) من مسار شمعة الدقيقة: فتح ثمّ أدنى ثمّ أعلى ثمّ إغلاق، أو العكس للهابطة.",
          "- الوقف 15–45 والهامش والكلفة 1.5 نقطة بالنسبة لسعر كلّ يوم (أرقام الحيّ عند وسيط سعر السنة الأخيرة).",
          "- لا مرشّح أخبار.", ""]
    (HERE / "تقرير معايرة المنظومة.md").write_text("\n".join(L), encoding="utf-8")
    return adopt


MOM_VALUES = (6, 12, 18, 37, 50, 100)
MOM_STRATS = ("404", "408")


def momentum():
    rng = np.random.default_rng(20261014)
    runs = {v: load("152:roc_period=%d" % v) for v in (25,) + MOM_VALUES}
    base = days_of(runs[25], "live", MOM_STRATS, BUILD)
    scored = sorted(((total(days_of(d, "live", MOM_STRATS, BUILD))[0], v) for v, d in runs.items()), key=lambda x: -x[0])
    top_r, top_v = scored[0]
    w_b = beats(days_of(runs[top_v], "live", MOM_STRATS, BUILD), base, BUILD_YEARS) if top_v != 25 else 0
    pick = top_v if top_v != 25 and w_b >= 4 else 25
    L = ["# تقرير معايرة الزخم وحده — نافذة صافي الحركة في الذرّة 152 (أمر المالك ١٠-١٤)", "",
         "القواعد كُتبت قبل النتائج (رأس أداة الحكم). الهدف: مجموع R لاستراتيجيّتي الزخم 408 والاتّجاه 404 (الوحيدتين اللتين تقرآن صافي "
         "الحركة) بعد الكلفة. الاختيار على البناء 2016–2020 وحده؛ الامتحان 2021-01 ⟵ 2025-09 مرّةً واحدة. المرشّحون: **6** · المحاولة الأولى.",
         "نافذتا الدفعة والاستمرار لا تدخلان أيّ صفقة اليوم ⟸ لا ربح يُقاس لهما، فلم تُعايَرا.", "",
         "## البناء (2016–2020)", "", "| النافذة | صفقات | مجموع R | R للصفقة | غلب الحيّ (سنوات من 5) |", "|---|---|---|---|---|"]
    for v in (25,) + MOM_VALUES:
        dd = days_of(runs[v], "live", MOM_STRATS, BUILD)
        r, n = total(dd)
        L.append("| %d%s | %d | %+.1f | %+.3f | %s |" % (v, " (الحيّ)" if v == 25 else "", n, r, r / n if n else 0,
                                                    "—" if v == 25 else beats(dd, base, BUILD_YEARS)))
    L += ["", "**المختار بالقاعدة: %d%s**" % (pick, " — لم يغلب أيٌّ الحيَّ في 4 سنواتٍ من 5، فالحيّ يبقى" if pick == 25 else ""), ""]
    tl, tc = days_of(runs[25], "live", MOM_STRATS, TEST), days_of(runs[pick], "live", MOM_STRATS, TEST)
    rl, nl = total(tl)
    rc, nc = total(tc)
    if pick != 25:
        days = sorted(set(tl) | set(tc))
        diff = [tc.get(d, [0, 0.0])[1] - tl.get(d, [0, 0.0])[1] for d in days]
        w, p = beats(tc, tl, TEST_YEARS), flip_p(diff, rng)
        adopt = rc > rl and w >= 3 and p < 0.05
        L += ["## الامتحان (2021-01 ⟵ 2025-09)", "", "- الحيّ 25: %+.1f R على %d صفقة (%+.3f للصفقة)" % (rl, nl, rl / nl if nl else 0),
              "- المختار %d: %+.1f R على %d صفقة (%+.3f للصفقة)" % (pick, rc, nc, rc / nc if nc else 0),
              "- غلب الحيَّ في %d سنواتٍ من 5 · حظّ الفرق %.3f" % (w, p), "",
              "**الحكم: %s**" % ("تُعتمد النافذة %d (الشروط الثلاثة تحقّقت)" % pick if adopt else "لا تُعتمد — النافذة 25 تبقى"), ""]
    yc = by_year(tc)
    L += ["**هل الزخم بالنافذة %d رابحٌ بذاته على الامتحان؟** %+.3f R للصفقة · سنواتٌ موجبة %d من 5 · حظّه مقابل الصفر %.3f" % (
        pick, rc / nc if nc else 0, sum(1 for y in TEST_YEARS if yc.get(y, 0) > 0), flip_p([tc[d][1] for d in sorted(tc)], rng)), ""]
    for v in sorted({25, pick}):
        L += ["### النافذة %d — لكلّ استراتيجيّة" % v, "",
              "| الاستراتيجيّة | البناء: صفقات · R للصفقة · موجبة/5 | الامتحان: صفقات · R للصفقة · موجبة/5 | المرجع: صفقات · R للصفقة |",
              "|---|---|---|---|"]
        for s in MOM_STRATS:
            row = []
            for span, yrs in ((BUILD, BUILD_YEARS), (TEST, TEST_YEARS), (REF, ())):
                dd = days_of(runs[v], "live", (s,), span)
                r, n = total(dd)
                y = by_year(dd)
                row.append((n, r / n if n else 0.0, sum(1 for k in yrs if y.get(k, 0.0) > 0)))
            L.append("| %s %s | %d · %+.3f · %d | %d · %+.3f · %d | %d · %+.3f |" % (
                s, NAMES[s], row[0][0], row[0][1], row[0][2], row[1][0], row[1][1], row[1][2], row[2][0], row[2][1]))
        L.append("")
    L += ["الفروق عن الحيّ كما في تقرير المنظومة: كلّ استراتيجيّة وإطار وحده · الوقف والكلفة بنسبة سعر اليوم · لا أخبار.", ""]
    (HERE / "تقرير معايرة الزخم.md").write_text("\n".join(L), encoding="utf-8")
    return pick


if __name__ == "__main__":
    arg = sys.argv[1:]
    print(json.dumps(build(), ensure_ascii=False) if arg == ["build"] else momentum() if arg == ["momentum"] else final())
