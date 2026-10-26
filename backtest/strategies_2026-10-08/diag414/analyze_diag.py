# -*- coding: utf-8 -*-
"""التشخيص على أ+ب — تقسيم صفقات 414 الحيّة الصيغة على كلّ بُعد، أ مقابل ب. قراءة ملفّات المحرّك فقط."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
A = json.load(open(os.path.join(HERE, "diag_A.json"), encoding="utf-8"))
B = json.load(open(os.path.join(HERE, "diag_B.json"), encoding="utf-8"))
CFG = sys.argv[1] if len(sys.argv) > 1 else "الحاليّة"


def st(tr, key="r"):
    if not tr:
        return {"n": 0}
    rs = [x[key] for x in tr]
    gp = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    return {"n": len(rs), "R": round(sum(rs), 1), "R/ص": round(sum(rs) / len(rs), 3),
            "معامل": round(gp / gl, 2) if gl else None, "فوز%": round(100 * sum(r > 0 for r in rs) / len(rs))}


def bucket(v, edges, labels):
    for e, lab in zip(edges, labels):
        if v < e:
            return lab
    return labels[-1]


DIMS = {
    "السنة": lambda x: str(x["year"]),
    "الجهة": lambda x: "شراء" if x["buy"] else "بيع",
    "النافذة": lambda x: "لندن" if x["win"] == "london_peak" else "نيويورك",
    "مع_متوسّط50": lambda x: "مع" if (x["buy"] == x["above50"]) else "ضدّ",
    "مع_متوسّط200": lambda x: "مع" if (x["buy"] == x["above200"]) else "ضدّ",
    "الجهة×متوسّط200": lambda x: ("شراء" if x["buy"] else "بيع") + ("_فوق200" if x["above200"] else "_تحت200"),
    "الجهة×متوسّط50": lambda x: ("شراء" if x["buy"] else "بيع") + ("_فوق50" if x["above50"] else "_تحت50"),
    "تذبذب_اليوم": lambda x: "فوق_وسيطه" if x["volhi"] else "تحت_وسيطه",
    "تذبذب×الجهة": lambda x: ("شراء" if x["buy"] else "بيع") + ("_تذبذب_عالٍ" if x["volhi"] else "_تذبذب_منخفض"),
    "الوقف_ن.أ": lambda x: bucket(x["bps"], (6, 10, 15, 25, 1e9), ("<6", "6–10", "10–15", "15–25", "≥25")),
    "نسبة_الهدف": lambda x: bucket(x["rr"], (3.5, 4.5, 6, 1e9), ("3–3.5", "3.5–4.5", "4.5–6", "≥6")),
    "الكلفة÷الخطر": lambda x: bucket(x["cost_r"], (0.05, 0.1, 0.2, 1e9), ("<0.05", "0.05–0.1", "0.1–0.2", "≥0.2")),
    "مرحلة_الأثلاث": lambda x: ("0_وقف_كامل", "1_الأوّل_ثمّ_تعادل", "2_الثاني_ثمّ_الأوّل", "3_الهدف")[x["stage"]],
}


def split(tr, f):
    out = {}
    for x in tr:
        out.setdefault(f(x), []).append(x)
    return {k: st(v) for k, v in sorted(out.items())}


def add_gross(tr):
    for x in tr:
        x["r_gross"] = x["r"] + x["cost_r"]
    return tr


ta = add_gross(A["عيارات"][CFG]["trades"]); tb = add_gross(B["عيارات"][CFG]["trades"])
RES = {"العيار": CFG, "تحقّق": {"أ": A.get("تحقّق"), "ب": B.get("تحقّق")}, "P_REF": A["P_REF"],
       "مرشّحات": {"أ": A["مرشّحات"], "ب": B["مرشّحات"]}, "الكلّ": {}, "أبعاد": {}}
for name in A["عيارات"]:
    a, b = A["عيارات"][name]["trades"], B["عيارات"][name]["trades"]
    RES["الكلّ"][name] = {"أ": st(a), "ب": st(b), "أ+ب": st(a + b), "رفض_أ": A["عيارات"][name]["رفض"],
                         "رفض_ب": B["عيارات"][name]["رفض"]}
    print("%-26s | أ %s | ب %s | أ+ب %s" % (name, st(a), st(b), st(a + b)))
print()
print("قبل الكلفة (R الإجماليّ): أ %s | ب %s" % (st(ta, "r_gross"), st(tb, "r_gross")))
RES["قبل_الكلفة"] = {"أ": st(ta, "r_gross"), "ب": st(tb, "r_gross"), "أ+ب": st(ta + tb, "r_gross")}
for dim, f in DIMS.items():
    sa, sb, sab = split(ta, f), split(tb, f), split(ta + tb, f)
    RES["أبعاد"][dim] = {"أ": sa, "ب": sb, "أ+ب": sab}
    print("── %s" % dim)
    for k in sorted(set(sa) | set(sb)):
        print("   %-24s | أ n=%4s R/ص=%7s معامل=%5s | ب n=%4s R/ص=%7s معامل=%5s R=%6s" % (
            k, sa.get(k, {}).get("n"), sa.get(k, {}).get("R/ص"), sa.get(k, {}).get("معامل"),
            sb.get(k, {}).get("n"), sb.get(k, {}).get("R/ص"), sb.get(k, {}).get("معامل"), sb.get(k, {}).get("R")))

# متوسّطات المزيج: ما الذي تغيّر بين الفترتين
def mean(tr, k):
    return round(sum(x[k] for x in tr) / len(tr), 3)


mix = {}
for lab, tr in (("أ", ta), ("ب", tb)):
    mix[lab] = {"وسيط_الوقف_ن.أ": sorted(x["bps"] for x in tr)[len(tr) // 2],
                "متوسّط_الكلفة÷الخطر": mean(tr, "cost_r"), "متوسّط_نسبة_الهدف": mean(tr, "rr"),
                "حصّة_البيع%": round(100 * sum(not x["buy"] for x in tr) / len(tr)),
                "حصّة_ضدّ_متوسّط200%": round(100 * sum(x["buy"] != x["above200"] for x in tr) / len(tr)),
                "حصّة_تذبذب_عالٍ%": round(100 * sum(x["volhi"] for x in tr) / len(tr)),
                "بلغ_الأوّل%": round(100 * sum(x["stage"] >= 1 for x in tr) / len(tr)),
                "بلغ_الثاني%": round(100 * sum(x["stage"] >= 2 for x in tr) / len(tr)),
                "بلغ_الهدف%": round(100 * sum(x["stage"] == 3 for x in tr) / len(tr)),
                "متوسّط_الكلفة_بالنقاط÷سعر_ن.أ": round(1.5 / (sum(x["entry"] for x in tr) / len(tr)) * 1e4, 2)}
RES["المزيج"] = mix
print("\nالمزيج:", json.dumps(mix, ensure_ascii=False))

# ما يرفضه حكم الإرسال: صفقات «بلا حكم» التي لا تظهر في «الحاليّة» (بالوقت)
for lab, D in (("أ", A), ("ب", B)):
    cur = {x["t"] for x in D["عيارات"]["الحاليّة"]["trades"]}
    nov = D["عيارات"]["بلا_حكم_الإرسال_وقف3"]["trades"]
    gone = [x for x in nov if x["t"] not in cur]
    kept = [x for x in nov if x["t"] in cur]
    RES.setdefault("حكم_الإرسال", {})[lab] = {"بلا_حكم": st(nov), "يرفضها_الحكم": st(gone),
                                              "يبقيها": st(kept),
                                              "يرفضها_بالوقف": split(gone, DIMS["الوقف_ن.أ"]),
                                              "يرفضها_بنسبة_الهدف": split(gone, DIMS["نسبة_الهدف"]),
                                              "يرفضها_بالجهة": split(gone, DIMS["الجهة"])}
    print("حكم الإرسال %s: بلا حكم %s | يرفض %s | يبقي %s" % (lab, st(nov), st(gone), st(kept)))
    print("   يرفضها بالوقف:", RES["حكم_الإرسال"][lab]["يرفضها_بالوقف"])
    print("   يرفضها بنسبة الهدف:", RES["حكم_الإرسال"][lab]["يرفضها_بنسبة_الهدف"])

json.dump(RES, open(os.path.join(HERE, "diag_%s.json" % ("analysis" if CFG == "الحاليّة" else CFG)), "w",
                    encoding="utf-8"), ensure_ascii=False, indent=1)
