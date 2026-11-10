# -*- coding: utf-8 -*-
"""البطاقة الجامعة — الخطوة ٢: البحث عن قواعد قصيرة (شرطان، ثمّ ثالث) من حقائق كلّ الأقسام، بثلاث خزائن وضابط حظّ.

الخزائن: اكتشاف 2018-01 ⟶ 2021-12 · تحقّق 2022-01 ⟶ 2024-02-19 · **خزنةٌ مقفلة 2024-02-19 ⟶ اليوم تُفتح مرّة واحدة.**
الشرط «موافق» = الحقيقة في جهة الصفقة · «معاكس» = ضدّها · والنظاميّ (التذبذب · الضوضاء) بثُلثيّات الاكتشاف.
الترتيب على الاكتشاف بـ t مجمّعة باليوم (عيّنات اليوم الواحد مترابطة، فتُحسب وحدةً واحدة).
ضابط الحظّ: البحث نفسه على نتائج مخلوطة بين الأيّام (200 خلطة) ⟵ أقصى t بالصدفة.
التحقّق: أوّل صفقتين في الجلسة يفصل بينهما 30 دقيقة على الأقلّ (قانون المالك: صفقتان) — وتُختار القاعدة به وحده.
"""
import json
import math
import pathlib
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

D = pathlib.Path(__file__).resolve().parent
T_VAL = datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp()
T_HOLD = datetime(2024, 2, 19, tzinfo=timezone.utc).timestamp()
FR = {"5m": 300, "15m": 900}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def dir_str(v):
    if not isinstance(v, str):
        return 0
    s = v.lower()
    if s in ("up", "strong_up", "bullish", "uptrend", "hh", "hl", "above", "fvg_bullish") or s.startswith("above") \
            or s.endswith("_up") or s.startswith("bull"):
        return 1
    if s in ("down", "strong_down", "bearish", "downtrend", "ll", "lh", "below", "fvg_bearish") or s.startswith("below") \
            or s.endswith("_down") or s.startswith("bear"):
        return -1
    return 0


def build_conditions(df):
    """⟵ dict اسم ⟵ (مصفوفة جهةٍ لكلّ لحظة ∈ {−1,0,+1}) للاتّجاهيّ، و(مصفوفة منطقيّة) للنظاميّ."""
    dirs, regs = {}, {}
    disc = df.t < T_VAL
    for c in df.columns:
        if c.startswith("f") and "|" in c:
            col = df[c]
            if c.endswith("m.pattern") or c.endswith("m.price_position"):
                dirs[c] = col.map(dir_str).fillna(0).to_numpy(int)
            elif c.endswith(("m.ema_distance", "m.ema_slope", "m.roc")):
                dirs[c] = np.sign(pd.to_numeric(col, errors="coerce").fillna(0)).to_numpy(int)
            elif c.endswith(("m.ratio", "m.efficiency", "m.body_ratio")):
                x = pd.to_numeric(col, errors="coerce")
                q1, q2 = x[disc].quantile([1 / 3, 2 / 3])
                regs[f"{c}<=ث1"] = (x <= q1).to_numpy()
                regs[f"{c}>ث2"] = (x > q2).to_numpy()
        elif c.startswith("s") and "|" in c and not c.endswith("_t"):
            if c.endswith(("official", "break_side", ".sig")):
                dirs[c] = df[c].map(dir_str).fillna(0).to_numpy(int)
    # السيولة: كنسٌ حديث (≤ 3 شموع) — أخذ القيعان ⟸ +1 (فكرة الكسر الكاذب) · فجوةٌ حديثة (≤ 6 شموع)
    for fr, sec in FR.items():
        k = f"l{fr}|sweep."
        if k + "direction" in df.columns:
            fresh = (df.t - df[k + "sweep_t"]).fillna(1e12) <= 3 * sec
            dv = df[k + "direction"].map({"sell_side": 1, "buy_side": -1}).fillna(0).to_numpy(int)
            dirs[f"كنس_حديث_{fr}"] = np.where(fresh, dv, 0)
        k = f"l{fr}|fvg."
        if k + "sig" in df.columns:
            fresh = (df.t - df[k + "fvg_t"]).fillna(1e12) <= 6 * sec
            dirs[f"فجوة_حديثة_{fr}"] = np.where(fresh, df[k + "sig"].map(dir_str).fillna(0).to_numpy(int), 0)
    # حقائق الجلسة (البحث)
    dirs["زخم_منذ_إغلاق_الأمس"] = np.sign((df.close - df.prev_close).fillna(0)).to_numpy(int)
    # ⛔ تسريبٌ أُصلح (١٠-٠٩): افتتاح اليوم = افتتاح نيويورك 09:30 — **مستقبلٌ للحظات لندن**؛ فلا يُقرأ قبله.
    dirs["منذ_افتتاح_اليوم"] = np.where(df.nym >= 571, np.sign((df.close - df.day_open).fillna(0)), 0).astype(int)
    after_or = df.nym >= 585
    dirs["نطاق_الافتتاح"] = np.where(after_or & (df.close > df.or_hi), 1,
                                     np.where(after_or & (df.close < df.or_lo), -1, 0))
    dirs["متوسّط_الجلسة_الموزون"] = np.sign((df.close - df.vwap).fillna(0)).to_numpy(int)
    regs["لندن"] = (df.sess == "london").to_numpy()
    regs["نيويورك"] = (df.sess == "ny").to_numpy()
    return dirs, regs


