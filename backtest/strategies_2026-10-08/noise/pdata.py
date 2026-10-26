# -*- coding: utf-8 -*-
"""نسخةٌ للقراءة من أدوات `backtest/card_414/card_replay.py` بفترةٍ قابلة للضبط — الأصل لا يُلمس.

الضبط بمتغيّرَي البيئة:
  NOISE_START  (افتراضيًّا 2024-10-01 كالأصل)
  NOISE_END    (حصريّ؛ غيابه ⟸ آخر شمعة دقيقة كالأصل: END = m1[-1][0])
الدوالّ منسوخةٌ حرفيًّا (ema · atr · swings · closed_index · thirds · stats · news_block)، والتحميل بنفس
هوامش التحمية (دقيقة −1 يوم · ساعة −120 · 4س −300 · يوم −400 يوم). الفرق الوحيد:
  · 5 د تُحمَّل من −60 يومًا ومعها tick_volume (للحدود ولمتوسّط السعر المرجّح بالحجم)؛ متوسّط مدى 5 د
    بسيطٌ على آخر 14 فلا يتغيّر ببداية التحميل.
  · مع NOISE_END: كلّ شموع القرار (5 د · ساعة · 4س · يوم) تُقطع عند النهاية، وشموع الدقيقة وحدها تمتدّ
    45 يومًا بعدها لتكمل إدارة صفقةٍ فُتحت قبل النهاية (نتيجة الصفقة لا قرارها).
  · شموع الدقيقة مصفوفاتٌ مضغوطة (الذاكرة) — الإدارة نفسها حرفيًّا.
"""
from __future__ import annotations

import bisect
import calendar
import os
import sqlite3
import time
from array import array
from datetime import datetime, timezone

DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
SYMBOL = "USTEC"
COST = 1.5
CAL_OFFSET_S = 3 * 3600
MGMT_TAIL_S = 45 * 86400
KEEP = {"1h": 200, "4h": 200}      # = LADDER_KEEP في 201 (كـcard_replay_shared)


def ts(s):
    return calendar.timegm(time.strptime(s, "%Y-%m-%d"))


START = ts(os.environ.get("NOISE_START", "2024-10-01"))
_END_ENV = os.environ.get("NOISE_END")
END_FIXED = ts(_END_ENV) if _END_ENV else None

db = sqlite3.connect(DB, uri=True)


def bars(period, since, until=None, vol=False):
    cols = "period_start, open, high, low, close" + (", tick_volume" if vol else "")
    q = "select %s from candles_history where symbol=? and period=? and period_start>=?" % cols
    args = [SYMBOL, period, int(since)]
    if until is not None:
        q += " and period_start<?"
        args.append(int(until))
    q += " order by period_start"
    return [tuple(map(float, r)) for r in db.execute(q, args)]


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
    return bisect.bisect_right(times, t - seconds) - 1


print("تحميل الفترة %s → %s …" % (datetime.fromtimestamp(START, timezone.utc).date(),
                                  _END_ENV or "آخر البيانات"), flush=True)
_until_dec = END_FIXED
_until_m1 = END_FIXED + MGMT_TAIL_S if END_FIXED else None

# الدقيقة: مصفوفات
T1, O1, H1, L1, C1 = array("d"), array("d"), array("d"), array("d"), array("d")
_q = "select period_start, open, high, low, close from candles_history where symbol=? and period='M1' and period_start>=?"
_a = [SYMBOL, int(START - 86400)]
if _until_m1 is not None:
    _q += " and period_start<?"
    _a.append(int(_until_m1))
for _r in db.execute(_q + " order by period_start", _a):
    T1.append(float(_r[0])); O1.append(float(_r[1])); H1.append(float(_r[2])); L1.append(float(_r[3])); C1.append(float(_r[4]))
t1 = T1

