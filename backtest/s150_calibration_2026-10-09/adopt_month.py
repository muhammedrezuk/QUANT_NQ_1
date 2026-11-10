# -*- coding: utf-8 -*-
"""اعتماد الشهر (أمر المالك ١٠-١٠ ~13:00: «اعتمد الأرقام الأحسن» ثمّ «Nq»).

لكلّ ذرّةٍ معايَرة: العيار الذي مجموع متوسّط «زيادته» في لندن ونيويورك على الأيّام الـ23 أعلى (month_results.json)؛
والتعادل للحيّ. يكتب adopt_month.json بصيغة adopt_day.json — والكتابة في البيانات بـ write_adopt.py.
"""
import gzip
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calib_day as C  # noqa: E402

D = pathlib.Path(__file__).resolve().parent
m = json.loads((D / "month_results.json").read_text(encoding="utf-8"))
score = defaultdict(dict)
for r in m["rows"]:
    score[r["atom"]].setdefault(r["cfg"], {})[r["session"]] = r["mean"]
cat = C.catalog()
last_day = m["days"][-1]
import yaml  # noqa: E402


def valid(tune, cfg):
    """عيارٌ خارج حدود بيان الذرّة (config_schema) ترفضه المنظومة عند الإقلاع — يُتخطّى إلى التالي."""
    y = yaml.safe_load((cat[tune]["dir"] / "manifest.yaml").read_text(encoding="utf-8")) or {}
    props = (y.get("config_schema") or {}).get("properties") or {}
    for k, v in cfg.items():
        p = props.get(k, {})
        if isinstance(v, (int, float)) and (("minimum" in p and v < p["minimum"]) or ("maximum" in p and v > p["maximum"])):
            return False
    return True


out = []
for tune, cfgs in sorted(score.items()):
    tot = {c: s.get("london", 0) + s.get("ny", 0) for c, s in cfgs.items()}
    best, cfg = "live", {}
    for c in sorted(tot, key=lambda c: (-tot[c], c != "live")):
        if c == "live" or tot[c] <= tot.get("live", float("-inf")):
            break
        f = C.SCRATCH / f"runs_{last_day}" / f"{tune}__{c}.json.gz"
        cand = json.load(gzip.open(f, "rt", encoding="utf-8"))["cfg"]
        if valid(tune, cand):
            best, cfg = c, cand
            break
    base = cat[tune]["config"]
    diff = {k: [base.get(k), v] for k, v in cfg.items() if base.get(k) != v}
    out.append({"atom": tune, "name": cat[tune]["dir"].name, "cfg": best, "score": round(tot[best], 1),
                "live_score": round(tot.get("live", 0), 1), "changes": diff})
(D / "adopt_month.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
for o in out:
    print(o["atom"], o["cfg"], o["live_score"], "⟵", o["score"], o["changes"])
