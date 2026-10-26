# -*- coding: utf-8 -*-
"""ج مرّة واحدة: الحاليّة والعيار «للعلم» جنبًا إلى جنب بالأنصاف العشرة، وحكم ج المسجَّل مسبقًا، ثمّ results.json."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import calendar
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
C = json.load(open(os.path.join(HERE, "grid_C.json"), encoding="utf-8"))
GA = json.load(open(os.path.join(HERE, "grid_A.json"), encoding="utf-8"))
GB = json.load(open(os.path.join(HERE, "grid_B.json"), encoding="utf-8"))
DA = json.load(open(os.path.join(HERE, "diag_A.json"), encoding="utf-8"))
DB = json.load(open(os.path.join(HERE, "diag_B.json"), encoding="utf-8"))
SEL = json.load(open(os.path.join(HERE, "grid_selection.json"), encoding="utf-8"))
DIAG = json.load(open(os.path.join(HERE, "diag_analysis.json"), encoding="utf-8"))
PRE = json.load(open(os.path.join(HERE, "prereg.json"), encoding="utf-8"))


def edges(y0, m0, count):
    out, y, m = [], y0, m0
    for _ in range(count + 1):
        out.append(calendar.timegm((y, m, 1, 0, 0, 0)))
        m += 6
        if m > 12:
            m -= 12; y += 1
    return out


EC = edges(2014, 10, 10)
LAB = ["%d-%02d" % (time.gmtime(a).tm_year, time.gmtime(a).tm_mon) for a in EC[:-1]]


def st(tr, key="r"):
    if not tr:
        return {"n": 0, "R": 0.0, "R/ص": 0.0, "معامل": None}
    rs = [x[key] for x in tr]
    gp = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    eq = pk = dd = 0.0
    for r in rs:
        eq += r; pk = max(pk, eq); dd = max(dd, pk - eq)
    return {"n": len(rs), "R": round(sum(rs), 1), "R/ص": round(sum(rs) / len(rs), 3),
            "معامل": round(gp / gl, 2) if gl else None, "سحب_R": round(dd, 1),
            "فوز%": round(100 * sum(r > 0 for r in rs) / len(rs))}


OUT = {}
for name, blk in C["عيارات"].items():
    tr = blk["trades"]
    for x in tr:
        x["r_gross"] = x["r"] + x["cost_r"]
    hv = [{"R": round(sum(x["r"] for x in tr if a <= x["t"] < b), 1), "n": sum(1 for x in tr if a <= x["t"] < b)}
          for a, b in zip(EC, EC[1:])]
    pos = sum(h["R"] > 0 for h in hv)
    s = st(tr)
    ok = {"R/ص>0": s["R/ص"] > 0, "معامل≥1.1": (s["معامل"] or 0) >= 1.1, "أنصاف≥6من10": pos >= 6}
    yrs = {}
    for x in tr:
        yrs.setdefault(str(x["year"]), []).append(x)
    OUT[name] = {"cfg": blk["cfg"], "رفض": blk["رفض"], "كلّه": s, "قبل_الكلفة": st(tr, "r_gross"),
                 "أنصاف_عشرة": dict(zip(LAB, hv)), "أنصاف_موجبة": "%d/10" % pos,
                 "سنويًّا": {y: st(v) for y, v in sorted(yrs.items())},
                 "شراء": st([x for x in tr if x["buy"]]), "بيع": st([x for x in tr if not x["buy"]]),
                 "لندن": st([x for x in tr if x["win"] == "london_peak"]),
                 "نيويورك": st([x for x in tr if x["win"] == "ny_open"]),
                 "متوسّط_الكلفة÷الخطر": round(sum(x["cost_r"] for x in tr) / len(tr), 3) if tr else None,
                 "وسيط_الوقف_ن.أ": round(sorted(x["bps"] for x in tr)[len(tr) // 2], 1) if tr else None,
                 "بلغ_الأوّل%": round(100 * sum(x["stage"] >= 1 for x in tr) / len(tr)) if tr else None,
                 "شروط_ج": ok, "يُقبل_على_ج": all(ok.values())}
    print("%-48s | n=%d R=%s R/ص=%s معامل=%s سحب=%s | قبل الكلفة R/ص=%s | أنصاف %d/10 | يُقبل=%s | رفض=%s" % (
        name, s["n"], s["R"], s["R/ص"], s["معامل"], s.get("سحب_R"), OUT[name]["قبل_الكلفة"]["R/ص"], pos,
        all(ok.values()), blk["رفض"]))
    print("    شراء %s | بيع %s" % (OUT[name]["شراء"], OUT[name]["بيع"]))
    print("    سنويًّا %s" % {y: (v["n"], v["R"], v["R/ص"]) for y, v in OUT[name]["سنويًّا"].items()})

CUR, INFO = "الحاليّة", "للعلم_شراء_وبيع_تحت50|ن3.0|ج1.0|ب0.0"
side = [{"النصف": lab, "الحاليّة_R": OUT[CUR]["أنصاف_عشرة"][lab]["R"], "الحاليّة_n": OUT[CUR]["أنصاف_عشرة"][lab]["n"],
         "للعلم_R": OUT[INFO]["أنصاف_عشرة"][lab]["R"], "للعلم_n": OUT[INFO]["أنصاف_عشرة"][lab]["n"]} for lab in LAB]
print("\nالأنصاف العشرة (ج):")
for r in side:
    print("  %s | الحاليّة %6.1f R n=%3d | للعلم %6.1f R n=%3d" % (r["النصف"], r["الحاليّة_R"], r["الحاليّة_n"],
                                                                   r["للعلم_R"], r["للعلم_n"]))

# الصورة الكاملة: ج + ب + أ (اثنتا عشرة سنة) للحاليّة وللعيار «للعلم»
def whole(name_grid, c_name):
    a = GA["عيارات"][name_grid]["trades"]; b = GB["عيارات"][name_grid]["trades"]; c = C["عيارات"][c_name]["trades"]
    return {"ج_2014-10⟶2019-09": st(c), "ب_2019-10⟶2024-09": st(b), "أ_2024-10⟶2026-10": st(a),
            "عشر_سنوات_ج+ب": st(c + b), "اثنتا_عشرة_سنة_ج+ب+أ": st(c + b + a)}


FULL = {"الحاليّة": whole("الجهتان|ن2.0|ج1.5|ب0.0", CUR), "للعلم": whole("شراء_وبيع_تحت50|ن3.0|ج1.0|ب0.0", INFO)}
print("\n", json.dumps(FULL, ensure_ascii=False))

# results.json الجامع
grid_rows = [{"العيار": r["العيار"], "أ": r["أ"], "ب": r["ب"], "أ+ب": r["أ+ب"], "أنصاف_موجبة_من14": r["أنصاف_موجبة"],
              "شروط": r["شروط"], "ينجح": r["ينجح"]} for r in SEL["الشبكة"]]
RES = {
    "المهمّة": "تشخيص البطاقة 414 ومعايرتها على أ+ب ثمّ ج مرّة واحدة — قياسٌ فقط",
    "التحقّق_من_المحرّك": DIAG["تحقّق"],
    "التسجيل_المسبق": PRE,
    "التشخيص_أ+ب": {k: DIAG[k] for k in ("الكلّ", "قبل_الكلفة", "المزيج", "حكم_الإرسال", "أبعاد", "P_REF")},
    "الشبكة_أ+ب": {"الحكم": SEL["الحكم"], "الصفوف_مرتّبة_بـR/ص_أ+ب": grid_rows},
    "ج_مرّة_واحدة": {"الفترة": C["الفترة"], "العيارات": OUT, "جنبًا_إلى_جنب": side},
    "الصورة_الكاملة": FULL,
    "ترتيب_الزمن": {"التسجيل_المسبق_غرينتش": PRE["وقت_الكتابة_غرينتش"],
                    "قرار_الشبكة_قبل_ج": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(
                        os.path.getmtime(os.path.join(HERE, "grid_selection.json")))),
                    "تشغيل_ج": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(
                        os.path.getmtime(os.path.join(HERE, "grid_C.json"))))},
}
json.dump(RES, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("كُتب results.json")
