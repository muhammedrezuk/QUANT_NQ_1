# -*- coding: utf-8 -*-
"""تدقيقٌ مستقلّ: يعيد حساب الافتتاح والضجيج والحدّين والإشارة من القاعدة مباشرةً (استعلامات SQL جديدة،
وكودٌ مستقلّ عن noise.py) لعيّنةٍ عشوائيّة من الصفقات المختارة — ويقارن بما سجّله القياس."""
import sys
import os
import json
import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
db = sqlite3.connect(DB, uri=True)
NY, LON = ZoneInfo("America/New_York"), ZoneInfo("Europe/London")
ANCH = {"ny": (NY, 9, 30), "lon": (LON, 8, 0)}
CFG = json.load(open(os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "results_two.json"), encoding="utf-8"))["المختارات"]
FILES = {"نيويورك": "trades_best_detail.json", "لندن": "trades_best_london_detail.json", "كلاهما": "trades_best_both_detail.json"}


def bar(t):
    r = db.execute("select open, high, low, close from candles_history where symbol='USTEC' and period='M5' and period_start=?",
                   (int(t),)).fetchone()
    return r


def anchor(leg, d):
    tz, hh, mm = ANCH[leg]
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz).timestamp())


random.seed(11)
worst, checked = 0.0, 0
mism = []
for lname, fn in FILES.items():
    n, mult = CFG[lname][0], CFG[lname][1]
    tr = json.load(open(os.path.join(HERE, fn), encoding="utf-8"))
    for x in random.sample(tr, min(25, len(tr))):
        leg, tc = x["leg"], x["t_close"]
        d = datetime.strptime(x["day"], "%Y-%m-%d").date()
        a = anchor(leg, d)
        assert a == x["anchor_t"]
        o = bar(a)[0]
        k = (tc - a) // 60
        # الأيّام الماضية: نرجع يومًا يومًا، أيّام العمل التي فيها شمعة الافتتاح، حتّى n يومًا
        past, dd = [], d
        while len(past) < n:
            dd -= timedelta(days=1)
            if dd.weekday() >= 5:
                continue
            pa = anchor(leg, dd)
            pb = bar(pa)
            if pb is None:
                continue
            past.append((dd, pa, pb[0]))
        vals = []
        for dd, pa, po in past:
            b = bar(pa + (k - 5) * 60)
            if b is not None:
                vals.append(abs(b[3] / po - 1))
        sig = sum(vals) / len(vals) if len(vals) >= math.ceil(0.7 * n) else None
        ub, lb = o * (1 + mult * sig), o * (1 - mult * sig)
        cl = bar(tc - 300)[3]
        side_ok = (cl > ub) if x["buy"] else (cl < lb)
        dev = max(abs(sig - x["sigma"]), abs(ub - x["ub"]), abs(lb - x["lb"]), abs(o - x["open"]), abs(cl - x["entry"]))
        worst = max(worst, dev)
        checked += 1
        if dev > 1e-9 or not side_ok or sorted(str(p[0]) for p in past) != sorted(x["sigma_days"]):
            mism.append((lname, x["day"], k, dev, side_ok))
print("صفقات مدقَّقة: %d · أكبر فرق: %.3g · مخالفات: %d" % (checked, worst, len(mism)))
for m in mism[:20]:
    print("  ", m)
