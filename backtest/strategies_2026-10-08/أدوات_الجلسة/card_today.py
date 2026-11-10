# -*- coding: utf-8 -*-
"""ما رأته البطاقة 414 اليوم شمعةً شمعة — القلب المشترك نفسه على شموع سي‑تريدر (قراءة فقط)."""
import bisect
import calendar
import sqlite3
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
from shared import card_trend as CT
from shared.owner_windows import owner_window

DB = "file:C:/Users/NQ/QUANT_NQ/forex_runtime/var/history/ctrader_history.db?mode=ro"
CAL = "file:C:/Users/NQ/AppData/Roaming/MetaQuotes/Terminal/Common/Files/nq_calendar_history.db?mode=ro"
DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-10-08"
D0 = calendar.timegm(time.strptime(DAY, "%Y-%m-%d"))
db = sqlite3.connect(DB, uri=True)


def bars(sym, period, since):
    return [tuple(map(float, r)) for r in db.execute(
        "select period_start, open, high, low, close from candles_history where symbol=? and period=? "
        "and period_start>=? order by period_start", (sym, period, int(since)))]


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


def pack(sym, period, seconds, days):
    rows = bars(sym, period, D0 - days * 86400)
    return rows, ema([r[4] for r in rows]), [r[0] for r in rows], seconds


def fact(p, t):
    rows, e, times, seconds = p
    i = closed_index(times, seconds, t)
    return None if i < 20 else {"close": rows[i][4], "ema_slow_value": e[i]}


m5 = bars("USTEC", "M5", D0 - 20 * 86400)
t5 = [r[0] for r in m5]
a5 = atr(m5)
H1, H4 = pack("USTEC", "H1", 3600, 60), pack("USTEC", "H4", 14400, 200)
d1 = bars("USTEC", "D1", D0 - 400 * 86400)
td1, ad1 = [r[0] for r in d1], atr(d1)
PEERS = {s: (pack(s, "H1", 3600, 60), pack(s, "H4", 14400, 200)) for s in ("US500", "US30")}

KEEP = {"5m": 100, "1h": 200, "4h": 200}


def split(rows):
    hi = [(ts, p) for ts, p, h in rows if h]; lo = [(ts, p) for ts, p, h in rows if not h]
    return (hi, [x[0] for x in hi]), (lo, [x[0] for x in lo])


frames = {"5m": split(swings(m5, 300)), "1h": split(swings(H1[0], 3600)), "4h": split(swings(H4[0], 14400))}


def ladder_at(t):
    out = {}
    for name, ((hi, hit), (lo, lot)) in frames.items():
        kh, kl = bisect.bisect_right(hit, t), bisect.bisect_right(lot, t)
        out[name] = {"highs": [[p, ts] for ts, p in hi[max(0, kh - KEEP[name]):kh]],
                     "lows": [[p, ts] for ts, p in lo[max(0, kl - KEEP[name]):kl]]}
    return out


cal = sqlite3.connect(CAL, uri=True)
news = sorted(t - 3 * 3600 for (t,) in cal.execute(
    "select time_server from calendar_history where country_code='US' and importance=3"))


def news_block(t):
    i = bisect.bisect_left(news, t - 900)
    return i < len(news) and news[i] <= t + 900


def side(f):
    if not f:
        return "؟"
    return "↑" if f["close"] > f["ema_slow_value"] else "↓" if f["close"] < f["ema_slow_value"] else "="


print("آخر شمعة 5د (غرينتش):", datetime.fromtimestamp(m5[-1][0], timezone.utc).strftime("%H:%M"))
tally = {}
for j in range(1, len(m5)):
    t_close = m5[j][0] + 300
    if t_close < D0 or t_close >= D0 + 86400:
        continue
    win = owner_window(t_close)
    if not win:
        continue
    idd = closed_index(td1, 86400, t_close)
    peers = {s: (fact(h1, t_close), fact(h4, t_close)) for s, (h1, h4) in PEERS.items()}
    f1, f4 = fact(H1, t_close), fact(H4, t_close)
    card = CT.evaluate(at=t_close, close=m5[j][4], prev_close=m5[j - 1][4], trend_1h=f1, trend_4h=f4,
                       atr_5m=a5[j], atr_1d=ad1[idd] if idd >= 0 else None, ladder=ladder_at(t_close),
                       window=win, news_blocked=news_block(t_close), peers=peers)
    st = card["status"]
    tally[st] = tally.get(st, 0) + 1
    local = datetime.fromtimestamp(t_close + 3 * 3600, timezone.utc).strftime("%H:%M")
    extra = ""
    if st == CT.OPEN:
        extra = " دخول=%.2f وقف=%.2f هدف=%.2f" % (card["entry"], card["stop"], card["target"])
    print("%s %s ناسداك[س%s 4س%s] إس‌آند‌بي[%s%s] داو[%s%s] %.2f ⟵ %s%s" % (
        local, win, side(f1), side(f4), side(peers["US500"][0]), side(peers["US500"][1]),
        side(peers["US30"][0]), side(peers["US30"][1]), m5[j][4], st, extra))
print("الحصيلة:", tally)
