# -*- coding: utf-8 -*-
"""الاحتمالات الأساسيّة — الخطوة 5 من «العمل على ما بين أيدينا» (المالك ١٠-١٣: «كمّل»). وصفٌ لا فكرة: «سعر العدل» لأيّ استراتيجيّة.

السؤال: دخولٌ بلا أيّ ميزة (كلّ ساعةٍ في أيّام العمل، شراءً وبيعًا معًا)، بوقفٍ وهدف — ما احتمال أن يُضرب الهدف قبل الوقف؟ وكم تأكل التكلفة؟
الوقف بطريقتين:
  ① بالتقلّب: k × انحراف ربع الساعة المتوقَّع (من تقلّب الدقيقة في الساعة السابقة × √15)، k = 0.5 · 1 · 2 · 3.
  ② بالنقاط (كما تعمل استراتيجيّاتنا): 5 · 10 · 15 · 20 · 30 · 45 نقطة — في 2025–2026 وحدها (السعر الحاليّ).
الهدف = 1 · 2 · 3 أضعاف الوقف. المشي على شموع الدقيقة (قمّة/قاع) حتّى 8 ساعات؛ إن ضُربا في الدقيقة نفسها يُعدّ وقفًا (أحوط)؛ وإن لم يُضرب
أيٌّ منهما يُغلق على سعر الساعة الثامنة. النتيجة بوحدة المخاطرة، والتكلفة = سبريد نقطة ÷ مسافة الوقف.
مرجع السير العشوائيّ بلا انحراف: احتمال الهدف ≈ 1 ÷ (1 + النسبة) — 50٪ · 33٪ · 25٪.
الفترات: 2014–2019 · 2020–2024 · 2025–2026، وجلسة نيويورك (09:30–16:00) مقابل خارجها. قياسٌ فقط.
"""
import calendar
import json
import math
import os
import sqlite3
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "run_probs.log"), "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ROOT)
from shared.market_clock import CITY_NEW_YORK, local_time  # noqa: E402

HIST = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
ERAS = (("2014–2019", 0, calendar.timegm((2020, 1, 1, 0, 0, 0))),
        ("2020–2024", calendar.timegm((2020, 1, 1, 0, 0, 0)), calendar.timegm((2025, 1, 1, 0, 0, 0))),
        ("2025–2026", calendar.timegm((2025, 1, 1, 0, 0, 0)), 1e12))
KS = (0.5, 1.0, 2.0, 3.0)
POINTS = (5.0, 10.0, 15.0, 20.0, 30.0, 45.0)
RRS = (1.0, 2.0, 3.0)
HOLD = 8 * 60
LOOKBACK = 60
SPREAD_PTS = 1.0
STEP_S = 3600
MIN_BARS = 300
MAX_GAP_S = 90 * 60


def load():
    con = sqlite3.connect(HIST, uri=True)
    a = np.array(con.execute("select period_start, high, low, close from candles_history where symbol='USTEC' and period='M1' "
                             "order by period_start").fetchall(), dtype=float)
    con.close()
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def first_hit(hi, lo, p0, stop, target, side):
    """+النسبة إن ضُرب الهدف أوّلًا، −1 إن ضُرب الوقف (أو كلاهما في الدقيقة نفسها)، وإلّا الإغلاق الأخير بوحدة المخاطرة."""
    if side > 0:
        s_hit = lo <= p0 - stop
        t_hit = hi >= p0 + target
    else:
        s_hit = hi >= p0 + stop
        t_hit = lo <= p0 - target
    si = int(np.argmax(s_hit)) if s_hit.any() else None
    ti = int(np.argmax(t_hit)) if t_hit.any() else None
    if si is None and ti is None:
        return None
    if si is not None and (ti is None or si <= ti):
        return -1.0
    return target / stop


