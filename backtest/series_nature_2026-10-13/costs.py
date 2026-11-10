# -*- coding: utf-8 -*-
"""التكلفة الحقيقيّة — الخطوة 2 من «العمل على ما بين أيدينا» (المالك ١٠-١٣: «كمّلها»). وصفٌ لا فكرة: الحدّ الذي يجب أن تتجاوزه أيّ ميزة.

(١) السبريد من تِكّات سي‑تريدر لسنة (الناسداك، جهتا العرض والطلب منفصلتان): عند كلّ تِكّة طلب، السبريد = الطلب − آخر عرضٍ خلال ثانية.
    يُقرأ يومًا يومًا (لا يُحمَّل 127 مليون سطر). يُلخَّص حسب ساعة نيويورك: الوسيط · المتوسّط · المئين 90 · ونقطة الأساس.
(٢) التنفيذ من بطاقات الصفقات المؤرشفة (تصفير ١٠-١٢) والحاليّة: انزلاق الدخول = (سعر التنفيذ − المطلوب) × الجهة (موجبٌ = أسوأ)،
    وتجاوز الوقف عند ضربه — لكلّ رمز. تمويل الليلة والعمولة: غير محسوبين هنا (لا رقم مؤكَّد في بياناتنا).
قياسٌ فقط.
"""
import calendar
import glob
import json
import os
import sqlite3
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ROOT)
from shared.market_clock import CITY_NEW_YORK, local_time  # noqa: E402

HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CARDS = [r"C:\Users\NQ\QUANT_NQ\forex_runtime\var\store\trade_cards.db"] + \
        glob.glob(r"C:\Users\NQ\Desktop\سجلات\**\trade_cards.db", recursive=True)
DAY_MS = 86400 * 1000
MATCH_MS = 1000


def ny_offset_h(t):
    lt = local_time(t, CITY_NEW_YORK)
    g = time.gmtime(t)
    return ((lt.hour - g.tm_hour + 12) % 24) - 12


