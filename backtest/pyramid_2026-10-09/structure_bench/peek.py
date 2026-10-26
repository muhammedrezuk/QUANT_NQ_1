import json, collections
seen = collections.defaultdict(int)
for line in open("probe_full.jsonl", encoding="utf-8"):
    r = json.loads(line)
    e = r["_event"]
    if seen[e] >= 2 or e == "analysis.trend.state": continue
    if e in ("structure.trend.state", "structure.phase.state") and r.get("signal") in ("range", "neutral"): continue
    seen[e] += 1
    keep = {k: r[k] for k in ("t", "timeframe", "signal", "score", "status") if k in r}
    keep["metadata"] = r.get("metadata")
    print(e, json.dumps(keep, ensure_ascii=False, default=str)[:600])
