# -*- coding: utf-8 -*-
"""الحكم على البنية (201–207) بمبدأ الهرم — قياسٌ فقط، على أحداث `run_chain.py` بكود الذرّات نفسه.

القمّة (ساعة · 4 ساعات · يوم): هل تصيب حقيقة البنية عند لحظة القرار جهةَ الجلسة؟
    لندن: القرار 08:15 لندن ⟵ النهاية 11:00 لندن · نيويورك: القرار 09:45 ⟵ النهاية 13:00 نيويورك.
الوسط (5د · 15د): كسرٌ (BOS 204) أو تغيّرٌ (CHoCH 205) داخل النافذة ⟸ دخولٌ عند إغلاق شمعة الكسر في جهته،
    الوقف خلف آخر قمّة/قاع مؤكَّد لـ201 على الإطار نفسه ± نقطة (التحليل نفسه يضع الوقف — بلا قصّ)،
    يُقبل إن وقع بين 10 و50 نقطة (قانون المالك) ويُعدّ ما خرج، الهدف 3R، أثلاث المالك على شموع الدقيقة بكلفة 1.5،
    مركزٌ واحد، صفقتان في الجلسة. ومرشّح الهرم: جهة 207 على الساعة/الأربع ساعات عند الدخول.
التعلّم حتّى 2023-02-05، والاختبار بعده (كالقياسات السابقة).
"""
import bisect
import json
import math
import pathlib
import sqlite3
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

D = pathlib.Path(__file__).resolve().parent
EV = D / "events"
# أمر المالك «ما بدها ترجع لـ2014 … خلّيها من 2018» (١٠-٠٩ فجرًا): تعلّمٌ أوّل 70٪ واختبارٌ آخر 30٪.
START = datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp()  # المالك: «خلّيها من 2018»
END = datetime(2026, 10, 6, tzinfo=timezone.utc).timestamp()
SPLIT = START + 0.7 * (END - START)
COST = 1.5
LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")

db = sqlite3.connect(r"file:C:\Users\NQ\QUANT_NQ\forex_runtime\var\history\ctrader_history.db?mode=ro", uri=True)
M1 = db.execute("select period_start, open, high, low, close from candles_history "
                "where symbol='USTEC' and period='M1' and period_start >= ? order by period_start", (int(START) - 86400 * 7,)).fetchall()
MT = [r[0] for r in M1]
print("دقائق:", len(M1), flush=True)


def close_at(t):
    """إغلاق آخر دقيقةٍ أُغلقت عند t أو قبله."""
    i = bisect.bisect_right(MT, t - 60) - 1
    return (M1[i][4], M1[i][0] + 60) if i >= 0 else (None, None)


def sessions():
    """أيّام التداول بلحظتي القرار والنهاية لكلّ جلسة (بالتوقيتين الصيفيّ والشتويّ)."""
    days = sorted({datetime.fromtimestamp(t, timezone.utc).date() for t in MT[::60]})
    out = []
    for d in days:
        if d.weekday() >= 5:
            continue
        for name, tz, dh, dm, eh, em in (("london", LON, 8, 15, 11, 0), ("ny", NY, 9, 45, 13, 0)):
            td = datetime(d.year, d.month, d.day, dh, dm, tzinfo=tz).timestamp()
            te = datetime(d.year, d.month, d.day, eh, em, tzinfo=tz).timestamp()
            c0, k0 = close_at(td)
            c1, k1 = close_at(te)
            if c0 is None or c1 is None or k0 < td - 300 or k1 < te - 300 or k1 <= k0:
                continue
            out.append((name, d.isoformat(), td, te, c0, c1))
    return out


SESS = sessions()
print("جلسات:", len(SESS), flush=True)


def load(frame, lb):
    p = EV / f"{frame}_lb{lb}.jsonl"
    if not p.exists():
        return None
    ev = defaultdict(list)
    for line in open(p, encoding="utf-8"):
        r = json.loads(line)
        ev[r["e"]].append(r)
    return ev


def last_before(rows, times, t):
    i = bisect.bisect_right(times, t) - 1
    return rows[i] if i >= 0 else None


def top_signals(ev):
    """حقائق الجهة عند لحظةٍ: 207 · آخر خارجيّ (HH/LL) · آخر داخليّ (HL/LH) · آخر BOS · آخر تحوّل MSS."""
    def series(rows, fn):
        rows = [r for r in rows if fn(r) != 0]
        return rows, [r["t"] for r in rows], fn
    return {
        "207_حالة_الاتجاه": series(ev.get("trend207", []),
                                    lambda r: {"uptrend": 1, "downtrend": -1}.get(r.get("official"), 0)),
        "202_آخر_خارجي": series(ev.get("external", []), lambda r: {"HH": 1, "LL": -1}.get(r.get("sig"), 0)),
        "203_آخر_داخلي": series(ev.get("internal", []), lambda r: {"HL": 1, "LH": -1}.get(r.get("sig"), 0)),
        "204_آخر_BOS": series(ev.get("bos", []),
                              lambda r: {"above": 1, "below": -1}.get(r.get("break_side"), 0)),
        "206_آخر_MSS": series(ev.get("mss", []),
                              lambda r: {"above": 1, "below": -1}.get(r.get("break_side"), 0)),
    }


