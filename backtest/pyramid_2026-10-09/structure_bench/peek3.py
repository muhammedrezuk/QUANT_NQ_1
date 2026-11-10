import json
done = set()
for line in open("probe_full.jsonl", encoding="utf-8"):
    r = json.loads(line)
    e = r["_event"]
    if e in done or e not in ("structure.trend.state", "structure.phase.state", "analysis.trend.state", "structure.bos.state"): continue
    if e == "structure.trend.state" and (r.get("metadata") or {}).get("source") != "mss": continue
    done.add(e)
    print("=====", e)
    print(json.dumps(r, ensure_ascii=False, default=str)[:1500])
