# -*- coding: utf-8 -*-
"""التشريح قال «الدخول» في لندن والكسر الكاذب: نصف الموقوفة بلغت 3R بعد الوقف، ووسيط المعاكسة قبل 1R = 0.85–1.0R.
فالسؤال: لو انتظرنا «السعر المثاليّ» (كلام المالك) — أمرٌ معلّق أعمق بـ x من مسافة الوقف — والوقف نفسه مكانه
(من التحليل، لا يُقصّ)، والهدف 3R من سعر الدخول الجديد، والإدارة أثلاث المالك كما هي؟
لا يُنفَّذ الأمر إن لم يلمسه السعر خلال W دقيقة (قبل الوقف). يُختار x وW على التعلّم وحده.
"""
import bisect
import json
import statistics as st
from collections import defaultdict

import eval_structure as E
from decompose import load_414, from_mid

XS = (0.0, 0.25, 0.5, 0.75)
WS = (15, 60)


def fill_and_manage(tr, x, w):
    e0, s, buy = tr["entry"], tr["stop"], tr["buy"]
    r0 = abs(e0 - s)
    sgn = 1 if buy else -1
    lim = e0 - sgn * x * r0
    if x == 0:
        t_fill = tr["t"]
    else:
        k = bisect.bisect_left(E.MT, tr["t"])
        t_fill = None
        while k < len(E.M1) and E.M1[k][0] < tr["t"] + w * 60:
            _, o, h, lo, c = E.M1[k]
            if (lo <= lim) if buy else (h >= lim):
                t_fill = E.M1[k][0]  # الدقيقة التي لمسته — الإدارة تبدأ منها (محافظ: الوقف في الدقيقة نفسها يُحسب)
                break
            k += 1
        if t_fill is None:
            return None
    r1 = abs(lim - s)
    if r1 <= 0:
        return None
    target = lim + sgn * 3 * r1
    R, stage, _ = E.thirds(lim, s, target, buy, t_fill)
    if R is None:
        return None
    return R, stage, r1


def evaluate(name, trades, split):
    out = []
    for x in XS:
        for w in (WS if x > 0 else (0,)):
            res = {"set": name, "x": x, "w": w}
            for part, sel in (("train", lambda t: t["t"] < split), ("test", lambda t: t["t"] >= split)):
                tt = [t for t in trades if sel(t)]
                rs, st3, fills = [], 0, 0
                for t in tt:
                    r = fill_and_manage(t, x, w)
                    if r is None:
                        continue
                    fills += 1
                    rs.append(r[0])
                    st3 += r[1] == 3
                g, l = sum(v for v in rs if v > 0), -sum(v for v in rs if v < 0)
                res[part] = {"setups": len(tt), "fills": fills, "R_per": round(st.mean(rs), 4) if rs else None,
                             "total": round(sum(rs), 1), "pf": round(g / l, 2) if l > 0 else None,
                             "t3%": round(st3 / fills, 3) if fills else None}
            out.append(res)
            a, b = res["train"], res["test"]
            print(f"{name:<26} x={x:<4} w={w:<3} | تعلّم {a['fills']}/{a['setups']} R={a['R_per']} pf={a['pf']} t3={a['t3%']} "
                  f"| اختبار {b['fills']}/{b['setups']} R={b['R_per']} pf={b['pf']} t3={b['t3%']} مجموع={b['total']}", flush=True)
    return out


if __name__ == "__main__":
    t414 = load_414()
    ts = sorted(t["t"] for t in t414)
    split414 = ts[int(len(ts) * 0.7)]
    res = []
    res += evaluate("414 لندن", [t for t in t414 if t["window"].startswith("london")], split414)
    res += evaluate("414 نيويورك", [t for t in t414 if t["window"].startswith("ny")], split414)
    res += evaluate("كسر كاذب 5د (2018+)", from_mid("liq_trades.json", "5m_lb2_false_break_none"), E.SPLIT)
    res += evaluate("كسر 15د (2018+)", from_mid("mid_trades.json", "15m_lb2_bos_none"), E.SPLIT)
    json.dump(res, open(E.D / "entry_limit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
