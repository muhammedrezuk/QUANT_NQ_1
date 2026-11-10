# -*- coding: utf-8 -*-
"""حكم معايرة قسم البنية — القواعد مكتوبةٌ هنا قبل أيّ نتيجة (١٠-١٤)، وهي قواعد قسم التحليل نفسها على الأرقام والأسماء معًا.

الخليّة: رقمٌ (إطار · ذرّة.حقل) أو اسم (إطار · ذرّة.حقل · اسم · حجم/جهة) من حقائق الذرّات الثماني بالعيار الحيّ.
  البناء 2016–2020: قوّة الخليّة = متوسّط سنواتها إن ثبتت إشارته في 4 سنواتٍ من 5، وإلّا صفر؛ قيمة الإعداد = متوسّط القوّة المطلقة على
  الخلايا كلّها؛ المختار = الأعلى، أو الحيّ إن لم يزد عليه.
  الامتحان 2021-01 ⟵ 2025-09 مرّةً: يُعتمد المختار إن ثبتت إشارة البناء في 3 من 5 على عددٍ من الخلايا لا يقلّ عن الحيّ وكانت قوّته
  المتوسّطة أعلى. ويُعرض تفصيل كلّ ذرّةٍ (الحيّ مقابل المختار) كي لا تغلب ذرّةٌ على القسم في الخفاء (درس الضوضاء ١٠-١٤).
المحاولات: أوّل معايرةٍ لهذا الإعداد على سنوات البناء والامتحان (السابقة على أيلول–تشرين الأوّل 2025، أي المرجع). الاعتماد بختم المالك.
"""
import json
import pathlib
from collections import defaultdict

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
DEST = HERE / "out200"
BUILD_Y, TEST_Y = ("2016", "2017", "2018", "2019", "2020"), ("2021", "2022", "2023", "2024", "2025")
GRID = (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100)
LIVE = 8
NAMES = {"201": "القمم والقيعان", "202": "الهيكل الخارجيّ", "203": "الهيكل الداخليّ", "204": "الكسر", "205": "تغيّر الطابع",
         "206": "التحوّل", "207": "حالة الاتّجاه", "208": "طور السوق"}


def load(v):
    p = DEST / ("201__live__x.json" if v == LIVE else "201__lookback__%d.json" % v)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cells(run):
    out = {}
    for fr, fs in run["frames"].items():
        for f, c in fs.items():
            out[("n", fr, f)] = c
    for fr, fs in run.get("labels", {}).items():
        for f, labs in fs.items():
            for lab, v in labs.items():
                for t in ("size", "dir"):
                    out[("l", fr, f, lab, t)] = v[t]
    return out


def strength(cell, years, sign=None):
    if not cell:
        return 0.0, 0
    ys = cell["years"]
    ics = [ys[y][0] for y in years if y in ys]
    if len(ics) < len(years):
        return 0.0, 0
    mean = float(np.mean(ics))
    sg = sign if sign is not None else np.sign(mean)
    same = sum(1 for x in ics if np.sign(x) == sg and x != 0)
    return (mean if same >= (4 if sign is None else 3) and np.sign(mean) == sg else 0.0), same


def atom_of(key):
    return key[2].split(".")[0]