def spreads():
    h = sqlite3.connect(HIST, uri=True)
    a, b = h.execute("select min(ts_ms), max(ts_ms) from ticks_history where symbol='USTEC'").fetchone()
    by_hour = {k: [] for k in range(24)}
    prices = []
    ask_side = None
    day = a - a % DAY_MS
    while day <= b:
        s1 = np.array(h.execute("select ts_ms, price from ticks_history where symbol='USTEC' and side=1 and ts_ms >= ? and ts_ms < ? "
                                "order by ts_ms", (day, day + DAY_MS)).fetchall(), dtype=float).reshape(-1, 2)
        s2 = np.array(h.execute("select ts_ms, price from ticks_history where symbol='USTEC' and side=2 and ts_ms >= ? and ts_ms < ? "
                                "order by ts_ms", (day, day + DAY_MS)).fetchall(), dtype=float).reshape(-1, 2)
        day_start = day
        day += DAY_MS
        if len(s1) < 100 or len(s2) < 100:
            continue
        if ask_side is None:
            j = np.searchsorted(s1[:, 0], s2[:, 0], side="right") - 1
            ok = j >= 0
            ask_side = 2 if np.median(s2[ok, 1] - s1[j[ok], 1]) > 0 else 1
        bid, ask = (s1, s2) if ask_side == 2 else (s2, s1)
        j = np.searchsorted(bid[:, 0], ask[:, 0], side="right") - 1
        ok = (j >= 0)
        ok[ok] &= (ask[ok, 0] - bid[j[ok], 0]) <= MATCH_MS
        sp = ask[ok, 1] - bid[j[ok], 1]
        t = ask[ok, 0] / 1000.0
        good = sp >= 0
        sp, t, px = sp[good], t[good], ask[ok, 1][good]
        if not len(sp):
            continue
        off = ny_offset_h(day_start / 1000.0 + 43200)
        hours = np.floor(((t % 86400) / 3600.0 + off) % 24).astype(int)
        step = max(1, len(sp) // 4000)                     # عيّنةٌ منتظمة لكلّ يوم تكفي للوسيط والمئين
        for hh, v in zip(hours[::step], sp[::step]):
            by_hour[int(hh)].append(float(v))
        prices.append(float(np.median(px)))
    h.close()
    price = float(np.median(prices)) if prices else None
    out = {}
    for hh, v in by_hour.items():
        if len(v) < 100:
            continue
        v = np.array(v)
        out[hh] = {"عيّنة": int(len(v)), "وسيط": round(float(np.median(v)), 2), "متوسّط": round(float(v.mean()), 2),
                   "مئين_90": round(float(np.quantile(v, 0.9)), 2),
                   "وسيط_ن.أ": round(float(np.median(v)) / price * 1e4, 2) if price else None}
    allv = np.concatenate([np.array(v) for v in by_hour.values() if v])
    return out, {"وسيط": round(float(np.median(allv)), 2), "متوسّط": round(float(allv.mean()), 2),
                 "مئين_90": round(float(np.quantile(allv, 0.9)), 2), "سعر_وسيط": round(price, 1) if price else None,
                 "جهة_الطلب": ask_side}


def execution():
    rows = []
    for p in CARDS:
        if not os.path.isfile(p):
            continue
        c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
        rows += c.execute("select symbol, side, entry, fill_price, entry_slip, stop_overshoot, spread_points, outcome, sent_stop, "
                          "exit_price from cards where fill_price is not null and entry is not null").fetchall()
        c.close()
    by = {}
    for sym, side, entry, fill, slip_col, over, spr, outcome, sstop, exitp in rows:
        d = 1 if str(side).lower() == "buy" else -1 if str(side).lower() == "sell" else 0
        if not d or not entry:
            continue
        by.setdefault(sym, []).append(((fill - entry) * d, (fill - entry) * d / entry * 1e4, over, spr))
    out = {}
    for sym, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        pts = np.array([x[0] for x in v]); bps = np.array([x[1] for x in v])
        ov = np.array([x[2] for x in v if x[2] is not None], dtype=float)
        sp = np.array([x[3] for x in v if x[3] is not None], dtype=float)
        out[sym] = {"صفقات": len(v), "انزلاق_وسيط_نقاط": round(float(np.median(pts)), 3),
                    "انزلاق_متوسّط_نقاط": round(float(pts.mean()), 3), "انزلاق_متوسّط_ن.أ": round(float(bps.mean()), 2),
                    "أسوأ_من_المطلوب_٪": round(float(np.mean(pts > 0)) * 100, 1),
                    "تجاوز_الوقف_وسيط": round(float(np.median(ov)), 3) if len(ov) else None,
                    "تجاوز_الوقف_متوسّط": round(float(ov.mean()), 3) if len(ov) else None,
                    "سبريد_البطاقة_وسيط": round(float(np.median(sp)), 3) if len(sp) else None}
    return out


def main():
    t0 = time.time()
    hours, overall = spreads()
    ex = execution()
    out = {"التصميم": __doc__, "سبريد_الناسداك": overall, "حسب_ساعة_نيويورك": hours, "التنفيذ": ex, "المدّة_ث": None}
    out["المدّة_ث"] = round(time.time() - t0, 1)
    json.dump(out, open(os.path.join(HERE, "costs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# التكلفة الحقيقيّة — السبريد والتنفيذ (الخطوة 2، ١٠-١٣)", "",
         "**سبريد الناسداك على سنة (نقاط):** الوسيط %s · المتوسّط %s · المئين 90 %s · عند سعرٍ وسيط %s." % (
             overall["وسيط"], overall["متوسّط"], overall["مئين_90"], overall["سعر_وسيط"]), "",
         "| ساعة نيويورك | وسيط | متوسّط | مئين 90 | وسيط ن.أ |", "|---|---|---|---|---|"]
    for hh in sorted(hours):
        r = hours[hh]
        L.append("| %02d | %s | %s | %s | %s |" % (hh, r["وسيط"], r["متوسّط"], r["مئين_90"], r["وسيط_ن.أ"]))
    L += ["", "**التنفيذ من بطاقات الصفقات** (انزلاق الدخول موجبٌ = أسوأ من المطلوب؛ تجاوز الوقف كما سجّلته البطاقة):", "",
          "| الرمز | صفقات | انزلاق وسيط (نقاط) | انزلاق متوسّط (نقاط) | متوسّط ن.أ | أسوأ من المطلوب ٪ | تجاوز الوقف وسيط / متوسّط | سبريد البطاقة وسيط |",
          "|---|---|---|---|---|---|---|---|"]
    for sym, r in ex.items():
        L.append("| %s | %d | %s | %s | %s | %s | %s / %s | %s |" % (sym, r["صفقات"], r["انزلاق_وسيط_نقاط"], r["انزلاق_متوسّط_نقاط"],
                                                                r["انزلاق_متوسّط_ن.أ"], r["أسوأ_من_المطلوب_٪"], r["تجاوز_الوقف_وسيط"],
                                                                r["تجاوز_الوقف_متوسّط"], r["سبريد_البطاقة_وسيط"]))
    L += ["", "تمويل الليلة والعمولة غير محسوبين. المدّة: %s ث." % out["المدّة_ث"]]
    open(os.path.join(HERE, "التكلفة الحقيقيّة.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("انتهى", out["المدّة_ث"], "ث", flush=True)


if __name__ == "__main__":
    main()
