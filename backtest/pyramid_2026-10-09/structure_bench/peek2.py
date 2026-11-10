import json, collections
c = collections.Counter()
for line in open("probe_full.jsonl", encoding="utf-8"):
    r = json.loads(line)
    if r["_event"] in ("structure.trend.state", "structure.phase.state", "analysis.trend.state"):
        c[(r["_event"], r.get("signal"), (r.get("metadata") or {}).get("source"))] += 1
for k, v in sorted(c.items(), key=lambda x: -x[1]): print(v, k)
