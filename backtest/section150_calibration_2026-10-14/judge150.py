# -*- coding: utf-8 -*-
"""حكم معايرة قسم التحليل — القواعد مكتوبةٌ هنا قبل أيّ نتيجة (١٠-١٤)، وهي قواعد ذرّة الزخم 152 نفسها.

الخليّة = (إطار · رقمٍ تنشره الذرّة). ارتباط الرتب لكلّ سنة (رقمٌ بإشارتين أو مستوى ⟵ مع العائد التالي؛ رقمٌ بإشارةٍ واحدة ⟵ مع حجمه).
  البناء 2016–2020: قوّة الخليّة = متوسّط سنواتها إن ثبتت إشارته في 4 سنواتٍ من 5 (وكلّ السنوات الخمس موجودة)، وإلّا صفر.
  قيمة الإعداد = متوسّط القوّة المطلقة على خلايا الذرّة كلّها؛ المختار = الأعلى، أو الحيّ إن كان الأعلى صفرًا.
  الامتحان 2021-01 ⟵ 2025-09 مرّةً واحدة: يُعتمد المختار بدل الحيّ إن (أ) ثبتت إشارة البناء في 3 سنواتٍ من 5 على عددٍ من الخلايا
  لا يقلّ عن الحيّ، و(ب) متوسّط قوّته المطلقة في الامتحان أعلى من الحيّ. المرجع 2025-10 ⟵ اليوم للعلم.
كلّ إعدادٍ يُعايَر وحده والبقيّة على الحيّ. المحاولات تُعلَن: 151 قيست على هذا التاريخ ١٠-٠٩ (5,790 اختبارًا منذ 2018) ⟸ الثانية؛
والبقيّة الأولى على سنوات البناء والامتحان (معايراتها السابقة على أيلول–تشرين الأوّل 2025، أي المرجع).
الاعتماد في الذرّات بختم المالك بعد التقرير.
"""
import json
import pathlib

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
BUILD_Y, TEST_Y = (2016, 2017, 2018, 2019, 2020), (2021, 2022, 2023, 2024, 2025)
AR_FRAME = {"1m": "1د", "5m": "5د", "15m": "15د", "1h": "1س", "4h": "4س"}
KIND = {"signed": "جهة", "level": "بُعد عن مستوى", "size": "حجم"}
SECOND = {"151"}


def load(a, k, v):
    p = HERE / "out" / ("%s__%s__%s.json" % (a, k, v))
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def fmt(v):
    return str(v) if isinstance(v, int) else ("%g" % v)


def strength(cell, years, sign=None):
    if not cell:
        return 0.0, 0
    ys = cell["years"]
    ics = [ys[str(y)][0] for y in years if str(y) in ys]
    if len(ics) < len(years):
        return 0.0, 0
    mean = float(np.mean(ics))
    sg = sign if sign is not None else np.sign(mean)
    same = sum(1 for x in ics if np.sign(x) == sg and x != 0)
    need = 4 if sign is None else 3
    return (mean if same >= need and np.sign(mean) == sg else 0.0), same


def cells_of(run):
    return {(fr, f): c for fr, fs in run["frames"].items() for f, c in fs.items()} if run else {}


def score(run, keys):
    cs = cells_of(run)
    return float(np.mean([abs(strength(cs.get(k), BUILD_Y)[0]) for k in keys])) if keys else 0.0


def test(run, live_cells, keys):
    cs = cells_of(run)
    stab, strs = 0, []
    for k in keys:
        lb = live_cells.get(k)
        b = cs.get(k)
        bics = [b["years"][str(y)][0] for y in BUILD_Y if b and str(y) in b["years"]]
        bs = np.sign(np.mean(bics)) if bics else 0
        st, _ = strength(b, TEST_Y, sign=bs) if bs else (0.0, 0)
        stab += 1 if st else 0
        strs.append(abs(st))
    return stab, float(np.mean(strs)) if strs else 0.0


