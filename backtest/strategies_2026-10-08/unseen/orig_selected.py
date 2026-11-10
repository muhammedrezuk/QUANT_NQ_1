# -*- coding: utf-8 -*-
"""استخراج أرقام المختارات على السنتين من نتائج اليوم (للمقارنة) — قراءة فقط."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import json
import os

B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ld = lambda p: json.load(open(os.path.join(B, p), encoding="utf-8"))
keys = ("n", "R", "R/صفقة", "معامل", "سحب_R", "فوز%", "أنصاف")
sh = lambda s: {k: s.get(k) for k in keys}

sq = ld("squeeze/results.json")
print("squeeze المختارة كلّه:", sh(sq["المختارة"]["كلّه"]), "ص/يوم", sq["المختارة"]["صفقات/يوم"])
for r in sq["التركيبات"]:
    if r["م"] == 12 and r["ق"] == 0.25 and r["الوقف"] == "مقابل" and r["السياق"] == "اتّفاق" and r["ج"] == 1.5:
        print("squeeze الضابط 0.25 كلّه:", sh(r["كلّه"]), "ص/يوم", r["صفقات/يوم"])
print("  البداية/النهاية", sq["البداية"], sq["النهاية"], sq["أيّام_عمل"])
ob = ld("orb/results.json")
r = ob["تركيبات"][ob["المختارة"]]
print("orb المختارة:", {k: r[k] for k in ("D", "الوقف", "N", "السياق", "C")}, sh(r["كلّه"]), "ص/يوم", r["صفقات/يوم"])
print("  البداية/النهاية", ob["البداية"], ob["النهاية"])
rv = ld("reversion/results.json")
print("reversion المختارة:", rv["المختارة"]["المعامِلات"], sh(rv["المختارة"]["كلّه"]), "ص/يوم", rv["المختارة"]["صفقات/يوم"])
for r in rv["تركيبات"]:
    if r["تمدّد"] == "متوسّط" and r["ك"] == 0.5 and r["ب"] == 0.25 and r["ن"] == 1.0 and r["سياق"] == "ضدّ_المتّفق":
        print("reversion عائلة المتوسّط:", sh(r["كلّه"]), "ص/يوم", r["صفقات/يوم"])
sw = ld("sweep/results.json")
print("sweep المختارة:", {k: sw["المختارة"][k] for k in ("ب", "ن", "ج", "السياق", "المستويات")}, sh(sw["المختارة"]["كلّه"]), "ص/يوم", sw["المختارة"]["صفقات/يوم"])
for name in ("squeeze", "orb", "reversion", "sweep"):
    tr = ld(name + "/trades_best.json")
    print(name, "trades_best:", len(tr), "R=%.2f" % sum(x[2] for x in tr), "أوّل", tr[0][:2], "آخر", tr[-1][:2])
tr = ld("reversion/trades_ema_family_best.json")
print("ema family trades:", len(tr), "R=%.2f" % sum(x[2] for x in tr))
