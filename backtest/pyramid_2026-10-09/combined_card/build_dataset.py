# -*- coding: utf-8 -*-
"""البطاقة الجامعة — الخطوة ١: جدولٌ لكلّ لحظة دخولٍ ممكنة بحقائق الأقسام كلّها ونتيجتها بقوانين المالك. قياسٌ فقط.

اللحظات: كلّ إغلاق شمعة خمس دقائق في نافذتَي المالك (لندن 08:15–11:00 · نيويورك 09:45–13:00) من 2018، بالجهتين.
النتيجة لكلّ (لحظة، جهة): الدخول إغلاق الشمعة · الوقف خلف آخر قاع/قمّة مؤكَّد (201 بكوده) — الخمس دقائق عرض 2 أوّلًا،
ثمّ الربع ساعة عرض 2، ثمّ الدقيقة عرض 3 — أوّل ما يقع بين 15 و50 نقطة (التحليل نفسه، بلا قصّ)، وإلّا لا صفقة ·
الهدف 3R · أثلاث المالك على الدقيقة · كلفة 1.5 · إغلاقٌ إجباريّ 16:00 نيويورك (لا مبيت).
الحقائق: كلّ ملفّات أدوات الليلة (بكود الذرّات) بآخر قيمةٍ معروفة عند إغلاق الشمعة (merge_asof للخلف — لا مستقبل)،
وحقائق الجلسة من البحث (الزخم منذ إغلاق الأمس · نطاق الافتتاح · موضع السعر من متوسّط الجلسة الموزون · الفجوة).
"""
import json
import pathlib
import sqlite3
import sys
import time
from datetime import datetime, timezone
from multiprocessing import Pool
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

D = pathlib.Path(__file__).resolve().parent
SP = D.parent
SB, S150 = SP / "structure_bench", SP / "s150_bench"
LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")
START = datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp()
DB = r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\ctrader_history.db?mode=ro"
COST = 1.5


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def candles(period, since):
    c = sqlite3.connect(DB, uri=True)
    df = pd.read_sql_query("select period_start, open, high, low, close, tick_volume from candles_history "
                           "where symbol='USTEC' and period=? and period_start>=? order by period_start",
                           c, params=(period, int(since)))
    return df


# ───────────── الدقائق للإدارة ─────────────
M1 = candles("M1", START - 86400 * 10)
MT = M1.period_start.to_numpy(np.int64)
MO, MH, ML, MC = (M1[k].to_numpy(float) for k in ("open", "high", "low", "close"))
log("دقائق", len(M1))


def ny_close_after(t):
    lt = datetime.fromtimestamp(t, NY)
    return lt.replace(hour=16, minute=0, second=0, microsecond=0).timestamp()


def thirds(entry, stop, buy, t0):
    """أثلاث المالك بهدف 3R، وإغلاقٌ عند 16:00 نيويورك ⟵ (R، المرحلة 0..3 أو 9 للإغلاق القسريّ)."""
    risk = abs(entry - stop)
    span = 3 * risk
    sgn = 1 if buy else -1
    t1_, t2_, tg = entry + sgn * span / 3, entry + sgn * 2 * span / 3, entry + sgn * span
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    k = int(np.searchsorted(MT, t0, "left"))
    end = ny_close_after(t0)
    while k < len(MT) and MT[k] < end:
        o, h, lo = MO[k], MH[k], ML[k]
        if (lo <= cur) if buy else (h >= cur):
            px = min(o, cur) if buy else max(o, cur)
            return real + rem * ((px - entry) * sgn / risk) - COST / risk, stage
        if stage < 1 and ((h >= t1_) if buy else (lo <= t1_)):
            real += (rem / 3) * (span / 3 / risk); rem -= rem / 3; cur = entry; stage = 1
        if stage < 2 and ((h >= t2_) if buy else (lo <= t2_)):
            real += (rem / 2) * (2 * span / 3 / risk); rem -= rem / 2; cur = t1_; stage = 2
        if (h >= tg) if buy else (lo <= tg):
            return real + rem * (span / risk) - COST / risk, 3
        k += 1
    if k == 0:
        return np.nan, -1
    px = MC[k - 1]
    return real + rem * ((px - entry) * sgn / risk) - COST / risk, 9 if stage == 0 else stage


def _sim(args):
    return [thirds(*a) for a in args]


# ───────────── اللحظات ─────────────
def moments():
    m5 = candles("M5", START)
    m5["t"] = m5.period_start + 300
    rows = []
    for t, c in zip(m5.t.to_numpy(np.int64), m5.close.to_numpy(float)):
        for name, tz, (sh, sm), (eh, em) in (("london", LON, (8, 15), (11, 0)), ("ny", NY, (9, 45), (13, 0))):
            lt = datetime.fromtimestamp(t, tz)
            if lt.weekday() >= 5:
                continue
            mm = lt.hour * 60 + lt.minute
            if sh * 60 + sm <= mm <= eh * 60 + em - 5:
                rows.append((t, name, lt.date().isoformat(), c))
    return pd.DataFrame(rows, columns=["t", "sess", "day", "close"])


