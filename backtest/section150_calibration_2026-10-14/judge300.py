# -*- coding: utf-8 -*-
"""حكم معايرة قسم الإحصاء — القواعد مكتوبةٌ هنا قبل أيّ نتيجة (١٠-١٤)، وهي قواعد القسمين قبله على الأرقام والأسماء معًا.

الخليّة: رقمٌ (إطار · حقل) أو اسم (إطار · حقل · اسم · حجم/جهة) من حقائق الذرّة بعيارها الحيّ.
  البناء 2016–2020: قوّة الخليّة = متوسّط سنواتها إن ثبتت إشارته في 4 من 5، وإلّا صفر؛ قيمة الإعداد = متوسّط القوّة المطلقة على خلايا الذرّة؛
  المختار = الأعلى إن زاد على الحيّ، وإلّا الحيّ.
  الامتحان 2021-01 ⟵ 2025-09 مرّةً: يُعتمد المختار إن ثبتت إشارة البناء في 3 من 5 على عددٍ من الخلايا لا يقلّ عن الحيّ وكانت قوّته أعلى.
  ويُعرض لكلّ مختارٍ تفصيل كلّ رقمٍ واسم (الحيّ مقابل المختار) — درس الضوضاء: رقمٌ جانبيّ قد يغلب الرقم الرئيس، والقرار للمالك عندها.
معلن: بلا إطار الدقيقة · أوّل معايرةٍ لهذا القسم على سنوات البناء والامتحان (السابقة على أيلول–تشرين الأوّل 2025، أي المرجع).
"""
import json
import pathlib
import sys
from collections import defaultdict

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
DEST = HERE / "out300"
BUILD_Y, TEST_Y = ("2016", "2017", "2018", "2019", "2020"), ("2021", "2022", "2023", "2024", "2025")


def fmt(v):
    return str(v) if isinstance(v, int) else ("%g" % v)


def load(a, k, v):
    p = DEST / ("%s__%s__%s.json" % (a, k, v))
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cells(run):
    out = {}
    if not run:
        return out
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


def name_of(k):
    return k[2].lstrip("^") + ("=%s (%s)" % (k[3], "حجم" if k[4] == "size" else "جهة") if k[0] == "l" else "")


def tested(rc, ref_cells, keys):
    stab, strs, per = 0, [], defaultdict(lambda: [[], []])
    for k in keys:
        b = rc.get(k)
        sb, _ = strength(b, BUILD_Y)
        bics = [b["years"][y][0] for y in BUILD_Y if b and y in b["years"]]
        bs = np.sign(np.mean(bics)) if bics else 0
        st, _ = strength(b, TEST_Y, sign=bs) if bs else (0.0, 0)
        stab += 1 if st else 0
        strs.append(abs(st))
        per[name_of(k)][0].append(sb)
        per[name_of(k)][1].append(st)
    return stab, float(np.mean(strs)) if strs else 0.0, per


