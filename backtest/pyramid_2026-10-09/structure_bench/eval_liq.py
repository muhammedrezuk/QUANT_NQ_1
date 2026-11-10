# -*- coding: utf-8 -*-
"""وسط الهرم للسيولة (254 الكنس بكوده) — قياسٌ فقط، بقوانين المالك وبأدوات eval_structure نفسها.

الكنس (254): شمعةٌ أخذت مجمّعًا (buy_side = أخذت قمّة · sell_side = أخذت قاعًا).
  أ) «الكسر الكاذب» كما وصفه المالك: أخذت القاع وأُغلقت فوقه ⟸ شراء (والعكس) — الوقف خلف ذيل الشمعة الكانسة ± نقطة.
  ب) كود الذرّة كما هو (أيّ لمسة) بجهة الانعكاس.
  ج) الاستمرار في جهة الكنس (البحث: الكنس يُتبع بالاستمرار) — الوقف خلف الطرف المقابل للشمعة.
الوقف 15–50 نقطة عاديّة · الهدف 3R · أثلاث المالك على الدقيقة بكلفة 1.5 · مركزٌ واحد · صفقتان في الجلسة ·
نافذتا المالك · مرشّح الهرم: حكم 207 على الساعة/الأربع ساعات · من 2018، تعلّمٌ حتّى 2024-02-19.
"""
import bisect
import json
import statistics as st
from collections import defaultdict
from datetime import datetime, timezone

import eval_structure as E  # يحمّل الدقائق من 2018 والجلسات وحكم 207 (المرشّح) مرّة

LIQ = E.D / "liq"


_CACHE = {}


def _sweeps(frame, lb):
    k = (frame, lb)
    if k not in _CACHE:
        p = LIQ / f"{frame}_lb{lb}.jsonl"
        rows = []
        if p.exists():
            for line in open(p, encoding="utf-8"):
                if '"e": "sweep"' not in line:
                    continue
                r = json.loads(line)
                if r.get("t", 0) >= E.START:
                    rows.append(r)
        rows.sort(key=lambda r: r["t"])
        _CACHE.clear()
        _CACHE[k] = rows
    return _CACHE[k]


def run(frame, lb, mode, filt):
    sweeps = _sweeps(frame, lb)
    if not sweeps:
        return None, []
    pyr = E.PYR[filt]
    trades, stops, busy, per = [], {"<15": 0, ">50": 0, "ok": 0}, 0.0, defaultdict(int)
    for r in sweeps:
        t = r["t"]
        if t < busy:
            continue
        key = E.in_window(t - 1)
        if key is None or per[key] >= 2:
            continue
        took_high = r.get("direction") == "buy_side"
        level, hi, lo = r.get("price"), r.get("high"), r.get("low")
        if level is None or hi is None or lo is None:
            continue
        c, _ = E.close_at(t)  # إغلاق الشمعة الكانسة (آخر دقيقة قبل إغلاقها)
        if c is None:
            continue
        if mode == "false_break":
            back = (c < level) if took_high else (c > level)
            if not back:
                continue
            buy = not took_high
        elif mode == "atom_raw":
            buy = not took_high
        else:  # continuation
            buy = took_high
        if pyr is not None:
            prow = E.last_before(pyr[0], pyr[1], t)
            if prow is None or prow.get("official") != ("uptrend" if buy else "downtrend"):
                continue
        entry = c
        if mode == "continuation":
            stop = (lo - 1.0) if buy else (hi + 1.0)
        else:
            stop = (lo - 1.0) if buy else (hi + 1.0)
        risk = (entry - stop) if buy else (stop - entry)
        if risk < 15.0:
            stops["<15"] += 1
            continue
        if risk > 50.0:
            stops[">50"] += 1
            continue
        stops["ok"] += 1
        target = entry + 3 * risk if buy else entry - 3 * risk
        R, stage, t_exit = E.thirds(entry, stop, target, buy, t)
        if R is None:
            continue
        per[key] += 1
        busy = t_exit
        trades.append({"t": t, "buy": buy, "risk": round(risk, 1), "R": round(R, 4), "stage": stage})
    row = {"frame": frame, "lb": lb, "mode": mode, "filter": filt, "stops": stops}
    for part, sel in (("train", lambda x: x["t"] < E.SPLIT), ("test", lambda x: x["t"] >= E.SPLIT)):
        tt = [x for x in trades if sel(x)]
        rs = [x["R"] for x in tt]
        g, l = sum(x for x in rs if x > 0), -sum(x for x in rs if x < 0)
        sg = defaultdict(int)
        for x in tt:
            sg[x["stage"]] += 1
        n = len(tt)
        row[part] = {"n": n, "R_per": round(st.mean(rs), 4) if rs else None, "total": round(sum(rs), 1),
                     "pf": round(g / l, 2) if l > 0 else None,
                     "stop%": round(sg[0] / n, 3) if n else None, "t1_be%": round(sg[1] / n, 3) if n else None,
                     "t2%": round(sg[2] / n, 3) if n else None, "t3%": round(sg[3] / n, 3) if n else None}
    halves = defaultdict(float)
    for x in trades:
        if x["t"] >= E.SPLIT:
            dt = datetime.fromtimestamp(x["t"], timezone.utc)
            halves[f"{dt.year}{'a' if dt.month <= 6 else 'b'}"] += x["R"]
    row["test_halves"] = {k: round(v, 1) for k, v in sorted(halves.items())}
    return row, trades


if __name__ == "__main__":
    res, all_trades = [], {}
    for frame in ("1m", "5m", "15m"):
        for lb in (1, 2, 3):
            for mode in ("false_break", "atom_raw", "continuation"):
                for filt in ("none", "1h", "4h"):
                    row, tr = run(frame, lb, mode, filt)
                    if row:
                        res.append(row)
                        all_trades[f"{frame}_lb{lb}_{mode}_{filt}"] = tr
    json.dump(res, open(E.D / "liq_mid.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(all_trades, open(E.D / "liq_trades.json", "w", encoding="utf-8"))
    print("السيولة: تركيبات", len(res), flush=True)
    for r in sorted(res, key=lambda r: -((r["train"]["R_per"] or -9) if (r["train"]["n"] or 0) >= 100 else -9))[:12]:
        a, b = r["train"], r["test"]
        print(f'{r["frame"]:>3} lb{r["lb"]} {r["mode"]:<12} {r["filter"]:<4} | تعلّم n={a["n"]} R={a["R_per"]} pf={a["pf"]} t3={a["t3%"]} | '
              f'اختبار n={b["n"]} R={b["R_per"]} pf={b["pf"]} وقف={b["stop%"]} t3={b["t3%"]} | أنصاف {r["test_halves"]} | {r["stops"]}')
