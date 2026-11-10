# -*- coding: utf-8 -*-
"""الحيّ = المقيس؟ — شموع الأربع ساعات واليوم في قاعدة التاريخ على ساعة خادم الوسيط (تبدأ 01/05/09… غرينتش
صيفًا، واليوم 21:00/22:00)، وباني الشموع الحيّ 103 يبنيها على غرينتش (00/04/08…، واليوم 00:00).
هنا تُبنى الأربع ساعات واليوم **من شموع الساعة على غرينتش** كما يبنيها الحيّ، ثمّ تُعاد البطاقة بقلبها نفسه:
  (1) بلا حكم الإرسال · (2) بحكم الإرسال (نسبةٌ صافية بعد سبريد نقطة)."""
import os
import sys

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_replay as R

_orig_bars = R.bars


def utc_bars(period, since):
    """الأربع ساعات واليوم من شموع الساعة في دلاء غرينتش (period_start % الطول == 0)."""
    if period not in ("H4", "D1"):
        return _orig_bars(period, since)
    seconds = 14400 if period == "H4" else 86400
    h1 = _orig_bars("H1", since - seconds)
    out, cur = [], None
    for t, o, h, l, c in h1:
        b = t - (t % seconds)
        if cur is None or cur[0] != b:
            if cur is not None:
                out.append(tuple(cur))
            cur = [b, o, h, l, c]
        else:
            cur[2], cur[3], cur[4] = max(cur[2], h), min(cur[3], l), c
    if cur is not None:
        out.append(tuple(cur))
    return [r for r in out if r[0] >= since]


R.bars = utc_bars
R.h4 = R.bars("H4", R.START - 300 * 86400)
R.d1 = R.bars("D1", R.START - 400 * 86400)
R.th4 = [r[0] for r in R.h4]
R.td1 = [r[0] for r in R.d1]
R.e_h4 = R.ema([r[4] for r in R.h4])
R.ad1 = R.atr(R.d1)
R.sw_htf = sorted(R.swings(R.h1, 3600) + R.swings(R.h4, 14400))
R.swh_t = [s[0] for s in R.sw_htf]
print("بناء غرينتش: 4س=%d يوم=%d · أوّل 4س يبدأ %s" % (len(R.h4), len(R.d1), R.h4[-1][0] % 14400), flush=True)

import card_replay_shared as S      # noqa: E402  (يبني سلّم الأربع ساعات من R.h4 المبنيّ أعلاه)
import card_variants as V           # noqa: E402  (الأسواق المرتبطة تُحمَّل عبر R.bars المبدَّلة)
import card_final_check as F        # noqa: E402
import card_send_ratio as SR        # noqa: E402

if __name__ == "__main__":
    import json
    split = R.START + 0.7 * (R.END - R.START)
    out = {}
    tr, tally = F.run()
    out["بلا_حكم_الإرسال"] = {"كلّه": R.stats(tr), "تعلّم": R.stats([x for x in tr if x[0] < split]),
                              "اختبار": R.stats([x for x in tr if x[0] >= split]),
                              "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
                              "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"])}
    tr2, rej = SR.run("a", 1.0)
    out["بحكم_الإرسال_س1"] = {"مردود": rej, "كلّه": R.stats(tr2), "تعلّم": R.stats([x for x in tr2 if x[0] < split]),
                              "اختبار": R.stats([x for x in tr2 if x[0] >= split]),
                              "لندن": R.stats([x for x in tr2 if x[2] == "london_peak"]),
                              "نيويورك": R.stats([x for x in tr2 if x[2] == "ny_open"])}
    for k, s in out.items():
        print("%s | n=%s R=%s R/ص=%s معامل=%s سحب=%s أنصاف=%s | تعلّم %s | اختبار n=%s %s معامل=%s" % (
            k, s["كلّه"].get("n"), s["كلّه"].get("R"), s["كلّه"].get("R/صفقة"), s["كلّه"].get("معامل"),
            s["كلّه"].get("سحب_R"), s["كلّه"].get("أنصاف"), s["تعلّم"].get("R/صفقة"), s["اختبار"].get("n"),
            s["اختبار"].get("R/صفقة"), s["اختبار"].get("معامل")), flush=True)
    json.dump(out, open("card_live_align.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
