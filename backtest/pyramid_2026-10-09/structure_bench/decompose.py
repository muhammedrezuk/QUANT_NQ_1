# -*- coding: utf-8 -*-
"""سؤال المالك: «ليش ما عم تضرب هدف ثالث — نقطة الدخول أم إدارة الصفقة أم التحليل؟» — تشريحٌ على شموع الدقيقة.

لكلّ صفقة (الدخول · الوقف · الجهة · R) ننظر في ما فعله السعر حتّى نهاية يوم نيويورك (16:00) **بلا أيّ إدارة**:
  التحليل: هل بلغ السعر في جهة الصفقة 3R أصلًا قبل نهاية اليوم (بلا وقف)؟ — إن لم يبلغ فالهدف أبعد من حركة السوق أو الجهة خطأ.
  الإدارة: من الصفقات التي انتهت «الهدف الأوّل ثمّ التعادل» أو «الهدفان ثمّ وقف الأوّل»: كم كانت ستبلغ 3R قبل الوقف الأصليّ؟
  الدخول: من الصفقات التي ضربت الوقف الأصليّ: كم بلغت 3R بعده (فالفكرة صحيحة والتوقيت مبكّر)؟ وكم ذهب السعر ضدّها
          قبل أن يبلغ 1R معها (أقصى معاكسة بـR)؟
المجموعات: البطاقة 414 على سنتين (card_prob_trades.json) · كسرات 15د · كسر كاذب 5د (قياس الليلة).
"""
import bisect
import json
import pathlib
import statistics as st
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import eval_structure as E

NY = ZoneInfo("America/New_York")


def day_end(t):
    lt = datetime.fromtimestamp(t, NY)
    end = lt.replace(hour=16, minute=0, second=0, microsecond=0)
    if lt >= end:
        end = end.replace(day=lt.day)  # بعد الإغلاق: نهاية اليوم نفسه (لا ننظر في الغد)
    return end.timestamp()


def path_stats(entry, stop, buy, t0):
    """على الدقائق من الدخول حتّى 16:00 نيويورك: (بلغ 3R؟ · بلغ 3R قبل الوقف الأصليّ؟ · ضرب الوقف ثمّ بلغ 3R؟ · أقصى معاكسة قبل 1R)."""
    risk = abs(entry - stop)
    sgn = 1 if buy else -1
    k = bisect.bisect_left(E.MT, t0)
    end = day_end(t0)
    hit3 = hit3_before_stop = stopped = stop_then3 = False
    hit1 = False
    mae = 0.0
    while k < len(E.M1) and E.M1[k][0] < end:
        _, o, h, lo, c = E.M1[k]
        fav = ((h - entry) if buy else (entry - lo)) / risk
        adv = ((entry - lo) if buy else (h - entry)) / risk
        if not hit1:
            mae = max(mae, adv)
            if fav >= 1:
                hit1 = True
        if not stopped and adv >= 1:
            stopped = True
        if fav >= 3:
            hit3 = True
            if not stopped:
                hit3_before_stop = True
            elif stopped:
                stop_then3 = True
            break
        k += 1
    return hit3, hit3_before_stop, stop_then3, mae


def analyse(name, trades):
    n = len(trades)
    if n == 0:
        return None
    rows = []
    for tr in trades:
        rows.append((tr,) + path_stats(tr["entry"], tr["stop"], tr["buy"], tr["t"]))
    stage_of = lambda tr: tr.get("stage")
    reach3_any = sum(1 for r in rows if r[1]) / n
    mgmt = [r for r in rows if stage_of(r[0]) in (1, 2)]
    stopped = [r for r in rows if stage_of(r[0]) == 0]
    t3 = sum(1 for r in rows if stage_of(r[0]) == 3) / n
    res = {
        "المجموعة": name, "صفقات": n, "الهدف_الثالث_الفعليّ": round(t3, 3),
        "التحليل: بلغ 3R في جهتها قبل نهاية اليوم (بلا وقف)": round(reach3_any, 3),
        "الإدارة: من «هدف أوّل ثمّ رجوع» كم بلغ 3R قبل الوقف الأصليّ": round(sum(1 for r in mgmt if r[2]) / len(mgmt), 3) if mgmt else None,
        "عدد صفقات الرجوع": len(mgmt),
        "الدخول: من الموقوفة كم بلغ 3R بعد الوقف": round(sum(1 for r in stopped if r[3]) / len(stopped), 3) if stopped else None,
        "عدد الموقوفة": len(stopped),
        "أقصى معاكسة قبل 1R (الوسيط بـR)": round(st.median(r[4] for r in rows), 2),
    }
    return res


def load_414():
    p = pathlib.Path(r"C:\Users\NQ\QUANT_NQ\backtest\card_414\نتائج\card_prob_trades.json")
    d = json.load(open(p, encoding="utf-8"))
    x = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
    out = []
    for t in x:
        r = t["r"]
        rr = t["rr"]
        # المرحلة من R بأثلاث المالك (هدفٌ بنسبة rr): −1 · ≈ rr/9 · ≈ 4rr/9 · ≈ 2rr/3
        stage = 0 if r < -0.5 else (3 if r > 0.55 * rr else (2 if r > 0.3 * rr else 1))
        out.append({"t": t["t"], "buy": bool(t["buy"]), "entry": t["entry"], "stop": t["stop"], "stage": stage,
                    "window": t["window"]})
    return out


def from_mid(fname, key):
    d = json.load(open(E.D / fname, encoding="utf-8")).get(key, [])
    out = []
    for tr in d:
        # الدخول عند إغلاق شمعة الحدث، والوقف من R المحفوظ: نعيد بناءه من سعر الدقيقة
        c, _ = E.close_at(tr["t"])
        if c is None:
            continue
        stop = c - tr["risk"] if tr["buy"] else c + tr["risk"]
        out.append({"t": tr["t"], "buy": tr["buy"], "entry": c, "stop": stop, "stage": tr["stage"]})
    return out


if __name__ == "__main__":
    t414 = load_414()
    sets = {
        "414 لندن (سنتان)": [t for t in t414 if t["window"].startswith("london")],
        "414 نيويورك (سنتان)": [t for t in t414 if t["window"].startswith("ny")],
        "كسر 15د عرض 2 (من 2018)": from_mid("mid_trades.json", "15m_lb2_bos_none"),
        "كسر كاذب 5د عرض 2 (من 2018)": from_mid("liq_trades.json", "5m_lb2_false_break_none"),
    }
    out = []
    for name, tr in sets.items():
        r = analyse(name, tr)
        if r:
            out.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    json.dump(out, open(E.D / "decompose.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