def binom_p(k, n, p=0.5):
    if n == 0:
        return 1.0
    z = (k - n * p) / math.sqrt(n * p * (1 - p))
    return 0.5 * math.erfc(z / math.sqrt(2))  # جانبٌ واحد: أفضل من p


def eval_top():
    res = []
    for frame in ("1h", "4h", "1d"):
        for lb in (1, 2, 3, 5):
            ev = load(frame, lb)
            if ev is None:
                continue
            sigs = top_signals(ev)
            for sname, (rows, times, fn) in sigs.items():
                for sess in ("london", "ny", "both"):
                    agg = {"train": [0, 0, []], "test": [0, 0, []]}
                    up_base = {"train": [0, 0], "test": [0, 0]}
                    for name, day, td, te, c0, c1 in SESS:
                        if td < START: continue
                        if sess != "both" and name != sess:
                            continue
                        part = "train" if td < SPLIT else "test"
                        ret = (c1 - c0) / c0 * 1e4
                        up_base[part][0] += ret > 0
                        up_base[part][1] += 1
                        r = last_before(rows, times, td)
                        if r is None:
                            continue
                        d = fn(r)
                        a = agg[part]
                        a[1] += 1
                        a[0] += (ret * d) > 0
                        a[2].append(ret * d)
                    row = {"frame": frame, "lb": lb, "signal": sname, "session": sess}
                    for part in ("train", "test"):
                        k, n, rs = agg[part]
                        row[part] = {"n": n, "agree": round(k / n, 4) if n else None,
                                     "p_vs_half": round(binom_p(k, n), 4),
                                     "mean_bps": round(st.mean(rs), 2) if rs else None,
                                     "t": round(st.mean(rs) / (st.pstdev(rs) / math.sqrt(len(rs))), 2)
                                     if len(rs) > 2 and st.pstdev(rs) > 0 else None,
                                     "up_base": round(up_base[part][0] / up_base[part][1], 4)
                                     if up_base[part][1] else None}
                    res.append(row)
    return res


# ─────────────── الوسط: صفقات الكسر بأثلاث المالك ───────────────
def thirds(entry, stop, target, buy, t_entry):
    """أثلاث المالك (مطابقة `R.thirds`): الهدف الأوّل ثلث المسافة ⟸ ثلثٌ والوقف للدخول ·
    الثاني ثلثاها ⟸ نصف الباقي والوقف للأوّل · الثالث الهدف. ⟵ (R، المرحلة، وقت الخروج).
    الكلفة 1.5 نقطة عاديّة (كالمسطرة)."""
    COST = 1.5
    risk, span, sgn = abs(entry - stop), abs(target - entry), (1 if buy else -1)
    t1_, t2_ = entry + sgn * span / 3, entry + sgn * 2 * span / 3
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    k = bisect.bisect_left(MT, t_entry)  # أوّل دقيقةٍ تبدأ عند الدخول أو بعده
    while k < len(M1):
        t, o, h, lo, c = M1[k]
        if (lo <= cur) if buy else (h >= cur):
            px = min(o, cur) if buy else max(o, cur)
            return real + rem * ((px - entry) * sgn / risk) - COST / risk, stage, t
        hit = (lambda v: h >= v) if buy else (lambda v: lo <= v)
        if stage < 1 and hit(t1_):
            real += (rem / 3) * (span / 3 / risk); rem -= rem / 3; cur = entry; stage = 1
        if stage < 2 and hit(t2_):
            real += (rem / 2) * (2 * span / 3 / risk); rem -= rem / 2; cur = t1_; stage = 2
        if hit(target):
            return real + rem * (span / risk) - COST / risk, 3, t
        k += 1
    return None, None, None


def in_window(t):
    for tz, (sh, sm), (eh, em) in ((LON, (8, 15), (11, 0)), (NY, (9, 45), (13, 0))):
        lt = datetime.fromtimestamp(t, tz)
        if lt.weekday() >= 5:
            continue
        m = lt.hour * 60 + lt.minute
        if sh * 60 + sm <= m < eh * 60 + em:
            return ("london" if tz is LON else "ny") + "|" + lt.date().isoformat()
    return None


def dir207_series(frame, lb=2):
    ev = load(frame, lb)
    if ev is None:
        return None
    rows = [r for r in ev.get("trend207", [])]
    return rows, [r["t"] for r in rows]