# ───────────── حقائق الملفّات ─────────────
def jsonl_frame(path, keep, filt=None):
    recs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if filt and filt not in line:
                continue
            r = json.loads(line)
            if r.get("t", 0) < START - 86400 * 30:
                continue
            recs.append({k: r.get(k) for k in keep})
    df = pd.DataFrame(recs)
    if len(df):
        df = df.sort_values("t").reset_index(drop=True)
        df["t"] = df["t"].astype("int64")
    return df


def asof(base, df, prefix, cols):
    if df is None or not len(df):
        return base
    df = df[["t"] + cols].rename(columns={c: f"{prefix}{c}" for c in cols})
    return pd.merge_asof(base.sort_values("t"), df, on="t", direction="backward")


def dir_of(v):
    if not isinstance(v, str):
        return 0
    s = v.lower()
    if s in ("up", "strong_up", "bullish", "uptrend", "above", "hh", "hl", "above_fast", "above_slow", "above_both"):
        return 1
    if s in ("down", "strong_down", "bearish", "downtrend", "below", "ll", "lh", "below_fast", "below_slow", "below_both"):
        return -1
    if s.startswith("above") or s.endswith("_up") or s.startswith("bull"):
        return 1
    if s.startswith("below") or s.endswith("_down") or s.startswith("bear"):
        return -1
    return 0


