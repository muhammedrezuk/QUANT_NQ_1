# -*- coding: utf-8 -*-
"""الاستراتيجيّات السبع (404–410) على حقائق الأقسام — المنطق الواحد الذي قيس (ختم المالك «NQ» ٢٠٢٦-١٠-١٠).

أمر المالك: «رجّعهم على الحيّ بهالأرقام … كلّهن» · «ما بيصير تحلّل لحالها — لازم تاخد كلّ التحليل من الأقسام» ·
«بتشتغل على أيّ زوج مفعّل». المقيس: `backtest/strategies_facts_2026-10-10/` (23 يومًا، 09-08⟵10-08، الناسداك):
القواعد هنا هي قواعد `signal()` و`stop_for()` هناك حرفًا، والإطارات الأربعة والجلستان كما قيست.

لا تحليل هنا: كلّ رقمٍ حقيقةٌ نشرها قسم —
  151 analysis.trend.state (المتوسّطان وميل البطيء) · 152 analysis.momentum.state (roc) · 165 analysis.noise.state
  (efficiency_ratio) · 202 structure.external.state (آخر قمّة/قاع خارجيّين) · 204 structure.bos.state (كسر) ·
  254 liquidity.sweep.state (كنس) · 310 stats.zscore.state (Z) · 315 stats.range.state (موقع السعر في مداه).
"""
from __future__ import annotations

from typing import Any

from shared.market_clock import CITY_LONDON, CITY_NEW_YORK, local_time
from shared.pips import from_pips, to_pips

FRAMES = ("1m", "5m", "15m", "1h")
STOP_FRAMES = ("5m", "15m", "1m")
#: عتبات البيانات المؤرشفة نفسها (405 z_threshold · 407 pullback_min_pct/100 · 409 MAX_RANGE_EFFICIENCY · edge_fraction).
Z_TH, PULL_MIN, RANGE_EFF, EDGE = 1.5, 0.0001, 0.35, 0.25
#: الوقف بالبِب (`shared.pips`) — قانون المالك «15–45 نقطة» للناسداك (النقطة بِبه). ٢٠٢٦-١٠-١٧ (ختمه «nq»: «بِب على كلّ السستم، ما في شي
#: اسمه نقاط أساس»): ما كان لغيره 5–15 نقطة أساس والهامش 0.3 حُوّل إلى بِب بأسعار ذلك اليوم فلا يتغيّر الحكم يومها، والرقم ثابتٌ بعدها
#: (الداو 51,969 · الإس آند بي 7,658 · الذهب 4,166 والبِب 0.1 · البتكوين 81,593 · اليورو 1.1239 · الجنيه 1.3326). الهدف 3R والأثلاث في 574.
# ١٧/١٠ (ختم المالك «عمّم وقف 20 Nq»): الناسداك 15 ⟵ 20 — قيس على 2023 في أداة الباك تست: أدنى وقف 20 رفع التوليفة الرابحة من +5.8٪ إلى +10.8٪
# وأكبر تراجعها من 14٪ إلى 10٪ (والعشوائيّ بالقوانين نفسها من −33٪ إلى −1٪: الوقف الضيّق كان يضرّ كلّ دخول).
STOP_PIPS = {"USTEC": (20.0, 45.0), "US30": (26.0, 78.0), "US500": (4.0, 11.0), "XAUUSD": (21.0, 62.0),
             "BTCUSD": (41.0, 122.0), "EURUSD": (6.0, 17.0), "GBPUSD": (7.0, 20.0)}
STOP_PIPS_DEFAULT = (5.0, 15.0)
STOP_PAD_PIPS = {"USTEC": 1.0, "US30": 1.6, "US500": 0.2, "XAUUSD": 1.2, "BTCUSD": 2.4, "EURUSD": 0.3, "GBPUSD": 0.4}
STOP_PAD_PIPS_DEFAULT = 0.3
#: الاسمان القديمان للناسداك (أدوات القياس تقرؤهما) — هما الجدولان نفساهما، والنقطة بِب الناسداك.
STOP_PTS, STOP_PAD_PTS = STOP_PIPS, STOP_PAD_PIPS
TARGET_R = 3.0
#: ٢٠٢٦-١٠-١٤ (ختم المالك «NQ»): بوّابة طلب الدخول 555 تطلب النسبة **بعد** السبريد (قاعدته ٠٩-٠٦:
#: (العائد − السبريد) ÷ (المخاطرة + السبريد) ≥ 3) — وهدف 3R تمامًا يسقط تحتها بأيّ سبريد، فحُجبت 23 صفقة
#: من 52 منذ إقلاع ١٠-١٤ مساءً، وصفقتا الناسداك كلتاهما. الهدف الآن 3R + 4×السبريد فتبقى النسبة 3 صافية،
#: وهامش 25٪ على السبريد لأنّ سبريد الإرسال (513) قد يتّسع عن سبريد البناء.
SPREAD_CUSHION = 1.25


