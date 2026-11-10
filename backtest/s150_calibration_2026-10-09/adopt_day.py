# -*- coding: utf-8 -*-
"""اعتماد يوم الخميس (أمر المالك ٢٠٢٦-١٠-٠٩ ~22:40: «اعتمد هي الأرقام كلّها بدل الموجود NQ»).

البيان عيارٌ واحد للذرّة، وأحسن عيار لندن غير أحسن عيار نيويورك أحيانًا ⟸ القاعدة الواحدة: لكلّ ذرّةٍ معايَرة، العيار
الذي مجموع أحسن «زيادة» له في لندن وأحسن «زيادة» له في نيويورك (على حقائق الذرّة نفسها، أيّ إطار) أعلى؛ والتعادل
للحيّ. يكتب adopt_day.json — ولا يكتب في البيانات (الكتابة خطوةٌ منفصلة مسجَّلة).
"""
import gzip
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calib_day as C  # noqa: E402

D = pathlib.Path(__file__).resolve().parent
rows = json.loads((C.SCRATCH / "day_results_all.json").read_text(encoding="utf-8"))
best = defaultdict(lambda: {"london": None, "ny": None})
for x in rows:
    if x["atom"] != x["tune"]:
        continue
    k = (x["tune"], x["cfg"])
    cur = best[k][x["session"]]
    if cur is None or x["edge"] > cur:
        best[k][x["session"]] = x["edge"]
choice = {}
for (tune, cfg), s in best.items():
    score = (s["london"] or 0) + (s["ny"] or 0)
    old = choice.get(tune)
    if old is None or score > old["score"] or (score == old["score"] and cfg == "live"):
        choice[tune] = {"cfg": cfg, "score": round(score, 1), "london": s["london"], "ny": s["ny"]}
cfgs = {}
for f in (C.SCRATCH / "runs").glob("*.json.gz"):
    tune, tag = f.name[:-8].split("__", 1)
    if tune in choice and choice[tune]["cfg"] == tag:
        cfgs[tune] = json.load(gzip.open(f, "rt", encoding="utf-8"))["cfg"]
cat = C.catalog()
out = []
for tune, c in sorted(choice.items()):
    live = best[(tune, "live")]
    new = cfgs.get(tune, {})
    diff = {k: [cat[tune]["config"].get(k), v] for k, v in new.items() if cat[tune]["config"].get(k) != v}
    out.append({"atom": tune, "name": cat[tune]["dir"].name, "cfg": c["cfg"], "score": c["score"], "london": c["london"],
                "ny": c["ny"], "live_london": live["london"], "live_ny": live["ny"], "changes": diff})
(D / "adopt_day.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
for o in out:
    print(o["atom"], o["cfg"], "| لندن", o["live_london"], "⟵", o["london"], "| نيويورك", o["live_ny"], "⟵", o["ny"], "|", o["changes"])
