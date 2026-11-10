# -*- coding: utf-8 -*-
"""حكم معايرة 151: هل تقول حقيقة الاتّجاه شيئًا عن السعر بعدها؟ — قياسٌ فقط.

التصميم مثبَّتٌ قبل النتائج:
  الحقائق (من ملفّات calib151.py، عند إغلاق الشمعة — لا نظر في المستقبل):
    dist   إشارة ema_distance (السريع فوق/تحت البطيء)        slope  إشارة ميل البطيء
    pos    الإغلاق فوق/تحت السريع                            slow   الإغلاق فوق/تحت البطيء (ما تقرؤه 414)
    distQ  طرفا ema_distance (أعلى/أدنى 20٪ — العتبتان من الاكتشاف وحده)   slopeQ  مثله للميل
    pattern حكم الذرّة القديم الباقي في metadata (العيار الحيّ وحده)
  الأهداف: (أ) عائد الإطار نفسه بعد H شمعة (H = 1 · 3 · 6 · 12)، عيّناتٌ غير متداخلة؛
           (ب) جهة جلستَي المالك: لندن 08:15⟵11:00 لندن · نيويورك 09:45⟵13:00 نيويورك، بآخر حقيقةٍ أُغلقت قبل القرار.
  المقياس الذي لا يخدعه «اشترِ دائمًا»: الفرق بين متوسّط العائد حين الحقيقة +1 وحين −1 (نقاط أساس)، و t (ويلش).
  الخزائن: اكتشاف 2018-01-01 ⟵ 2022-01-01 · تحقّق ⟵ 2024-02-19 · خزنة ⟵ 2026-10-06 (تُفتح مرّةً بأمر vault).
  الاختيار: لكلّ (إطار × حقيقة × هدف) العيار الأعلى |t| في الاكتشاف. يُعدّ «مرشّحًا» إن تجاوز ضابط الحظّ
  (المئين 95 لأعلى |t| تحت الصدفة: إزاحةٌ دائريّة عشوائيّة للحقيقة على العائد، 100 مرّة، على كلّ اختبارات
  الإطار معًا) ثمّ كانت جهته في التحقّق نفسها و t ≥ 2. الخزنة تحكم على المرشّحين وعلى العيار الحيّ.

الاستعمال:  python eval151.py select [--in DIR]   ⟵ select.json + جدول الاكتشاف والتحقّق
            python eval151.py vault  [--in DIR]   ⟵ vault.json (مرّةً واحدة، بعد تجميد select.json)
"""
import argparse
import bisect
import json
import math
import pathlib
import sqlite3
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

D = pathlib.Path(__file__).resolve().parent
SCRATCH = pathlib.Path(r"C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib151")
TS = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()  # noqa: E731
P_DISC, P_VAL, P_VAULT, P_END = TS("2018-01-01"), TS("2022-01-01"), TS("2024-02-19"), TS("2026-10-06")
PERIODS = {"disc": (P_DISC, P_VAL), "val": (P_VAL, P_VAULT), "vault": (P_VAULT, P_END)}
HORIZONS = (1, 3, 6, 12)
FRAME_SEC = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")
N_SHIFTS = 100
RNG = np.random.default_rng(20261009)


def welch(r, s):
    a, b = r[s == 1], r[s == -1]
    if len(a) < 30 or len(b) < 30:
        return None
    ma, mb = a.mean(), b.mean()
    se = math.sqrt(a.var() / len(a) + b.var() / len(b))
    return {"n_up": int(len(a)), "n_dn": int(len(b)), "up": round(float(ma), 2), "dn": round(float(mb), 2),
            "spread": round(float(ma - mb), 2), "t": round(float((ma - mb) / se), 2) if se > 0 else 0.0}


def t_only(r, s):
    a, b = r[s == 1], r[s == -1]
    if len(a) < 30 or len(b) < 30:
        return 0.0
    se = math.sqrt(a.var() / len(a) + b.var() / len(b))
    return float((a.mean() - b.mean()) / se) if se > 0 else 0.0


