# -*- coding: utf-8 -*-
"""إعادة بطاقة «استمرار الاتّجاه بعد الارتداد» على تاريخ الناسداك — قراءة فقط، خارج المشروع.

البطاقة (ورقة النقاش ٤-س/٤-ف):
  الجهة   : آخر شمعة ساعة مغلقة وآخر أربع ساعات مغلقة كلتاهما فوق متوسّطهما الأسّيّ 20 ⟸ شراء (أو تحته ⟸ بيع).
  الوقت   : نافذتا المالك — ذروة لندن 08:00–11:00 بتوقيت لندن · افتتاح أمريكا 09:30–12:00 بتوقيت نيويورك.
  الخبر   : لا دخول من 15 د قبل خبرٍ أمريكيّ عالي الأهمّيّة حتّى 15 د بعده (تقويم ميتاتريدر المصدَّر).
  الدخول  : على 5 د — قمّةٌ مؤكَّدة ثمّ قاعٌ مؤكَّد بعدها (الارتداد) ثمّ إغلاق 5 د فوق تلك القمّة (كسر الهيكل) ⟸ شراء.
  الوقف   : أبعد من (قاع الارتداد − ب × متوسّط المدى 5 د) ومن (الدخول − ن × متوسّط المدى 5 د).
  الهدف   : أقرب قمّة ساعة/4 ساعات مؤكَّدة تعطي ≥ 3R، وفي متناول السوق: ≤ ج × متوسّط المدى اليوميّ.
  الإدارة : أثلاث المالك — الأوّل ثلث المسافة: ثلث العقد والوقف للدخول · الثاني: نصف الباقي والوقف للأوّل · الثالث خروج.
  مركزٌ واحد في الوقت · كلفة 1.5 نقطة للدورة · المحاكاة على شموع الدقيقة والوقف أوّلًا عند الالتباس.
"""
from __future__ import annotations

import bisect
import calendar
import itertools
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
SYMBOL = "USTEC"
START = calendar.timegm(time.strptime("2024-10-01", "%Y-%m-%d"))
COST = 1.5
CAL_OFFSET_S = 3 * 3600          # وقت التقويم − 3 ساعات = غرينتش (ثبت على قرارات الفائدة؛ يُؤكَّد)
LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")

db = sqlite3.connect(DB, uri=True)


def bars(period, since):
    return [tuple(map(float, r)) for r in db.execute(
        "select period_start, open, high, low, close from candles_history where symbol=? and period=? "
        "and period_start>=? order by period_start", (SYMBOL, period, int(since)))]


def ema(values, n=20):
    k, out, e = 2.0 / (n + 1), [], None
    for v in values:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def atr(rows, n=14):
    out, trs, prev = [], [], None
    for t, o, h, l, c in rows:
        tr = h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))
        trs.append(tr); prev = c
        w = trs[-n:]
        out.append(sum(w) / len(w))
    return out


def swings(rows, seconds, look=2):
    """(وقت التأكيد، سعر، قمّة؟) — تأكيدٌ بعد إغلاق الشمعة look بعد المركز."""
    out = []
    for i in range(look, len(rows) - look):
        h, l = rows[i][2], rows[i][3]
        win = rows[i - look:i + look + 1]
        confirm = rows[i + look][0] + seconds
        if h == max(r[2] for r in win) and all(r[2] < h for r in win if r is not rows[i]):
            out.append((confirm, h, True))
        if l == min(r[3] for r in win) and all(r[3] > l for r in win if r is not rows[i]):
            out.append((confirm, l, False))
    out.sort()
    return out


def closed_index(times, seconds, t):
    """فهرس آخر شمعةٍ أُغلقت قبل t."""
    return bisect.bisect_right(times, t - seconds) - 1


