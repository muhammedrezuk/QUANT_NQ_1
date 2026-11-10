# -*- coding: utf-8 -*-
"""إضافة أمر المالك ١٠-٠٨: البطاقة 414 بصيغتي الارتباط على الفترة نفسها — قياسٌ فقط.
  (أ) الإس آند بي والداو  (القديمة)  : CT.PEERS = ("US500", "US30") · V.REF بالرمزين.
  (ب) الإس آند بي وحده    (الحيّة)   : CT.PEERS = ("US500",)        · V.REF بلا الداو.
كلتاهما بحكم الإرسال الصافي (combine.card414 كما هو). والدمج بالصيغة (ب)، و(أ) للعلم.
صفقات الاستراتيجيّات الأخرى تُقرأ من ملفّ صفقات unseen_run (لا تتأثّر بالارتباط: لا تقرأ CT.PEERS؛
واختراق الافتتاح يقرأ V.REF في سياقه — وقد قيس بالرمزين كما عُويِر، ولا يُعاد هنا).
الاستعمال: python unseen_414_peers.py <ملفّ النتائج للتحديث> <ملفّ الصفقات> [البداية] [آخر يوم]
"""
import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")

import bisect
import calendar
import importlib.util
import json
import os
import time
from datetime import datetime, timezone, timedelta

T0 = time.time()
os.environ.pop("UNSEEN_START", None); os.environ.pop("UNSEEN_END", None)
if len(sys.argv) > 3:
    os.environ["UNSEEN_START"] = sys.argv[3]
if len(sys.argv) > 4:
    os.environ["UNSEEN_END"] = sys.argv[4]
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, HERE)

import card_replay as R
import card_replay_shared as S
import card_variants as V
import card_final_check as FC
from shared import card_trend as CT
for _m in (R, S, V, FC):
    assert os.path.dirname(os.path.abspath(_m.__file__)) == HERE, _m.__file__

spec = importlib.util.spec_from_file_location("combine_unseen", os.path.join(BASE, "combine.py"))
CB = importlib.util.module_from_spec(spec); sys.modules["combine_unseen"] = CB; spec.loader.exec_module(CB)
assert CB.R is R and CB.V is V and CB.CT is CT

fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")
print("الفترة: %s ⟶ %s · PEERS في الملفّ الحيّ الآن = %s" % (fmt(R.START), fmt(R.END), CT.PEERS), flush=True)


def add_months(t, k):
    d = datetime.fromtimestamp(t, timezone.utc)
    y, m = d.year + (d.month - 1 + k) // 12, (d.month - 1 + k) % 12 + 1
    return calendar.timegm((y, m, 1, 0, 0, 0))


HALF_EDGES = [R.START]
while HALF_EDGES[-1] < R.END:
    HALF_EDGES.append(min(add_months(HALF_EDGES[-1], 6), R.END))
HALF_LABELS = ["%s⟶%s" % (datetime.fromtimestamp(a, timezone.utc).strftime("%Y-%m"),
                          (datetime.fromtimestamp(b, timezone.utc) - timedelta(days=1)).strftime("%Y-%m"))
               for a, b in zip(HALF_EDGES, HALF_EDGES[1:])]


def weekdays(a, b):
    d0 = datetime.fromtimestamp(a, timezone.utc).date()
    d1 = datetime.fromtimestamp(b - 1, timezone.utc).date()
    return sum(1 for i in range((d1 - d0).days + 1) if (d0 + timedelta(days=i)).weekday() < 5)


DAYS = weekdays(R.START, R.END)


def brief(tr):
    if not tr:
        return {"n": 0}
    rs = [x[1] for x in tr]
    gp = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    return {"n": len(rs), "R": round(sum(rs), 1), "R/صفقة": round(sum(rs) / len(rs), 3),
            "معامل": round(gp / gl, 2) if gl else None, "فوز%": round(100 * sum(r > 0 for r in rs) / len(rs))}


def summary(tr):
    tr = sorted(tr, key=lambda x: x[0])
    st = R.stats(tr)
    if not tr:
        return {"كلّه": st, "يثبت": False}
    halves = [0.0] * len(HALF_LABELS); hn = [0] * len(HALF_LABELS)
    for x in tr:
        k = bisect.bisect_right(HALF_EDGES, x[0]) - 1
        halves[k] += x[1]; hn[k] += 1
    pos = sum(1 for v in halves if v > 0)
    years = {}
    for x in tr:
        years.setdefault(datetime.fromtimestamp(x[0], timezone.utc).year, []).append(x)
    verdict = {"R/صفقة>0": st["R/صفقة"] > 0, "معامل≥1.15": (st["معامل"] or 0) >= 1.15, "أنصاف≥7من10": pos >= 7}
    return {"كلّه": {k: st[k] for k in ("n", "R", "R/صفقة", "معامل", "سحب_R", "فوز%", "وقف_ن.أ_وسيط")},
            "أنصاف_عشرة": {lab: {"R": round(v, 1), "n": n} for lab, v, n in zip(HALF_LABELS, halves, hn)},
            "أنصاف_موجبة": "%d/%d" % (pos, len(HALF_LABELS)), "أنصاف_تقويميّة": st["أنصاف"],
            "سنويًّا": {str(y): brief(v) for y, v in sorted(years.items())},
            "صفقات/يوم": round(len(tr) / DAYS, 3),
            "لندن": brief([x for x in tr if x[2] == "london_peak"]),
            "نيويورك": brief([x for x in tr if x[2] == "ny_open"]),
            "شراء": brief([x for x in tr if x[3]]), "بيع": brief([x for x in tr if not x[3]]),
            "شروط": verdict, "يثبت": all(verdict.values())}


