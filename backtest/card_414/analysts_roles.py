# -*- coding: utf-8 -*-
"""المحلّلون في أدوارهم (ورقة النقاش ٤-ح) — كلّ محلّلٍ شرطٌ واحد فوق البطاقة 414 الحيّة، تغييرٌ واحد في كلّ مرّة.

القاعدة: البطاقة كما هي حيّة (القلب المشترك `shared/card_trend.evaluate` مع الإس آند بي والداو) = المرجع
241 صفقة · +25.4R · تعلّم 0.081 · اختبار 0.171 · سحب 13.7.

حقيقة كلّ محلّل تُعاد حسابها **بكوده نفسه** (atoms/قسم 150-199/<الرقم>/atom.py) وبعيار بيانه (manifest)
على مفتاح السرعة 50 (المعامل ×1)، على شموعٍ **مغلقة** فقط قبل لحظة الزناد (لا نظر في المستقبل)،
وعلى نوافذ واسعة: ربع ساعة وساعة (والسياق ساعة وأربع ساعات ويوم).

المعنى مثبَّتٌ قبل القياس من الدور؛ ولكلّ محلّلٍ عياران فقط (نافذتان غالبًا)؛ ويُختار العيار على أوّل ٧٠٪ وحدها.
معيار القبول (المالك): اختبار > 0.171 · تعلّم ≥ 0.081 · الأنصاف الخمسة موجبة · سحب ≤ 13.7 · العدد > نصف المرجع.

السبريد 155: كوده لا يقرأ سبريدًا (عرض/طلب) بل «اتّساع المدى» من أعلى وأدنى الشموع (METHOD = range_expansion)
فيُحسب من الشموع كما هو. الحجم 154 وجودة الحجم 164: القاعدة التاريخيّة تحمل `tick_volume` (عدّ تِكّات سي‑تريدر)؛
يُقاسان ملحقًا بعلامةٍ صريحة — مصدر الحيّ غير مطابَق بعد (154 يقرأ tick_count من التغذية، و164 لا يقرأ إلّا volume=0).
"""
import bisect
import json
import random
import sys
import time
from collections import deque
from datetime import datetime, timezone

sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
import card_replay as R
import card_replay_shared as S
import card_variants as V
import card_final_check as F
from shared import card_trend as CT
from shared.owner_windows import owner_window

T0 = time.time()


def log(*a):
    print("[%5.0fث]" % (time.time() - T0), *a, flush=True)


# ───────────────────────── الشموع (مع عدّ التِّكّات) ─────────────────────────
def bars_v(sym, period, since):
    return [tuple(map(float, r)) for r in R.db.execute(
        "select period_start, open, high, low, close, tick_volume from candles_history "
        "where symbol=? and period=? and period_start>=? order by period_start", (sym, period, int(since)))]


