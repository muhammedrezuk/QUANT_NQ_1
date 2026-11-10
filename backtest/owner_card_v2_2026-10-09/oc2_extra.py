# -*- coding: utf-8 -*-
"""المرحلة 3: مطابقة الأثلاث مع R.thirds الأصليّ (والمرحلة) · عرض التشخيص للتقرير."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import bisect
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc2_core as C

HERE = C.HERE
RES = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\card_414")
import card_replay as R  # noqa: E402  (يحمّل 2024-10 ⟶ للقراءة فقط)

n = same = 0
bad = []
for fname in ("trades_best_london.json", "trades_best_ny.json"):
    for x in json.load(open(os.path.join(HERE, fname), encoding="utf-8")):
        if x["t"] < R.START + 86400:
            continue
        k1 = bisect.bisect_right(R.t1, x["t"] - 60)
        r2, e2 = R.thirds(x["سعر_الدخول"], x["الوقف"], x["الهدف"], x["شراء"], k1)
        n += 1
        ok = r2 is not None and abs(r2 - x["R"]) < 1e-3 and e2 == x["خروج_t"]
        same += ok
        if not ok and len(bad) < 5:
            bad.append({"t": x["دخول_غ"], "R_محرّكي": x["R"], "R_المسطرة": r2, "خروج": [x["خروج_t"], e2]})
# المرحلة من R الصافي: الوقف الكامل ≈ −1R − الكلفة، والهدف الثالث أعلى قيمة
stage_ok = 0
cnt = 0
for fname in ("trades_best_london.json", "trades_best_ny.json"):
    for x in json.load(open(os.path.join(HERE, fname), encoding="utf-8")):
        cnt += 1
        if x["المرحلة"] == 0:
            stage_ok += x["R"] < -0.99
        elif x["المرحلة"] == 3:
            stage_ok += x["R"] > 1.9
        else:
            stage_ok += x["R"] > -0.3
ver = {"الأثلاث": {"صفقات_مقارنة": n, "مطابقة": same, "أوّل_فروق": bad},
       "اتّساق_المرحلة_مع_R": "%d من %d" % (stage_ok, cnt)}
print(json.dumps(ver, ensure_ascii=False), flush=True)
RES["مطابقة_المسطرة"] = ver
json.dump(RES, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("تمّ", flush=True)
