# -*- coding: utf-8 -*-
"""الخطأ المعياريّ لـ R/صفقة، والبيع ضدّ متوسّط 50 على ج (للعلم بعد ج)."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import json, os, math
HERE = os.path.dirname(os.path.abspath(__file__))
L = lambda f: json.load(open(os.path.join(HERE, f), encoding="utf-8"))
DA, DB, C = L("diag_A.json"), L("diag_B.json"), L("grid_C.json")
print("P_REF", DA["P_REF"])
for lab, tr in (("أ", DA["عيارات"]["الحاليّة"]["trades"]), ("ب", DB["عيارات"]["الحاليّة"]["trades"]),
                ("ج", C["عيارات"]["الحاليّة"]["trades"])):
    rs = [x["r"] for x in tr]; n = len(rs); m = sum(rs) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in rs) / (n - 1))
    print(lab, "n=%d متوسّط=%.3f انحراف=%.2f خطأ_معياريّ=%.3f ت=%.2f" % (n, m, sd, sd / math.sqrt(n), m / (sd / math.sqrt(n))))
    for name, f in (("بيع_فوق50", lambda x: (not x["buy"]) and x["above50"]), ("بيع_تحت50", lambda x: (not x["buy"]) and not x["above50"]),
                    ("شراء_فوق50", lambda x: x["buy"] and x["above50"]), ("شراء_تحت50", lambda x: x["buy"] and not x["above50"])):
        s = [x["r"] for x in tr if f(x)]
        print("   %s n=%d R=%.1f R/ص=%.3f" % (name, len(s), sum(s), sum(s) / len(s) if s else 0))
