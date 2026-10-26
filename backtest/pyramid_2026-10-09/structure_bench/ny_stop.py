# -*- coding: utf-8 -*-
"""مبدأ المالك على البطاقة 414: «الوقف من التحليل نفسه بين 15 و45 نقطة — لا نسبة ثابتة ولا قصّ».
نيويورك اليوم: الوقف ضعفا مدى الخمس دقائق (وسيطه 107 نقاط) فالهدف 339 والسعر لا يبلغه (التشريح: 8٪).
البديل المقيس: صفقات 414 نفسها (الزناد والجهة والدخول كما هي)، والوقف خلف آخر قاع/قمّة **دقيقة** مؤكَّد (201 بكوده، عرض 2)
قبل الدخول ± نقطة — يُقبل إن وقع بين 15 و50 نقطة، وإلّا جُرّب عرض 3 ثمّ 5 (التحليل نفسه على نافذةٍ أوسع)، وإلّا لا صفقة.
الهدف: (أ) 3R من الوقف الجديد · (ب) هدف 414 الأصليّ (المستوى) إن بلغت نسبته ≥ 3. الإدارة أثلاث المالك بكلفة 1.5.
"""
import bisect
import json
import statistics as st

import eval_structure as E
from decompose import load_414

SW = {}
for lb in (2, 3, 5):
    p = E.D / "liq" / f"1m_lb{lb}.jsonl"
    hi, lo = [], []
    if p.exists():
        for line in open(p, encoding="utf-8"):
            if '"e": "swing"' not in line:
                continue
            r = json.loads(line)
            if r.get("t", 0) < 1.7e9 or "price" not in r:  # صفقات 414 من 2024-10 فقط
                continue
            (hi if r["sig"] == "swing_high" else lo).append((r["t"], r["price"]))
    SW[lb] = (hi, [x[0] for x in hi], lo, [x[0] for x in lo])
print("قمم/قيعان الدقيقة:", {k: (len(v[0]), len(v[2])) for k, v in SW.items()}, flush=True)

d414 = json.load(open(r"C:\Users\NQ\QUANT_NQ\backtest\card_414\نتائج\card_prob_trades.json", encoding="utf-8"))
RAW = d414 if isinstance(d414, list) else next(v for v in d414.values() if isinstance(v, list))


def new_stop(t, entry, buy):
    for lb in (2, 3, 5):
        hi, hit, lo, lot = SW[lb]
        if buy:
            i = bisect.bisect_right(lot, t) - 1
            if i < 0:
                continue
            s = lo[i][1] - 1.0
            risk = entry - s
        else:
            i = bisect.bisect_right(hit, t) - 1
            if i < 0:
                continue
            s = hi[i][1] + 1.0
            risk = s - entry
        if 15.0 <= risk <= 50.0:
            return s, risk, lb
    return None, None, None


def run(win, mode):
    rows = []
    for t in RAW:
        if not t["window"].startswith(win):
            continue
        buy, entry = bool(t["buy"]), t["entry"]
        s, risk, lb = new_stop(t["t"], entry, buy)
        if s is None:
            rows.append({"t": t["t"], "skip": True})
            continue
        sgn = 1 if buy else -1
        if mode == "3R":
            target = entry + sgn * 3 * risk
        else:
            target = t["target"]
            if (target - entry) * sgn < 3 * risk:
                rows.append({"t": t["t"], "skip": True})
                continue
        R, stage, _ = E.thirds(entry, s, target, buy, t["t"])
        if R is None:
            continue
        rows.append({"t": t["t"], "R": R, "stage": stage, "risk": risk, "lb": lb, "old_R": t["r"]})
    return rows


if __name__ == "__main__":
    ts = sorted(t["t"] for t in RAW)
    split = ts[int(len(ts) * 0.7)]
    out = {}
    for win in ("ny", "london"):
        old = [t["r"] for t in RAW if t["window"].startswith(win)]
        print(f"{win}: الأصل {len(old)} صفقة R={st.mean(old):+.3f}", flush=True)
        for mode in ("3R", "level"):
            rows = run(win, mode)
            taken = [r for r in rows if not r.get("skip")]
            res = {"taken": len(taken), "skipped": sum(1 for r in rows if r.get("skip"))}
            for part, sel in (("train", lambda r: r["t"] < split), ("test", lambda r: r["t"] >= split)):
                tt = [r for r in taken if sel(r)]
                rs = [r["R"] for r in tt]
                res[part] = {"n": len(tt), "R": round(st.mean(rs), 3) if rs else None,
                             "old_R_same": round(st.mean(r["old_R"] for r in tt), 3) if tt else None,
                             "t3%": round(sum(1 for r in tt if r["stage"] == 3) / len(tt), 3) if tt else None,
                             "risk_med": round(st.median(r["risk"] for r in tt), 1) if tt else None}
            out[f"{win}_{mode}"] = res
            print(f"  {mode:<5} مأخوذة {res['taken']} متروكة {res['skipped']} | تعلّم {res['train']} | اختبار {res['test']}", flush=True)
    json.dump(out, open(E.D / "ny_stop.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