def line(name, s, extra=""):
    print("%-34s | n=%s R=%s R/ص=%s معامل=%s سحب=%s فوز=%s | أنصاف موجبة %s | ص/يوم %s | يثبت=%s %s| %.0f ث" % (
        name, s["كلّه"].get("n"), s["كلّه"].get("R"), s["كلّه"].get("R/صفقة"), s["كلّه"].get("معامل"),
        s["كلّه"].get("سحب_R"), s["كلّه"].get("فوز%"), s.get("أنصاف_موجبة"), s.get("صفقات/يوم"), s.get("يثبت"),
        extra, time.time() - T0), flush=True)


REF_FULL = dict(V.REF)
assert set(REF_FULL) == {"US500", "US30"}
FORMS = {"أ": (("US500", "US30"), REF_FULL), "ب": (("US500",), {"US500": REF_FULL["US500"]})}
BASES, OUT414 = {}, {}
for form, (peers, ref) in FORMS.items():
    CT.PEERS = peers; V.REF = ref
    base = CB.card414()
    BASES[form] = base
    tr = [(t[0], t[2], t[3], t[4], t[5], t[1]) for t in base]
    bad = sum(1 for a, b in zip(tr, tr[1:]) if b[0] < a[5] + 60) + sum(1 for x in tr if not (R.START <= x[0] <= R.END))
    assert bad == 0, bad
    OUT414[form] = summary(tr)
    line("414 (%s) %s" % (form, "+".join(peers)), OUT414[form])
# للعلم: الصيغة (ب) بلا حكم الإرسال الصافي (card_final_check كما هو)
CT.PEERS, V.REF = FORMS["ب"]
tr_fc, tally_fc = FC.run()
OUT414["ب_بلا_حكم_الإرسال_للعلم"] = summary(tr_fc)
line("414 (ب) بلا حكم الإرسال", OUT414["ب_بلا_حكم_الإرسال_للعلم"])
CT.PEERS, V.REF = FORMS["أ"]                      # إرجاع (لا أثر بعده — لا قياس آخر في هذه العمليّة)

# الدمج: (ب) مع كلّ واحدة، و(أ) للعلم
TR = json.load(open(os.path.join(HERE, sys.argv[2]), encoding="utf-8"))
names = ("التذبذب", "اختراق_الافتتاح", "الانعكاس", "الكنس_ثمّ_العودة",
         "التذبذب_الضابط_ق0.25_للعلم", "الانعكاس_عائلة_المتوسّط_للعلم")
MERGE = {"ب": {}, "أ": {}}
for form in ("ب", "أ"):
    for name in names:
        other = [x for x in TR[name]]                 # [t_close, exit_t, r, win, buy, bps]
        merged = CB.merge(BASES[form], other)
        s = {**summary(merged), "من_الأخرى": sum(1 for x in merged if x[5] == 1)}
        MERGE[form]["414(%s) + %s" % (form, name)] = s
        line("414(%s) + %s" % (form, name), s, "من الأخرى %d " % s["من_الأخرى"])

side = [{"النصف": lab, "أ_R": OUT414["أ"]["أنصاف_عشرة"][lab]["R"], "أ_n": OUT414["أ"]["أنصاف_عشرة"][lab]["n"],
         "ب_R": OUT414["ب"]["أنصاف_عشرة"][lab]["R"], "ب_n": OUT414["ب"]["أنصاف_عشرة"][lab]["n"]} for lab in HALF_LABELS]
for row in side:
    print("  %s | (أ) %6.1f R n=%3d | (ب) %6.1f R n=%3d" % (row["النصف"], row["أ_R"], row["أ_n"], row["ب_R"], row["ب_n"]))

path = os.path.join(HERE, sys.argv[1])
RES = json.load(open(path, encoding="utf-8"))
RES["414_صيغتا_الارتباط"] = {"أ_الإس_والداو": OUT414["أ"], "ب_الإس_وحده": OUT414["ب"],
                              "ب_بلا_حكم_الإرسال_للعلم": OUT414["ب_بلا_حكم_الإرسال_للعلم"],
                              "جنبًا_إلى_جنب_بالأنصاف": side}
if "دمج" in RES and "دمج_بالصيغة_أ_للعلم" not in RES:
    RES["دمج_سابق_بالصيغة_أ_من_unseen_run"] = RES.pop("دمج")
RES["دمج"] = MERGE["ب"]
RES["دمج_بالصيغة_أ_للعلم"] = MERGE["أ"]
RES["ملاحظة_الارتباط"] = ("414 في «استراتيجيّات» من unseen_run = الصيغة (أ) (بدأ قبل تعديل PEERS في 16:10:59)؛ "
                          "الدمج الرسميّ هنا بالصيغة (ب) الحيّة.")
json.dump(RES, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"414_أ": [[t[0], t[1], round(t[2], 5), t[3], t[4], round(t[5], 3)] for t in BASES["أ"]],
           "414_ب": [[t[0], t[1], round(t[2], 5), t[3], t[4], round(t[5], 3)] for t in BASES["ب"]]},
          open(os.path.join(HERE, sys.argv[1].replace(".json", "_414_trades.json")), "w", encoding="utf-8"),
          ensure_ascii=False)
print("تمّ: %.0f ث" % (time.time() - T0), flush=True)
