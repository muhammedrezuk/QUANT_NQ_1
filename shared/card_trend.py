"""بطاقة «استمرار الاتّجاه بعد الارتداد» — قلب القرار، دالّةٌ صِرفة واحدة يقرؤها الحيّ (ذرّة 414)
وإعادة القياس على التاريخ معًا، فلا يختلف تعريفان (ورقة النقاش ٢٠٢٦-١٠-٠٧: ٤-س-٤ · ٤-س-٥ · ٤-ف).

قوانين المالك فيها:
  · الأقسام تعطي حقائق خامًا، والاستراتيجيّة وحدها تقرّر — لا تصويت ولا وزن ولا ثقة.
  · للاستراتيجيّة دخولها ووقفها وهدفها؛ والإدارة أثلاث المالك (574) للجميع.
  · الهدف ١:٣ فأكثر — وتحته لا دخول؛ والوقف لا يُصغَّر ليصحّ الحساب.
  · المعايرة لا الحدود: الوقف خلف ضجيجٍ مقيس، والهدف في متناول السوق المقيس.

الحقائق (ومن أيّ ذرّة):
  الجهة   : الإغلاق مقابل متوسّط 20 على الساعة والأربع ساعات  ⟵ 151 (`ema_slow_value` = متوسّط 20)
  الضجيج  : متوسّط المدى الحقيقيّ 14 على 5 د وعلى اليوم          ⟵ 153 (`atr`)
  البنية  : القمم والقيعان المؤكَّدة على 5 د والساعة و4 س        ⟵ 201 (سلّم المستويات)
  الزناد  : إغلاق شمعة 5 د وإغلاق التي قبلها                     ⟵ 103 (الشموع)
  الوقت   : نافذة المالك (ذروة لندن · افتتاح أمريكا)              ⟵ 412 (`owner_window`)
  الخبر   : نافذة منعٍ حول الخبر العالي                          ⟵ 411
  الارتباط: الإس آند بي والداو في جهة الناسداك على الساعة و4 س     ⟵ 151 (للرمزين)

العيار (معايَرٌ على أوّل ٧٠٪ من سنتين، مقيسٌ على آخر ٣٠٪ — ٤-ص):
  B = 0.0  (لا هامش خلف قاع الارتداد)  ·  N = 2.0  (الوقف لا يقلّ عن ضعفَي متوسّط مدى 5 د)
  C = 1.5  (الهدف لا يبعد أكثر من مرّة ونصف من متوسّط مدى اليوم)  ·  RR = 3.0
  الارتباط (أُضيف بعد قياسه وحده — ٤-ص): بلا شرط 364 صفقة +0.089R للصفقة، سحب 21.5R، ٣ أنصافٍ من ٥ موجبة؛
  وبشرط الإس آند بي والداو 241 صفقة +0.105R، سحب 13.7R، **الأنصاف الخمسة موجبة**، وخارج العيّنة +0.171R.
"""
from __future__ import annotations

from typing import Any, Iterable

STRATEGY_ID = "414"
STRATEGY_NAME = "trend_continuation_pullback"

B_PULL = 0.0
N_NOISE = 2.0
C_REACH = 1.5
MIN_RR = 3.0

BUY, SELL = "buy", "sell"

# حالات البطاقة — كلّها تُؤرشف بسببها (المرفوضة والفائتة مادّة المعايرة).
OPEN = "OPEN"
NO_WINDOW = "OUTSIDE_OWNER_WINDOW"
NEWS = "NEWS_BLACKOUT"
NO_DIRECTION = "FRAMES_DISAGREE"
PEERS_DISAGREE = "CORRELATION_DISAGREES"
# ٢٠٢٦-١٠-٠٨ (أمر المالك «الغِ الداو من الارتباط، بس الإس آند بي 500» + ختم «NQ»): كانت ("US500", "US30").
# مقيس قبل الحيّ على السنتين بحكم الإرسال (سبريد 1.5): الاثنان 155 صفقة · +22.7R · سحب 9.3 · ٥ من ٥ أنصاف ·
# اختبار +0.142 — والإس آند بي وحده 211 صفقة · +29.9R · سحب 9.4 · ٤ من ٥ · اختبار +0.308 (معامل 1.74).
PEERS = ("US500",)
FACT_MISSING = "FACT_MISSING"
NO_STRUCTURE = "NO_PULLBACK_STRUCTURE"
NO_TRIGGER = "NO_TRIGGER"
NO_TARGET = "NO_TARGET_WITHIN_REACH"
BAD_RISK = "NON_POSITIVE_RISK"


def direction_of(trend_1h: dict | None, trend_4h: dict | None) -> int:
    """+1 إن كان الإغلاق فوق متوسّط 20 على الإطارين معًا، و−1 إن كان تحته عليهما، وإلّا 0."""
    def side(fact):
        if not fact:
            return None
        close, ema20 = fact.get("close"), fact.get("ema_slow_value")
        if close is None or ema20 is None:
            return None
        return 1 if close > ema20 else -1 if close < ema20 else 0
    a, b = side(trend_1h), side(trend_4h)
    if a is None or b is None:
        return 0
    return a if a == b and a != 0 else 0


