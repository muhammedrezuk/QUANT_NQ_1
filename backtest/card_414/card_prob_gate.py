# -*- coding: utf-8 -*-
"""احتمال نجاح البطاقة — المرحلة ٣: قاعدة «لا دخول تحت احتمال p» بإعادةٍ كاملة (المتروكة لا تشغل الوقت).

الاحتمال الوحيد الذي اتّفقت جهته بين التعلّم والاختبار: بلوغ الهدف النهائيّ حسب النافذة
(تعلّم: لندن 17.8٪ · نيويورك 5.4٪). فالعتبة الوحيدة ذات المعنى بين القيمتين = «لندن وحدها».
معيار المالك: R/صفقة خارج العيّنة > 0.171 · التعلّم لا يسوء (≥ 0.081) · الأنصاف الخمسة موجبة
· السحب لا يسوء (≤ 13.7R) · العدد لا ينهار.
"""
import json

import card_replay as R
import card_prob_features as P

split = R.START + 0.7 * (R.END - R.START)


def report(tr, skipped):
    tt = P.as_tuples(tr)
    return {"كلّه": R.stats(tt), "تعلّم": R.stats([x for x in tt if x[0] < split]),
            "اختبار": R.stats([x for x in tt if x[0] >= split]), "متروكة": skipped,
            "الهدف_الأوّل%": round(100 * sum(x["hit1"] for x in tr) / len(tr), 1),
            "النهائيّ%": round(100 * sum(x["hit_final"] for x in tr) / len(tr), 1)}


out = {}
for name, take in (("أساس", None), ("لندن_وحدها (احتمال النهائيّ ≥ 10٪)", lambda f: f["window"] == "london_peak")):
    tr, skipped, mismatch = P.run(take)
    out[name] = report(tr, skipped)
    s = out[name]
    print("%-34s | كلّه n=%s R=%s R/ص=%s سحب=%s أنصاف=%s | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | أوّل=%s%% نهائيّ=%s%% متروكة=%s" % (
        name, s["كلّه"]["n"], s["كلّه"]["R"], s["كلّه"]["R/صفقة"], s["كلّه"]["سحب_R"], s["كلّه"]["أنصاف"],
        s["تعلّم"]["n"], s["تعلّم"]["R/صفقة"], s["اختبار"]["n"], s["اختبار"]["R/صفقة"], s["اختبار"]["معامل"],
        s["الهدف_الأوّل%"], s["النهائيّ%"], skipped), flush=True)
json.dump(out, open("card_prob_gate.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
