# -*- coding: utf-8 -*-
"""دمج 414 مع منطقة الضجيج على السنتين — بمنطق combine.py نفسه (مستورَدٌ منه بلا تعديل):
414 بحكم الإرسال الحيّ (سبريد 1.5 · صافي ≥ 3)، مركزٌ واحد، والأسبق أوّلًا؛ صفقات الأخرى بسلسلتها وحدها."""
import sys
import os
import json

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))           # مجلّد الاستراتيجيّات (combine.py)
import combine as C
R = C.R

split = R.START + 0.7 * (R.END - R.START)
days = (R.END - R.START) / 86400 * 5 / 7


def summary(tr):
    s = {"كلّه": R.stats(tr), "تعلّم": R.stats([x for x in tr if x[0] < split]),
         "اختبار": R.stats([x for x in tr if x[0] >= split]), "صفقات/يوم": round(len(tr) / days, 2)}
    halves = s["كلّه"].get("أنصاف") or {}
    T = s["اختبار"]
    pos = sum(1 for v in halves.values() if v > 0)
    s["معيار_المالك"] = {"أنصاف_موجبة": "%d/%d" % (pos, len(halves)),
                         "يجتاز": (T.get("R/صفقة") or -1) > 0 and (T.get("معامل") or 0) >= 1.15 and T.get("n", 0) >= 30
                         and pos >= 4 and len(halves) >= 5}
    return s


# ٢٠٢٦-١٠-٠٨ 16:10 تغيّر القلب المشترك في المشروع: PEERS = ("US500",) وحده (كان ("US500", "US30")).
# المسطرة المكتوبة في المهمّة (155 صفقة · +22.7R) هي الارتباط المزدوج؛ نقيس الاثنين — والتبديل في الذاكرة فقط.
out = {}
live_peers = tuple(C.CT.PEERS)
for label, peers in (("414 (الإس آند بي والداو — مسطرة المهمّة)", ("US500", "US30")),
                     ("414 (الإس آند بي وحده — الحيّ منذ 16:10)", ("US500",))):
    C.CT.PEERS = peers
    base = C.card414()
    out[label + " وحدها"] = summary([(t[0], t[2], t[3], t[4], t[5]) for t in base])
    for name, fn in (("نيويورك", "trades_best.json"), ("لندن", "trades_best_london.json"), ("كلاهما", "trades_best_both.json")):
        other = json.load(open(os.path.join(HERE, fn), encoding="utf-8"))
        merged = C.merge(base, other)
        key = label + " + الضجيج " + name
        out[key] = summary(merged)
        out[key]["من الأخرى"] = sum(1 for x in merged if x[5] == 1)
        out[key]["من 414"] = sum(1 for x in merged if x[5] == 0)
C.CT.PEERS = live_peers
out["ملاحظة"] = "PEERS في الملفّ الحيّ عند القياس: %s" % (live_peers,)
for k, v in out.items():
    if isinstance(v, dict):
        print(k, json.dumps({kk: v[kk] for kk in v if kk != "تعلّم"}, ensure_ascii=False), flush=True)
json.dump(out, open(os.path.join(HERE, "combine_noise.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
