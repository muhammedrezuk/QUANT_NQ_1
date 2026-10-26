# -*- coding: utf-8 -*-
"""مطابقة النسخة القابلة للضبط مع قياسات اليوم الأصليّة على السنتين — صفقةً بصفقة. قراءة فقط."""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.dirname(HERE)
ld = lambda p: json.load(open(p, encoding="utf-8"))
V = ld(os.path.join(HERE, "validate_2y_trades.json"))
VS = ld(os.path.join(HERE, "validate_2y.json"))

pairs = {"التذبذب": "squeeze/trades_best.json", "اختراق_الافتتاح": "orb/trades_best.json",
         "الانعكاس": "reversion/trades_best.json", "الكنس_ثمّ_العودة": "sweep/trades_best.json",
         "الانعكاس_عائلة_المتوسّط_للعلم": "reversion/trades_ema_family_best.json"}
for name, path in pairs.items():
    orig = ld(os.path.join(B, path))            # [t_close, exit_t, r, win, buy, bps]
    mine = V[name]                               # [t_close, exit_t, r, win, buy, bps]
    o = [(x[0], round(x[2], 3)) for x in orig]
    m = [(x[0], round(x[2], 3)) for x in mine]
    same_t = [a[0] for a in o] == [b[0] for b in m]
    maxdiff = max((abs(a[1] - b[1]) for a, b in zip(o, m)), default=0) if same_t else None
    print("%-30s أصل n=%d R=%.2f | نسخة n=%d R=%.2f | أوقات متطابقة=%s أقصى فرق R=%s" % (
        name, len(o), sum(x[2] for x in orig), len(m), sum(x[2] for x in mine), same_t, maxdiff))
    if not same_t:
        so, sm = set(a[0] for a in o), set(b[0] for b in m)
        print("   في الأصل وحده:", sorted(so - sm)[:10], "· في النسخة وحدها:", sorted(sm - so)[:10])

cb = ld(os.path.join(B, "combine.json"))
s = VS["استراتيجيّات"]["414"]["كلّه"]
print("414: أصل", {k: cb["414 وحدها"]["كلّه"][k] for k in ("n", "R", "R/صفقة", "معامل", "سحب_R")}, "| نسخة", s)
for k_orig, k_mine in (("414 + squeeze", "414 + التذبذب"), ("414 + orb", "414 + اختراق_الافتتاح")):
    print(k_orig, "أصل", {k: cb[k_orig]["كلّه"][k] for k in ("n", "R", "R/صفقة", "معامل", "سحب_R")},
          "من الأخرى", cb[k_orig]["من الأخرى"], "| نسخة", VS["دمج"][k_mine]["كلّه"], "من الأخرى", VS["دمج"][k_mine]["من_الأخرى"])
sq = ld(os.path.join(B, "squeeze/results.json"))
for r in sq["التركيبات"]:
    if r["م"] == 12 and r["ق"] == 0.25 and r["الوقف"] == "مقابل" and r["السياق"] == "اتّفاق" and r["ج"] == 1.5:
        print("الضابط 0.25: أصل", {k: r["كلّه"][k] for k in ("n", "R", "R/صفقة")}, "| نسخة",
              VS["استراتيجيّات"]["التذبذب_الضابط_ق0.25_للعلم"]["كلّه"])
print("تدقيق النسخة:", VS["تدقيق"])