SEC = {"M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}
SINCE = {"M15": 90, "H1": 120, "H4": 300, "D1": 400}
NQ = {p: bars_v("USTEC", p, R.START - d * 86400) for p, d in SINCE.items()}
PEER = {s: {p: bars_v(s, p, R.START - SINCE[p] * 86400) for p in ("H1", "H4")} for s in ("US500", "US30")}
TIMES = {p: [r[0] for r in rows] for p, rows in NQ.items()}
PTIMES = {s: {p: [r[0] for r in rows] for p, rows in d.items()} for s, d in PEER.items()}
log("شموع الناسداك:", {p: len(v) for p, v in NQ.items()}, "· الإس آند بي/الداو ساعة/4س:",
    {s: {p: len(v) for p, v in d.items()} for s, d in PEER.items()})


def mean(v):
    return sum(v) / len(v) if v else 0.0


# ───────────────────────── المحلّلون بكودهم (عيار البيان) ─────────────────────────
def a151(rows, fast=10, slow=20, k=3, min_c=20, flat_slope=0.015, flat_dist=0.04):
    """151 الاتّجاه: متوسّط 10 مقابل 20؛ الإشارة جهةٌ إن أكّدها الميل أو موضع السعر، ولا تشابك مع ميلٍ مسطّح."""
    af, as_ = 2.0 / (fast + 1), 2.0 / (slow + 1)
    out, ef, es, hist, count = [], None, None, deque(maxlen=k * 5 + 1), 0
    for t, o, h, l, c, v in rows:
        if ef is None:
            ef = es = c
            hist.append(c)
        else:
            ef = af * c + (1 - af) * ef
            es = as_ * c + (1 - as_) * es
            hist.append(es)
        count += 1
        if count < min_c or es == 0:
            out.append(None)
            continue
        dist = (ef - es) / es * 100
        if len(hist) <= k:
            slope = 0.0
        else:
            b = hist[-(k + 1)]
            slope = (es - b) / b * 100 / k if b else 0.0
        dr = 1 if ef > es else -1 if ef < es else 0
        pos = 1 if c > ef else -1 if c < ef else 0
        sc = (dr == 1 and slope > flat_slope) or (dr == -1 and slope < -flat_slope)
        pc = dr != 0 and pos == dr
        if dr == 0 or (abs(dist) < flat_dist and abs(slope) < flat_slope) or not (sc or pc):
            out.append(0)
        else:
            out.append(dr)
    return out


def a161_ret(rows, w=20):
    """161 القوّة النسبيّة: عائد النافذة (الإغلاق مقابل إغلاقٍ قبل w شمعة)."""
    return [None if i < w or not rows[i - w][4] else (rows[i][4] - rows[i - w][4]) / rows[i - w][4]
            for i in range(len(rows))]


def a153(rows, atr_w=16, base_w=32, min_c=16):
    """153 التذبذب: متوسّط المدى الحقيقيّ 16 ÷ متوسّطه على 32 (منخفض ≤0.7 · مرتفع ≥1.35)."""
    out, trs, prev = [], [], None
    for t, o, h, l, c, v in rows:
        tr = h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))
        prev = c
        trs.append(tr)
        win = trs[-base_w:]
        if len(win) < min_c:
            out.append(None)
            continue
        base = mean(win)
        out.append(mean(win[-atr_w:]) / base if base > 0 else 1.0)
    return out


def a155(rows, base_w=24, short=5, long_=20, min_c=16, exp=1.25):
    """155 «السبريد» = اتّساع المدى: متوسّط مدى 5 ÷ متوسّط مدى 20 (اتّساع >1.25 · انكماش <1/1.25 · وإلّا مستقرّ)."""
    out, rng = [], []
    for t, o, h, l, c, v in rows:
        rng.append(max(0.0, h - l))
        vals = rng[-base_w:]
        if len(vals) < min_c:
            out.append(None)
            continue
        la = mean(vals[-long_:])
        ratio = mean(vals[-short:]) / la if la > 0 else 1.0
        out.append("expansion" if ratio > exp else "contraction" if ratio < 1.0 / exp else "stable")
    return out


def a165(rows, w=16):
    """165 الضوضاء: نسبة الكفاءة = |صافي الحركة| ÷ طول المسار على 16 شمعة (ضوضاء <0.35 · كفاءة >0.55)."""
    out, cl = [], deque(maxlen=w + 1)
    for t, o, h, l, c, v in rows:
        cl.append(c)
        if len(cl) <= w:
            out.append(None)
            continue
        path = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl)))
        out.append(abs(cl[-1] - cl[0]) / path if path > 0 else None)
    return out


def a157(rows, thr=0.1):
    """157 الفجوات: فتحٌ يبعد ≥ thr٪ عن الإغلاق السابق = فجوةٌ مفتوحة حتّى يلمس السعر مستواها. True = لا فجوة مفتوحة."""
    out, prev, gap = [], None, None
    for t, o, h, l, c, v in rows:
        if prev is None or prev <= 0:
            out.append(None)
            prev = c
            continue
        gp = (o - prev) / prev * 100
        if gap is not None and l <= gap <= h:
            gap = None
        if gp >= thr or gp <= -thr:
            gap = prev
        out.append(gap is None)
        prev = c
    return out


