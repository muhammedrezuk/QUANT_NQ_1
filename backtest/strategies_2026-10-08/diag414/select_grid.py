# -*- coding: utf-8 -*-
"""الاختيار على أ+ب بالمعيار المسجَّل مسبقًا (prereg.json) — لا يقرأ ج."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import calendar
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GA = json.load(open(os.path.join(HERE, "grid_A.json"), encoding="utf-8"))
GB = json.load(open(os.path.join(HERE, "grid_B.json"), encoding="utf-8"))


def edges(y0, m0, count):
    out = []
    y, m = y0, m0
    for _ in range(count + 1):
        out.append(calendar.timegm((y, m, 1, 0, 0, 0)))
        m += 6
        if m > 12:
            m -= 12; y += 1
    return out


EB = edges(2019, 10, 10)     # 2019-10 ⟶ 2024-10
EA = edges(2024, 10, 4)      # 2024-10 ⟶ 2026-10 (والذيل 2026-10-01⟶05 خارج العدّ)
HALVES = list(zip(EB, EB[1:])) + list(zip(EA, EA[1:]))
LABELS = ["%d-%02d" % (lambda s: (s.tm_year, s.tm_mon))(__import__("time").gmtime(a)) for a, _ in HALVES]


def st(tr):
    if not tr:
        return {"n": 0, "R": 0.0, "R/ص": 0.0, "معامل": None}
    rs = [x["r"] for x in tr]
    gp = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    eq = pk = dd = 0.0
    for r in rs:
        eq += r; pk = max(pk, eq); dd = max(dd, pk - eq)
    return {"n": len(rs), "R": round(sum(rs), 1), "R/ص": round(sum(rs) / len(rs), 4),
            "معامل": round(gp / gl, 3) if gl else None, "سحب_R": round(dd, 1),
            "فوز%": round(100 * sum(r > 0 for r in rs) / len(rs))}


ROWS = []
for name in GA["عيارات"]:
    a, b = GA["عيارات"][name]["trades"], GB["عيارات"][name]["trades"]
    sa, sb, sab = st(a), st(b), st(a + b)
    hv = []
    for lo, hi in HALVES:
        hv.append(round(sum(x["r"] for x in a + b if lo <= x["t"] < hi), 2))
    pos = sum(v > 0 for v in hv)
    ok = {"أ_R/ص>0": sa["R/ص"] > 0, "أ_معامل≥1.15": (sa["معامل"] or 0) >= 1.15,
          "ب_R/ص>0": sb["R/ص"] > 0, "ب_معامل≥1.15": (sb["معامل"] or 0) >= 1.15, "أنصاف≥9من14": pos >= 9}
    ROWS.append({"العيار": name, "cfg": GA["عيارات"][name]["cfg"], "أ": sa, "ب": sb, "أ+ب": sab,
                 "أنصاف14": dict(zip(LABELS, hv)), "أنصاف_موجبة": pos, "شروط": ok, "ينجح": all(ok.values()),
                 "رفض_أ": GA["عيارات"][name]["رفض"], "رفض_ب": GB["عيارات"][name]["رفض"]})

ROWS.sort(key=lambda r: -r["أ+ب"]["R/ص"])
for r in ROWS:
    print("%-34s | أ n=%3d R/ص=%7.3f م=%5s | ب n=%3d R/ص=%7.3f م=%5s | أ+ب n=%4d R=%6.1f R/ص=%7.3f | أنصاف %2d/14 | %s" % (
        r["العيار"], r["أ"]["n"], r["أ"]["R/ص"], r["أ"]["معامل"], r["ب"]["n"], r["ب"]["R/ص"], r["ب"]["معامل"],
        r["أ+ب"]["n"], r["أ+ب"]["R"], r["أ+ب"]["R/ص"], r["أنصاف_موجبة"], "ينجح" if r["ينجح"] else ""))
passing = [r for r in ROWS if r["ينجح"]]
if passing:
    chosen = max(passing, key=lambda r: r["أ+ب"]["R/ص"])
    verdict = {"المختار": chosen["العيار"], "نوعه": "مختارٌ بالمعيار", "عدد_الناجحة": len(passing)}
else:
    chosen = max(ROWS, key=lambda r: min(r["أ"]["R/ص"], r["ب"]["R/ص"]))
    verdict = {"المختار": None, "للعلم_وحده": chosen["العيار"], "نوعه": "لا ينجح أحد — أعلى min(أ، ب) للعلم وحده",
               "عدد_الناجحة": 0}
print("\n", json.dumps(verdict, ensure_ascii=False))
print("أنصاف المختار/للعلم:", chosen["أنصاف14"])
json.dump({"معيار": "prereg.json", "الحكم": verdict, "الشبكة": ROWS}, open(os.path.join(HERE, "grid_selection.json"), "w",
          encoding="utf-8"), ensure_ascii=False, indent=1)
