import json
mid = json.load(open("mid.json", encoding="utf-8"))
for r in mid[:12]:
    print(r["frame"], r["lb"], r["kind"], r["filter"], r["stops"], r["train"]["n"], r["test"]["n"])