def a152(rows, roc_p=5, imp=8, pers=12, min_c=16, flat=0.04, pmin=0.55):
    """152 الزخم: تغيّر 5 شموع٪ مع ثبات الاتّجاه على 12 (جانبيّ إن |التغيّر| ≤0.04٪ أو الثبات <0.55)."""
    need = max(roc_p, imp, pers, min_c) + 1
    out, cl = [], []
    for t, o, h, l, c, v in rows:
        cl.append(c)
        if len(cl) < need:
            out.append(None)
            continue
        past = cl[-(roc_p + 1)]
        roc = (cl[-1] - past) / past * 100 if past else 0.0
        ups = downs = 0
        for i in range(-pers, 0):
            dd = cl[i] - cl[i - 1]
            ups += dd > 0
            downs += dd < 0
        p = max(ups, downs) / (ups + downs) if ups + downs else 0.5
        out.append(0 if abs(roc) <= flat or p < pmin else (1 if roc > 0 else -1))
    return out


def a162_163(rows, base_w=24):
    """162 السرعة: |تغيّر الشمعة|٪ ÷ متوسّطه على 24 سابقة · 163 التسارع: (السرعة − السابقة) ÷ المتوسّط نفسه.
    يُرجع (الحركة الموقَّعة، نسبة السرعة، نسبة التسارع)."""
    out, prev, prev_sp, sp_hist = [], None, None, []
    for t, o, h, l, c, v in rows:
        if prev is None:
            prev = c
            out.append(None)
            continue
        sp = abs(c - prev) / prev * 100 if prev else 0.0
        move = c - prev
        prev = c
        base = mean(sp_hist[-base_w:])
        sp_hist.append(sp)
        ok = len(sp_hist) >= base_w and base > 0
        vel = sp / base if ok else None
        acc = (sp - prev_sp) / base if ok and prev_sp is not None else None
        prev_sp = sp
        out.append((move, vel, acc))
    return out


def a156(rows, doji=0.1, maru=0.85, pin_wick=0.6, pin_body=0.3):
    """156 الشموع: ابتلاع · خارجيّة · داخليّة · مربوزو · دبّوس · دوجي — ويُرجع الجهة (+1 صاعد · −1 هابط · 0 بلا)."""
    out, pv = [], None
    for t, o, h, l, c, v in rows:
        cur = (o, h, l, c)
        if pv is None:
            out.append(None)
            pv = cur
            continue
        rng = h - l
        res = ("none", 0)
        if rng > 0:
            body = abs(c - o)
            br = body / rng
            up, lo_ = h - max(o, c), min(o, c) - l
            bull = c > o
            dr = 1 if bull else -1
            po, ph, pl, pc = pv
            ct, cb, pt, pb = max(o, c), min(o, c), max(po, pc), min(po, pc)
            if ct >= pt and cb <= pb and bull != (pc > po) and body > 0:
                res = ("engulfing", dr)
            elif h > ph and l < pl:
                res = ("outside", dr)
            elif h < ph and l > pl:
                res = ("inside", 0)
            elif br >= maru:
                res = ("marubozu", dr)
            elif br <= pin_body and max(up, lo_) >= pin_wick * rng:
                res = ("pin_bar", 1 if lo_ > up else -1)
            elif br <= doji:
                res = ("doji", 0)
        out.append(res)
        pv = cur
    return out


def a154(rows, base_w=50, min_c=20, high=1.5):
    """154 الحجم (عدّ التِّكّات): النسبة إلى متوسّط 50 شاملًا الحاليّة؛ ≥1.5 مع صعود = تجميع (+1)، مع هبوط = تصريف (−1)."""
    out, vols, prev = [], [], None
    for t, o, h, l, c, v in rows:
        vols.append(v)
        win = vols[-base_w:]
        pc, prev = prev, c
        if len(win) < min_c:
            out.append(None)
            continue
        avg = mean(win)
        ratio = v / avg if avg > 0 else 1.0
        out.append(1 if ratio >= high and pc is not None and c > pc else
                   -1 if ratio >= high and pc is not None and c < pc else 0)
    return out


