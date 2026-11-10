# -*- coding: utf-8 -*-
"""تحقّقٌ مستقلّ على فترةٍ لم يرها أيّ قياس — بالعيارات المختارة نفسها بلا أيّ إعادة ضبط. قياسٌ فقط.

المسطرة: نسخ أدوات card_414 في هذا المجلّد (التغيير الوحيد: البداية والنهاية من UNSEEN_START/UNSEEN_END).
الاستراتيجيّات: تُحمَّل من ملفّاتها الأصليّة كما هي (لا نسخ ولا تعديل) — دوالّها run بالعيار المختار وحده.
الاستعمال: python unseen_run.py <ملفّ_الإخراج.json> [البداية] [آخر يوم]
"""
import sys
sys.dont_write_bytecode = True            # لا ذاكرة بايت في أيّ مجلّد (ولا داخل المشروع)
sys.stdout.reconfigure(encoding="utf-8")

import bisect
import calendar
import importlib.util
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone, timedelta

T0 = time.time()
# البداية والنهاية من سطر الأمر (تُمرَّر لنسخة المسطرة عبر بيئة هذه العمليّة وحدها):
#   unseen_run.py <ملفّ_الإخراج> [البداية YYYY-MM-DD] [آخر يوم YYYY-MM-DD]
os.environ.pop("UNSEEN_START", None); os.environ.pop("UNSEEN_END", None)
if len(sys.argv) > 2:
    os.environ["UNSEEN_START"] = sys.argv[2]
if len(sys.argv) > 3:
    os.environ["UNSEEN_END"] = sys.argv[3]
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)              # مجلّد الاستراتيجيّات
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, HERE)

import card_replay as R                   # النسخة القابلة للضبط (تحمّل البيانات عند الاستيراد)
import card_replay_shared as S
import card_variants as V
import card_final_check as FC
for _m in (R, S, V, FC):
    assert os.path.dirname(os.path.abspath(_m.__file__)) == HERE, _m.__file__


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    assert mod.R is R, name               # الاستراتيجيّة تقرأ المسطرة نفسها (النسخة القابلة للضبط)
    return mod


fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")
print("الفترة: %s ⟶ %s (حصريّ) · آخر دقيقة محمّلة %s · آخر 5 د %s" % (
    fmt(R.START), fmt(R.END), fmt(R.m1[-1][0]), fmt(R.m5[-1][0])), flush=True)

# ───────────── التقسيمات ─────────────
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
    """tr: صفوف (t_close, r, النافذة, شراء؟, ن.أ, ...) بترتيب الزمن."""
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
        y = datetime.fromtimestamp(x[0], timezone.utc).year
        years.setdefault(y, []).append(x)
    rpt = st["R/صفقة"]; pf = st["معامل"] or 0
    verdict = {"R/صفقة>0": rpt > 0, "معامل≥1.15": pf >= 1.15, "أنصاف≥7من10": pos >= 7}
    return {"كلّه": {k: st[k] for k in ("n", "R", "R/صفقة", "معامل", "سحب_R", "فوز%", "وقف_ن.أ_وسيط")},
            "أنصاف_عشرة": {lab: {"R": round(v, 1), "n": n} for lab, v, n in zip(HALF_LABELS, halves, hn)},
            "أنصاف_موجبة": "%d/%d" % (pos, len(HALF_LABELS)),
            "أنصاف_تقويميّة": st["أنصاف"],
            "سنويًّا": {str(y): brief(v) for y, v in sorted(years.items())},
            "صفقات/يوم": round(len(tr) / DAYS, 3),
            "لندن": brief([x for x in tr if x[2] == "london_peak"]),
            "نيويورك": brief([x for x in tr if x[2] == "ny_open"]),
            "شراء": brief([x for x in tr if x[3]]), "بيع": brief([x for x in tr if not x[3]]),
            "شروط": verdict, "يثبت": all(verdict.values())}


def audit(name, tr, with_exit=True):
    """فحوص سببيّة: لا دخول خارج الفترة · الخروج بعد الدخول · لا تداخل مراكز · لا نهاية بيانات مبتورة."""
    bad = {"قبل_البداية": 0, "بعد_النهاية": 0, "خروج_قبل_الدخول": 0, "تداخل": 0}
    for x in tr:
        bad["قبل_البداية"] += x[0] < R.START
        bad["بعد_النهاية"] += x[0] > R.END
        if with_exit:
            bad["خروج_قبل_الدخول"] += x[5] < x[0]
    if with_exit:
        s = sorted(tr, key=lambda x: x[0])
        for a, b in zip(s, s[1:]):
            bad["تداخل"] += b[0] < a[5] + 60
    last = max((x[0] for x in tr), default=None)
    out = {**bad, "آخر_دخول": fmt(last) if last else None}
    print("  تدقيق %s: %s" % (name, out), flush=True)
    return out


def as_rows(tr):
    """(t_close, r, win, buy, bps, exit_t) ⟶ صيغة combine: [t_close, exit_t, r, win, buy, bps]."""
    return [[x[0], x[5], x[1], x[2], x[3], x[4]] for x in tr]


RES = {"الفترة": {"البداية": fmt(R.START), "النهاية_حصريّة": fmt(R.END), "أيّام_عمل": DAYS,
                 "أنصاف": HALF_LABELS, "آخر_دقيقة_محمّلة": fmt(R.m1[-1][0])},
       "بيانات": {"دقيقة": len(R.m1), "5د": len(R.m5), "ساعة": len(R.h1), "4س": len(R.h4), "يوم": len(R.d1),
                  "أخبار_بعد_البداية_قبل_النهاية": sum(1 for t in R.news if R.START <= t < R.END)},
       "استراتيجيّات": {}, "تدقيق": {}, "عدّادات": {}, "دمج": {}}
