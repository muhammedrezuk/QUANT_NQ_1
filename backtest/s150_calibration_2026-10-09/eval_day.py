# -*- coding: utf-8 -*-
"""حكم يوم الخميس 2026-10-08: «كم من 100» لكلّ حقيقةٍ من كلّ ذرّة بكلّ عيارٍ وكلّ إطار — قياسٌ فقط.

الجلستان (أمر المالك): لندن 08:00⟵16:30 لندن (07:00⟵15:30 غرينتش) · نيويورك 09:30⟵16:00 نيويورك (13:30⟵20:00).
عند إغلاق كلّ دقيقةٍ داخل الجلسة: آخر قيمةٍ نشرتها الحقيقة حتّى تلك اللحظة (لا نظر في المستقبل)، وجهة السعر من تلك
اللحظة حتّى نهاية الجلسة.
قراءة الجهة من الحقيقة:
  نصّ   — كلمات الصعود (up · bull · above · rising · buy · high …) = صاعد، والهبوط = هابط، وغيرها لا جهة.
  رقمٌ له إشارتان — موجب = صاعد، سالب = هابط.
  رقمٌ بإشارةٍ واحدة — فوق وسيطه قبل الجلسة = صاعد، تحته = هابط (الوسيط من الساعات قبلها وحدها).
الإصابة: قالت صاعد فصعد السعر حتّى نهاية الجلسة، أو هابط فهبط — من 100. «صعد أصلًا»: نسبة الدقائق التي صعد بعدها
السعر حتّى النهاية. «الزيادة» = (صاعد أصاب − صعد أصلًا) + (هابط أصاب − هبط أصلًا).
⚠️ يومٌ واحد: دقائق الجلسة كلّها تنتهي عند سعرٍ واحد، فهي ليست مستقلّة — النتيجة «ماذا نجح هذا اليوم» لا قاعدة.

الاستعمال:  python eval_day.py [--in DIR]   ⟵ day_results.json + day_summary.md بجانب الأداة
"""
import argparse
import bisect
import gzip
import json
import pathlib
import pickle
import statistics
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calib_day as C  # noqa: E402

D = pathlib.Path(__file__).resolve().parent
DAY0 = C.TS(C.DAY)
SESSIONS = {"london": (DAY0 + 7 * 3600, DAY0 + 15.5 * 3600), "ny": (DAY0 + 13.5 * 3600, DAY0 + 20 * 3600)}
UP_W = ("up", "bull", "bullish", "above", "rising", "buy", "long", "higher", "high", "positive", "uptrend", "gap_up",
        "leader", "strong_up", "accelerating_up", "buyside")
DN_W = ("down", "bear", "bearish", "below", "falling", "sell", "short", "lower", "low", "negative", "downtrend",
        "gap_down", "laggard", "strong_down", "accelerating_down", "sellside")
SKIP_FIELDS = ("period_start", "m.period_start", "m.candles", "m.count", "m.window", "computed_on", "m.timeframe",
               "timeframe", "m.method", "warnings", "status", "data_completeness")
NAMES = {}


def word_dir(s):
    s = s.lower()
    for w in UP_W:
        if s == w or s.startswith(w + "_") or s.endswith("_" + w):
            return 1
    for w in DN_W:
        if s == w or s.startswith(w + "_") or s.endswith("_" + w):
            return -1
    return 0


def price_minutes():
    ev = pickle.loads((C.SCRATCH / f"candles_{C.DAY}.pkl").read_bytes())
    pts = {e[0]: e[3]["close"] for e in ev if e[3]["timeframe"] == "1m" and e[2] == "USTEC" and DAY0 <= e[0] <= DAY0 + 86400}
    return pts


def hits(d, r):
    up, dn = d == 1, d == -1
    if up.sum() < 10 or dn.sum() < 10:
        return None
    base = float((r > 0).mean()) * 100
    uh = float((r[up] > 0).mean()) * 100
    dh = float((r[dn] < 0).mean()) * 100
    return {"up": round(uh, 1), "dn": round(dh, 1), "base": round(base, 1), "edge": round((uh - base) + (dh - (100 - base)), 1),
            "n_up": int(up.sum()), "n_dn": int(dn.sum())}