def a164(rows, base_w=16):
    """164 جودة الحجم (عدّ التِّكّات): الحاليّة ÷ متوسّط 16 سابقة؛ منخفضة إن <0.4."""
    out, vols = [], []
    for t, o, h, l, c, v in rows:
        if v <= 0:
            out.append(None)
            continue
        base = mean(vols[-base_w:])
        vols.append(v)
        out.append(v / base if len(vols) >= base_w and base > 0 else None)
    return out


# حساب السلاسل مرّةً واحدة
F151 = {p: a151(NQ[p]) for p in ("H1", "H4", "D1")}
RET = {"USTEC": {p: a161_ret(NQ[p]) for p in ("H1", "H4")}}
RET.update({s: {p: a161_ret(PEER[s][p]) for p in ("H1", "H4")} for s in PEER})
F153 = {p: a153(NQ[p]) for p in ("M15", "H1")}
F155 = {p: a155(NQ[p]) for p in ("M15", "H1")}
F165 = {p: a165(NQ[p]) for p in ("M15", "H1")}
F157 = {"H1_0.1": a157(NQ["H1"], 0.1), "H1_0.25": a157(NQ["H1"], 0.25)}
F152 = {p: a152(NQ[p]) for p in ("M15", "H1")}
F162 = {p: a162_163(NQ[p]) for p in ("M15", "H1")}
F156 = {p: a156(NQ[p]) for p in ("M15", "H1")}
F154 = {p: a154(NQ[p]) for p in ("M15", "H1")}
F164 = {p: a164(NQ[p]) for p in ("M15", "H1")}
log("حُسبت حقائق المحلّلين")


def at(series, period, t):
    """قيمة المحلّل عند آخر شمعةٍ أُغلقت قبل t (أو عندها تمامًا)."""
    i = R.closed_index(TIMES[period], SEC[period], t)
    return series[i] if i >= 0 else None


def rs_rank(period, t):
    """ترتيب عائد الناسداك بين الثلاثة: 2 = الأقوى · 0 = الأضعف · None = حقيقة ناقصة."""
    i = R.closed_index(TIMES[period], SEC[period], t)
    me = RET["USTEC"][period][i] if i >= 0 else None
    rets = [me]
    for s in PEER:
        k = R.closed_index(PTIMES[s][period], SEC[period], t)
        rets.append(RET[s][period][k] if k >= 0 else None)
    if any(r is None for r in rets):
        return None
    return sum(1 for r in rets if r < me)