PYR = {"none": None, "1h": dir207_series("1h"), "4h": dir207_series("4h")}


def eval_mid():
    res, trades_out = [], {}
    for frame in ("5m", "15m", "1h"):
        for lb in (1, 2, 3, 5):
            ev = load(frame, lb)
            if ev is None:
                continue
            sw_hi = [(r["t"], r["price"]) for r in ev.get("swing", []) if r.get("sig") == "swing_high" and "price" in r]
            sw_lo = [(r["t"], r["price"]) for r in ev.get("swing", []) if r.get("sig") == "swing_low" and "price" in r]
            hi_t, lo_t = [x[0] for x in sw_hi], [x[0] for x in sw_lo]
            for kind in ("bos", "choch"):
                evs = sorted(ev.get(kind, []), key=lambda r: r["t"])
                for filt in ("none", "1h", "4h"):
                    pyr = PYR[filt]
                    trades, out_range, busy, per_sess = [], {"<10": 0, ">50": 0, "ok": 0}, 0.0, defaultdict(int)
                    for r in evs:
                        t = r["t"]
                        side = r.get("break_side")
                        if side not in ("above", "below") or t < busy or t < START:
                            continue
                        key = in_window(t - 1)
                        if key is None or per_sess[key] >= 2:
                            continue
                        buy = side == "above"
                        if pyr is not None:
                            prow = last_before(pyr[0], pyr[1], t)
                            if prow is None or prow.get("official") != ("uptrend" if buy else "downtrend"):
                                continue
                        entry = r.get("close")
                        if entry is None:
                            continue
                        if buy:
                            i = bisect.bisect_right(lo_t, t) - 1
                            if i < 0:
                                continue
                            stop = sw_lo[i][1] - 1.0
                        else:
                            i = bisect.bisect_right(hi_t, t) - 1
                            if i < 0:
                                continue
                            stop = sw_hi[i][1] + 1.0
                        risk = (entry - stop) if buy else (stop - entry)
                        # قانون المالك «ستوبنا بين 15 و45، وأقصاه 50 — نقاط عاديّة مو نقطة أساس» (١٠-٠٩ فجرًا).
                        risk_bps = risk / entry * 1e4 if entry else 0.0
                        if risk < 15.0:
                            out_range["<10"] += 1
                            continue
                        if risk > 50.0:
                            out_range[">50"] += 1
                            continue
                        out_range["ok"] += 1
                        target = entry + 3 * risk if buy else entry - 3 * risk
                        R, stage, t_exit = thirds(entry, stop, target, buy, t)
                        if R is None:
                            continue
                        per_sess[key] += 1
                        busy = t_exit
                        trades.append({"t": t, "buy": buy, "risk": round(risk, 2), "risk_bps": round(risk_bps, 2),
                                       "R": round(R, 4), "stage": stage, "sess": key.split("|")[0]})
                    row = {"frame": frame, "lb": lb, "kind": kind, "filter": filt, "stops": out_range}
                    for part, sel in (("train", lambda x: x["t"] < SPLIT), ("test", lambda x: x["t"] >= SPLIT)):
                        tt = [x for x in trades if sel(x)]
                        rs = [x["R"] for x in tt]
                        g = sum(x for x in rs if x > 0)
                        l = -sum(x for x in rs if x < 0)
                        stages = defaultdict(int)
                        for x in tt:
                            stages[x["stage"]] += 1
                        n = len(tt)
                        row[part] = {"n": n, "R_per": round(st.mean(rs), 4) if rs else None,
                                     "total": round(sum(rs), 1), "pf": round(g / l, 2) if l > 0 else None,
                                     "stop%": round(stages[0] / n, 3) if n else None,
                                     "t1_be%": round(stages[1] / n, 3) if n else None,
                                     "t2%": round(stages[2] / n, 3) if n else None,
                                     "t3%": round(stages[3] / n, 3) if n else None}
                    # أنصاف السنة في الاختبار
                    halves = defaultdict(float)
                    for x in trades:
                        if x["t"] >= SPLIT:
                            dt = datetime.fromtimestamp(x["t"], timezone.utc)
                            halves[f"{dt.year}{'a' if dt.month <= 6 else 'b'}"] += x["R"]
                    row["test_halves"] = {k: round(v, 1) for k, v in sorted(halves.items())}
                    res.append(row)
                    trades_out[f"{frame}_lb{lb}_{kind}_{filt}"] = trades
    return res, trades_out


if __name__ == "__main__":
    top = eval_top()
    json.dump(top, open(D / "top.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("القمّة:", len(top), flush=True)
    mid, trades = eval_mid()
    json.dump(mid, open(D / "mid.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(trades, open(D / "mid_trades.json", "w", encoding="utf-8"))
    print("الوسط:", len(mid), flush=True)