def evaluate_file(path, prices):
    blob = json.load(gzip.open(path, "rt", encoding="utf-8"))
    series = defaultdict(lambda: ([], []))
    for t, aid, ev, tf, row in blob["rows"]:
        for k, v in row.items():
            if k in SKIP_FIELDS or k.startswith("m.bench_") and k != "m.bench_signal":
                continue
            ts, vs = series[(aid, tf or "-", k)]
            ts.append(t)
            vs.append(v)
    out = []
    for sname, (s0, s1) in SESSIONS.items():
        mins = [m for m in sorted(prices) if s0 < m < s1]
        if s1 not in prices or not mins:
            continue
        end = prices[s1]
        r = np.array([end - prices[m] for m in mins])
        for (aid, tf, k), (ts, vs) in series.items():
            idx = [bisect.bisect_right(ts, m) - 1 for m in mins]
            vals = [vs[i] if i >= 0 else None for i in idx]
            if isinstance(next((v for v in vals if v is not None), None), str):
                d = np.array([word_dir(v) if isinstance(v, str) else 0 for v in vals])
                reading = "كلمة"
            else:
                nums = [v for v in vs if isinstance(v, (int, float))]
                if not nums:
                    continue
                if min(nums) < 0 < max(nums):
                    d = np.array([0 if v is None else (1 if v > 0 else -1 if v < 0 else 0) for v in vals])
                    reading = "إشارة"
                else:
                    before = [v for t, v in zip(ts, vs) if t < s0 and isinstance(v, (int, float))]
                    if len(before) < 5:
                        continue
                    med = statistics.median(before)
                    d = np.array([0 if v is None else (1 if v > med else -1 if v < med else 0) for v in vals])
                    reading = "فوق وسيطه"
            h = hits(d, r)
            if h:
                out.append({"session": sname, "atom": aid, "frame": tf, "field": k, "reading": reading,
                            "tune": blob["tune"], "cfg": blob["tag"], **h})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(C.SCRATCH / "runs"))
    a = ap.parse_args()
    prices = price_minutes()
    allr = []
    for f in sorted(pathlib.Path(a.inp).glob("*.json.gz")):
        allr += evaluate_file(f, prices)
        print(f.name, len(allr), flush=True)
    multi = "CALIB_DAY" in __import__("os").environ
    (C.SCRATCH / (f"day_results_all_{C.DAY}.json" if multi else "day_results_all.json")).write_text(
        json.dumps(allr, ensure_ascii=False), encoding="utf-8")
    out_dir = D / "days" / C.DAY if multi else D
    out_dir.mkdir(parents=True, exist_ok=True)
    cat = C.catalog()
    names = {k: v["dir"].name for k, v in cat.items()}
    best = {}
    for x in allr:
        k = (x["atom"], x["session"])
        if k not in best or x["edge"] > best[k]["edge"]:
            best[k] = x
    live = {}
    for x in allr:
        if x["cfg"] != "live" or x["tune"] != x["atom"] and x["tune"] != "201":
            continue
        k = (x["atom"], x["session"])
        if k not in live or x["edge"] > live[k]["edge"]:
            live[k] = x
    (out_dir / "day_results.json").write_text(json.dumps({"best": list(best.values()), "live": list(live.values())},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# يوم {C.DAY} — أحسن ما خرج من كلّ ذرّة (من 100)\n",
             "| الذرّة | الجلسة | العيار الحيّ: الحقيقة · الإطار · الزيادة | أحسن عيار: التركيبة · الحقيقة · الإطار | صاعد أصاب | هابط أصاب | صعد أصلًا | الزيادة |",
             "|---|---|---|---|---|---|---|---|"]
    for (aid, s), b in sorted(best.items()):
        lv = live.get((aid, s))
        lvs = f"{lv['field']} · {lv['frame']} · {lv['edge']:+.1f}" if lv else "—"
        lines.append(f"| {names.get(aid, aid)} | {'لندن' if s == 'london' else 'نيويورك'} | {lvs} | {b['cfg']} · {b['field']} "
                     f"({b['reading']}) · {b['frame']} | {b['up']} | {b['dn']} | {b['base']} | {b['edge']:+.1f} |")
    (out_dir / "day_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("تمّ", len(allr), "قراءة ·", len(best), "ذرّة×جلسة")


if __name__ == "__main__":
    main()
