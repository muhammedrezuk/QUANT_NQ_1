# -*- coding: utf-8 -*-
"""قمّة الهرم لقسم 150: هل تتنبّأ حقيقة المحلّل (بكوده، عند لحظة القرار) بجهة الجلسة؟ — قياسٌ فقط.

لكلّ ملفّ حقائق من run150.py ولكلّ حقلٍ اتّجاهيّ فيه: الجهة d ∈ {+1, −1} عند آخر حقيقةٍ أُغلقت قبل القرار.
المقياس الذي لا يخدعه «اشترِ دائمًا»: الفرق بين متوسّط عائد الجلسة حين d=+1 وحين d=−1 (نقاط أساس) واختبار t
(ويلش)، تعلّمًا (حتّى 2023-02-05) ثمّ اختبارًا. ونسبة الإصابة للعلم. والتقويم (159) بالفئة: عائد الجلسة في كلّ فئة.
لندن: القرار 08:15 ⟵ 11:00 لندن · نيويورك: 09:45 ⟵ 13:00 نيويورك.
"""
import bisect
import json
import math
import pathlib
import sqlite3
import statistics as st
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

D = pathlib.Path(__file__).resolve().parent
START = datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp()  # المالك: «خلّيها من 2018»
END = datetime(2026, 10, 6, tzinfo=timezone.utc).timestamp()
SPLIT = START + 0.7 * (END - START)  # 2024-02-19
LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")
db = sqlite3.connect(r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\ctrader_history.db?mode=ro", uri=True)
M1 = db.execute("select period_start, close from candles_history where symbol='USTEC' and period='M1' and period_start >= ? order by period_start", (int(START),)).fetchall()
MT = [r[0] for r in M1]


def close_at(t):
    i = bisect.bisect_right(MT, t - 60) - 1
    return (M1[i][1], M1[i][0] + 60) if i >= 0 else (None, None)


SESS = []
for d in sorted({datetime.fromtimestamp(t, timezone.utc).date() for t in MT[::60]}):
    if d.weekday() >= 5:
        continue
    for name, tz, dh, dm, eh, em in (("london", LON, 8, 15, 11, 0), ("ny", NY, 9, 45, 13, 0)):
        td = datetime(d.year, d.month, d.day, dh, dm, tzinfo=tz).timestamp()
        te = datetime(d.year, d.month, d.day, eh, em, tzinfo=tz).timestamp()
        c0, k0 = close_at(td)
        c1, k1 = close_at(te)
        if c0 and c1 and k0 >= td - 300 and k1 >= te - 300 and k1 > k0:
            SESS.append((name, td, (c1 - c0) / c0 * 1e4))
print("جلسات", len(SESS), flush=True)

UP = ("up", "bull", "above", "strong_up", "rising", "gap_up", "leader", "strong")
DOWN = ("down", "bear", "below", "strong_down", "falling", "gap_down", "laggard", "weak")
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


def welch(a, b):
    if len(a) < 20 or len(b) < 20:
        return None, None
    ma, mb = st.mean(a), st.mean(b)
    va, vb = st.pvariance(a), st.pvariance(b)
    se = math.sqrt(va / len(a) + vb / len(b))
    return round(ma - mb, 2), round((ma - mb) / se, 2) if se > 0 else None


def evaluate(path):
    recs = [json.loads(l) for l in open(path, encoding="utf-8")]
    recs = [r for r in recs if r.get("t")]
    times = [r["t"] for r in recs]
    fields = sorted({k for r in recs[-2000:] for k in r} - SKIP)
    out = []
    for f in fields:
        for sess in ("london", "ny"):
            parts = {"train": defaultdict(list), "test": defaultdict(list)}
            for name, td, ret in SESS:
                if name != sess:
                    continue
                i = bisect.bisect_right(times, td) - 1
                if i < 0 or td - times[i] > 3 * 86400:
                    continue
                v = recs[i].get(f)
                dd = direction(f, v)
                parts["train" if td < SPLIT else "test"][dd].append(ret)
            row = {"field": f, "session": sess}
            ok = False
            for p in ("train", "test"):
                up, dn = parts[p][1], parts[p][-1]
                diff, t = welch(up, dn)
                agree = (sum(1 for x in up if x > 0) + sum(1 for x in dn if x < 0)) / (len(up) + len(dn)) if up or dn else None
                row[p] = {"n_up": len(up), "n_dn": len(dn), "diff_bps": diff, "t": t,
                          "agree": round(agree, 4) if agree else None}
                ok = ok or (len(up) + len(dn)) > 0
            if ok and row["train"]["t"] is not None:
                out.append(row)
    return out


def evaluate_calendar(path):
    recs = [json.loads(l) for l in open(path, encoding="utf-8")]
    recs = [r for r in recs if r.get("t")]
    times = [r["t"] for r in recs]
    out = []
    for f in ("m.weekday_name", "m.is_month_start", "m.is_month_end", "m.is_quarter_end", "m.month"):
        for sess in ("london", "ny"):
            groups = {"train": defaultdict(list), "test": defaultdict(list)}
            for name, td, ret in SESS:
                if name != sess:
                    continue
                i = bisect.bisect_right(times, td) - 1
                if i < 0:
                    continue
                groups["train" if td < SPLIT else "test"][recs[i].get(f)].append(ret)
            for val in sorted(groups["train"], key=str):
                row = {"field": f, "value": val, "session": sess}
                for p in ("train", "test"):
                    g = groups[p].get(val, [])
                    rest = [x for k, v in groups[p].items() if k != val for x in v]
                    diff, t = welch(g, rest)
                    row[p] = {"n": len(g), "up": round(sum(1 for x in g if x > 0) / len(g), 3) if g else None,
                              "mean_bps": round(st.mean(g), 2) if g else None, "diff_vs_rest": diff, "t": t}
                out.append(row)
    return out


res = {}
for p in sorted((D / "facts").glob("*.jsonl")):
    name = p.stem
    try:
        res[name] = evaluate_calendar(p) if name.startswith("159") else evaluate(p)
    except Exception as e:  # noqa: BLE001
        res[name] = {"error": repr(e)}
    print(name, "حقول", len(res[name]) if isinstance(res[name], list) else res[name], flush=True)
json.dump(res, open(D / "top150.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# الخلاصة: ما اجتاز t ≥ 2 في التعلّم والاختبار معًا وبالإشارة نفسها
passed, tested = [], 0
for name, rows in res.items():
    if not isinstance(rows, list):
        continue
    for r in rows:
        a, b = r["train"], r["test"]
        ta, tb = a.get("t"), b.get("t")
        if ta is None or tb is None:
            continue
        tested += 1
        if abs(ta) >= 2 and abs(tb) >= 2 and (ta > 0) == (tb > 0):
            passed.append((name, r))
print(f"اختُبر {tested} — اجتاز t≥2 في الفترتين بالإشارة نفسها: {len(passed)} (المتوقّع بالصدفة ≈ {tested * 0.05 * 0.05 * 2:.1f})")
for name, r in passed:
    print("  ", name, r["field"], r.get("value", ""), r["session"], "تعلّم", r["train"], "اختبار", r["test"])