def main():
    mo = moments()
    log("لحظات", len(mo))
    base = mo.copy()
    # — القمّة والوسط: 151 · 152 · 153 · 165 من ملفّات قسم 150 —
    for f in sorted((S150 / "facts").glob("15[1235]_*.jsonl")) + sorted((S150 / "facts").glob("165_*.jsonl")) + \
             sorted((S150 / "facts_mid").glob("*.jsonl")):
        name = f.stem
        keep = ["t", "m.pattern", "m.ema_distance", "m.ema_slope", "m.price_position", "m.roc", "m.ratio",
                "m.efficiency", "m.body_ratio"]
        df = jsonl_frame(f, keep)
        cols = [c for c in keep[1:] if c in df.columns and df[c].notna().any()]
        base = asof(base, df, f"f{name}|", cols)
        log("حقائق", name, cols)
    # — البنية: 207 والأحداث على 5د/15د/ساعة/4س (عرض 2) —
    for fr in ("5m", "15m", "1h", "4h"):
        p = SB / "events" / f"{fr}_lb2.jsonl"
        if not p.exists():
            continue
        t207 = jsonl_frame(p, ["t", "official"], '"e": "trend207"')
        base = asof(base, t207, f"s{fr}|", ["official"])
        for ev in ("bos", "choch", "external", "internal"):
            df = jsonl_frame(p, ["t", "break_side", "sig"], f'"e": "{ev}"')
            df = df.rename(columns={"t": "t"})
            if len(df):
                df[f"{ev}_t"] = df["t"]
                base = asof(base, df, f"s{fr}|{ev}.", ["break_side", "sig", f"{ev}_t"])
        log("بنية", fr)
    # — السيولة: آخر كنس وآخر فجوة على 5د/15د (عرض 2) —
    for fr in ("5m", "15m"):
        p = SB / "liq" / f"{fr}_lb2.jsonl"
        if not p.exists():
            continue
        sw = jsonl_frame(p, ["t", "direction", "price", "high", "low"], '"e": "sweep"')
        sw["sweep_t"] = sw["t"]
        base = asof(base, sw, f"l{fr}|sweep.", ["direction", "price", "sweep_t"])
        fv = jsonl_frame(p, ["t", "sig", "gap_top", "gap_bottom"], '"e": "fvg"')
        fv["fvg_t"] = fv["t"]
        base = asof(base, fv, f"l{fr}|fvg.", ["sig", "gap_top", "gap_bottom", "fvg_t"])
        log("سيولة", fr)
    # — القمم/القيعان للوقف: 5د عرض2 · 15د عرض2 · دقيقة عرض3 —
    for tag, fr, lb, src in (("s5", "5m", 2, "events"), ("s15", "15m", 2, "events"), ("s1", "1m", 3, "liq")):
        p = SB / src / f"{fr}_lb{lb}.jsonl"
        sw = jsonl_frame(p, ["t", "sig", "price"], '"e": "swing"')
        hi = sw[sw.sig == "swing_high"][["t", "price"]].rename(columns={"price": f"{tag}_hi"})
        lo = sw[sw.sig == "swing_low"][["t", "price"]].rename(columns={"price": f"{tag}_lo"})
        base = pd.merge_asof(base.sort_values("t"), hi, on="t", direction="backward")
        base = pd.merge_asof(base.sort_values("t"), lo, on="t", direction="backward")
        log("قمم/قيعان", tag)
    # — حقائق الجلسة من البحث (من شموع الدقيقة مباشرةً) —
    m1 = M1.copy()
    m1["tc"] = m1.period_start + 60
    m1["ny"] = pd.to_datetime(m1.period_start, unit="s", utc=True).dt.tz_convert(NY)
    m1["nyday"] = m1.ny.dt.date
    m1["nym"] = m1.ny.dt.hour * 60 + m1.ny.dt.minute
    cash = m1[(m1.nym >= 570) & (m1.nym < 960)]
    prev_close = cash.groupby("nyday").close.last().shift(1)  # إغلاق الأمس النقديّ
    day_open = cash.groupby("nyday").open.first()
    orng = m1[(m1.nym >= 570) & (m1.nym < 585)].groupby("nyday").agg(or_hi=("high", "max"), or_lo=("low", "min"))
    base["nyday"] = pd.to_datetime(base.t, unit="s", utc=True).dt.tz_convert(NY).dt.date
    base["nym"] = pd.to_datetime(base.t, unit="s", utc=True).dt.tz_convert(NY).dt.hour * 60 + \
        pd.to_datetime(base.t, unit="s", utc=True).dt.tz_convert(NY).dt.minute
    base = base.merge(prev_close.rename("prev_close"), left_on="nyday", right_index=True, how="left")
    base = base.merge(day_open.rename("day_open"), left_on="nyday", right_index=True, how="left")
    base = base.merge(orng, left_on="nyday", right_index=True, how="left")
    # متوسّط الجلسة الموزون بعدد التِّكّات منذ 09:30 (نيويورك) — للحظات بعد الافتتاح
    cash = cash.copy()
    cash["pv"] = cash.close * cash.tick_volume.clip(lower=1)
    cash["v"] = cash.tick_volume.clip(lower=1)
    cash["cpv"] = cash.groupby("nyday").pv.cumsum()
    cash["cv"] = cash.groupby("nyday").v.cumsum()
    cash["vwap"] = cash.cpv / cash.cv
    vw = cash[["tc", "vwap"]].rename(columns={"tc": "t"}).sort_values("t")
    base = pd.merge_asof(base.sort_values("t"), vw, on="t", direction="backward")
    base.loc[base.nym < 575, "vwap"] = np.nan  # قبل افتتاح نيويورك لا متوسّط جلسة
    log("حقائق الجلسة")
    base = base.sort_values(["t"]).reset_index(drop=True)
    # ───────────── النتيجة بالجهتين ─────────────
    jobs, idx = [], []
    for i, r in enumerate(base.itertuples(index=False)):
        c = r.close
        for buy in (True, False):
            stop = None
            for tag in ("s5", "s15", "s1"):
                lvl = getattr(r, f"{tag}_lo" if buy else f"{tag}_hi")
                if lvl is None or (isinstance(lvl, float) and np.isnan(lvl)):
                    continue
                s = lvl - 1.0 if buy else lvl + 1.0
                risk = (c - s) if buy else (s - c)
                if 15.0 <= risk <= 50.0:
                    stop = s
                    break
            if stop is not None:
                jobs.append((c, stop, buy, int(r.t)))
                idx.append((i, buy))
    log("صفقات ممكنة", len(jobs))
    chunks = [jobs[k:k + 20000] for k in range(0, len(jobs), 20000)]
    with Pool(5) as pool:
        res = [x for part in pool.map(_sim, chunks) for x in part]
    base["R_buy"] = np.nan; base["st_buy"] = np.nan; base["R_sell"] = np.nan; base["st_sell"] = np.nan
    base["risk_buy"] = np.nan; base["risk_sell"] = np.nan
    Rb = np.full(len(base), np.nan); Sb = np.full(len(base), np.nan); Rs = np.full(len(base), np.nan); Ss = np.full(len(base), np.nan)
    rkb = np.full(len(base), np.nan); rks = np.full(len(base), np.nan)
    for (i, buy), (R, stg), job in zip(idx, res, jobs):
        if buy:
            Rb[i], Sb[i], rkb[i] = R, stg, abs(job[0] - job[1])
        else:
            Rs[i], Ss[i], rks[i] = R, stg, abs(job[0] - job[1])
    base["R_buy"], base["st_buy"], base["R_sell"], base["st_sell"] = Rb, Sb, Rs, Ss
    base["risk_buy"], base["risk_sell"] = rkb, rks
    base.to_pickle(D / "dataset.pkl")
    log("حُفظ", base.shape, "· شراء", int(np.isfinite(Rb).sum()), "· بيع", int(np.isfinite(Rs).sum()),
        "· متوسّط R شراء", round(np.nanmean(Rb), 4), "· بيع", round(np.nanmean(Rs), 4))


if __name__ == "__main__":
    main()
