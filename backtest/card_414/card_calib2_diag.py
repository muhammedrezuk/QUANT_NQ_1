# -*- coding: utf-8 -*-
"""تشخيصٌ لا اقتراح: لماذا رفعت «المسافة حتّى نهاية اليوم» نتيجة الاختبار؟
  أ) لكلّ جلسة: سقف المسافة المقيس (المئين 70 حتّى نهاية اليوم) بالنقاط مقابل 3R المطلوبة، على لحظات زناد البطاقة.
  ب) أعمدة الجلسات وأنصافها في التجربة المختارة (q=70 حتّى نهاية اليوم) مقابل المرجع.
  ج) لندن وحدها بالعيار المرجعيّ (n=2 · c=1.5) — لفصل أثر «خلوّ نيويورك» عن أثر السقف داخل لندن.
"""
import json

import numpy as np

import card_calib2 as C
import card_replay as R


def by_session(tr):
    out = {}
    for w in ("london_peak", "ny_open"):
        out[w] = R.stats([x for x in tr if x[2] == w])
    return out


if __name__ == "__main__":
    res = {}
    # أ) السقف المقيس مقابل 3R على كلّ لحظات الزناد (بلا شرط الانشغال)
    for w in ("london_peak", "ny_open"):
        caps, need, ok = [], [], 0
        for tr in C.triggers:
            kw = tr["kw"]
            if kw["window"] != w:
                continue
            arr, src = tr["pools"][60]["eod"]
            card = C.CT.evaluate(**kw)
            if "risk" not in card or arr is None:
                continue
            cap = float(np.percentile(arr, 70)) * kw["atr_5m"]
            caps.append(cap); need.append(3 * card["risk"]); ok += cap >= 3 * card["risk"]
        res["سقف_مقابل_3R_" + w] = {"لحظات": len(caps), "وسيط_السقف_نقاط": round(float(np.median(caps)), 1),
                                    "وسيط_3R_نقاط": round(float(np.median(need)), 1), "السقف≥3R": ok}
        C.log("أ) %s: %s" % (w, res["سقف_مقابل_3R_" + w]))
    C.REF = C.summary(C.run()[0])
    ref_tr, _ = C.run()
    q_tr, _ = C.run(q=70, hz="eod")
    res["مرجع_بالجلسة"] = by_session(ref_tr)
    res["q70_eod_بالجلسة"] = by_session(q_tr)
    for k in ("مرجع_بالجلسة", "q70_eod_بالجلسة"):
        for w, s in res[k].items():
            C.log("ب) %s %s: n=%s R=%s R/ص=%s أنصاف=%s" % (k, w, s.get("n"), s.get("R"), s.get("R/صفقة"), s.get("أنصاف")))
    # ج) لندن وحدها بالعيار المرجعيّ
    keep = C.triggers
    C.triggers = [t for t in keep if t["kw"]["window"] == "london_peak"]
    lon_tr, _ = C.run()
    C.triggers = keep
    s = C.summary(lon_tr)
    s["قبول"], s["فحوص"] = C.accept(s)
    res["لندن_وحدها_مرجعيّ"] = s
    C.log("ج) " + C.line("لندن وحدها (مرجعيّ)", s), "| قبول:", s["قبول"])
    json.dump(res, open("card_calib2_diag.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    C.log("كُتب card_calib2_diag.json")