print("تحميل…", flush=True)
m1 = bars("M1", START - 86400)
m5 = bars("M5", START - 30 * 86400)
h1 = bars("H1", START - 120 * 86400)
h4 = bars("H4", START - 300 * 86400)
d1 = bars("D1", START - 400 * 86400)
END = m1[-1][0]
t1 = [r[0] for r in m1]
t5, th1, th4, td1 = ([r[0] for r in x] for x in (m5, h1, h4, d1))
e_h1, e_h4 = ema([r[4] for r in h1]), ema([r[4] for r in h4])
a5, ad1 = atr(m5), atr(d1)
sw5 = swings(m5, 300)
sw_htf = sorted(swings(h1, 3600) + swings(h4, 14400))
sw5_t = [s[0] for s in sw5]
swh_t = [s[0] for s in sw_htf]
print("شموع: دقيقة=%d 5د=%d ساعة=%d 4س=%d يوم=%d · قمم/قيعان 5د=%d · ساعة+4س=%d" % (
    len(m1), len(m5), len(h1), len(h4), len(d1), len(sw5), len(sw_htf)), flush=True)

cal = sqlite3.connect(CAL, uri=True)
news = sorted(t - CAL_OFFSET_S for (t,) in cal.execute(
    "select time_server from calendar_history where country_code='US' and importance=3"))
print("أخبار أمريكيّة عالية الأهمّيّة: %d" % len(news), flush=True)


def in_window(t):
    lt = datetime.fromtimestamp(t, LON); nt = datetime.fromtimestamp(t, NY)
    if lt.weekday() >= 5:
        return None
    lm, nm = lt.hour * 60 + lt.minute, nt.hour * 60 + nt.minute
    if 8 * 60 <= lm < 11 * 60:
        return "لندن"
    if 9 * 60 + 30 <= nm < 12 * 60:
        return "نيويورك"
    return None


def news_block(t):
    i = bisect.bisect_left(news, t - 900)
    return i < len(news) and news[i] <= t + 900


def direction(t):
    i1, i4 = closed_index(th1, 3600, t), closed_index(th4, 14400, t)
    if i1 < 20 or i4 < 20:
        return 0
    up = h1[i1][4] > e_h1[i1] and h4[i4][4] > e_h4[i4]
    dn = h1[i1][4] < e_h1[i1] and h4[i4][4] < e_h4[i4]
    return 1 if up else -1 if dn else 0


def thirds(entry, stop, target, buy, k):
    risk, span, sgn = abs(entry - stop), abs(target - entry), (1 if buy else -1)
    t1_, t2_ = entry + sgn * span / 3, entry + sgn * 2 * span / 3
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    while k < len(m1):
        t, o, h, lo, c = m1[k]
        if (lo <= cur) if buy else (h >= cur):
            px = min(o, cur) if buy else max(o, cur)
            return real + rem * ((px - entry) * sgn / risk) - COST / risk, t
        hit = (lambda v: h >= v) if buy else (lambda v: lo <= v)
        if stage < 1 and hit(t1_):
            real += (rem / 3) * (span / 3 / risk); rem -= rem / 3; cur = entry; stage = 1
        if stage < 2 and hit(t2_):
            real += (rem / 2) * (2 * span / 3 / risk); rem -= rem / 2; cur = t1_; stage = 2
        if hit(target):
            return real + rem * (span / risk) - COST / risk, t
        k += 1
    return None, None