def expand(dirs, regs):
    """كلّ شرطٍ اتّجاهيّ يصير «موافق»/«معاكس» لجهة الصفقة — ⟵ قائمة (اسم، مصفوفة شراء، مصفوفة بيع)."""
    conds = []
    for k, v in dirs.items():
        conds.append((f"{k}=موافق", v == 1, v == -1))
        conds.append((f"{k}=معاكس", v == -1, v == 1))
    for k, v in regs.items():
        conds.append((k, v, v))
    return conds


def day_t(R, mask, day_codes, ndays):
    """t مجمّعة باليوم: متوسّط R لكلّ يوم فيه عيّنات، ثمّ t على الأيّام."""
    m = mask & np.isfinite(R)
    if m.sum() < 400:
        return None, 0, 0
    s = np.bincount(day_codes[m], weights=R[m], minlength=ndays)
    c = np.bincount(day_codes[m], minlength=ndays)
    dm = s[c > 0] / c[c > 0]
    nd = len(dm)
    if nd < 120:
        return None, nd, m.sum()
    sd = dm.std(ddof=1)
    return (dm.mean() / (sd / math.sqrt(nd)) if sd > 0 else None), nd, int(m.sum())


def screen(R_b, R_s, conds, day_codes, ndays, sel, top=60, pairs=True):
    """على العيّنات المختارة (sel): كلّ شرطٍ وحده ثمّ كلّ زوج — ⟵ أفضل القواعد بـ t المجمّعة."""
    R = np.concatenate([R_b, R_s])
    dc = np.concatenate([day_codes, day_codes])
    selx = np.concatenate([sel, sel])
    out = []
    singles = []
    for i, (n, mb, ms) in enumerate(conds):
        mask = np.concatenate([mb, ms]) & selx
        t, nd, ns = day_t(R, mask, dc, ndays)
        if t is not None:
            singles.append((t, i))
            out.append((t, (i,), nd, ns))
    if pairs:
        good = [i for t, i in sorted(singles, reverse=True)[:80]] + [i for t, i in sorted(singles)[:10]]
        for a in range(len(good)):
            ia = good[a]
            ma = np.concatenate([conds[ia][1], conds[ia][2]]) & selx
            for b in range(a + 1, len(good)):
                ib = good[b]
                mask = ma & np.concatenate([conds[ib][1], conds[ib][2]])
                t, nd, ns = day_t(R, mask, dc, ndays)
                if t is not None:
                    out.append((t, (ia, ib), nd, ns))
    out.sort(key=lambda x: -x[0])
    return out[:top]


def trades_of(df, rule, conds, part_mask):
    """قانون المالك: أوّل صفقتين في الجلسة بينهما 30 دقيقة على الأقلّ — الجهة من الشرط."""
    mb = np.ones(len(df), bool)
    ms = np.ones(len(df), bool)
    for i in rule:
        mb &= conds[i][1]
        ms &= conds[i][2]
    rows = []
    sub = df[part_mask]
    mb, ms = mb[part_mask.to_numpy()], ms[part_mask.to_numpy()]
    last = {}
    for j, r in enumerate(sub.itertuples(index=False)):
        key = (r.sess, r.day)
        n_taken, t_last = last.get(key, (0, -1e18))
        if n_taken >= 2 or r.t - t_last < 1800:
            continue
        cands = []
        if mb[j] and np.isfinite(r.R_buy):
            cands.append((r.R_buy, r.st_buy, True, r.risk_buy))
        if ms[j] and np.isfinite(r.R_sell):
            cands.append((r.R_sell, r.st_sell, False, r.risk_sell))
        if len(cands) != 1:  # الجهتان معًا (تعارض) أو لا شيء ⟸ لا صفقة
            continue
        R, stg, buy, risk = cands[0]
        rows.append({"t": int(r.t), "day": r.day, "R": float(R), "stage": int(stg), "buy": buy, "risk": float(risk)})
        last[key] = (n_taken + 1, r.t)
    return rows


