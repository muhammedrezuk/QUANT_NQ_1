# -*- coding: utf-8 -*-
"""حكم طريقة اختيار الوقف — القواعد مكتوبةٌ هنا قبل أيّ نتيجة (١٠-١٦، ختم المالك «قيس nq»).

السؤال: الوقف خلف آخر قاع/قمّة على 5د ثمّ 15د ثمّ 1د ضمن 15–45 نقطة يجد مكانًا في 37٪ فقط من دقائق نيويورك (مقيس ١٠-١٦)؛
فهل طريقةٌ أخرى أربح؟ الطرق الستّ (calib_system.STOP_VARIANTS): الحيّ · الدقيقة أوّلًا · أقرب صالحٍ من آخر خمسة · الاثنان ·
مدى 10–60 · الثلاثة. الربح = مجموع R لصفقات الاستراتيجيّات السبع على الإطارات الأربعة بالذرّات الحيّة وأثلاث المالك بعد الكلفة.
  البناء 2016–2020: المختار الأعلى ربحًا، ولا يُقبل غير الحيّ إلّا إن غلبه في 4 سنواتٍ من 5.
  الامتحان 2021-01 ⟵ 2025-09 مرّةً واحدة: يُعتمد إن ربح أكثر من الحيّ وغلبه في 3 سنواتٍ من 5 وحظّ الفرق (قلب إشارة كلّ يوم 5000 مرّة) < 0.05.
  المرجع 2025-10 ⟵ اليوم للعلم. ويُكتب بلا تجميل هل الحيّ والمختار رابحان بذاتهما.
المحاولات: أوّل قياسٍ لطريقة الوقف على هذه السنوات (معايرة المنظومة ١٠-١٣ أُوقفت قبل أيّ نتيجة).
معلن: كلّ استراتيجيّة وإطار وحده · الكنس من مسار شمعة الدقيقة · الوقف والكلفة بالنسبة لسعر اليوم · لا أخبار · قطعٌ بتسخين ستّة أشهر.
"""
import csv
import pathlib
from collections import defaultdict

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
BUILD, TEST, REF = ("2016-01-01", "2020-12-31"), ("2021-01-01", "2025-09-30"), ("2025-10-01", "2099-12-31")
BUILD_Y, TEST_Y = ("2016", "2017", "2018", "2019", "2020"), ("2021", "2022", "2023", "2024", "2025")
AR = {"live": "الحيّ (5د⟵15د⟵1د · آخر قاع · 15–45)", "SEL=1m-first": "الدقيقة أوّلًا", "SEL=nearest5": "أقرب صالحٍ من آخر خمسة",
      "SEL=1m-first+nearest5": "الدقيقة أوّلًا + أقرب صالح", "BAND=10-60": "مدى 10–60",
      "BAND=10-60+1m-first+nearest5": "مدى 10–60 + الدقيقة أوّلًا + أقرب صالح"}
NAMES = {"404": "الاتّجاه", "405": "الانعكاس", "406": "الاختراق", "407": "الارتداد", "408": "الزخم", "409": "المدى", "410": "السيولة"}


def load():
    d = defaultdict(lambda: [0, 0.0])            # (عيار، استراتيجيّة، يوم) ⟵ [صفقات، مجموع R]
    files = sorted(OUT.glob("stops_c*.csv"))
    for p in files:
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                a = d[(r["variant"], r["strategy"], r["day"])]
                a[0] += int(r["n"])
                a[1] += float(r["sumR"])
    return d, len(files)


def days(d, v, span, strat=None):
    out = defaultdict(lambda: [0, 0.0])
    for (vv, s, day), (n, r) in d.items():
        if vv == v and span[0] <= day <= span[1] and (strat is None or s == strat):
            out[day][0] += n
            out[day][1] += r
    return out


def tot(dd):
    return sum(r for _, r in dd.values()), sum(n for n, _ in dd.values())


def yearly(dd):
    y = defaultdict(float)
    for day, (_, r) in dd.items():
        y[day[:4]] += r
    return y


def flip_p(x, rng):
    x = np.asarray(x, dtype=float)
    if not len(x):
        return 1.0
    s = (rng.choice((-1.0, 1.0), size=(5000, len(x))) * x).sum(axis=1)
    return float((s >= x.sum()).mean())


