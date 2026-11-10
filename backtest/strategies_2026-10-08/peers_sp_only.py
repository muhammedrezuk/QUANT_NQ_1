# -*- coding: utf-8 -*-
"""أمر المالك ١٠-٠٨: «الغِ الداو من الارتباط، بس الإس آند بي 500» — البطاقة 414 بحكم الإرسال (سبريد 1.5)
بالأسواق المرتبطة: (أ) الإس آند بي والداو كما هي · (ب) الإس آند بي وحده · (ج) بلا ارتباط."""
import json
import sys

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\card_414")
import card_replay as R
import card_variants as V
from shared import card_trend as CT
import combine as C

FULL = dict(V.REF)
out = {}
split = R.START + 0.7 * (R.END - R.START)
days = (R.END - R.START) / 86400 * 5 / 7
for name, peers in (("أ_الإس_آند_بي_والداو", ("US500", "US30")), ("ب_الإس_آند_بي_وحده", ("US500",)), ("ج_بلا_ارتباط", ())):
    CT.PEERS = peers
    V.REF.clear(); V.REF.update({k: v for k, v in FULL.items() if k in peers})
    tr = [(t[0], t[2], t[3], t[4], t[5]) for t in C.card414()]
    out[name] = {"كلّه": R.stats(tr), "تعلّم": R.stats([x for x in tr if x[0] < split]),
                 "اختبار": R.stats([x for x in tr if x[0] >= split]), "صفقات/يوم": round(len(tr) / days, 2),
                 "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
                 "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"])}
    s = out[name]
    print(name, "| n=%s R=%s R/ص=%s معامل=%s سحب=%s أنصاف=%s | اختبار n=%s R/ص=%s معامل=%s | يوم=%s" % (
        s["كلّه"].get("n"), s["كلّه"].get("R"), s["كلّه"].get("R/صفقة"), s["كلّه"].get("معامل"), s["كلّه"].get("سحب_R"),
        s["كلّه"].get("أنصاف"), s["اختبار"].get("n"), s["اختبار"].get("R/صفقة"), s["اختبار"].get("معامل"),
        s["صفقات/يوم"]), flush=True)
json.dump(out, open("peers_sp_only.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
