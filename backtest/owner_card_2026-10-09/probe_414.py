# -*- coding: utf-8 -*-
"""فحص ملفّات صفقات 414 على الفترات الثلاث — قراءة فقط."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
D = r"C:\Users\NQ\QUANT_NQ\backtest\strategies_2026-10-08\diag414"
print(open(D + r"\prereg.json", encoding="utf-8").read()[:3000])
for name in ("diag_A", "diag_B", "grid_C", "postC_A", "postC_B"):
    try:
        x = json.load(open(D + "\\" + name + ".json", encoding="utf-8"))
    except Exception as e:
        print(name, "ERR", e); continue
    print("==", name, x.get("الفترة"), x.get("مرشّحات"))
    for k, v in list(x.get("عيارات", {}).items())[:60]:
        tr = v["trades"]
        print("  ", k, v["cfg"], len(tr), round(sum(t["r"] for t in tr), 2) if tr else None)