def hour_utc(t):        # 158: ساعة بداية شمعة الزناد (5 د) بغرينتش
    return int((t - 300) // 3600) % 24


def weekday_utc(t):     # 159: يوم بداية شمعة الزناد بغرينتش
    return datetime.fromtimestamp(t - 300, timezone.utc).weekday()


def in_w(h, a, b):
    return a <= h < b if a <= b else (h >= a or h < b)


def sessions(t):
    h = hour_utc(t)
    return [n for n, (a, b) in (("asia", (0, 9)), ("london", (7, 16)), ("new_york", (12, 21))) if in_w(h, a, b)]


def moved_with(x, d, key):
    """162/163: الشمعة الأخيرة تحرّكت في الجهة، والنسبة المطلوبة متحقّقة."""
    if x is None:
        return False
    move, vel, acc = x
    if move * d <= 0:
        return False
    return (vel is not None and vel >= 0.7) if key == "vel" else (acc is not None and acc > 0)


# ───────────────────────── الاختبارات (المعنى مثبَّت قبل القياس) ─────────────────────────
# (الرقم، الاسم، الدور، العيار، الوصف، الشرط(t, d) ⟵ True = يُسمح بالدخول)
TESTS = [
    # السياق — مع الإطار الكبير
    ("151", "الاتّجاه", "السياق", "ساعة+4س",
     "إشارة الاتّجاه الكاملة (متوسّط 10 مقابل 20 مؤكَّدةً بالميل أو بموضع السعر) في جهة الصفقة على الساعة والأربع ساعات معًا",
     lambda t, d: at(F151["H1"], "H1", t) == d and at(F151["H4"], "H4", t) == d),
    ("151", "الاتّجاه", "السياق", "يوم",
     "إشارة الاتّجاه الكاملة في جهة الصفقة على اليوم (آخر يومٍ مغلق)",
     lambda t, d: at(F151["D1"], "D1", t) == d),
    ("161", "القوّة النسبيّة", "السياق", "ساعة×20",
     "عائد الناسداك على آخر 20 ساعة الأقوى بين الثلاثة للشراء / الأضعف للبيع (أمام الإس آند بي والداو)",
     lambda t, d: rs_rank("H1", t) == (2 if d > 0 else 0)),
    ("161", "القوّة النسبيّة", "السياق", "4س×20",
     "عائد الناسداك على آخر 20 شمعة أربع ساعات الأقوى بين الثلاثة للشراء / الأضعف للبيع",
     lambda t, d: rs_rank("H4", t) == (2 if d > 0 else 0)),
    # هل السوق صالحٌ الآن
    ("153", "التذبذب", "صلاحيّة السوق", "ربع ساعة",
     "التذبذب «طبيعيّ»: متوسّط المدى 16 ÷ متوسّطه على 32 بين 0.7 و1.35 (لا ميّت ولا منفجر) — ربع ساعة",
     lambda t, d: (lambda r: r is not None and 0.7 < r < 1.35)(at(F153["M15"], "M15", t))),
    ("153", "التذبذب", "صلاحيّة السوق", "ساعة",
     "التذبذب «طبيعيّ» بين 0.7 و1.35 — ساعة",
     lambda t, d: (lambda r: r is not None and 0.7 < r < 1.35)(at(F153["H1"], "H1", t))),
    ("155", "السبريد (اتّساع المدى)", "صلاحيّة السوق", "ربع ساعة",
     "المدى «مستقرّ»: متوسّط مدى 5 شموع ÷ متوسّط 20 بين 0.8 و1.25 (لا اتّساع ولا انكماش) — ربع ساعة",
     lambda t, d: at(F155["M15"], "M15", t) == "stable"),
    ("155", "السبريد (اتّساع المدى)", "صلاحيّة السوق", "ساعة",
     "المدى «مستقرّ» — ساعة",
     lambda t, d: at(F155["H1"], "H1", t) == "stable"),
    ("165", "الضوضاء", "صلاحيّة السوق", "ربع ساعة",
     "لا ضوضاء: نسبة الكفاءة على 16 شمعة ≥ 0.35 — ربع ساعة",
     lambda t, d: (lambda e: e is not None and e >= 0.35)(at(F165["M15"], "M15", t))),
    ("165", "الضوضاء", "صلاحيّة السوق", "ساعة",
     "لا ضوضاء: نسبة الكفاءة على 16 شمعة ≥ 0.35 — ساعة",
     lambda t, d: (lambda e: e is not None and e >= 0.35)(at(F165["H1"], "H1", t))),
    ("158", "الجلسات", "صلاحيّة السوق", "أيّ تداخل",
     "تداخل جلستين (إشارة الذرّة overlap: آسيا 0–9 · لندن 7–16 · نيويورك 12–21 غرينتش)",
     lambda t, d: len(sessions(t)) >= 2),
    ("158", "الجلسات", "صلاحيّة السوق", "لندن+نيويورك",
     "تداخل لندن ونيويورك معًا (12–16 غرينتش)",
     lambda t, d: {"london", "new_york"} <= set(sessions(t))),
    ("159", "أثر الوقت", "صلاحيّة السوق", "وسط الأسبوع",
     "وسط الأسبوع فقط (الثلاثاء–الخميس؛ لا افتتاح الأسبوع ولا إغلاقه)",
     lambda t, d: weekday_utc(t) in (1, 2, 3)),
    ("159", "أثر الوقت", "صلاحيّة السوق", "بلا جمعة",
     "ليس يوم إغلاق الأسبوع (لا جمعة)",
     lambda t, d: weekday_utc(t) != 4),
    ("157", "الفجوات", "صلاحيّة السوق", "ساعة 0.1٪",
     "لا فجوة مفتوحة: كلّ فجوةٍ ≥ 0.1٪ (عيار الذرّة) أُغلقت — ساعة",
     lambda t, d: at(F157["H1_0.1"], "H1", t) is True),
    ("157", "الفجوات", "صلاحيّة السوق", "ساعة 0.25٪",
     "لا فجوة كبيرة مفتوحة: كلّ فجوةٍ ≥ 0.25٪ أُغلقت — ساعة",
     lambda t, d: at(F157["H1_0.25"], "H1", t) is True),
    # الارتداد والتوقيت
    ("152", "الزخم", "التوقيت", "ربع ساعة",
     "الزخم عاد في الجهة: إشارة الزخم (تغيّر 5 شموع مع ثبات 12) في جهة الصفقة — ربع ساعة",
     lambda t, d: at(F152["M15"], "M15", t) == d),
    ("152", "الزخم", "التوقيت", "ساعة",
     "إشارة الزخم في جهة الصفقة — ساعة",
     lambda t, d: at(F152["H1"], "H1", t) == d),
    ("162", "السرعة", "التوقيت", "ربع ساعة",
     "السرعة موجبة في الجهة: آخر شمعةٍ تحرّكت في الجهة وسرعتها ليست «بطيئة» (≥ 0.7 من متوسّط 24) — ربع ساعة",
     lambda t, d: moved_with(at(F162["M15"], "M15", t), d, "vel")),
    ("162", "السرعة", "التوقيت", "ساعة",
     "السرعة موجبة في الجهة — ساعة",
     lambda t, d: moved_with(at(F162["H1"], "H1", t), d, "vel")),
    ("163", "التسارع", "التوقيت", "ربع ساعة",
     "التسارع موجب في الجهة: آخر شمعةٍ في الجهة وسرعتها أكبر من التي قبلها — ربع ساعة",
     lambda t, d: moved_with(at(F162["M15"], "M15", t), d, "acc")),
    ("163", "التسارع", "التوقيت", "ساعة",
     "التسارع موجب في الجهة — ساعة",
     lambda t, d: moved_with(at(F162["H1"], "H1", t), d, "acc")),
    ("156", "الشموع", "التوقيت", "ربع ساعة",
     "لا نموذج شموعٍ عكس الجهة على آخر شمعةٍ مغلقة (ابتلاع/خارجيّة/مربوزو/دبّوس معاكس) — ربع ساعة",
     lambda t, d: (lambda x: x is not None and x[1] != -d)(at(F156["M15"], "M15", t))),
    ("156", "الشموع", "التوقيت", "ساعة",
     "لا نموذج شموعٍ عكس الجهة — ساعة",
     lambda t, d: (lambda x: x is not None and x[1] != -d)(at(F156["H1"], "H1", t))),
    # ملحق: الصامتان بعدّ التِّكّات التاريخيّ (مصدر الحيّ غير مطابَق)
    ("154", "الحجم (عدّ التِّكّات)", "ملحق", "ربع ساعة",
     "الحجم لا يعاكس: ليس «تصريفًا» للشراء ولا «تجميعًا» للبيع (نسبة ≥1.5 مع حركةٍ معاكسة) — ربع ساعة",
     lambda t, d: (lambda x: x is not None and x != -d)(at(F154["M15"], "M15", t))),
    ("154", "الحجم (عدّ التِّكّات)", "ملحق", "ساعة",
     "الحجم لا يعاكس — ساعة",
     lambda t, d: (lambda x: x is not None and x != -d)(at(F154["H1"], "H1", t))),
    ("164", "جودة الحجم (عدّ التِّكّات)", "ملحق", "ربع ساعة",
     "النشاط ليس ضعيفًا: عدّ تِكّات آخر شمعة ≥ 0.4 من متوسّط 16 — ربع ساعة",
     lambda t, d: (lambda r: r is not None and r >= 0.4)(at(F164["M15"], "M15", t))),
    ("164", "جودة الحجم (عدّ التِّكّات)", "ملحق", "ساعة",
     "النشاط ليس ضعيفًا — ساعة",
     lambda t, d: (lambda r: r is not None and r >= 0.4)(at(F164["H1"], "H1", t))),
]


# ───────────────────────── أحداث البطاقة (مرّةً واحدة) ثمّ الإعادة ─────────────────────────
def collect():
    """كلّ لحظةٍ تقول فيها البطاقة الحيّة OPEN. التقييم دالّةٌ صِرفة، فجمعها ثمّ تطبيق «مركزٌ واحد» يطابق الحلقة الأصليّة."""
    ev = []
    for j in range(1, len(R.m5)):
        t_close = R.m5[j][0] + 300
        if t_close < R.START:
            continue
        win = owner_window(t_close)
        if not win:            # = OUTSIDE_OWNER_WINDOW في evaluate
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        peers = {sym: (F.peer_fact(h1, 3600, t_close), F.peer_fact(h4, 14400, t_close)) for sym, (h1, h4) in V.REF.items()}
        card = CT.evaluate(at=t_close, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                           trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close),
                           atr_5m=R.a5[j], atr_1d=R.ad1[idd] if idd >= 0 else None,
                           ladder=S.ladder_at(t_close, S.frames), window=win,
                           news_blocked=R.news_block(t_close), peers=peers)
        if card["status"] == CT.OPEN:
            ev.append((t_close, card))
    return ev