def main():
    t0 = time.time()
    ts, hi, lo, cl = load()
    r1 = np.diff(np.log(cl))
    # ١٠-١٣ تصحيح (المالك «حلّ»): كان الشرط 480 شمعةً متّصلة في 540 دقيقة، فاستُبعد كلّ دخولٍ يعبر توقّف 17:00–18:00 نيويورك —
    # أي أغلب دخولات الجلسة. الآن النافذة 8 ساعات **بالوقت**، تُقبل فيها فجوة التوقّف اليوميّ، ويُستبعد ما يعبر العطلة (فجوة > 90 دقيقة)
    # أو ما فيه أقلّ من 300 شمعة.
    entries, ends = [], []
    last = -1e18
    for i in range(LOOKBACK + 1, len(ts) - 1):
        if ts[i] - last < STEP_S or time.gmtime(ts[i]).tm_wday >= 5:
            continue
        j = int(np.searchsorted(ts, ts[i] + HOLD * 60, side="right"))
        if j - i < MIN_BARS or j > len(ts) or float(np.max(np.diff(ts[i:j]))) > MAX_GAP_S:
            continue
        last = ts[i]
        entries.append(i)
        ends.append(j)
    days = {}
    res = {}
    for i, j_end in zip(entries, ends):
        era = next(name for name, a, b in ERAS if a <= ts[i] < b)
        d = int(ts[i] // 86400)
        if d not in days:
            lt = local_time(d * 86400 + 43200, CITY_NEW_YORK)
            days[d] = (lt.hour - time.gmtime(d * 86400 + 43200).tm_hour + 12) % 24 - 12
        ny = ((ts[i] % 86400) / 3600.0 + days[d]) % 24
        sess = "الجلسة" if 9.5 <= ny < 16 else "خارجها"
        sd = float(np.std(r1[i - LOOKBACK:i]))
        if sd == 0:
            continue
        p0 = float(cl[i])
        sig15 = p0 * sd * math.sqrt(15)
        h, l = hi[i + 1:j_end], lo[i + 1:j_end]
        end = float(cl[j_end - 1])
        stops = [("تقلّب %g" % k, k * sig15) for k in KS]
        if era == "2025–2026":
            stops += [("%g نقطة" % p, p) for p in POINTS]
        for name, stop in stops:
            for rr in RRS:
                for side in (1, -1):
                    out = first_hit(h, l, p0, stop, rr * stop, side)
                    if out is None:
                        out = side * (end - p0) / stop
                    key = (era, sess, name, rr)
                    res.setdefault(key, []).append((out, SPREAD_PTS / stop, out >= rr))
    table = {}
    for (era, sess, name, rr), v in res.items():
        a = np.array(v)
        table.setdefault(era, {}).setdefault(sess, {}).setdefault(name, {})["%g" % rr] = {
            "عدد": int(len(a)), "احتمال_الهدف_٪": round(float(a[:, 2].mean()) * 100, 1),
            "متوسّط_قبل_التكلفة": round(float(a[:, 0].mean()), 3), "التكلفة": round(float(a[:, 1].mean()), 3),
            "متوسّط_بعد_التكلفة": round(float((a[:, 0] - a[:, 1]).mean()), 3)}
    out = {"التصميم": __doc__, "دخولات": len(entries), "النتائج": table, "المدّة_ث": round(time.time() - t0, 1)}
    json.dump(out, open(os.path.join(HERE, "probs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# الاحتمالات الأساسيّة — «سعر العدل» لأيّ صفقة بلا ميزة (الخطوة 5، ١٠-١٣)", "",
         "دخولات: %d (كلّ ساعة، أيّام العمل، شراءً وبيعًا). النتيجة بوحدة المخاطرة؛ التكلفة سبريد نقطة ÷ الوقف. مرجع السير العشوائيّ لاحتمال"
         " الهدف: 50٪ (1:1) · 33٪ (1:2) · 25٪ (1:3)." % len(entries), ""]
    for era, by_sess in table.items():
        for sess, by_stop in by_sess.items():
            L += ["## %s — %s" % (era, sess), "", "| الوقف | النسبة | عدد | احتمال الهدف ٪ | قبل التكلفة | التكلفة | بعد التكلفة |",
                  "|---|---|---|---|---|---|---|"]
            for name, by_rr in by_stop.items():
                for rr, r in by_rr.items():
                    L.append("| %s | 1:%s | %d | %s | %s | %s | %s |" % (name, rr, r["عدد"], r["احتمال_الهدف_٪"], r["متوسّط_قبل_التكلفة"],
                                                                     r["التكلفة"], r["متوسّط_بعد_التكلفة"]))
            L.append("")
    L.append("المدّة: %s ث." % out["المدّة_ث"])
    open(os.path.join(HERE, "الاحتمالات الأساسيّة.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("انتهى", out["المدّة_ث"], "ث", flush=True)


if __name__ == "__main__":
    main()