def run(b, n, c, rr=3.0):
    trades, busy = [], 0.0
    last_bar = None
    for j in range(len(m5)):
        t_close = m5[j][0] + 300
        if t_close < START or t_close < busy:
            continue
        win = in_window(t_close)
        if not win or news_block(t_close):
            continue
        d = direction(t_close)
        if d == 0:
            continue
        buy = d > 0
        close = m5[j][4]
        # آخر قمّة وآخر قاع مؤكَّدَين قبل إغلاق هذه الشمعة
        i = bisect.bisect_right(sw5_t, t_close - 1) - 1
        last_hi = last_lo = None
        while i >= 0 and (last_hi is None or last_lo is None):
            ts, px, is_hi = sw5[i]
            if is_hi and last_hi is None:
                last_hi = (ts, px)
            if not is_hi and last_lo is None:
                last_lo = (ts, px)
            i -= 1
        if last_hi is None or last_lo is None:
            continue
        if buy:   # قمّة ثمّ قاعٌ بعدها (ارتداد) ثمّ إغلاقٌ فوق القمّة
            if not (last_lo[0] > last_hi[0] and close > last_hi[1] and m5[j - 1][4] <= last_hi[1]):
                continue
            pull = last_lo[1]
        else:
            if not (last_hi[0] > last_lo[0] and close < last_lo[1] and m5[j - 1][4] >= last_lo[1]):
                continue
            pull = last_hi[1]
        atr5 = a5[j]
        entry = close
        stop = min(pull - b * atr5, entry - n * atr5) if buy else max(pull + b * atr5, entry + n * atr5)
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        idd = closed_index(td1, 86400, t_close)
        reach = c * ad1[idd] if idd >= 0 else None
        # أقرب مستوى ساعة/4س مؤكَّد في الجهة يعطي ≥ rr وفي المتناول
        k = bisect.bisect_right(swh_t, t_close) - 1
        cands = [px for ts, px, is_hi in sw_htf[max(0, k - 400):k + 1]
                 if is_hi == buy and ((px > entry) if buy else (px < entry))]
        ok = [px for px in cands if abs(px - entry) >= rr * risk and (reach is None or abs(px - entry) <= reach)]
        if not ok:
            continue
        target = min(ok) if buy else max(ok)
        k1 = bisect.bisect_right(t1, t_close - 60)   # أوّل دقيقة بعد الإغلاق
        r, exit_t = thirds(entry, stop, target, buy, k1)
        if r is None:
            break
        trades.append((t_close, r, win, buy, risk / entry * 1e4))
        busy = exit_t + 60
    return trades


def stats(tr, label=""):
    if not tr:
        return {"n": 0}
    rs = [x[1] for x in tr]
    wins = sum(r > 0 for r in rs)
    gp = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    eq = peak = dd = 0.0
    for r in rs:
        eq += r; peak = max(peak, eq); dd = max(dd, peak - eq)
    halves = {}
    for t, r, *_ in tr:
        dt = datetime.fromtimestamp(t, timezone.utc)
        key = "%d%s" % (dt.year, "أ" if dt.month <= 6 else "ب")
        halves[key] = halves.get(key, 0.0) + r
    return {"n": len(rs), "فوز%": round(100 * wins / len(rs)), "R": round(sum(rs), 1), "R/صفقة": round(sum(rs) / len(rs), 3),
            "معامل": round(gp / gl, 2) if gl else None, "سحب_R": round(dd, 1),
            "أنصاف": {k: round(v, 1) for k, v in sorted(halves.items())},
            "وقف_ن.أ_وسيط": round(sorted(x[4] for x in tr)[len(tr) // 2], 1)}


if __name__ == "__main__":
    split = START + 0.7 * (END - START)
    rows = []
    for b, n, c in itertools.product((0.0, 0.5), (1.0, 1.5, 2.0, 2.5), (0.75, 1.0, 1.5)):
        tr = run(b, n, c)
        learn = [x for x in tr if x[0] < split]
        test = [x for x in tr if x[0] >= split]
        rows.append({"ب": b, "ن": n, "ج": c, "تعلّم": stats(learn), "اختبار": stats(test), "كلّه": stats(tr),
                     "لندن": stats([x for x in tr if x[2] == "لندن"]), "نيويورك": stats([x for x in tr if x[2] == "نيويورك"])})
        s = rows[-1]
        print("ب=%.1f ن=%.1f ج=%.2f | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | كلّه R=%s أنصاف=%s" % (
            b, n, c, s["تعلّم"].get("n"), s["تعلّم"].get("R/صفقة"), s["اختبار"].get("n"), s["اختبار"].get("R/صفقة"),
            s["اختبار"].get("معامل"), s["كلّه"].get("R"), s["كلّه"].get("أنصاف")), flush=True)
    json.dump(rows, open(sys.argv[1] if len(sys.argv) > 1 else "card_replay_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
