# -*- coding: utf-8 -*-
"""يجمع results_two + results_five + الدمج + التدقيقات في results.json واحد، ومعه جدول اتّساق الشبكة بين الفترتين."""
import sys
import os
import json
import statistics as st

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
L = lambda n: json.load(open(os.path.join(HERE, n), encoding="utf-8"))
two, five, comb = L("results_two.json"), L("results_five.json"), L("combine_noise.json")


def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
    for p, i in enumerate(o):
        r[i] = p
    return r


def key(r):
    return (r["ي"], r["م"], r["الوقف"], r["السياق"], r["ج"])


consistency = {}
for leg in ("نيويورك", "لندن", "كلاهما"):
    t = {key(r): r for r in two[leg]["التركيبات"] if r["في_الشبكة"]}
    f = {key(r): r for r in five[leg]["الشبكة_للعلم"]}
    ks = list(t)
    Lr = [t[k]["تعلّم"].get("R/صفقة") or 0 for k in ks]
    Tr = [t[k]["اختبار"].get("R/صفقة") or 0 for k in ks]
    Fr = [f[k]["كلّه"].get("R/صفقة") or 0 for k in ks]
    consistency[leg] = {
        "يجتاز_السنتين": [list(k) for k in ks if t[k]["معيار_المالك"]["يجتاز"]],
        "يجتاز_الخمس": [list(k) for k in ks if f[k]["معيار_المالك"]["يجتاز"]],
        "يجتاز_الاثنين": [list(k) for k in ks if t[k]["معيار_المالك"]["يجتاز"] and f[k]["معيار_المالك"]["يجتاز"]],
        "اختبار_موجب_وخمس_موجبة": sum(1 for a, b in zip(Tr, Fr) if a > 0 and b > 0),
        "ارتباط_رتب_تعلّم_خمس": round(st.correlation(rank(Lr), rank(Fr)), 2),
        "ارتباط_رتب_اختبار_خمس": round(st.correlation(rank(Tr), rank(Fr)), 2),
        "ارتباط_رتب_تعلّم_اختبار": round(st.correlation(rank(Lr), rank(Tr)), 2)}

out = {"الاستراتيجيّة": "منطقة الضجيج للزخم داخل اليوم (زاراتيني وعزيز وباربون ٢٠٢٤) — بطاقة بقوانين المالك",
       "تعريف": two["تعريف"], "ثوابت": two["ثوابت"],
       "الشبكة": "ي{10,14,20} × م{1.0,1.25} × الوقف{مقابل,افتتاح} × السياق{أيّ,اتّفاق} × ج{1.0,1.5} = 48؛ "
                 "والوقف «مرجّح» (متوسّط السعر المرجّح بـtick_volume) 24 ضابطًا للعلم لا تدخل الاختيار",
       "الأرجل": {"نيويورك": "افتتاح 09:30 نيويورك في نافذة افتتاح أمريكا (الأصل)",
                  "لندن": "افتتاح 08:00 لندن في نافذة ذروة لندن (البديل)",
                  "كلاهما": "الرجلان معًا بمركزٍ واحد، كلٌّ بافتتاحه"},
       "السنتان": {k: two[k] for k in ("البداية", "النهاية", "حدّ_التعلّم", "أيّام_عمل", "أيّام_عمل_تعلّم_اختبار",
                                       "أيّام_صالحة", "قرارات", "المختارات")},
       "الخمس": {k: five[k] for k in ("البداية", "النهاية", "أيّام_عمل", "أيّام_صالحة", "قرارات")},
       "اتّساق_الشبكة_بين_الفترتين": consistency,
       "الدمج_مع_414_على_السنتين": comb,
       "التدقيق": {"نسخة_الشموع=الأصل": open(os.path.join(HERE, "check_pdata.log"), encoding="utf-8").read().strip().splitlines()[-2:],
                   "تدقيق_SQL_المستقلّ": open(os.path.join(HERE, "audit_sql.log"), encoding="utf-8").read().strip()}}
for leg in ("نيويورك", "لندن", "كلاهما"):
    out["السنتان"][leg] = two[leg]
    out["الخمس"][leg] = five[leg]
json.dump(out, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(consistency, ensure_ascii=False))
print("results.json: %.0f ك.ب" % (os.path.getsize(os.path.join(HERE, "results.json")) / 1024))