def main():
    plan = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))
    names = plan["names"]
    L = ["# تقرير معايرة قسم التحليل — كلّ ذرّةٍ وحدها بلا استراتيجيّة (أمر المالك ١٠-١٤)", "",
         "الاختبار نفسه الذي عويرت به ذرّة الزخم، بكود كلّ ذرّةٍ الحيّ: أيّ قيمةٍ لكلّ إعدادٍ تجعل أرقام الذرّة تسبق الشموع الخمس التالية "
         "(الجهة للأرقام ذات الإشارتين، والحجم لغيرها)، بثباتٍ سنةً بسنة. القيم × 100 للقراءة. القواعد كُتبت قبل النتائج (رأس أداة الحكم).", "",
         "**خارج الاختبار:** 152 الزخم (عويرت قبلها) · 160 الارتباط و161 القوّة النسبيّة (تحتاجان رموزًا غير الناسداك) · 158 الجلسات و159 أثر "
         "الوقت (لا إعداد رقميّ) · والتذبذب 153 بلا إطار الدقيقة (ثقل كوده).", ""]
    summary = []
    for a, params in plan["plan"].items():
        nm = names.get(a, a)
        live = load(a, "live", "x")
        L += ["## %s" % nm, ""]
        if not live or not cells_of(live):
            qp = HERE / "quick" / ("%s__live__x.json" % a)
            published = qp.exists() and json.loads(qp.read_text(encoding="utf-8")).get("digest")
            if published and params and not any(p["alive"] for p in params.values()):
                # تنشر أرقامًا، لكنّ إعداداتها كلّها لا تغيّر رقمًا منها (عتباتٌ تصنع أسماءً أو حكمًا) ⟸ لا تشغيل كامل.
                L += ["**إعداداتها كلّها ميّتة** — تنشر أرقامها الخام، وإعداداتها لا تغيّر منها شيئًا: %s" % " · ".join(
                    "%s = %s" % (k, fmt(p["live"])) for k, p in params.items()), ""]
                summary.append("- %s: إعداداتها كلّها لا تغيّر رقمًا منشورًا" % nm)
            else:
                L += ["لا تنشر من الشموع رقمًا يُقاس (تحتاج التِّكّات) ⟸ خارج هذا الاختبار.", ""]
                summary.append("- %s: خارج الاختبار (لا تنشر من الشموع)" % nm)
            continue
        live_cells = cells_of(live)
        keys = sorted(live_cells)
        kinds = sorted({"%s (%s)" % (f, KIND[c["kind"]]) for (fr, f), c in live_cells.items()})
        L += ["أرقامها المقيسة: %s%s" % (" · ".join(kinds), " — ⚠️ المحاولة الثانية على هذا التاريخ" if a in SECOND else ""), ""]
        dead = [k for k, p in params.items() if not p["alive"]]
        if dead:
            L += ["**إعداداتٌ ميّتة** (لا تغيّر أيّ رقمٍ منشور — تصنع حكمًا ينزعه عقد الحقائق): %s" % " · ".join(
                "%s = %s" % (k, fmt(params[k]["live"])) for k in dead), ""]
        for k, p in params.items():
            if not p["alive"]:
                continue
            lv = p["live"]
            vals = sorted(set(p["grid"]) | {lv})
            sc = {}
            for v in vals:
                run = live if v == lv else load(a, k, fmt(v))
                if run is not None:
                    sc[v] = score(run, keys)
            best = max(sc, key=lambda v: sc[v]) if sc else lv
            pick = best if sc.get(best, 0) > 0 else lv
            L += ["### %s (الحيّ %s)" % (k, fmt(lv)), "",
                  "البناء — قيمة كلّ رقم (متوسّط القوّة المطلقة × 100): " + " · ".join(
                      ("**%s: %.2f**" if v == lv else "%s: %.2f") % (fmt(v), sc[v] * 100) for v in vals if v in sc), ""]
            if pick == lv:
                verdict = "يبقى %s" % fmt(lv) + ("" if sc.get(best, 0) > 0 else " — لا قيمة ثبتت في البناء")
                L += ["**المختار في البناء: الحيّ %s ⟸ %s**" % (fmt(lv), verdict), ""]
                summary.append("- %s · %s: يبقى %s" % (nm, k, fmt(lv)))
                continue
            st_l = test(live, live_cells, keys)
            st_p = test(live if pick == lv else load(a, k, fmt(pick)), live_cells, keys)
            adopt = st_p[0] >= st_l[0] and st_p[1] > st_l[1]
            pr = cells_of(load(a, k, fmt(pick)))
            ref = [pr[c]["ref"] for c in keys if c in pr and pr[c].get("ref") is not None]
            L += ["**المختار في البناء: %s** · الامتحان: خلايا ثابتة %d مقابل %d للحيّ · القوّة %.2f مقابل %.2f · المرجع (متوسّط) %+.2f" % (
                fmt(pick), st_p[0], st_l[0], st_p[1] * 100, st_l[1] * 100, float(np.mean(ref)) * 100 if ref else 0.0), "",
                "**الحكم: %s**" % (("يُعتمد %s بدل %s" % (fmt(pick), fmt(lv))) if adopt else ("يبقى %s — المختار %s لم يتحقّق شرطاه" % (fmt(lv), fmt(pick)))), ""]
            summary.append("- %s · %s: %s" % (nm, k, ("%s ⟵ %s" % (fmt(lv), fmt(pick))) if adopt else ("يبقى %s" % fmt(lv))))
        L.append("")
    L += ["## الخلاصة", ""] + summary + ["", "الاعتماد في الذرّات بختم المالك؛ والسبق ليس ربحًا بعد السبريد.", ""]
    (HERE / "تقرير معايرة قسم التحليل.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
