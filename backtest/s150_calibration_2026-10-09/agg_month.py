# -*- coding: utf-8 -*-
"""جمع الشهر (09-08 ⟵ 10-08، أمر المالك ١٠-١٠ «شهر كامل … وسّع وضيّق NQ») — قياسٌ فقط، لا يكتب في الذرّات.

لكلّ ذرّةٍ معايَرة ولكلّ عيار: في كلّ يومٍ وكلّ جلسة أحسن «زيادة» من حقائق الذرّة نفسها (كما في adopt_day)، ثمّ:
متوسّطها على الأيّام · كم يومًا كانت موجبة · كم يومًا كان هذا العيار الأوّل بين عيارات الذرّة. والعيار الحيّ للمقارنة.
⚠️ «أحسن قراءة» تُختار داخل كلّ يومٍ بعد رؤيته — فالمتوسّط متفائل لكلّ العيارات بالقدر نفسه تقريبًا؛ المقارنة بينها عادلة،
والرقم المطلق ليس ربحًا متوقّعًا.
"""
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calib_day as C  # noqa: E402

D = pathlib.Path(__file__).resolve().parent
files = sorted(C.SCRATCH.glob("day_results_all_2026-*.json"))
per = defaultdict(dict)          # (tune, cfg, session) ⟶ {day: best edge}
for f in files:
    day = f.stem.split("_")[-1]
    for x in json.loads(f.read_text(encoding="utf-8")):
        if x["atom"] != x["tune"]:
            continue
        k = (x["tune"], x["cfg"], x["session"])
        if day not in per[k] or x["edge"] > per[k][day]:
            per[k][day] = x["edge"]
days = [f.stem.split("_")[-1] for f in files]
rows = []
for (tune, cfg, s), d in per.items():
    vals = list(d.values())
    rows.append({"atom": tune, "cfg": cfg, "session": s, "days": len(vals), "mean": round(sum(vals) / len(vals), 1),
                 "pos": sum(v > 0 for v in vals)})
wins = defaultdict(int)
for s in ("london", "ny"):
    for day in days:
        best = {}
        for (tune, cfg, ss), d in per.items():
            if ss == s and day in d and (tune not in best or d[day] > best[tune][1]):
                best[tune] = (cfg, d[day])
        for tune, (cfg, _) in best.items():
            wins[(tune, cfg, s)] += 1
for r in rows:
    r["first"] = wins[(r["atom"], r["cfg"], r["session"])]
(D / "month_results.json").write_text(json.dumps({"days": days, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
cat = C.catalog()
lines = [f"# الشهر {days[0] if days else ''} ⟵ {days[-1] if days else ''} — {len(days)} يومًا (قياسٌ فقط)\n",
         "متوسّط «الزيادة» من 100 على الأيّام · (أيّام موجبة / الأيّام) · كم يومًا كان الأوّل\n",
         "| الذرّة | الجلسة | العيار الحيّ | أحسن عيار على الشهر |", "|---|---|---|---|"]
for tune in sorted({r["atom"] for r in rows}):
    for s in ("london", "ny"):
        rs = [r for r in rows if r["atom"] == tune and r["session"] == s]
        if not rs:
            continue
        live = next((r for r in rs if r["cfg"] == "live"), None)
        best = max(rs, key=lambda r: (r["mean"], r["pos"]))
        f = lambda r: f"{r['cfg']} · {r['mean']:+.1f} · ({r['pos']}/{r['days']}) · الأوّل {r['first']}" if r else "—"  # noqa: E731
        lines.append(f"| {cat[tune]['dir'].name if tune in cat else tune} | {'لندن' if s == 'london' else 'نيويورك'} | {f(live)} | {f(best)} |")
(D / "month_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("أيّام", len(days), "· صفوف", len(rows))
