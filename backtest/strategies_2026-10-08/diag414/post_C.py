# -*- coding: utf-8 -*-
"""ملحق بعد ج (للعلم، لا قرار): الكلفة النسبيّة على الفترات الثلاث للحاليّة وللعيار المرجعيّ، وقبل الكلفة بالجهة."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import calendar
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
L = lambda f: json.load(open(os.path.join(HERE, f), encoding="utf-8"))
DA, DB, C, PA, PB, RES = L("diag_A.json"), L("diag_B.json"), L("grid_C.json"), L("postC_A.json"), L("postC_B.json"), L("results.json")


def st(tr, key="r"):
    if not tr:
        return {"n": 0}
    rs = [x[key] if key == "r" else x["r"] + x["cost_r"] for x in tr]
    gp = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    return {"n": len(rs), "R": round(sum(rs), 1), "R/ص": round(sum(rs) / len(rs), 3),
            "معامل": round(gp / gl, 2) if gl else None}


def halves(tr, y0, m0, k):
    out, y, m, e = {}, y0, m0, []
    for _ in range(k + 1):
        e.append(calendar.timegm((y, m, 1, 0, 0, 0))); m += 6
        if m > 12:
            m -= 12; y += 1
    for a, b in zip(e, e[1:]):
        out[time.strftime("%Y-%m", time.gmtime(a))] = round(sum(x["r"] for x in tr if a <= x["t"] < b), 1)
    return out


INFO = "للعلم_شراء_وبيع_تحت50|ن3.0|ج1.0|ب0.0_كلفة_نسبيّة"
rows = {}
for lab, a, b, c in (("الحاليّة_كلفة_نسبيّة", DA["عيارات"]["كلفة_نسبيّة"]["trades"], DB["عيارات"]["كلفة_نسبيّة"]["trades"],
                      C["عيارات"]["الحاليّة_كلفة_نسبيّة_للعلم"]["trades"]),
                     ("المرجعيّ_كلفة_نسبيّة", PA["عيارات"][INFO]["trades"], PB["عيارات"][INFO]["trades"],
                      C["عيارات"][INFO]["trades"])):
    h = {**halves(c, 2014, 10, 10), **halves(b, 2019, 10, 10), **halves(a, 2024, 10, 4)}
    rows[lab] = {"ج": st(c), "ب": st(b), "أ": st(a), "اثنتا_عشرة_سنة": st(a + b + c),
                 "أنصاف_موجبة_من24": "%d/24" % sum(v > 0 for v in h.values()), "الأنصاف": h}
    print(lab, json.dumps({k: v for k, v in rows[lab].items() if k != "الأنصاف"}, ensure_ascii=False))
    print("   ", h)

cur_b, cur_a = DB["عيارات"]["الحاليّة"]["trades"], DA["عيارات"]["الحاليّة"]["trades"]
cur_c = C["عيارات"]["الحاليّة"]["trades"]
gross = {}
for lab, tr in (("أ", cur_a), ("ب", cur_b), ("ج", cur_c)):
    gross[lab] = {"شراء_قبل_الكلفة": st([x for x in tr if x["buy"]], "g"), "بيع_قبل_الكلفة": st([x for x in tr if not x["buy"]], "g"),
                  "شراء_بعدها": st([x for x in tr if x["buy"]]), "بيع_بعدها": st([x for x in tr if not x["buy"]]),
                  "متوسّط_الكلفة÷الخطر": round(sum(x["cost_r"] for x in tr) / len(tr), 3)}
    print(lab, json.dumps(gross[lab], ensure_ascii=False))
yrs = {}
for x in cur_b + cur_a:
    yrs.setdefault(str(x["year"]), []).append(x)
gy = {y: {"بعد": st(v), "قبل_الكلفة": st(v, "g")} for y, v in sorted(yrs.items())}
print(json.dumps({y: (v["بعد"]["R/ص"], v["قبل_الكلفة"]["R/ص"]) for y, v in gy.items()}, ensure_ascii=False))
RES["ملحق_بعد_ج_للعلم_لا_قرار"] = {"الكلفة_النسبيّة_على_الفترات_الثلاث": rows, "الحاليّة_بالجهة_قبل_الكلفة_وبعدها": gross,
                                    "الحاليّة_سنويًّا_أ+ب_قبل_الكلفة_وبعدها": gy,
                                    "تنبيه": "قِيس بعد فتح ج؛ لا يصلح للاختيار — ج لم تعد غير مرئيّة."}
json.dump(RES, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("أُلحق بـ results.json")