def main():
    rng = np.random.default_rng(20261016)
    d, nfiles = load()
    vs = list(AR)
    L = ["# تقرير طريقة اختيار الوقف — الناسداك 2016–2026 (ختم المالك «قيس nq» ١٠-١٦)", "",
         "القواعد كُتبت قبل النتائج (رأس أداة الحكم). القطع المقروءة: %d من 5. القيم مجموع R بعد الكلفة." % nfiles, "",
         "| الطريقة | البناء: صفقات · مجموع R · للصفقة | الامتحان: صفقات · مجموع R · للصفقة | المرجع: صفقات · للصفقة |", "|---|---|---|---|"]
    res = {}
    for v in vs:
        b, t, r = days(d, v, BUILD), days(d, v, TEST), days(d, v, REF)
        (br, bn), (tr_, tn), (rr, rn) = tot(b), tot(t), tot(r)
        res[v] = (b, t, br, tr_)
        L.append("| %s | %d · %+.1f · %+.3f | %d · %+.1f · %+.3f | %d · %+.3f |" % (
            AR[v], bn, br, br / bn if bn else 0, tn, tr_, tr_ / tn if tn else 0, rn, rr / rn if rn else 0))
    best = max(vs, key=lambda v: res[v][2])
    bl = yearly(res["live"][0])
    wins_b = sum(1 for y in BUILD_Y if yearly(res[best][0]).get(y, 0) > bl.get(y, 0)) if best != "live" else 0
    pick = best if best != "live" and wins_b >= 4 else "live"
    L += ["", "**المختار في البناء: %s**%s" % (AR[pick], "" if pick != "live" or best == "live" else
                                                  " — الأعلى (%s) غلب الحيّ في %d سنواتٍ من 5 فقط" % (AR[best], wins_b)), ""]
    tl, tp = res["live"][1], res[pick][1]
    if pick != "live":
        dd = sorted(set(tl) | set(tp))
        diff = [tp.get(x, [0, 0.0])[1] - tl.get(x, [0, 0.0])[1] for x in dd]
        yl, yp = yearly(tl), yearly(tp)
        w = sum(1 for y in TEST_Y if yp.get(y, 0) > yl.get(y, 0))
        p = flip_p(diff, rng)
        adopt = res[pick][3] > res["live"][3] and w >= 3 and p < 0.05
        L += ["**الامتحان:** المختار %+.1f مقابل الحيّ %+.1f · غلبه في %d سنواتٍ من 5 · حظّ الفرق %.3f" % (res[pick][3], res["live"][3], w, p),
              "", "**الحكم: %s**" % ("يُعتمد «%s»" % AR[pick] if adopt else "لا يُعتمد — الحيّ يبقى"), ""]
    for v in sorted({"live", pick}):
        t = res[v][1]
        r, n = tot(t)
        y = yearly(t)
        L.append("**هل «%s» رابحٌ بذاته على الامتحان؟** %+.3f R للصفقة · سنواتٌ موجبة %d من 5 · حظّه مقابل الصفر %.3f" % (
            AR[v], r / n if n else 0, sum(1 for k in TEST_Y if y.get(k, 0) > 0), flip_p([t[x][1] for x in sorted(t)], rng)))
    L += ["", "### لكلّ استراتيجيّة على الامتحان (R للصفقة): الحيّ ⟵ المختار", ""]
    for s in NAMES:
        a = tot(days(d, "live", TEST, s))
        b = tot(days(d, pick, TEST, s))
        L.append("- %s %s: %+.3f (%d) ⟵ %+.3f (%d)" % (s, NAMES[s], a[0] / a[1] if a[1] else 0, a[1], b[0] / b[1] if b[1] else 0, b[1]))
    L += ["", "معلن: كلّ استراتيجيّة وإطار وحده (الحيّ يمنع صفقةً ثانية على الرمز) · الكنس من مسار شمعة الدقيقة · الوقف والكلفة "
          "بالنسبة لسعر اليوم · لا أخبار · الهدف هنا 3R بالأثلاث (لا الهدف الصافي الجديد).", ""]
    (HERE / "تقرير طريقة الوقف.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
