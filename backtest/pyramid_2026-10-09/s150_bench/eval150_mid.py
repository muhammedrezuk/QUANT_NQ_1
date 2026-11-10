# -*- coding: utf-8 -*-
"""وسط الهرم لقسم 150: هل تحسّن حقيقة المحلّل (بكوده، على الخمس/الربع ساعة، عند لحظة الدخول) صفقاتِ الإعداد؟

الصفقات الأساس (بلا انتقاء، كي لا نختار على الضجيج): كسرات البنية وكنس السيولة من القياسين السابقين
(أثلاث المالك · وقف 15–50 نقطة · 3R · نافذتاه · من 2018، تعلّم حتّى 2024-02-19).
لكلّ حقل: الصفقات تُقسم — الاتّجاهيّ: «توافق جهة الصفقة» / «تخالفها»؛ الفئويّ: بقيمته؛ الرقميّ: بثُلثيّات التعلّم —
ويُقارن R للصفقة ونسبة الهدف الثالث في كلّ قسمٍ بالباقي (ويلش t)، تعلّمًا ثمّ اختبارًا.
الاجتياز: القسم نفسه أفضل من الباقي بـ t ≥ 2 في الفترتين.
"""
import bisect
import json
import math
import pathlib
import statistics as st
from collections import defaultdict

# الدالّة نفسها التي حكمت على القمّة (منسوخة: استيراد eval150_top يعيد حسابه كلّه)
UP = ("up", "bull", "above", "strong_up", "rising", "gap_up", "leader", "strong", "bullish")
DOWN = ("down", "bear", "below", "strong_down", "falling", "gap_down", "laggard", "weak", "bearish")
SKIP = {"t", "status", "m.timeframe", "m.method", "m.twin", "m.period_start", "m.candles", "m.close",
        "m.ema_fast", "m.ema_slow", "m.roc_period", "m.ema_fast_value", "m.ema_slow_value", "m.atr", "m.atr_14",
        "m.baseline_atr", "m.range", "m.stddev", "m.hour_utc", "m.hour", "m.utc_offset_new_york_h",
        "m.utc_offset_london_h", "m.pattern_score"}


def direction(field, v):
    if isinstance(v, str):
        s = v.lower()
        if any(s == u or s.startswith(u + "_") or s.endswith("_" + u) for u in UP):
            return 1
        if any(s == w or s.startswith(w + "_") or s.endswith("_" + w) for w in DOWN):
            return -1
        return 0
    if isinstance(v, (int, float)):
        if any(k in field for k in ("pct_rank", "persistence", "percentile", "rank")):
            return 1 if v > 0.5 else (-1 if v < 0.5 else 0)
        if any(k in field for k in ("distance", "slope", "roc", "gap_pct", "relative", "excess", "return")):
            return 1 if v > 0 else (-1 if v < 0 else 0)
    return 0

D = pathlib.Path(__file__).resolve().parent
SB = D.parent / "structure_bench"
SPLIT = 1708300800.0  # 2024-02-19 (70٪ من 2018-01 ⟵ 2026-10)

BASES = {
    "كسر_15د_عرض2": ("mid_trades.json", "15m_lb2_bos_none", "15m"),
    "كسر_5د_عرض2": ("mid_trades.json", "5m_lb2_bos_none", "5m"),
    "تغيّر_15د_عرض3": ("mid_trades.json", "15m_lb3_choch_none", "15m"),
    "كنس_كاذب_5د_عرض2": ("liq_trades.json", "5m_lb2_false_break_none", "5m"),
    "كنس_كاذب_15د_عرض2": ("liq_trades.json", "15m_lb2_false_break_none", "15m"),
}


def welch(a, b):
    if len(a) < 25 or len(b) < 25:
        return None
    va, vb = st.pvariance(a), st.pvariance(b)
    se = math.sqrt(va / len(a) + vb / len(b))
    return round((st.mean(a) - st.mean(b)) / se, 2) if se > 0 else None


def load_facts(path):
    recs = [json.loads(l) for l in open(path, encoding="utf-8")]
    recs = [r for r in recs if r.get("t")]
    return recs, [r["t"] for r in recs]


def main():
    trades_cache = {}
    out, passed, tested = [], [], 0
    for base, (fname, key, frame) in BASES.items():
        if fname not in trades_cache:
            p = SB / fname
            trades_cache[fname] = json.load(open(p, encoding="utf-8")) if p.exists() else {}
        trades = trades_cache[fname].get(key, [])
        if len(trades) < 100:
            print("أساسٌ قليل:", base, len(trades))
            continue
        for fp in sorted((D / "facts_mid").glob(f"*_{frame}.jsonl")):
            recs, times = load_facts(fp)
            if not recs:
                continue
            fields = sorted({k for r in recs[-3000:] for k in r} - SKIP)
            for f in fields:
                rows = []
                for tr in trades:
                    i = bisect.bisect_right(times, tr["t"]) - 1
                    if i < 0:
                        continue
                    v = recs[i].get(f)
                    if v is None:
                        continue
                    dd = direction(f, v)
                    if dd != 0:
                        g = "توافق" if (dd > 0) == tr["buy"] else "تخالف"
                    elif isinstance(v, str):
                        g = v
                    elif isinstance(v, (int, float)):
                        g = v
                    else:
                        continue
                    rows.append((tr, g))
                if len(rows) < 100:
                    continue
                numeric = all(isinstance(g, (int, float)) for _, g in rows)
                if numeric:
                    tv = sorted(g for tr, g in rows if tr["t"] < SPLIT)
                    if len(tv) < 60:
                        continue
                    q1, q2 = tv[len(tv) // 3], tv[2 * len(tv) // 3]
                    rows = [(tr, "ثلث_أدنى" if g <= q1 else ("ثلث_أوسط" if g <= q2 else "ثلث_أعلى")) for tr, g in rows]
                groups = sorted({g for _, g in rows}, key=str)
                for g in groups:
                    res = {"base": base, "facts": fp.stem, "field": f, "group": g}
                    ok = True
                    for part, sel in (("train", lambda x: x["t"] < SPLIT), ("test", lambda x: x["t"] >= SPLIT)):
                        ing = [tr["R"] for tr, gg in rows if gg == g and sel(tr)]
                        rest = [tr["R"] for tr, gg in rows if gg != g and sel(tr)]
                        t3 = [tr for tr, gg in rows if gg == g and sel(tr)]
                        res[part] = {"n": len(ing), "R": round(st.mean(ing), 4) if ing else None,
                                     "R_rest": round(st.mean(rest), 4) if rest else None, "t": welch(ing, rest),
                                     "t3%": round(sum(1 for x in t3 if x["stage"] == 3) / len(t3), 3) if t3 else None}
                        ok = ok and res[part]["t"] is not None
                    if not ok:
                        continue
                    tested += 1
                    out.append(res)
                    if res["train"]["t"] >= 2 and res["test"]["t"] >= 2:
                        passed.append(res)
    json.dump(out, open(D / "mid150.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"اختُبر {tested} — اجتاز t≥2 في الفترتين: {len(passed)} (المتوقّع بالصدفة ≈ {tested * 0.023 * 0.023:.1f})")
    for r in passed:
        print("  ", r["base"], r["facts"], r["field"], r["group"], "تعلّم", r["train"], "اختبار", r["test"])
    best = sorted(out, key=lambda r: -min(r["train"]["t"], r["test"]["t"]))[:8]
    print("أقربها:")
    for r in best:
        print("  ", r["base"], r["facts"], r["field"], r["group"], "تعلّم", r["train"], "اختبار", r["test"])


if __name__ == "__main__":
    main()