def target_distance(risk: float, spread: float) -> float:
    """مسافة الهدف من الدخول كي تبقى النسبة بعد السبريد = TARGET_R: (ه − س) ÷ (م + س) = ن ⟸ ه = ن×م + (ن+1)×س."""
    return TARGET_R * risk + (TARGET_R + 1.0) * spread * SPREAD_CUSHION
#: الجلستان (أمر المالك ١٠-٠٩): لندن 08:00⟵16:30 لندن · نيويورك 09:30⟵16:00 نيويورك — أيّام العمل.
#: الوقت المحلّيّ من ساعة المشروع الموحّدة (`shared/market_clock` — بايثون المنظومة بلا جداول مناطق).
SESSIONS = (("london", CITY_LONDON, (8, 0), (16, 30)), ("ny", CITY_NEW_YORK, (9, 30), (16, 0)))

STRATEGIES = {
    "404": {"name": "trend", "ar": "الاتّجاه", "setup": "TREND_CONTINUATION_PULLBACK", "frames": FRAMES},
    "405": {"name": "reversal", "ar": "الانعكاس", "setup": "MEAN_REVERSION", "frames": FRAMES},  # ١٠-١٢: 310 على الشموع ⟸ كلّ إطار
    "406": {"name": "breakout", "ar": "الاختراق", "setup": "BREAKOUT_ACCEPTANCE", "frames": FRAMES},
    "407": {"name": "pullback", "ar": "الارتداد", "setup": "TREND_CONTINUATION_PULLBACK", "frames": FRAMES},
    "408": {"name": "momentum", "ar": "الزخم", "setup": "TREND_CONTINUATION_PULLBACK", "frames": FRAMES},
    "409": {"name": "range", "ar": "المدى", "setup": "MEAN_REVERSION", "frames": FRAMES},
    "410": {"name": "liquidity", "ar": "السيولة", "setup": "LIQUIDITY_RAID", "frames": FRAMES},
}
#: الحقائق التي يقرؤها كلّ واحد — اشتراكات ذرّته.
NEEDS = {
    "404": ("analysis.trend.state", "analysis.momentum.state"), "405": ("stats.zscore.state",),
    "406": ("structure.bos.state",), "407": ("analysis.trend.state",),
    "408": ("analysis.momentum.state", "analysis.acceleration.state", "analysis.noise.state", "stats.zscore.state"),
    "409": ("analysis.noise.state", "stats.range.state", "probability.hurst.state", "analysis.trend.state",
            "analysis.candle.state"),
    "410": ("liquidity.sweep.state",),
}
EVENT_ATOM = {"analysis.trend.state": "151", "analysis.momentum.state": "152", "analysis.noise.state": "165",
              "structure.external.state": "202", "structure.bos.state": "204", "liquidity.sweep.state": "254",
              "stats.zscore.state": "310", "stats.range.state": "315", "analysis.acceleration.state": "163",
              "probability.hurst.state": "358", "analysis.candle.state": "156"}


def num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


#: ٢٠٢٦-١٠-١٠ (أمر المالك «بطاقة للبتكوين تشتغل 7/24 بلا توقّف … عدّة استراتيجيّات الناسداك» + «ب NQ»): رموزٌ
#: بلا جلسات — كلّ ساعةٍ وكلّ يوم، والعطلة ضمنها. وقفها بنقاط الأساس (5–15) كأيّ رمزٍ غير الناسداك.
ROUND_CLOCK = frozenset({"BTCUSD"})
SESSION_ROUND_CLOCK = "24/7"


def session_of(at: float, symbol: str = "") -> str | None:
    """الجلسة التي تقع فيها اللحظة (أوّلها في التداخل: لندن)، أو لا شيء؛ والبتكوين جلسته الساعة كلّها."""
    if symbol.upper() in ROUND_CLOCK:
        return SESSION_ROUND_CLOCK
    for name, city, (h0, m0), (h1, m1) in SESSIONS:
        local = local_time(at, city)
        if local.weekday() >= 5:
            return None
        minutes = local.hour * 60 + local.minute
        if h0 * 60 + m0 < minutes <= h1 * 60 + m1:
            return name
    return None