def last_swings(highs: Iterable, lows: Iterable, before: float):
    """آخر قمّة وآخر قاع مؤكَّدَين **قبل** اللحظة (تأكيدٌ أصغر منها تمامًا). كلٌّ (السعر، وقت التأكيد)."""
    def last(rows):
        best = None
        for row in rows or ():
            price, confirmed = float(row[0]), float(row[1])
            if confirmed < before and (best is None or confirmed >= best[1]):
                best = (price, confirmed)
        return best
    return last(highs), last(lows)


def nearest_target(levels: Iterable, buy: bool, entry: float, risk: float,
                   reach: float | None, at: float, rr: float = MIN_RR):
    """أقرب مستوى مؤكَّد (حتّى اللحظة) في الجهة يعطي ≥ rr، ولا يبعد أكثر من المتناول."""
    best = None
    for row in levels or ():
        price, confirmed = float(row[0]), float(row[1])
        if confirmed > at:
            continue
        dist = (price - entry) if buy else (entry - price)
        if dist <= 0 or dist < rr * risk or (reach is not None and dist > reach):
            continue
        if best is None or dist < best[1]:
            best = (price, dist)
    return None if best is None else best[0]


def evaluate(*, at: float, close: float, prev_close: float | None,
             trend_1h: dict | None, trend_4h: dict | None,
             atr_5m: float | None, atr_1d: float | None,
             ladder: dict | None, window: str | None, news_blocked: bool,
             peers: dict | None = None,
             b: float = B_PULL, n: float = N_NOISE, c: float = C_REACH,
             rr: float = MIN_RR) -> dict[str, Any]:
    """تقييم البطاقة عند إغلاق شمعة 5 د (اللحظة `at` = وقت الإغلاق). تُرجع الحالة وكلّ ما بُني عليه."""
    card: dict[str, Any] = {"strategy": STRATEGY_ID, "at": at, "window": window, "close": close}
    if not window:
        return {**card, "status": NO_WINDOW}
    if news_blocked:
        return {**card, "status": NEWS}
    d = direction_of(trend_1h, trend_4h)
    card["direction"] = d
    if d == 0:
        return {**card, "status": NO_DIRECTION}
    if peers is not None:
        if any(not peers.get(name) or None in tuple(peers.get(name)) for name in PEERS):
            return {**card, "status": FACT_MISSING, "missing": "peers"}
        sides = {name: direction_of(*peers.get(name)) for name in PEERS}
        card["peers"] = sides
        if any(side != d for side in sides.values()):
            return {**card, "status": PEERS_DISAGREE}
    if prev_close is None or atr_5m is None or atr_5m <= 0 or not ladder:
        return {**card, "status": FACT_MISSING}
    # ٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق): سقف المتناول جزءٌ من القاعدة المقيسة (الهدف ≤ ١٫٥ × مدى اليوم) — غيابه بعد
    # إقلاعٍ لا يرفع السقف بل يجعل الحقيقة ناقصة (في القياس كان حاضرًا دائمًا، فالنتيجة المقيسة لا تتغيّر).
    if atr_1d is None or atr_1d <= 0:
        return {**card, "status": FACT_MISSING, "missing": "atr_1d"}
    buy = d > 0
    five = (ladder or {}).get("5m") or {}
    hi, lo = last_swings(five.get("highs"), five.get("lows"), at)
    if hi is None or lo is None:
        return {**card, "status": NO_STRUCTURE}
    if buy:
        if not (lo[1] > hi[1]):
            return {**card, "status": NO_STRUCTURE}
        if not (close > hi[0] and prev_close <= hi[0]):
            return {**card, "status": NO_TRIGGER, "trigger_level": hi[0]}
        pull, broken = lo[0], hi[0]
        stop = min(pull - b * atr_5m, close - n * atr_5m)
    else:
        if not (hi[1] > lo[1]):
            return {**card, "status": NO_STRUCTURE}
        if not (close < lo[0] and prev_close >= lo[0]):
            return {**card, "status": NO_TRIGGER, "trigger_level": lo[0]}
        pull, broken = hi[0], lo[0]
        stop = max(pull + b * atr_5m, close + n * atr_5m)
    risk = abs(close - stop)
    if risk <= 0:
        return {**card, "status": BAD_RISK}
    reach = c * atr_1d if atr_1d and atr_1d > 0 else None
    side_key = "highs" if buy else "lows"
    levels = []
    for frame in ("1h", "4h"):
        levels.extend(((ladder or {}).get(frame) or {}).get(side_key) or [])
    target = nearest_target(levels, buy, close, risk, reach, at, rr)
    card.update({"side": BUY if buy else SELL, "entry": close, "stop": stop, "risk": risk,
                 "pullback": pull, "broken_level": broken, "reach": reach,
                 "atr_5m": atr_5m, "atr_1d": atr_1d})
    if target is None:
        return {**card, "status": NO_TARGET}
    card.update({"status": OPEN, "target": target, "rr": abs(target - close) / risk})
    return card