def main():
    # الأداة نفسها لكلّ قسمٍ بعد الإحصاء (١٠-١٤): الخطّة · مجلّد النتائج · اسم التقرير · اسم القسم · ما خرج من الاختبار.
    global DEST
    a = sys.argv[1:]
    plan_name, DEST = (a[0], HERE / a[1]) if len(a) >= 2 else ("plan300.json", DEST)
    report = a[2] if len(a) >= 3 else "تقرير معايرة قسم الإحصاء.md"
    title = a[3] if len(a) >= 4 else "قسم الإحصاء"
    outside = a[4] if len(a) >= 5 else "307 الارتباط الإحصائيّ (يقارن برموزٍ أخرى) · 316 جودة البيانات (على التِّكّ)"
    plan = json.loads((HERE / plan_name).read_text(encoding="utf-8"))
    L = ["# تقرير معايرة %s — كلّ ذرّةٍ وحدها بكودها الحيّ (أمر المالك ١٠-١٤)" % title, "",
         "لكلّ إعداد: أيّ قيمةٍ تجعل أرقام الذرّة وأسماءها تسبق الشموع الخمس التالية (الجهة لذي الإشارتين وللمستوى، والحجم لغيرهما) بثباتٍ "
         "سنةً بسنة. القيم × 100. بلا إطار الدقيقة (معلن). القواعد كُتبت قبل النتائج (رأس أداة الحكم).", "",
         "**خارج الاختبار:** %s." % outside, ""]
    summary = []
    for a, params in plan["plan"].items():
        nm = plan["names"].get(a, a)
        live = load(a, "live", "x")
        L += ["## %s" % nm, ""]
        dead = ["%s = %s" % (k, fmt(p["live"])) for k, p in params.items() if not p["alive"]]
        if dead:
            L += ["ميّتة (لا تغيّر رقمًا ولا اسمًا منشورًا): " + " · ".join(dead), ""]
        lc = cells(live)
        keys = sorted(lc)
        if not keys:
            L += ["لا حقائق تُقاس في تشغيل الحيّ.", ""]
            continue
        for k, p in params.items():
            if not p["alive"]:
                continue
            lv = p["live"]
            sc = {lv: float(np.mean([abs(strength(lc.get(c), BUILD_Y)[0]) for c in keys]))}
            for v in p["grid"]:
                r = load(a, k, fmt(v))
                if r is not None:
                    rc = cells(r)
                    sc[v] = float(np.mean([abs(strength(rc.get(c), BUILD_Y)[0]) for c in keys]))
            best = max(sc, key=lambda v: sc[v])
            pick = best if best != lv and sc[best] > sc[lv] else lv
            L += ["### %s (الحيّ %s) — يغيّر: %s" % (k, fmt(lv), " · ".join(x.lstrip("^") for x in p["changes"])), "",
                  "البناء: " + " · ".join(("**%s: %.2f**" if v == lv else "%s: %.2f") % (fmt(v), sc[v] * 100) for v in sorted(sc)), ""]
            if pick == lv:
                L += ["**الحكم: يبقى %s**" % fmt(lv), ""]
                summary.append("- %s · %s: يبقى %s" % (nm, k, fmt(lv)))
                continue
            sl, ml, pl = tested(lc, lc, keys)
            sp, mp, pp = tested(cells(load(a, k, fmt(pick))), lc, keys)
            adopt = sp >= sl and mp > ml
            L += ["**المختار في البناء: %s** · الامتحان: خلايا ثابتة %d مقابل %d · القوّة %.2f مقابل %.2f" % (fmt(pick), sp, sl, mp * 100, ml * 100),
                  "", "**الحكم: %s**" % (("يُعتمد %s بدل %s" % (fmt(pick), fmt(lv))) if adopt else ("يبقى %s — المختار لم يتحقّق شرطاه" % fmt(lv))),
                  "", "تفصيل كلّ رقمٍ واسم (متوسّط الإطارات × 100، بناء/امتحان): الحيّ ⟵ المختار", ""]
            for f in sorted(pl, key=lambda f: -max(abs(np.mean(pl[f][0])), abs(np.mean(pp.get(f, [[0], [0]])[0])))):
                b0, t0 = np.mean(pl[f][0]) * 100, np.mean(pl[f][1]) * 100
                b1, t1 = (np.mean(pp[f][0]) * 100, np.mean(pp[f][1]) * 100) if f in pp else (0.0, 0.0)
                if max(abs(b0), abs(b1), abs(t0), abs(t1)) >= 0.5:
                    L.append("- %s: %+.1f/%+.1f ⟵ %+.1f/%+.1f" % (f, b0, t0, b1, t1))
            L.append("")
            summary.append("- %s · %s: %s" % (nm, k, ("%s ⟵ %s" % (fmt(lv), fmt(pick))) if adopt else ("يبقى %s" % fmt(lv))))
    L += ["## الخلاصة", ""] + summary + ["", "الاعتماد في الذرّات بختم المالك؛ والسبق ليس ربحًا بعد السبريد.", ""]
    (HERE / report).write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
