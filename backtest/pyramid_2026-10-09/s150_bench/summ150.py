import json
res = json.load(open("top150.json", encoding="utf-8"))
rows = []
for name, rs in res.items():
    if not isinstance(rs, list): continue
    for r in rs:
        a, b = r["train"], r["test"]
        if a.get("t") is None or b.get("t") is None: continue
        same = (a["t"] > 0) == (b["t"] > 0)
        rows.append((min(abs(a["t"]), abs(b["t"])) if same else 0, name, r))
rows.sort(key=lambda x: -x[0])
for s, name, r in rows[:10]:
    a, b = r["train"], r["test"]
    extra = f'{r.get("value","")}' if "value" in r else ""
    if "diff_bps" in a:
        print(f"{name:<16} {r['field']:<22} {extra:<10} {r['session']:<6} | تعلّم فرق={a['diff_bps']} t={a['t']} موافقة={a.get('agree')} | اختبار فرق={b['diff_bps']} t={b['t']} موافقة={b.get('agree')}")
    else:
        print(f"{name:<16} {r['field']:<22} {extra:<10} {r['session']:<6} | تعلّم n={a['n']} صعود={a['up']} م={a['mean_bps']} t={a['t']} | اختبار n={b['n']} صعود={b['up']} م={b['mean_bps']} t={b['t']}")