class FactBook:
    """آخر حقيقةٍ لكلّ (ذرّة · رمز · إطار): قيمها وزمن وصولها بساعة البيانات."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}

    def put(self, event: str, payload: dict[str, Any], at: float) -> None:
        atom = EVENT_ATOM.get(event)
        symbol = str(payload.get("symbol") or "").upper()
        if not atom or not symbol:
            return
        tf = str(payload.get("timeframe") or (payload.get("metadata") or {}).get("timeframe") or "tick")
        row = dict(payload.get("metadata") or {})
        if "signal" in payload:
            row["signal"] = payload.get("signal")
        self.rows[(atom, symbol, tf)] = (at, row)

    def at(self, atom: str, symbol: str, tf: str, key: str) -> Any:
        hit = self.rows.get((atom, symbol, tf))
        return None if hit is None else hit[1].get(key)

    def event(self, atom: str, symbol: str, tf: str, key: str, m: float) -> Any:
        """حقيقة حدثٍ (كسر · كنس) نُشرت عند إغلاق الدقيقة m وحدها — وصولها بعد m بثوانٍ (يُقيَّم بعد مهلةٍ
        قصيرة)، فالنافذة ±30 ث حولها: لا تُعدّ في الدقيقة التالية مرّةً ثانية."""
        hit = self.rows.get((atom, symbol, tf))
        return hit[1].get(key) if hit is not None and m - 58.0 < hit[0] <= m + 30.0 else None  # ١٠-١٢: الكنس على التِّكّ يقع داخل الدقيقة


def signal(strat: str, f: FactBook, symbol: str, tf: str, m: float, close: float) -> int:
    """+1 شراء · −1 بيع · 0 لا شيء — قاعدة الاستراتيجيّة المؤرشفة بمدخل حقيقة القسم."""
    if strat == "404":
        fast, slow = num(f.at("151", symbol, tf, "ema_fast")), num(f.at("151", symbol, tf, "ema_slow"))
        fv, sv = num(f.at("151", symbol, tf, "ema_fast_value")), num(f.at("151", symbol, tf, "ema_slow_value"))
        if None in (fast, slow, fv, sv) or fv == sv:
            return 0
        short, long_ = (fv, sv) if fast < slow else (sv, fv)
        return 1 if short > long_ else -1
    if strat == "405":
        z = num(f.at("310", symbol, tf, "value"))  # ١٠-١٢: الإحصاء على الشموع
        return 0 if z is None else (-1 if z >= Z_TH else 1 if z <= -Z_TH else 0)
    if strat == "406":
        if f.event("204", symbol, tf, "signal", m) != "bos":
            return 0
        side = f.event("204", symbol, tf, "break_side", m)
        return 1 if side == "above" else -1 if side == "below" else 0
    if strat == "407":
        slope, mean = num(f.at("151", symbol, tf, "ema_slope")), num(f.at("151", symbol, tf, "ema_slow_value"))
        if slope is None or not mean:
            return 0
        dev = close / mean - 1
        return 1 if slope > 0 and dev <= -PULL_MIN else -1 if slope < 0 and dev >= PULL_MIN else 0
    if strat == "408":
        roc = num(f.at("152", symbol, tf, "roc"))
        return 0 if not roc else (1 if roc > 0 else -1)
    if strat == "409":
        eff, pos = num(f.at("165", symbol, tf, "efficiency_ratio")), num(f.at("315", symbol, tf, "position"))
        if eff is None or pos is None or eff >= RANGE_EFF:
            return 0
        return 1 if pos <= EDGE else -1 if pos >= 1 - EDGE else 0
    if strat == "410":
        if f.event("254", symbol, tf, "signal", m) != "sweep":
            return 0
        d = f.event("254", symbol, tf, "direction", m)
        return 1 if d == "sell_side" else -1 if d == "buy_side" else 0
    return 0


# ═══ العوامل (٢٠٢٦-١٠-١٠، أمر المالك «الّي تحسّن ضيفه … NQ») ═══════════════════════════════════════════════
# المقيس (`backtest/strategies_facts_2026-10-10/confluence.py`، 23 يومًا): بـ«الأغلبيّة» (الزناد + نصف العوامل فأكثر)
# تحسّنت ثلاث — 408 الزخم +26.9R ⟵ +36.7R · 404 الاتّجاه +0.226 ⟵ +0.266 للصفقة · 409 المدى −2.3R ⟵ +19.3R.
# فتعمل الثلاث بعواملها حيًّا؛ والأربع الأخرى بالزناد وحده حتّى يُعاد قياسها. العوامل هي دوالّ القياس نفسها.
HIGHER = {"1m": "5m", "5m": "15m", "15m": "1h", "1h": "4h", "tick": "5m"}
#: «لا مستوى أمامه» بالبِب (كان 20 نقطة أساس؛ حُوّل ١٠-١٧ بأسعار ذلك اليوم).
AHEAD_PIPS = {"USTEC": 58.0, "US30": 104.0, "US500": 15.0, "XAUUSD": 83.0, "BTCUSD": 163.0, "EURUSD": 22.0, "GBPUSD": 27.0}
AHEAD_PIPS_DEFAULT = 20.0


def _trend(f: FactBook, symbol: str, tf: str) -> int:
    fast, slow = num(f.at("151", symbol, tf, "ema_fast")), num(f.at("151", symbol, tf, "ema_slow"))
    fv, sv = num(f.at("151", symbol, tf, "ema_fast_value")), num(f.at("151", symbol, tf, "ema_slow_value"))
    if None in (fast, slow, fv, sv) or fv == sv:
        return 0
    short, long_ = (fv, sv) if fast < slow else (sv, fv)
    return 1 if short > long_ else -1


def _mom(f: FactBook, symbol: str, tf: str, d: int) -> bool:
    roc = num(f.at("152", symbol, tf, "roc"))
    return roc is not None and roc * d > 0


def _ratio(f: FactBook, atom: str, symbol: str, tf: str, key: str) -> float | None:
    return num(f.at(atom, symbol, "5m" if tf == "tick" else tf, key))


def _no_level_ahead(f: FactBook, symbol: str, d: int, close: float) -> bool:
    for tf in ("1h", "4h"):
        lvl = num(f.at("202", symbol, tf, "swing_high" if d > 0 else "swing_low"))
        if lvl and 0 < (lvl - close) * d and to_pips((lvl - close) * d, symbol) <= AHEAD_PIPS.get(symbol, AHEAD_PIPS_DEFAULT):
            return False
    return True


def _rejection(f: FactBook, symbol: str, d: int) -> bool:
    for tf in ("1m", "5m"):
        pat = f.at("156", symbol, tf, "pattern")
        up, lo = num(f.at("156", symbol, tf, "upper_wick")), num(f.at("156", symbol, tf, "lower_wick"))
        if pat in ("pin_bar", "engulfing") and up is not None and lo is not None and (lo > up if d > 0 else up > lo):
            return True
    return False


FACTORS = {
    "404": (lambda f, s, tf, d, c: _trend(f, s, "1h") == d and _trend(f, s, "4h") == d,
            lambda f, s, tf, d, c: _mom(f, s, tf, d),
            lambda f, s, tf, d, c: _no_level_ahead(f, s, d, c)),
    "408": (lambda f, s, tf, d, c: _mom(f, s, HIGHER[tf], d),
            lambda f, s, tf, d, c: (_ratio(f, "163", s, tf, "ratio") or 0.0) > 0,
            lambda f, s, tf, d, c: (_ratio(f, "165", s, tf, "efficiency_ratio") or 0.0) >= RANGE_EFF,
            lambda f, s, tf, d, c: (lambda z: z is not None and abs(z) < Z_TH)(num(f.at("310", s, tf, "value")))),
    "409": (lambda f, s, tf, d, c: (lambda h: h is not None and h < 0.5)(num(f.at("358", s, tf, "hurst"))),
            lambda f, s, tf, d, c: _trend(f, s, "1h") != _trend(f, s, "4h"),
            lambda f, s, tf, d, c: _rejection(f, s, d)),
}


def confirmed(strat: str, f: FactBook, symbol: str, tf: str, d: int, close: float) -> tuple[bool, int, int]:
    """الأغلبيّة: نصف عوامل الاستراتيجيّة فأكثر (الزناد شرطٌ قبلها). ما لا عوامل له يمرّ."""
    factors = FACTORS.get(strat)
    if not factors:
        return True, 0, 0
    got = sum(1 for fn in factors if fn(f, symbol, tf, d, close))
    need = -(-len(factors) // 2)
    return got >= need, got, len(factors)


# ═══ أرقام القرار (٢٠٢٦-١٠-١٢، أمر المالك «كلّ صفقة تحمل الحقائق التي فُتحت عليها وأرقامها» + «NQ») ══════════
# صفقة 405 (١٠-١٠) لم يُعرف كم كانت Z فيها: الدليل حمل «كم من كم» وحده. الآن لحظة الإرسال: الزناد على إطار الصفقة،
# وكلّ عاملٍ نجح أم لا ومدخلاته، والوقف — في `evidence.facts`، ويختمها دفتر البطاقات (465) على البطاقة.
TRIGGER = {
    "404": (("151", "ema_fast_value"), ("151", "ema_slow_value")),
    "405": (("310", "value"),),
    "406": (("204", "signal"), ("204", "break_side")),
    "407": (("151", "ema_slope"), ("151", "ema_slow_value")),
    "408": (("152", "roc"),),
    "409": (("165", "efficiency_ratio"), ("315", "position")),
    "410": (("254", "signal"), ("254", "direction")),
}
FACTOR_NAMES = {
    "404": ("trend_1h_4h", "momentum", "no_level_ahead"),
    "408": ("momentum_higher", "acceleration", "efficiency", "z_not_extreme"),
    "409": ("hurst_below_half", "trend_1h_vs_4h", "rejection"),
}
FACT_DIGITS = 6


def _clean(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int)):
        return v
    f = num(v)
    return round(f, FACT_DIGITS) if f is not None else str(v)


def _factor_inputs(strat: str, f: FactBook, s: str, tf: str, d: int) -> dict[str, Any]:
    if strat == "404":
        lvl = "swing_high" if d > 0 else "swing_low"
        return {"trend_1h": _trend(f, s, "1h"), "trend_4h": _trend(f, s, "4h"), "152_roc": f.at("152", s, tf, "roc"),
                "202_1h_" + lvl: f.at("202", s, "1h", lvl), "202_4h_" + lvl: f.at("202", s, "4h", lvl)}
    if strat == "408":
        return {"152_roc_" + HIGHER[tf]: f.at("152", s, HIGHER[tf], "roc"),
                "163_ratio": _ratio(f, "163", s, tf, "ratio"),
                "165_efficiency_ratio": _ratio(f, "165", s, tf, "efficiency_ratio"),
                "310_value": f.at("310", s, tf, "value")}
    if strat == "409":
        return {"358_hurst": f.at("358", s, tf, "hurst"), "trend_1h": _trend(f, s, "1h"),
                "trend_4h": _trend(f, s, "4h"), "156_1m_pattern": f.at("156", s, "1m", "pattern"),
                "156_5m_pattern": f.at("156", s, "5m", "pattern")}
    return {}


def decision_facts(strat: str, f: FactBook, symbol: str, tf: str, d: int, close: float,
                   stop: float, risk: float, stop_tf: str) -> dict[str, Any]:
    """الأرقام التي فُتحت عليها الصفقة لحظة فتحها — مفاتيحها «ذرّة_مفتاح» كما نشرها قسمها."""
    out: dict[str, Any] = {"frame": tf, "side": d, "close": close}
    for atom, key in TRIGGER.get(strat, ()):
        out["%s_%s" % (atom, key)] = f.at(atom, symbol, tf, key)
    if strat == "407":
        mean = num(f.at("151", symbol, tf, "ema_slow_value"))
        out["deviation"] = close / mean - 1 if mean else None
    for name, fn in zip(FACTOR_NAMES.get(strat, ()), FACTORS.get(strat, ())):
        out["factor_" + name] = bool(fn(f, symbol, tf, d, close))
    out.update(_factor_inputs(strat, f, symbol, tf, d))
    out.update({"stop": stop, "stop_points": risk, "stop_frame": stop_tf})
    return {k: _clean(v) for k, v in out.items()}


def stop_for(f: FactBook, symbol: str, side: int, entry: float) -> tuple[float, float, str] | None:
    """خلف آخر قاع/قمّة خارجيّة من 202 على 5د ثمّ 15د ثمّ 1د، ضمن حدود الوقف — وإلّا لا صفقة."""
    lo_p, hi_p = STOP_PIPS.get(symbol, STOP_PIPS_DEFAULT)
    lo, hi = from_pips(lo_p, symbol), from_pips(hi_p, symbol)
    pad = from_pips(STOP_PAD_PIPS.get(symbol, STOP_PAD_PIPS_DEFAULT), symbol)
    for tf in STOP_FRAMES:
        lvl = num(f.at("202", symbol, tf, "swing_low" if side > 0 else "swing_high"))
        if lvl is None:
            continue
        stop = lvl - pad if side > 0 else lvl + pad
        risk = (entry - stop) * side
        if lo <= risk <= hi:
            return stop, risk, tf
    return None