EVENTS = collect()
log("لحظات OPEN للبطاقة:", len(EVENTS))
SIM = {}


def sim(k):
    if k not in SIM:
        t_close, card = EVENTS[k]
        buy = card["side"] == CT.BUY
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        SIM[k] = R.thirds(card["entry"], card["stop"], card["target"], buy, k1)
    return SIM[k]


def replay(cond=None):
    trades, busy = [], 0.0
    for k, (t_close, card) in enumerate(EVENTS):
        if t_close < busy:
            continue
        d = 1 if card["side"] == CT.BUY else -1
        if cond is not None and not cond(t_close, d):
            continue
        r, exit_t = sim(k)
        if r is None:
            break
        trades.append((t_close, r, card["window"], d > 0, card["risk"] / card["entry"] * 1e4))
        busy = exit_t + 60
    return trades


SPLIT = R.START + 0.7 * (R.END - R.START)


def raw(tr):
    if not tr:
        return {"n": 0, "rpt": None, "dd": None, "halves": {}}
    rs = [x[1] for x in tr]
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    halves = {}
    for t, r, *_ in tr:
        dt = datetime.fromtimestamp(t, timezone.utc)
        key = "%d%s" % (dt.year, "أ" if dt.month <= 6 else "ب")
        halves[key] = halves.get(key, 0.0) + r
    return {"n": len(rs), "rpt": sum(rs) / len(rs), "dd": dd, "halves": halves}