def main():
    live = load(LIVE)
    lc = cells(live)
    keys = sorted(lc)
    runs = {v: load(v) for v in (LIVE,) + GRID}
    sc = {}
    for v, r in runs.items():
        if r is not None:
            rc = cells(r)
            sc[v] = float(np.mean([abs(strength(rc.get(k), BUILD_Y)[0]) for k in keys]))
    best = max(sc, key=lambda v: sc[v])
    pick = best if best != LIVE and sc[best] > sc[LIVE] else LIVE
    L = ["# تقرير معايرة قسم البنية — عدد الشموع لتأكيد القمّة والقاع (الذرّة 201) وأثره على القسم كلّه (أمر المالك ١٠-١٤)", "",
         "في القسم إعدادٌ واحد؛ لكلّ قيمةٍ شُغّلت الذرّات الثماني بكودها الحيّ على تاريخ الناسداك، وقيست حقائقها أرقامًا (بُعد الإغلاق عن "
         "المستوى ٪ ⟵ الجهة التالية) وأسماءً (الحجم والجهة التاليان). القيم × 100. القواعد كُتبت قبل النتائج (رأس أداة الحكم).", "",
         "**البناء 2016–2020 — قيمة كلّ عدد:** " + " · ".join(("**%d: %.2f**" if v == LIVE else "%d: %.2f") % (v, sc[v] * 100)
                                                         for v in sorted(sc)), ""]
    res = {}
    for v in sorted({LIVE, pick}):
        rc = cells(runs[v])
        per = defaultdict(lambda: [[], [], 0])
        stab, strs = 0, []
        for k in keys:
            b = lc.get(k) if v == LIVE else rc.get(k)
            sb, _ = strength(b, BUILD_Y)
            bics = [b["years"][y][0] for y in BUILD_Y if b and y in b["years"]]
            bs = np.sign(np.mean(bics)) if bics else 0
            st, _ = strength(b, TEST_Y, sign=bs) if bs else (0.0, 0)
            stab += 1 if st else 0
            strs.append(abs(st))
            a = atom_of(k)
            per[a][0].append(abs(sb))
            per[a][1].append(abs(st))
            per[a][2] += 1 if st else 0
        res[v] = (stab, float(np.mean(strs)), per)
    if pick == LIVE:
        L += ["**المختار في البناء: الحيّ 8 ⟸ يبقى 8**", ""]
    else:
        adopt = res[pick][0] >= res[LIVE][0] and res[pick][1] > res[LIVE][1]
        L += ["**المختار في البناء: %d** · الامتحان: خلايا ثابتة %d مقابل %d للحيّ · القوّة %.2f مقابل %.2f" % (
            pick, res[pick][0], res[LIVE][0], res[pick][1] * 100, res[LIVE][1] * 100), "",
            "**الحكم: %s**" % (("يُعتمد %d بدل 8" % pick) if adopt else "يبقى 8 — المختار لم يتحقّق شرطاه"), ""]
    L += ["## تفصيل كلّ ذرّة (متوسّط القوّة المطلقة × 100: البناء / الامتحان · خلايا ثابتة في الامتحان)", "",
          "| الذرّة | 8 (الحيّ) | %s |" % ("—" if pick == LIVE else "%d (المختار)" % pick), "|---|---|---|"]
    for a in sorted(res[LIVE][2]):
        cols = []
        for n, v in enumerate((LIVE, pick)):
            if n == 1 and pick == LIVE:
                cols.append("—")
                continue
            b, t, s = res[v][2][a]
            cols.append("%.2f / %.2f · %d" % (np.mean(b) * 100, np.mean(t) * 100, s))
        L.append("| %s %s | %s | %s |" % (a, NAMES.get(a, ""), cols[0], cols[1]))
    # أقوى ما تحمله حقائق القسم بالعيار الحيّ.
    top = []
    for k in keys:
        sb, _ = strength(lc[k], BUILD_Y)
        if sb:
            tics = [lc[k]["years"][y][0] for y in TEST_Y if y in lc[k]["years"]]
            name = "%s %s" % (k[1], k[2]) + ("=%s (%s)" % (k[3], "حجم" if k[4] == "size" else "جهة") if k[0] == "l" else "")
            top.append((abs(sb), "%s: %+.1f / %+.1f" % (name, sb * 100, np.mean(tics) * 100 if tics else 0)))
    top.sort(reverse=True)
    L += ["", "**أقوى ما تحمله حقائق القسم بالعيار الحيّ** (بناء / امتحان): " + (" · ".join(t for _, t in top[:10]) or "لا شيء ثبت"), "",
          "الاعتماد في الذرّة بختم المالك؛ والسبق ليس ربحًا بعد السبريد.", ""]
    (HERE / "تقرير معايرة قسم البنية.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
