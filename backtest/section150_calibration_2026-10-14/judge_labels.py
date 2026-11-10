# -*- coding: utf-8 -*-
"""حكم اختبار الأسماء — القواعد مكتوبةٌ هنا قبل أيّ نتيجة (١٠-١٤، ختم المالك «Nq»)، وهي قواعد الأرقام نفسها.

الخليّة = (إطار · حقل · اسم · هدف)؛ الهدف «حجم» (هل يسبق الاسم حركةً أكبر/أصغر في الشموع الخمس التالية) أو «جهة» (هل تستمرّ
الشمعة المسمّاة في جهتها — جهة الجسم، وللدبّوس جهة ذيله الأطول — أو تنعكس). خلايا العيار الحيّ هي المرجع.
  البناء 2016–2020: قوّة الخليّة = متوسّط سنواتها إن ثبتت إشارته في 4 سنواتٍ من 5، وإلّا صفر؛ قيمة العتبة = متوسّط القوّة المطلقة
  على الخلايا؛ المختار = الأعلى، أو الحيّ إن كان الأعلى صفرًا. اسمٌ يختفي بالعتبة الجديدة قوّته صفر.
  الامتحان 2021-01 ⟵ 2025-09 مرّةً: يُعتمد المختار إن ثبتت إشارة البناء في 3 من 5 على عددٍ من الخلايا لا يقلّ عن الحيّ وكانت قوّته
  المتوسّطة أعلى. المرجع 2025-10 ⟵ اليوم للعلم. أوّل محاولةٍ للأسماء على هذا التاريخ. الاعتماد في الذرّات بختم المالك.
"""
import json
import pathlib

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
DEST = HERE / "out_labels"
BUILD_Y, TEST_Y = ("2016", "2017", "2018", "2019", "2020"), ("2021", "2022", "2023", "2024", "2025")
AR_T = {"size": "حجم", "dir": "جهة"}
PARAMS = {"153": ("high_mult", "low_mult"), "156": ("doji_body_ratio", "marubozu_body_ratio", "pin_wick_ratio", "pin_body_ratio"),
          "162": ("slow_ratio", "fast_ratio"), "163": ("accel_ratio",), "165": ("noisy_max",)}


def fmt(v):
    return str(v) if isinstance(v, int) else ("%g" % v)


def cells(run):
    out = {}
    for fr, fs in (run or {}).get("labels", {}).items():
        for field, labs in fs.items():
            for lab, v in labs.items():
                for t in ("size", "dir"):
                    out[(fr, field, lab, t)] = v[t]
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


def load(a, k, v):
    p = DEST / ("%s__%s__%s.json" % (a, k, v))
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main():
    plan = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))
    L = ["# تقرير معايرة الأسماء — العتبات التي تغيّر كلمةً منشورة (ختم المالك ١٠-١٤)", "",
         "لكلّ اسمٍ تنشره الذرّة: هل تسبق الشموعُ التي تحمله حركةً أكبر/أصغر في الشموع الخمس التالية (حجم)، وهل تستمرّ في جهتها أو تنعكس "
         "(جهة)؟ القيم × 100 (ارتباط رتب؛ موجبٌ في الجهة = استمرار، سالبٌ = انعكاس). القواعد كُتبت قبل النتائج (رأس أداة الحكم).", ""]
    summary = []
    for a, ks in PARAMS.items():
        nm = plan["names"].get(a, a)
        live = load(a, "live", "x")
        L += ["## %s" % nm, ""]
        lc = cells(live)
        keys = sorted(lc)
        if not keys:
            L += ["لا أسماء بحصّةٍ كافية في تشغيل الحيّ.", ""]
            continue
        # ما يحمله كلّ اسمٍ اليوم (العيار الحيّ): أقوى الخلايا الثابتة في البناء.
        rows = []
        for k in keys:
            sb, _ = strength(lc[k], BUILD_Y)
            if sb:
                tics = [lc[k]["years"][y][0] for y in TEST_Y if y in lc[k]["years"]]
                rows.append((abs(sb), "%s %s=%s (%s): بناء %+.1f · امتحان %+.1f" % (k[0], k[1].lstrip("^"), k[2], AR_T[k[3]], sb * 100,
                                                                              np.mean(tics) * 100 if tics else 0)))
        rows.sort(reverse=True)
        L += ["**ما تحمله الأسماء بعيارها الحيّ** (الخلايا الثابتة في البناء، أقواها أوّلًا): " + (" · ".join(r for _, r in rows[:8]) or "لا شيء ثبت"), ""]
        for k in ks:
            p = plan["plan"][a][k]
            lv = p["live"]
            sc = {lv: float(np.mean([abs(strength(lc.get(c), BUILD_Y)[0]) for c in keys]))}
            for v in p["grid"]:
                r = load(a, k, fmt(v))
                if r is not None:
                    rc = cells(r)
                    sc[v] = float(np.mean([abs(strength(rc.get(c), BUILD_Y)[0]) for c in keys]))
            best = max(sc, key=lambda v: sc[v])
            pick = best if sc[best] > 0 and best != lv and sc[best] > sc[lv] else lv
            L += ["### %s (الحيّ %s)" % (k, fmt(lv)), "", "البناء: " + " · ".join(
                ("**%s: %.2f**" if v == lv else "%s: %.2f") % (fmt(v), sc[v] * 100) for v in sorted(sc)), ""]
            if pick == lv:
                L += ["**الحكم: يبقى %s**" % fmt(lv), ""]
                summary.append("- %s · %s: يبقى %s" % (nm, k, fmt(lv)))
                continue
            res = {}
            for v, run in ((lv, live), (pick, load(a, k, fmt(pick)))):
                rc = cells(run)
                stab, strs = 0, []
                for c in keys:
                    b = lc.get(c) if v == lv else rc.get(c)
                    bics = [b["years"][y][0] for y in BUILD_Y if b and y in b["years"]]
                    bs = np.sign(np.mean(bics)) if bics else 0
                    st, _ = strength(b, TEST_Y, sign=bs) if bs else (0.0, 0)
                    stab += 1 if st else 0
                    strs.append(abs(st))
                res[v] = (stab, float(np.mean(strs)))
            adopt = res[pick][0] >= res[lv][0] and res[pick][1] > res[lv][1]
            L += ["**المختار في البناء: %s** · الامتحان: خلايا ثابتة %d مقابل %d للحيّ · القوّة %.2f مقابل %.2f" % (
                fmt(pick), res[pick][0], res[lv][0], res[pick][1] * 100, res[lv][1] * 100), "",
                "**الحكم: %s**" % (("يُعتمد %s بدل %s" % (fmt(pick), fmt(lv))) if adopt else ("يبقى %s — المختار لم يتحقّق شرطاه" % fmt(lv))), ""]
            summary.append("- %s · %s: %s" % (nm, k, ("%s ⟵ %s" % (fmt(lv), fmt(pick))) if adopt else ("يبقى %s" % fmt(lv))))
    L += ["## الخلاصة", ""] + summary + ["", "الاعتماد في الذرّات بختم المالك؛ والسبق ليس ربحًا بعد السبريد.", ""]
    (HERE / "تقرير معايرة الأسماء.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