def summary(tr):
    learn = [x for x in tr if x[0] < SPLIT]
    test = [x for x in tr if x[0] >= SPLIT]
    return {"كلّه": R.stats(tr), "تعلّم": R.stats(learn), "اختبار": R.stats(test),
            "_raw": {"all": raw(tr), "learn": raw(learn), "test": raw(test)}}


def verdict(s, base):
    a, l, te = s["_raw"]["all"], s["_raw"]["learn"], s["_raw"]["test"]
    b = base["_raw"]
    checks = {
        "اختبار>المرجع": te["rpt"] is not None and te["rpt"] > b["test"]["rpt"],
        "تعلّم_لا_يسوء": l["rpt"] is not None and l["rpt"] >= b["learn"]["rpt"],
        "الأنصاف_الخمسة_موجبة": len(a["halves"]) == 5 and all(v > 0 for v in a["halves"].values()),
        "سحب_لا_يسوء": a["dd"] is not None and a["dd"] <= b["all"]["dd"] + 1e-9,
        "العدد>نصف_المرجع": a["n"] > b["all"]["n"] / 2,
    }
    return all(checks.values()), checks


def random_control(pass_rate, base, seeds=300):
    """ضابط الحظّ: مرشِّحاتٌ عشوائيّة بنسبة السماح نفسها — كم منها يجتاز المعيار كلّه؟"""
    hits = 0
    for sd in range(seeds):
        rnd = random.Random(1000 + sd)
        keep = {t for t, _ in EVENTS if rnd.random() < pass_rate}
        s = summary(replay(lambda t, d: t in keep))
        hits += verdict(s, base)[0]
    return hits / seeds