_m5v = bars("M5", START - 60 * 86400, _until_dec, vol=True)
m5 = [r[:5] for r in _m5v]
v5 = [r[5] for r in _m5v]
del _m5v
h1 = bars("H1", START - 120 * 86400, _until_dec)
h4 = bars("H4", START - 300 * 86400, _until_dec)
d1 = bars("D1", START - 400 * 86400, _until_dec)
END = END_FIXED if END_FIXED else T1[-1]
t5, th1, th4, td1 = ([r[0] for r in x] for x in (m5, h1, h4, d1))
e_h1, e_h4 = ema([r[4] for r in h1]), ema([r[4] for r in h4])
a5, ad1 = atr(m5), atr(d1)
sw1, sw4 = swings(h1, 3600), swings(h4, 14400)
sw_htf = sorted(sw1 + sw4)
print("شموع: دقيقة=%d 5د=%d ساعة=%d 4س=%d يوم=%d · قمم/قيعان ساعة+4س=%d" % (
    len(T1), len(m5), len(h1), len(h4), len(d1), len(sw_htf)), flush=True)

cal = sqlite3.connect(CAL, uri=True)
news = sorted(t - CAL_OFFSET_S for (t,) in cal.execute(
    "select time_server from calendar_history where country_code='US' and importance=3"))
print("أخبار أمريكيّة عالية الأهمّيّة: %d" % len(news), flush=True)


def news_block(t):
    i = bisect.bisect_left(news, t - 900)
    return i < len(news) and news[i] <= t + 900


def fact_trend(rows, ema_vals, times, seconds, t):
    i = closed_index(times, seconds, t)
    return None if i < 20 else {"close": rows[i][4], "ema_slow_value": ema_vals[i]}


def _split(rows):
    hi = [(ts_, p) for ts_, p, h in rows if h]
    lo = [(ts_, p) for ts_, p, h in rows if not h]
    return (hi, [x[0] for x in hi]), (lo, [x[0] for x in lo])


frames = {"1h": _split(sw1), "4h": _split(sw4)}


def ladder_keys(t):
    """مفتاح حالة السلّم عند t: عدد القمم/القيعان المؤكَّدة حتّى t في كلّ إطار."""
    out = []
    for name in ("1h", "4h"):
        (hi, hit), (lo, lot) = frames[name]
        out.append((bisect.bisect_right(hit, t), bisect.bisect_right(lot, t)))
    return tuple(out)


def ladder_prices(keys, buy):
    """أسعار آخر KEEP قمّة (للشراء) أو قاع (للبيع) مؤكَّدة على الساعة والأربع ساعات — بمفتاح الحالة."""
    out = []
    for (kh, kl), name in zip(keys, ("1h", "4h")):
        (hi, hit), (lo, lot) = frames[name]
        if buy:
            out.extend(p for _, p in hi[max(0, kh - KEEP[name]):kh])
        else:
            out.extend(p for _, p in lo[max(0, kl - KEEP[name]):kl])
    return out


def ladder_detail(t, buy):
    """للتدقيق: (سعر، وقت التأكيد، إطار) لكلّ مستوى حتّى t."""
    out = []
    for name in ("1h", "4h"):
        (hi, hit), (lo, lot) = frames[name]
        rows, tt = (hi, hit) if buy else (lo, lot)
        k = bisect.bisect_right(tt, t)
        out.extend((p, ts_, name) for ts_, p in rows[max(0, k - KEEP[name]):k])
    return out


def thirds(entry, stop, target, buy, k):
    """منسوخةٌ حرفيًّا من card_replay.thirds (الدقيقة مصفوفات)."""
    risk, span, sgn = abs(entry - stop), abs(target - entry), (1 if buy else -1)
    t1_, t2_ = entry + sgn * span / 3, entry + sgn * 2 * span / 3
    cur, rem, real, stage = stop, 1.0, 0.0, 0
    n = len(T1)
    while k < n:
        t, o, h, lo = T1[k], O1[k], H1[k], L1[k]
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


def stats(tr, label=""):
    """منسوخةٌ حرفيًّا من card_replay.stats (أنصاف السنة التقويميّة)."""
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
