# -*- coding: utf-8 -*-
"""سجلّ العائد الأسبوعيّ من اليوم فصاعدًا — بلا تداول (ختم المالك «NQ» ٢٠٢٦-١٠-١٣).

لماذا: في macro.py كان «العائد» على الأسبوع التالي الوحيدَ بإشارةٍ واحدة في الفترات الثلاث (−0.073 / −0.076 / −0.214: أسبوعٌ يرتفع فيه عائد
العشر سنين ⟸ الناسداك أدنى الأسبوع التالي) لكنّ الأسابيع قليلة فلم يخرج من الصدفة. الاختبار الصادق: أسابيع لم تُرَ.
يعمل كلّ ليلة (مهمّة ويندوز) ويعيد الحساب كلّه:
- العائد: عائد العشر سنين اليوميّ من الاحتياطيّ الفيدراليّ (fed/DGS10.csv يُحدَّث إن مضى عليه يوم).
- الناسداك: إغلاق كلّ يوم تداول من مخزن سي‑تريدر (آخر شمعة دقيقة قبل 21:00 غرينتش).
- لكلّ أسبوع W ابتداءً من أسبوع 2026-10-12: تغيّر العائد في W (نقطة أساس) وعائد الناسداك في W+1؛ «مع القاعدة» = −إشارة(تغيّر العائد) ×
  عائد W+1. يُكتب حين يكتمل W+1. بلا تكلفة (أسبوعيّ، السبريد ≈ 0.4 ن.أ).
المخرج: «سجلّ العائد الأسبوعيّ.md» و yield_records.json. قياسٌ فقط.
"""
import datetime as dt
import json
import math
import os
import sqlite3
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run_yield.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CSV = os.path.join(HERE, "fed", "DGS10.csv")
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
START = dt.date(2026, 10, 12)
REFRESH_S = 20 * 3600
DAY_SHIFT_S = 3 * 3600


def refresh():
    try:
        if time.time() - os.path.getmtime(CSV) < REFRESH_S:
            return "حديث"
    except OSError:
        pass
    try:
        data = urllib.request.urlopen(URL, timeout=90).read()
        if b"DGS10" in data[:200]:
            open(CSV, "wb").write(data)
            return "حُدِّث"
    except Exception as e:  # noqa: BLE001 — يبقى الملفّ السابق
        return "تعذّر التحديث (%s)" % type(e).__name__
    return "تعذّر التحديث"


def yields():
    out = {}
    for line in open(CSV, encoding="utf-8").read().splitlines()[1:]:
        p = line.split(",")
        try:
            out[dt.date.fromisoformat(p[0])] = float(p[1])
        except (ValueError, IndexError):
            continue
    return out


def closes():
    since = int(time.mktime((START - dt.timedelta(days=21)).timetuple()))
    con = sqlite3.connect(HIST, uri=True)
    out = {}
    for t, c in con.execute("select period_start, close from candles_history where symbol='USTEC' and period='M1' and "
                            "period_start >= ? order by period_start", (since,)):
        out[dt.datetime.utcfromtimestamp(t + DAY_SHIFT_S).date()] = c
    con.close()
    return out


def week(d):
    return d.isocalendar()[:2]


def last_by_week(series):
    out = {}
    for d in sorted(series):
        out[week(d)] = series[d]
    return out


def main():
    state = refresh()
    y, c = last_by_week(yields()), last_by_week(closes())
    today = dt.datetime.utcnow().date()
    weeks = []
    d = START
    while week(d) < week(today):
        weeks.append(week(d))
        d += dt.timedelta(days=7)
    prev = week(START - dt.timedelta(days=7))
    recs = []
    for i, w in enumerate(weeks[:-1]):
        nxt = weeks[i + 1]
        p = prev if i == 0 else weeks[i - 1]
        if not all(k in y for k in (p, w)) or not all(k in c for k in (w, nxt)):
            recs.append({"الأسبوع": "%d-%02d" % w, "الحال": "بيانات ناقصة"})
            continue
        dy = (y[w] - y[p]) * 100
        ret = math.log(c[nxt] / c[w]) * 1e4
        side = -1 if dy > 0 else 1 if dy < 0 else 0
        recs.append({"الأسبوع": "%d-%02d" % w, "تغيّر_العائد_ن.أ": round(dy, 1), "الناسداك_الأسبوع_التالي_ن.أ": round(ret, 1),
                     "مع_القاعدة_ن.أ": round(side * ret, 1)})
    json.dump(recs, open(os.path.join(HERE, "yield_records.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    done = [r for r in recs if "مع_القاعدة_ن.أ" in r and r["مع_القاعدة_ن.أ"] != 0]
    L = ["# سجلّ العائد الأسبوعيّ — من أسبوع %s فصاعدًا (بلا تداول، ختم «NQ» ١٠-١٣)" % START, "",
         "القاعدة المتابَعة: أسبوعٌ يرتفع فيه عائد العشر سنين ⟸ الناسداك أدنى الأسبوع التالي (والعكس). آخر تحديث: %s غ · ملفّ العائد: %s." % (
             dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M"), state), "",
         "**المجموع:** %d أسبوعًا · صحّت %d · متوسّط «مع القاعدة» %s ن.أ · المجموع %s ن.أ" % (
             len(done), sum(1 for r in done if r["مع_القاعدة_ن.أ"] > 0),
             round(sum(r["مع_القاعدة_ن.أ"] for r in done) / len(done), 1) if done else "—",
             round(sum(r["مع_القاعدة_ن.أ"] for r in done), 1) if done else "—"), "",
         "| الأسبوع | تغيّر العائد ن.أ | الناسداك الأسبوع التالي ن.أ | مع القاعدة ن.أ |", "|---|---|---|---|"]
    for r in reversed(recs):
        L.append("| %s | %s | %s | %s |" % (r["الأسبوع"], r.get("تغيّر_العائد_ن.أ", "—"), r.get("الناسداك_الأسبوع_التالي_ن.أ", "—"),
                                         r.get("مع_القاعدة_ن.أ", r.get("الحال", "—"))))
    open(os.path.join(HERE, "سجلّ العائد الأسبوعيّ.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M غ"), "أسابيع مسجّلة:", len(done), "· العائد:", state, flush=True)


if __name__ == "__main__":
    main()
