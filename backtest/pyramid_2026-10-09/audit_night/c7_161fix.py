# -*- coding: utf-8 -*-
"""فحص 7: القوّة النسبيّة 161 على الساعة — الأصل (الناسداك قبل أقرانه في الشمعة نفسها) مقابل المصحَّح (بعدهم)،
بدالّة التقييم نفسها في eval150_top (تُنفَّذ حتّى ما قبل حلقتها)."""
import json
import pathlib

S150 = pathlib.Path(r"C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\s150_bench")
A = pathlib.Path(r"C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\audit_night")
src = (S150 / "eval150_top.py").read_text(encoding="utf-8")
src = src.split("\nres = {}")[0]
g = {"__file__": str(S150 / "eval150_top.py"), "__name__": "evaltop"}
exec(compile(src, "eval150_top_head", "exec"), g)
for label, p in (("الأصل", S150 / "facts" / "161_1h_base.jsonl"), ("المصحَّح", A / "facts_fix" / "161_1h_base.jsonl")):
    rows = g["evaluate"](p)
    for r in rows:
        print(label, r["field"], r["session"], "تعلّم", r["train"], "اختبار", r["test"], flush=True)
# كم تختلف القيم نفسها؟
a = {json.loads(l)["t"]: json.loads(l) for l in open(S150 / "facts" / "161_1h_base.jsonl", encoding="utf-8")}
b = {json.loads(l)["t"]: json.loads(l) for l in open(A / "facts_fix" / "161_1h_base.jsonl", encoding="utf-8")}
common = [t for t in a if t in b and "m.percentile" in a[t] and "m.percentile" in b[t]]
diff = sum(1 for t in common if a[t]["m.percentile"] != b[t]["m.percentile"])
print("شموعٌ مشتركة", len(common), "· تغيّر ترتيب الناسداك في", diff, f"({diff / max(1, len(common)):.1%})", flush=True)