def sessions():
    db = sqlite3.connect(r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\ctrader_history.db?mode=ro", uri=True)
    m1 = db.execute("select period_start, close from candles_history where symbol='USTEC' and period='M1' "
                    "and period_start >= ? order by period_start", (int(P_DISC - 86400),)).fetchall()
    mt = [r[0] for r in m1]

    def close_at(t):
        i = bisect.bisect_right(mt, t - 60) - 1
        return (m1[i][1], m1[i][0] + 60) if i >= 0 else (None, None)

    out = {"london": [], "ny": []}
    days = sorted({datetime.fromtimestamp(t, timezone.utc).date() for t in mt[::60]})
    for d in days:
        if d.weekday() >= 5:
            continue
        for name, tz, dh, dm, eh, em in (("london", LON, 8, 15, 11, 0), ("ny", NY, 9, 45, 13, 0)):
            td = datetime(d.year, d.month, d.day, dh, dm, tzinfo=tz).timestamp()
            te = datetime(d.year, d.month, d.day, eh, em, tzinfo=tz).timestamp()
            c0, k0 = close_at(td)
            c1, k1 = close_at(te)
            if c0 and c1 and k0 >= td - 300 and k1 >= te - 300 and k1 > k0:
                out[name].append((td, (c1 - c0) / c0 * 1e4))
    return {k: np.array(v) for k, v in out.items()}


def facts_of(z, q):
    dist, slope = z["dist"].astype(np.float64), z["slope"].astype(np.float64)
    ok = np.isfinite(dist)
    f = {"dist": np.where(ok, np.sign(dist), 0).astype(np.int8),
         "slope": np.where(ok, np.sign(slope), 0).astype(np.int8),
         "pos": z["pos"], "slow": z["above_slow"]}
    lo, hi = q["dist"]
    f["distQ"] = np.where(ok & (dist >= hi), 1, np.where(ok & (dist <= lo), -1, 0)).astype(np.int8)
    lo, hi = q["slope"]
    f["slopeQ"] = np.where(ok & (slope >= hi), 1, np.where(ok & (slope <= lo), -1, 0)).astype(np.int8)
    if np.any(z["pattern"] != 0):
        f["pattern"] = z["pattern"]
    return f


def quantiles(z):
    t = z["t"]
    m = (t >= P_DISC) & (t < P_VAL) & np.isfinite(z["dist"])
    return {k: (float(np.quantile(z[k][m], 0.2)), float(np.quantile(z[k][m], 0.8))) for k in ("dist", "slope")}


def targets(z, frame, sess):
    """كلّ هدف: (مؤشّرات العيّنات في مصفوفة الحقائق، العائد بنقاط الأساس، زمن العيّنة)."""
    t, close = z["t"], z["close"].astype(np.float64)
    out = {}
    for h in HORIZONS:
        idx = np.arange(0, len(t) - h, h)
        r = (close[idx + h] / close[idx] - 1.0) * 1e4
        out[f"H{h}"] = (idx, r, t[idx])
    for name, arr in sess.items():
        if not len(arr):
            continue
        dec = arr[:, 0]
        j = np.searchsorted(t, dec, side="right") - 1
        fresh = (j >= 0) & (dec - t[np.maximum(j, 0)] <= 2 * FRAME_SEC[frame])
        out[name] = (j[fresh], arr[fresh, 1], dec[fresh])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["select", "vault"])
    ap.add_argument("--in", dest="inp", default=str(SCRATCH / "out"))
    a = ap.parse_args()
    files = sorted(pathlib.Path(a.inp).glob("*.npz"))
    frames = sorted({f.name.split("_")[0] for f in files}, key=lambda x: FRAME_SEC[x])
    sess = sessions()
    print("جلسات", {k: len(v) for k, v in sess.items()}, flush=True)
    if a.mode == "vault":
        sel = json.loads((D / "select.json").read_text(encoding="utf-8"))
    results, selection, luck = [], [], {}
    for frame in frames:
        tests = []                   # (tag, fact, target, s_idx, r, times)
        for f in [x for x in files if x.name.startswith(frame + "_")]:
            tag = f.stem[len(frame) + 1:]
            z = np.load(f)
            facts = facts_of(z, quantiles(z))
            for tg, (idx, r, tt) in targets(z, frame, sess).items():
                for fact, s in facts.items():
                    tests.append((tag, fact, tg, s[idx], r, tt))
        if a.mode == "select":
            # ضابط الحظّ: أعلى |t| في الاكتشاف تحت إزاحةٍ دائريّة واحدة للحقائق كلّها (تحفظ ترابطها).
            disc = [(s[(tt >= P_DISC) & (tt < P_VAL)], r[(tt >= P_DISC) & (tt < P_VAL)]) for _, _, _, s, r, tt in tests]
            maxes = []
            for _ in range(N_SHIFTS):
                u = RNG.uniform(0.1, 0.9)
                maxes.append(max(abs(t_only(r, np.roll(s, int(u * len(s))))) for s, r in disc if len(s) > 60))
            luck[frame] = round(float(np.quantile(maxes, 0.95)), 2)
            print(frame, "اختبارات", len(tests), "ضابط الحظّ (95٪)", luck[frame], flush=True)
        best = {}
        for tag, fact, tg, s, r, tt in tests:
            row = {"frame": frame, "cfg": tag, "fact": fact, "target": tg}
            for p, (p0, p1) in PERIODS.items():
                if p == "vault" and a.mode != "vault":
                    continue
                m = (tt >= p0) & (tt < p1)
                row[p] = welch(r[m], s[m])
            results.append(row)
            if a.mode == "select" and row["disc"]:
                k = (fact, tg)
                if k not in best or abs(row["disc"]["t"]) > abs(best[k]["disc"]["t"]):
                    best[k] = row
        if a.mode == "select":
            for row in best.values():
                d, v = row["disc"], row["val"]
                row["candidate"] = bool(abs(d["t"]) > luck[frame] and v and np.sign(v["t"]) == np.sign(d["t"])
                                        and abs(v["t"]) >= 2)
                selection.append({k: row[k] for k in ("frame", "cfg", "fact", "target", "disc", "val", "candidate")})
    name = "select" if a.mode == "select" else "vault"
    if a.mode == "select":
        (D / "select.json").write_text(json.dumps({"luck95": luck, "best": selection}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    else:
        keep = {(b["frame"], b["cfg"], b["fact"], b["target"]) for b in sel["best"] if b["candidate"]}
        results = [r for r in results if (r["frame"], r["cfg"], r["fact"], r["target"]) in keep or r["cfg"] == "live"]
    (SCRATCH / f"{name}_all.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    if a.mode == "vault":
        (D / "vault.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("تمّ", name, len(results), flush=True)


if __name__ == "__main__":
    sys.exit(main())