if __name__ == "__main__":
    base = summary(replay())
    log("المرجع:", json.dumps({k: base[k] for k in ("كلّه", "تعلّم", "اختبار")}, ensure_ascii=False))
    assert base["كلّه"]["n"] == 241 and base["كلّه"]["R"] == 25.4, "الإعادة لا تطابق المرجع الحيّ"
    out = {"المرجع": {k: base[k] for k in ("كلّه", "تعلّم", "اختبار")}, "عدد_الاختبارات": len(TESTS),
           "اختبارات": [], "أحكام": []}
    results = []
    for num, name, role, cal, desc, cond in TESTS:
        passed = sum(1 for t, c in EVENTS if cond(t, 1 if c["side"] == CT.BUY else -1))
        s = summary(replay(cond))
        ok, checks = verdict(s, base)
        row = {"الرقم": num, "المحلّل": name, "الدور": role, "العيار": cal, "الشرط": desc,
               "نسبة_السماح_من_لحظات_البطاقة": round(passed / len(EVENTS), 3),
               "كلّه": s["كلّه"], "تعلّم": s["تعلّم"], "اختبار": s["اختبار"], "فحوص_المعيار": checks, "يجتاز": ok}
        results.append((num, cal, s, ok, row, cond, passed / len(EVENTS)))
        out["اختبارات"].append(row)
        log("%s %-22s %-12s | سماح=%.2f | n=%d R=%s R/ص=%s سحب=%s أنصاف=%s | تعلّم %s | اختبار %s معامل=%s | %s" % (
            num, name, cal, passed / len(EVENTS), s["كلّه"]["n"], s["كلّه"].get("R"), s["كلّه"].get("R/صفقة"),
            s["كلّه"].get("سحب_R"), s["كلّه"].get("أنصاف"), s["تعلّم"].get("R/صفقة"), s["اختبار"].get("R/صفقة"),
            s["اختبار"].get("معامل"), "يجتاز" if ok else "—"))
    # العيار يُختار على التعلّم وحده (أعلى R/صفقة في أوّل ٧٠٪)، ثمّ يُحكم عليه بالمعيار
    accepted = []
    for num in dict.fromkeys(r[0] for r in results):
        cands = [r for r in results if r[0] == num]
        best = max(cands, key=lambda r: -9.0 if r[2]["_raw"]["learn"]["rpt"] is None else r[2]["_raw"]["learn"]["rpt"])
        ok = best[3]
        role = best[4]["الدور"]
        out["أحكام"].append({"الرقم": num, "المحلّل": best[4]["المحلّل"], "الدور": role,
                             "العيار_المختار_على_التعلّم": best[1], "يُقبل": ok, "فحوص": best[4]["فحوص_المعيار"]})
        log("حكم %s %s: العيار المختار على التعلّم = %s ⟸ %s" % (num, best[4]["المحلّل"], best[1], "يُقبل" if ok else "يُرفض"))
        if ok and role != "ملحق":
            accepted.append(best)
    out["المقبولون"] = [(a[0], a[1]) for a in accepted]
    for a in accepted:
        rc = random_control(a[6], base)
        out.setdefault("ضابط_الحظّ", {})["%s/%s" % (a[0], a[1])] = {"نسبة_السماح": round(a[6], 3),
                                                                  "نسبة_المرشِّحات_العشوائيّة_المجتازة": rc}
        log("ضابط الحظّ %s/%s: سماح %.2f ⟸ %.1f٪ من 300 مرشِّحٍ عشوائيّ يجتاز المعيار" % (a[0], a[1], a[6], 100 * rc))
    if len(accepted) >= 2:
        conds = [a[5] for a in accepted]
        s = summary(replay(lambda t, d: all(c(t, d) for c in conds)))
        ok, checks = verdict(s, base)
        out["اجتماع_المقبولين"] = {"كلّه": s["كلّه"], "تعلّم": s["تعلّم"], "اختبار": s["اختبار"], "فحوص": checks, "يجتاز": ok}
        log("اجتماع المقبولين:", json.dumps(out["اجتماع_المقبولين"], ensure_ascii=False))
    json.dump(out, open("analysts_roles.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("تمّ — analysts_roles.json")
