# -*- coding: utf-8 -*-
"""للعلم: وزن الكلفة الثابتة (1.5 نقطة) بوحدات R سنةً بسنة — هل يفسّر مستوى السعر الأدنى قديمًا الفرق؟ قراءة فقط.
الخطر بالنقاط = ن.أ × سعر الدخول ÷ 10000 (سعر الدخول = إغلاق شمعة 5 د الزناد)؛ الكلفة بـR = 1.5 ÷ الخطر."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
db = sqlite3.connect(DB, uri=True)
close = {}


def px(t_close):
    t0 = int(t_close) - 300
    if t0 not in close:
        r = db.execute("select close from candles_history where symbol='USTEC' and period='M5' and period_start=?", (t0,)).fetchone()
        close[t0] = r[0] if r else None
    return close[t0]


OUT = {}
for label, f414, ftr in (("خمس_سنوات", "results_414_trades.json", "results_trades.json"),
                         ("سنتان", "validate_2y_414_trades.json", "validate_2y_trades.json")):
    sets = {}
    d414 = json.load(open(os.path.join(HERE, f414), encoding="utf-8"))
    sets["414_ب"] = d414["414_ب"]; sets["414_أ"] = d414["414_أ"]
    dtr = json.load(open(os.path.join(HERE, ftr), encoding="utf-8"))
    for k in ("التذبذب", "اختراق_الافتتاح", "الانعكاس", "الكنس_ثمّ_العودة"):
        sets[k] = dtr[k]
    OUT[label] = {}
    for name, rows in sets.items():
        by = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])   # n, R, كلفة R, سعر, خطر نقاط
        for t, ex, r, w, buy, bps in rows:
            p = px(t)
            if p is None:
                continue
            risk = bps * p / 1e4
            y = datetime.fromtimestamp(t, timezone.utc).year
            a = by[y]; a[0] += 1; a[1] += r; a[2] += 1.5 / risk; a[3] += p; a[4] += risk
        OUT[label][name] = {str(y): {"n": a[0], "R/صفقة": round(a[1] / a[0], 3), "كلفة_R/صفقة": round(a[2] / a[0], 3),
                                     "قبل_الكلفة_R/صفقة": round((a[1] + a[2]) / a[0], 3),
                                     "متوسّط_السعر": round(a[3] / a[0]), "متوسّط_الوقف_نقاط": round(a[4] / a[0], 1)}
                            for y, a in sorted(by.items())}
        print(label, name)
        for y, v in OUT[label][name].items():
            print("   ", y, v)
json.dump(OUT, open(os.path.join(HERE, "cost_share.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