def summary(rows):
    if not rows:
        return {"n": 0}
    R = np.array([x["R"] for x in rows])
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    halves = {}
    for x in rows:
        dt = datetime.fromtimestamp(x["t"], timezone.utc)
        k = f"{dt.year}{'a' if dt.month <= 6 else 'b'}"
        halves[k] = halves.get(k, 0) + x["R"]
    months = len({x["day"][:7] for x in rows})
    st = np.array([x["stage"] for x in rows])
    return {"n": len(R), "R_per": round(R.mean(), 4), "total": round(R.sum(), 1), "pf": round(g / l, 2) if l else None,
            "t3%": round((st == 3).mean(), 3), "stop%": round((st == 0).mean(), 3),
            "per_month": round(len(R) / max(months, 1), 1),
            "halves_pos": f"{sum(1 for v in halves.values() if v > 0)}/{len(halves)}",
            "halves": {k: round(v, 1) for k, v in sorted(halves.items())}}


def main():
    df = pd.read_pickle(D / "dataset.pkl")
    df = df[df.t >= datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp()].reset_index(drop=True)
    log("لحظات", len(df))
    dirs, regs = build_conditions(df)
    conds = expand(dirs, regs)
    log("شروط", len(conds))
    days = pd.Categorical(df.day)
    dcode, ndays = days.codes.astype(np.int64), len(days.categories)
    R_b, R_s = df.R_buy.to_numpy(float), df.R_sell.to_numpy(float)
    disc = (df.t < T_VAL).to_numpy()
    val = ((df.t >= T_VAL) & (df.t < T_HOLD))
    hold = (df.t >= T_HOLD)
    # ١· الاكتشاف
    best = screen(R_b, R_s, conds, dcode, ndays, disc)
    log("أفضل t على الاكتشاف:", round(best[0][0], 2), [conds[i][0] for i in best[0][1]])
    # ٢· ضابط الحظّ: نتائج مخلوطة بين الأيّام (الجهتان معًا لكلّ يوم تُنقل كتلةً)
    rng = np.random.default_rng(7)
    perm_max = []
    uniq = np.unique(dcode[disc])
    for k in range(int(sys.argv[1]) if len(sys.argv) > 1 else 60):
        mapping = dict(zip(uniq, rng.permutation(uniq)))
        # نقل نتائج كلّ يومٍ إلى يومٍ آخر: نعيد ترتيب R بحسب اليوم المبدَّل مع الحفاظ على الحقائق
        Rb2, Rs2 = R_b.copy(), R_s.copy()
        idx_by_day = {d: np.where((dcode == d) & disc)[0] for d in uniq}
        for d_from, d_to in mapping.items():
            a, b = idx_by_day[d_from], idx_by_day[d_to]
            m = min(len(a), len(b))
            Rb2[a[:m]], Rs2[a[:m]] = R_b[b[:m]], R_s[b[:m]]
        bb = screen(Rb2, Rs2, conds, dcode, ndays, disc, top=1)
        perm_max.append(bb[0][0] if bb else 0)
    perm_max = np.array(perm_max)
    thr = float(np.quantile(perm_max, 0.95))
    log("ضابط الحظّ: أقصى t بالصدفة — الوسيط", round(np.median(perm_max), 2), "· المئين 95", round(thr, 2))
    # ٣· التحقّق: أفضل 60 بقانون الصفقتين، والاختيار عليه وحده
    rows = []
    for t, rule, nd, ns in best:
        rv = trades_of(df, rule, conds, val)
        sv = summary(rv)
        rows.append({"rule": [conds[i][0] for i in rule], "idx": list(rule), "disc_t": round(t, 2),
                     "disc_days": nd, "disc_samples": ns, "val": sv})
    rows.sort(key=lambda r: -(r["val"].get("R_per") or -9) if r["val"].get("n", 0) >= 60 else 9)
    chosen = rows[0]
    log("المختارة بالتحقّق:", chosen["rule"], chosen["val"])
    # ٤· الخزنة المقفلة — مرّةً واحدة، للمختارة وحدها
    rh = trades_of(df, tuple(chosen["idx"]), conds, hold)
    sh = summary(rh)
    log("🔓 الخزنة:", sh)
    out = {"conditions": len(conds), "luck_perm_t_median": round(float(np.median(perm_max)), 2),
           "luck_perm_t_95": round(thr, 2), "best_disc_t": round(best[0][0], 2),
           "beats_luck": bool(best[0][0] > thr), "top_validation": rows[:15], "chosen": chosen, "holdout": sh}
    json.dump(out, open(D / "search_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    json.dump(rh, open(D / "holdout_trades.json", "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
