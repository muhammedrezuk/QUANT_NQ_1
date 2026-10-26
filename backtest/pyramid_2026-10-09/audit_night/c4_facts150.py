# -*- coding: utf-8 -*-
"""فحص 4: هل قيم m.* في حقائق القسم 150 صحيحة (لا ناقصة ولا صفريّة)؟ — مقارنةٌ بحسابٍ يدويّ من الشموع نفسها،
وتوزيع الحالة، وتغطية الحقول، وما يُسقطه `direction()` من الحقول."""
import json
import sqlite3
import statistics as st
import sys
from collections import Counter

S = r"C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\s150_bench"
db = sqlite3.connect(r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\ctrader_history.db?mode=ro", uri=True)
t0 = 1405900800  # 2014-07-21
H1 = db.execute("select period_start, close from candles_history where symbol='USTEC' and period='H1' and period_start between ? and 1791244800 order by period_start", (t0,)).fetchall()

# EMA 10/20 كما في 151 (البذرة = أوّل إغلاق)
ef = es = None
calc = {}
closes = []
for ps, c in H1:
    if ef is None:
        ef = es = c
    else:
        ef = 2 / 11 * c + (1 - 2 / 11) * ef
        es = 2 / 21 * c + (1 - 2 / 21) * es
    closes.append(c)
    calc[ps + 3600] = (ef, es, c, list(closes[-25:]))

recs = [json.loads(l) for l in open(S + r"\facts\151_1h_base.jsonl", encoding="utf-8")]
status = Counter(r.get("status") for r in recs)
diffs = []
for r in recs[::500]:
    if "m.ema_fast_value" not in r:
        continue
    ef_, es_, c_, _ = calc[r["t"]]
    diffs.append(max(abs(ef_ - r["m.ema_fast_value"]), abs(es_ - r["m.ema_slow_value"]), abs(c_ - r["m.close"])))
print("151 ساعة: سجلّات", len(recs), "الحالة", dict(status), "· أقصى فرق EMA/إغلاق عن الحساب اليدويّ", max(diffs), "على", len(diffs), "عيّنة", flush=True)

# 152: ROC بالفترة 10
recs = [json.loads(l) for l in open(S + r"\facts\152_1h_roc10.jsonl", encoding="utf-8")]
bad = n = 0
for r in recs[1000::700]:
    if "m.roc" not in r:
        continue
    cl = calc[r["t"]][3]
    roc = (cl[-1] - cl[-11]) / cl[-11] * 100
    ups = sum(1 for i in range(-12, 0) if cl[i] > cl[i - 1]); dns = sum(1 for i in range(-12, 0) if cl[i] < cl[i - 1])
    pers = max(ups, dns) / (ups + dns) if ups + dns else 0.5
    n += 1
    if abs(roc - r["m.roc"]) > 0.01 or abs(pers - r["m.persistence"]) > 0.01:
        bad += 1
        if bad <= 3:
            print("   مثال مخالفة:", r["t"], "roc", round(roc, 4), r["m.roc"], "pers", round(pers, 2), r["m.persistence"])
print("152 ساعة roc10: عيّنة", n, "مخالفة", bad, "· الثبات (persistence) ≥ 0.5 دائمًا:",
      all(r.get("m.persistence", 1) >= 0.5 for r in recs), flush=True)

# تغطية الحقول وما يُسقطه direction() في القمّة
sys.path.insert(0, S)
UP = ("up", "bull", "above", "strong_up", "rising", "gap_up", "leader", "strong")
DOWN = ("down", "bear", "below", "strong_down", "falling", "gap_down", "laggard", "weak")


def direction(field, v):
    if isinstance(v, str):
        s = v.lower()
        if any(s == u or s.startswith(u + "_") or s.endswith("_" + u) for u in UP):
            return 1
        if any(s == w or s.startswith(w + "_") or s.endswith("_" + w) for w in DOWN):
            return -1
        return 0
    if isinstance(v, (int, float)):
        if any(k in field for k in ("pct_rank", "persistence", "percentile", "rank")):
            return 1 if v > 0.5 else (-1 if v < 0.5 else 0)
        if any(k in field for k in ("distance", "slope", "roc", "gap_pct", "relative", "excess", "return")):
            return 1 if v > 0 else (-1 if v < 0 else 0)
    return 0


for name in ("151_1h_base", "152_1h_roc10", "157_1d_base", "161_1h_base", "165_1h_base", "153_1h_base", "158_1h_base"):
    recs = [json.loads(l) for l in open(S + rf"\facts\{name}.jsonl", encoding="utf-8")][-20000:]
    fields = sorted({k for r in recs for k in r} - {"t", "status"})
    rep = {}
    for f in fields:
        c = Counter(direction(f, r.get(f)) for r in recs if f in r)
        vals = Counter(str(r.get(f))[:12] for r in recs if f in r)
        rep[f] = {"+": c[1], "-": c[-1], "0": c[0], "قيم": len(vals)}
    print(name, json.dumps(rep, ensure_ascii=False), flush=True)