TR = {}


def record(name, tr, tally=None, with_exit=True):
    TR[name] = tr
    RES["استراتيجيّات"][name] = summary(tr)
    RES["تدقيق"][name] = audit(name, tr, with_exit)
    if tally is not None:
        RES["عدّادات"][name] = {k: v for k, v in dict(tally).items()}
    s = RES["استراتيجيّات"][name]
    print("%-28s | n=%s R=%s R/ص=%s معامل=%s سحب=%s فوز=%s | أنصاف موجبة %s | ص/يوم %s | يثبت=%s | %.0f ث" % (
        name, s["كلّه"].get("n"), s["كلّه"].get("R"), s["كلّه"].get("R/صفقة"), s["كلّه"].get("معامل"),
        s["كلّه"].get("سحب_R"), s["كلّه"].get("فوز%"), s.get("أنصاف_موجبة"), s.get("صفقات/يوم"), s.get("يثبت"),
        time.time() - T0), flush=True)


# ───────────── 1) البطاقة 414 (المرجع) ─────────────
CB = load("combine_unseen", os.path.join(BASE, "combine.py"))
base = CB.card414()                                   # [t_close, exit_t, r, window, buy, bps] — بحكم الإرسال الصافي
record("414", [(t[0], t[2], t[3], t[4], t[5], t[1]) for t in base])
tr_fc, tally_fc = FC.run()                            # للعلم: بلا حكم الإرسال الصافي (card_final_check كما هو)
record("414_بلا_حكم_الإرسال_للعلم", tr_fc, tally_fc, with_exit=False)

# ───────────── 2) التذبذب ─────────────
SQ = load("squeeze_unseen", os.path.join(BASE, "squeeze", "squeeze.py"))
tr, tl = SQ.run(12, 0.15, "مقابل", "اتّفاق", 1.5)
record("التذبذب", tr, tl)
tr, tl = SQ.run(12, 0.25, "مقابل", "اتّفاق", 1.5)
record("التذبذب_الضابط_ق0.25_للعلم", tr, tl)

# ───────────── 3) اختراق الافتتاح ─────────────
OB = load("orb_unseen", os.path.join(BASE, "orb", "orb_measure.py"))
ev, evt = OB.build_events(15)
RES["عدّادات"]["زنادات_الافتتاح_د15"] = evt
tr, why = OB.run(ev, "mid", 1.0, 2, 1.0)
record("اختراق_الافتتاح", tr, why)

# ───────────── 4) الانعكاس ─────────────
RV = load("reversion_unseen", os.path.join(BASE, "reversion", "reversion.py"))
tr, tl = RV.run("يوم_سابق", 0.5, 0.25, 1.0, "أيّ")
record("الانعكاس", tr, tl)
tr, tl = RV.run("متوسّط", 0.5, 0.25, 1.0, "ضدّ_المتّفق")
record("الانعكاس_عائلة_المتوسّط_للعلم", tr, tl)

# ───────────── 5) الكنس ثمّ العودة ─────────────
SW = load("sweep_unseen", os.path.join(BASE, "sweep", "sweep_card.py"))
ev, both = SW.precompute(True)
RES["عدّادات"]["أحداث_الكنس"] = {"كلّها": len(ev), "الجهتان_معًا": both}
tr, rej = SW.run(ev, 0.0, 2.0, 1.5, "ضدّ", True)
record("الكنس_ثمّ_العودة", tr, rej)

# ───────────── الدمج: 414 + كلّ واحدة (مركزٌ واحد، الأسبق أوّلًا — CB.merge كما هو) ─────────────
for name in ("التذبذب", "اختراق_الافتتاح", "الانعكاس", "الكنس_ثمّ_العودة",
             "التذبذب_الضابط_ق0.25_للعلم", "الانعكاس_عائلة_المتوسّط_للعلم"):
    merged = CB.merge(base, as_rows(TR[name]))        # (t_close, r, win, buy, bps, src)
    key = "414 + " + name
    RES["دمج"][key] = {**summary(merged), "من_الأخرى": sum(1 for x in merged if x[5] == 1)}
    s = RES["دمج"][key]
    print("%-36s | n=%s (من الأخرى %s) R=%s R/ص=%s معامل=%s سحب=%s | أنصاف موجبة %s | ص/يوم %s | يثبت=%s" % (
        key, s["كلّه"].get("n"), s["من_الأخرى"], s["كلّه"].get("R"), s["كلّه"].get("R/صفقة"),
        s["كلّه"].get("معامل"), s["كلّه"].get("سحب_R"), s["أنصاف_موجبة"], s["صفقات/يوم"], s["يثبت"]), flush=True)

out_name = sys.argv[1] if len(sys.argv) > 1 else "results.json"
json.dump(RES, open(os.path.join(HERE, out_name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({k: [[x[0], (x[5] if len(x) > 5 else None), round(x[1], 5), x[2], x[3], round(x[4], 3)] for x in v]
           for k, v in TR.items()},
          open(os.path.join(HERE, out_name.replace(".json", "_trades.json")), "w", encoding="utf-8"), ensure_ascii=False)
print("تمّ: %.0f ث" % (time.time() - T0), flush=True)
