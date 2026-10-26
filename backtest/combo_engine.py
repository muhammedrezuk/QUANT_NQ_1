# -*- coding: utf-8 -*-
"""محرّك التوليفة — أداة الباك تست الاحترافيّة (ورقة الخطوات ١٧/١٠، الخطوات 3 و4؛ ختم المالك «NQ»).

قوله: «أحطّ محلّل فلاني مع بنية مع داو واختبر، ثمّ أغيّر سيولة وقمّة وقاع وتذبذب مع أخبار — أيّ توليفة بدّي ياها بقدر أختبرها أنا
بيدي … وأغيّر أهداف واقتصاص وستوب … سريعة … ومخرجاتها مفصّلة، تقرير كامل واضح بالعربي» · «كلّ اختبار ينفتح مجلّد بتاريخ اليوم،
واسم الاختبار يقول شو هو وعلى أيش، وملفّ الاختبار كيف مشي، والنتيجة بملفٍّ مستقلّ».

The test reads the facts store (`backtest/facts_store.py`: the real atoms' published facts over the period) instead of
re-running the atoms, so any combination runs in seconds. A specification (JSON, written by the backtest page):
  symbol, from, to                      the data (minute candles of the broker)
  decision_frame                        decisions at every close of this frame
  direction {atom, frame, key} | random where the side comes from (a word field: rising/up/bullish = buy ...)
  conditions [{atom, frame, key, op, value, max_age_min}]   all must hold (op: == != > >= < <= between same_way)
  stop {method: structure|fixed|atr, band, pips, atr_frame, atr_mult, pad}
  targets [{r, close_pct}], breakeven_after, trail_after, trail_to_r
  risk_pct, cost_pips, scale_with_price, wait_min, max_per_day
  session {use_red_lines, first_minutes}, news {on, colors, before_min, after_min, close_open}, time_enough
  reference_random
Results go to «اختبارات الباك تست/<يوم التشغيل>/<اسم الاختبار>/»: الاختبار.md · النتيجة.md · الصفقات.csv · summary.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

HISTORY_DB = ROOT / "forex_runtime" / "var" / "history" / "ctrader_history.db"
CALENDAR_DB = Path(os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_calendar_history.db"))
# ٢٠٢٦-١٠-٢٦ (فحص تسرّب المستقبل، وختم المالك «NQ» على الإصلاح): ساعة خادم سجلّ التقويم غرينتش +3 ثابتة صيفًا وشتاءً — خبر الوظائف
# 08:30 نيويورك فيه 16:30 شتاءً و15:30 صيفًا في كلّ موعدٍ فُحص من 2022 و2023. كان يُطرح فرق يوم الوسيط (نيويورك + 7، أي +2 شتاءً)
# فتقع أخبار الشتاء بعد موعدها بساعة.
CALENDAR_SERVER_OFFSET_S = 3 * 3600
STORE = ROOT / "forex_runtime" / "var" / "facts_store"
OUT_ROOT = ROOT / "اختبارات الباك تست"
FRAME_S = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
PERIOD_OF = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4", "1d": "D1"}
UP_WORDS = {"up", "rising", "bullish", "bull", "buy", "long", "uptrend", "higher_highs_higher_lows", "above_fast",
            "with_primary", "positive", "above", "gap_up", "fvg_bullish"}
DOWN_WORDS = {"down", "falling", "bearish", "bear", "sell", "short", "downtrend", "lower_highs_lower_lows",
              "below_fast", "against_primary", "negative", "below", "gap_down", "fvg_bearish"}
STOP_FRAMES = ("5m", "15m", "1m")
SEED = 20230101
SYMBOL_AR = {"USTEC": "الناسداك", "US30": "داو جونز", "US500": "إس آند بي", "XAUUSD": "الذهب", "BTCUSD": "البتكوين",
             "EURUSD": "يورو/دولار", "GBPUSD": "جنيه/دولار"}
EXIT_AR = {"stop": "وقف", "target": "آخر هدف", "session_end": "خطّ الإغلاق", "news": "خبر", "end_of_data": "نهاية البيانات"}
DEFAULTS = {"symbol": "USTEC", "from": "2023-01-01", "to": "2024-01-01", "decision_frame": "15m",
            "direction": {"source": "random"}, "conditions": [],
            "stop": {"method": "structure", "band": [20.0, 45.0], "pips": 20.0, "atr_frame": "15m", "atr_mult": 1.5,
                     "pad": 1.0},
            "targets": [{"r": 1.0, "close_pct": 33.3}, {"r": 2.0, "close_pct": 33.3}, {"r": 3.0, "close_pct": 33.4}],
            "breakeven_after": 1, "trail_after": 2, "trail_to_r": 1.0, "risk_pct": 0.5, "cost_pips": 1.5,
            "scale_with_price": True, "wait_min": 75, "max_per_day": 0,
            "session": {"use_red_lines": True, "first_minutes": 15},
            "news": {"on": True, "colors": ["red"], "before_min": 15, "after_min": 15, "close_open": True, "currencies": []},
            "time_enough": True, "reference_random": True, "name": "", "balance": 10000.0, "live_stop_floor": True}
# ٢٠٢٦-١٠-٢٣ (ورقة «خطوط حمراء» المختومة — «كلّ قياسٍ يعمل داخل هذه الورقة»): الافتراضات صارت قوانينها — المخاطرة 0.50٪ من رصيدٍ
# ابتدائيّ 10,000 (القانون 7، من `shared/account_limits`) · انتظار 75 دقيقة بعد كلّ صفقة (12) · الخبر الأحمر 15 دقيقة قبل وبعد (25)
# على عملات الأصل والدولار (24، تُملأ في `run` حين تكون القائمة فارغة). كانت 1٪ · 15 دقيقة · ±6 للدولار وحده.
from shared import account_limits as _account_limits  # noqa: E402
DEFAULTS["risk_pct"] = _account_limits.DEFAULTS[_account_limits.PAIR_RISK_PCT]
DEFAULTS["balance"] = _account_limits.DEFAULTS[_account_limits.INITIAL_BALANCE]


def _epoch(day: str) -> float:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()


def merged(spec: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(DEFAULTS))
    for k, v in (spec or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


# ── the facts store ──────────────────────────────────────────────────────────────────────────────────────────
class Facts:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
        self._files: dict[str, Any] = {}

    def find(self, atom: str, frame: str, key: str) -> tuple[dict, dict] | None:
        for g in self.index["groups"]:
            if g["atom"] == str(atom) and g["frame"] == frame:
                for f in g["fields"]:
                    if f["key"] == key:
                        return g, f
        return None

    def series(self, atom: str, frame: str, key: str) -> tuple[np.ndarray, np.ndarray, dict] | None:
        hit = self.find(atom, frame, key)
        if hit is None:
            return None
        g, f = hit
        folder = self.folder / g["dir"]
        if g["dir"] not in self._files:
            self._files[g["dir"]] = np.fromfile(folder / "t.f64", dtype=np.float64)
        cache = "%s/%s" % (g["dir"], f["file"])
        if cache not in self._files:
            self._files[cache] = np.fromfile(folder / f["file"], dtype=np.float64 if f["kind"] == "num" else np.int32)
        return self._files[g["dir"]], self._files[cache], f

    @staticmethod
    def at(t: np.ndarray, values: np.ndarray, when: np.ndarray, max_age_s: float | None) -> tuple[np.ndarray, np.ndarray]:
        """The latest value at or before each moment, and whether one exists (and is young enough)."""
        idx = np.searchsorted(t, when, side="right") - 1
        ok = idx >= 0
        safe = np.where(ok, idx, 0)
        if max_age_s:
            ok &= (when - t[safe]) <= max_age_s
        return values[safe], ok


def _signed_pips(d: float, symbol: str) -> float:
    """shared.pips.to_pips gives a distance without sign (2026-10-19: the sign was lost in three places); this keeps it."""
    from shared.pips import to_pips
    return math.copysign(to_pips(d, symbol), d)


def _below_live_floor(risk: float, symbol: str) -> bool:
    """٢٠٢٦-١٠-٢٦ (ختم المالك «NQ» على الإصلاح): حارس أدنى الوقف الذي يردّ به 555 عند الإرسال (`entry_request_sizing.send_economics`
    و`shared.trade_setup.min_stop_pips`، بالهامش نفسه) — ما يردّه الحيّ تردّه الأداة. كان نطاق الإس آند بي 4–11 والبتكوين 41–122 يمرّ كلّه
    هنا، والحيّ يردّ ما دون 8 و50."""
    from shared.pips import to_pips
    from shared.trade_setup import min_stop_pips
    return to_pips(risk, symbol) + 1e-9 < min_stop_pips(symbol)


def word_side(word: str) -> int:
    w = str(word).strip().lower()
    return 1 if w in UP_WORDS else -1 if w in DOWN_WORDS else 0


# ── the context facts (owner, 2026-10-17: «هدول مو قلتلك عملهم»): what the live atoms 123 / 124 / 109 / 469 know, computed
#    exactly at each decision moment from the same shared code, so the builder can use them as conditions ──────────────
HOLIDAY_AR = {"birthday-of-martin-luther-king": "ميلاد مارتن لوثر كينغ", "christmas-day": "عيد الميلاد", "columbus-day": "يوم كولومبوس",
              "good-friday": "الجمعة العظيمة", "independence-day": "عيد الاستقلال الأمريكيّ",
              "juneteenth-national-independence-day": "يوم التحرير (جونتينث)", "labor-day": "عيد العمّال",
              "memorial-day": "يوم الذكرى", "new-years-day": "رأس السنة", "thanksgiving-day": "عيد الشكر",
              "veterans-day": "يوم المحاربين القدامى", "washingtons-birthday": "ميلاد واشنطن", "early-close": "إغلاق مبكّر",
              "none": "لا عطلة", "": ""}
EXCHANGE_AR = {"SYDNEY": "سيدني", "TOKYO": "طوكيو", "SHANGHAI": "شنغهاي", "HONG_KONG": "هونغ كونغ", "SINGAPORE": "سنغافورة",
               "FRANKFURT": "فرانكفورت", "LONDON": "لندن", "NEW_YORK": "نيويورك", "TORONTO": "تورونتو", "": ""}
GAP_AR = {"above_yesterday_close": "فوق إغلاق الأمس", "below_yesterday_close": "تحت إغلاق الأمس",
          "at_yesterday_close": "عند إغلاق الأمس", "": ""}
EXCHANGES = ("SYDNEY", "TOKYO", "SHANGHAI", "HONG_KONG", "SINGAPORE", "FRANKFURT", "LONDON", "NEW_YORK", "TORONTO")
VIRTUAL: dict[str, dict[str, Any]] = {
    "ctx": {"name": "سياق الزمن والجلسات والعطل (123)", "fields": {
        "time.quarter": "الربع", "time.half": "نصف السنة", "time.month": "الشهر", "time.day": "يوم الشهر",
        "time.weekday": "يوم الأسبوع (0 الإثنين)", "time.week_of_month": "أسبوع الشهر", "time.weeks_in_month": "أسابيع الشهر",
        "time.first_week_full": "أوّل أسبوعٍ كامل", "time.last_week_full": "آخر أسبوعٍ كامل",
        "time.days_left_in_month": "أيّام الشهر الباقية", "time.hours_to_daily_close": "ساعات حتّى الإغلاق اليوميّ",
        "time.hours_to_week_end": "ساعات حتّى إغلاق الأسبوع", "sessions.open_count": "بورصات مفتوحة",
        "sessions.overlap_count": "تداخلات الآن", "sessions.hours_to_next_open": "ساعات حتّى افتتاح التالية",
        "sessions.next_open": "البورصة التالية افتتاحًا", **{"open.%s" % x: "مفتوحة: %s" % EXCHANGE_AR[x] for x in EXCHANGES},
        "holiday.today": "عطلة اليوم وسببها", "holiday.days_to_next": "أيّام حتّى العطلة القادمة",
        "holiday.next": "العطلة القادمة", "holiday.days_since_prev": "أيّام منذ العطلة السابقة", "holiday.prev": "العطلة السابقة"}},
    "news": {"name": "الأخبار القادمة والسابقة", "fields": {
        "news.minutes_to_next": "دقائق حتّى الخبر القادم", "news.minutes_since_last": "دقائق منذ الخبر السابق"}},
    "lvl": {"name": "مستويات اليوم والحركة (124)", "fields": {}},
    "ema": {"name": "متوسّطات المالك 5 و10 و50 (ترتيبها)", "fields": {
        "order.%s" % f: "ترتيب المتوسّطات على %s" % f for f in ("1m", "5m", "15m", "30m", "1h", "4h", "1d")}},
    "perf": {"name": "أداء التوليفة قبل الصفقة", "fields": {
        "perf.day_pct": "ربح اليوم ٪", "perf.week_pct": "ربح الأسبوع ٪", "perf.month_pct": "ربح الشهر ٪",
        "perf.last_pct": "نتيجة آخر صفقة ٪", "perf.trades_today": "صفقات اليوم", "perf.losses_in_row": "خاسرات متتالية"}},
}
VIRTUAL["depth"] = {"name": "عمق الدفتر المسجّل (261–264 بتسجيل 265)", "fields": {
    "depth.imbalance": "ميل الدفتر: حجم المشترين − البائعين (موجب = شراء)",
    "depth.tilt_pips": "ميل السعر الدقيق عن الوسط بالبِب (موجب = شراء)",
    "depth.ofi": "تدفّق الأوامر (موجب = شراء)",
    "depth.impact_skew": "أثر الصعود − أثر النزول بالبِب (موجب = الصعود أسهل)"}}
DEPTH_DB = Path(r"M:\QUANT_NQ_DATA\depth_facts.db")


def _num_or_none(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


DEPTH_FIELDS = {
    "depth.imbalance": ("depth", lambda f: _num_or_none(f.get("m.imbalance_raw", (f.get("metadata") or {}).get("imbalance_raw")))),
    "depth.tilt_pips": ("microprice", lambda f: _num_or_none(f.get("m.tilt_pips", (f.get("metadata") or {}).get("tilt_pips")))),
    "depth.ofi": ("ofi", lambda f: _num_or_none(f.get("m.ofi", (f.get("metadata") or {}).get("ofi")))),
    "depth.impact_skew": ("price_impact", lambda f: (lambda u, d: u - d if u is not None and d is not None else None)(
        _num_or_none(f.get("m.impact_up_pips")), _num_or_none(f.get("m.impact_down_pips")))),
}
LEVEL_NAMES = ("yesterday", "premarket", "overnight", "opening", "week", "prev_week", "month", "prev_month")
for _lv in LEVEL_NAMES:
    for _side in ("high", "low"):
        VIRTUAL["lvl"]["fields"]["pips_from.%s.%s" % (_lv, _side)] = "بِب السعر عن %s %s" % (
            {"yesterday": "الأمس", "premarket": "ما قبل الافتتاح", "overnight": "الليل", "opening": "الافتتاح", "week": "الأسبوع",
             "prev_week": "الأسبوع السابق", "month": "الشهر", "prev_month": "الشهر السابق"}[_lv], "أعلى" if _side == "high" else "أدنى")
VIRTUAL["lvl"]["fields"].update({"pips_from.yesterday.close": "بِب السعر عن إغلاق الأمس", "gap.pips": "الفجوة بالبِب",
                                 "gap.filled": "امتلأت الفجوة", "gap.opened": "الافتتاح فوق/تحت إغلاق الأمس",
                                 "movement_pips.today": "مدى اليوم بالبِب", "movement_pips.yesterday": "مدى الأمس بالبِب"})
EMA_PERIODS = (5, 10, 50)
EMA_WARM_BARS = 150
CLEAR50_BARS = (1, 3, 5, 10)                                        # how many closed candles must stay clear of the 50 line
_EMA_FRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")
WORD_FIELDS = {"sessions.next_open", "holiday.today", "holiday.next", "holiday.prev", "gap.opened",
               *("order.%s" % f for f in _EMA_FRAMES), *("above50.%s" % f for f in _EMA_FRAMES),
               *("clear50_%d.%s" % (k, f) for k in CLEAR50_BARS for f in _EMA_FRAMES)}
VIRTUAL["ema"]["fields"].update({"above50.%s" % f: "السعر فوق خطّ 50 أو تحته على %s" % f for f in _EMA_FRAMES})
VIRTUAL["ema"]["fields"].update({"clear50_%d.%s" % (k, f): "آخر %d شموع على %s بعيدة عن خطّ 50" % (k, f)
                                 for k in CLEAR50_BARS for f in _EMA_FRAMES})
VIRTUAL["ema"]["fields"].update({"far50.%s" % f: "بعد السعر عن خطّ 50 على %s من 100 (مقارنةً بالشهر قبله)" % f
                                 for f in _EMA_FRAMES})


def virtual_values(atom: str, moments: np.ndarray, symbol: str, news: np.ndarray, closes: np.ndarray) -> dict[str, list]:
    """Every field of one context atom at each moment (words as text, numbers as float)."""
    from shared.pips import to_pips
    out: dict[str, list] = defaultdict(list)
    if atom == "ctx":
        from shared import market_clock
        from shared import market_context as mc
        table: dict[date, str] = {}
        for y in range(2012, 2031):
            table.update(market_clock.nyse_holidays(y))
            table.update(market_clock.bank_only_holidays(y))
        days = sorted(table)
        cache: dict[int, dict] = {}
        for m in moments:
            key = int(m // 60)
            if key not in cache:
                c = mc.context(float(m))
                tm, ss = c.get("time", {}), c.get("sessions", {})
                row = {"time.%s" % k: float(tm[k]) for k in ("quarter", "half", "month", "day", "weekday", "week_of_month",
                                                              "weeks_in_month", "days_left_in_month") if k in tm}
                row["time.first_week_full"] = float(bool(tm.get("first_week_full")))
                row["time.last_week_full"] = float(bool(tm.get("last_week_full")))
                row["time.hours_to_daily_close"] = float(tm.get("seconds_to_daily_close") or 0) / 3600
                row["time.hours_to_week_end"] = float(tm.get("seconds_to_week_end") or 0) / 3600
                opened = set(ss.get("open_now") or [])
                row["sessions.open_count"] = float(len(opened))
                row["sessions.overlap_count"] = float(len(ss.get("overlaps") or []))
                row["sessions.hours_to_next_open"] = float(ss.get("seconds_to_next_open") or 0) / 3600
                row["sessions.next_open"] = EXCHANGE_AR.get(str(ss.get("next_open") or ""), str(ss.get("next_open") or ""))
                for x in EXCHANGES:
                    row["open.%s" % x] = float(x in opened)
                today = market_clock.broker_day(float(m))[0]
                row["holiday.today"] = HOLIDAY_AR.get(market_clock.no_trade_day(float(m)) or "none", "")
                nxt = next((d for d in days if d > today), None)
                prv = next((d for d in reversed(days) if d < today), None)
                row["holiday.days_to_next"] = float((nxt - today).days) if nxt else float("nan")
                row["holiday.next"] = HOLIDAY_AR.get(table.get(nxt, ""), "") if nxt else ""
                row["holiday.days_since_prev"] = float((today - prv).days) if prv else float("nan")
                row["holiday.prev"] = HOLIDAY_AR.get(table.get(prv, ""), "") if prv else ""
                cache[key] = row
            for k, v in cache[key].items():
                out[k].append(v)
    elif atom == "news":
        for m in moments:
            k = np.searchsorted(news, m)
            out["news.minutes_to_next"].append(float((news[k] - m) / 60) if k < len(news) else float("nan"))
            out["news.minutes_since_last"].append(float((m - news[k - 1]) / 60) if k > 0 else float("nan"))
    elif atom == "ema":
        # المالك ١٧/١٠: «أنا استعملت المتوسّط الأسّيّ … 5 و10 و50 … لأعرف الاتّجاه» — صاعد 5 فوق 10 فوق 50، وهابط عكسه
        con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
        lo = float(moments.min()) if len(moments) else 0.0
        for frame, sec in FRAME_S.items():
            rows = con.execute("select period_start, close, high, low from candles_history where symbol=? and period=? and "
                               "period_start>=? and period_start<? order by period_start",
                               (symbol, PERIOD_OF[frame], lo - EMA_WARM_BARS * 3 * sec - 30 * 86400,
                                float(moments.max()) + sec if len(moments) else 0.0)).fetchall()
            ends = np.array([r[0] + sec for r in rows])
            alphas = [2.0 / (n_ + 1.0) for n_ in EMA_PERIODS]
            marks, e50, vals_ = [], [], None
            for i, (_, c_, _h, _l) in enumerate(rows):
                vals_ = [c_] * 3 if vals_ is None else [a * c_ + (1 - a) * v for a, v in zip(alphas, vals_)]
                marks.append("none" if i + 1 < EMA_WARM_BARS else "rising" if vals_[0] > vals_[1] > vals_[2]
                             else "falling" if vals_[0] < vals_[1] < vals_[2] else "none")
                e50.append(vals_[2] if i + 1 >= EMA_WARM_BARS else float("nan"))
            idx = np.searchsorted(ends, moments, side="right") - 1
            out["order.%s" % frame] = [marks[i] if i >= 0 else "none" for i in idx]
            # المالك ٢١/١٠: «كلّ شي فوق 50 صاعد، كلّ شي تحت 50 هابط» — السعر لحظة القرار مقابل متوسّط 50 لآخر شمعةٍ مغلقة
            out["above50.%s" % frame] = ["none" if i < 0 or not np.isfinite(e50[i]) else "rising" if p > e50[i]
                                         else "falling" if p < e50[i] else "none" for i, p in zip(idx, closes)]
            # المالك ٢١/١٠: «كلّ شموع صارت قريبة من خط 50، لمست خط 50 أو تذبذبت حوله، احذفها» — صاعدٌ فقط إن كانت آخر k شموعٍ
            # مغلقة كلّها فوق الخطّ بكاملها (قاعها فوقه) والسعر الآن فوقه، وهابطٌ عكسه، وغير ذلك «none» (قرب الخطّ)
            hi_ = np.array([r[2] for r in rows], dtype=np.float64)
            lo_ = np.array([r[3] for r in rows], dtype=np.float64)
            line = np.array(e50, dtype=np.float64)
            with np.errstate(invalid="ignore"):
                up_c = np.concatenate([[0], np.cumsum(lo_ > line)])
                dn_c = np.concatenate([[0], np.cumsum(hi_ < line)])
            for k_ in CLEAR50_BARS:
                words = []
                for i, p in zip(idx, closes):
                    if i < k_ - 1 or not np.isfinite(line[i]):
                        words.append("none")
                    elif up_c[i + 1] - up_c[i + 1 - k_] == k_ and p > line[i]:
                        words.append("rising")
                    elif dn_c[i + 1] - dn_c[i + 1 - k_] == k_ and p < line[i]:
                        words.append("falling")
                    else:
                        words.append("none")
                out["clear50_%d.%s" % (k_, frame)] = words
            # المالك ٢١/١٠: «عرضيّ بكون بعيد عن خطّ كثير» — بعد السعر عن الخطّ من 100، مقارنةً بأبعاد شموع هذا الإطار في الثلاثين
            # يومًا قبل يوم اللحظة (97 = أبعد من 97 من كلّ 100 شمعة في ذلك الشهر)
            gap_ = np.abs(np.array([r[1] for r in rows], dtype=np.float64) - line)
            far, ref_day, ref = [], None, np.zeros(0)
            for i, p, m in zip(idx, closes, moments):
                if i < 0 or not np.isfinite(line[i]):
                    far.append(float("nan"))
                    continue
                day0 = math.floor(float(m) / 86400) * 86400.0
                if day0 != ref_day:
                    a_, b_ = np.searchsorted(ends, [day0 - 30 * 86400, day0])
                    ref = gap_[a_:b_]
                    ref, ref_day = np.sort(ref[np.isfinite(ref)]), day0
                far.append(100.0 * float(np.searchsorted(ref, abs(float(p) - line[i]))) / len(ref) if len(ref) >= 100
                           else float("nan"))
            out["far50.%s" % frame] = far
        con.close()
    elif atom == "lvl":
        from shared import day_levels
        con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
        lo = float(moments.min()) - 40 * 86400 if len(moments) else 0
        m15 = con.execute("select period_start, open, high, low, close from candles_history where symbol=? and period='M15' "
                          "and period_start>=? order by period_start", (symbol, lo)).fetchall()
        d1 = con.execute("select period_start, open, high, low, close from candles_history where symbol=? and period='D1' "
                         "and period_start>=? order by period_start", (symbol, lo - 200 * 86400)).fetchall()
        con.close()
        t15 = np.array([r[0] for r in m15]) + 900
        td1 = np.array([r[0] for r in d1]) + 86400
        for m, price in zip(moments, closes):
            i, j = int(np.searchsorted(t15, m, side="right")), int(np.searchsorted(td1, m, side="right"))
            lv = day_levels.levels(symbol, float(m), m15[max(0, i - 1600):i], d1[max(0, j - 140):j])
            for name in LEVEL_NAMES:
                box = lv.get(name) or {}
                for side_ in ("high", "low"):
                    v = box.get(side_)
                    out["pips_from.%s.%s" % (name, side_)].append(_signed_pips(float(price) - float(v), symbol) if v else float("nan"))
            y = (lv.get("yesterday") or {}).get("close")
            out["pips_from.yesterday.close"].append(_signed_pips(float(price) - float(y), symbol) if y else float("nan"))
            gap = lv.get("gap") or {}
            out["gap.pips"].append(float(gap.get("pips")) if gap.get("pips") is not None else float("nan"))
            out["gap.filled"].append(float(bool(gap.get("filled"))) if gap else float("nan"))
            out["gap.opened"].append(GAP_AR.get(str(gap.get("opened") or ""), str(gap.get("opened") or "")))
            mv = lv.get("movement_pips") or {}
            for k in ("today", "yesterday"):
                v = mv.get(k)
                out["movement_pips.%s" % k].append(float(v) if isinstance(v, (int, float)) else float("nan"))
    elif atom == "depth":
        # ١٩/١٠ (المالك: «عنا عمق مسجّل صحيح قليل بس اختبر عليه»): آخر حقيقةٍ لكلّ محلّلٍ من محلّلات الدفتر الأربعة (261–264)
        # كما سجّلها 265 كلّ دقيقة — ما لم تكن أقدم من ثلاث دقائق عند لحظة القرار.
        con = sqlite3.connect("file:%s?mode=ro" % DEPTH_DB, uri=True, timeout=30)
        cols = {k: ([], []) for k in DEPTH_FIELDS}
        for at, analyzer, facts in con.execute("select at, analyzer, facts from depth_facts where symbol=? and at>=? and at<=? "
                                               "order by at", (symbol, float(moments.min()) - 600 if len(moments) else 0,
                                                               float(moments.max()) + 60 if len(moments) else 0)):
            f = json.loads(facts)
            for key, (an, fn) in DEPTH_FIELDS.items():
                if an == analyzer:
                    v = fn(f)
                    if v is not None:
                        cols[key][0].append(float(at))
                        cols[key][1].append(float(v))
        con.close()
        for key, (ts, vs) in cols.items():
            ts_, vs_ = np.array(ts), np.array(vs)
            idx = np.searchsorted(ts_, moments, side="right") - 1
            out[key] = [float(vs_[i]) if i >= 0 and m - ts_[i] <= 180 else float("nan") for i, m in zip(idx, moments)]
    return out


# ── the data ────────────────────────────────────────────────────────────────────────────────────────────────
def load_minutes(symbol: str, t0: float, t1: float) -> dict[str, np.ndarray]:
    con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    rows = con.execute("select period_start, high, low, close from candles_history where symbol=? and period='M1' and "
                       "period_start>=? and period_start<? order by period_start", (symbol, t0, t1)).fetchall()
    con.close()
    a = np.array(rows, dtype=np.float64) if rows else np.zeros((0, 4))
    return {"t": a[:, 0] + 60.0, "h": a[:, 1], "l": a[:, 2], "c": a[:, 3]}       # t = the minute's close


def decision_moments(symbol: str, frame: str, t0: float, t1: float) -> tuple[np.ndarray, np.ndarray]:
    con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    rows = con.execute("select period_start, close from candles_history where symbol=? and period=? and period_start>=? "
                       "and period_start<? order by period_start", (symbol, PERIOD_OF[frame], t0, t1)).fetchall()
    con.close()
    a = np.array(rows, dtype=np.float64) if rows else np.zeros((0, 2))
    return a[:, 0] + FRAME_S[frame], a[:, 1]


def price_ref(symbol: str) -> float:
    con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    hi = con.execute("select max(period_start) from candles_history where symbol=? and period='M1'", (symbol,)).fetchone()[0]
    xs = sorted(r[0] for r in con.execute("select close from candles_history where symbol=? and period='M1' and "
                                          "period_start>=? and period_start % 3600 = 0", (symbol, hi - 365 * 86400)))
    con.close()
    return xs[len(xs) // 2] if xs else 1.0


def news_times(news: dict[str, Any], t0: float, t1: float) -> np.ndarray:
    """Instants of the chosen-colour items of the chosen currencies (MetaTrader history, our colour reference)."""
    if not news.get("on"):
        return np.zeros(0)
    colors = json.loads((ROOT / "shared" / "news_colors.json").read_text(encoding="utf-8"))
    wanted = {c for c in news.get("colors") or ["red"]}
    codes = {code for code, v in colors.get("mt5_codes", {}).items() if v.get("color") in wanted}
    currencies = tuple(news.get("currencies") or ["USD"])
    con = sqlite3.connect("file:%s?mode=ro" % CALENDAR_DB, uri=True)
    marks = "?" * len(currencies)
    out = [float(ts) - CALENDAR_SERVER_OFFSET_S for code, ts in con.execute(
        "SELECT event_code, time_server FROM calendar_history WHERE currency IN (%s)" % ",".join(marks), currencies)
        if str(code) in codes and ts]
    con.close()
    return np.array(sorted(t for t in out if t0 - 86400 <= t <= t1 + 86400), dtype=np.float64)


# ── one trade ───────────────────────────────────────────────────────────────────────────────────────────────
class Trade:
    def __init__(self, label, side, at, entry, stop, targets, be_after, trail_after, trail_to_r, cost):
        self.label, self.side, self.at, self.entry, self.stop0, self.st = label, side, at, entry, stop, stop
        self.risk = abs(entry - stop)
        self.targets = targets                                    # [(r, fraction)]
        self.be_after, self.trail_after, self.trail_to_r, self.cost = be_after, trail_after, trail_to_r, cost
        self.stage, self.left, self.got, self.exit, self.exit_at = 0, 1.0, 0.0, "", 0.0
        self.mfe, self.mae = 0.0, 0.0

    def minute(self, t, h, l) -> bool:
        s, e, r = self.side, self.entry, self.risk
        self.mfe = max(self.mfe, ((h - e) if s > 0 else (e - l)) / r)
        self.mae = min(self.mae, ((l - e) if s > 0 else (e - h)) / r)
        if (l <= self.st) if s > 0 else (h >= self.st):           # the stop first when a minute reaches both
            self.got += self.left * (self.st - e) * s / r
            self.left, self.exit, self.exit_at = 0.0, "stop", t
            return True
        reach = h if s > 0 else l
        while self.stage < len(self.targets):
            tr, frac = self.targets[self.stage]
            if (reach - (e + s * r * tr)) * s < 0:
                break
            take = min(frac, self.left)
            self.got += take * tr
            self.left -= take
            self.stage += 1
            if self.be_after and self.stage == self.be_after:
                self.st = e
            if self.trail_after and self.stage >= self.trail_after:
                self.st = e + s * r * self.trail_to_r if self.stage == self.trail_after else self.st
            if self.left <= 1e-9:
                self.exit, self.exit_at = "target", t
                return True
        return False

    def close(self, t, price, why):
        self.got += self.left * (price - self.entry) * self.side / self.risk
        self.left, self.exit, self.exit_at = 0.0, why, t

    def result_r(self) -> float:
        return self.got - self.cost / self.risk


# ── the run ─────────────────────────────────────────────────────────────────────────────────────────────────
def run(spec: dict[str, Any], log=print) -> dict[str, Any]:
    from shared import red_lines
    from shared.pips import from_pips, to_pips
    began = time.time()
    sym = spec["symbol"]
    if not (spec.get("news") or {}).get("currencies"):   # ٢٣/١٠ (القانون 24): عملات الأصل، والدولار لكلّ الرموز
        spec = {**spec, "news": {**(spec.get("news") or {}),
                                 "currencies": sorted({red_lines.USD, *red_lines.currencies_of(sym)})}}
    t0, t1 = _epoch(spec["from"]), _epoch(spec["to"])
    folder = Path(spec["store"]) if spec.get("store") else STORE / sym / ("%s_%s" % (spec["from"], spec["to"]))
    if not (folder / "index.json").exists():
        raise SystemExit("لا مخزن حقائق لهذا الرمز وهذه الفترة — ابنِه من الصفحة أوّلًا (%s)" % folder)
    facts = Facts(folder)
    frame = spec["decision_frame"]
    moments, closes = decision_moments(sym, frame, t0, t1)
    log("التوليفة: لحظات القرار %d على إطار %s" % (len(moments), frame))
    keep = np.ones(len(moments), dtype=bool)
    why: dict[str, int] = defaultdict(int)
    first_s = float(spec["session"].get("first_minutes") or 0) * 60
    if spec["session"].get("use_red_lines", True):
        from shared import market_clock
        for i, m in enumerate(moments):
            inside, opened = red_lines.session_state(m, sym)
            if not inside or (opened is not None and m - opened < first_s):
                keep[i] = False
        why["outside_window_or_first_minutes"] = int((~keep).sum())
        # ٢٣/١٠ (القانون 22 في «خطوط حمراء»): لا تداول يوم عطلة البورصة أو البنوك الأمريكيّة أو الإغلاق المبكر — كان هذا المسار
        # لا يمنعه، والحيّ يمنعه (طالب الدخول 555).
        for i in np.nonzero(keep)[0]:
            if market_clock.no_trade_day(float(moments[i])):
                keep[i] = False
                why["no_trade_day"] += 1
    news = news_times(spec["news"], t0, t1) if spec["news"].get("on") else news_times({**spec["news"], "on": True}, t0, t1)
    virt: dict[str, dict[str, list]] = {}
    perf_conds = [c for c in spec["conditions"] if c.get("atom") == "perf"]
    ordered = sorted([c for c in spec["conditions"] if c.get("atom") != "perf"], key=lambda c: c["atom"] in VIRTUAL)
    for cond in ordered:
        op, target = cond.get("op", "=="), cond.get("value")
        if cond["atom"] in VIRTUAL:
            if cond["atom"] not in virt:
                idx = np.nonzero(keep)[0]
                log("التوليفة: تُحسب حقائق «%s» عند %d لحظة قرارٍ باقية" % (VIRTUAL[cond["atom"]]["name"], len(idx)))
                part = virtual_values(cond["atom"], moments[idx], sym, news, closes[idx])
                full: dict[str, list] = {}
                for k, vals_ in part.items():
                    col = [("" if k in WORD_FIELDS else float("nan"))] * len(moments)
                    for pos, val in zip(idx, vals_):
                        col[pos] = val
                    full[k] = col
                virt[cond["atom"]] = full
            raw = virt[cond["atom"]].get(cond["key"])
            if raw is None:
                raise SystemExit("حقيقة السياق غير معروفة: %s" % cond["key"])
            if cond["key"] in WORD_FIELDS:
                f = {"kind": "word"}
                words = np.array([str(x) for x in raw], dtype=object)
                ok = np.ones(len(moments), dtype=bool)
            else:
                f = {"kind": "num"}
                vals = np.array(raw, dtype=np.float64)
                ok = np.isfinite(vals)
        else:
            s = facts.series(cond["atom"], cond["frame"], cond["key"])
            if s is None:
                raise SystemExit("الحقيقة غير موجودة في المخزن: %s %s %s" % (cond["atom"], cond["frame"], cond["key"]))
            tt, v, f = s
            vals, ok = Facts.at(tt, v, moments, float(cond.get("max_age_min") or 0) * 60 or None)
            if f["kind"] == "word":
                vocab = f["vocab"] or []
                words = np.array([vocab[i] if 0 <= i < len(vocab) else "" for i in vals.astype(int)], dtype=object)
        if f["kind"] == "word":
            if op == "same_way":
                cond["_words"] = words
                passed = ok
            elif op in ("==", "!="):
                eq = words == str(target)
                passed = ok & (eq if op == "==" else ~eq)
            elif op == "in":
                passed = ok & np.isin(words, list(target or []))
            else:
                raise SystemExit("مقارنةٌ لا تصلح لكلمة: %s" % op)
        elif op == "same_way":
            cond["_signs"] = np.sign(np.nan_to_num(vals))
            passed = ok
        else:
            x = vals
            if op == "between":
                lo, hi = target
                passed = ok & (x >= float(lo)) & (x <= float(hi))
            else:
                y = float(target)
                passed = ok & {"==": x == y, "!=": x != y, ">": x > y, ">=": x >= y, "<": x < y, "<=": x <= y}[op]
        before = int(keep.sum())
        keep &= passed
        why["condition %s %s %s" % (cond["atom"], cond["frame"], cond["key"])] += before - int(keep.sum())
    side = np.zeros(len(moments), dtype=int)
    direction = spec["direction"]
    rng = random.Random(SEED)
    if direction.get("source") == "fact":
        s = facts.series(direction["atom"], direction["frame"], direction["key"])
        if s is None:
            raise SystemExit("حقيقة الجهة غير موجودة في المخزن")
        t, v, f = s
        vals, ok = Facts.at(t, v, moments, float(direction.get("max_age_min") or 0) * 60 or None)
        vocab = f.get("vocab") or []
        if f["kind"] == "word":
            side = np.array([word_side(vocab[i]) if ok[j] and 0 <= i < len(vocab) else 0
                             for j, i in enumerate(vals.astype(int))], dtype=int)
        else:
            side = np.where(ok, np.sign(vals), 0).astype(int)
    elif direction.get("source") == "virtual":
        # ١٩/١٠: الجهة من حقيقة سياقٍ محسوبة (مثل عمق الدفتر المسجّل) — إشارة الرقم، أو كلمة الجهة.
        raw = virtual_values(direction["atom"], moments, sym, news, closes).get(direction["key"], [])
        side = np.array([word_side(v) if isinstance(v, str) else (0 if v != v or v == 0 else (1 if v > 0 else -1))
                         for v in raw], dtype=int)
    else:
        side = np.array([rng.choice((1, -1)) for _ in moments], dtype=int)
    for cond in spec["conditions"]:
        if "_words" in cond or "_signs" in cond:                   # «في جهة الصفقة نفسها»
            agree = (np.array([word_side(w) for w in cond.pop("_words")]) if "_words" in cond
                     else cond.pop("_signs").astype(int)) == side
            before = int(keep.sum())
            keep &= agree
            why["same_way %s %s" % (cond["atom"], cond["key"])] += before - int(keep.sum())
    if direction.get("invert"):
        # ١٩/١٠ (المالك: «وين الحافّة؟»): الجهة معكوسة بعد الشروط كلّها — المقارنة العادلة بالتوليفة نفسها، لا بالقرعة.
        side = -side
    before = int(keep.sum())
    keep &= side != 0
    why["no_direction"] += before - int(keep.sum())
    minutes = load_minutes(sym, t0 - 86400, t1 + 3 * 86400)
    if not spec["news"].get("on"):
        news = np.zeros(0)                                         # the filter is off: the times served only as facts
    pref = price_ref(sym)
    labels = ["التوليفة"] + (["مرجع: جهة عشوائيّة"] if spec.get("reference_random") else [])
    trades = {lb: [] for lb in labels}
    skipped = {lb: defaultdict(int) for lb in labels}
    tg_total = sum(float(x["close_pct"]) for x in spec["targets"]) or 100.0
    targets = [(float(x["r"]), float(x["close_pct"]) / tg_total) for x in spec["targets"]]
    stop_cfg = spec["stop"]
    nb, na = float(spec["news"].get("before_min", 6)) * 60, float(spec["news"].get("after_min", 6)) * 60
    entry = spec.get("entry") or {}
    triggers = _triggers(facts, entry["triggers"]) if entry.get("triggers") else \
        level_triggers(sym, t0, t1, entry["levels"]) if entry.get("levels") else None
    within_s = float(entry.get("within_min") or 15) * 60
    if triggers is not None:
        log("التوليفة: إشارات الدخول %d (شراء %d · بيع %d) · الانتظار حتّى %g دقيقة" % (
            len(triggers[0]), int((triggers[1] > 0).sum()), int((triggers[1] < 0).sum()), within_s / 60))
    # ١٩/١٠ (المالك: «ليش التوليفة ما بتعطي أكثر من 3 أضعاف … 1/3 حدّ، أكثر منه مو مشكلة»): الهدف الأخير من التحليل —
    # أقرب مستوى في جهة الصفقة بعد min_r أضعافٍ أو أبعد: قمم الهيكل وقيعانه (202) على أطرٍ مختارة، وأعلى/أدنى الأمس والأسبوع
    # والشهر (حقائق المستويات نفسها)؛ وإلّا min_r. والأهداف قبله كما هي.
    tgt_cfg = spec.get("target_from") or {}
    lvl_at: dict[int, dict[str, float]] = {}
    rounds_at: dict[float, list[float]] = {}
    map_at: dict[float, list[float]] = {}
    map_rows = None
    if tgt_cfg.get("method") == "next_level" and tgt_cfg.get("map"):
        # ٢٣/١٠ (المالك «قيس»: خريطة المتداول وحدها) — الخريطة نفسها التي تُطلق رأس الحربة، مثبّتةً عند افتتاح النافذة
        m15_ = _bars_db(sym, "M15", t0 - 40 * 86400, t1)
        d1_ = _bars_db(sym, "D1", t0 - 60 * 86400, t1)
        map_rows = (m15_, np.array([r[0] for r in m15_]) + 900, d1_, np.array([r[0] for r in d1_]) + 86400)
    if tgt_cfg.get("method") in ("analysis", "next_level") and tgt_cfg.get("levels", True) and not tgt_cfg.get("map"):
        idx = np.nonzero(keep)[0]
        vv = virtual_values("lvl", moments[idx], sym, news, closes[idx])
        for n_, i_ in enumerate(idx):
            lvl_at[int(i_)] = {k: vv[k][n_] for k in vv if k.startswith("pips_from.") and not k.endswith(".close")}
    for lb in labels:
        rnd = random.Random(SEED + 1)
        free_at, per_day = -1.0, defaultdict(int)
        open_until = -1.0
        for i in np.nonzero(keep)[0]:
            m, price = float(moments[i]), float(closes[i])
            # ١٨/١٠ (المالك: «1,749 كم وحدة ضربت أهداف وستوب؟»): «مستقلّة» = كلّ لحظةٍ صفقةٌ وحدها، بلا انتظار المفتوحة.
            if not spec.get("independent") and m < max(free_at, open_until):
                skipped[lb]["busy_or_waiting"] += 1
                continue
            day = datetime.fromtimestamp(m, timezone.utc).date()
            if spec.get("max_per_day") and per_day[day] >= int(spec["max_per_day"]):
                skipped[lb]["max_per_day"] += 1
                continue
            k = np.searchsorted(news, m)
            near = [x for x in news[max(0, k - 1):k + 1] if -nb <= m - x <= na]
            if near:
                skipped[lb]["news_window"] += 1
                continue
            if perf_conds and not _perf_ok(perf_conds, trades[lb], m):
                skipped[lb]["performance_condition"] += 1
                continue
            s = int(side[i]) if lb == "التوليفة" else rnd.choice((1, -1))
            kind = None
            if triggers is not None:                       # «رأس الحربة» (١٨/١٠): الدخول ينتظر إشارة البنية في جهة الصفقة
                hit = _first_trigger(triggers, s, m, within_s)
                if hit is None:
                    skipped[lb]["no_trigger"] += 1
                    continue
                kind = _trigger_kind(triggers, hit, s)
                # ١٩/١٠: إشارةٌ داخل الدقيقة (الكنس على التِّكّ) ⟸ الدخول بإغلاق دقيقتها نفسها، بعدها لا قبلها؛ كان يُدخل بإغلاق
                # الدقيقة السابقة ثمّ يُحاسَب على الدقيقة التي فيها ذيل الكنس، فيُضرب الوقف في الدقيقة الأولى زورًا.
                m = math.ceil(hit / 60.0) * 60.0
                price = float(minutes["c"][max(0, int(np.searchsorted(minutes["t"], m, side="right")) - 1)])
                k = np.searchsorted(news, m)
                if [x for x in news[max(0, k - 1):k + 1] if -nb <= m - x <= na]:
                    skipped[lb]["news_window"] += 1
                    continue
                if spec["session"].get("use_red_lines", True) and not red_lines.session_state(m, sym)[0]:
                    skipped[lb]["trigger_outside_window"] += 1
                    continue
            scale = price / pref if spec.get("scale_with_price", True) else 1.0
            stop = _stop(facts, stop_cfg, sym, s, m, price, scale, from_pips)
            if stop is None:
                skipped[lb]["no_stop"] += 1
                continue
            risk = abs(price - stop)
            if spec.get("live_stop_floor", True) and _below_live_floor(risk, sym):
                skipped[lb]["stop_below_floor"] += 1
                continue
            tg, tkind = targets, None
            if tgt_cfg.get("method") == "analysis":
                tg = _analysis_targets(facts, tgt_cfg, targets, lvl_at.get(int(i), {}), sym, s, m, price, risk, to_pips)
            elif tgt_cfg.get("method") == "next_level":
                # ٢٣/١٠ (المالك: «الوقف خلف البنية، والهدف عند المستوى التالي قبله لا عليه» ثمّ «بس ما يكون اقل من 1/3»)
                if map_rows is not None:
                    ahead = _map_levels(sym, m, minutes, map_at, map_rows)
                else:
                    ahead = _level_prices(lvl_at.get(int(i), {}), float(closes[i]), sym, from_pips) if tgt_cfg.get("levels", True) else []
                    if tgt_cfg.get("round", True):
                        ahead = ahead + _round_levels(sym, m, minutes, rounds_at)
                tg, tkind = _next_level_targets(targets, ahead, s, price, risk,
                                                from_pips(float(spec.get("cost_pips") or 0), sym) * scale,
                                                from_pips(float(tgt_cfg.get("pad_pips") or 0), sym) * scale,
                                                float(tgt_cfg.get("min_r") or 3.0))
                if tg is None:
                    skipped[lb]["target_below_three"] += 1
                    continue
            nxt = news[k] if k < len(news) else float("inf")
            news_left = nxt - nb - m if spec["news"].get("close_open", True) else float("inf")
            window_left = red_lines.seconds_to_red_line(m, sym, None) if spec["session"].get("use_red_lines", True) else None
            window_left = float(window_left) if window_left is not None and window_left > 0 else float("inf")
            left = min(news_left, window_left)
            reason = "news" if news_left < window_left else "session_end"
            left = left if math.isfinite(left) else 86400.0
            # ٢٥/١٠ (ختم المالك «nq»، القانون 21): «ما تفتح صفقات جديدة» في الساعة الأخيرة من نافذة الأصل — كما في الحيّ. وسقط شرط
            # الحركة المتوقّعة قبل أقرب خطٍّ أحمر كلّه؛ والمفتوح يكمل حتّى نهاية النافذة.
            if spec.get("time_enough") and red_lines.in_last_hour(m, sym):
                skipped[lb]["last_hour"] += 1
                continue
            tr = Trade(lb, s, m, price, stop, tg, int(spec.get("breakeven_after") or 0),
                       int(spec.get("trail_after") or 0), float(spec.get("trail_to_r") or 0),
                       from_pips(float(spec.get("cost_pips") or 0), sym) * scale)
            j = int(np.searchsorted(minutes["t"], m, side="right"))
            end = m + left
            closed = False
            while j < len(minutes["t"]):
                t, h, l, c = minutes["t"][j], minutes["h"][j], minutes["l"][j], minutes["c"][j]
                if t > end:
                    # ٢٥/١٠: يُغلق عند الخطّ نفسه بسعر آخر دقيقةٍ قبله — كانت ساعة الإغلاق ساعة أوّل دقيقةٍ بعده، فتقع بعد العطلة
                    # الأسبوعيّة إن جاءت بينهما (ظهر حين صار الدخول مسموحًا حتّى الساعة الأخيرة).
                    tr.close(min(t, end), float(minutes["c"][j - 1]), reason)
                    closed = True
                    break
                if tr.minute(t, h, l):
                    closed = True
                    break
                j += 1
            if not closed:
                tr.close(float(minutes["t"][-1]), float(minutes["c"][-1]), "end_of_data")
            trades[lb].append(_record(tr, spec, to_pips))
            if kind is not None:                           # which trader level fired the spearhead (٢٣/١٠)
                trades[lb][-1]["level"] = kind
            if tkind is not None:                          # the last target: at the next level, or 3R with none ahead
                trades[lb][-1]["target_from"] = tkind
            per_day[day] += 1
            open_until = tr.exit_at
            free_at = tr.exit_at + float(spec.get("wait_min") or 0) * 60
    return {"spec": spec, "moments": len(moments), "candidates": int(keep.sum()), "filtered": dict(why),
            "skipped": {k: dict(v) for k, v in skipped.items()}, "trades": trades,
            "seconds": round(time.time() - began, 1), "store": str(folder)}


def _analysis_targets(facts, cfg, targets, lvl, sym, side, m, price, risk, to_pips) -> list:
    """The last target moved to the nearest level beyond min_r in the trade direction (or min_r when none is that far)."""
    min_r = float(cfg.get("min_r") or 3.0)
    risk_p = to_pips(risk, sym)
    dists = []
    for key, v in lvl.items():                                   # pips_from.<level>.<high|low> = price − level, in pips
        if v == v:
            dists.append(-v if side > 0 else v)
    for fr in cfg.get("swings") or ():
        s_ = facts.series("202", fr, "m.swing_high" if side > 0 else "m.swing_low")
        if s_ is not None:
            vals, ok = Facts.at(s_[0], s_[1], np.array([m]), None)
            if ok[0] and np.isfinite(vals[0]):
                dists.append(_signed_pips((float(vals[0]) - price) * side, sym))
    far = [d for d in dists if d >= min_r * risk_p]
    final_r = (min(far) / risk_p) if far and risk_p > 0 else min_r
    if cfg.get("max_r"):
        final_r = min(final_r, float(cfg["max_r"]))
    return list(targets[:-1]) + [(final_r, targets[-1][1])]


def _level_prices(lvl: dict[str, float], decision_close: float, sym: str, from_pips) -> list[float]:
    """The prices of atom 124's levels from its `pips_from.*` facts (price − level, in pips, read at the decision close)."""
    out = []
    for v in lvl.values():
        if v == v:
            out.append(decision_close - math.copysign(from_pips(abs(v), sym), v))
    return out


def _round_levels(sym: str, m: float, minutes: dict[str, np.ndarray], cache: dict[float, list[float]]) -> list[float]:
    """The two round numbers around the last price before the asset's window opened (the trader's map, ROUND_STEP)."""
    from shared import red_lines
    step = ROUND_STEP.get(sym, (0.0, 0.0))[0]
    opened = red_lines.session_state(m, sym)[1]
    if not step or opened is None:
        return []
    if opened not in cache:
        j = int(np.searchsorted(minutes["t"], opened, side="right")) - 1
        price = float(minutes["c"][j]) if j >= 0 else 0.0
        below = math.floor(price / step) * step
        cache[opened] = [below, below + step] if price > 0 else []
    return cache[opened]


def _map_levels(sym: str, m: float, minutes: dict[str, np.ndarray], cache: dict[float, list[float]], rows: tuple) -> list[float]:
    """The trader's map of the day the moment belongs to (`trader_levels` at the window's opening, from the past only):
    yesterday's high, low and close, the night's high and low, last week's high and low, the two round numbers."""
    from shared import red_lines
    opened = red_lines.session_state(m, sym)[1]
    if opened is None:
        return []
    if opened not in cache:
        m15, t15, d1, td1 = rows
        j = int(np.searchsorted(minutes["t"], opened, side="right")) - 1
        k15, kd = int(np.searchsorted(t15, opened, side="right")), int(np.searchsorted(td1, opened, side="right"))
        cache[opened] = [v for _, v in trader_levels(sym, opened, m15[max(0, k15 - 1600):k15], d1[max(0, kd - 140):kd],
                                                     float(minutes["c"][j]))] if j >= 0 and k15 > 0 else []
    return cache[opened]


#: why a trade's last target is what it is (written on each trade)
TARGET_FROM_AR = {"level": "المستوى التالي", "none_ahead": "لا مستوى أمامها: ثلاثة أضعاف"}


def _next_level_targets(targets: list, levels: list[float], side: int, entry: float, risk: float, cost: float, pad: float,
                        min_r: float) -> tuple[list | None, str | None]:
    """The owner's target (2026-10-23): the last target just before the next level ahead of the entry («قبله لا عليه»),
    the earlier targets as they are (the engine's method of 2026-10-19); no trade when that level leaves less than
    min_r after the cost -- (reward − cost) ÷ (risk + cost) ≥ min_r, the rule of 17/10. No level ahead: min_r."""
    ahead = [(lv - entry) * side for lv in levels if (lv - entry) * side > 0]
    if not ahead:
        return list(targets[:-1]) + [(min_r, targets[-1][1])], "none_ahead"
    reward = min(ahead) - pad
    if reward <= 0 or (reward - cost) / (risk + cost) < min_r:
        return None, None
    return list(targets[:-1]) + [(reward / risk, targets[-1][1])], "level"


def _triggers(facts: "Facts", spec: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """The owner's spearhead (2026-10-18, «حطّ بنية معهم»): every moment a structure or liquidity atom fired, with the
    side it points to -- {atom, frame, key: "signal", value: "bos", side_key: "m.break_side", buy: "above", sell: "below"}."""
    ts, sides = [], []
    for trg in spec:
        sig = facts.series(trg["atom"], trg["frame"], trg.get("key", "signal"))
        way = facts.series(trg["atom"], trg["frame"], trg["side_key"])
        if sig is None or way is None:
            raise SystemExit("إشارة الدخول غير موجودة في المخزن: %s %s %s" % (trg["atom"], trg["frame"], trg["side_key"]))
        t, v, f = sig
        vocab, wvocab = f.get("vocab") or [], way[2].get("vocab") or []
        fired = v == (vocab.index(trg["value"]) if trg["value"] in vocab else -9)
        up = wvocab.index(trg["buy"]) if trg["buy"] in wvocab else -9
        down = wvocab.index(trg["sell"]) if trg["sell"] in wvocab else -9
        side = np.where(way[1] == up, 1, np.where(way[1] == down, -1, 0))
        ok = fired & (side != 0)
        ts.append(t[ok])
        sides.append(side[ok])
    t, s = np.concatenate(ts), np.concatenate(sides)
    order = np.argsort(t, kind="stable")
    return t[order], s[order]


def _first_trigger(trig: tuple, side: int, m: float, within_s: float) -> float | None:
    """The first trigger in the trade's direction from the decision close m to m + within_s, or none."""
    t, s = trig[0], trig[1]
    a, b = int(np.searchsorted(t, m, side="left")), int(np.searchsorted(t, m + within_s, side="right"))
    hits = np.nonzero(s[a:b] == side)[0]
    return float(t[a + hits[0]]) if len(hits) else None


def _trigger_kind(trig: tuple, hit: float, side: int) -> str | None:
    """The trader level behind a trigger (the level triggers carry a third array), or none for an atom's signal."""
    if len(trig) < 3:
        return None
    t, s, kinds = trig
    a = int(np.searchsorted(t, hit, side="left"))
    while a < len(t) and t[a] == hit:
        if s[a] == side:
            return str(kinds[a])
        a += 1
    return None


# ── the trader's levels and his two scenarios (the owner's paper of 2026-10-23, «حط هدول مع سستم حي» then «يقاس») ─────────
#: Fixed at the opening of the asset's window from the past only (atom 124's shared code `shared.day_levels`, and the round
#: numbers, which only this tool has -- the live 124 is not touched before the second seal).
TRADER_LEVEL_AR = {"y_high": "أعلى الأمس", "y_low": "أدنى الأمس", "y_close": "إغلاق الأمس", "n_high": "أعلى الليل",
                   "n_low": "أدنى الليل", "w_high": "أعلى الأسبوع الماضي", "w_low": "أدنى الأسبوع الماضي",
                   "round": "رقم مستدير", "round_strong": "رقم مستدير قويّ"}
#: (every, the stronger every) in the asset's price -- the Nasdaq: «كلّ 100 نقطة، والأقوى كلّ 1,000». Each pair's step is
#: written here before its own measurement.
ROUND_STEP = {"USTEC": (100.0, 1000.0)}
SCENARIO_AR = {"break": "كسرٌ وثبات", "false": "كسرٌ كاذب"}
CANDLE_AR = {"M5": "الخمس دقائق", "M1": "الدقيقة"}


def trader_levels(symbol: str, t_open: float, m15: list, d1: list, price: float) -> list[tuple[str, float]]:
    """The trader's map at the window's opening: yesterday's session high, low and close, the night's high and low (from
    yesterday's close to today's opening), last week's high and low (the last full trading week before today -- the shared
    `prev_week` counts from the last closed day, which on a Monday is the week before last), and the two round numbers
    around the price."""
    from shared import day_levels
    lv = day_levels.levels(symbol, t_open, m15, d1)
    out: list[tuple[str, float]] = []
    for key, block, field in (("y_high", "yesterday", "high"), ("y_low", "yesterday", "low"), ("y_close", "yesterday", "close"),
                              ("n_high", "overnight", "high"), ("n_low", "overnight", "low")):
        v = (lv.get(block) or {}).get(field) if lv.get("available") else None
        if v is not None:
            out.append((key, float(v)))
    week = datetime.fromtimestamp(t_open, timezone.utc).date().isocalendar()[:2]
    groups: dict[tuple, list] = {}
    for row in d1:
        groups.setdefault(tuple(day_levels._trading_date(row[0]).isocalendar()[:2]), []).append(row)
    before = [k for k in groups if k < tuple(week)]
    if before:
        rows = groups[max(before)]
        out += [("w_high", max(r[2] for r in rows)), ("w_low", min(r[3] for r in rows))]
    step, strong = ROUND_STEP.get(symbol, (0.0, 0.0))
    if step and price > 0:
        below = math.floor(price / step) * step
        for v in (below, below + step):
            out.append(("round_strong" if strong and abs(v / strong - round(v / strong)) < 1e-9 else "round", float(v)))
    return out


def level_signals(close: np.ndarray, high: np.ndarray, low: np.ndarray, level: float, scenario: str) -> np.ndarray:
    """Per candle: +1 a buy signal at its close, -1 a sell, 0 none. The previous candles must be in the arrays.
    break («كسرٌ وثبات»): the candle closes beyond the level, the one before had not (buy: from at-or-below to above).
    false («كسرٌ كاذب»): price goes past the level against the trade for at most one candle and a candle closes back --
    buy: it was above, this candle dips below and closes above; or the one before closed below and this one closes above
    again, with the price above before it. The sell is the mirror (the owner's example: «سحب فوقه ثمّ رجع تحته»)."""
    sig = np.zeros(len(close), dtype=np.int8)
    if len(close) < 3:
        return sig
    c, h, l = close[2:], high[2:], low[2:]
    c1, c2 = close[1:-1], close[:-2]
    L = level
    if scenario == "break":
        buy = (c1 <= L) & (c > L)
        sell = (c1 >= L) & (c < L)
    else:
        buy = (c > L) & (((l < L) & (c1 > L)) | ((c1 < L) & (c2 > L)))
        sell = (c < L) & (((h > L) & (c1 < L)) | ((c1 > L) & (c2 < L)))
    sig[2:] = np.where(buy, 1, np.where(sell, -1, 0))
    return sig


def level_triggers(symbol: str, t0: float, t1: float, cfg: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every scenario signal at the trader's levels in each window of the asset over [t0, t1): (the candle's close, the
    side, the level's kind), in time order. A candle closing on two levels gives one signal per level."""
    from zoneinfo import ZoneInfo

    from shared import day_levels, market_clock, red_lines
    period = cfg.get("candle", "M5")
    ps = DIRECTION_PERIOD_S[period]
    scenario = cfg.get("scenario", "break")
    kinds_wanted = set(cfg.get("kinds") or TRADER_LEVEL_AR)
    bars = np.array(_bars_db(symbol, period, t0 - 7 * 86400, t1), dtype=float)
    m15 = _bars_db(symbol, "M15", t0 - 40 * 86400, t1)
    d1 = _bars_db(symbol, "D1", t0 - 60 * 86400, t1)
    m1 = np.array(_bars_db(symbol, "M1", t0 - 7 * 86400, t1), dtype=float)
    t15 = np.array([r[0] for r in m15]) + 900
    td1 = np.array([r[0] for r in d1]) + 86400
    ends = bars[:, 0] + ps if len(bars) else np.zeros(0)
    name = red_lines.session_of(symbol)
    zone = ZoneInfo(red_lines.SESSIONS[name][0]) if name in red_lines.SESSIONS else None
    ts, sides, kinds = [], [], []
    day = datetime.fromtimestamp(t0, timezone.utc).date() - timedelta(days=1)
    last = datetime.fromtimestamp(t1, timezone.utc).date()
    while day <= last:
        day += timedelta(days=1)
        if zone is not None:
            close_hm = red_lines.SESSIONS[name][2]
            probe = datetime(day.year, day.month, day.day, close_hm[0], close_hm[1], tzinfo=zone).timestamp() - 1
        else:
            probe = datetime(day.year, day.month, day.day, 23, 59, tzinfo=timezone.utc).timestamp()
        wins = day_levels.windows(probe, symbol, count=1)
        if not wins:
            continue
        t_open, t_close = wins[0]
        if not (t0 <= t_open < t1) or market_clock.no_trade_day(t_open + 60):
            continue
        k15, kd = int(np.searchsorted(t15, t_open, side="right")), int(np.searchsorted(td1, t_open, side="right"))
        j1 = int(np.searchsorted(m1[:, 0] + 60, t_open, side="right")) - 1 if len(m1) else -1
        if j1 < 0 or k15 == 0:
            continue
        price = float(m1[j1, 4])                                   # the last close before the window opens
        levels = [(k, v) for k, v in trader_levels(symbol, t_open, m15[max(0, k15 - 1600):k15], d1[max(0, kd - 140):kd], price)
                  if k in kinds_wanted]
        a, b = int(np.searchsorted(ends, t_open, side="right")), int(np.searchsorted(ends, t_close, side="right"))
        if b - a <= 0 or a < 2:
            continue
        c, h, l = bars[a - 2:b, 4], bars[a - 2:b, 2], bars[a - 2:b, 3]
        when = ends[a - 2:b]
        for k, v in levels:
            sig = level_signals(c, h, l, v, scenario)
            hit = np.flatnonzero(sig[2:]) + 2
            ts.extend(when[hit].tolist())
            sides.extend(sig[hit].tolist())
            kinds.extend([k] * len(hit))
    order = np.argsort(np.array(ts, dtype=float), kind="stable")
    return (np.array(ts, dtype=float)[order], np.array(sides, dtype=int)[order], np.array(kinds, dtype=object)[order])


def _perf_ok(conds: list[dict], done: list[dict], m: float) -> bool:
    """The combination's own results before this moment (Turkey day / ISO week / month), against the owner's conditions."""
    from zoneinfo import ZoneInfo
    local = datetime.fromtimestamp(m, timezone.utc).astimezone(ZoneInfo("Europe/Istanbul"))
    day, week, month = local.date().isoformat(), local.date().isocalendar()[:2], local.strftime("%Y-%m")
    vals = {"perf.day_pct": sum(t["pct"] for t in done if t["day"] == day),
            "perf.week_pct": sum(t["pct"] for t in done if date.fromisoformat(t["day"]).isocalendar()[:2] == week),
            "perf.month_pct": sum(t["pct"] for t in done if t["day"][:7] == month),
            "perf.last_pct": done[-1]["pct"] if done else 0.0,
            "perf.trades_today": float(sum(1 for t in done if t["day"] == day))}
    run = 0
    for t in reversed(done):
        if t["pct"] > 0:
            break
        run += 1
    vals["perf.losses_in_row"] = float(run)
    for c in conds:
        x, op, y = vals.get(c["key"]), c.get("op", ">"), c.get("value")
        if x is None:
            continue
        if op == "between":
            if not float(y[0]) <= x <= float(y[1]):
                return False
        elif not {"==": x == float(y), "!=": x != float(y), ">": x > float(y), ">=": x >= float(y), "<": x < float(y),
                  "<=": x <= float(y)}[op]:
            return False
    return True


def _session_ranges(sym, t0, t1, to_pips) -> dict[date, float]:
    con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    days = defaultdict(lambda: [float("-inf"), float("inf")])
    for ps, h, l in con.execute("select period_start, high, low from candles_history where symbol=? and period='H1' and "
                                "period_start>=? and period_start<?", (sym, t0, t1)):
        d = datetime.fromtimestamp(ps, timezone.utc).date()
        days[d][0], days[d][1] = max(days[d][0], h), min(days[d][1], l)
    con.close()
    return {d: to_pips(v[0] - v[1], sym) for d, v in days.items() if v[0] > v[1]}


def _ref(ranges: dict[date, float], m: float) -> float | None:
    d = datetime.fromtimestamp(m, timezone.utc).date()
    prev = sorted((x for x in ranges if x < d), reverse=True)[:5]
    vals = sorted(ranges[x] for x in prev)
    return vals[len(vals) // 2] if len(vals) >= 3 else None


def _stop(facts, cfg, sym, side, m, price, scale, from_pips) -> float | None:
    method = cfg.get("method", "structure")
    lo_p, hi_p = (float(x) for x in cfg.get("band", [15, 45]))
    lo, hi = from_pips(lo_p, sym) * scale, from_pips(hi_p, sym) * scale
    if method == "fixed":
        return price - side * from_pips(float(cfg.get("pips") or 20), sym) * scale
    if method == "atr":
        s = facts.series("153", cfg.get("atr_frame", "15m"), "m.atr")
        if s is None:
            return None
        vals, ok = Facts.at(s[0], s[1], np.array([m]), None)
        return price - side * float(vals[0]) * float(cfg.get("atr_mult") or 1.5) if ok[0] and vals[0] > 0 else None
    pad = from_pips(float(cfg.get("pad") or 1.0), sym) * scale
    nearest = None
    # ١٩/١٠ (المالك: «الوقف خلف قاع دقيقة»): إطار القاع/القمّة يُختار، والافتراض 5د ثمّ 15د ثمّ دقيقة.
    for fr in cfg.get("frames") or STOP_FRAMES:
        s = facts.series("202", fr, "m.swing_low" if side > 0 else "m.swing_high")
        if s is None:
            continue
        vals, ok = Facts.at(s[0], s[1], np.array([m]), None)
        if not ok[0] or not np.isfinite(vals[0]):
            continue
        stop = float(vals[0]) - pad if side > 0 else float(vals[0]) + pad
        risk = (price - stop) * side
        if lo <= risk <= hi:
            return stop
        if risk > 0 and (nearest is None or risk < nearest):
            nearest = risk
    if method == "structure_clamp":
        # ١٨/١٠ (المالك: «لازم نوصل 1000 صفقة»): لا قمّة/قاع داخل الحدّين ⟸ الوقف يُشدّ إلى أقرب حدٍّ بدل ترك الصفقة —
        # أقرب قاعٍ أقرب من الأدنى ⟸ الأدنى (خلفه)، وأبعد من الأعلى ⟸ الأعلى.
        return price - side * (lo if nearest is None or nearest < lo else hi)
    return None


def _record(tr: Trade, spec, to_pips) -> dict[str, Any]:
    r = tr.result_r()
    from zoneinfo import ZoneInfo
    local = datetime.fromtimestamp(tr.at, timezone.utc).astimezone(ZoneInfo("Europe/Istanbul"))
    return {"opened": local.strftime("%Y-%m-%d %H:%M"), "day": local.date().isoformat(), "hour": local.hour,
            "weekday": local.weekday(), "side": "شراء" if tr.side > 0 else "بيع", "entry": round(tr.entry, 2),
            "stop": round(tr.stop0, 2), "risk_pips": round(to_pips(tr.risk, spec["symbol"]), 1), "reached": tr.stage,
            "exit": EXIT_AR.get(tr.exit, tr.exit), "minutes": round((tr.exit_at - tr.at) / 60.0, 1),
            "mfe_r": round(tr.mfe, 2), "mae_r": round(tr.mae, 2), "r": round(r, 3),
            "pct": round(r * float(spec.get("risk_pct") or 1.0), 3), "target_r": round(float(tr.targets[-1][0]), 2)}


# ── the report ──────────────────────────────────────────────────────────────────────────────────────────────
def stats(rows: list[dict], n_targets: int) -> dict[str, Any]:
    pct = [t["pct"] for t in rows]
    wins, losses = [p for p in pct if p > 0], [p for p in pct if p <= 0]
    curve, peak, low, dd, run_w, run_l, best_w, best_l = 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0
    for p in pct:
        curve += p
        peak, low = max(peak, curve), min(low, curve)
        dd = max(dd, peak - curve)
        run_w, run_l = (run_w + 1, 0) if p > 0 else (0, run_l + 1)
        best_w, best_l = max(best_w, run_w), max(best_l, run_l)
    daily = defaultdict(float)
    for t in rows:
        daily[t["day"]] += t["pct"]
    dv = list(daily.values())
    sharpe = (np.mean(dv) / np.std(dv) * math.sqrt(252)) if len(dv) > 1 and np.std(dv) > 0 else None
    out = {"صفقات": len(rows), "رابحة": len(wins), "خاسرة": len(losses),
           "نسبة_الربح": round(100 * len(wins) / len(rows), 1) if rows else 0.0,
           "صافي_٪": round(sum(pct), 2), "إجماليّ_الربح_٪": round(sum(wins), 2), "إجماليّ_الخسارة_٪": round(sum(losses), 2),
           "معامل_الربح": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None,
           "متوسّط_الصفقة_R": round(float(np.mean([t["r"] for t in rows])), 3) if rows else 0.0,
           "أكبر_ربح_٪": round(max(pct), 2) if pct else 0.0, "أكبر_خسارة_٪": round(min(pct), 2) if pct else 0.0,
           "متوسّط_الرابحة_٪": round(float(np.mean(wins)), 2) if wins else 0.0,
           "متوسّط_الخاسرة_٪": round(float(np.mean(losses)), 2) if losses else 0.0,
           "أطول_سلسلة_ربح": best_w, "أطول_سلسلة_خسارة": best_l, "أكبر_تراجع_٪": round(dd, 2),
           "أعمق_نزول_تحت_البداية_٪": round(low, 2),
           "معامل_التعافي": round(sum(pct) / dd, 2) if dd > 0 else None,
           "شارب_سنويّ": round(float(sharpe), 2) if sharpe is not None else None,
           "متوسّط_المدّة_دقيقة": round(float(np.mean([t["minutes"] for t in rows])), 1) if rows else 0.0,
           "متوسّط_أقصى_ربح_داخل_الصفقة_R": round(float(np.mean([t["mfe_r"] for t in rows])), 2) if rows else 0.0,
           "متوسّط_أقصى_ضدّيّة_R": round(float(np.mean([t["mae_r"] for t in rows])), 2) if rows else 0.0,
           "وقف_قبل_أيّ_هدف": sum(1 for t in rows if t["reached"] == 0 and t["exit"] == EXIT_AR["stop"])}
    for k in range(1, n_targets + 1):
        out["بلغ_الهدف_%d" % k] = sum(1 for t in rows if t["reached"] >= k)
    for side in ("شراء", "بيع"):
        sub = [t for t in rows if t["side"] == side]
        out["%s_صفقات" % side] = len(sub)
        out["%s_نسبة_الربح" % side] = round(100 * sum(1 for t in sub if t["pct"] > 0) / len(sub), 1) if sub else 0.0
        out["%s_صافي_٪" % side] = round(sum(t["pct"] for t in sub), 2)
    exits = defaultdict(int)
    for t in rows:
        exits[t["exit"]] += 1
    out["الخروج"] = dict(exits)
    ends: dict[str, list] = {}
    for t in rows:
        r = int(t["reached"])
        if t["exit"] == EXIT_AR["stop"] and r == 0:
            k = "ضربت الوقف قبل أيّ هدف"
        elif t["exit"] == EXIT_AR["target"] or r >= n_targets:
            k = "بلغت الهدف الأخير"
        elif t["exit"] == EXIT_AR["stop"]:
            k = "بلغت الهدف %d ثمّ رجعت إلى وقفها المرفوع" % r
        else:
            k = "أُغلقت عند %s بعد الهدف %d" % (t["exit"], r) if r else "أُغلقت عند %s قبل أيّ هدف" % t["exit"]
        ends.setdefault(k, [0, 0.0])
        ends[k][0] += 1
        ends[k][1] += t["r"]
    out["النهايات"] = {k: {"صفقات": v[0], "متوسّط_R": round(v[1] / v[0], 2)} for k, v in ends.items()}
    return out


def tables(rows: list[dict], n_targets: int) -> dict[str, Any]:
    months, hours, weekdays = [], defaultdict(list), defaultdict(list)
    for t in rows:
        hours[t["hour"]].append(t["pct"])
        weekdays[t["weekday"]].append(t["pct"])
    # ١٩/١٠ (المالك: «بدّي حساب عن كلّ شهر»): الحساب في آخر كلّ شهر وأدنى ما بلغه حتّى آخره، من أوّل الفترة.
    run_end, run_low, cum, low = {}, {}, 0.0, 0.0
    for t in sorted(rows, key=lambda x: x["opened"]):
        cum += t["pct"]
        low = min(low, cum)
        run_end[t["day"][:7]], run_low[t["day"][:7]] = cum, low
    for key in sorted({t["day"][:7] for t in rows}):
        mrows = [t for t in rows if t["day"][:7] == key]
        weeks = defaultdict(float)
        for t in mrows:
            weeks[date.fromisoformat(t["day"]).isocalendar()[1]] += t["pct"]
        s = stats(mrows, n_targets)
        months.append({"الشهر": key, "صفقات": s["صفقات"], **{"هدف_%d" % k: s["بلغ_الهدف_%d" % k] for k in range(1, n_targets + 1)},
                       "وقف": s["وقف_قبل_أيّ_هدف"], "نسبة_الربح": s["نسبة_الربح"], "عائد_٪": s["صافي_٪"],
                       "أكبر_تراجع_٪": s["أكبر_تراجع_٪"], "الأسابيع": [round(weeks[w], 2) for w in sorted(weeks)],
                       "الحساب_٪": round(run_end[key], 2), "أدنى_حتّى_الآن_٪": round(run_low[key], 2)})
    days = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    curve, points = 0.0, []
    for t in rows:
        curve += t["pct"]
        points.append([t["opened"], round(curve, 3)])
    return {"الأشهر": months,
            "الساعات": {h: {"صفقات": len(v), "صافي_٪": round(sum(v), 2)} for h, v in sorted(hours.items())},
            "الأيّام": {days[d]: {"صفقات": len(v), "صافي_٪": round(sum(v), 2)} for d, v in sorted(weekdays.items())},
            "منحنى_الرصيد": points}


REASON_AR = {"outside_window_or_first_minutes": "خارج نافذة الأصل أو في أوّل دقائق الجلسة", "no_direction": "بلا جهة",
             "no_stop": "لا وقف صالح داخل الحدّين", "busy_or_waiting": "صفقة مفتوحة أو انتظار بعد صفقة",
             "not_enough_time": "الوقت لا يكفي للهدف الأخير (قانون ما قبل ٢٥/١٠)",
             "last_hour": "الساعة الأخيرة من نافذة الأصل — لا صفقة جديدة (القانون 21)",
             "news_window": "نافذة خبر", "max_per_day": "بلغ أقصى صفقات اليوم",
             "performance_condition": "شرط الأداء السابق", "no_trigger": "لا إشارة دخول في جهتها خلال الانتظار",
             "trigger_outside_window": "الإشارة جاءت خارج نافذة الأصل", "no_trade_day": "يوم عطلة أو إغلاقٍ مبكر",
             "target_below_three": "المستوى التالي أقرب من ثلاثة أضعاف بعد الكلفة",
             "stop_below_floor": "وقفٌ أقصر من حارس أدنى الوقف في الحيّ (555)"}
TOKEN_AR = {
    "m": "", "ema": "المتوسّط الأسّيّ", "distance": "البُعد", "slope": "الميل", "fast": "السريع", "slow": "البطيء", "value": "القيمة",
    "ratio": "النسبة", "atr": "متوسّط المدى الحقيقيّ", "pct": "٪", "swing": "", "high": "القمّة", "low": "القاع", "close": "الإغلاق",
    "price": "السعر", "signal": "الإشارة", "status": "الحالة", "direction": "الجهة", "efficiency": "الكفاءة", "roc": "معدّل التغيّر",
    "impulse": "الاندفاع", "persistence": "الثبات", "body": "الجسم", "wick": "الذيل", "upper": "العلويّ", "lower": "السفليّ",
    "pattern": "النمط", "gap": "الفجوة", "filled": "امتلأت", "session": "الجلسة", "now": "الآن", "hour": "الساعة",
    "correlation": "الارتباط", "speed": "السرعة", "baseline": "الأساس", "detected": "اكتُشف", "break": "الكسر", "side": "الجهة",
    "level": "المستوى", "shift": "التحوّل", "type": "النوع", "confirmations": "التأكيدات", "mean": "المتوسّط", "median": "الوسيط",
    "std": "الانحراف المعياريّ", "window": "النافذة", "count": "العدد", "z": "زد", "score": "الدرجة", "range": "المدى",
    "position": "الموقع", "hurst": "هيرست", "band": "النطاق", "trend": "الاتّجاه", "frames": "", "readings": "القراءة",
    "agree": "متّفقة", "dow": "داو", "legs": "الموجات", "retracement": "الاسترداد", "structure": "الهيكل", "secondary": "الثانويّ",
    "four": "الأربع", "hours": "ساعات", "primary": "الأساسيّ", "sub": "الفرعيّ", "groups": "المجموعة", "in": "في",
    "correction": "التصحيح", "zone": "النطاق", "volume": "الحجم", "up": "الصاعدة", "vs": "مقابل", "down": "الهابطة",
    "last": "آخر", "since": "منذ", "highs": "القمم", "lows": "القيعان", "available": "متاح", "confirmation": "التأكيد",
    "all": "كلّها", "same": "نفسها", "net": "الصافي", "move": "الحركة", "total": "المجموع", "path": "المسار", "deviation": "الانحراف",
    "positive": "الموجبة", "negative": "السالبة", "return": "العائد", "lookback": "النظرة للخلف", "prominence": "البروز",
    "pool": "المجمّع", "taken": "أُخذ", "returned": "عاد", "seconds": "ثوانٍ", "beyond": "تجاوز", "top": "الأعلى", "bottom": "الأسفل",
    "drift": "الانجراف", "skew": "الالتواء", "kurtosis": "التفلطح", "q1": "الربيع الأوّل", "q3": "الربيع الثالث",
    "multiplier": "المضاعف", "bins": "الفئات", "latest": "الأخيرة", "bin": "الفئة", "modal": "الأكثر تكرارًا", "max": "الأعلى",
    "min": "الأدنى", "older": "الأقدم", "recent": "الأحدث", "vol": "التذبذب", "intercept": "التقاطع", "threshold": "العتبة",
    "frequency": "التكرار", "reference": "المرجع", "points": "النقاط", "anchor": "المرجع", "cash": "السوق النقديّ", "open": "الافتتاح",
    "month": "الشهر", "quarter": "الربع", "day": "اليوم", "of": "", "is": "", "start": "البداية", "end": "النهاية",
    "trading": "تداول", "net_move": "صافي الحركة", "emerging": "ناشئ", "phase": "الطور",
}


def field_label(key: str) -> str:
    """تسمية عربيّة لحقلٍ تقنيّ — كلمةً كلمة؛ ما لا ترجمة له يبقى كما هو."""
    words = []
    for part in key.replace(".", "_").split("_"):
        if not part:
            continue
        ar = TOKEN_AR.get(part.lower())
        if ar is None:
            words.append(part)
        elif ar:
            words.append(ar)
    return " ".join(words) or key


def describe(spec: dict[str, Any], names: dict[str, str]) -> str:
    def nm(a):
        return (names.get(str(a)) or str(a)).replace("_", " ")
    parts = []
    d = spec["direction"]
    parts.append("الجهة من %s %s" % (nm(d["atom"]), d["frame"]) if d.get("source") == "fact" else "جهة عشوائيّة")
    for c in spec["conditions"]:
        parts.append("%s %s" % (nm(c["atom"]), c["frame"]))
    return " + ".join(parts)


def safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip()[:150]


def write(result: dict[str, Any], names: dict[str, str], root: Path | None = None) -> Path:
    spec = result["spec"]
    n_t = len(spec["targets"])
    title = spec.get("name") or "%s — %s — %s إلى %s" % (describe(spec, names), SYMBOL_AR.get(spec["symbol"], spec["symbol"]),
                                                        spec["from"], spec["to"])
    today = datetime.now().strftime("%Y-%m-%d")
    base = root or OUT_ROOT / today                        # `root`: a measurement that keeps its runs in its own folder
    folder = base / safe(title)
    if folder.exists():
        folder = base / safe("%s (%s)" % (title, datetime.now().strftime("%H-%M-%S")))
    folder.mkdir(parents=True, exist_ok=True)
    summary = {"kind": "combo", "الاسم": title, "المجلّد": str(folder), "ثوانٍ": result["seconds"],
               "لحظات_القرار": result["moments"], "مرشّحة_بعد_الشروط": result["candidates"],
               "استُبعدت_بالشروط": result["filtered"], "تُخطّيت": result["skipped"], "النتائج": {}}
    with (folder / "الصفقات.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = None
        for lb, rows in result["trades"].items():
            summary["النتائج"][lb] = {"الإحصاء": stats(rows, n_t), **tables(rows, n_t)}
            for t in rows:
                row = {"المجموعة": lb, **t}
                if writer is None:
                    writer = csv.DictWriter(fh, fieldnames=list(row), extrasaction="ignore")
                    writer.writeheader()
                writer.writerow(row)
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "الاختبار.md").write_text(_test_md(title, spec, result, names), encoding="utf-8")
    summary["المخاطرة"] = float(spec.get("risk_pct") or 1.0)
    summary["رأس_المال"] = float(spec.get("balance") or 10000.0)
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "النتيجة.md").write_text(_result_md(title, summary, n_t, summary["رأس_المال"]), encoding="utf-8")
    # ٢٠٢٦-١٠-٢٣ (القانون 7: «القياس يعمل على حسابٍ افتراضيّ بالمعادلة نفسها والحدود نفسها»، ويُعدّ كم مرّة كان الحساب سيسقط):
    # المعادلة الواحدة `shared/account_limits.simulate` بإعدادات المالك (أو قيمه الأولى) — مخاطرة الزوج الثابتة وحدّ الزوج والحدّ
    # الشامل والتراجع الكلّيّ.
    limits = spec.get("account_limits")
    lines = ["", "## الحساب الافتراضيّ بحدود المالك (القوانين 7–10)", ""]
    for lb, rows in result["trades"].items():
        trades = [(datetime.strptime(t["opened"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=3))).timestamp()
                   + float(t.get("minutes") or 0) * 60, spec["symbol"], float(t["r"])) for t in rows]
        sim = _account_limits.simulate(trades, limits)
        summary["النتائج"][lb]["الحساب_الافتراضيّ"] = sim
        lines.append("- **%s:** صفقات محسوبة %d · مُسقطة بالحدود %d · سقوط الحساب (التراجع الكلّيّ) **%d** مرّة · أيّام وقفها الحدّ "
                     "الشامل %d · وقفات حدّ الزوج %d · أسوأ خسارة يوم %.2f$ · أدنى حقوق %.2f$ · الصافي %.2f$"
                     % (lb, sim["taken"], sim["skipped"], sim["account_falls"], sim["daily_stops"], sim["pair_stops"],
                        sim["max_day_loss"], sim["lowest_equity"], sim["net"]))
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    with (folder / "النتيجة.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    day_comparison(folder.parent)
    return folder


def _test_md(title, spec, result, names) -> str:
    def nm(a):
        return (names.get(str(a)) or str(a)).replace("_", " ")
    L = ["# %s" % title, "", "## ما اختُبر", "",
         "- **الرمز:** %s · **الفترة:** %s إلى %s · **البيانات:** شموع الدقيقة المحفوظة من سي‑تريدر، وحقائق الذرّات الحقيقيّة من مخزن الحقائق"
         % (SYMBOL_AR.get(spec["symbol"], spec["symbol"]), spec["from"], spec["to"]),
         "- **لحظة القرار:** كلّ إغلاق %s" % spec["decision_frame"]]
    d = spec["direction"]
    if spec.get("owner_method"):
        L.append("- **طريقة المالك — مربّعات الدقيقة:** %s · الدخول لحظة كسر المربّع في جهة بنية الدقيقة (قاعٌ أعلى للشراء، قمّةٌ أدنى للبيع) · الوقف خلف الطرف الآخر من المربّع · الأثلاث 1 و2 و3 أضعاف" % spec["owner_method"])
    L.append("- **الجهة:** %s" % ("%s · إطار %s · %s" % (nm(d["atom"]), d["frame"], field_label(d["key"])) if d.get("source") == "fact" else "%s · %s" % (VIRTUAL[d["atom"]]["name"], VIRTUAL[d["atom"]]["fields"].get(d["key"], d["key"])) if d.get("source") == "virtual" else "عشوائيّة"))
    L.append("- **الشروط (كلّها معًا):**")
    for c in spec["conditions"] or [{"atom": "—", "frame": "", "key": "لا شروط", "op": "", "value": ""}]:
        L.append("  - %s · إطار %s · %s %s %s" % (nm(c["atom"]), c.get("frame", ""), field_label(c.get("key", "")), c.get("op", ""),
                                               json.dumps(c.get("value"), ensure_ascii=False) if c.get("op") not in ("same_way", "") else "(في جهة الصفقة)"))
    en = spec.get("entry") or {}
    if en.get("triggers"):
        L.append("- **إشارة الدخول (رأس الحربة):** أوّل ما يأتي في جهة الصفقة خلال %s دقيقة من لحظة القرار، والدخول بإغلاق دقيقتها:" % (
            en.get("within_min") or 15))
        for tg in en["triggers"]:
            L.append("  - %s · إطار %s · %s = %s (الشراء %s · البيع %s)" % (nm(tg["atom"]), tg["frame"], field_label(tg.get("key", "signal")),
                                                                     tg["value"], tg["buy"], tg["sell"]))
    elif en.get("levels"):
        lv = en["levels"]
        L.append("- **رأس الحربة — مستويات المتداول:** %s على شمعة %s، أوّل إشارةٍ في جهة الصفقة خلال %s دقيقة من لحظة القرار،"
                 " والدخول بإغلاق شمعتها. المستويات تُثبَّت عند افتتاح نافذة الأصل من الماضي وحده: %s" % (
                     SCENARIO_AR.get(lv.get("scenario"), lv.get("scenario")), CANDLE_AR.get(lv.get("candle"), lv.get("candle")),
                     en.get("within_min") or 15, " · ".join(TRADER_LEVEL_AR[k] for k in (lv.get("kinds") or TRADER_LEVEL_AR))))
    else:
        L.append("- **الدخول:** بإغلاق لحظة القرار نفسها")
    st = spec["stop"]
    L.append("- **الوقف:** %s" % {"structure": "خلف آخر قاع/قمّة (الذرّة 202) على %s، بين %s و%s بِب" % ((" ثمّ ".join(st.get("frames") or STOP_FRAMES),) + tuple(st.get("band", [15, 45]))),
                                 "structure_clamp": "خلف آخر قاع/قمّة (الذرّة 202) بين %s و%s بِب، وإلّا يُشدّ إلى أقرب حدّ" % tuple(st.get("band", [15, 45])),
                                 "fixed": "ثابت %s بِب" % st.get("pips"), "atr": "%s × متوسّط المدى الحقيقيّ على %s" % (st.get("atr_mult"), st.get("atr_frame"))}.get(st.get("method"), st.get("method")))
    if spec.get("live_stop_floor", True):
        from shared.trade_setup import min_stop_pips
        L.append("- **حارس أدنى الوقف كالحيّ (555):** يُردّ كلّ وقفٍ أقصر من %g بِب" % min_stop_pips(spec["symbol"]))
    L.append("- **الأهداف:** " + " · ".join("%s× المخاطرة يُغلق %s٪" % (x["r"], x["close_pct"]) for x in spec["targets"]))
    tf = spec.get("target_from") or {}
    if tf.get("method") == "next_level":
        L.append("- **الهدف الأخير عند المستوى التالي، قبله لا عليه:** أقرب مستوى أمام الدخول في جهة الصفقة (%s)، قبله بـ%s بِب. ولا صفقة إن"
                 " كان (العائد − الكلفة) ÷ (المخاطرة + الكلفة) أقلّ من %s. ولا مستوى أمامها = %s أضعاف." % (
                     "خريطة المتداول عند افتتاح النافذة: " + " · ".join(TRADER_LEVEL_AR.values()) if tf.get("map") else
                     " · ".join((["مستويات الذرّة 124 لحظة القرار"] if tf.get("levels", True) else [])
                                + (["الرقمان المستديران عند الافتتاح"] if tf.get("round", True) else [])),
                     tf.get("pad_pips"), tf.get("min_r") or 3, tf.get("min_r") or 3))
    L.append("- **حماية الصفقة:** التعادل بعد الهدف %s · ورفع الوقف إلى %s× بعد الهدف %s" % (spec.get("breakeven_after") or "—",
                                                                                  spec.get("trail_to_r"), spec.get("trail_after") or "—"))
    n = spec["news"]
    L.append("- **الأخبار:** %s" % ("ألوان %s لعملات %s، لا دخول %s دقيقة قبل و%s بعد، ويُغلق المفتوح قبله" % (
        "·".join(n.get("colors") or []), "·".join(n.get("currencies") or []), n.get("before_min"), n.get("after_min")) if n.get("on") else "بلا مرشّح"))
    L.append("- **الوقت:** نوافذ الأصول وخطوطها الحمراء %s · أوّل %s دقيقة ممنوعة · انتظار %s دقيقة بعد كلّ صفقة · لا صفقة جديدة في الساعة"
             " الأخيرة (القانون 21) %s" % (
        "مفعّلة" if spec["session"].get("use_red_lines", True) else "معطّلة", spec["session"].get("first_minutes"),
        spec.get("wait_min"), "مفعّل" if spec.get("time_enough") else "معطّل"))
    L.append("- **المخاطرة:** %s٪ للصفقة · الكلفة %s بِب%s" % (spec.get("risk_pct"), spec.get("cost_pips"),
                                                           " (بنسبة السعر)" if spec.get("scale_with_price", True) else ""))
    L += ["", "## كيف جرى", "", "- الزمن: %s ثانية · لحظات القرار: %d · بقيت بعد الشروط: %d" % (
        result["seconds"], result["moments"], result["candidates"]), "- ما استبعدته الشروط:"]
    for k, v in result["filtered"].items():
        if k.startswith("condition ") or k.startswith("same_way "):
            _, a, f_or_k, *rest = k.split(" ")
            k = "شرط %s %s" % (nm(a), " ".join([f_or_k] + rest))
        L.append("  - %s: %d" % (REASON_AR.get(k, k), v))
    L.append("- ما تُخطّي عند التنفيذ:")
    for lb, sk in result["skipped"].items():
        L.append("  - %s: %s" % (lb, " · ".join("%s %d" % (REASON_AR.get(k, k), v) for k, v in sk.items()) or "لا شيء"))
    L.append("- مخزن الحقائق: `%s`" % result["store"])
    return "\n".join(L) + "\n"


def _result_md(title, summary, n_t, balance=10000.0) -> str:
    """ملفّ النتيجة بشكل المالك (١٧/١٠: «هدول جداول بدّي أشوفها بعد كلّ اختبار … ما بدّي أسألك عنها»)."""
    res = summary["النتائج"]
    combo = res.get("التوليفة", {}).get("الإحصاء", {})
    ref = res.get("مرجع: جهة عشوائيّة", {}).get("الإحصاء", {})
    money = lambda pct: "{:+,.0f}$".format(pct * balance / 100.0)
    L = ["# النتيجة — %s" % title, "",
         "المخاطرة %s٪ من رأس المال الأوّل في كلّ صفقة، والكلفة مخصومة. «على %s$» = النسبة مضروبةً في رأس المال." % (
             summary.get("المخاطرة", 1.0), "{:,.0f}".format(balance)), "",
         "## 1. الخلاصة", "",
         "| | صفقات | رابحة من 100 | صافي السنة | معامل الربح | أكبر تراجع | أعمق نزول تحت البداية |",
         "|---|---|---|---|---|---|---|"]
    for lb in res:
        s = res[lb]["الإحصاء"]
        L.append("| %s | %d | %s | %+.1f٪ | %s | %.0f٪ | %+.0f٪ |" % (lb, s["صفقات"], s["نسبة_الربح"], s["صافي_٪"],
                 s["معامل_الربح"] if s["معامل_الربح"] is not None else "—", s["أكبر_تراجع_٪"], s["أعمق_نزول_تحت_البداية_٪"]))
    L += ["", "## 2. الأهداف والوقف", "", "الأهداف متداخلة: كلّ صفقة بلغت الثاني بلغت الأوّل قبله.", "",
          "| | صفقات | %s | ضربت الوقف قبل أيّ هدف |" % " | ".join("بلغت الهدف %d" % k for k in range(1, n_t + 1)),
          "|---|---|" + "---|" * n_t + "---|"]
    for lb in res:
        s = res[lb]["الإحصاء"]
        L.append("| %s | %d | %s | %d |" % (lb, s["صفقات"], " | ".join(str(s["بلغ_الهدف_%d" % k]) for k in range(1, n_t + 1)),
                                         s["وقف_قبل_أيّ_هدف"]))
    L += ["", "## 3. كيف انتهت صفقات التوليفة", "", "| النهاية | صفقات | ما ربحته الصفقة في المتوسّط |", "|---|---|---|"]
    for k, v in sorted(combo.get("النهايات", {}).items(), key=lambda kv: -kv[1]["صفقات"]):
        L.append("| %s | %d | %+.2f من المخاطرة |" % (k, v["صفقات"], v["متوسّط_R"]))
    L += ["", "## 4. الأشهر (التوليفة)", "",
          "| الشهر | صفقات | %s | وقف | العائد | الحساب آخر الشهر | أدنى ما بلغه حتّى الآن | الأسابيع |" % " | ".join("الهدف %d" % k for k in range(1, n_t + 1)),
          "|---|---|" + "---|" * n_t + "---|---|---|---|---|"]
    for m in res.get("التوليفة", {}).get("الأشهر", []):
        low = m.get("أدنى_حتّى_الآن_٪", 0.0)
        L.append("| %s | %d | %s | %d | %+.1f٪ | %s$ | %s | %s |" % (
            m["الشهر"], m["صفقات"], " | ".join(str(m["هدف_%d" % k]) for k in range(1, n_t + 1)), m["وقف"], m["عائد_٪"],
            "{:,.0f}".format(balance * (1 + m.get("الحساب_٪", 0.0) / 100)),
            "ربح مباشرة" if low >= 0 else "{:,.0f}$ ({:.1f}٪)".format(balance * (1 + low / 100), low),
            " · ".join("%+.1f" % w for w in m["الأسابيع"])))
    L += ["", "## 5. المال", "", "| | النسبة | على %s$ |" % "{:,.0f}".format(balance), "|---|---|---|"]
    if combo:
        L += ["| مجموع الصفقات الرابحة | %+.1f٪ | %s |" % (combo["إجماليّ_الربح_٪"], money(combo["إجماليّ_الربح_٪"])),
              "| مجموع الصفقات الخاسرة | %+.1f٪ | %s |" % (combo["إجماليّ_الخسارة_٪"], money(combo["إجماليّ_الخسارة_٪"])),
              "| **الصافي آخر الفترة** | **%+.1f٪** | **%s** |" % (combo["صافي_٪"], money(combo["صافي_٪"]))]
        if ref:
            L.append("| الجهة العشوائيّة بالقوانين نفسها | %+.1f٪ | %s |" % (ref["صافي_٪"], money(ref["صافي_٪"])))
    L += ["", "## 6. أين الضعف (أرقام لا حكم)", ""]
    if combo.get("صفقات"):
        n = combo["صفقات"]
        L.append("- الهدف الأخير بلغته %d من %d صفقة (%.0f من 100)." % (combo["بلغ_الهدف_%d" % n_t], n, 100 * combo["بلغ_الهدف_%d" % n_t] / n))
        L.append("- ضربت الوقف كاملًا %d صفقة (%.0f من 100)." % (combo["وقف_قبل_أيّ_هدف"], 100 * combo["وقف_قبل_أيّ_هدف"] / n))
        months = res["التوليفة"]["الأشهر"]
        win = [m["الشهر"][5:] for m in months if m["عائد_٪"] > 0]
        lose = [m["الشهر"][5:] for m in months if m["عائد_٪"] <= 0]
        L.append("- أشهرٌ رابحة %d: %s · وخاسرة %d: %s." % (len(win), "، ".join(win) or "—", len(lose), "، ".join(lose) or "—"))
        if months:
            worst = min(months, key=lambda m: m["عائد_٪"])
            L.append("- أسوأ شهر %s (%+.1f٪): وقفٌ كامل %d من %d صفقة." % (worst["الشهر"][5:], worst["عائد_٪"], worst["وقف"], worst["صفقات"]))
        if ref:
            L.append("- الفرق عن الجهة العشوائيّة: %+.1f نقطة في الفترة." % (combo["صافي_٪"] - ref["صافي_٪"]))
    else:
        L.append("- لا صفقة: الشروط لم تجتمع في الفترة.")
    L += ["", "---", "", "## التفاصيل الكاملة", ""]
    for lb, r in res.items():
        s = r["الإحصاء"]
        L += ["### %s" % lb, "", "| البند | القيمة |", "|---|---|"]
        L += ["| %s | %s |" % (k.replace("_", " "), json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v)
              for k, v in s.items() if k != "النهايات"]
        L += ["", "**الأيّام:** " + " · ".join("%s %d صفقة %+.2f٪" % (d, v["صفقات"], v["صافي_٪"]) for d, v in r["الأيّام"].items()),
              "", "**الساعات (تركيا):** " + " · ".join("%s:00 %d صفقة %+.2f٪" % (h, v["صفقات"], v["صافي_٪"]) for h, v in r["الساعات"].items()), ""]
    return "\n".join(L)


def day_comparison(day_folder: Path) -> None:
    """«مقارنة اختبارات اليوم.md» — كلّ اختبارات اليوم في جدولٍ واحد مرتّبٍ بالصافي، يتجدّد بعد كلّ اختبار."""
    rows = []
    for f in sorted(day_folder.glob("*/summary.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        res = s.get("النتائج", {})
        c, r = res.get("التوليفة", {}).get("الإحصاء", {}), res.get("مرجع: جهة عشوائيّة", {}).get("الإحصاء", {})
        if not c:
            continue
        n_t = sum(1 for k in c if k.startswith("بلغ_الهدف_"))
        rows.append((c.get("صافي_٪", 0.0), s.get("الاسم", f.parent.name), c, r, n_t))
    rows.sort(key=lambda x: -x[0])
    L = ["# مقارنة اختبارات يوم %s" % day_folder.name, "", "مرتّبة بالصافي، من الأعلى. تتجدّد وحدها بعد كلّ اختبار.", "",
         "| الاختبار | صفقات | الهدف 1 | الهدف 2 | الهدف 3 | وقف كامل | نزل تحت البداية قبل الربح | الصافي | العشوائيّ | رابحة من 100 | معامل الربح | أكبر تراجع |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for net, name, c, r, n_t in rows:
        dip = c.get("أعمق_نزول_تحت_البداية_٪", 0.0)
        # ١٩/١٠ (قانون المالك): صفقات · هدف 1/2/3 · وقف · كم نزل قبل الربح أو ربح مباشرة · الصافي — ثمّ ما بعدها.
        L.append("| %s | %d | %s | %s | %s | %d | %s | %+.1f٪ | %s | %s | %s | %.0f٪ |" % (
            name, c["صفقات"], c.get("بلغ_الهدف_1", "—"), c.get("بلغ_الهدف_2", "—"), c.get("بلغ_الهدف_3", "—"),
            c["وقف_قبل_أيّ_هدف"], "ربح مباشرة" if dip >= 0 else "%.1f٪" % dip, net, ("%+.1f٪" % r["صافي_٪"]) if r else "—",
            c["نسبة_الربح"], c["معامل_الربح"] if c["معامل_الربح"] is not None else "—", c["أكبر_تراجع_٪"]))
    (day_folder / "مقارنة اختبارات اليوم.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ── the grid (owner, 2026-10-18: «كمّل لنشوف» — many combinations on every pair and two years, one folder) ──────────
def _grid_spec(cfg: dict[str, Any], combo: tuple, sym: str, y0: str, y1: str) -> dict[str, Any]:
    spec = json.loads(json.dumps(cfg["base"]))
    for axis in combo:
        for k, v in axis["set"].items():
            if k == "conditions":
                spec["conditions"] = list(spec.get("conditions") or []) + list(v)
            elif isinstance(v, dict) and isinstance(spec.get(k), dict):
                spec[k] = {**spec[k], **v}
            else:
                spec[k] = v
    per = cfg.get("per_symbol", {}).get(sym, {})
    spec.update({"symbol": sym, "from": y0, "to": y1, "store": str(Path(cfg["store_root"]) / sym / ("%s_%s" % (y0, y1)))})
    if "cost" in per:
        spec["cost_pips"] = per["cost"]
    spec["stop"] = {**(spec.get("stop") or {}), **{k: per[k] for k in ("band", "pad") if k in per}}
    return merged(spec)


def grid(cfg: dict[str, Any], log=print) -> Path:
    """Every combination of the axes on every symbol and year: net % per cell, the random reference beside it, and a
    table ranked by how many symbol-years each combination wins -- one folder, the number of attempts declared."""
    import itertools
    began = time.time()
    axes = cfg["axes"]
    combos = list(itertools.product(*[axes[a] for a in axes]))
    years = [tuple(y) for y in cfg["years"]]
    total, done, last = len(combos) * len(cfg["symbols"]) * len(years), 0, 0.0
    rows = []
    for combo in combos:
        cells: dict[str, dict[str, Any]] = {}
        for sym in cfg["symbols"]:
            for y0, y1 in years:
                spec = _grid_spec(cfg, combo, sym, y0, y1)
                res = run(spec, log=lambda s: None)
                tr, rnd = res["trades"]["التوليفة"], res["trades"].get("مرجع: جهة عشوائيّة", [])
                st, n_t = stats(tr, len(spec["targets"])), len(spec["targets"])
                cells["%s %s" % (sym, y0[:4])] = {
                    "n": len(tr), "t": [st.get("بلغ_الهدف_%d" % k, 0) for k in range(1, 4)] if n_t else [0, 0, 0],
                    "stop": st["وقف_قبل_أيّ_هدف"], "low": st["أعمق_نزول_تحت_البداية_٪"], "dd": st["أكبر_تراجع_٪"],
                    "net": st["صافي_٪"], "rnd": round(sum(t["pct"] for t in rnd), 2), "months": _months(tr),
                    "win": st.get("نسبة_الربح", 0.0)}
                done += 1
                if time.time() - last > 30 or done == total:
                    last = time.time()
                    left = (time.time() - began) / done * (total - done)
                    log("الشبكة: %d من %d · باقي %s · ينتهي نحو %s" % (done, total, _span(left),
                                                                    datetime.fromtimestamp(time.time() + left).strftime("%H:%M")))
        rows.append((" · ".join(a["label"] for a in combo), cells))
    folder = OUT_ROOT / date.today().isoformat() / safe("شبكة — " + cfg["name"])
    folder.mkdir(parents=True, exist_ok=True)
    keys = ["%s %s" % (s, y0[:4]) for s in cfg["symbols"] for y0, _ in years]
    heads = ("صفقات", "هدف أوّل", "هدف ثانٍ", "هدف ثالث", "وقف كامل", "أعمق نزول تحت البداية ٪", "أكبر تراجع ٪", "صافٍ ٪", "عشوائيّ ٪")
    with open(folder / "الخلايا.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["التوليفة"] + [k + " " + x for k in keys for x in heads])
        for label, cells in rows:
            w.writerow([label] + [v for k in keys for v in (cells[k]["n"], *cells[k]["t"], cells[k]["stop"], cells[k]["low"],
                                                            cells[k]["dd"], cells[k]["net"], cells[k]["rnd"])])

    def score(cells):
        wins = sum(1 for k in keys if cells[k]["net"] > 0)
        by_year = [sum(cells[k]["net"] for k in keys if k.endswith(y0[:4])) for y0, _ in years]
        return wins, min(by_year), by_year

    def owner_row(name: str, c: dict[str, Any]) -> str:
        # ١٩/١٠ (قانون المالك): كلّ تقرير قياس — صفقات · هدف 1/2/3 · وقف · كم نزل قبل الربح أو ربح مباشرة · الصافي.
        dip = "ربح مباشرة" if c["low"] >= 0 else "%.1f٪ (%s$)" % (c["low"], "{:,.0f}".format(c["low"] * 100))
        return "| %s | %d | %s | %d | %d | %d | %d | %s | %+.1f٪ | %+.1f٪ |" % (
            name, c["n"], c.get("win", 0.0), *c["t"], c["stop"], dip, c["net"], c["rnd"])

    table_head = ["| الخليّة | صفقات | رابحة من 100 | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف كامل | نزل تحت البداية قبل الربح (على 10,000$) | "
                  "الصافي | العشوائيّ |", "|---|---|---|---|---|---|---|---|---|---|"]
    ranked = sorted(rows, key=lambda r: (score(r[1])[0], score(r[1])[1]), reverse=True)
    yl = [y0[:4] for y0, _ in years]
    L = ["# شبكة — %s" % cfg["name"], "", "مرتّبة بعدد الخلايا الرابحة (زوج × سنة) ثمّ بأسوأ سنة. **عدد المحاولات: %d توليفة × %d زوج × %d سنة = %d اختبار.**"
         % (len(combos), len(cfg["symbols"]), len(years), total), ""]
    for rank, (label, cells) in enumerate(ranked, 1):
        wins, _, by_year = score(cells)
        L += ["## %d. %s" % (rank, label), "",
              "رابحة في %d خليّة من %d · %s" % (wins, len(keys), " · ".join("صافي %s %+.1f٪" % (y, v) for y, v in zip(yl, by_year))), ""]
        L += table_head + [owner_row("%s %s" % (SYMBOL_AR.get(k.split()[0], k.split()[0]), k.split()[1]), cells[k]) for k in keys] + [""]
    (folder / "النتيجة.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    # ١٩/١٠ (المالك: «بدّي حساب عن كلّ شهر مو بس سنة كاملة»): أشهر كلّ خليّة لأوّل خمس توليفات.
    M = ["# الأشهر — %s" % cfg["name"], "", "لأوّل خمس توليفات في النتيجة: لكلّ خليّة شهرًا شهرًا، والحساب على 10,000$ بمخاطرة 1٪.", ""]
    for rank, (label, cells) in enumerate(ranked[:5], 1):
        for k in keys:
            M += ["## %d. %s — %s %s" % (rank, label, SYMBOL_AR.get(k.split()[0], k.split()[0]), k.split()[1]), "",
                  "| الشهر | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف كامل | صافي الشهر | الحساب آخر الشهر |", "|---|---|---|---|---|---|---|---|"]
            cum = 0.0
            for ym, c in sorted(cells[k]["months"].items()):
                cum += c[5]
                M.append("| %s | %d | %d | %d | %d | %d | %+.1f٪ | %s$ |" % (ym, *c[:5], c[5], "{:,.0f}".format(10000 * (1 + cum / 100))))
            M.append("")
    (folder / "الأشهر.md").write_text("\n".join(M) + "\n", encoding="utf-8")
    T = ["# شبكة — %s" % cfg["name"], "", "- الأزواج: %s" % " · ".join(SYMBOL_AR.get(s, s) for s in cfg["symbols"]),
         "- السنوات: %s" % " · ".join("%s إلى %s" % y for y in years), "- المحاور:"]
    for a, opts in axes.items():
        T.append("  - %s: %s" % (a, " · ".join(o["label"] for o in opts)))
    T += ["- الأساس: `%s`" % json.dumps(cfg["base"], ensure_ascii=False), "- لكلّ زوج: `%s`" % json.dumps(cfg.get("per_symbol", {}), ensure_ascii=False),
          "- الزمن: %s" % _span(time.time() - began)]
    (folder / "الاختبار.md").write_text("\n".join(T) + "\n", encoding="utf-8")
    return folder


def _months(rows: list[dict]) -> dict[str, list]:
    """Per month (Turkey clock): trades, target 1 / 2 / 3, full stops, net %."""
    out: dict[str, list] = {}
    for r in rows:
        c = out.setdefault(r["day"][:7], [0, 0, 0, 0, 0, 0.0])
        k = int(r["reached"])
        c[0] += 1
        c[1] += k >= 1
        c[2] += k >= 2
        c[3] += k >= 3
        c[4] += int(r["exit"] == EXIT_AR["stop"] and k == 0)
        c[5] += r["pct"]
    return out


# ── the market state (owner, 2026-10-19: «داو والمؤشّرات لازم بس تحلّل الاتّجاه: صاعد أو هابط أو عرضيّ … قيس من داو ومؤشّرات») ──
def regime(cfg: dict[str, Any], log=print) -> Path:
    """Dow and the indicators say up / down / sideways only -- no trade. At every quarter-hour close inside the asset's window
    (after its first minutes) each definition labels the state; then what the price did: for up / down, how often it went
    that way and how many points, over each horizon; for sideways, how often it moved less than the market's usual move
    over the same horizon (the median absolute move of all those moments). The market itself is the base line."""
    from shared import red_lines
    from shared.pips import to_pips
    began = time.time()
    sym = cfg.get("symbol", "USTEC")
    horizons = [int(h) for h in cfg.get("horizons_min", [60])] + ["close"]
    defs = cfg["definitions"]
    out_rows: dict[str, dict] = {}
    monthly: dict[str, dict] = {}
    for y0, y1 in [tuple(y) for y in cfg["years"]]:
        t0, t1 = _epoch(y0), _epoch(y1)
        facts = Facts(Path(cfg["store_root"]) / sym / ("%s_%s" % (y0, y1))) if any(d.get("dow") for d in defs) else None
        moments, closes = decision_moments(sym, "15m", t0, t1)
        keep = np.array([red_lines.session_state(m, sym)[0] and not red_lines.in_first_minutes(m, sym) for m in moments])
        moments, closes = moments[keep], closes[keep]
        mins = load_minutes(sym, t0 - 86400, t1 + 3 * 86400)
        fut: dict[Any, np.ndarray] = {}
        for h in horizons:
            if h == "close":
                ends = np.array([m + max(0.0, float(red_lines.seconds_to_red_line(m, sym, None) or 0.0)) for m in moments])
            else:
                ends = moments + h * 60.0
            j = np.searchsorted(mins["t"], ends, side="right") - 1
            # to_pips gives a distance (no sign): the sign of the move is kept apart
            fut[h] = np.array([math.copysign(to_pips(float(mins["c"][k]) - float(c), sym), float(mins["c"][k]) - float(c))
                               if k >= 0 else np.nan for k, c in zip(j, closes)])
        ema = virtual_values("ema", moments, sym, np.zeros(0), closes)
        dow_cache: dict[str, np.ndarray] = {}
        for d in defs:
            parts = []
            for key in d.get("dow") or []:
                if key not in dow_cache:
                    s = facts.series("209", "15m", key)
                    vals, ok = Facts.at(s[0], s[1], moments, None)
                    vocab = s[2].get("vocab") or []
                    dow_cache[key] = np.array([word_side(vocab[i]) if ok[n] and 0 <= i < len(vocab) else 0
                                               for n, i in enumerate(vals.astype(int))])
                parts.append(dow_cache[key])
            for fr in d.get("ema") or []:
                parts.append(np.array([word_side(w) for w in ema["order.%s" % fr]]))
            for fr in d.get("above50") or []:
                parts.append(np.array([word_side(w) for w in ema["above50.%s" % fr]]))
            for spec_ in d.get("clear50") or []:                    # "15m:5" = the last 5 quarter-hours clear of the line
                fr, k_ = spec_.split(":")
                parts.append(np.array([word_side(w) for w in ema["clear50_%s.%s" % (k_, fr)]]))
            stack = np.vstack(parts)
            label = np.where((stack > 0).all(axis=0), 1, np.where((stack < 0).all(axis=0), -1, 0))
            row = out_rows.setdefault(d["label"], {})
            for h in horizons:
                mv = fut[h]
                ok = np.isfinite(mv)
                med = float(np.median(np.abs(mv[ok]))) if ok.any() else 0.0
                cell = {"all": int(ok.sum()), "market_up": round(100 * float((mv[ok] > 0).mean()), 1) if ok.any() else 0, "median": med}
                for lab, name in ((1, "up"), (-1, "down"), (0, "side")):
                    sel = ok & (label == lab)
                    n = int(sel.sum())
                    if name == "side":
                        cell[name] = (n, round(100 * float((np.abs(mv[sel]) < med).mean()), 1) if n else 0.0,
                                      round(float(np.mean(np.abs(mv[sel]))), 1) if n else 0.0)
                    else:
                        way = mv[sel] * lab
                        cell[name] = (n, round(100 * float((way > 0).mean()), 1) if n else 0.0,
                                      round(float(np.mean(way)), 1) if n else 0.0)
                row["%s %s" % (y0[:4], h)] = cell
            if d.get("monthly"):
                mv = fut[horizons[0]]
                for n_, m in enumerate(moments):
                    key = datetime.fromtimestamp(m, timezone.utc).strftime("%Y-%m")
                    c = monthly.setdefault(d["label"], {}).setdefault(key, [0, 0, 0, 0, 0, 0])
                    if not np.isfinite(mv[n_]):
                        continue
                    lab = int(label[n_])
                    if lab:
                        c[0] += 1
                        c[1] += int(mv[n_] * lab > 0)
                    else:
                        c[2] += 1
                    c[3] += 1
                    c[4] += int(lab == 1)
                    c[5] += int(lab == -1)
        log("حالة السوق: %s انتهت · لحظات %d" % (y0[:4], len(moments)))
    folder = OUT_ROOT / date.today().isoformat() / safe("حالة السوق — " + cfg["name"])
    folder.mkdir(parents=True, exist_ok=True)
    hname = {h: ("حتّى إغلاق الجلسة" if h == "close" else "بعد %d دقيقة" % h) for h in horizons}
    L = ["# حالة السوق — %s" % cfg["name"], "",
         "عند كلّ إغلاق ربع ساعة داخل الجلسة (بعد أوّل دقائقها): التعريف يقول صاعد أو هابط أو عرضيّ، ثمّ ما فعله السعر. «أصاب» للصاعد"
         " والهابط = ذهب السعر في جهته؛ وللعرضيّ = تحرّك أقلّ من الحركة المعتادة (وسط الحركة المطلقة لكلّ اللحظات في المدّة نفسها)،"
         " فأساسه 50 من 100. والنقاط في جهة الحالة.", ""]
    for label_, row in out_rows.items():
        L += ["## %s" % label_, "",
              "| السنة والمدّة | صاعد: لحظات · أصاب من 100 · نقاط | هابط: لحظات · أصاب من 100 · نقاط | عرضيّ: لحظات · بقي عرضيًّا من 100 · حركته | السوق: صعد من 100 · حركته المعتادة |",
              "|---|---|---|---|---|"]
        for k, c in row.items():
            y, h = k.split(" ", 1)
            h = "close" if h == "close" else int(h)
            L.append("| %s %s | %d · %.1f · %+.1f | %d · %.1f · %+.1f | %d · %.1f · %.1f | %.1f · %.1f |" % (
                y, hname[h], *c["up"], *c["down"], *c["side"], c["market_up"], c["median"]))
        L.append("")
    for label_, months in monthly.items():
        L += ["## الأشهر — %s (%s)" % (label_, hname[horizons[0]]), "",
              "| الشهر | لحظات | صاعد | هابط | عرضيّ | الصاعد والهابط: أصاب من 100 |", "|---|---|---|---|---|---|"]
        for key in sorted(months):
            c = months[key]
            L.append("| %s | %d | %d | %d | %d | %s |" % (key, c[3], c[4], c[5], c[2], ("%.0f" % (100 * c[1] / c[0])) if c[0] else "—"))
        L.append("")
    (folder / "النتيجة.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (folder / "الاختبار.md").write_text("# حالة السوق — %s\n\n- الرمز: %s\n- السنوات: %s\n- التعريفات: `%s`\n- المدد: %s\n- الزمن: %s\n" % (
        cfg["name"], SYMBOL_AR.get(sym, sym), " · ".join("%s إلى %s" % tuple(y) for y in cfg["years"]),
        json.dumps(defs, ensure_ascii=False), " · ".join(hname[h] for h in horizons), _span(time.time() - began)), encoding="utf-8")
    return folder


# ── the frames' direction (owner, 2026-10-22, «NQ»: «بدّي أشوف كلّ الفريمات على كلّ زوج صاعد أو هابط بنظرة وحدة» ·
#    «قيس بأيّ طريقة بدّك» · «سنة صاعدة وسنة هابطة فقط») ──
DIRECTION_FRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1")
DIRECTION_PERIOD_S = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400,
                      "W1": 7 * 86400, "MN1": 31 * 86400}
FRAME_AR = {"M1": "الدقيقة", "M5": "الخمس دقائق", "M15": "الربع ساعة", "M30": "النصف ساعة", "H1": "الساعة",
            "H4": "الأربع ساعات", "D1": "اليوم", "W1": "الأسبوع", "MN1": "الشهر"}
DIRECTION_WARM_BARS = 300
#: 2026-10-22 (owner, «NQ»): «بدّي مؤشّرات مع داو تقول صاعد أو هابط، ما تشتري ولا تبيع، مع شموع» -- each tool says up or
#: down only (an undecided reading keeps the last one: never sideways), and is compared with the candles' own direction.
TOOL_AR = {"ema_order": "المتوسّطات 5 و10 و50 مرتّبة", "above50": "السعر فوق متوسّط 50 أو تحته", "dow": "داو",
           "dow_ema": "داو والمتوسّطات معًا"}
EMA_FAST, EMA_MID, EMA_SLOW = 5, 10, 50
FLIP_WINDOW_BARS = 50


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    alpha, acc, out = 2.0 / (n + 1), float(x[0]), np.empty(len(x))
    for i, v in enumerate(x):
        acc += alpha * (float(v) - acc)
        out[i] = acc
    return out


def _hold(raw: np.ndarray) -> np.ndarray:
    """0 = no reading at that candle: the last up or down stands (the owner: up or down only)."""
    out, cur = np.zeros(len(raw), dtype=np.int8), 0
    for i, v in enumerate(raw):
        cur = int(v) or cur
        out[i] = cur
    return out


def _order_states(emas: list[np.ndarray]) -> np.ndarray:
    """Up when every faster average sits above the slower one, down when all below; otherwise the last reading stands."""
    up = np.all([emas[i] > emas[i + 1] for i in range(len(emas) - 1)], axis=0)
    down = np.all([emas[i] < emas[i + 1] for i in range(len(emas) - 1)], axis=0)
    return _hold(np.where(up, 1, np.where(down, -1, 0)).astype(np.int8))


def _dow_states(closes: np.ndarray, span: int) -> np.ndarray:
    from shared import dow_theory
    trends, breaks = dow_theory.trend_series([float(c) for c in closes], span)
    # Dow's trend stands until a clear reversal: a break below the last swing low ends a rise, so it reads down.
    return np.array([1 if t == dow_theory.RISING else -1 if t == dow_theory.FALLING else
                     -1 if b == dow_theory.BREAK_DOWN else 1 if b == dow_theory.BREAK_UP else 0
                     for t, b in zip(trends, breaks)], dtype=np.int8)


def _tool_states(closes: np.ndarray, tool: str) -> np.ndarray:
    from shared import dow_theory
    e5, e10, e50 = _ema(closes, EMA_FAST), _ema(closes, EMA_MID), _ema(closes, EMA_SLOW)
    if tool == "above50":
        return _hold(np.sign(closes - e50).astype(np.int8))
    ema = _order_states([e5, e10, e50])
    if tool == "ema_order":
        return ema
    dow = _dow_states(closes, dow_theory.PIVOT_SPAN)
    if tool == "dow":
        return dow
    return _hold(np.where(dow == ema, dow, 0).astype(np.int8))


def _flips(state: np.ndarray) -> np.ndarray:
    return np.flatnonzero((state[1:] != state[:-1]) & (state[1:] != 0) & (state[:-1] != 0)) + 1


def _compare_states(truth: np.ndarray, tool: np.ndarray, inside: np.ndarray) -> dict[str, Any] | None:
    """How often the tool says what the candles say, on each side; and when the candles turn, how many candles before (−)
    or after (+) the tool turns the same way (the nearest turn within the window)."""
    sel = inside[(truth[inside] != 0) & (tool[inside] != 0)]
    if not len(sel):
        return None
    t, k = truth[sel], tool[sel]
    out: dict[str, Any] = {"n": int(len(sel)), "agree": 100.0 * float((t == k).mean()),
                           "base": 100.0 * max(float((t == 1).mean()), float((t == -1).mean())),
                           "up": 100.0 * float((k[t == 1] == 1).mean()) if (t == 1).any() else float("nan"),
                           "down": 100.0 * float((k[t == -1] == -1).mean()) if (t == -1).any() else float("nan")}
    lo, hi = int(inside[0]), int(inside[-1])
    tflips = [i for i in _flips(truth) if lo <= i <= hi]
    kflips = _flips(tool)
    offsets = []
    for i in tflips:
        same = kflips[tool[kflips] == truth[i]]
        if not len(same):
            continue
        j = same[np.argmin(np.abs(same - i))]
        if abs(int(j) - i) <= FLIP_WINDOW_BARS:
            offsets.append(int(j) - i)
    out.update({"flips": len(tflips), "found": 100.0 * len(offsets) / len(tflips) if tflips else float("nan"),
                "lag": float(np.median(offsets)) if offsets else float("nan"),
                "earlier": 100.0 * float(np.mean(np.array(offsets) < 0)) if offsets else float("nan")})
    return out


#: Then (same day): «في إفادة من دمج 3 متوسّطات مع داو وشموع لمعرفة اتّجاه؟ … قيسها» -- a combination reads up (or down)
#: only when the candles and every tool in it say the same; then does the price go that way more often than the market?
COMBO_PART_AR = {"candles": "الشموع", **TOOL_AR}


def _combo_name(parts: list[str]) -> str:
    return " + ".join(COMBO_PART_AR[p] for p in parts)


def _ahead_stats(cl: np.ndarray, known: np.ndarray, state: np.ndarray, ahead: list[int], pip: float) -> dict[str, Any]:
    """For each horizon and side: moments, hit rate, the market's own rate over all `known` moments, the difference, twice
    its standard error, and the mean move in the side's way."""
    out: dict[str, Any] = {}
    for k in ahead:
        idx = known[known + k < len(cl)]
        mv = cl[idx + k] - cl[idx]
        side_of = state[idx]
        for side in (1, -1):
            base = float((mv * side > 0).mean()) if len(mv) else 0.0
            sel = side_of == side
            n = int(sel.sum())
            hit = float((mv[sel] * side > 0).mean()) if n else float("nan")
            margin = 2.0 * math.sqrt(base * (1.0 - base) / n) if n else float("nan")
            pips = float((mv[sel] * side).mean()) * pip if n else float("nan")
            out["%d %d" % (k, side)] = (n, 100 * hit, 100 * base, 100 * (hit - base), 100 * margin, pips)
    return out


def direction(cfg: dict[str, Any], log=print) -> Path:
    """Each frame is up or down by the owner's rule (shared/direction_rule.py), on the broker's own candles of that frame.
    For every closed candle inside each year the state is known at its close; then what the next candle and the next five
    did: an up state is right when the close went higher, a down state when it went lower. The market itself is the base
    line (how often any candle there was followed by a rise or by a fall), and twice the standard error of that rate is the
    chance margin. Sequence lengths are compared; the steadiest is the one whose worst edge over both years, both sides and
    both horizons is highest. No trade."""
    from shared import direction_rule as rule
    from shared.pips import to_pips
    began = time.time()
    sym = cfg.get("symbol", "USTEC")
    frames = [f for f in cfg.get("frames", DIRECTION_FRAMES) if f in DIRECTION_PERIOD_S]
    runs = [int(r) for r in cfg.get("runs", [2, 3, 4])]
    ahead = [int(k) for k in cfg.get("ahead", [1, 5])]
    years = [tuple(y) for y in cfg["years"]]
    pip = float(to_pips(1.0, sym))
    cells: dict[tuple, dict] = {}
    tool_cells: dict[tuple, dict] = {}
    combo_cells: dict[tuple, dict] = {}
    align_cells: dict[tuple, dict] = {}
    year_move: dict[str, tuple] = {}
    for y0, y1 in years:
        t0, t1 = _epoch(y0), _epoch(y1)
        days = _bars_db(sym, "D1", t0, t1)
        if days:
            year_move[y0[:4]] = (days[0][1], days[-1][4])
        for fr in frames:
            p = DIRECTION_PERIOD_S[fr]
            bars = _bars_db(sym, fr, t0 - DIRECTION_WARM_BARS * p, t1 + (max(ahead) + 2) * p)
            if len(bars) < max(runs) + max(ahead) + 2:
                log("اتّجاه الفريمات: %s %s بلا شموع كافية" % (y0[:4], FRAME_AR[fr]))
                continue
            arr = np.array(bars, dtype=float)
            ts, hi, lo, cl = arr[:, 0], arr[:, 2], arr[:, 3], arr[:, 4]
            inside = np.flatnonzero((ts >= t0) & (ts < t1))
            if (cfg.get("tools") or cfg.get("combos")) and len(inside):
                truth = rule.directions(hi, lo, int(cfg.get("truth_run", rule.DEFAULT_RUN)))
                states = {"candles": truth}
                for tool in {t for t in cfg.get("tools", [])} | {p for c in cfg.get("combos", []) for p in c} - {"candles"}:
                    states[tool] = _tool_states(cl, tool)
                for tool in cfg.get("tools", []):
                    got = _compare_states(truth, states[tool], inside)
                    if got:
                        tool_cells[(y0[:4], fr, tool)] = got
                known_all = inside[truth[inside] != rule.UNKNOWN]
                for parts in cfg.get("combos", []):
                    agree = np.all(np.vstack([states[p] == truth for p in parts]), axis=0)
                    combined = np.where(agree, truth, 0).astype(np.int8)
                    cell = _ahead_stats(cl, known_all, combined, ahead, pip)
                    cell["share"] = 100.0 * float((combined[known_all] != 0).mean()) if len(known_all) else 0.0
                    combo_cells[(y0[:4], fr, _combo_name(parts))] = cell
            for run in runs:
                st = rule.directions(hi, lo, run)
                known = inside[st[inside] != rule.UNKNOWN]
                if not len(known):
                    continue
                chg = np.flatnonzero(np.diff(st[known]) != 0)
                lengths = np.diff(np.concatenate(([0], chg + 1, [len(known)])))
                cell: dict[str, Any] = {"candles": int(len(inside)), "up_share": 100.0 * float((st[known] == rule.UP).mean()),
                                        "median_len": float(np.median(lengths)), "flips": int(len(chg))}
                for k in ahead:
                    idx = known[known + k < len(cl)]
                    mv = cl[idx + k] - cl[idx]
                    side_of = st[idx]
                    for side in (rule.UP, rule.DOWN):
                        base = float((mv * side > 0).mean()) if len(mv) else 0.0
                        sel = side_of == side
                        n = int(sel.sum())
                        hit = float((mv[sel] * side > 0).mean()) if n else float("nan")
                        margin = 2.0 * math.sqrt(base * (1.0 - base) / n) if n else float("nan")
                        pips = float((mv[sel] * side).mean()) * pip if n else float("nan")
                        cell["%d %d" % (k, side)] = (n, 100 * hit, 100 * base, 100 * (hit - base), 100 * margin, pips)
                cells[(y0[:4], fr, run)] = cell
        # 2026-10-22 (owner): «لازم يكون عنّا اتّجاه واضح حقيقي» -- the heavy frames (his words 19/10: four hours, an hour
        # and a quarter) all saying the same by the candles; at each lower candle close only heavy candles already closed
        # count. Then does the lower frame go that way more often than the market?
        align = cfg.get("align")
        if align:
            heavy = []
            for hf in align["heavy"]:
                p = DIRECTION_PERIOD_S[hf]
                hb = np.array(_bars_db(sym, hf, t0 - DIRECTION_WARM_BARS * p, t1), dtype=float)
                if len(hb):
                    heavy.append((hb[:, 0] + p, rule.directions(hb[:, 2], hb[:, 3], int(align.get("run", rule.DEFAULT_RUN)))))
            for tf in align["targets"] if len(heavy) == len(align["heavy"]) else []:
                p = DIRECTION_PERIOD_S[tf]
                tb = np.array(_bars_db(sym, tf, t0 - p, t1 + (max(ahead) + 2) * p), dtype=float)
                if not len(tb):
                    continue
                inside_t = np.flatnonzero((tb[:, 0] >= t0) & (tb[:, 0] < t1))
                close_t = tb[:, 0] + p
                parts = []
                for closes_h, states_h in heavy:
                    k = np.searchsorted(closes_h, close_t, side="right") - 1
                    parts.append(np.where(k >= 0, states_h[np.clip(k, 0, None)], 0))
                stack = np.vstack(parts)
                aligned = np.where((stack == stack[0]).all(axis=0) & (stack[0] != 0), stack[0], 0).astype(np.int8)
                cell = _ahead_stats(tb[:, 4], inside_t, aligned, ahead, pip)
                cell["share"] = 100.0 * float((aligned[inside_t] != 0).mean()) if len(inside_t) else 0.0
                align_cells[(y0[:4], tf)] = cell
        log("اتّجاه الفريمات: %s انتهت" % y0[:4])

    def worst(fr: str, run: int) -> tuple[float, bool]:
        diffs = [(c["%d %d" % (k, s)][3], c["%d %d" % (k, s)][4]) for (y, f, r), c in cells.items() if f == fr and r == run
                 for k in ahead for s in (rule.UP, rule.DOWN) if c["%d %d" % (k, s)][0]]
        if not diffs:
            return float("nan"), False
        return min(d for d, _ in diffs), all(d > m for d, m in diffs)

    best: dict[str, dict] = {}
    for fr in frames:
        scored = [(worst(fr, r), r) for r in runs if any(f == fr and rr == r for (_, f, rr) in cells)]
        scored = [x for x in scored if not math.isnan(x[0][0])]
        if scored:
            (score, steady), run = max(scored, key=lambda x: x[0][0])
            best[fr] = {"التتالي": run, "أسوأ_فرق": round(score, 1), "فوق_الصدفة_دائمًا": steady}

    folder = OUT_ROOT / date.today().isoformat() / safe("اتّجاه الفريمات — " + cfg.get("name", SYMBOL_AR.get(sym, sym)))
    folder.mkdir(parents=True, exist_ok=True)
    side_ar = {rule.UP: "الصاعد", rule.DOWN: "الهابط"}
    L = ["# اتّجاه الفريمات — %s" % SYMBOL_AR.get(sym, sym), "",
         "قاعدة المالك: «شموع صاعدة وشموع هابطة». الشمعة الصاعدة قمّتها وقاعها أعلى من التي قبلها، والهابطة أدنى. يصير الفريم"
         " صاعدًا بعد عددٍ من الشموع الصاعدة المتتالية (التتالي)، ويبقى صاعدًا حتّى يأتي العدد نفسه من الشموع الهابطة المتتالية،"
         " والعكس. فلا عرضيّ أبدًا، وشمعة خبرٍ واحدة لا تقلبه.", "",
         "لكلّ شمعةٍ مغلقة في السنة: الفريم يقول صاعد أو هابط عند إغلاقها، ثمّ ما فعله السعر بعدها. «أصاب» = أغلق السعر بعدها في"
         " جهته. «السوق» = كم مرّةً صعد السعر (أو نزل) بعد أيّ شمعةٍ في الفريم نفسه. «الفرق» = أصاب ناقص السوق، و«هامش الصدفة»"
         " ضعفُ خطئه المعياريّ: الفرق الأصغر منه لا يُعتدّ به.", ""]
    for y, (o, c) in sorted(year_move.items()):
        L.append("- **سنة %s:** افتتحت %.0f وأغلقت %.0f (%+.1f٪) ⟸ %s." % (y, o, c, 100 * (c - o) / o, "صاعدة" if c > o else "هابطة"))
    L += ["", "## الخلاصة — لكلّ فريم أثبت تتالٍ في السنتين", "",
          "| الفريم | أثبت تتالٍ | أسوأ فرقٍ في السنتين والجهتين والمدّتين | فوق الصدفة في كلّها؟ |", "|---|---|---|---|"]
    for fr in frames:
        b = best.get(fr)
        L.append("| %s | %s | %s | %s |" % (FRAME_AR[fr], b["التتالي"] if b else "—", "%+.1f" % b["أسوأ_فرق"] if b else "—",
                                          ("نعم" if b["فوق_الصدفة_دائمًا"] else "لا") if b else "—"))
    for y0, _ in years:
        y = y0[:4]
        for k in ahead:
            L += ["", "## %s — بعد %s" % (y, "شمعة واحدة" if k == 1 else "%d شموع" % k), "",
                  "| الفريم | التتالي | صاعد من الوقت ٪ | يدوم (شموع، الوسط) | تبدّل | الصاعد: لحظات · أصاب · السوق · الفرق ± الصدفة · نقاط"
                  " | الهابط: لحظات · أصاب · السوق · الفرق ± الصدفة · نقاط |", "|---|---|---|---|---|---|---|"]
            for fr in frames:
                for run in runs:
                    c = cells.get((y, fr, run))
                    if not c:
                        continue
                    parts = []
                    for side in (rule.UP, rule.DOWN):
                        n, hit, base, diff, margin, pips = c["%d %d" % (k, side)]
                        parts.append("%d · %.1f · %.1f · %+.1f ±%.1f · %+.1f" % (n, hit, base, diff, margin, pips) if n else "—")
                    L.append("| %s | %d | %.1f | %.0f | %d | %s | %s |" % (FRAME_AR[fr], run, c["up_share"], c["median_len"],
                                                                         c["flips"], *parts))
    L += ["", "أصاب = أغلق السعر بعد المدّة في جهة الفريم. النقاط في جهة الفريم بالبِب، وسطها على كلّ اللحظات."]
    if tool_cells:
        tools = cfg["tools"]
        L += ["", "# الأدوات مقابل الشموع — المتوسّطات وداو تقول صاعد أو هابط فقط", "",
              "الحقيقة: اتّجاه الشموع بقاعدة المالك (%d متتالية). كلّ أداة تقول صاعد أو هابط فقط، والقراءة التي لا تحسم تُبقي"
              " آخر قراءة. «المتوسّطات مرتّبة» = 5 فوق 10 فوق 50 صاعد، والعكس هابط. «فوق 50» = الإغلاق فوق متوسّط 50 صاعد."
              " «داو» = اتّجاه داو بحساب الذرّة 209، وكسرُ آخر قاعٍ بعد صعودٍ يُقرأ هابطًا (والعكس). «داو والمتوسّطات معًا» ="
              " حين يتّفقان، وإلّا يبقى آخر اتّفاق." % int(cfg.get("truth_run", rule.DEFAULT_RUN)), "",
              "«تطابق» = كم من 100 شمعة قالت الأداة ما قالته الشموع. «الثابت» = لو قالت دائمًا الجهة الأكثر في السنة."
              " «التأخّر» = حين تنقلب الشموع، بعد كم شمعة تنقلب الأداة إلى الجهة نفسها (سالب = قبل الشموع)، وسطه.", "",
              "## الخلاصة — الأقرب إلى الشموع على كلّ فريم (أسوأ سنةٍ من السنتين)", "",
              "| الفريم | %s |" % " | ".join(TOOL_AR[t] for t in tools), "|---|%s" % ("---|" * len(tools))]
        for fr in frames:
            row = []
            for tool in tools:
                got = [tool_cells[(y0[:4], fr, tool)] for y0, _ in years if (y0[:4], fr, tool) in tool_cells]
                row.append("تطابق %.0f · تأخّر %+.0f" % (min(g["agree"] for g in got), max(g["lag"] for g in got))
                           if got and all(g["lag"] == g["lag"] for g in got) else "—")
            L.append("| %s | %s |" % (FRAME_AR[fr], " | ".join(row)))
        for y0, _ in years:
            L += ["", "## %s" % y0[:4], "",
                  "| الفريم | الأداة | تطابق من 100 | الثابت | حين الشموع صاعدة قالت صاعد | حين هابطة قالت هابط | انقلابات الشموع"
                  " | وجدت انقلابًا قريبًا من 100 | التأخّر بالشموع | قبل الشموع من 100 |", "|---|---|---|---|---|---|---|---|---|---|"]
            for fr in frames:
                for tool in tools:
                    g = tool_cells.get((y0[:4], fr, tool))
                    if g:
                        lag = "%+.0f" % g["lag"] if g["lag"] == g["lag"] else "—"
                        early = "%.0f" % g["earlier"] if g["earlier"] == g["earlier"] else "—"
                        L.append("| %s | %s | %.1f | %.1f | %.1f | %.1f | %d | %.0f | %s | %s |" % (
                            FRAME_AR[fr], TOOL_AR[tool], g["agree"], g["base"], g["up"], g["down"], g["flips"], g["found"],
                            lag, early))
        L += ["", "انقلاب الشموع بلا انقلابٍ للأداة خلال %d شمعة لا يدخل التأخّر." % FLIP_WINDOW_BARS]
    if combo_cells:
        names = [_combo_name(p) for p in cfg["combos"]]
        L += ["", "# الدمج — هل يصدق الاتّجاه أكثر حين تتّفق الأدوات مع الشموع؟", "",
              "الدمج يقول صاعد (أو هابط) فقط حين تقوله الشموع وكلّ أداةٍ فيه معًا، وإلّا فلا قراءة. ثمّ: بعد إغلاق الشمعة، هل ذهب"
              " السعر في جهته في الشمعة التالية والخمس التالية أكثر من السوق نفسه؟ «يتّفق من الوقت» = كم من 100 شمعة كانت له"
              " قراءة. «الفرق» = أصاب ناقص السوق، و«± الصدفة» ضعف خطئه المعياريّ.", "",
              "## الخلاصة — أسوأ فرقٍ في السنتين والجهتين والمدّتين", "",
              "| الفريم | %s |" % " | ".join(names), "|---|%s" % ("---|" * len(names))]
        for fr in frames:
            row = []
            for name in names:
                got = [combo_cells[(y0[:4], fr, name)] for y0, _ in years if (y0[:4], fr, name) in combo_cells]
                diffs = [(g["%d %d" % (k, s)][3], g["%d %d" % (k, s)][4]) for g in got for k in ahead for s in (1, -1)
                         if g["%d %d" % (k, s)][0]]
                row.append("%+.1f%s" % (min(d for d, _ in diffs), " فوق الصدفة" if all(d > m for d, m in diffs) else "")
                           if diffs else "—")
            L.append("| %s | %s |" % (FRAME_AR[fr], " | ".join(row)))
        for y0, _ in years:
            for k in ahead:
                L += ["", "## %s — بعد %s" % (y0[:4], "شمعة واحدة" if k == 1 else "%d شموع" % k), "",
                      "| الفريم | الدمج | يتّفق من الوقت ٪ | الصاعد: لحظات · أصاب · السوق · الفرق ± الصدفة · نقاط"
                      " | الهابط: لحظات · أصاب · السوق · الفرق ± الصدفة · نقاط |", "|---|---|---|---|---|"]
                for fr in frames:
                    for name in names:
                        c = combo_cells.get((y0[:4], fr, name))
                        if not c:
                            continue
                        parts = []
                        for side in (1, -1):
                            n, hit, base, diff, margin, pips = c["%d %d" % (k, side)]
                            parts.append("%d · %.1f · %.1f · %+.1f ±%.1f · %+.1f" % (n, hit, base, diff, margin, pips) if n else "—")
                        L.append("| %s | %s | %.0f | %s | %s |" % (FRAME_AR[fr], name, c["share"], *parts))
    if align_cells:
        heavy_ar = " و".join(FRAME_AR[f] for f in cfg["align"]["heavy"])
        L += ["", "# الاتّجاه الواضح — %s متّفقة بالشموع" % heavy_ar, "",
              "عند إغلاق كلّ شمعةٍ من الفريم الصغير: إن كانت %s كلّها صاعدة بالشموع (%d متتالية، والمحسوب منها ما أُغلق قبل"
              " تلك اللحظة فقط) فالاتّجاه الواضح صاعد، أو كلّها هابطة فهابط، وإلّا فلا قراءة. ثمّ: هل ذهب الفريم الصغير في جهته"
              " في الشمعة التالية والخمس التالية أكثر من السوق نفسه؟" % (heavy_ar, int(cfg["align"].get("run", rule.DEFAULT_RUN))), "",
              "| السنة | الفريم | المدّة | متّفقة من الوقت ٪ | الصاعد: لحظات · أصاب · السوق · الفرق ± الصدفة · نقاط"
              " | الهابط: لحظات · أصاب · السوق · الفرق ± الصدفة · نقاط |", "|---|---|---|---|---|---|"]
        for y0, _ in years:
            for tf in cfg["align"]["targets"]:
                c = align_cells.get((y0[:4], tf))
                if not c:
                    continue
                for k in ahead:
                    parts = []
                    for side in (1, -1):
                        n, hit, base, diff, margin, pips = c["%d %d" % (k, side)]
                        parts.append("%d · %.1f · %.1f · %+.1f ±%.1f · %+.1f" % (n, hit, base, diff, margin, pips) if n else "—")
                    L.append("| %s | %s | %s | %.0f | %s | %s |" % (y0[:4], FRAME_AR[tf], "شمعة" if k == 1 else "%d شموع" % k,
                                                                   c["share"], *parts))
    (folder / "النتيجة.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (folder / "الاختبار.md").write_text(
        "# اتّجاه الفريمات — %s\n\n- الرمز: %s\n- السنتان: %s\n- الأطر: %s\n- التتالي: %s\n- المدّتان: %s\n"
        "- البيانات: شموع الوسيط لكلّ فريم من مخزن سي‑تريدر، و%d شمعة قبل كلّ سنة للتحضير\n- الزمن: %s\n" % (
            cfg.get("name", ""), SYMBOL_AR.get(sym, sym), " · ".join("%s إلى %s" % y for y in years),
            " · ".join(FRAME_AR[f] for f in frames), " · ".join(str(r) for r in runs),
            " · ".join("%d شمعة" % k for k in ahead), DIRECTION_WARM_BARS, _span(time.time() - began)), encoding="utf-8")
    (folder / "summary.json").write_text(json.dumps({"kind": "direction", "الاسم": cfg.get("name", ""), "الرمز": sym,
                                                     "السنوات": [list(y) for y in years], "الخلاصة": {FRAME_AR[f]: best[f] for f in best},
                                                     "الأدوات": {"%s %s %s" % (y, FRAME_AR[f], TOOL_AR[t]): v
                                                                 for (y, f, t), v in tool_cells.items()},
                                                     "الدمج": {"%s %s %s" % (y, FRAME_AR[f], n): v
                                                               for (y, f, n), v in combo_cells.items()},
                                                     "الاتّجاه_الواضح": {"%s %s" % (y, FRAME_AR[f]): v
                                                                         for (y, f), v in align_cells.items()}},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


# ── tuning the direction on the past (owner, 2026-10-22: «الضبط على الماضي: نجرّب أعدادًا كثيرة، مثل أطوال المتوسّطات وعدد
#    الشموع وحساسيّة داو، على 2022 و2023، ونختار الأعلى نتيجة … مع العلم أنّه قد لا يصدق في المستقبل») ──
FIT_RUNS = [2, 3, 4, 5]
FIT_ORDERS = [(5, 10, 50), (3, 8, 21), (5, 13, 34), (8, 21, 55), (9, 21, 50), (10, 20, 100), (20, 50, 200)]
FIT_LINES = [20, 50, 100, 200]
FIT_SPANS = [1, 2, 3, 5]
FIT_MIN_SHARE = 10.0
FIT_TOP = 10


def _fit_readings(hi: np.ndarray, lo: np.ndarray, cl: np.ndarray, hold_combos: bool = False) -> dict[str, np.ndarray]:
    """Every single reading and every candles + averages + Dow combination (a reading only where all three agree, or with
    `hold_combos` the last agreement standing -- up or down always, as the owner reads a frame)."""
    from shared import direction_rule as rule
    lengths = sorted({n for o in FIT_ORDERS for n in o} | set(FIT_LINES))
    emas = {n: _ema(cl, n) for n in lengths}
    candles = {r: rule.directions(hi, lo, r) for r in FIT_RUNS}
    orders = {o: _order_states([emas[n] for n in o]) for o in FIT_ORDERS}
    dows = {s: _dow_states(cl, s) for s in FIT_SPANS}
    out: dict[str, np.ndarray] = {}
    out.update({"الشموع %d متتالية" % r: s for r, s in candles.items()})
    out.update({"المتوسّطات %s" % "/".join(map(str, o)): s for o, s in orders.items()})
    out.update({"السعر مع متوسّط %d" % n: _hold(np.sign(cl - emas[n]).astype(np.int8)) for n in FIT_LINES})
    out.update({"داو بحساسيّة %d" % s: d for s, d in dows.items()})
    for r, c in candles.items():
        for o, e in orders.items():
            for s, d in dows.items():
                agree = (c == e) & (e == d) & (c != 0)
                combined = np.where(agree, c, 0).astype(np.int8)
                out["الشموع %d + المتوسّطات %s + داو %d" % (r, "/".join(map(str, o)), s)] = _hold(combined) if hold_combos else combined
    return out


def direction_fit(cfg: dict[str, Any], log=print) -> Path:
    """Tries every reading on each frame over both years and ranks them by how much more often the price went their way
    after they spoke than the market did (next candle and next five, both sides, both years). In-sample by the owner's
    choice: the best on the past, said with the number of tries."""
    from shared.pips import to_pips
    began = time.time()
    sym = cfg.get("symbol", "USTEC")
    frames = [f for f in cfg["frames"] if f in DIRECTION_PERIOD_S]
    years = [tuple(y) for y in cfg["years"]]
    ahead = [int(k) for k in cfg.get("ahead", [1, 5])]
    pip = float(to_pips(1.0, sym))
    ranked: dict[str, list] = {}
    tries = 0
    for fr in frames:
        p = DIRECTION_PERIOD_S[fr]
        per_name: dict[str, list] = defaultdict(list)
        for y0, y1 in years:
            t0, t1 = _epoch(y0), _epoch(y1)
            arr = np.array(_bars_db(sym, fr, t0 - DIRECTION_WARM_BARS * p, t1 + (max(ahead) + 2) * p), dtype=float)
            if len(arr) < DIRECTION_WARM_BARS:
                continue
            inside = np.flatnonzero((arr[:, 0] >= t0) & (arr[:, 0] < t1))
            for name, state in _fit_readings(arr[:, 2], arr[:, 3], arr[:, 4]).items():
                share = 100.0 * float((state[inside] != 0).mean()) if len(inside) else 0.0
                per_name[name].append((y0[:4], share, _ahead_stats(arr[:, 4], inside, state, ahead, pip)))
        rows = []
        for name, got in per_name.items():
            tries += 1
            cells = [g[2]["%d %d" % (k, s)] for g in got for k in ahead for s in (1, -1)]
            if len(got) != len(years) or any(c[0] == 0 for c in cells) or min(g[1] for g in got) < FIT_MIN_SHARE:
                continue
            diffs = [c[3] for c in cells]
            rows.append({"name": name, "avg": float(np.mean(diffs)), "min": float(min(diffs)),
                         "steady": all(c[3] > c[4] for c in cells), "hit": float(np.mean([c[1] for c in cells])),
                         "share": float(np.mean([g[1] for g in got])), "years": {g[0]: g[2] for g in got}})
        ranked[fr] = sorted(rows, key=lambda r: r["avg"], reverse=True)
        log("ضبط الاتّجاه: %s انتهى (%d قراءة)" % (FRAME_AR[fr], len(per_name)))
    folder = OUT_ROOT / date.today().isoformat() / safe("ضبط الاتّجاه على الماضي — " + cfg.get("name", SYMBOL_AR.get(sym, sym)))
    folder.mkdir(parents=True, exist_ok=True)
    L = ["# ضبط الاتّجاه على الماضي — %s" % SYMBOL_AR.get(sym, sym), "",
         "طلب المالك: نجرّب أعدادًا كثيرة على %s ونختار الأعلى نتيجة، مع العلم أنّه قد لا يصدق في المستقبل." % " و".join(
             y[0][:4] for y in years), "",
         "«النتيجة» = بعد أن تقول القراءة صاعد (أو هابط)، كم مرّةً ذهب السعر في جهتها في الشمعة التالية والخمس التالية، ناقص"
         " ما يفعله السوق نفسه — وسط الخانات الثماني (سنتان · جهتان · مدّتان). «أسوأ خانة» أدناها. «فوق الصدفة» = الخانات"
         " الثماني كلّها أكبر من ضعف خطئها المعياريّ. «نجح من 100» = وسط الإصابة نفسها. «تقرأ من الوقت» = كم من 100 شمعة"
         " كانت لها قراءة (الدمج يقرأ فقط حين تتّفق الثلاثة). ولا تدخل قراءةٌ تقرأ أقلّ من %d من 100." % FIT_MIN_SHARE, "",
         "- عدد ما جُرّب: **%d قراءة** (%d لكلّ فريم: شموع %s متتالية · متوسّطات %s · السعر مع متوسّط %s · داو بحساسيّة %s"
         " · وكلّ دمجٍ للثلاثة). أعلى رقمٍ بين هذا العدد يأتي بالصدفة أيضًا." % (
             tries, tries // max(1, len(frames)), "/".join(map(str, FIT_RUNS)),
             " · ".join("/".join(map(str, o)) for o in FIT_ORDERS), "/".join(map(str, FIT_LINES)), "/".join(map(str, FIT_SPANS))), ""]
    L += ["## الخلاصة — الأعلى على كلّ فريم", "",
          "| الفريم | الأعلى | النتيجة (وسط) | أسوأ خانة | فوق الصدفة؟ | نجح من 100 | تقرأ من الوقت ٪ |", "|---|---|---|---|---|---|---|"]
    for fr in frames:
        top = ranked.get(fr) or []
        if top:
            b = top[0]
            L.append("| %s | %s | %+.2f | %+.2f | %s | %.1f | %.0f |" % (FRAME_AR[fr], b["name"], b["avg"], b["min"],
                                                                      "نعم" if b["steady"] else "لا", b["hit"], b["share"]))
    for fr in frames:
        top = ranked.get(fr) or []
        L += ["", "## %s — أعلى %d" % (FRAME_AR[fr], FIT_TOP), "",
              "| # | القراءة | النتيجة (وسط) | أسوأ خانة | فوق الصدفة؟ | نجح من 100 | تقرأ من الوقت ٪ |", "|---|---|---|---|---|---|---|"]
        for i, r in enumerate(top[:FIT_TOP], 1):
            L.append("| %d | %s | %+.2f | %+.2f | %s | %.1f | %.0f |" % (i, r["name"], r["avg"], r["min"],
                                                                       "نعم" if r["steady"] else "لا", r["hit"], r["share"]))
        mine = [r for r in top if r["name"] in ("الشموع 3 متتالية", "الشموع 3 + المتوسّطات 5/10/50 + داو 2")]
        for r in mine:
            L.append("| %d | %s (المعتمد اليوم) | %+.2f | %+.2f | %s | %.1f | %.0f |" % (
                top.index(r) + 1, r["name"], r["avg"], r["min"], "نعم" if r["steady"] else "لا", r["hit"], r["share"]))
    (folder / "النتيجة.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (folder / "الاختبار.md").write_text(
        "# ضبط الاتّجاه على الماضي — %s\n\n- الرمز: %s\n- السنتان: %s\n- الأطر: %s\n- عدد القراءات المجرّبة: %d\n- الزمن: %s\n" % (
            cfg.get("name", ""), SYMBOL_AR.get(sym, sym), " · ".join("%s إلى %s" % y for y in years),
            " · ".join(FRAME_AR[f] for f in frames), tries, _span(time.time() - began)), encoding="utf-8")
    (folder / "summary.json").write_text(json.dumps({"kind": "direction", "الاسم": cfg.get("name", ""), "عدد_المجرّب": tries,
                                                     "الأعلى": {FRAME_AR[f]: {k: v for k, v in (ranked.get(f) or [{}])[0].items()
                                                                               if k != "years"} for f in frames}},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


# ── calibrating the direction to the past as the eye sees it (owner, 2026-10-22, «NQ»: «هل صعد السوق أم هبط؟ … وأنت حين
#    تنظر إلى الشارت ترى الحركة كاملة، من القاع الذي بدأت منه إلى القمّة التي انتهت إليها … هيك لازم يتعاير بالبداية») ──
DESCRIBE_SIZES = {"صغيرة": 5.0, "متوسّطة": 10.0, "كبيرة": 20.0}   # a move = this many times the frame's median candle range
DESCRIBE_MIN_SHARE = 90.0


def zigzag_legs(hi: np.ndarray, lo: np.ndarray, threshold: float) -> np.ndarray:
    """The chart split into its completed moves, seen afterwards: a rise runs from a low to the high where a fall of at least
    `threshold` began, a fall the mirror. Every candle is labelled with the move it belonged to (+1 rise, −1 fall); the
    candles before the first move are 0. Hindsight on purpose: this is the eye's truth, never an input to a reading."""
    n = len(hi)
    labels = np.zeros(n, dtype=np.int8)
    if n < 2:
        return labels
    trend, first_side, hi_i, lo_i, pivots = 0, 0, 0, 0, []
    for i in range(1, n):
        if trend == 0:
            hi_i = i if hi[i] > hi[hi_i] else hi_i
            lo_i = i if lo[i] < lo[lo_i] else lo_i
            if hi[hi_i] - lo[lo_i] >= threshold:
                trend = first_side = 1 if lo_i < hi_i else -1
                pivots.append(lo_i if trend == 1 else hi_i)
        elif trend == 1:
            if hi[i] > hi[hi_i]:
                hi_i = i
            elif hi[hi_i] - lo[i] >= threshold:
                pivots.append(hi_i)
                trend, lo_i = -1, i
        else:
            if lo[i] < lo[lo_i]:
                lo_i = i
            elif hi[i] - lo[lo_i] >= threshold:
                pivots.append(lo_i)
                trend, hi_i = 1, i
    if not pivots:
        return labels
    side = first_side                                                # moves alternate from the first one
    bounds = pivots + [n - 1]
    for a, b in zip(bounds[:-1], bounds[1:]):
        labels[a + 1:b + 1] = side
        side = -side
    return labels


#: The owner (same message, «NQ»): «إذا مو صحيحة لازم تصحّحه لا يقول صح» -- the live wave corrects itself: it holds the
#: move it is in and turns the moment the price comes back this share of the wave size from the last extreme.
DESCRIBE_LIVE = [0.25, 0.5, 0.75, 1.0]


def zigzag_live(hi: np.ndarray, lo: np.ndarray, threshold: float) -> np.ndarray:
    """The same walk as `zigzag_legs`, read at each candle with only the candles up to it: +1 while in a confirmed rise,
    −1 in a confirmed fall, turning as soon as a turn of `threshold` is proven (0 before the first move)."""
    n = len(hi)
    out = np.zeros(n, dtype=np.int8)
    trend, hi_i, lo_i = 0, 0, 0
    for i in range(1, n):
        if trend == 0:
            hi_i = i if hi[i] > hi[hi_i] else hi_i
            lo_i = i if lo[i] < lo[lo_i] else lo_i
            if hi[hi_i] - lo[lo_i] >= threshold:
                trend = 1 if lo_i < hi_i else -1
        elif trend == 1:
            if hi[i] > hi[hi_i]:
                hi_i = i
            elif hi[hi_i] - lo[i] >= threshold:
                trend, lo_i = -1, i
        else:
            if lo[i] < lo[lo_i]:
                lo_i = i
            elif hi[i] - lo[lo_i] >= threshold:
                trend, hi_i = 1, i
        out[i] = trend
    return out


def known_waves(hi: np.ndarray, lo: np.ndarray, threshold: float) -> list[tuple[int, int, int, int]]:
    """The waves the system knows, in the order it learns them: (candle where it became known, start, end, side). A wave is
    known the moment the price turns from its end by the wave size -- the same walk as `zigzag_legs`, so it never changes."""
    n = len(hi)
    waves: list[tuple[int, int, int, int]] = []
    trend, hi_i, lo_i, last = 0, 0, 0, 0
    for i in range(1, n):
        if trend == 0:
            hi_i = i if hi[i] > hi[hi_i] else hi_i
            lo_i = i if lo[i] < lo[lo_i] else lo_i
            if hi[hi_i] - lo[lo_i] >= threshold:
                trend = 1 if lo_i < hi_i else -1
                last = lo_i if trend == 1 else hi_i
        elif trend == 1:
            if hi[i] > hi[hi_i]:
                hi_i = i
            elif hi[hi_i] - lo[i] >= threshold:
                waves.append((i, last, hi_i, 1))
                trend, last, lo_i = -1, hi_i, i
        else:
            if lo[i] < lo[lo_i]:
                lo_i = i
            elif hi[i] - lo[lo_i] >= threshold:
                waves.append((i, last, lo_i, -1))
                trend, last, hi_i = 1, lo_i, i
    return waves


EXAM_AHEAD = [1, 5, 20]


def _describe_year(sym: str, fr: str, y0: str, y1: str, live_market: bool = False) -> tuple[dict[tuple, dict], dict[str, tuple]]:
    """One frame and one year: every reading against the moves of the finished chart, and the known waves checked. With
    `live_market` also the real-market question (owner: «اختبره كأنّه سوق حقيقي»): after the reading spoke, did the price
    go its way over the next 1, 5 and 20 candles, against the market itself."""
    from shared.pips import to_pips
    p = DIRECTION_PERIOD_S[fr]
    t0, t1 = _epoch(y0), _epoch(y1)
    arr = np.array(_bars_db(sym, fr, t0 - DIRECTION_WARM_BARS * p, t1 + DIRECTION_WARM_BARS * p), dtype=float)
    out: dict[tuple, dict] = {}
    known: dict[str, tuple] = {}
    if len(arr) < DIRECTION_WARM_BARS:
        return out, known
    hi, lo, cl = arr[:, 2], arr[:, 3], arr[:, 4]
    inside = np.flatnonzero((arr[:, 0] >= t0) & (arr[:, 0] < t1))
    unit = float(np.median((hi - lo)[inside])) if len(inside) else 0.0
    readings = _fit_readings(hi, lo, cl, hold_combos=True)
    for size, k in DESCRIBE_SIZES.items():
        truth = zigzag_legs(hi, lo, k * unit)
        ok = inside[truth[inside] != 0]
        live = {"الموجة الحيّة تصحّح نفسها عند %d٪ من حجم الموجة" % round(100 * f): zigzag_live(hi, lo, f * k * unit)
                for f in DESCRIBE_LIVE}
        for name, state in {**readings, **live}.items():
            sel = ok[state[ok] != 0]
            if not len(sel):
                continue
            t, s = truth[sel], state[sel]
            out[(size, name)] = {"year": y0[:4], "agree": 100.0 * float((t == s).mean()),
                                 "share": 100.0 * len(sel) / max(1, len(ok)),
                                 "up": 100.0 * float((s[t == 1] == 1).mean()) if (t == 1).any() else float("nan"),
                                 "down": 100.0 * float((s[t == -1] == -1).mean()) if (t == -1).any() else float("nan"),
                                 "legs": int(np.count_nonzero(np.diff(truth[ok]) != 0)) + 1, "unit": unit * k}
            if live_market:
                out[(size, name)]["market"] = _ahead_stats(cl, inside, state, EXAM_AHEAD, float(to_pips(1.0, sym)))
        lo_t, hi_t = (int(inside[0]), int(inside[-1])) if len(inside) else (0, -1)
        waves = [w for w in known_waves(hi, lo, k * unit) if lo_t <= w[0] <= hi_t]
        right = sum(1 for _, a, b, side in waves if (truth[a + 1:b + 1] == side).all())
        known[size] = (len(waves), right, sum(b - a for _, a, b, _ in waves), k * unit)
    return out, known


def direction_exam(cfg: dict[str, Any], log=print) -> Path:
    """The official exam (owner, 2026-10-22: «قيسه على سنة بنفس الإعدادات بدون ما يعرف — باك تست رسمي»): the settings are
    chosen on the training years only, then applied unchanged to a year they never saw."""
    began = time.time()
    sym = cfg.get("symbol", "USTEC")
    frames = [f for f in cfg["frames"] if f in DIRECTION_PERIOD_S]
    train = [tuple(y) for y in cfg["train"]]
    test = tuple(cfg["test"])
    rows = []
    for fr in frames:
        trained: dict[tuple, list] = defaultdict(list)
        for y0, y1 in train:
            got, _ = _describe_year(sym, fr, y0, y1)
            for key, v in got.items():
                trained[key].append(v)
        exam, known = _describe_year(sym, fr, *test, live_market=True)
        for size in DESCRIBE_SIZES:
            cands = [(float(np.mean([v["agree"] for v in vs])), name) for (s, name), vs in trained.items()
                     if s == size and len(vs) == len(train) and min(v["share"] for v in vs) >= DESCRIBE_MIN_SHARE]
            if not cands:
                continue
            score, chosen = max(cands)
            got = exam.get((size, chosen))
            mine = exam.get((size, "الشموع 3 متتالية"))
            n_w, right, candles, wave_pts = known.get(size, (0, 0, 0, 0.0))
            rows.append({"frame": fr, "size": size, "chosen": chosen, "train": score,
                         "test": got["agree"] if got else float("nan"), "mine": mine["agree"] if mine else float("nan"),
                         "waves": n_w, "right": right, "candles": candles, "points": wave_pts,
                         "market": got.get("market") if got else None})
        log("الامتحان: %s انتهى" % FRAME_AR[fr])
    folder = OUT_ROOT / date.today().isoformat() / safe("امتحان الاتّجاه على %s — %s" % (test[0][:4], SYMBOL_AR.get(sym, sym)))
    folder.mkdir(parents=True, exist_ok=True)
    L = ["# امتحان الاتّجاه على سنة %s — %s" % (test[0][:4], SYMBOL_AR.get(sym, sym)), "",
         "قول المالك: «قيسه على سنة بنفس الإعدادات بدون ما يعرف — باك تست رسمي — وشوف كم راح يطلع صح».", "",
         "- **الإعدادات:** اختيرت على %s وحدهما (الأعلى تطابقًا مع موجات الماضي لكلّ فريم وحجم)، ثمّ طُبّقت كما هي على %s"
         " التي لم تُرَ." % (" و".join(y[0][:4] for y in train), test[0][:4]),
         "- **الموجات المعروفة:** كلّ موجةٍ قال الجهاز إنّه عرفها في %s (انتهت بقاعٍ أو قمّة ارتدّ عنها السعر بحجم موجة)،"
         " وهل هي موجة الشارت المنتهي نفسها، شمعةً شمعة." % test[0][:4],
         "- **الموجة الجارية:** كم من 100 شمعة قال الإعداد المختار الموجة التي كانت فيها، بما عرفه يومها فقط.", "",
         "| الفريم | حجم الموجة | بالنقاط | موجات عرفها | صحيحة | الإعداد المختار | على سنتي التدريب | على %s | الشموع 3 على %s |" % (
             test[0][:4], test[0][:4]), "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %.0f | %d | %d (%.0f٪) | %s | %.1f | **%.1f** | %.1f |" % (
            FRAME_AR[r["frame"]], r["size"], r["points"], r["waves"], r["right"],
            100.0 * r["right"] / r["waves"] if r["waves"] else float("nan"), r["chosen"], r["train"], r["test"], r["mine"]))
    L += ["", "> الجدول أعلاه **وصفٌ** لا امتحان سوق: «صحيحة» = وصفُ موجةٍ انتهت، و«على %s» = هل وصف الموجة التي كانت فيها"
          " الشمعة — والجواب يُعرف من الشارت بعد انتهائه." % test[0][:4], "",
          "## كأنّه سوقٌ حقيقيّ — يقول الآن، فماذا فعل السعر بعده؟ (%s، لم يُرَ)" % test[0][:4], "",
          "عند كلّ شمعةٍ تُغلق، بما قبلها فقط: الإعداد المختار يقول صاعد أو هابط. ثمّ هل أغلق السعر في جهته بعد شمعة وبعد 5"
          " وبعد 20 — مقابل السوق نفسه (كم مرّة صعد أو نزل بعد أيّ شمعة). «الفرق» = أصاب ناقص السوق، و«±» ضعف خطئه"
          " المعياريّ، والنقاط بالبِب في جهته.", "",
          "| الفريم | الحجم | المدّة | قال صاعد: لحظات · أصاب · السوق · الفرق ± · نقاط | قال هابط: لحظات · أصاب · السوق · الفرق ± · نقاط |",
          "|---|---|---|---|---|"]
    for r in rows:
        m = r.get("market") or {}
        for k in EXAM_AHEAD:
            parts = []
            for side in (1, -1):
                cell = m.get("%d %d" % (k, side))
                parts.append("%d · %.1f · %.1f · %+.1f ±%.1f · %+.1f" % cell if cell and cell[0] else "—")
            L.append("| %s | %s | %s | %s | %s |" % (FRAME_AR[r["frame"]], r["size"], "شمعة" if k == 1 else "%d شمعة" % k, *parts))
    (folder / "النتيجة.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (folder / "الاختبار.md").write_text(
        "# امتحان الاتّجاه — %s\n\n- الرمز: %s\n- التدريب: %s\n- الامتحان: %s إلى %s\n- الأطر: %s\n- الزمن: %s\n" % (
            test[0][:4], SYMBOL_AR.get(sym, sym), " · ".join("%s إلى %s" % y for y in train), test[0], test[1],
            " · ".join(FRAME_AR[f] for f in frames), _span(time.time() - began)), encoding="utf-8")
    (folder / "summary.json").write_text(json.dumps({"kind": "direction", "الاسم": "امتحان %s" % test[0][:4], "النتائج": rows},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


# ── teaching the system (owner, 2026-10-22: «نظام بدّك تعلّمو … فرجيه شارت كامل مشان يتعلّم كيف ينقرا منه حركة ويظبط إعداداته
#    عليها مشان يحسن يتوقّع مستقبل … مثل طفل جبته عم تقلّه تداول») -- the finished charts of the training years are the
#    teacher (the waves the eye sees, and where the price went), the student sees only what came before each candle, and the
#    exam is a year it never saw, graded as a real market ──
LEARN_HEAVY = {"M5": ["M15", "H1", "H4"], "M15": ["H1", "H4", "D1"], "H1": ["H4", "D1"]}
LEARN_ATR = 50
LEARN_WAVE_SIZE = 10.0
LEARN_FUTURE = 5
LEARN_SURE = 0.6
LEARN_PARAMS = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 200,
                "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8, "n_estimators": 300, "verbose": -1}


def _rolling(x: np.ndarray, n: int, fn) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = fn(np.lib.stride_tricks.sliding_window_view(x, n), axis=1)
    return out


def learn_frame_features(hi: np.ndarray, lo: np.ndarray, cl: np.ndarray, wave_threshold: float) -> dict[str, np.ndarray]:
    """What a trader reads on one frame at each close, from that close and the candles before it only."""
    from shared import direction_rule as rule
    atr = _rolling(hi - lo, LEARN_ATR, np.mean)
    ema = {n: _ema(cl, n) for n in (5, 10, 20, 50, 200)}
    c3 = rule.directions(hi, lo, 3)
    feats = {"شموع 2": rule.directions(hi, lo, 2), "شموع 3": c3, "شموع 4": rule.directions(hi, lo, 4),
             "منذ كم شمعة": rule.since(c3).astype(float),
             "متوسّطات 5/10/50": _order_states([ema[5], ema[10], ema[50]]),
             "متوسّطات 20/50/200": _order_states([ema[20], ema[50], ema[200]]),
             "داو": _dow_states(cl, 2), "الموجة الحيّة": zigzag_live(hi, lo, wave_threshold)}
    for n in (20, 50, 200):
        feats["بعد السعر عن متوسّط %d" % n] = (cl - ema[n]) / atr
    for n in (1, 3, 10, 30):
        prev = np.concatenate([np.full(n, np.nan), cl[:-n]])
        feats["حركة آخر %d شمعة" % n] = (cl - prev) / atr
    for n in (20, 100):
        top, bottom = _rolling(hi, n, np.max), _rolling(lo, n, np.min)
        feats["موقع السعر في آخر %d شمعة" % n] = (cl - bottom) / np.where(top > bottom, top - bottom, np.nan)
    return feats


#: «غذّيه معلومات وأدوات — عنّا أدوات كتيرة وأقسام كتيرة» (owner, 2026-10-22): what else the student may read, every one
#: of it known before the candle closes -- the five sections' facts (the facts store), the related markets, the red dollar
#: news (their times are scheduled in advance) and yesterday's and last week's levels.
LEARN_RELATED = ["US500", "US30", "XAUUSD", "EURUSD"]
LEARN_SECTION_FRAMES = {"M5": ["5m"], "M15": ["15m", "1h"], "H1": ["1h", "4h"]}
LEARN_NEWS_CAP_MIN = 2880.0
LEARN_FACT_MAX_AGE_S = 3.5 * 86400            # a long weekend and a little: the market's longest normal silence
_SKIP_KEYS = ("as_of", "computed_on", "period_start", "timestamp", "section_id", "atom_id",
              # 2026-10-23: counters and calendar dates tell the student which year it is, not what the market does --
              # the first sections run leaned on «analysis_maturity» (grows from the store's first candle) and a date
              "maturity", "date", "count", "samples", "version", "seq")
_SKIP_TAILS = ("close", "open", "high", "low", "price", "level", "value", "start", "_at", "time", "candles", "bars", ".n")


def _stores_for(sym: str, years: list[tuple[str, str]], log) -> list[Path | None]:
    """The full facts store of each year; the machine builds the missing ones first, all at once -- the owner, 2026-10-22:
    «سرّعه أكثر» (a year takes hours; each build is one process, so they run side by side)."""
    import subprocess
    paths = [STORE / sym / ("%s_%s" % (y0, y1)) for y0, y1 in years]

    def launch(y0: str, y1: str, path: Path, extra: list[str]):
        return subprocess.Popen([sys.executable, "-m", "backtest.facts_store", "--symbol", sym, "--from", y0, "--to", y1,
                                 "--warm-days", "60", "--out", str(path), *extra], cwd=str(ROOT))

    # 2026-10-23 (the owner: «حاول إنقاذ الـ92٪ المبنيّة أوّلًا»): a store cut before its end is rescued first.
    cut = [(y, p) for y, p in zip(years, paths) if not (p / "index.json").exists() and p.exists() and any(p.iterdir())]
    if cut:
        log("التعليم: يحاول الجهاز إنقاذ %d مخزن انقطع قبل آخره …" % len(cut))
        for job in [launch(y0, y1, p, ["--recover"]) for (y0, y1), p in cut]:
            job.wait()
    jobs = []
    for (y0, y1), path in zip(years, paths):
        if not (path / "index.json").exists():
            log("التعليم: يبني الجهاز مخزن حقائق الأقسام لسنة %s …" % y0[:4])
            jobs.append(launch(y0, y1, path, []))
    for job in jobs:
        job.wait()
    return [path if (path / "index.json").exists() else None for path in paths]


def _section_fields(store: Facts, frames: list[str]) -> set[tuple[str, str, str]]:
    out = set()
    for g in store.index["groups"]:
        if g["frame"] not in frames:
            continue
        for f in g["fields"]:
            key = f["key"]
            tail = key.rsplit(".", 1)[-1]
            if any(s in key for s in _SKIP_KEYS) or tail.endswith(_SKIP_TAILS):
                continue
            out.add((g["atom"], g["frame"], key))
    return out


def _store_words(stores: list[Facts], fields: list[tuple[str, str, str]]) -> dict[tuple, dict[str, int]]:
    """One numbering of each word fact's words across every store (each store numbers its words in the order it first
    met them, so the same code can mean different words in two years -- found 2026-10-23)."""
    out: dict[tuple, dict[str, int]] = {}
    for key in fields:
        words: set[str] = set()
        for st in stores:
            hit = st.find(*key)
            if hit is not None and hit[1]["kind"] == "word":
                words.update(hit[1]["vocab"] or [])
        if words:
            out[key] = {w: i for i, w in enumerate(sorted(words))}
    return out


def _store_until(stores: list[Facts]) -> float:
    return max(float(st.index.get("to") or 0.0) for st in stores)


def _section_columns(stores: list[Facts], fields: list[tuple[str, str, str]], close_t: np.ndarray,
                     words: dict[tuple, dict[str, int]]) -> dict[str, np.ndarray]:
    """For every fact: the latest value each section published at or before the candle's close (a word by its one shared
    number), across the stores of the years the table spans -- and nothing after the last day the stores hold."""
    cols: dict[str, np.ndarray] = {}
    until = _store_until(stores)
    for atom, frame, key in fields:
        ts, vs = [], []
        for st in stores:
            got = st.series(atom, frame, key)
            if got is None or not len(got[0]):
                continue
            n = min(len(got[0]), len(got[1]))
            v = got[1][:n].astype(np.float64)
            if got[2]["kind"] == "word":
                vocab = got[2]["vocab"] or []
                table = np.array([words.get((atom, frame, key), {}).get(w, np.nan) for w in vocab] + [np.nan])
                v = table[np.where((v >= 0) & (v < len(vocab)), v, len(vocab)).astype(int)]
            ts.append(got[0][:n])
            vs.append(v)
        if not ts:
            continue
        t, v = np.concatenate(ts), np.concatenate(vs)
        order = np.argsort(t, kind="stable")
        # a fact older than LEARN_FACT_MAX_AGE_S is no fact: a rescued store holds its sparse groups only up to their last
        # written batch (the hour frame until summer), and the last value must not stand in for months it never saw
        vals, ok = Facts.at(t[order], v[order], close_t, LEARN_FACT_MAX_AGE_S)
        ok &= close_t <= until
        name = stores[0].index.get("names", {}).get(atom, atom)
        label = "ذرّة %s «%s» على %s · %s" % (atom, name, frame, key)
        cols[label] = np.where(ok, vals, np.nan).astype(np.float32)
    return cols


def _rich_columns(sym: str, target: str, bars: np.ndarray, close_t: np.ndarray, atr: np.ndarray,
                  thresholds: dict[str, float], t_from: float, t_to: float) -> dict[str, np.ndarray]:
    cols: dict[str, np.ndarray] = {}
    p = DIRECTION_PERIOD_S[target]
    for other in LEARN_RELATED:
        ob = np.array(_bars_db(other, target, t_from - DIRECTION_WARM_BARS * p, t_to + DIRECTION_WARM_BARS * p), dtype=float)
        if not len(ob):
            continue
        idx = np.searchsorted(ob[:, 0] + p, close_t, side="right") - 1
        thr = thresholds.get((other, target)) or LEARN_WAVE_SIZE * float(np.median(ob[:, 2] - ob[:, 3]))
        for k, v in learn_frame_features(ob[:, 2], ob[:, 3], ob[:, 4], thr).items():
            cols["%s · %s" % (SYMBOL_AR.get(other, other), k)] = np.where(idx >= 0, v[np.clip(idx, 0, None)], np.nan)
    red = news_times({"on": True, "colors": ["red"], "currencies": ["USD"]}, t_from - 86400 * 7, t_to + 86400 * 7)
    if len(red):
        j = np.searchsorted(red, close_t, side="right")
        last = np.where(j > 0, red[np.clip(j - 1, 0, None)], np.nan)
        nxt = np.where(j < len(red), red[np.clip(j, 0, len(red) - 1)], np.nan)
        cols["دقائق منذ آخر خبرٍ أحمر للدولار"] = np.minimum((close_t - last) / 60.0, LEARN_NEWS_CAP_MIN)
        cols["دقائق حتّى الخبر الأحمر القادم"] = np.minimum((nxt - close_t) / 60.0, LEARN_NEWS_CAP_MIN)
    cl = bars[:, 4]
    for frame, label in (("D1", "الأمس"), ("W1", "الأسبوع الماضي")):
        pf = DIRECTION_PERIOD_S[frame]
        lv = np.array(_bars_db(sym, frame, t_from - 400 * 86400, t_to + 86400 * 8), dtype=float)
        if not len(lv):
            continue
        prev = np.searchsorted(lv[:, 0] + pf, close_t, side="right") - 1        # the last closed day or week
        ok = prev >= 0
        safe = np.clip(prev, 0, None)
        for col, name in ((2, "قمّة"), (3, "قاع"), (4, "إغلاق")):
            cols["بعد السعر عن %s %s" % (name, label)] = np.where(ok, (cl - lv[safe, col]) / atr, np.nan)
        if frame == "D1":
            cur = np.searchsorted(lv[:, 0], close_t, side="right") - 1          # today's candle: its open is known
            cols["بعد السعر عن افتتاح اليوم"] = np.where(cur >= 0, (cl - lv[np.clip(cur, 0, None), 1]) / atr, np.nan)
    return cols


def _learn_table(sym: str, target: str, t_from: float, t_to: float, thresholds: dict[str, float],
                 beyond: bool, rich: bool = False, sections: tuple[list, list] | None = None) -> dict[str, Any]:
    """The student's table for one target frame: its own reading and its heavier frames' (closed candles only), and time.
    `beyond` lets candles after `t_to` in (only to grade the exam year; the teaching chart stops at its end). `rich` adds
    the related markets, the news and the levels; `sections` (stores, fields) the five sections' facts."""
    p = DIRECTION_PERIOD_S[target]
    bars = np.array(_bars_db(sym, target, t_from - DIRECTION_WARM_BARS * p, t_to + (DIRECTION_WARM_BARS * p if beyond else 0)),
                    dtype=float)
    ts, hi, lo, cl = bars[:, 0], bars[:, 2], bars[:, 3], bars[:, 4]
    close_t = ts + p
    cols: dict[str, np.ndarray] = {"%s · %s" % (FRAME_AR[target], k): v
                                   for k, v in learn_frame_features(hi, lo, cl, thresholds[target]).items()}
    for heavy in LEARN_HEAVY[target]:
        ph = DIRECTION_PERIOD_S[heavy]
        hb = np.array(_bars_db(sym, heavy, t_from - DIRECTION_WARM_BARS * ph, t_to + ph), dtype=float)
        if not len(hb):
            continue
        idx = np.searchsorted(hb[:, 0] + ph, close_t, side="right") - 1          # the last heavy candle already closed
        for k, v in learn_frame_features(hb[:, 2], hb[:, 3], hb[:, 4], thresholds[heavy]).items():
            cols["%s · %s" % (FRAME_AR[heavy], k)] = np.where(idx >= 0, v[np.clip(idx, 0, None)], np.nan)
    cols["ساعة اليوم"] = (close_t % 86400) / 3600.0
    cols["يوم الأسبوع"] = np.array([datetime.fromtimestamp(t, timezone.utc).weekday() for t in close_t], dtype=float)
    if rich:
        cols.update(_rich_columns(sym, target, bars, close_t, _rolling(hi - lo, LEARN_ATR, np.mean), thresholds, t_from, t_to))
    if sections:
        cols.update(_section_columns(sections[0], sections[1], close_t, sections[2]))
    names = list(cols)
    return {"X": np.column_stack([cols[n] for n in names]).astype(np.float32), "names": names, "ts": ts, "hi": hi, "lo": lo,
            "cl": cl, "inside": np.flatnonzero((ts >= t_from) & (ts < t_to))}


def direction_learn(cfg: dict[str, Any], log=print) -> Path:
    """Two students per frame, both taught on the training years only: one learns the wave each candle is in (the eye's
    reading of the finished chart), one learns where the price stood LEARN_FUTURE candles later. The teaching chart stops
    at the end of the training years, so nothing of the exam year reaches a label. Then the unseen year, as a market: each
    says up or down from the past alone, and the price after it is compared with the market itself."""
    import lightgbm as lgb
    from shared.pips import to_pips
    began = time.time()
    sym = cfg.get("symbol", "USTEC")
    train = [tuple(y) for y in cfg["train"]]
    test = tuple(cfg["test"])
    pip = float(to_pips(1.0, sym))
    t_train0, t_train1 = _epoch(train[0][0]), _epoch(train[-1][1])
    t_test0, t_test1 = _epoch(test[0]), _epoch(test[1])
    frames_needed = {f for t in cfg["targets"] for f in [t] + LEARN_HEAVY[t]}
    thresholds = {}
    for f in frames_needed:                                       # the wave size from the training years only
        b = np.array(_bars_db(sym, f, t_train0, t_train1), dtype=float)
        thresholds[f] = LEARN_WAVE_SIZE * float(np.median(b[:, 2] - b[:, 3])) if len(b) else 0.0
    if cfg.get("rich"):
        for other in LEARN_RELATED:
            for f in cfg["targets"]:
                b = np.array(_bars_db(other, f, t_train0, t_train1), dtype=float)
                thresholds[(other, f)] = LEARN_WAVE_SIZE * float(np.median(b[:, 2] - b[:, 3])) if len(b) else 0.0
    rich = bool(cfg.get("rich"))
    train_stores = test_stores = None
    if cfg.get("sections"):
        *built, exam_store = _stores_for(sym, train + [test], log)
        if all(built) and exam_store:
            train_stores, test_stores = [Facts(b) for b in built], [Facts(exam_store)]
        else:
            log("التعليم: مخزنٌ ناقص — يكمل بلا حقائق الأقسام")
    rows, importance = [], {}
    for target in cfg["targets"]:
        sec_tr = sec_te = None
        if train_stores:
            frames_ = LEARN_SECTION_FRAMES[target]
            common = set.intersection(*[_section_fields(s, frames_) for s in train_stores + test_stores])
            fields = sorted(common)
            words = _store_words(train_stores + test_stores, fields)
            sec_tr, sec_te = (train_stores, fields, words), (test_stores, fields, words)
        tr = _learn_table(sym, target, t_train0, t_train1, thresholds, beyond=False, rich=rich, sections=sec_tr)
        te = _learn_table(sym, target, t_test0, t_test1, thresholds, beyond=True, rich=rich, sections=sec_te)
        if test_stores:                         # the exam stops where the exam year's store stops (a rescued store ends early)
            exam_until = _store_until(test_stores)
            te["inside"] = te["inside"][te["ts"][te["inside"]] + DIRECTION_PERIOD_S[target] <= exam_until]
            out_until = datetime.fromtimestamp(exam_until, timezone.utc).strftime("%Y-%m-%d")
        else:
            out_until = test[1]
        if tr["names"] != te["names"]:                                # the same columns in the same order, or no exam
            keep = [n for n in tr["names"] if n in set(te["names"])]
            tr["X"] = tr["X"][:, [tr["names"].index(n) for n in keep]]
            te["X"] = te["X"][:, [te["names"].index(n) for n in keep]]
            tr["names"] = te["names"] = keep
        teach_wave = zigzag_legs(tr["hi"], tr["lo"], thresholds[target])
        fut = np.concatenate([tr["cl"][LEARN_FUTURE:] - tr["cl"][:-LEARN_FUTURE], np.full(LEARN_FUTURE, np.nan)])
        out: dict[str, Any] = {"frame": target, "rows_train": int(len(tr["inside"])), "rows_test": int(len(te["inside"])),
                               "features": len(tr["names"]), "until": out_until}
        exam_wave = zigzag_legs(te["hi"], te["lo"], thresholds[target])
        for kind, label in (("الموجة", teach_wave), ("بعد %d شموع" % LEARN_FUTURE, np.sign(fut))):
            sel = tr["inside"][(label[tr["inside"]] != 0) & np.isfinite(label[tr["inside"]])]
            # the core API: the scikit-learn wrapper needs a library this runtime does not carry
            params = {k: v for k, v in LEARN_PARAMS.items() if k != "n_estimators"}
            model = lgb.train(params, lgb.Dataset(tr["X"][sel], (label[sel] > 0).astype(int)),
                              num_boost_round=LEARN_PARAMS["n_estimators"])
            prob = np.full(len(te["cl"]), np.nan)
            prob[te["inside"]] = model.predict(te["X"][te["inside"]])
            always = np.where(prob >= 0.5, 1, -1).astype(np.int8)
            always[~np.isfinite(prob)] = 0
            sure = np.where(prob >= LEARN_SURE, 1, np.where(prob <= 1 - LEARN_SURE, -1, 0)).astype(np.int8)
            sure[~np.isfinite(prob)] = 0
            graded = te["inside"][exam_wave[te["inside"]] != 0]
            out[kind] = {"wave_agree": 100.0 * float((always[graded] == exam_wave[graded]).mean()) if len(graded) else float("nan"),
                         "market": _ahead_stats(te["cl"], te["inside"], always, EXAM_AHEAD, pip),
                         "sure_market": _ahead_stats(te["cl"], te["inside"], sure, EXAM_AHEAD, pip),
                         "sure_share": 100.0 * float((sure[te["inside"]] != 0).mean())}
            gain = model.feature_importance(importance_type="gain")
            importance["%s · %s" % (FRAME_AR[target], kind)] = [tr["names"][i] for i in np.argsort(gain)[::-1][:8]]
        rows.append(out)
        log("التعليم: %s انتهى" % FRAME_AR[target])
    fed = ("بالأقسام والأدوات" if train_stores else "بالأدوات") if rich else "بالشارت"
    folder = OUT_ROOT / date.today().isoformat() / safe("تعليم الاتّجاه %s — تعلّم على %s وامتُحن على %s" % (
        fed, " و".join(y[0][:4] for y in train), test[0][:4]))
    folder.mkdir(parents=True, exist_ok=True)
    L = ["# تعليم الاتّجاه — %s" % SYMBOL_AR.get(sym, sym), "",
         "قول المالك: «نظام بدّك تعلّمو … فرجيه شارت كامل مشان يتعلّم كيف ينقرا منه حركة ويظبط إعداداته عليها مشان يحسن يتوقّع"
         " مستقبل».", "",
         "- **الأستاذ:** شارت %s كاملًا بعد انتهائه — لكلّ شمعة موجتها كما تراها العين (حجم الموجة %g ضعف وسط مدى الشمعة)،"
         " وأين كان السعر بعد %d شموع." % (" و".join(y[0][:4] for y in train), LEARN_WAVE_SIZE, LEARN_FUTURE),
         "- **التلميذ:** نموذج تعلّم (أشجار متدرّجة) يرى عند كلّ شمعة ما قبلها فقط، على فريمه وأطره الأثقل (المغلق منها فقط):"
         " الشموع المتتالية · المتوسّطات · داو · الموجة الحيّة · بعد السعر عن المتوسّطات · حركة آخر الشموع · موقع السعر في"
         " مداه · ساعة اليوم ويوم الأسبوع.",
         "- **تلميذان لكلّ فريم:** الأوّل تعلّم الموجة، والثاني تعلّم أين يكون السعر بعد %d شموع." % LEARN_FUTURE,
         "- **ما غُذّي به فوق الشارت:** %s." % (" · ".join(
             (["الأسواق المرتبطة (%s)" % "، ".join(SYMBOL_AR.get(s, s) for s in LEARN_RELATED),
               "أخبار الدولار الحمراء (منذ آخرها وحتّى القادم)", "مستويات الأمس والأسبوع الماضي وافتتاح اليوم"] if rich else [])
             + (["حقائق الأقسام الخمسة من مخازنها (51 ذرّة)"] if train_stores else [])) or "لا شيء"),
         "- **الامتحان:** سنة %s التي لم يرها، كأنّها سوقٌ حقيقيّ: يقول صاعد أو هابط بما قبل اللحظة فقط، ثمّ ما فعله السعر"
         " بعد 1 و5 و20 شمعة مقابل السوق نفسه. و«الواثق» = يقول فقط حين احتماله %d٪ أو أكثر." % (test[0][:4], round(100 * LEARN_SURE)),
         ""]
    for r in rows:
        L += ["## %s — تعلّم على %d شمعة، وامتُحن على %d حتّى %s، بـ%d معلومة" % (
                  FRAME_AR[r["frame"]], r["rows_train"], r["rows_test"], r["until"], r["features"]), "",
              "| التلميذ | وصف الموجة على %s | المدّة | قال صاعد: لحظات · أصاب · السوق · الفرق ± · نقاط | قال هابط: لحظات · أصاب · السوق ·"
              " الفرق ± · نقاط | الواثق: يقول من الوقت ٪ · صاعد: الفرق ± | الواثق · هابط: الفرق ± |" % test[0][:4],
              "|---|---|---|---|---|---|---|"]
        for kind in ("الموجة", "بعد %d شموع" % LEARN_FUTURE):
            g = r[kind]
            for k in EXAM_AHEAD:
                cells = []
                for side in (1, -1):
                    c = g["market"]["%d %d" % (k, side)]
                    cells.append("%d · %.1f · %.1f · %+.1f ±%.1f · %+.1f" % c if c[0] else "—")
                sure = []
                for side in (1, -1):
                    c = g["sure_market"]["%d %d" % (k, side)]
                    sure.append("%+.1f ±%.1f (%d)" % (c[3], c[4], c[0]) if c[0] else "—")
                L.append("| %s | %.1f | %s | %s | %s | %.0f · %s | %s |" % (
                    kind, g["wave_agree"], "شمعة" if k == 1 else "%d شمعة" % k, *cells, g["sure_share"], *sure))
        L.append("")
    L += ["## ماذا اعتمد التلميذ أكثر (أعلى ثمانٍ)", ""]
    for key, names in importance.items():
        L.append("- **%s:** %s" % (key, " · ".join(names)))
    (folder / "النتيجة.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (folder / "الاختبار.md").write_text(
        "# تعليم الاتّجاه\n\n- الرمز: %s\n- التعلّم: %s\n- الامتحان: %s إلى %s\n- الأطر: %s\n- الزمن: %s\n" % (
            SYMBOL_AR.get(sym, sym), " · ".join("%s إلى %s" % y for y in train), test[0], test[1],
            " · ".join(FRAME_AR[t] for t in cfg["targets"]), _span(time.time() - began)), encoding="utf-8")
    (folder / "summary.json").write_text(json.dumps({"kind": "direction", "الاسم": "تعليم الاتّجاه", "النتائج": rows,
                                                     "الأهمّ": importance}, ensure_ascii=False, indent=1, default=float),
                                         encoding="utf-8")
    return folder


# ── the strategy search: build the trade, not the direction (the owner's paper of 2026-10-23, sealed «NQ») ────────────
#: «بحث برمجيّ عن استراتيجيّة رابحة على مدار سنوات ماضية وسنوات قادمة» -- what earned money was the trade's construction
#: (entry, stop, targets), not knowing the direction. For every five-minute close and each side: had we entered now with
#: the structure stop and the three thirds, what was the net in risk units after the cost -- every red line applied. The
#: student learns that answer from the tools' 147 readings (`_learn_table`, rich) and trades only when it expects more
#: than a margin above the cost. Exam: each year taught on the years before it only, then traded as a market.
SEARCH_FRAME = "M5"
SEARCH_TRAIN_FROM = "2018-01-01"
SEARCH_MARGIN_R = 0.10
SEARCH_MIN_TRADES = 30
SEARCH_PARAMS = {"objective": "regression", "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 200,
                 "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8, "verbose": -1}
SEARCH_ROUNDS = 300
#: the engine's STOP_FRAMES order (`_stop`): five minutes, then the quarter hour, then the minute
SEARCH_SWING_FRAMES = (("M5", 300), ("M15", 900), ("M1", 60))
SEARCH_SWING_WARM_S = 7 * 86400
SEARCH_GROUPS = ("التلميذ", "مرجع: الصفقات نفسها بجهة عشوائيّة")


def swing_lookback() -> int:
    """Atom 201's `lookback` from its manifest -- the candles on each side of a swing (8 on 2026-10-23; a comment in the
    atom still says 2, the manifest is what the live atom and the facts store run)."""
    text = (ROOT / "atoms" / "قسم 200-249" / "201_القمم_والقيعان" / "manifest.yaml").read_text(encoding="utf-8")
    found = re.search(r"^\s*lookback:\s*(\d+)\s*$", text, re.M)
    if not found:
        raise SystemExit("لا عدد شموعٍ في بيان الذرّة 201")
    return int(found.group(1))


def confirmed_swings(hi: np.ndarray, lo: np.ndarray, close_t: np.ndarray,
                     side: int | None = None) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Atoms 201 and 202 on candles: a candle strictly higher than the `side` candles before it and the `side` after it is
    a swing high -- else, strictly lower than all of them, a swing low (201 names one signal per candle, the high first);
    known only when the `side`-th candle after it closes, and 202 keeps the latest of each. Per kind: (the moment it
    became known, its price), in time order."""
    side = swing_lookback() if side is None else side
    empty = (np.zeros(0), np.zeros(0))
    n = len(hi)
    if n < 2 * side + 1:
        return {"high": empty, "low": empty}
    c = np.arange(side, n - side)
    up, down = np.ones(len(c), dtype=bool), np.ones(len(c), dtype=bool)
    for k in range(1, side + 1):
        up &= (hi[c] > hi[c - k]) & (hi[c] > hi[c + k])
        down &= (lo[c] < lo[c - k]) & (lo[c] < lo[c + k])
    down &= ~up
    known = close_t[c + side]
    return {"high": (known[up], hi[c][up]), "low": (known[down], lo[c][down])}


def structure_stops(swings: list[dict[str, tuple[np.ndarray, np.ndarray]]], moments: np.ndarray, entry: np.ndarray,
                    side: int, lo: float, hi: float, pad: float) -> np.ndarray:
    """The engine's `_stop` (method structure) for many moments at once: on each frame in order, the latest known swing low
    (buy) or high (sell), a pad behind it -- the first whose distance lies within [lo, hi]. NaN where none does."""
    stop = np.full(len(moments), np.nan)
    for sw in swings:
        known, price = sw["low" if side > 0 else "high"]
        if not len(known):
            continue
        idx = np.searchsorted(known, moments, side="right") - 1
        level = price[np.clip(idx, 0, None)]
        cand = level - pad if side > 0 else level + pad
        risk = (entry - cand) * side
        take = (idx >= 0) & np.isnan(stop) & (risk >= lo) & (risk <= hi)
        stop[take] = cand[take]
    return stop


def _day_refs(ranges: dict[date, float], days: set[date]) -> dict[date, float | None]:
    """`_ref` for every day at once (the median of the five days before it, three at least), without re-sorting per call."""
    import bisect
    have = sorted(ranges)
    out: dict[date, float | None] = {}
    for d in days:
        k = bisect.bisect_left(have, d)
        vals = sorted(ranges[x] for x in have[max(0, k - 5):k])
        out[d] = vals[len(vals) // 2] if len(vals) >= 3 else None
    return out


def search_trade(side: int, m: float, price: float, stop: float, left: float, reason: str,
                 minutes: tuple[list, list, list, list], targets: list, be_after: int, trail_after: int,
                 trail_to_r: float, cost: float) -> "Trade":
    """One hypothetical trade exactly as `run` walks it: minute by minute from the decision close, the stop first when a
    minute reaches both, closed whole at the first minute past the nearest red line or the time before the red news."""
    import bisect
    mt, mh, ml, mc = minutes
    tr = Trade("", side, m, price, stop, targets, be_after, trail_after, trail_to_r, cost)
    j = bisect.bisect_right(mt, m)
    end = m + left
    while j < len(mt):
        t = mt[j]
        if t > end:
            tr.close(min(t, end), mc[j - 1], reason)          # at the red line itself (see `run`)
            return tr
        if tr.minute(t, mh[j], ml[j]):
            return tr
        j += 1
    tr.close(mt[-1], mc[-1], "end_of_data")
    return tr


def _search_answers(sym: str, y0: float, y1: float, cfg: dict[str, Any], news: np.ndarray,
                    why: dict[str, int]) -> dict[str, Any]:
    """The answer for one year: every five-minute close the red lines allow, and for each side its trade (or none)."""
    from shared import market_clock, red_lines
    p = DIRECTION_PERIOD_S[SEARCH_FRAME]
    bars = np.array(_bars_db(sym, SEARCH_FRAME, y0, y1), dtype=float)
    if not len(bars):
        return {"m": np.zeros(0), "price": np.zeros(0), 1: [], -1: []}
    moments, closes = bars[:, 0] + p, bars[:, 4]
    nb, na, first_s = cfg["news_before_s"], cfg["news_after_s"], cfg["first_s"]
    keep = np.zeros(len(moments), dtype=bool)
    for i, m in enumerate(moments):
        inside, opened = red_lines.session_state(float(m), sym)
        if not inside or (opened is not None and m - opened < first_s):
            why["outside_window_or_first_minutes"] += 1
            continue
        if market_clock.no_trade_day(float(m)):
            why["no_trade_day"] += 1
            continue
        k = int(np.searchsorted(news, m))
        if [x for x in news[max(0, k - 1):k + 1] if -nb <= m - x <= na]:
            why["news_window"] += 1
            continue
        if red_lines.in_last_hour(float(m), sym):          # 2026-10-25 (owner seal, law 21): nothing new in the last hour
            why["last_hour"] += 1
            continue
        keep[i] = True
    moments, closes = moments[keep], closes[keep]
    swings = []
    for period, ps in SEARCH_SWING_FRAMES:
        sb = np.array(_bars_db(sym, period, y0 - SEARCH_SWING_WARM_S, y1), dtype=float)
        swings.append(confirmed_swings(sb[:, 2], sb[:, 3], sb[:, 0] + ps) if len(sb) else
                      {"high": (np.zeros(0), np.zeros(0)), "low": (np.zeros(0), np.zeros(0))})
    lo, hi = cfg["band"]
    stops = {s: structure_stops(swings, moments, closes, s, lo, hi, cfg["pad"]) for s in (1, -1)}
    mins = load_minutes(sym, y0 - 86400, y1 + 3 * 86400)
    minutes = (mins["t"].tolist(), mins["h"].tolist(), mins["l"].tolist(), mins["c"].tolist())
    out: dict[Any, Any] = {"m": moments, "price": closes, 1: [None] * len(moments), -1: [None] * len(moments)}
    for i, m in enumerate(moments.tolist()):
        k = int(np.searchsorted(news, m))
        news_left = (float(news[k]) - nb - m) if k < len(news) else float("inf")
        window_left = red_lines.seconds_to_red_line(m, sym, None)
        window_left = float(window_left) if window_left is not None and window_left > 0 else float("inf")
        left = min(news_left, window_left)
        reason = "news" if news_left < window_left else "session_end"
        left = left if math.isfinite(left) else 86400.0
        for s in (1, -1):
            stop = float(stops[s][i])
            if stop != stop:
                why["no_stop_%s" % ("buy" if s > 0 else "sell")] += 1
                continue
            if cfg.get("live_stop_floor", True) and _below_live_floor(abs(float(closes[i]) - stop), sym):
                why["stop_below_floor_%s" % ("buy" if s > 0 else "sell")] += 1
                continue
            out[s][i] = search_trade(s, m, float(closes[i]), stop, left, reason, minutes, cfg["targets"],
                                     cfg["breakeven_after"], cfg["trail_after"], cfg["trail_to_r"], cfg["cost"])
    return out


def _search_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    """The search's rules: the tool's defaults (= the red lines) under whatever the page sent, prices in the asset's units."""
    from shared.facts_strategies import STOP_PAD_PIPS, STOP_PAD_PIPS_DEFAULT, STOP_PIPS, STOP_PIPS_DEFAULT
    from shared.pips import from_pips
    base = merged({})
    sym = cfg.get("symbol", "USTEC")
    tg = cfg.get("targets") or base["targets"]
    total = sum(float(x["close_pct"]) for x in tg) or 100.0
    lo_p, hi_p = cfg.get("band") or STOP_PIPS.get(sym, STOP_PIPS_DEFAULT)
    pad_p = float(cfg.get("pad_pips") or STOP_PAD_PIPS.get(sym, STOP_PAD_PIPS_DEFAULT))
    cost_p = float(cfg.get("cost_pips", base["cost_pips"]))
    return {"symbol": sym, "targets": [(float(x["r"]), float(x["close_pct"]) / total) for x in tg],
            "targets_raw": tg, "breakeven_after": int(cfg.get("breakeven_after", base["breakeven_after"]) or 0),
            "trail_after": int(cfg.get("trail_after", base["trail_after"]) or 0),
            "trail_to_r": float(cfg.get("trail_to_r", base["trail_to_r"]) or 0.0),
            "wait_s": float(cfg.get("wait_min", base["wait_min"])) * 60,
            "news_before_s": float(base["news"]["before_min"]) * 60, "news_after_s": float(base["news"]["after_min"]) * 60,
            "first_s": float(base["session"]["first_minutes"]) * 60,
            "band_pips": (float(lo_p), float(hi_p)), "band": (from_pips(float(lo_p), sym), from_pips(float(hi_p), sym)),
            "pad_pips": pad_p, "pad": from_pips(pad_p, sym), "cost_pips": cost_p, "cost": from_pips(cost_p, sym),
            "margin": float(cfg.get("margin_r", SEARCH_MARGIN_R)), "risk_pct": float(cfg.get("risk_pct") or base["risk_pct"]),
            "balance": float(cfg.get("balance") or base["balance"]), "account_limits": cfg.get("account_limits"),
            "live_stop_floor": bool(cfg.get("live_stop_floor", base["live_stop_floor"]))}


def _rank_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra, rb = np.argsort(np.argsort(a)).astype(float), np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def strategy_search(cfg: dict[str, Any], log=print) -> Path:
    """The answer at every moment for both sides (the red lines' own trade), the student taught on it, and the exam:
    each exam year taught on the years before it only, then traded as a market -- one trade at a time, an hour and a
    quarter after each (law 12), only when the student expects at least the margin above the cost."""
    import lightgbm as lgb
    from shared import red_lines
    from shared.pips import to_pips
    began = time.time()
    rules = _search_cfg(cfg)
    sym = rules["symbol"]
    exams = [tuple(y) for y in cfg["exams"]]
    train_from = cfg.get("train_from") or SEARCH_TRAIN_FROM
    t_all0, t_all1 = _epoch(train_from), max(_epoch(e[1]) for e in exams)
    currencies = sorted({red_lines.USD, *red_lines.currencies_of(sym)})
    news = news_times({"on": True, "colors": ["red"], "currencies": currencies}, t_all0, t_all1)
    why: dict[str, int] = defaultdict(int)
    parts = []
    years = list(range(int(train_from[:4]), int(datetime.fromtimestamp(t_all1 - 1, timezone.utc).year) + 1))
    for n, y in enumerate(years):
        y0, y1 = max(_epoch("%d-01-01" % y), t_all0), min(_epoch("%d-01-01" % (y + 1)), t_all1)
        part = _search_answers(sym, y0, y1, rules, news, why)
        parts.append(part)
        log("البحث: أجوبة سنة %d — %d لحظة قرار · باقي %d سنة" % (y, len(part["m"]), len(years) - n - 1))
    moments = np.concatenate([p_["m"] for p_ in parts])
    price = np.concatenate([p_["price"] for p_ in parts])
    trades = {s: [t for p_ in parts for t in p_[s]] for s in (1, -1)}
    valid = {s: np.array([t is not None for t in trades[s]], dtype=bool) for s in (1, -1)}
    answer = {s: np.array([t.result_r() if t is not None else np.nan for t in trades[s]]) for s in (1, -1)}
    spec_rec = {"symbol": sym, "risk_pct": rules["risk_pct"]}
    results: dict[str, Any] = {}
    importance: dict[str, list[str]] = {}
    csv_rows: list[dict[str, Any]] = []
    for e0s, e1s in exams:
        e0, e1 = _epoch(e0s), _epoch(e1s)
        year = e0s[:4]
        log("البحث: يتعلّم التلميذ لامتحان %s على %s إلى %s …" % (year, train_from[:4], int(year) - 1))
        frames_needed = [SEARCH_FRAME] + LEARN_HEAVY[SEARCH_FRAME]
        thresholds: dict[Any, float] = {}
        for f in frames_needed:                                    # the wave size from the training years only
            b = np.array(_bars_db(sym, f, t_all0, e0), dtype=float)
            thresholds[f] = LEARN_WAVE_SIZE * float(np.median(b[:, 2] - b[:, 3])) if len(b) else 0.0
        for other in LEARN_RELATED:
            b = np.array(_bars_db(other, SEARCH_FRAME, t_all0, e0), dtype=float)
            thresholds[(other, SEARCH_FRAME)] = LEARN_WAVE_SIZE * float(np.median(b[:, 2] - b[:, 3])) if len(b) else 0.0
        tables_ = {}
        for key, (a, b_, beyond) in {"train": (t_all0, e0, False), "exam": (e0, e1, True)}.items():
            tab = _learn_table(sym, SEARCH_FRAME, a, b_, thresholds, beyond=beyond, rich=True)
            sel = np.flatnonzero((moments >= a) & (moments < b_))
            close_t = tab["ts"] + DIRECTION_PERIOD_S[SEARCH_FRAME]
            row = np.searchsorted(close_t, moments[sel])
            found = (row < len(close_t)) & (close_t[np.clip(row, 0, len(close_t) - 1)] == moments[sel])
            tables_[key] = {"sel": sel[found], "X": tab["X"][row[found]], "names": tab["names"]}
            del tab
        tr_, te_ = tables_["train"], tables_["exam"]
        if tr_["names"] != te_["names"]:                         # the same columns in the same order, or no exam
            keep = [n_ for n_ in tr_["names"] if n_ in set(te_["names"])]
            tr_["X"] = tr_["X"][:, [tr_["names"].index(n_) for n_ in keep]]
            te_["X"] = te_["X"][:, [te_["names"].index(n_) for n_ in keep]]
            tr_["names"] = te_["names"] = keep
        pred = {s: np.full(len(moments), np.nan) for s in (1, -1)}
        taught = {}
        for s in (1, -1):
            use = valid[s][tr_["sel"]]
            taught["الشراء" if s > 0 else "البيع"] = int(use.sum())
            model = lgb.train(SEARCH_PARAMS, lgb.Dataset(tr_["X"][use], answer[s][tr_["sel"]][use]),
                              num_boost_round=SEARCH_ROUNDS)
            pred[s][te_["sel"]] = model.predict(te_["X"])
            gain = model.feature_importance(importance_type="gain")
            importance["%s · %s" % (year, "الشراء" if s > 0 else "البيع")] = [
                tr_["names"][i] for i in np.argsort(gain)[::-1][:8] if gain[i] > 0]
        log("البحث: يتداول التلميذ سنة %s كأنّها سوقٌ حقيقيّ …" % year)
        free_at, taken = -math.inf, []
        for i in te_["sel"].tolist():
            m = float(moments[i])
            if m < free_at:
                continue
            best_side, best = 0, -math.inf
            for s in (1, -1):
                if valid[s][i] and pred[s][i] > best:
                    best_side, best = s, float(pred[s][i])
            if not best_side or best < rules["margin"]:
                continue
            taken.append((i, best_side, best))
            free_at = trades[best_side][i].exit_at + rules["wait_s"]
        rng = random.Random(SEED + 1)
        groups: dict[str, list[dict[str, Any]]] = {g: [] for g in SEARCH_GROUPS}
        ref_missing = 0
        for i, s, guess in taken:
            groups[SEARCH_GROUPS[0]].append({**_record(trades[s][i], spec_rec, to_pips), "predicted_r": round(guess, 3)})
            rs = rng.choice((1, -1))
            if valid[rs][i]:
                groups[SEARCH_GROUPS[1]].append({**_record(trades[rs][i], spec_rec, to_pips), "predicted_r": ""})
            else:
                ref_missing += 1
        res_year: dict[str, Any] = {}
        for g, rows in groups.items():
            sim = _account_limits.simulate([(_exit_epoch(t), sym, float(t["r"])) for t in rows], rules["account_limits"])
            res_year[g] = {"الإحصاء": stats(rows, len(rules["targets"])), **tables(rows, len(rules["targets"])),
                           "الحساب_الافتراضيّ": sim}
            for t in rows:
                csv_rows.append({"السنة": year, "المجموعة": g, **t})
        ex = te_["sel"]
        skill = {}
        for s in (1, -1):
            ok = ex[valid[s][ex] & np.isfinite(pred[s][ex])]
            above = ok[pred[s][ok] >= rules["margin"]]
            skill["الشراء" if s > 0 else "البيع"] = {
                "لحظات": int(len(ok)), "متوسّط_الجواب_R": round(float(np.nanmean(answer[s][ok])), 3) if len(ok) else None,
                "توقّع_فوق_الهامش": int(len(above)),
                "متوسّط_الجواب_فيها_R": round(float(np.nanmean(answer[s][above])), 3) if len(above) else None,
                "ارتباط_الترتيب": round(_rank_corr(pred[s][ok], answer[s][ok]), 3) if len(ok) >= 3 else None}
        st, rf = res_year[SEARCH_GROUPS[0]]["الإحصاء"], res_year[SEARCH_GROUPS[1]]["الإحصاء"]
        verdict = {"صافٍ_موجب": st["صافي_٪"] > 0, "فوق_العشوائيّ": st["صافي_٪"] > rf["صافي_٪"],
                   "صفر_سقوط": res_year[SEARCH_GROUPS[0]]["الحساب_الافتراضيّ"]["account_falls"] == 0,
                   "صفقات_تكفي": st["صفقات"] >= SEARCH_MIN_TRADES}
        last_seen = max((trades[s][i].exit_at for s in (1, -1) for i in tr_["sel"].tolist() if trades[s][i] is not None),
                        default=None)
        results[year] = {"النتائج": res_year, "قدرة_التلميذ": skill, "الشروط": verdict, "مرجع_بلا_وقف": ref_missing,
                         "صفوف_التعلّم": int(len(tr_["sel"])), "صفوف_الامتحان": int(len(ex)), "معلومات": len(tr_["names"]),
                         "تعلّم_على_صفقات": taught,
                         # the last instant any taught answer saw -- before the exam's first moment, or the exam is void
                         "آخر_ما_رآه_التعلّم": last_seen, "أوّل_الامتحان": e0}
        log("البحث: امتحان %s انتهى — %d صفقة · الصافي %+.1f٪ · العشوائيّ %+.1f٪" % (year, st["صفقات"], st["صافي_٪"], rf["صافي_٪"]))
    questions = {}
    for y in sorted({datetime.fromtimestamp(m, timezone.utc).year for m in moments.tolist()}):
        sel = (moments >= _epoch("%d-01-01" % y)) & (moments < _epoch("%d-01-01" % (y + 1)))
        row = {"لحظات": int(sel.sum())}
        for s, nm in ((1, "الشراء"), (-1, "البيع")):
            a = answer[s][sel & valid[s]]
            row[nm] = {"ممكنة": int(len(a)), "متوسّط_R": round(float(a.mean()), 3) if len(a) else None,
                       "فوق_الهامش_٪": round(100.0 * float((a >= rules["margin"]).mean()), 1) if len(a) else None}
        questions[str(y)] = row
    passed = all(all(r["الشروط"].values()) for r in results.values())
    name = cfg.get("name") or "البحث عن استراتيجيّة رابحة — %s — امتحان %s" % (
        SYMBOL_AR.get(sym, sym), " و".join(e[0][:4] for e in exams))
    folder = OUT_ROOT / date.today().isoformat() / safe(name)
    if folder.exists():
        folder = OUT_ROOT / date.today().isoformat() / safe("%s (%s)" % (name, datetime.now().strftime("%H-%M-%S")))
    folder.mkdir(parents=True, exist_ok=True)
    summary = {"kind": "strategy", "الاسم": name, "المجلّد": str(folder), "الحكم": "نعم" if passed else "لا",
               "السنوات": results, "السؤال_نفسه": questions, "الأهمّ": importance, "استُبعدت": dict(why),
               "الزمن": _span(time.time() - began), "القواعد": {k: v for k, v in rules.items() if k not in ("targets",)}}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    if csv_rows:
        fields = list(dict.fromkeys(k for r in csv_rows for k in r))
        with (folder / "الصفقات.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(csv_rows)
    (folder / "الاختبار.md").write_text(_search_test_md(name, rules, exams, train_from, why, summary), encoding="utf-8")
    (folder / "النتيجة.md").write_text(_search_result_md(name, rules, summary), encoding="utf-8")
    log("البحث: انتهى في %s · الحكم %s" % (summary["الزمن"], summary["الحكم"]))
    return folder


def _exit_epoch(t: dict[str, Any]) -> float:
    """The trade's close as an instant (its open is written in the owner's clock, Turkey +3)."""
    opened = datetime.strptime(t["opened"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=3))).timestamp()
    return opened + float(t.get("minutes") or 0) * 60


def _search_test_md(name: str, rules: dict[str, Any], exams: list, train_from: str, why: dict[str, int],
                    summary: dict[str, Any]) -> str:
    sym = rules["symbol"]
    L = ["# %s" % name, "", "قول المالك: «بحث برمجيّ عن استراتيجيّة رابحة على مدار سنوات ماضية وسنوات قادمة».", "",
         "## ما قيس", "",
         "- **السؤال:** لكلّ إغلاق خمس دقائق تسمح به الخطوط الحمراء، ولكلّ جهة: لو دخلنا الآن بوقف البنية وثلاثة أهداف بالأثلاث،"
         " فكم كان الصافي بوحدة المخاطرة بعد الكلفة؟",
         "- **الوقت:** نافذة %s وحدها، لا دخول في أوّل %d دقيقة منها، ولا يوم عطلة البورصة أو البنوك الأمريكيّة أو الإغلاق المبكر،"
         " ولا من %d دقيقة قبل الخبر الأحمر إلى %d بعده (عملات الأصل والدولار)." % (
             SYMBOL_AR.get(sym, sym), rules["first_s"] / 60, rules["news_before_s"] / 60, rules["news_after_s"] / 60),
         "- **وقف البنية:** آخر قاعٍ للشراء أو قمّةٍ للبيع مؤكّدة (تعريف الذرّتين 201 و202: شمعةٌ أدنى أو أعلى بصرامة من الشمعتين"
         " قبلها والشمعتين بعدها) على الخمس دقائق ثمّ الربع ساعة ثمّ الدقيقة، وخلفه %g بِب، والمسافة بين %g و%g بِب بلا تحجيم."
         " لا وقف بين الحدّين = لا صفقة." % (rules["pad_pips"], *rules["band_pips"]),
         "- **الأهداف:** " + " · ".join("%s× المخاطرة يُغلق %s٪" % (x["r"], x["close_pct"]) for x in rules["targets_raw"])
         + " · الوقف إلى الدخول بعد الهدف %d، وإلى %g× بعد الهدف %d · الدقيقة التي تلمس الوقف والهدف معًا وقف." % (
             rules["breakeven_after"], rules["trail_to_r"], rules["trail_after"]),
         "- **الإغلاق الكامل:** قبل الخبر الأحمر بـ%d دقيقة، وعند خطّ نافذة الأصل. ولا صفقة جديدة في الساعة الأخيرة من النافذة (القانون 21)." % (
             rules["news_before_s"] / 60),
         "- **الكلفة:** %g بِب من كلّ صفقة." % rules["cost_pips"],
         "- **التلميذ:** نموذج تعلّم (أشجار متدرّجة) لكلّ جهة، يرى عند كلّ لحظة ما قبلها فقط: الخمس دقائق وأطرها الأثقل (الربع ساعة"
         " والساعة والأربع ساعات) · الأسواق المرتبطة (%s) · أخبار الدولار الحمراء · مستويات الأمس والأسبوع الماضي وافتتاح اليوم ·"
         " ساعة اليوم ويوم الأسبوع." % "، ".join(SYMBOL_AR.get(s, s) for s in LEARN_RELATED),
         "- **الامتحان:** " + " · ".join("سنة %s يتعلّم على %s إلى %d ثمّ يتداولها" % (e[0][:4], train_from[:4], int(e[0][:4]) - 1)
                                       for e in exams) + ".",
         "- **التداول:** يدخل الجهة الأعلى توقّعًا فقط إن توقّع %+.2f من وحدة المخاطرة أو أكثر بعد الكلفة، ثمّ لا دخول حتّى"
         " تُغلق الصفقة وتمرّ %d دقيقة (القانون 12)." % (rules["margin"], rules["wait_s"] / 60),
         "- **المرجع:** الصفقات نفسها في اللحظات نفسها بجهةٍ عشوائيّة.",
         "- **الحساب الافتراضيّ:** معادلة الحيّ الواحدة بحدود المالك الأولى، ويُعدّ كم مرّة كان سيسقط.", "",
         "## كيف جرى", "", "- الزمن: %s" % summary["الزمن"], "- ما استُبعد:"]
    names = {"outside_window_or_first_minutes": "خارج نافذة الأصل أو في أوّل ربع ساعة", "no_trade_day": "يوم عطلة أو إغلاقٍ مبكر",
             "news_window": "نافذة خبرٍ أحمر", "no_stop_buy": "شراء بلا وقف بنيةٍ بين الحدّين",
             "no_stop_sell": "بيع بلا وقف بنيةٍ بين الحدّين", "last_hour": "الساعة الأخيرة من نافذة الأصل (القانون 21)",
             "not_enough_time_buy": "شراء لا يتّسع وقته للهدف الأخير (قانون ما قبل ٢٥/١٠)",
             "not_enough_time_sell": "بيع لا يتّسع وقته للهدف الأخير (قانون ما قبل ٢٥/١٠)",
             "stop_below_floor_buy": "شراءٌ وقفه أقصر من حارس أدنى الوقف في الحيّ (555)",
             "stop_below_floor_sell": "بيعٌ وقفه أقصر من حارس أدنى الوقف في الحيّ (555)"}
    for k, v in sorted(why.items()):
        L.append("  - %s: %d" % (names.get(k, k), v))
    for y, r in summary["السنوات"].items():
        seen = r.get("آخر_ما_رآه_التعلّم")
        taught = r.get("تعلّم_على_صفقات", {})
        L.append("- سنة %s: تعلّم على %d لحظة (منها صفقات ممكنة: شراء %d · بيع %d)، وامتُحن على %d، بـ%d معلومة · آخر ما رآه"
                 " التعلّم %s (الامتحان يبدأ %s) · صفقات العشوائيّ التي لم يكن لجهتها وقف: %d" % (
                     y, r["صفوف_التعلّم"], taught.get("الشراء", 0), taught.get("البيع", 0), r["صفوف_الامتحان"], r["معلومات"],
                     datetime.fromtimestamp(seen, timezone.utc).strftime("%Y-%m-%d %H:%M") if seen else "—",
                     datetime.fromtimestamp(r["أوّل_الامتحان"], timezone.utc).strftime("%Y-%m-%d"), r["مرجع_بلا_وقف"]))
    return "\n".join(L) + "\n"


def _search_result_md(name: str, rules: dict[str, Any], summary: dict[str, Any]) -> str:
    bal = rules["balance"]
    money = lambda pct: "{:+,.0f}$".format(pct * bal / 100.0)
    dip = lambda low: "ربح مباشرة" if low >= 0 else "{:.1f}٪ ({:,.0f}$)".format(low, bal * low / 100.0)
    years = summary["السنوات"]
    g0, g1 = SEARCH_GROUPS
    L = ["# النتيجة — %s" % name, "",
         "المخاطرة %s٪ من رأس المال الأوّل في كلّ صفقة، والكلفة مخصومة. «على %s$» = النسبة مضروبةً في رأس المال." % (
             rules["risk_pct"], "{:,.0f}".format(bal)), "",
         "## الحكم بمعيار النجاح المكتوب في الورقة قبل النتيجة", "",
         "| الشرط | %s | تحقّق؟ |" % " | ".join(years), "|---|" + "---|" * len(years) + "---|"]
    rows = (("صافي التلميذ بعد الكلفة موجب", "صافٍ_موجب", lambda r: "%+.1f٪" % r["النتائج"][g0]["الإحصاء"]["صافي_٪"]),
            ("أعلى من الصفقات نفسها بجهة عشوائيّة", "فوق_العشوائيّ", lambda r: "%+.1f٪ مقابل %+.1f٪" % (
                r["النتائج"][g0]["الإحصاء"]["صافي_٪"], r["النتائج"][g1]["الإحصاء"]["صافي_٪"])),
            ("صفر سقوطٍ للحساب الافتراضيّ", "صفر_سقوط", lambda r: "%d سقوط" % r["النتائج"][g0]["الحساب_الافتراضيّ"]["account_falls"]),
            ("ثلاثون صفقةً على الأقلّ", "صفقات_تكفي", lambda r: "%d صفقة" % r["النتائج"][g0]["الإحصاء"]["صفقات"]))
    for label, key, cell in rows:
        L.append("| %s | %s | %s |" % (label, " | ".join(cell(r) for r in years.values()),
                                     "نعم" if all(r["الشروط"][key] for r in years.values()) else "لا"))
    L += ["", "**الجواب: %s.**" % summary["الحكم"], "",
          "## 1. كلّ سنة بشكل المالك", "",
          "| السنة | المجموعة | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف | كم نزل قبل الربح | الصافي | على %s$ | سقوط الحساب |" % (
              "{:,.0f}".format(bal)), "|---|---|---|---|---|---|---|---|---|---|---|"]
    for y, r in years.items():
        for g in SEARCH_GROUPS:
            s = r["النتائج"][g]["الإحصاء"]
            L.append("| %s | %s | %d | %d | %d | %d | %d | %s | %+.1f٪ | %s | %d |" % (
                y, "التلميذ" if g == g0 else "عشوائيّ", s["صفقات"], s.get("بلغ_الهدف_1", 0), s.get("بلغ_الهدف_2", 0),
                s.get("بلغ_الهدف_3", 0), s["وقف_قبل_أيّ_هدف"], dip(s["أعمق_نزول_تحت_البداية_٪"]), s["صافي_٪"],
                money(s["صافي_٪"]), r["النتائج"][g]["الحساب_الافتراضيّ"]["account_falls"]))
    L += ["", "«وقف» = ضربت الوقف كاملًا قبل أيّ هدف. والأهداف متداخلة: كلّ صفقة بلغت الثاني بلغت الأوّل قبله.", ""]
    for y, r in years.items():
        ref_month = {m["الشهر"]: m["عائد_٪"] for m in r["النتائج"][g1]["الأشهر"]}
        L += ["## 2. أشهر %s — التلميذ، ومعه العشوائيّ" % y, "",
              "| الشهر | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف | كم نزل قبل الربح (من أوّل السنة) | الصافي | الحساب آخر الشهر | العشوائيّ |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        months = r["النتائج"][g0]["الأشهر"]
        for m in months:
            L.append("| %s | %d | %d | %d | %d | %d | %s | %+.1f٪ | %s$ | %s |" % (
                m["الشهر"], m["صفقات"], m.get("هدف_1", 0), m.get("هدف_2", 0), m.get("هدف_3", 0), m["وقف"],
                dip(m.get("أدنى_حتّى_الآن_٪", 0.0)), m["عائد_٪"], "{:,.0f}".format(bal * (1 + m.get("الحساب_٪", 0.0) / 100)),
                ("%+.1f٪" % ref_month[m["الشهر"]]) if m["الشهر"] in ref_month else "—"))
        if not months:
            L.append("| — | لا صفقة: لم يتوقّع التلميذ ربحًا فوق الهامش في أيّ لحظة | | | | | | | | |")
        L.append("")
    L += ["## 3. الحساب الافتراضيّ بحدود المالك (القوانين 7–10)", ""]
    for y, r in years.items():
        for g in SEARCH_GROUPS:
            sim = r["النتائج"][g]["الحساب_الافتراضيّ"]
            L.append("- **%s · %s:** صفقات محسوبة %d · مُسقطة بالحدود %d · سقوط الحساب **%d** مرّة · أيّام وقفها الحدّ الشامل %d"
                     " · وقفات حدّ الزوج %d · أسوأ خسارة يوم %.2f$ · أدنى حقوق %.2f$ · الصافي %.2f$" % (
                         y, "التلميذ" if g == g0 else "عشوائيّ", sim["taken"], sim["skipped"], sim["account_falls"],
                         sim["daily_stops"], sim["pair_stops"], sim["max_day_loss"], sim["lowest_equity"], sim["net"]))
    L += ["", "## 4. السؤال نفسه: لو دخلنا في كلّ لحظةٍ ممكنة", "",
          "كلّ صفقةٍ وحدها، بلا تلميذ ولا انتظار — ما يعطيه الدخول الأعمى في كلّ لحظة بالقوانين نفسها.", "",
          "| السنة | لحظات القرار | شراء ممكن | متوسّط صافي الشراء | فوق الهامش ٪ | بيع ممكن | متوسّط صافي البيع | فوق الهامش ٪ |",
          "|---|---|---|---|---|---|---|---|"]
    fmt = lambda v, f: (f % v) if v is not None else "—"
    for y, q in summary["السؤال_نفسه"].items():
        b, s = q["الشراء"], q["البيع"]
        L.append("| %s | %d | %d | %s | %s | %d | %s | %s |" % (y, q["لحظات"], b["ممكنة"], fmt(b["متوسّط_R"], "%+.3f"),
                 fmt(b["فوق_الهامش_٪"], "%.1f"), s["ممكنة"], fmt(s["متوسّط_R"], "%+.3f"), fmt(s["فوق_الهامش_٪"], "%.1f")))
    L += ["", "## 5. هل عرف التلميذ الجواب؟ (كلّ لحظات الامتحان، بلا انتظار)", "",
          "| السنة | الجهة | لحظات ممكنة | متوسّط الجواب فيها | لحظات توقّع فيها فوق الهامش | متوسّط الجواب الفعليّ فيها | ارتباط ترتيب التوقّع بالجواب |",
          "|---|---|---|---|---|---|---|"]
    for y, r in years.items():
        for side, k in r["قدرة_التلميذ"].items():
            L.append("| %s | %s | %d | %s | %d | %s | %s |" % (y, side, k["لحظات"], fmt(k["متوسّط_الجواب_R"], "%+.3f"),
                     k["توقّع_فوق_الهامش"], fmt(k["متوسّط_الجواب_فيها_R"], "%+.3f"), fmt(k["ارتباط_الترتيب"], "%+.3f")))
    L += ["", "الجواب بوحدة المخاطرة بعد الكلفة. الارتباط من −1 إلى +1، والصفر = لا علم.", "",
          "## 6. ماذا اعتمد التلميذ أكثر (أعلى ثمانٍ)", ""]
    for key, names in summary["الأهمّ"].items():
        L.append("- **%s:** %s" % (key, "؛ ".join(n.replace(" · ", " — ") for n in names)
                                   or "لا شيء — لم يجد التلميذ معلومةً تفرّق الجواب"))
    L += ["", "## 7. أين قرب ولماذا (أرقام لا حكم)", ""]
    for y, r in years.items():
        s = r["النتائج"][g0]["الإحصاء"]
        if not s["صفقات"]:
            L.append("- %s: لا صفقة." % y)
            continue
        months = r["النتائج"][g0]["الأشهر"]
        win = [m["الشهر"][5:] for m in months if m["عائد_٪"] > 0]
        L.append("- %s: رابحة %d من 100 · الشراء %d صفقة %+.1f٪ والبيع %d صفقة %+.1f٪ · أشهرٌ رابحة %d من %d (%s)." % (
            y, round(s["نسبة_الربح"]), s["شراء_صفقات"], s["شراء_صافي_٪"], s["بيع_صفقات"], s["بيع_صافي_٪"], len(win),
            len(months), "، ".join(win) or "—"))
        for k, v in sorted(s.get("النهايات", {}).items(), key=lambda kv: -kv[1]["صفقات"]):
            L.append("  - %s: %d صفقة، متوسّطها %+.2f من المخاطرة" % (k, v["صفقات"], v["متوسّط_R"]))
    return "\n".join(L) + "\n"


#: The live combination 415 as the measuring tool holds it (the runs of 2026-10-19): Dow on four hours read on the quarter
#: hour, the owner's averages 5/10/50 on the quarter hour the same way, the structure stop 20-45 unscaled (the live band),
#: the thirds and every red line from DEFAULTS.
LIVE_COMBO = {"decision_frame": "15m",
              "direction": {"source": "fact", "atom": "209", "frame": "15m", "key": "readings.four_hours.trend"},
              "conditions": [{"atom": "ema", "frame": "كلّ لحظة", "key": "order.15m", "op": "same_way", "value": None}],
              "stop": {"method": "structure"}, "scale_with_price": False, "reference_random": True}
#: 2026-10-23 (the owner's correction: «الوقف خلف البنية، والهدف عند المستوى التالي قبله لا عليه» then «بس ما يكون اقل من
#: 1/3»): the spearhead's last target is the next level, never under 3R after the cost; the fixed 3R stays beside it, and the
#: combination without a spearhead keeps its live 3R target as the reference.
NEXT_LEVEL_TARGET = {"method": "next_level", "levels": True, "round": True, "min_r": 3.0}
_SCENARIOS = (("كسرٌ وثبات — الخمس دقائق", {"scenario": "break", "candle": "M5"}),
              ("كسرٌ وثبات — الدقيقة", {"scenario": "break", "candle": "M1"}),
              ("كسرٌ كاذب — الخمس دقائق", {"scenario": "false", "candle": "M5"}),
              ("كسرٌ كاذب — الدقيقة", {"scenario": "false", "candle": "M1"}))
LEVELS_VARIANTS = ((("بلا رأس حربة — التوليفة الحيّة كما هي (هدف 3 أضعاف)", None, None),)
                   + tuple(("%s — الهدف عند المستوى التالي" % lb, lv, NEXT_LEVEL_TARGET) for lb, lv in _SCENARIOS)
                   + tuple(("%s — هدف 3 أضعاف ثابت" % lb, lv, None) for lb, lv in _SCENARIOS))
#: then (the owner, «قيس»): the next level from the trader's map alone -- the four spearheads only, beside the combination
#: without one; the fixed-3R spearheads are not run again
NEXT_LEVEL_MAP_TARGET = {"method": "next_level", "map": True, "levels": False, "round": False, "min_r": 3.0}
LEVELS_MAP_VARIANTS = ((LEVELS_VARIANTS[0],)
                       + tuple(("%s — الهدف عند المستوى التالي من خريطة المتداول" % lb, lv, NEXT_LEVEL_MAP_TARGET)
                               for lb, lv in _SCENARIOS))
#: then (the owner, the night of 23-24/10, on learning the real entries fit about two hours a day: «1560 ساعة بل سنة منها 6
#: ساعات كل جلسة قيس بلا قاعدة وقت يكفي»): the live combination as it is, with law 21 and without it alone -- for knowledge;
#: law 21 stays a red line in the live system. Every trade still closes whole at the window's end (laws 19-20).
#: 2026-10-25 (owner seal, law 21): law 21 is now «no new trade in the last hour», so these two read «with law 21» and
#: «without it alone»; the runs of 24/10 measured the old time-enough law under the old names.
NOTIME_VARIANTS = (("بالقانون 21 — التوليفة الحيّة كما هي", None, None),
                   ("بلا القانون 21 وحده", None, None))
VARIANT_SPEC = {NOTIME_VARIANTS[1][0]: {"time_enough": False}}
LEVELS_WITHIN_MIN = 15
FAST_STOP_MIN = 5.0
#: the paper's step 10, word for word -- written into «الاختبار.md» before the first run
LEVELS_CRITERION = ("صافٍ أعلى من التوليفة الحيّة بلا رأس حربة في 2022 و2023 كلتيهما، وموجبٌ بعد الكلفة، وأعلى من الجهة"
                    " العشوائيّة، ووقوف أوّل 5 دقائق أقلّ نسبةً. وإلّا يُقال «لا» بالأرقام.")


def _plan_store(sym: str, y0: str, y1: str) -> Path:
    """A complete store covering [y0, y1): the quick one (Dow, swings, structure) first, then the full one."""
    for root in ("facts_store_quick", "facts_store"):
        for p in sorted((ROOT / "forex_runtime" / "var" / root / sym).glob("*_*")):
            a, _, b = p.name.partition("_")
            if "__" not in p.name and a <= y0 and y1 <= b and (p / "index.json").exists():
                return p
    raise SystemExit("لا مخزن حقائق لـ%s %s — ابنِه من الصفحة أوّلًا" % (SYMBOL_AR.get(sym, sym), y0[:4]))


def _fast_stops(rows: list[dict]) -> int:
    return sum(1 for t in rows if t["exit"] == EXIT_AR["stop"] and int(t["reached"]) == 0 and float(t["minutes"]) <= FAST_STOP_MIN)


def _window_end(rows: list[dict]) -> dict[str, Any]:
    """The trades closed whole at the window's end before their last target (laws 19-20), and what they made; and those
    closed before a red news item."""
    end = [t for t in rows if t["exit"] == EXIT_AR["session_end"]]
    return {"صفقات": len(end), "قبل_أيّ_هدف": sum(1 for t in end if int(t["reached"]) == 0),
            "بعد_هدفٍ_أو_اثنين": sum(1 for t in end if int(t["reached"]) > 0),
            "صافيها_٪": round(sum(t["pct"] for t in end), 2),
            "متوسّطها_R": round(float(np.mean([t["r"] for t in end])), 2) if end else None,
            "قبل_الخبر": sum(1 for t in rows if t["exit"] == EXIT_AR["news"])}


def _by_hour(rows: list[dict]) -> dict[str, dict[str, Any]]:
    """The trades by the hour they opened, in the owner's clock (Turkey)."""
    out = {}
    for h in sorted({int(t["hour"]) for t in rows}):
        s = stats([t for t in rows if int(t["hour"]) == h], 3)
        out["%02d:00–%02d:00" % (h, (h + 1) % 24)] = {"صفقات": s["صفقات"], "هدف_1": s.get("بلغ_الهدف_1", 0),
                                                     "هدف_2": s.get("بلغ_الهدف_2", 0), "هدف_3": s.get("بلغ_الهدف_3", 0),
                                                     "وقف": s["وقف_قبل_أيّ_هدف"], "صافي_٪": s["صافي_٪"]}
    return out


def _per_session(rows: list[dict]) -> dict[str, int]:
    count: dict[str, int] = defaultdict(int)
    for t in rows:
        count[t["day"]] += 1
    vals = list(count.values())
    return {"جلسات": len(vals), "بصفقة": sum(1 for v in vals if v == 1), "بصفقتين": sum(1 for v in vals if v == 2),
            "بثلاث_فأكثر": sum(1 for v in vals if v >= 3), "أقصى": max(vals) if vals else 0}


def levels_plan(cfg: dict[str, Any], log=print) -> Path:
    """The trader's levels and his two scenarios as one spearhead inside the live combination (the owner's paper of
    2026-10-23): the combination without a spearhead, then break-and-hold and false break, each on five-minute and on
    minute candles, every year asked -- each run the engine's own `run`, written in full under «التجارب»."""
    from shared.facts_strategies import STOP_PAD_PIPS, STOP_PAD_PIPS_DEFAULT, STOP_PIPS, STOP_PIPS_DEFAULT
    began = time.time()
    sym = cfg.get("symbol", "USTEC")
    years = [tuple(y) for y in cfg["years"]]
    map_only = cfg.get("variants") == "map"          # the owner's «قيس» (23/10): the next level from his map alone
    notime = cfg.get("variants") == "notime"         # the owner (24/10): the combination without law 21, for knowledge
    variants = LEVELS_MAP_VARIANTS if map_only else NOTIME_VARIANTS if notime else LEVELS_VARIANTS
    name = cfg.get("name") or ("التوليفة الحيّة بلا القانون 21 — للمعرفة — %s — %s" % (
        SYMBOL_AR.get(sym, sym), " و".join(y[0][:4] for y in years)) if notime else
        "مستويات المتداول والسيناريوهان داخل التوليفة الحيّة — %s — %s%s" % (
            SYMBOL_AR.get(sym, sym), " و".join(y[0][:4] for y in years), " — الهدف من خريطة المتداول" if map_only else ""))
    folder = OUT_ROOT / date.today().isoformat() / safe(name)
    if folder.exists():
        folder = OUT_ROOT / date.today().isoformat() / safe("%s (%s)" % (name, datetime.now().strftime("%H-%M-%S")))
    folder.mkdir(parents=True, exist_ok=True)
    band = list(STOP_PIPS.get(sym, STOP_PIPS_DEFAULT))
    pad = float(STOP_PAD_PIPS.get(sym, STOP_PAD_PIPS_DEFAULT))      # the stop a pad behind structure, the target a pad before
    (folder / "الاختبار.md").write_text(_notime_test_md(name, sym, years, band) if notime else
                                        _levels_test_md(name, sym, years, band, pad, map_only), encoding="utf-8")
    runs: dict[str, dict[str, Any]] = {}
    for y0, y1 in years:
        store = _plan_store(sym, y0, y1)
        for label, lv, tgt in variants:
            spec = json.loads(json.dumps({**LIVE_COMBO, "symbol": sym, "from": y0, "to": y1, "store": str(store),
                                          "name": "%s — %s — %s" % (label, SYMBOL_AR.get(sym, sym), y0[:4])}))
            spec["stop"]["band"] = band
            if lv:
                spec["entry"] = {"levels": lv, "within_min": LEVELS_WITHIN_MIN}
            if tgt:
                spec["target_from"] = dict(tgt, pad_pips=pad)
            spec.update(VARIANT_SPEC.get(label, {}))
            res = run(merged(spec), log=log)
            sub = write(res, Facts(Path(res["store"])).index.get("names", {}), root=folder / "التجارب")
            summ = json.loads((sub / "summary.json").read_text(encoding="utf-8"))
            year = y0[:4]
            out: dict[str, Any] = {"التجربة": label, "السنة": year, "المجلّد": sub.name}
            for g, rows in res["trades"].items():
                res_g = summ["النتائج"][g]
                kinds = {}
                for k in TRADER_LEVEL_AR:
                    sub_rows = [t for t in rows if t.get("level") == k]
                    if sub_rows:
                        kinds[TRADER_LEVEL_AR[k]] = stats(sub_rows, len(spec_targets(res["spec"])))
                out[g] = {"الإحصاء": res_g["الإحصاء"], "الأشهر": res_g["الأشهر"], "الحساب_الافتراضيّ": res_g["الحساب_الافتراضيّ"],
                          "وقف_أوّل_5_دقائق": _fast_stops(rows), "الجلسات": _per_session(rows), "المستويات": kinds,
                          "رُدّت_بشرط_الثلاثة": int(res["skipped"].get(g, {}).get("target_below_three", 0)),
                          "بلا_مستوى_أمامها": sum(1 for t in rows if t.get("target_from") == "none_ahead"),
                          "متوسّط_الهدف_الأخير": round(float(np.mean([t["target_r"] for t in rows])), 2) if rows else None,
                          "بهدف_المستوى": bool(tgt), "عند_نهاية_النافذة": _window_end(rows), "الساعات": _by_hour(rows)}
            runs["%s|%s" % (year, label)] = out
            log("المستويات: %s · %s — %d صفقة · باقي %d تجربة" % (year, label, len(res["trades"]["التوليفة"]),
                len(years) * len(variants) - len(runs)))
    base_label = variants[0][0]
    verdicts = {}
    for label, *_ in variants[1:]:
        per_year = {}
        for y0, _ in years:
            r, b = runs["%s|%s" % (y0[:4], label)], runs["%s|%s" % (y0[:4], base_label)]
            s, bs, rs = r["التوليفة"]["الإحصاء"], b["التوليفة"]["الإحصاء"], r["مرجع: جهة عشوائيّة"]["الإحصاء"]
            share = r["التوليفة"]["وقف_أوّل_5_دقائق"] / s["صفقات"] if s["صفقات"] else None
            b_share = b["التوليفة"]["وقف_أوّل_5_دقائق"] / bs["صفقات"] if bs["صفقات"] else None
            per_year[y0[:4]] = {"فوق_بلا_رأس_حربة": s["صفقات"] > 0 and s["صافي_٪"] > bs["صافي_٪"], "موجب": s["صافي_٪"] > 0,
                                "فوق_العشوائيّ": s["صفقات"] > 0 and s["صافي_٪"] > rs["صافي_٪"],
                                "وقف_سريع_أقلّ": share is not None and b_share is not None and share < b_share,
                                "نسبة_الوقف_السريع": share, "نسبته_بلا_رأس_حربة": b_share}
        verdicts[label] = {"السنوات": per_year, "نجح": all(all(v for k, v in yv.items() if not k.startswith("نسب"))
                                                           for yv in per_year.values())}
    passed = [k for k, v in verdicts.items() if v["نجح"]]
    verdict = "قياسٌ للمعرفة — بلا حكم" if notime else ("نعم: " + "، ".join(passed)) if passed else "لا"
    summary = {"kind": "levels", "الاسم": name, "المجلّد": str(folder), "الحكم": verdict,
               "التجارب": runs, "الشروط": {} if notime else verdicts, "الزمن": _span(time.time() - began),
               "المعيار": "" if notime else LEVELS_CRITERION, "للمعرفة": notime,
               "الترتيب": [[label, bool(lv), bool(tgt)] for label, lv, tgt in variants]}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    all_rows = []
    for key, r in runs.items():
        sub_csv = folder / "التجارب" / r["المجلّد"] / "الصفقات.csv"
        try:
            with sub_csv.open(encoding="utf-8-sig") as fh:
                all_rows += [{"السنة": r["السنة"], "التجربة": r["التجربة"], **row} for row in csv.DictReader(fh)]
        except OSError:
            pass
    if all_rows:
        fields = list(dict.fromkeys(k for row in all_rows for k in row))
        with (folder / "الصفقات.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(all_rows)
    (folder / "النتيجة.md").write_text(_levels_result_md(name, years, summary), encoding="utf-8")
    log("المستويات: انتهى في %s · الحكم %s" % (summary["الزمن"], summary["الحكم"]))
    return folder


def spec_targets(spec: dict[str, Any]) -> list:
    return spec.get("targets") or DEFAULTS["targets"]


def _levels_test_md(name: str, sym: str, years: list, band: list, pad: float = 1.0, map_only: bool = False) -> str:
    step = ROUND_STEP.get(sym)
    L = ["# %s" % name, "",
         "قول المالك: «حط هدول مع سستم حي nq» ثمّ «يقاس»، وعلى نقطتي القرار: «على حسب جلسة كم صفقة بتاخد» و«قيس على اثنين».", "",
         "## معيار النجاح — الخطوة 10 من الورقة بنصّها، كُتب هنا قبل أوّل تشغيل", "", "> " + LEVELS_CRITERION, "",
         "يُحكم لكلّ سيناريو ولكلّ شمعة وحده: الشروط الأربعة في السنتين كلتيهما.", "",
         "## ما قيس", "",
         "- **الأساس — التوليفة الحيّة 415 كما هي:** القرار عند كلّ إغلاق ربع ساعة · الجهة داو الأربع ساعات (الذرّة 209) · التأكيد"
         " ترتيب متوسّطات 5 و10 و50 على الربع ساعة في جهة الصفقة · وقف البنية خلف آخر قاعٍ أو قمّة (الذرّة 202) على الخمس ثمّ الربع"
         " ثمّ الدقيقة، بين %g و%g بِب بلا تحجيم · الأثلاث: ثلثٌ عند وحدة مخاطرة والوقف إلى الدخول، وثلثٌ عند وحدتين والوقف إلى"
         " الأولى، والباقي عند ثلاث · الخطوط الحمراء كلّها: نافذة نيويورك وحدها وأوّل ربع ساعة ممنوع · لا يوم عطلة ولا إغلاقٍ مبكر ·"
         " الخبر الأحمر 15 دقيقة قبل وبعد لعملات الأصل والدولار · ساعة وربع بعد كلّ صفقة · لا صفقة جديدة في الساعة الأخيرة (القانون 21) · الكلفة 1.5 بِب ·"
         " حدود الحساب بمعادلة الحيّ." % tuple(band),
         "- **رأس الحربة — مستويات المتداول:** بعد كلّ قرار، أوّل إشارةٍ في جهة التوليفة خلال %d دقيقة، والدخول بإغلاق شمعتها،"
         " ثمّ القوانين نفسها كلّها. لا دخول عكس جهة التوليفة." % LEVELS_WITHIN_MIN,
         "- **المستويات:** تُثبَّت عند افتتاح نافذة الأصل من الماضي وحده: أعلى جلسة الأمس وأدناها وإغلاقها · أعلى الليل وأدناه (من"
         " إغلاق الأمس إلى الافتتاح) · أعلى آخر أسبوع تداولٍ كامل وأدناه · أقرب رقمين مستديرين حول آخر سعرٍ قبل الافتتاح"
         + (" (كلّ %g، والقويّ ما كان من مضاعفات %g)." % step if step else "."),
         "- **السيناريو الأوّل — كسرٌ وثبات:** شمعةٌ تُغلق خلف المستوى في جهة التوليفة، والشمعة قبلها لم تكن خلفه.",
         "- **السيناريو الثاني — كسرٌ كاذب:** السعر يتجاوز المستوى عكس جهة التوليفة شمعةً واحدةً على الأكثر، ثمّ تُغلق شمعةٌ راجعة:"
         " للشراء كان السعر فوقه، فنزلت شمعةٌ تحته بذيلها وأُغلقت فوقه، أو أُغلقت الشمعة قبلها تحته وهذه فوقه. والبيع مرآته.",
         "- **الشمعة:** الخمس دقائق في تجربة، والدقيقة في تجربةٍ أخرى («قيس على اثنين»).",
         "- **الهدف في رأس الحربة — تصحيح المالك ٢٣/١٠:** «الوقف خلف البنية، والهدف عند المستوى التالي قبله لا عليه» ثمّ «بس ما يكون"
         " اقل من 1/3». الهدف الأخير قبل أقرب مستوى أمام الدخول في جهة الصفقة بـ%g بِب (هامش الوقف نفسه)، والهدفان الأوّل"
         " والثاني ضعفٌ وضعفان كما هما (طريقة المحرّك ١٩/١٠). المستويات: %s. **ولا صفقة** إن كان"
         " (العائد − الكلفة) ÷ (المخاطرة + الكلفة) أقلّ من 3، ويُعدّ ما رُدّ. ولا مستوى أمامها = ثلاثة أضعاف." % (
             pad, "**خريطة المتداول وحدها** (جواب المالك «قيس» ٢٣/١٠)، الخريطة نفسها التي تُطلق رأس الحربة: أعلى الأمس وأدناه"
             " وإغلاقه · أعلى الليل وأدناه · أعلى الأسبوع الماضي وأدناه · الرقمان المستديران" if map_only else
             "مستويات الذرّة 124 لحظة القرار (أعلى وأدنى الأمس وما قبل الافتتاح والليل والأسبوع والأسبوع السابق والشهر والشهر"
             " السابق) والرقمان المستديران عند الافتتاح"),
         ("- **التجارب الأربع وحدها** بهذا الهدف، ولا تُعاد تجارب الهدف الثابت (قيست قبلها). والتوليفة بلا رأس حربة بهدفها الحيّ"
          " ثلاثة أضعاف." if map_only else
          "- **والهدف الثابت بجانبه:** كلّ سيناريو وشمعة مرّةً ثانيةً بهدف ثلاثة أضعاف ثابت، كما في القياس الأوّل قبل التصحيح. والتوليفة"
          " بلا رأس حربة بهدفها الحيّ ثلاثة أضعاف."),
         "- **عدد الصفقات:** لا رقم ثابت؛ القوانين الموجودة وحدها.",
         "- **المقارنة:** التوليفة بلا رأس حربة · الجهة العشوائيّة بالقوانين نفسها · مرّات سقوط الحساب الافتراضيّ · كم وقفًا ضُرب في"
         " أوّل %g دقائق قبل أيّ هدف." % FAST_STOP_MIN,
         "- **السنتان:** %s · الرمز: %s · البيانات: شموع الدقيقة من سي‑تريدر، وحقائق الذرّات من المخزن." % (
             " و".join(y[0][:4] for y in years), SYMBOL_AR.get(sym, sym)),
         "- **كلّ تجربةٍ كاملة بملفّاتها** في مجلّد «التجارب» بجانب هذا الملفّ."]
    return "\n".join(L) + "\n"


def _notime_test_md(name: str, sym: str, years: list, band: list) -> str:
    L = ["# %s" % name, "",
         "قول المالك (ليلة ٢٣–٢٤/١٠، بعد أن عرف أنّ الدخول الفعليّ نحو ساعتين في اليوم): «1560 ساعة بل سنة منها 6 ساعات كل جلسة"
         " قيس بلا قاعدة وقت يكفي».", "",
         "**قياسٌ للمعرفة، بلا معيار نجاح:** القانون 21 خطٌّ أحمر، ولا يتغيّر في الحيّ إلّا بنقاش المالك وختمه. ومنذ ٢٥/١٠ هو «لا صفقة جديدة في"
         " الساعة الأخيرة من نافذة الأصل» بختم المالك، بدل «الوقت يكفي» الذي قيس بهذا الزرّ ليلة ٢٣–٢٤/١٠.", "",
         "## ما قيس", "",
         "- **التجربتان:** التوليفة الحيّة 415 كما هي **بالقانون 21**، ثمّ هي نفسها **بلا هذا القانون وحده**.",
         "- **وكلّ ما عداه كما هو في الحيّ:** القرار عند كلّ إغلاق ربع ساعة · الجهة داو الأربع ساعات (209) · التأكيد ترتيب متوسّطات"
         " 5 و10 و50 على الربع ساعة · وقف البنية (202) بين %g و%g بِب بلا تحجيم · الأثلاث وهدف الثلاثة أضعاف · نافذة نيويورك وحدها"
         " ولا دخول في أوّل ربع ساعة · لا يوم عطلة ولا إغلاقٍ مبكر · الخبر الأحمر 15 دقيقة قبل وبعد لعملات الأصل والدولار ·"
         " ساعة وربع بعد كلّ صفقة · الكلفة 1.5 بِب · حدود الحساب بمعادلة الحيّ." % tuple(band),
         "- **لا تبييت (القانونان 19 و20):** كلّ صفقةٍ لم تنتهِ تُغلق كاملةً عند نهاية نافذة نيويورك على سعر السوق، وكلّ صفقةٍ"
         " مفتوحة تُغلق قبل الخبر الأحمر بربع ساعة.",
         "- **في التقرير:** كلّ سنة وكلّ شهر بشكل المالك · الجهة العشوائيّة · مرّات سقوط الحساب · ما أُغلق عند نهاية النافذة قبل"
         " الهدف الأخير وبكم · الصفقات بساعة الدخول بساعة المالك.",
         "- **السنتان:** %s · الرمز: %s." % (" و".join(y[0][:4] for y in years), SYMBOL_AR.get(sym, sym)),
         "- **كلّ تجربةٍ كاملة بملفّاتها** في مجلّد «التجارب» بجانب هذا الملفّ."]
    return "\n".join(L) + "\n"


# ── which detector knows the session's turn earlier and better (the owner's seal «نقيس الثلاثة قيس nq», 24/10) ─────────
#: «داو 4 ساعات لازم يقرا شارت كامل … بالأخير بقول اتّجاه جلسة» · «ومؤشّرات تقرا سوق كامل كمان» · and the price's answer at his
#: levels. A direction measurement, no trades: each detector alone, from the session's opening direction, says when it turned.
DETECTORS_AR = {"dow": "(أ) داو الأربع ساعات", "ema": "(ب) المتوسّطات 5 و10 و50 على الربع ساعة",
                "levels": "(ج) ردّ السعر عند مستويات الخريطة على الخمس دقائق"}
DETECTOR_REVERSE_S = 30 * 60
DETECTOR_HORIZON_AR = {"1h": "بعد ساعة", "close": "حتّى إغلاق الجلسة"}
#: the paper's step 6, word for word -- written into «الاختبار.md» before the first run
DETECTORS_CRITERION = ("الكاشف الذي يصيب فوق السوق بعد ساعة وحتّى الإغلاق في 2022 و2023 كلتيهما، وأبكرها سبقًا بين من يصيب."
                       " وإن لم يصب أحدها فوق السوق في السنتين يُقال «لا» بالأرقام.")


def session_windows(symbol: str, t0: float, t1: float) -> list[tuple[float, float]]:
    """The asset's windows (opening, close) that open in [t0, t1), without the no-trade days (law 22)."""
    from zoneinfo import ZoneInfo

    from shared import day_levels, market_clock, red_lines
    name = red_lines.session_of(symbol)
    zone = ZoneInfo(red_lines.SESSIONS[name][0]) if name in red_lines.SESSIONS else None
    out = []
    day, last = datetime.fromtimestamp(t0, timezone.utc).date() - timedelta(days=1), datetime.fromtimestamp(t1, timezone.utc).date()
    while day <= last:
        day += timedelta(days=1)
        if zone is not None:
            hm = red_lines.SESSIONS[name][2]
            probe = datetime(day.year, day.month, day.day, hm[0], hm[1], tzinfo=zone).timestamp() - 1
        else:
            probe = datetime(day.year, day.month, day.day, 23, 59, tzinfo=timezone.utc).timestamp()
        wins = day_levels.windows(probe, symbol, count=1)
        if wins and t0 <= wins[0][0] < t1 and not market_clock.no_trade_day(wins[0][0] + 60) and wins[0] not in out:
            out.append(wins[0])
    return out


def dow4h_sides(symbol: str, t0: float, t1: float, moments: np.ndarray) -> tuple[np.ndarray, str]:
    """Atom 209's «four hours» reading at each moment (+1 rising, -1 falling, 0 none): from its facts store when one covers
    the period, else from the four-hour candles by the shared Dow -- the very calculation 209 runs (on 2023 the two agree
    at 99.6 of 100 session moments, 6,584 of them)."""
    from shared import dow_theory
    y0 = datetime.fromtimestamp(t0, timezone.utc).strftime("%Y-%m-%d")
    y1 = datetime.fromtimestamp(t1, timezone.utc).strftime("%Y-%m-%d")
    try:
        store = _plan_store(symbol, y0, y1)
    except SystemExit:
        store = None
    if store is not None:
        t, v, f = Facts(store).series("209", "15m", "readings.four_hours.trend")
        vals, ok = Facts.at(t, v, moments, None)
        vocab = f.get("vocab") or []
        return np.array([word_side(vocab[int(i)]) if ok[n] and 0 <= int(i) < len(vocab) else 0
                         for n, i in enumerate(vals)], dtype=int), "مخزن الذرّة 209"
    b = np.array(_bars_db(symbol, "H4", t0 - 400 * 86400, t1), dtype=float)
    trends, _ = dow_theory.trend_series(list(b[:, 4]))
    idx = np.searchsorted(b[:, 0] + 14400, moments, side="right") - 1
    return np.array([word_side(trends[i]) if i >= 0 else 0 for i in idx], dtype=int), "شموع الأربع ساعات بحساب داو المشترك"


def detector_flips(state: int, times: list[float], sides: list[int]) -> list[tuple[float, int]]:
    """From the opening direction: a turn wherever the detector reads the side opposite to its standing direction; the
    new side then stands. (time, new side) in order."""
    out = []
    for t, s in zip(times, sides):
        if s and s == -state:
            state = s
            out.append((t, s))
    return out


def _detector_period(sym: str, t0: float, t1: float, log) -> dict[str, Any]:
    """Every session of [t0, t1): its opening direction, each detector's turns with what price did after them, and the
    market's own moves at every quarter-hour close of the sessions (the base line)."""
    from shared import red_lines
    from shared.pips import to_pips
    wins = session_windows(sym, t0, t1)
    ends15, closes15 = decision_moments(sym, "15m", t0 - 86400, t1)
    b5 = np.array(_bars_db(sym, "M5", t0 - 7 * 86400, t1), dtype=float)
    ends5 = b5[:, 0] + 300 if len(b5) else np.zeros(0)
    mins = load_minutes(sym, t0 - 86400, t1 + 3 * 86400)
    m15_rows = _bars_db(sym, "M15", t0 - 40 * 86400, t1)
    d1_rows = _bars_db(sym, "D1", t0 - 60 * 86400, t1)
    t15 = np.array([r[0] for r in m15_rows]) + 900
    td1 = np.array([r[0] for r in d1_rows]) + 86400
    first_s = float(DEFAULTS["session"]["first_minutes"]) * 60
    opens = np.array([o for o, _ in wins], dtype=float)
    inside = np.zeros(len(ends15), dtype=bool)
    for o, c in wins:
        inside |= (ends15 >= o + first_s) & (ends15 < c)
    probe = np.concatenate([opens, ends15[inside]])
    order = np.argsort(probe, kind="stable")
    probe_sorted = probe[order]
    dow_all, dow_from = dow4h_sides(sym, t0, t1, probe_sorted)
    price_at = lambda x: float(mins["c"][max(0, int(np.searchsorted(mins["t"], x, side="right")) - 1)])
    ema_all = np.array([word_side(w) for w in virtual_values("ema", probe_sorted, sym, np.zeros(0),
                                                             np.array([price_at(x) for x in probe_sorted]))["order.15m"]])
    side_at = {"dow": dict(zip(probe_sorted.tolist(), dow_all.tolist())), "ema": dict(zip(probe_sorted.tolist(), ema_all.tolist()))}
    signals: dict[str, list[dict]] = {k: [] for k in DETECTORS_AR}
    market = {"1h": [], "close": []}
    sessions, skipped = [], 0
    for (o, c) in wins:
        d_dow, d_ema = side_at["dow"].get(o, 0), side_at["ema"].get(o, 0)
        d0 = d_dow or d_ema                          # agree: that · disagree: Dow («بالأخير بقول اتّجاه جلسة») · no Dow: the averages
        if not d0:
            skipped += 1
            continue
        q = ends15[(ends15 >= o + first_s) & (ends15 < c)]
        for m in q.tolist():
            p = price_at(m)
            market["1h"].append(_signed_pips(price_at(m + 3600) - p, sym))
            market["close"].append(_signed_pips(price_at(c) - p, sym))
        turns = {k: detector_flips(d0, q.tolist(), [side_at[k][m] for m in q.tolist()]) for k in ("dow", "ema")}
        a, b = int(np.searchsorted(ends5, o + first_s, side="left")), int(np.searchsorted(ends5, c, side="left"))
        if b > a and a >= 2:
            j15, jd = int(np.searchsorted(t15, o, side="right")), int(np.searchsorted(td1, o, side="right"))
            levels = [v for _, v in trader_levels(sym, o, m15_rows[max(0, j15 - 1600):j15], d1_rows[max(0, jd - 140):jd],
                                                  price_at(o))]
            cc, hh, ll = b5[a - 2:b, 4], b5[a - 2:b, 2], b5[a - 2:b, 3]
            buy, sell = np.zeros(b - a, dtype=bool), np.zeros(b - a, dtype=bool)
            for lv in levels:
                for scenario in ("false", "break"):
                    sig = level_signals(cc, hh, ll, lv, scenario)[2:]
                    buy |= sig > 0
                    sell |= sig < 0
            # a candle may answer both ways at two levels: the side against the standing direction is the one that turns it
            st, out_ = d0, []
            for t_, bu, se in zip(ends5[a:b].tolist(), buy, sell):
                if (st > 0 and se) or (st < 0 and bu):
                    st = -st
                    out_.append((t_, st))
            turns["levels"] = out_
        else:
            turns["levels"] = []
        local = datetime.fromtimestamp(o, timezone.utc).astimezone(timezone(timedelta(hours=3)))
        sessions.append({"day": local.date().isoformat(), "open": o, "close": c, "opening": d0, "dow": d_dow, "ema": d_ema,
                         "turns": {k: len(v) for k, v in turns.items()}})
        for k, tl in turns.items():
            start = o
            for n, (m, s) in enumerate(tl):
                p = price_at(m)
                a_, b_ = int(np.searchsorted(mins["t"], start, side="left")), int(np.searchsorted(mins["t"], m, side="right"))
                ext = float(mins["h"][a_:b_].max()) if s < 0 and b_ > a_ else float(mins["l"][a_:b_].min()) if b_ > a_ else p
                tm = datetime.fromtimestamp(m, timezone.utc).astimezone(timezone(timedelta(hours=3)))
                signals[k].append({"day": local.date().isoformat(), "time": tm.strftime("%H:%M"), "t": m, "side": s,
                                   "price": round(p, 2), "1h": _signed_pips(price_at(m + 3600) - p, sym),
                                   "close": _signed_pips(price_at(c) - p, sym), "early": abs(to_pips(ext - p, sym)),
                                   "reversed": n + 1 < len(tl) and tl[n + 1][0] - m <= DETECTOR_REVERSE_S})
                start = m
    return {"signals": signals, "market": {h: np.array(v) for h, v in market.items()}, "sessions": sessions,
            "skipped": skipped, "dow_from": dow_from}


def _detector_stats(sig: list[dict], market: dict[str, np.ndarray], n_sessions: int) -> dict[str, Any]:
    out: dict[str, Any] = {"إشارات": len(sig), "صعودًا": sum(1 for s in sig if s["side"] > 0),
                           "نزولًا": sum(1 for s in sig if s["side"] < 0),
                           "في_الجلسة": round(len(sig) / n_sessions, 2) if n_sessions else 0.0,
                           "رجعت_خلال_نصف_ساعة": sum(1 for s in sig if s["reversed"]),
                           "السبق_متوسّط": round(float(np.mean([s["early"] for s in sig])), 1) if sig else None,
                           "السبق_وسيط": round(float(np.median([s["early"] for s in sig])), 1) if sig else None}
    for h in ("1h", "close"):
        mv = market[h][np.isfinite(market[h])]
        up_rate = float((mv > 0).mean()) if len(mv) else 0.0
        down_rate = float((mv < 0).mean()) if len(mv) else 0.0
        way = np.array([s[h] * s["side"] for s in sig], dtype=float)
        expect = (out["صعودًا"] * up_rate + out["نزولًا"] * down_rate) / len(sig) if sig else 0.0
        expect_pts = (out["صعودًا"] * float(mv.mean()) - out["نزولًا"] * float(mv.mean())) / len(sig) if sig and len(mv) else 0.0
        hit = float((way > 0).mean()) if len(way) else 0.0
        out[h] = {"أصاب": round(100 * hit, 1), "السوق": round(100 * expect, 1), "الفرق": round(100 * (hit - expect), 1),
                  "نقاط": round(float(way.mean()), 1) if len(way) else 0.0, "نقاط_السوق": round(expect_pts, 1),
                  "خطأ_معياريّ": round(100 * math.sqrt(max(expect * (1 - expect), 1e-9) / len(sig)), 1) if sig else None,
                  "فوق_السوق": bool(sig) and hit > expect}
    return out


def session_detectors(cfg: dict[str, Any], log=print) -> Path:
    """The three detectors of the session's turn (the owner's paper of 24/10, «نقيس الثلاثة»): per year their accuracy after
    an hour and to the session's close against the market itself, how early, how many and how many undone within half an
    hour; per month; and the session of 23/10 as the example."""
    began = time.time()
    sym = cfg.get("symbol", "USTEC")
    years = [tuple(y) for y in cfg["years"]]
    name = cfg.get("name") or "الكواشف الثلاثة لتغيّر اتّجاه الجلسة — %s — %s" % (SYMBOL_AR.get(sym, sym), " و".join(y[0][:4] for y in years))
    folder = OUT_ROOT / date.today().isoformat() / safe(name)
    if folder.exists():
        folder = OUT_ROOT / date.today().isoformat() / safe("%s (%s)" % (name, datetime.now().strftime("%H-%M-%S")))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "الاختبار.md").write_text(_detectors_test_md(name, sym, years, cfg.get("example")), encoding="utf-8")
    results: dict[str, Any] = {}
    rows_csv = []
    for y0, y1 in years:
        per = _detector_period(sym, _epoch(y0), _epoch(y1), log)
        n_s = len(per["sessions"])
        year = y0[:4]
        res = {"جلسات": n_s, "بلا_اتّجاه_افتتاح": per["skipped"], "مصدر_داو": per["dow_from"], "الكواشف": {}, "الأشهر": {}}
        for k, sig in per["signals"].items():
            res["الكواشف"][k] = _detector_stats(sig, per["market"], n_s)
            months: dict[str, list] = {}
            for s in sig:
                c_ = months.setdefault(s["day"][:7], [0, 0, 0, 0.0])
                c_[0] += 1
                c_[1] += int(s["1h"] * s["side"] > 0)
                c_[2] += int(s["close"] * s["side"] > 0)
                c_[3] += s["close"] * s["side"]
            res["الأشهر"][k] = {m: {"إشارات": v[0], "أصاب_بعد_ساعة": round(100 * v[1] / v[0]), "أصاب_حتّى_الإغلاق": round(100 * v[2] / v[0]),
                                    "نقاط_حتّى_الإغلاق": round(v[3], 1)} for m, v in sorted(months.items())}
            for s in sig:
                rows_csv.append({"السنة": year, "الكاشف": DETECTORS_AR[k], "اليوم": s["day"], "الساعة": s["time"],
                                 "الجهة الجديدة": "صاعد" if s["side"] > 0 else "هابط", "السعر": s["price"],
                                 "بعد ساعة (نقاط في جهته)": round(s["1h"] * s["side"], 1),
                                 "حتّى الإغلاق (نقاط في جهته)": round(s["close"] * s["side"], 1),
                                 "السبق (نقاط)": round(s["early"], 1), "رجعت خلال نصف ساعة": "نعم" if s["reversed"] else "لا"})
        results[year] = res
        log("الكواشف: %s انتهت — %d جلسة · إشارات %s" % (year, n_s, " · ".join("%s %d" % (k, len(v)) for k, v in per["signals"].items())))
    example = None
    if cfg.get("example"):
        e0 = _epoch(cfg["example"])
        per = _detector_period(sym, e0, e0 + 86400, log)
        example = {"اليوم": cfg["example"], "مصدر_داو": per["dow_from"], "الجلسة": per["sessions"][0] if per["sessions"] else None,
                   "الإشارات": {k: [{kk: s[kk] for kk in ("time", "side", "price", "1h", "close", "early")} for s in v]
                                for k, v in per["signals"].items()}}
        log("الكواشف: جلسة %s مثالًا انتهت" % cfg["example"])
    passing = [k for k in DETECTORS_AR
               if all(results[y]["الكواشف"][k][h]["فوق_السوق"] for y in results for h in ("1h", "close"))]
    early = {k: float(np.mean([results[y]["الكواشف"][k]["السبق_متوسّط"] for y in results
                               if results[y]["الكواشف"][k]["السبق_متوسّط"] is not None] or [float("inf")])) for k in passing}
    best = min(early, key=early.get) if early else None
    summary = {"kind": "detectors", "الاسم": name, "المجلّد": str(folder), "السنوات": results, "المثال": example,
               "يصيب_فوق_السوق": passing, "الحكم": ("نعم: " + DETECTORS_AR[best]) if best else "لا",
               "المعيار": DETECTORS_CRITERION, "الزمن": _span(time.time() - began)}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    if rows_csv:
        with (folder / "الإشارات.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_csv[0]))
            w.writeheader()
            w.writerows(rows_csv)
    (folder / "النتيجة.md").write_text(_detectors_result_md(name, summary), encoding="utf-8")
    log("الكواشف: انتهى في %s · الحكم %s" % (summary["الزمن"], summary["الحكم"]))
    return folder


def _detectors_test_md(name: str, sym: str, years: list, example: str | None) -> str:
    L = ["# %s" % name, "",
         "ختم المالك: «نقيس الثلاثة قيس nq» — قياسُ اتّجاهٍ لا صفقات: أيّ الثلاثة يعرف تغيّر اتّجاه الجلسة أبكر وأصحّ؟", "",
         "## معيار النجاح — الخطوة 6 من الورقة بنصّها، كُتب هنا قبل أوّل تشغيل", "", "> " + DETECTORS_CRITERION, "",
         "«فوق السوق» = نسبة إصابة الكاشف أعلى من نسبة السوق المتوقّعة لإشاراته، بعد ساعة وحتّى الإغلاق، في السنتين.", "",
         "## ما قيس", "",
         "- **الجلسة:** نافذة نيويورك وحدها، بلا يوم عطلة ولا إغلاقٍ مبكر. والإشارات بعد أوّل ربع ساعة منها.",
         "- **الاتّجاه عند الافتتاح:** داو الأربع ساعات (قراءة الذرّة 209) وترتيب المتوسّطات 5 و10 و50 على الربع ساعة، كلاهما على شارت"
         " السوق كاملًا عند الافتتاح. إن اتّفقا فهو، وإن اختلفا فداو، وإن لم يكن لداو جهةٌ فالمتوسّطات، وإن لم يكن لأحدهما جهةٌ لا تُقاس"
         " الجلسة وتُعدّ.",
         "- **الانقلاب، لكلّ كاشفٍ وحده:** يبدأ من اتّجاه الافتتاح، ويقول «انقلب» حين يقرأ الجهة المعاكسة لاتّجاهه القائم، ثمّ يقوم"
         " الاتّجاه الجديد عنده.",
         "  - **(أ) داو الأربع ساعات** عند كلّ إغلاق ربع ساعة.",
         "  - **(ب) ترتيب المتوسّطات 5 و10 و50 على الربع ساعة** عند كلّ إغلاق ربع ساعة.",
         "  - **(ج) ردّ السعر عند مستويات خريطة المتداول** (أعلى الأمس وأدناه وإغلاقه · أعلى الليل وأدناه · أعلى الأسبوع الماضي وأدناه ·"
         " الرقمان المستديران، مثبّتةً عند الافتتاح) عند كلّ إغلاق خمس دقائق: كسرٌ كاذب أو كسرٌ وثبات في الجهة المعاكسة للقائم،"
         " بتعريفَي رأس حربة المستويات نفسيهما.",
         "- **الصحّة:** بعد كلّ انقلاب، هل سار السعر في الجهة الجديدة بعد ساعة، وحتّى إغلاق الجلسة؟ من 100، ومتوسّط النقاط في جهته.",
         "- **السوق مرجعًا (كقياس ١٩/١٠):** نسبة ما صعد وما نزل في المدّة نفسها، من كلّ إغلاقات الربع ساعة في الجلسات، في السنة نفسها."
         " ولكلّ كاشفٍ «نسبة السوق المتوقّعة» بعدد إشاراته صعودًا ونزولًا.",
         "- **السبق:** النقاط بين أعلى قمّةٍ (للانقلاب نزولًا) أو أدنى قاع (للانقلاب صعودًا) منذ بدأ الاتّجاه القائم عند الكاشف، وسعر"
         " الإشارة. الأقلّ أبكر.",
         "- **الكثرة:** الإشارات في الجلسة، وكم منها قلبها الكاشف نفسه خلال نصف ساعة.",
         "- **السنتان:** %s · الرمز: %s · داو في السنتين من مخزن الذرّة 209%s." % (
             " و".join(y[0][:4] for y in years), SYMBOL_AR.get(sym, sym),
             " · وجلسة %s مثالًا، وداوها من شموع الأربع ساعات بحساب داو المشترك (يطابق المخزن في 99.6 من 100 من لحظات 2023)" % example
             if example else "")]
    return "\n".join(L) + "\n"


def _detectors_result_md(name: str, summary: dict[str, Any]) -> str:
    years = summary["السنوات"]
    ys = list(years)
    L = ["# النتيجة — %s" % name, "", "## الحكم بمعيار النجاح المكتوب قبل النتيجة (الخطوة 6)", "", "> " + summary["المعيار"], "",
         "| الكاشف | %s | يصيب فوق السوق؟ |" % " | ".join("%s %s: أصاب · السوق" % (y, DETECTOR_HORIZON_AR[h]) for y in ys for h in ("1h", "close")),
         "|---|" + "---|" * (2 * len(ys)) + "---|"]
    for k, nm in DETECTORS_AR.items():
        cells = []
        for y in ys:
            for h in ("1h", "close"):
                c = years[y]["الكواشف"][k][h]
                cells.append("%.1f · %.1f (%+.1f ±%s)" % (c["أصاب"], c["السوق"], c["الفرق"],
                                                          "—" if c["خطأ_معياريّ"] is None else "%.1f" % c["خطأ_معياريّ"]))
        L.append("| %s | %s | %s |" % (nm, " | ".join(cells), "نعم" if k in summary["يصيب_فوق_السوق"] else "لا"))
    L += ["", "**الجواب: %s.**" % summary["الحكم"], "",
          "«أصاب» = من 100 إشارة، كم سار السعر بعدها في الجهة الجديدة. «السوق» = ما يعطيه السوق نفسه لإشاراتٍ بهذا العدد صعودًا ونزولًا."
          " والفرق بين القوسين، ومعه ± ما تعطيه الصدفة وحدها لهذا العدد من الإشارات (فرقٌ أصغر منه لا يُفرَّق عن الصدفة). والحكم بالمعيار"
          " كما كُتب: «فوق السوق».", ""]
    for y in ys:
        r = years[y]
        L += ["## %s — %d جلسة (بلا اتّجاه افتتاحٍ: %d) · داو من %s" % (y, r["جلسات"], r["بلا_اتّجاه_افتتاح"], r["مصدر_داو"]), "",
              "| الكاشف | إشارات | في الجلسة | صعودًا · نزولًا | رجعت خلال نصف ساعة | بعد ساعة: أصاب · السوق · نقاط | حتّى الإغلاق: أصاب · السوق · نقاط | السبق (نقاط): متوسّط · وسيط |",
              "|---|---|---|---|---|---|---|---|"]
        for k, nm in DETECTORS_AR.items():
            s = r["الكواشف"][k]
            cell = lambda h: "%.1f · %.1f · %+.1f" % (s[h]["أصاب"], s[h]["السوق"], s[h]["نقاط"]) if s["إشارات"] else "—"
            L.append("| %s | %d | %.2f | %d · %d | %d (%s) | %s | %s | %s |" % (
                nm, s["إشارات"], s["في_الجلسة"], s["صعودًا"], s["نزولًا"], s["رجعت_خلال_نصف_ساعة"],
                ("%.0f من 100" % (100 * s["رجعت_خلال_نصف_ساعة"] / s["إشارات"])) if s["إشارات"] else "—", cell("1h"), cell("close"),
                ("%.1f · %.1f" % (s["السبق_متوسّط"], s["السبق_وسيط"])) if s["إشارات"] else "—"))
        L.append("")
        for k, nm in DETECTORS_AR.items():
            months = r["الأشهر"][k]
            L += ["### أشهر %s — %s" % (y, nm), "", "| الشهر | إشارات | أصاب بعد ساعة من 100 | أصاب حتّى الإغلاق من 100 | نقاط حتّى الإغلاق |",
                  "|---|---|---|---|---|"]
            L += ["| %s | %d | %d | %d | %+.1f |" % (m, v["إشارات"], v["أصاب_بعد_ساعة"], v["أصاب_حتّى_الإغلاق"], v["نقاط_حتّى_الإغلاق"])
                  for m, v in months.items()] or ["| — | لا إشارة | | | |"]
            L.append("")
    ex = summary.get("المثال")
    if ex:
        s0 = ex.get("الجلسة")
        word = lambda v: "صاعد" if v > 0 else "هابط" if v < 0 else "بلا جهة"
        L += ["## جلسة %s مثالًا — متى قال كلّ كاشفٍ إنّ الاتّجاه انقلب (بساعة المالك)" % ex["اليوم"], ""]
        if s0:
            L.append("- **الاتّجاه عند الافتتاح:** %s (داو الأربع ساعات %s · المتوسّطات %s) · داو من %s." % (
                word(s0["opening"]), word(s0["dow"]), word(s0["ema"]), ex["مصدر_داو"]))
            L.append("")
            for k, nm in DETECTORS_AR.items():
                sig = ex["الإشارات"].get(k) or []
                L += ["### %s" % nm, ""]
                if not sig:
                    L += ["لم يقل «انقلب» في الجلسة.", ""]
                    continue
                L += ["| الساعة | انقلب إلى | السعر | بعد ساعة (نقاط في جهته) | حتّى الإغلاق (نقاط في جهته) | السبق (نقاط) |", "|---|---|---|---|---|---|"]
                L += ["| %s | %s | %s | %+.1f | %+.1f | %.1f |" % (s["time"], word(s["side"]), "{:,.1f}".format(s["price"]),
                                                               s["1h"] * s["side"], s["close"] * s["side"], s["early"]) for s in sig]
                L.append("")
        else:
            L += ["لا جلسة قابلة للقياس في هذا اليوم.", ""]
    L += ["كلّ إشارةٍ بساعتها ونتيجتها في «الإشارات.csv» بجانب هذا الملفّ. الزمن: %s." % summary["الزمن"]]
    return "\n".join(L) + "\n"


# ── the system as it is, on its seven pairs (the owner, 25/10 at night: «قيس شغلات سستم») ─────────────────────────────────
#: After laws 17 and 21 changed (no new trade in the last hour; the general window to 16:00 New York): the live combination 415
#: as the code holds it, on every pair it trades, with every red line and the account limits as saved by 509 -- for
#: knowledge, no verdict.
SYSTEM_SYMBOLS = ("USTEC", "US30", "US500", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")
#: each pair's cost in pips, as the seven-pair grid of 18/10 measured it
SYSTEM_COST_PIPS = {"USTEC": 1.5, "US30": 1.1, "US500": 0.8, "XAUUSD": 2.1, "BTCUSD": 7.5, "EURUSD": 0.9, "GBPUSD": 1.0}
QUICK_ATOMS = "201,202,209"                    # what 415 reads from a facts store: swings, the external structure, Dow
LIMITS_SNAPSHOT = ROOT / "forex_runtime" / "var" / "forex" / "snapshots" / "509.json"
SYSTEM_GROUPS = ("التوليفة", "مرجع: جهة عشوائيّة")


def saved_account_limits() -> tuple[dict[str, Any], str]:
    """The account limits as atom 509 last saved them (read only), else the owner's first values."""
    try:
        raw = json.loads(LIMITS_SNAPSHOT.read_text(encoding="utf-8")).get("settings")
    except (OSError, ValueError, AttributeError):
        raw = None
    return _account_limits.normalize(raw), ("لقطة الذرّة 509 المحفوظة" if raw else "القيم الأولى (لا لقطة محفوظة)")


def _quick_stores(jobs: list[tuple[str, str, str]], log) -> dict[tuple[str, str], Path | None]:
    """The quick facts store (201, 202, 209) of each (symbol, year); the machine builds the missing ones first, all at once."""
    import subprocess
    out: dict[tuple[str, str], Path | None] = {}
    build = []
    for sym, y0, y1 in jobs:
        try:
            out[(sym, y0)] = _plan_store(sym, y0, y1)
        except SystemExit:
            path = ROOT / "forex_runtime" / "var" / "facts_store_quick" / sym / ("%s_%s" % (y0, y1))
            build.append((sym, y0, y1, path))
    if build:
        log("المنظومة: يبني الجهاز %d مخزنًا ناقصًا معًا (%s) …" % (len(build), " · ".join("%s %s" % (SYMBOL_AR.get(s, s), y[:4])
                                                                                      for s, y, _, _ in build)))
        procs = [(sym, y0, path, subprocess.Popen(
            [sys.executable, "-m", "backtest.facts_store", "--symbol", sym, "--from", y0, "--to", y1, "--warm-days", "60",
             "--out", str(path), "--atoms", QUICK_ATOMS], cwd=str(ROOT))) for sym, y0, y1, path in build]
        for sym, y0, path, proc in procs:
            proc.wait()
            out[(sym, y0)] = path if (path / "index.json").exists() else None
            log("المنظومة: مخزن %s %s %s" % (SYMBOL_AR.get(sym, sym), y0[:4], "اكتمل" if out[(sym, y0)] else "لم يكتمل"))
    return out


def system_plan(cfg: dict[str, Any], log=print) -> Path:
    """The live combination as the code holds it today on each of its pairs and years, and the seven pairs together on one
    virtual account with the saved limits."""
    from shared.facts_strategies import STOP_PAD_PIPS, STOP_PAD_PIPS_DEFAULT, STOP_PIPS, STOP_PIPS_DEFAULT
    began = time.time()
    symbols = [s for s in cfg.get("symbols") or SYSTEM_SYMBOLS]
    years = [tuple(y) for y in cfg["years"]]
    limits, limits_from = saved_account_limits()
    name = cfg.get("name") or "المنظومة كما هي بالقانونين 17 و21 — الأزواج السبعة — %s" % " و".join(y[0][:4] for y in years)
    folder = OUT_ROOT / date.today().isoformat() / safe(name)
    if folder.exists():
        folder = OUT_ROOT / date.today().isoformat() / safe("%s (%s)" % (name, datetime.now().strftime("%H-%M-%S")))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "الاختبار.md").write_text(_system_test_md(name, symbols, years, limits, limits_from), encoding="utf-8")
    stores = _quick_stores([(s, y0, y1) for s in symbols for y0, y1 in years], log)
    runs: dict[str, dict[str, Any]] = {}
    together: dict[str, dict[str, list]] = {y0[:4]: {g: [] for g in SYSTEM_GROUPS} for y0, _ in years}
    all_rows = []
    for sym in symbols:
        risk_pct = _account_limits.pair_pcts(limits, sym)[0]
        for y0, y1 in years:
            year = y0[:4]
            store = stores.get((sym, y0))
            if store is None:
                runs["%s|%s" % (sym, year)] = {"الزوج": sym, "السنة": year, "بلا_مخزن": True}
                log("المنظومة: %s %s بلا مخزن — لم يُقس" % (SYMBOL_AR.get(sym, sym), year))
                continue
            spec = json.loads(json.dumps({**LIVE_COMBO, "symbol": sym, "from": y0, "to": y1, "store": str(store),
                                          "name": "التوليفة الحيّة — %s — %s" % (SYMBOL_AR.get(sym, sym), year)}))
            spec["stop"].update({"band": list(STOP_PIPS.get(sym, STOP_PIPS_DEFAULT)),
                                 "pad": float(STOP_PAD_PIPS.get(sym, STOP_PAD_PIPS_DEFAULT))})
            spec.update({"cost_pips": SYSTEM_COST_PIPS.get(sym, 1.5), "risk_pct": risk_pct,
                         "balance": limits[_account_limits.INITIAL_BALANCE], "account_limits": limits})
            res = run(merged(spec), log=log)
            sub = write(res, Facts(Path(res["store"])).index.get("names", {}), root=folder / "التجارب")
            summ = json.loads((sub / "summary.json").read_text(encoding="utf-8"))
            out: dict[str, Any] = {"الزوج": sym, "السنة": year, "المجلّد": sub.name, "الكلفة": spec["cost_pips"],
                                   "الوقف": spec["stop"]["band"]}
            for g, rows in res["trades"].items():
                res_g = summ["النتائج"][g]
                out[g] = {"الإحصاء": res_g["الإحصاء"], "الأشهر": res_g["الأشهر"], "الحساب_الافتراضيّ": res_g["الحساب_الافتراضيّ"],
                          "الجلسات": _per_session(rows), "عند_نهاية_النافذة": _window_end(rows)}
                together[year][g] += [(_exit_epoch(t), sym, float(t["r"])) for t in rows]
                all_rows += [{"الزوج": SYMBOL_AR.get(sym, sym), "السنة": year, "المجموعة": g, **t} for t in rows]
            out["لماذا_لا"] = res["skipped"].get("التوليفة", {})
            runs["%s|%s" % (sym, year)] = out
            log("المنظومة: %s %s — %d صفقة · باقي %d" % (SYMBOL_AR.get(sym, sym), year, len(res["trades"]["التوليفة"]),
                len(symbols) * len(years) - len(runs)))
    account = {y: {g: _account_limits.simulate(sorted(v), limits) for g, v in groups.items()} for y, groups in together.items()}
    summary = {"kind": "system", "الاسم": name, "المجلّد": str(folder), "الحكم": "قياسٌ للمعرفة — بلا حكم", "للمعرفة": True,
               "الأزواج": symbols, "السنوات": [y[0][:4] for y in years], "التجارب": runs, "الحساب_معًا": account,
               "الحدود": limits, "مصدر_الحدود": limits_from, "الناسداك_قبلًا": _nasdaq_before(),
               "الزمن": _span(time.time() - began)}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    if all_rows:
        fields = list(dict.fromkeys(k for r in all_rows for k in r))
        with (folder / "الصفقات.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(all_rows)
    (folder / "النتيجة.md").write_text(_system_result_md(name, summary), encoding="utf-8")
    log("المنظومة: انتهى في %s" % summary["الزمن"])
    return folder


def _nasdaq_before() -> dict[str, Any] | None:
    """The Nasdaq measured the night of 23-24/10 (the button «without the time law»): with the old law 21 and without it."""
    for f in sorted(OUT_ROOT.glob("*/التوليفة الحيّة بلا قانون «الوقت يكفي» — للمعرفة — الناسداك*/summary.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out = {}
        for key, r in (s.get("التجارب") or {}).items():
            year, label = key.split("|", 1)
            stats_ = (r.get("التوليفة") or {}).get("الإحصاء") or {}
            ref = (r.get("مرجع: جهة عشوائيّة") or {}).get("الإحصاء") or {}
            out.setdefault(year, {})["بلا" if label.startswith("بلا") else "بالقديم"] = {
                "صفقات": stats_.get("صفقات"), "هدف_1": stats_.get("بلغ_الهدف_1"), "هدف_2": stats_.get("بلغ_الهدف_2"),
                "هدف_3": stats_.get("بلغ_الهدف_3"), "وقف": stats_.get("وقف_قبل_أيّ_هدف"),
                "نزل": stats_.get("أعمق_نزول_تحت_البداية_٪"), "صافي": stats_.get("صافي_٪"), "العشوائيّ": ref.get("صافي_٪")}
        return out
    return None


def _system_test_md(name: str, symbols: list, years: list, limits: dict[str, Any], limits_from: str) -> str:
    from shared.facts_strategies import STOP_PAD_PIPS, STOP_PAD_PIPS_DEFAULT, STOP_PIPS, STOP_PIPS_DEFAULT
    L = ["# %s" % name, "",
         "أمر المالك (٢٥/١٠ مساءً، بعد أن عرف أنّ القانونين الجديدين 17 و21 لم يُقاسا): «قيس شغلات سستم».", "",
         "**قياسٌ للمعرفة، بلا معيار نجاح:** لم يطلب المالك حكمًا، فالتقرير أرقامٌ بلا حكم. ولا يُلمس شيءٌ في الحيّ.", "",
         "## ما قيس", "",
         "- **التوليفة الحيّة 415 كما هي في الشيفرة:** القرار عند كلّ إغلاق ربع ساعة · الجهة داو الأربع ساعات (الذرّة 209) · التأكيد ترتيب"
         " متوسّطات 5 و10 و50 على الربع ساعة في جهة الصفقة · وقف البنية خلف آخر قاعٍ أو قمّة (الذرّة 202) على الخمس ثمّ الربع ثمّ الدقيقة،"
         " بحدود كلّ زوجٍ من جدول المنظومة نفسه وهامشه، بلا تحجيم · الأثلاث وهدف الثلاثة أضعاف.",
         "- **القانونان الجديدان (٢٥/١٠):** لا صفقة جديدة في الساعة الأخيرة من نافذة الأصل، والمفتوح يكمل ويُغلق عند نهايتها · والذهب"
         " والبتكوين على النافذة العامّة حتّى 16:00 نيويورك (23:00 بساعة تركيا اليوم).",
         "- **وكلّ قانونٍ آخر كما هو:** كلّ أصلٍ مع بورصته · أوّل ربع ساعة ممنوع · لا عطلة ولا إغلاقٍ مبكر · الخبر الأحمر 15 دقيقة قبل"
         " وبعد لعملات الأصل والدولار، ويُغلق المفتوح قبله · ساعة وربع بعد كلّ صفقة · لا تبييت.",
         "- **حدود الحساب (%s):** الرصيد الابتدائيّ %s · مخاطرة الصفقة %s٪ · حدّ الزوج اليوميّ %s٪ · الحدّ اليوميّ الشامل %s٪ ·"
         " التراجع الكلّيّ %s٪ · وأرقام خاصّة بزوج: %s." % (
             limits_from, "{:,.0f}".format(limits[_account_limits.INITIAL_BALANCE]), limits[_account_limits.PAIR_RISK_PCT],
             limits[_account_limits.PAIR_DAILY_PCT], limits[_account_limits.DAILY_PCT], limits[_account_limits.TOTAL_PCT],
             "، ".join("%s %s" % (SYMBOL_AR.get(k, k), v) for k, v in (limits.get(_account_limits.PAIRS) or {}).items()) or "لا شيء"),
         "- **الحساب الافتراضيّ للأزواج السبعة معًا** بالمعادلة الواحدة للحيّ والقياس، بالحدود نفسها.",
         "- **كالحيّ منذ إصلاح ٢٦/١٠ (ختم المالك «NQ»):** يُردّ كلّ وقفٍ أقصر من حارس أدنى الوقف في 555 (الإس آند بي 8 بِب · البتكوين 50 ·"
         " الداو 10 · الذهب 15 · الناسداك 9 · العملات 5) · وأخبار سجلّ التقويم بساعة خادمه الثابتة (+3)، فلا تتأخّر أخبار الشتاء ساعة.",
         "- **الأزواج، وحدود الوقف بالبِب، والكلفة بالبِب (كما قاستها شبكة ١٨/١٠):**"]
    for s in symbols:
        lo, hi = STOP_PIPS.get(s, STOP_PIPS_DEFAULT)
        L.append("  - %s: الوقف %g–%g · الهامش %g · الكلفة %g" % (SYMBOL_AR.get(s, s), lo, hi, STOP_PAD_PIPS.get(s, STOP_PAD_PIPS_DEFAULT),
                                                           SYSTEM_COST_PIPS.get(s, 1.5)))
    L += ["- **السنتان:** %s. والمخازن الناقصة (داو والقمم والهيكل) يبنيها الجهاز أوّلًا بالذرّات الحقيقيّة 201 و202 و209." % " و".join(
              y[0][:4] for y in years),
          "- **كلّ زوجٍ وسنة بملفّاتهما الستّة** في مجلّد «التجارب» بجانب هذا الملفّ."]
    return "\n".join(L) + "\n"


def _system_result_md(name: str, summary: dict[str, Any]) -> str:
    runs, ys, syms = summary["التجارب"], summary["السنوات"], summary["الأزواج"]
    lim = summary["الحدود"]
    bal = float(lim[_account_limits.INITIAL_BALANCE])
    g0, g1 = SYSTEM_GROUPS
    dip = lambda low: "ربح مباشرة" if low >= 0 else "{:.1f}٪ ({:,.0f}$)".format(low, bal * low / 100.0)
    money = lambda pct: "{:+,.0f}$".format(pct * bal / 100.0)
    nm = lambda s: SYMBOL_AR.get(s, s)
    L = ["# النتيجة — %s" % name, "",
         "**قياسٌ للمعرفة بأمر المالك، بلا حكم.** المخاطرة %s٪ من الرصيد الابتدائيّ %s$ في كلّ صفقة، والكلفة مخصومة. «على %s$» = النسبة"
         " مضروبةً في الرصيد الابتدائيّ. والحدود من %s." % (lim[_account_limits.PAIR_RISK_PCT], "{:,.0f}".format(bal), "{:,.0f}".format(bal),
                                                         summary["مصدر_الحدود"]), "",
         "## 1. الأزواج السبعة معًا — الحساب الافتراضيّ بحدود الحيّ", "",
         "| السنة | المجموعة | صفقات | مُسقطة بالحدود | سقوط الحساب | أيّام وقفها الحدّ الشامل | وقفات حدّ الزوج | أسوأ يوم | أدنى حقوق | الصافي |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for y in ys:
        for g in (g0, g1):
            s = summary["الحساب_معًا"][y][g]
            L.append("| %s | %s | %d | %d | **%d** | %d | %d | %.0f$ | %s$ | %s$ |" % (
                y, "المنظومة" if g == g0 else "عشوائيّ", s["taken"], s["skipped"], s["account_falls"], s["daily_stops"],
                s["pair_stops"], s["max_day_loss"], "{:,.0f}".format(s["lowest_equity"]), "{:+,.0f}".format(s["net"])))
    L += ["", "## 2. كلّ زوجٍ وكلّ سنة بشكل المالك", "",
          "| الزوج | السنة | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف | كم نزل قبل الربح | الصافي | على %s$ | العشوائيّ | سقوط الحساب (الزوج وحده) |" % (
              "{:,.0f}".format(bal)), "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s_ in syms:
        for y in ys:
            r = runs.get("%s|%s" % (s_, y)) or {}
            if r.get("بلا_مخزن"):
                L.append("| %s | %s | لم يُقس: المخزن لم يكتمل | | | | | | | | | |" % (nm(s_), y))
                continue
            st, rs = r[g0]["الإحصاء"], r[g1]["الإحصاء"]
            L.append("| %s | %s | %d | %d | %d | %d | %d | %s | %+.1f٪ | %s | %+.1f٪ | %d |" % (
                nm(s_), y, st["صفقات"], st.get("بلغ_الهدف_1", 0), st.get("بلغ_الهدف_2", 0), st.get("بلغ_الهدف_3", 0),
                st["وقف_قبل_أيّ_هدف"], dip(st["أعمق_نزول_تحت_البداية_٪"]), st["صافي_٪"], money(st["صافي_٪"]), rs["صافي_٪"],
                r[g0]["الحساب_الافتراضيّ"]["account_falls"]))
    L += ["", "«وقف» = ضربت الوقف كاملًا قبل أيّ هدف. «العشوائيّ» = الجهة عشوائيّة والقوانين نفسها.", ""]
    before = summary.get("الناسداك_قبلًا")
    L += ["## 3. الناسداك بجانب قياسَي ليلة ٢٣–٢٤/١٠", "",
          "| السنة | القانون 21 | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف | كم نزل قبل الربح | الصافي | العشوائيّ |", "|---|---|---|---|---|---|---|---|---|---|"]
    for y in ys:
        for key, label in (("بالقديم", "القديم: «الوقت يكفي»"), ("بلا", "بلا القانون 21")):
            b = ((before or {}).get(y) or {}).get(key)
            if b:
                L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %+.1f٪ | %+.1f٪ |" % (
                    y, label, b["صفقات"], b["هدف_1"], b["هدف_2"], b["هدف_3"], b["وقف"], dip(b["نزل"] or 0.0), b["صافي"] or 0.0,
                    b["العشوائيّ"] or 0.0))
        r = runs.get("USTEC|%s" % y) or {}
        if r and not r.get("بلا_مخزن"):
            st, rs = r[g0]["الإحصاء"], r[g1]["الإحصاء"]
            L.append("| %s | **الجديد: لا جديد في الساعة الأخيرة** | %d | %d | %d | %d | %d | %s | %+.1f٪ | %+.1f٪ |" % (
                y, st["صفقات"], st.get("بلغ_الهدف_1", 0), st.get("بلغ_الهدف_2", 0), st.get("بلغ_الهدف_3", 0), st["وقف_قبل_أيّ_هدف"],
                dip(st["أعمق_نزول_تحت_البداية_٪"]), st["صافي_٪"], rs["صافي_٪"]))
    if not before:
        L.append("| — | لم يوجد ملفّ قياس ليلة ٢٣–٢٤/١٠ | | | | | | | | |")
    L += ["", "## 4. ما أغلقته نهاية النافذة قبل الهدف الأخير، وكم صفقةً أخذت كلّ جلسة", "",
          "| الزوج | السنة | صفقات | أُغلقت عند نهاية النافذة | منها قبل أيّ هدف | صافيها | على %s$ | أُغلقت قبل خبرٍ أحمر | جلسات تداولت | بصفقة | بصفقتين | بثلاث فأكثر | أقصى في جلسة |" % (
              "{:,.0f}".format(bal)), "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s_ in syms:
        for y in ys:
            r = runs.get("%s|%s" % (s_, y)) or {}
            if r.get("بلا_مخزن"):
                continue
            w, j = r[g0]["عند_نهاية_النافذة"], r[g0]["الجلسات"]
            L.append("| %s | %s | %d | %d | %d | %+.1f٪ | %s | %d | %d | %d | %d | %d | %d |" % (
                nm(s_), y, r[g0]["الإحصاء"]["صفقات"], w["صفقات"], w["قبل_أيّ_هدف"], w["صافيها_٪"], money(w["صافيها_٪"]),
                w["قبل_الخبر"], j["جلسات"], j["بصفقة"], j["بصفقتين"], j["بثلاث_فأكثر"], j["أقصى"]))
    for s_ in syms:
        for y in ys:
            r = runs.get("%s|%s" % (s_, y)) or {}
            if r.get("بلا_مخزن"):
                continue
            ref = {m["الشهر"]: m["عائد_٪"] for m in r[g1]["الأشهر"]}
            L += ["", "## 5. أشهر %s — %s" % (y, nm(s_)), "",
                  "| الشهر | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف | كم نزل قبل الربح (من أوّل السنة) | الصافي | العشوائيّ |",
                  "|---|---|---|---|---|---|---|---|---|"]
            L += ["| %s | %d | %d | %d | %d | %d | %s | %+.1f٪ | %s |" % (
                m["الشهر"], m["صفقات"], m.get("هدف_1", 0), m.get("هدف_2", 0), m.get("هدف_3", 0), m["وقف"],
                dip(m.get("أدنى_حتّى_الآن_٪", 0.0)), m["عائد_٪"], ("%+.1f٪" % ref[m["الشهر"]]) if m["الشهر"] in ref else "—")
                  for m in r[g0]["الأشهر"]] or ["| — | لا صفقة | | | | | | | |"]
    L += ["", "كلّ زوجٍ وسنة بملفّاتهما الستّة في مجلّد «التجارب» بجانب هذا الملفّ، وكلّ الصفقات في «الصفقات.csv». الزمن: %s." % summary["الزمن"]]
    return "\n".join(L) + "\n"


def _levels_result_md(name: str, years: list, summary: dict[str, Any]) -> str:
    runs, verdicts = summary["التجارب"], summary["الشروط"]
    order = [tuple(x) for x in summary["الترتيب"]]
    ys = [y[0][:4] for y in years]
    g0, g1 = "التوليفة", "مرجع: جهة عشوائيّة"
    bal = DEFAULTS["balance"]
    dip = lambda low: "ربح مباشرة" if low >= 0 else "{:.1f}٪ ({:,.0f}$)".format(low, bal * low / 100.0)
    pct = lambda v: "—" if v is None else "%.0f من 100" % (100 * v)
    yes = lambda b: "نعم" if b else "لا"
    knowledge = bool(summary.get("للمعرفة"))
    L = ["# النتيجة — %s" % name, "",
         "المخاطرة %s٪ من رأس المال الأوّل في كلّ صفقة، والكلفة مخصومة. «على %s$» = النسبة مضروبةً في رأس المال." % (
             DEFAULTS["risk_pct"], "{:,.0f}".format(bal)), ""]
    if knowledge:
        L += ["**قياسٌ للمعرفة بأمر المالك، بلا حكم.** القانون 21 خطٌّ أحمر في الحيّ، ولا يتغيّر إلّا بنقاشه وختمه.", ""]
    else:
        L += ["## الحكم بمعيار النجاح المكتوب قبل النتيجة (الخطوة 10)", "", "> " + summary["المعيار"], "",
              "| التجربة | %s | نجح؟ |" % " | ".join("%s: فوق بلا رأس حربة · موجب · فوق العشوائيّ · وقف سريع أقلّ" % y for y in ys),
              "|---|" + "---|" * len(ys) + "---|"]
        for label, v in verdicts.items():
            cells = []
            for y in ys:
                c = v["السنوات"][y]
                cells.append("%s · %s · %s · %s (%s مقابل %s)" % (yes(c["فوق_بلا_رأس_حربة"]), yes(c["موجب"]), yes(c["فوق_العشوائيّ"]),
                             yes(c["وقف_سريع_أقلّ"]), pct(c["نسبة_الوقف_السريع"]), pct(c["نسبته_بلا_رأس_حربة"])))
            L.append("| %s | %s | %s |" % (label, " | ".join(cells), yes(v["نجح"])))
        L += ["", "**الجواب: %s.**" % summary["الحكم"], ""]
    L += ["## 1. كلّ سنة بشكل المالك", "",
          "| السنة | التجربة | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف | كم نزل قبل الربح | الصافي | العشوائيّ | سقوط الحساب | وقف في أوّل 5 دقائق |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for y in ys:
        for label, *_ in order:
            r = runs["%s|%s" % (y, label)]
            s, rs = r[g0]["الإحصاء"], r[g1]["الإحصاء"]
            L.append("| %s | %s | %d | %d | %d | %d | %d | %s | %+.1f٪ | %+.1f٪ | %d | %d |" % (
                y, label, s["صفقات"], s.get("بلغ_الهدف_1", 0), s.get("بلغ_الهدف_2", 0), s.get("بلغ_الهدف_3", 0),
                s["وقف_قبل_أيّ_هدف"], dip(s["أعمق_نزول_تحت_البداية_٪"]), s["صافي_٪"], rs["صافي_٪"],
                r[g0]["الحساب_الافتراضيّ"]["account_falls"], r[g0]["وقف_أوّل_5_دقائق"]))
    L += ["", "«وقف» = ضربت الوقف كاملًا قبل أيّ هدف. «العشوائيّ» = الجهة عشوائيّة والقوانين ورأس الحربة نفسها.", "",
          "## 2. كم صفقةً أخذت كلّ جلسة", "",
          "| السنة | التجربة | جلسات تداولت | بصفقة | بصفقتين | بثلاث فأكثر | أقصى في جلسة |", "|---|---|---|---|---|---|---|"]
    for y in ys:
        for label, *_ in order:
            j = runs["%s|%s" % (y, label)][g0]["الجلسات"]
            L.append("| %s | %s | %d | %d | %d | %d | %d |" % (y, label, j["جلسات"], j["بصفقة"], j["بصفقتين"], j["بثلاث_فأكثر"], j["أقصى"]))
    if any(tgt for _, _, tgt in order):
        L += ["", "## 2ب. الهدف عند المستوى التالي — كم صفقةً رُدّت بشرط «لا أقلّ من واحد إلى ثلاثة»", "",
              "| السنة | التجربة | صفقات | رُدّت لأنّ المستوى التالي أقرب من ثلاثة أضعاف بعد الكلفة | بلا مستوى أمامها (ثلاثة أضعاف) | متوسّط الهدف الأخير |",
              "|---|---|---|---|---|---|"]
        for y in ys:
            for label, _lv, tgt in order:
                if not tgt:
                    continue
                r = runs["%s|%s" % (y, label)][g0]
                L.append("| %s | %s | %d | %d | %d | %s |" % (y, label, r["الإحصاء"]["صفقات"], r["رُدّت_بشرط_الثلاثة"], r["بلا_مستوى_أمامها"],
                         "—" if r["متوسّط_الهدف_الأخير"] is None else "%.2f ضعف المخاطرة" % r["متوسّط_الهدف_الأخير"]))
    if knowledge:
        L += ["", "## 2ج. ما أُغلق عند نهاية نافذة نيويورك قبل الهدف الأخير (لا تبييت — القانونان 19 و20)", "",
              "| السنة | التجربة | صفقات | أُغلقت عند نهاية النافذة | منها قبل أيّ هدف | منها بعد هدفٍ أو اثنين | صافيها | على %s$ | متوسّطها | أُغلقت قبل خبرٍ أحمر |" % (
                  "{:,.0f}".format(bal)), "|---|---|---|---|---|---|---|---|---|---|"]
        for y in ys:
            for label, *_ in order:
                r = runs["%s|%s" % (y, label)][g0]
                w = r["عند_نهاية_النافذة"]
                L.append("| %s | %s | %d | %d | %d | %d | %+.1f٪ | %s | %s | %d |" % (
                    y, label, r["الإحصاء"]["صفقات"], w["صفقات"], w["قبل_أيّ_هدف"], w["بعد_هدفٍ_أو_اثنين"], w["صافيها_٪"],
                    "{:+,.0f}$".format(w["صافيها_٪"] * bal / 100.0),
                    "—" if w["متوسّطها_R"] is None else "%+.2f من المخاطرة" % w["متوسّطها_R"], w["قبل_الخبر"]))
        L += ["", "## 2د. الصفقات بساعة الدخول — بساعة المالك (تركيا)", "",
              "النافذة 16:30–23:00 بساعة المالك في الصيف الأمريكيّ، و17:30–24:00 في شتائه (تركيا لا تغيّر ساعتها)، والدخول بعد أوّل ربع ساعة.", ""]
        for y in ys:
            for label, *_ in order:
                hours = runs["%s|%s" % (y, label)][g0]["الساعات"]
                L += ["### %s — %s" % (y, label), "", "| ساعة الدخول | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف | الصافي |",
                      "|---|---|---|---|---|---|---|"]
                L += ["| %s | %d | %d | %d | %d | %d | %+.1f٪ |" % (h, v["صفقات"], v["هدف_1"], v["هدف_2"], v["هدف_3"], v["وقف"], v["صافي_٪"])
                      for h, v in hours.items()] or ["| — | لا صفقة | | | | | |"]
                L.append("")
    if any(lv for _, lv, _ in order):
        L += ["", "## 3. لكلّ نوع مستوى", "",
              "| السنة | التجربة | المستوى | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف | الصافي |", "|---|---|---|---|---|---|---|---|---|"]
        for y in ys:
            for label, *_ in order[1:]:
                for k, s in runs["%s|%s" % (y, label)][g0]["المستويات"].items():
                    L.append("| %s | %s | %s | %d | %d | %d | %d | %d | %+.1f٪ |" % (
                        y, label, k, s["صفقات"], s.get("بلغ_الهدف_1", 0), s.get("بلغ_الهدف_2", 0), s.get("بلغ_الهدف_3", 0),
                        s["وقف_قبل_أيّ_هدف"], s["صافي_٪"]))
    for y in ys:
        for label, _lv, tgt in order:
            if _lv and not tgt:                 # the fixed-3R spearhead: its months are in its own folder under «التجارب»
                continue
            r = runs["%s|%s" % (y, label)]
            months = r[g0]["الأشهر"]
            ref = {m["الشهر"]: m["عائد_٪"] for m in r[g1]["الأشهر"]}
            L += ["", "## 4. أشهر %s — %s" % (y, label), "",
                  "| الشهر | صفقات | هدف أوّل | هدف ثانٍ | هدف ثالث | وقف | كم نزل قبل الربح (من أوّل السنة) | الصافي | العشوائيّ |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for m in months:
                L.append("| %s | %d | %d | %d | %d | %d | %s | %+.1f٪ | %s |" % (
                    m["الشهر"], m["صفقات"], m.get("هدف_1", 0), m.get("هدف_2", 0), m.get("هدف_3", 0), m["وقف"],
                    dip(m.get("أدنى_حتّى_الآن_٪", 0.0)), m["عائد_٪"], ("%+.1f٪" % ref[m["الشهر"]]) if m["الشهر"] in ref else "—"))
            if not months:
                L.append("| — | لا صفقة | | | | | | | |")
    L += ["", "## 5. الحساب الافتراضيّ بحدود المالك (القوانين 7–10)", ""]
    for y in ys:
        for label, *_ in order:
            for g in (g0, g1):
                sim = runs["%s|%s" % (y, label)][g]["الحساب_الافتراضيّ"]
                L.append("- **%s · %s · %s:** صفقات %d · سقوط الحساب **%d** · أيّام وقفها الحدّ الشامل %d · وقفات حدّ الزوج %d ·"
                         " أسوأ خسارة يوم %.2f$ · أدنى حقوق %.2f$ · الصافي %.2f$" % (
                             y, label, "التوليفة" if g == g0 else "عشوائيّ", sim["taken"], sim["account_falls"],
                             sim["daily_stops"], sim["pair_stops"], sim["max_day_loss"], sim["lowest_equity"], sim["net"]))
    L += ["", "كلّ تجربةٍ بملفّاتها الستّة كاملةً في مجلّد «التجارب» بجانب هذا الملفّ. الزمن: %s." % summary["الزمن"]]
    return "\n".join(L) + "\n"


def direction_describe(cfg: dict[str, Any], log=print) -> Path:
    """Every reading (each frame, both years) against the moves the eye sees afterwards: how many candles of 100 the
    reading -- knowing only the past at that candle -- named the move it was in. The readings never see the labels."""
    began = time.time()
    sym = cfg.get("symbol", "USTEC")
    frames = [f for f in cfg["frames"] if f in DIRECTION_PERIOD_S]
    years = [tuple(y) for y in cfg["years"]]
    table: dict[tuple, list] = {}
    tries = 0
    for fr in frames:
        p = DIRECTION_PERIOD_S[fr]
        per: dict[tuple, list] = defaultdict(list)
        for y0, y1 in years:
            t0, t1 = _epoch(y0), _epoch(y1)
            arr = np.array(_bars_db(sym, fr, t0 - DIRECTION_WARM_BARS * p, t1 + DIRECTION_WARM_BARS * p), dtype=float)
            if len(arr) < DIRECTION_WARM_BARS:
                continue
            hi, lo, cl = arr[:, 2], arr[:, 3], arr[:, 4]
            inside = np.flatnonzero((arr[:, 0] >= t0) & (arr[:, 0] < t1))
            unit = float(np.median((hi - lo)[inside])) if len(inside) else 0.0
            truths = {size: zigzag_legs(hi, lo, k * unit) for size, k in DESCRIBE_SIZES.items()}
            readings = _fit_readings(hi, lo, cl, hold_combos=True)
            for size, truth in truths.items():
                ok = inside[truth[inside] != 0]
                live = {"الموجة الحيّة تصحّح نفسها عند %d٪ من حجم الموجة" % round(100 * f):
                        zigzag_live(hi, lo, f * DESCRIBE_SIZES[size] * unit) for f in DESCRIBE_LIVE}
                for name, state in {**readings, **live}.items():
                    sel = ok[state[ok] != 0]
                    if not len(sel):
                        continue
                    t, k_ = truth[sel], state[sel]
                    per[(size, name)].append({"year": y0[:4], "agree": 100.0 * float((t == k_).mean()),
                                              "share": 100.0 * len(sel) / max(1, len(ok)),
                                              "up": 100.0 * float((k_[t == 1] == 1).mean()) if (t == 1).any() else float("nan"),
                                              "down": 100.0 * float((k_[t == -1] == -1).mean()) if (t == -1).any() else float("nan"),
                                              "legs": int(np.count_nonzero(np.diff(truth[ok]) != 0)) + 1,
                                              "unit": unit * DESCRIBE_SIZES[size]})
        for (size, name), got in per.items():
            tries += 1
            if len(got) != len(years) or min(g["share"] for g in got) < DESCRIBE_MIN_SHARE:
                continue
            table.setdefault((fr, size), []).append({"name": name, "avg": float(np.mean([g["agree"] for g in got])),
                                                     "min": float(min(g["agree"] for g in got)), "years": got})
        log("معايرة الاتّجاه: %s انتهت" % FRAME_AR[fr])
    for key in table:
        table[key].sort(key=lambda r: r["avg"], reverse=True)
    folder = OUT_ROOT / date.today().isoformat() / safe("معايرة الاتّجاه على موجات الماضي — " + cfg.get("name", SYMBOL_AR.get(sym, sym)))
    folder.mkdir(parents=True, exist_ok=True)
    mine = "الشموع 3 متتالية"
    L = ["# معايرة الاتّجاه على موجات الماضي — %s" % SYMBOL_AR.get(sym, sym), "",
         "قول المالك: «أنت حين تنظر إلى الشارت ترى الحركة كاملة، من القاع الذي بدأت منه إلى القمّة التي انتهت إليها … هيك لازم"
         " يتعاير بالبداية».", "",
         "- **الحقيقة:** الشارت بعد انتهائه مقسومٌ موجات: صاعدة من قاعٍ إلى القمّة التي بدأ منها هبوطٌ بحجم الموجة، وهابطة"
         " عكسها. وكلّ شمعة تأخذ موجتها. حجم الموجة ثلاثة: صغيرة = %g · متوسّطة = %g · كبيرة = %g ضعف وسط مدى شمعة"
         " الفريم في السنة." % tuple(DESCRIBE_SIZES.values()),
         "- **القراءة:** تُحسب عند كلّ شمعة بما قبلها فقط، ولا ترى الموجات أبدًا.",
         "- **النتيجة:** كم من 100 شمعة قالت القراءة الموجة التي كانت فيها. والخطأ يقع في أوّل كلّ موجة، قبل أن تُعرف.",
         "- **الموجة الحيّة** (قول المالك: «إذا مو صحيحة لازم تصحّحه»): تتبع آخر قمّةٍ وآخر قاع بما عُرف حتّى الشمعة فقط، وتصحّح"
         " نفسها إلى الموجة الجديدة لحظة يرتدّ السعر عن آخر طرفٍ بـ%s من حجم الموجة." % " أو ".join(
             "%d٪" % round(100 * f) for f in DESCRIBE_LIVE),
         "- **عدد ما جُرّب:** %d (135 قراءة × 3 أحجام × الأطر). ولا تدخل قراءةٌ تسكت في أكثر من %d من 100 شمعة، فالمالك:"
         " صاعد أو هابط دائمًا. والدمج هنا يُبقي آخر اتّفاقٍ للثلاثة حين يختلفون." % (tries, 100 - DESCRIBE_MIN_SHARE), ""]
    L += ["## الخلاصة — الأعلى لكلّ فريم وحجم (وسط السنتين · أسوأ سنة) ومعه المعتمد اليوم (الشموع 3)", "",
          "| الفريم | الحجم | حجم الموجة بالنقاط | موجات في السنة | الأعلى | تطابق | أسوأ سنة | الشموع 3 |", "|---|---|---|---|---|---|---|---|"]
    for fr in frames:
        for size in DESCRIBE_SIZES:
            rows = table.get((fr, size)) or []
            if not rows:
                continue
            b = rows[0]
            m = next((r for r in rows if r["name"] == mine), None)
            L.append("| %s | %s | %.0f | %d | %s | %.1f | %.1f | %s |" % (
                FRAME_AR[fr], size, float(np.mean([g["unit"] for g in b["years"]])),
                int(np.mean([g["legs"] for g in b["years"]])), b["name"], b["avg"], b["min"],
                "%.1f" % m["avg"] if m else "—"))
    for fr in frames:
        for size in DESCRIBE_SIZES:
            rows = table.get((fr, size)) or []
            if not rows:
                continue
            L += ["", "## %s — موجة %s — أعلى %d" % (FRAME_AR[fr], size, FIT_TOP), "",
                  "| # | القراءة | تطابق (وسط) | أسوأ سنة | حين الموجة صاعدة قالت صاعد | حين هابطة قالت هابط |", "|---|---|---|---|---|---|"]
            for i, r in enumerate(rows[:FIT_TOP], 1):
                up = float(np.nanmean([g["up"] for g in r["years"]]))
                down = float(np.nanmean([g["down"] for g in r["years"]]))
                L.append("| %d | %s | %.1f | %.1f | %.1f | %.1f |" % (i, r["name"], r["avg"], r["min"], up, down))
    (folder / "النتيجة.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (folder / "الاختبار.md").write_text(
        "# معايرة الاتّجاه على موجات الماضي — %s\n\n- الرمز: %s\n- السنتان: %s\n- الأطر: %s\n- أحجام الموجة: %s\n- عدد ما جُرّب: %d\n"
        "- الزمن: %s\n" % (cfg.get("name", ""), SYMBOL_AR.get(sym, sym), " · ".join("%s إلى %s" % y for y in years),
                           " · ".join(FRAME_AR[f] for f in frames), " · ".join("%s %g" % kv for kv in DESCRIBE_SIZES.items()),
                           tries, _span(time.time() - began)), encoding="utf-8")
    (folder / "summary.json").write_text(json.dumps(
        {"kind": "direction", "الاسم": cfg.get("name", ""), "عدد_المجرّب": tries,
         "الأعلى": {"%s %s" % (FRAME_AR[f], s): {k: v for k, v in rows[0].items() if k != "years"}
                    for (f, s), rows in table.items() if rows}}, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


# ── the owner's own method (2026-10-19, in his words): «لمس منطقة دعم على فريم أكبر وثبت عندها شوي، تذبذب، ثمّ اندفع بعكس الاتّجاه
#    بقوّة شراء» · «مناطق كلّ الفريمات بحترم: شهري أسبوعي 4 ساعات ساعة وأنا نازل للدقيقة» · «مو مهمّ كم يثبت، مهمّ يكسر الثبات» ·
#    «بحدّد بالنظر: شموع خضراء متتالية متسارعة» · «قاع وقمّة … بخد منطقة كاملة». Translated into rules to be checked by his eye. ──
OWNER_FRAMES = {"MN1": (1, 120, "شهريّ"), "W1": (2, 156, "أسبوعيّ"), "H4": (3, 600, "أربع ساعات"), "H1": (3, 1000, "ساعة")}
#: 2026-10-19 (the owner): «الشهري والأسبوعي واليومي نظرة بس … أربع ساعات وساعة وربع ساعة هنّ الثقيل، و5 دقائق حاسمة، والدقيقة مكان
#: تحسين دخولي» -- the belts come from the heavy frames; the range and its break are read on five minutes; the entry on one.
OWNER_HEAVY = {"H4": (3, 600, "أربع ساعات"), "H1": (3, 1000, "ساعة"), "M15": (3, 1500, "ربع ساعة")}
_PERIOD_S = {"MN1": 31 * 86400, "W1": 7 * 86400, "D1": 86400, "H4": 14400, "H1": 3600, "M15": 900, "M5": 300, "M1": 60}


def _bars_db(symbol: str, period: str, t0: float, t1: float) -> list[tuple]:
    con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    rows = con.execute("select period_start, open, high, low, close from candles_history where symbol=? and period=? and "
                       "period_start>=? and period_start<? order by period_start", (symbol, period, t0, t1)).fetchall()
    con.close()
    return rows


def owner_zones(symbol: str, at: float, frames: dict | None = None, mode: str = "candle", last: int = 2) -> list[dict[str, Any]]:
    """mode "candle" (the owner, 2026-10-19: «نطاق الشمعة اللي عملت آخر قاعدة»): on each big frame, the last `last` swing lows
    and highs, and the belt is the whole range of the candle that made each one. mode "cluster": the earlier translation."""
    if mode == "candle":
        out = []
        for period, (span, look, name) in (frames or OWNER_FRAMES).items():
            sec = _PERIOD_S[period]
            rows = [r for r in _bars_db(symbol, period, at - (look + 5) * sec, at) if r[0] + sec <= at][-look:]
            for kind, col, sign in (("low", 3, 1), ("high", 2, -1)):
                piv = [i for i in range(span, len(rows) - span)
                       if all(sign * (rows[i][col] - rows[j][col]) < 0 for j in range(i - span, i + span + 1) if j != i)]
                # «آخر قاعدة» = the last base the price has not closed beyond since it formed (2026-10-19: the September box
                # was the base the rally left from, still unbroken when the price came back) -- the nearest ones to the price.
                piv = [i for i in piv if all(sign * (rows[j][4] - rows[i][col]) >= 0 for j in range(i + 1, len(rows)))]
                now = rows[-1][4] if rows else 0.0
                piv = sorted(piv, key=lambda i: abs(now - rows[i][col]))[:max(last, 3)]
                for i in piv:
                    out.append({"frame": period, "name": name, "kind": kind, "lo": rows[i][3], "hi": rows[i][2], "touches": 1,
                                "at": rows[i][0]})
        return out
    return _owner_zones_cluster(symbol, at, frames)


def _owner_zones_cluster(symbol: str, at: float, frames: dict | None = None) -> list[dict[str, Any]]:
    """The belts: swing lows (and highs) of each big frame, closed before `at`, gathered into one belt when they sit within half
    of that frame's usual bar range (ATR 14), and never thinner than a third of it -- «منطقة كاملة» not a line."""
    out = []
    for period, (span, look, name) in (frames or OWNER_FRAMES).items():
        sec = {"MN1": 31 * 86400, "W1": 7 * 86400, "H4": 14400, "H1": 3600}[period]
        rows = [r for r in _bars_db(symbol, period, at - (look + 5) * sec, at) if r[0] + sec <= at][-look:]
        if len(rows) < 2 * span + 15:
            continue
        tr = [max(r[2], p[4]) - min(r[3], p[4]) for p, r in zip(rows, rows[1:])]
        atr = float(np.mean(tr[-14:]))
        for kind, col, sign in (("low", 3, 1), ("high", 2, -1)):
            piv = [rows[i][col] for i in range(span, len(rows) - span)
                   if all(sign * (rows[i][col] - rows[j][col]) < 0 for j in range(i - span, i + span + 1) if j != i)]
            piv.sort()
            group: list[float] = []
            for v in piv + [None]:
                if v is not None and (not group or (v - group[-1] <= 0.5 * atr and v - group[0] <= atr)):
                    group.append(v)
                    continue
                if group:
                    lo, hi = min(group), max(group)
                    if hi - lo < atr / 3:
                        lo, hi = (lo, lo + atr / 3) if kind == "low" else (hi - atr / 3, hi)
                    out.append({"frame": period, "name": name, "kind": kind, "lo": lo, "hi": hi, "touches": len(group)})
                group = [v] if v is not None else []
    return out


def owner_scan(symbol: str, t0: float, t1: float, n_accel: int = 2, min_bars: int = 3, min_r: float = 3.0,
               zone_every_s: float = 900.0, trace: list | None = None, zone_frames: dict | None = None,
               entry_wait_min: int = 15) -> list[dict[str, Any]]:
    """The owner's frames: belts (the range of the candle of the last lows and highs) from four hours, one hour and the quarter
    hour; at a belt the five-minute range builds, however long; a strong five-minute close outside it is the decision; then on
    the minute, within entry_wait_min, n_accel candles in that direction each closing beyond the one before with a body above
    the range's average minute body -- the entry at that minute's close. Leaving the belt without a decision ends the watch
    (that belt is not watched again until the price has left it). Stop behind the five-minute range; target the nearest belt in
    the way at min_r or more (else min_r)."""
    frames = zone_frames or OWNER_HEAVY
    m5 = _bars_db(symbol, "M5", t0, t1)
    m1 = _bars_db(symbol, "M1", t0, t1 + 3600)
    m1_t = np.array([r[0] for r in m1])
    zones, z_at, sigs, state, prev_c, spent = [], -1.0, [], None, None, set()
    key = lambda z: (z["frame"], round(z["lo"], 1), round(z["hi"], 1))
    for ps, o, h, l, c in m5:
        end = ps + 300
        if end - z_at >= zone_every_s or not zones:
            zones, z_at = owner_zones(symbol, end, frames=frames), end
        spent = {k for k in spent if any(key(z) == k and l <= z["hi"] + (z["hi"] - z["lo"]) and h >= z["lo"] - (z["hi"] - z["lo"])
                                         for z in zones)}
        if state is None:
            hit = [z for z in zones if l <= z["hi"] and h >= z["lo"] and key(z) not in spent and prev_c is not None
                   and (prev_c > z["hi"] or prev_c < z["lo"])]
            prev_c = c
            if hit:
                z = max(hit, key=lambda z: list(frames).index(z["frame"]) * -1)
                state = {"zone": z, "start": ps, "hi": h, "lo": l, "bodies": [abs(c - o)], "n": 1}
                if trace is not None:
                    trace.append((end, "لمس", z["name"], z["kind"], round(z["lo"]), round(z["hi"])))
            continue
        prev_c = c
        st, z = state, state["zone"]
        w = max(z["hi"] - z["lo"], st["hi"] - st["lo"])
        avg5 = float(np.mean(st["bodies"])) or 1e-9
        d = 1 if c > st["hi"] else -1 if c < st["lo"] else 0
        if not (st["n"] >= min_bars and d and (c - o) * d > 0 and abs(c - o) > avg5):
            if c > z["hi"] + w or c < z["lo"] - w:
                if trace is not None:
                    trace.append((end, "ابتعد بلا قرار", st["n"], round(st["hi"]), round(st["lo"])))
                spent.add(key(z))
                state = None
            else:
                st["hi"], st["lo"] = max(st["hi"], h), min(st["lo"], l)
                st["bodies"].append(abs(c - o))
                st["n"] += 1
            continue
        # the five-minute decision; now the minute
        i0 = int(np.searchsorted(m1_t, st["start"], side="left"))
        i1 = int(np.searchsorted(m1_t, end, side="left"))
        avg1 = float(np.mean([abs(r[4] - r[1]) for r in m1[i0:i1]])) if i1 > i0 else avg5 / 5
        seq, found = [], None
        for r in m1[i1:i1 + entry_wait_min]:
            ok = (r[4] - r[1]) * d > 0 and abs(r[4] - r[1]) > avg1 and (not seq or (r[4] - seq[-1][4]) * d > 0)
            seq = seq + [r] if ok else ([r] if (r[4] - r[1]) * d > 0 and abs(r[4] - r[1]) > avg1 else [])
            if len(seq) >= n_accel:
                found = r
                break
        if found is None:
            if trace is not None:
                trace.append((end, "قرار الخمس دقائق بلا تسارع على الدقيقة", d))
            spent.add(key(z))
            state = None
            continue
        entry = found[4]
        stop = st["lo"] - 1.0 if d > 0 else st["hi"] + 1.0
        risk = abs(entry - stop)
        if risk <= 0:
            state = None
            continue
        ahead = sorted((zz["lo"] - entry if d > 0 else entry - zz["hi"]) for zz in zones
                       if (zz["lo"] > entry if d > 0 else zz["hi"] < entry))
        far = [x for x in ahead if x >= min_r * risk]
        target = entry + d * (far[0] if far else min_r * risk)
        sigs.append({"at": found[0] + 60, "side": d, "entry": entry, "stop": stop, "target": target, "risk": risk, "zone": z,
                     "range": (st["start"], st["hi"], st["lo"]), "decision_at": end,
                     "target_from": "حزام" if far else "%g أضعاف" % min_r})
        spent.add(key(z))
        state = None
    return sigs

def _owner_context(symbol: str, t0: float, t1: float, tz: float) -> list[str]:
    """The big frames as the owner reads them -- information only: is the day rising or falling, is the week and the month
    green or red so far (their candle from its open to the day's start)."""
    out = []
    d1 = _bars_db(symbol, "D1", t0 - 40 * 86400, t1)
    w1 = _bars_db(symbol, "W1", t0 - 60 * 86400, t1)
    mn = _bars_db(symbol, "MN1", t0 - 70 * 86400, t1)
    for i, r in enumerate(d1):
        if r[0] < t0 - 86400 or r[0] >= t1:
            continue
        prev = d1[i - 1] if i else r
        wk = [w for w in w1 if w[0] <= r[0]][-1:] or [None]
        mo = [m for m in mn if m[0] <= r[0]][-1:] or [None]
        col = lambda o, c: "أخضر" if c >= o else "أحمر"
        out.append("%s — اليوميّ %s (إغلاقه %s، والسابق %s) · الأسبوع %s · الشهر %s" % (
            datetime.fromtimestamp(r[0] + tz + 6 * 3600, timezone.utc).strftime("%d/%m"), "صاعد" if r[4] >= prev[4] else "هابط",
            "{:,.0f}".format(r[4]), "{:,.0f}".format(prev[4]),
            col(wk[0][1], r[4]) if wk[0] else "—", col(mo[0][1], r[4]) if mo[0] else "—"))
    return out


def owner_draw(cfg: dict[str, Any]) -> Path:
    """A picture for the owner's eye: the belts, the ranges at them, the breaks and the entries with stop and target, over a
    few days of five-minute candles, a one-minute close-up around each entry, and his own trade beside them to compare."""
    sym = cfg.get("symbol", "USTEC")
    t0, t1 = _epoch(cfg["from"]), _epoch(cfg["to"])
    tz = float(cfg.get("tz_hours", 3)) * 3600
    sigs = owner_scan(sym, t0, t1, n_accel=int(cfg.get("n_accel", 2)))
    zones = owner_zones(sym, float(cfg.get("zones_at") or t1), frames=OWNER_HEAVY)
    colors = {"MN1": "#b06cff", "W1": "#4c8dff", "H4": "#ff9f43", "H1": "#2ecc71", "M15": "#4dd0e1"}
    fmt = lambda x: datetime.fromtimestamp(x + tz, timezone.utc).strftime("%d/%m %H:%M")

    def panel(bars, width, height, marks, title, zoom=False):
        n = len(bars)
        lo = min(min(b[3] for b in bars), *(m["stop"] for m in marks)) if marks else min(b[3] for b in bars)
        hi = max(max(b[2] for b in bars), *(m["target"] for m in marks)) if marks else max(b[2] for b in bars)
        pad = (hi - lo) * 0.05
        lo, hi = lo - pad, hi + pad
        L, R, T, B = 70, 260, 40, 40
        X = lambda i: L + (i + 0.5) * (width - L - R) / max(1, n)
        Y = lambda v: T + (hi - v) * (height - T - B) / (hi - lo)
        idx = lambda ts: int(np.searchsorted([b[0] for b in bars], ts, side="right")) - 1
        cw = max(1.0, (width - L - R) / max(1, n) * 0.7)
        s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" style="background:#0d0f14">' % (width, height),
             '<text x="%d" y="24" fill="#e8e8e8" font-size="16" text-anchor="end" direction="rtl">%s</text>' % (width - 10, title)]
        for z in zones:
            if z["hi"] < lo or z["lo"] > hi:
                continue
            y1, y2 = Y(min(z["hi"], hi)), Y(max(z["lo"], lo))
            s.append('<rect x="%d" y="%.1f" width="%d" height="%.1f" fill="%s" fill-opacity="0.13" stroke="%s" stroke-opacity="0.5"/>'
                     % (L, y1, width - L - R, max(1.0, y2 - y1), colors[z["frame"]], colors[z["frame"]]))
            s.append('<text x="%d" y="%.1f" fill="%s" font-size="11" direction="rtl">حزام %s · شمعة %s</text>' % (
                width - R + 6, (y1 + y2) / 2 + 4, colors[z["frame"]], z["name"], "آخر قاع" if z["kind"] == "low" else "آخر قمّة"))
        step = max(1, n // 12)
        for i in range(0, n, step):
            s.append('<text x="%.1f" y="%d" fill="#888" font-size="10" text-anchor="middle">%s</text>' % (X(i), height - 12, fmt(bars[i][0])))
        for k in range(6):
            v = lo + (hi - lo) * k / 5
            s.append('<text x="%d" y="%.1f" fill="#888" font-size="10" text-anchor="end">%s</text>' % (L - 6, Y(v) + 3, "{:,.0f}".format(v)))
        for i, (ps, o, h, l, c) in enumerate(bars):
            col = "#26a69a" if c >= o else "#ef5350"
            s.append('<line x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f" stroke="%s"/>' % (X(i), X(i), Y(h), Y(l), col))
            s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (
                X(i) - cw / 2, Y(max(o, c)), cw, max(0.8, abs(Y(o) - Y(c))), col))
        for m in marks:
            i = idx(m["at"] - 1)
            if i < 0:
                continue
            j = min(n - 1, i + max(6, n // 10))
            if m.get("range"):
                a = max(0, idx(m["range"][0]))
                s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#ffffff" fill-opacity="0.07" stroke="#bbbbbb" '
                         'stroke-dasharray="4 3"/>' % (X(a) - cw, Y(m["range"][1]), X(i) - X(a) + cw, Y(m["range"][2]) - Y(m["range"][1])))
            for v, col, name in ((m["target"], "#2ecc71", "هدف"), (m["entry"], m.get("color", "#ffffff"), "دخول"), (m["stop"], "#ef5350", "وقف")):
                s.append('<line x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f" stroke="%s" stroke-width="1.6"%s/>' % (
                    X(i), X(j), Y(v), Y(v), col, ' stroke-dasharray="6 3"' if m.get("dashed") else ""))
                s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="11" direction="rtl">%s %s</text>' % (
                    X(j) + 4, Y(v) + 4, col, name, "{:,.1f}".format(v)))
            arrow = "▲" if m["side"] > 0 else "▼"
            s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="16" text-anchor="middle">%s</text>' % (
                X(i), Y(m["entry"]) + (22 if m["side"] > 0 else -12), m.get("color", "#ffd54f"), arrow))
            s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="11" text-anchor="middle" direction="rtl">%s</text>' % (
                X(i), Y(m["stop"]) + (16 if m["side"] > 0 else -8), m.get("color", "#ffd54f"), m["label"]))
        s.append("</svg>")
        return "\n".join(s)

    m5 = _bars_db(sym, "M5", t0, t1)
    marks = [dict(x, label=("شراء" if x["side"] > 0 else "بيع") + " " + fmt(x["at"])) for x in sigs]
    own = [dict(o, label="صفقتك", color="#ffd54f", dashed=True) for o in cfg.get("owner_trades", [])]
    html = ['<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>طريقة المالك على الشارت</title>',
            '<style>body{background:#0d0f14;color:#e8e8e8;font-family:Tahoma,Arial,sans-serif;margin:16px}h1{font-size:20px}'
            'p,li{font-size:14px;line-height:1.7}.k{display:inline-block;width:14px;height:10px;margin-left:6px}</style></head><body>',
            "<h1>طريقة المالك مرسومةً على الناسداك — %s إلى %s</h1>" % (fmt(t0), fmt(t1)),
            "<p>الأحزمة: مدى شمعة آخر قاعين وآخر قمّتين على الفريمات الثقيلة، كلّ لونٍ فريم: "
            + " ".join('<span class="k" style="background:%s"></span>%s' % (colors[k], v[2]) for k, v in OWNER_HEAVY.items())
            + ". المربّع المنقّط: التذبذب على الخمس دقائق عند الحزام. السهم: الدخول على الدقيقة بعد قرار الخمس دقائق و%s شموع دقيقة"
            " متسارعة. الأبيض دخول، الأحمر وقف، الأخضر هدف. والأصفر المنقّط صفقتك للمقارنة.</p>" % cfg.get("n_accel", 2)
            + "".join("<p>%s</p>" % line for line in _owner_context(sym, t0, t1, tz)),
            "<p>عدد الإشارات: %d</p><ul>" % len(sigs)]
    for x in sigs:
        html.append("<li>%s · %s · دخول %s · وقف %s (%.0f نقطة) · هدف %s (%s) · %s %s %s–%s · التذبذب من %s</li>" % (
            fmt(x["at"]), "شراء" if x["side"] > 0 else "بيع", "{:,.1f}".format(x["entry"]), "{:,.1f}".format(x["stop"]), x["risk"],
            "{:,.1f}".format(x["target"]), x["target_from"], "حزام", x["zone"]["name"], "{:,.0f}".format(x["zone"]["lo"]),
            "{:,.0f}".format(x["zone"]["hi"]), fmt(x["range"][0])))
    html.append("</ul>")
    html.append(panel(m5, 1700, 760, marks + own, "خمس دقائق — الأيّام كلّها"))
    for x in sigs + [dict(o, range=None) for o in cfg.get("owner_trades", [])]:
        a = x["at"] - 150 * 60
        m1 = _bars_db(sym, "M1", a, x["at"] + 120 * 60)
        mk = [dict(x, label="صفقتك" if x.get("dashed") or x.get("color") else ("شراء" if x["side"] > 0 else "بيع"),
                   color=x.get("color", "#ffd54f"), dashed=x.get("dashed", False))]
        html.append(panel(m1, 1700, 520, mk, "دقيقة — حول %s" % fmt(x["at"]), zoom=True))
    html.append("</body></html>")
    folder = OUT_ROOT / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / safe("طريقة المالك على الشارت — %s إلى %s.html" % (cfg["from"], cfg["to"]))
    out.write_text("\n".join(html), encoding="utf-8")
    return out


# ── the owner's minute boxes (2026-10-19: «قيس … الأرقام بدها قياس … أنا باخد عدّة قرارات بأجزاء من ثانية») ──────────────
#    his words: in a trend every short pause on the minute is a small box; «لحظة كسر» it is traded with the trend; at the end of
#    a fall «ما نزل تحت قاع عمله» -- no lower low -- the next box is accumulation and its break up is a buy. The numbers are
#    ours to try: the box (minutes, tightness against the minute's usual range), the structure (minute swings).
def box_signals(symbol: str, t0: float, t1: float, n_box: int = 5, k_width: float = 2.0, span: int = 3,
                min_stop: float = 0.0) -> list[dict[str, Any]]:
    from shared import red_lines
    from shared.pips import from_pips
    rows = _bars_db(symbol, "M1", t0 - 86400, t1)
    if not rows:
        return []
    ts = np.array([r[0] for r in rows])
    o, h, l, c = (np.array([r[k] for r in rows]) for k in (1, 2, 3, 4))
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h, prev) - np.minimum(l, prev)
    atr = np.convolve(tr, np.ones(30) / 30.0, mode="full")[:len(tr)]
    lows, highs = [], []                                           # confirmed minute swings: (time, price)
    sigs, used_until, min_stop_px = [], -1, from_pips(min_stop, symbol) if min_stop else 0.0
    for i in range(max(n_box, 2 * span + 1, 31), len(rows)):
        j = i - span                                               # a swing is known span minutes after it
        if all(l[j] < l[k] for k in range(j - span, j + span + 1) if k != j):
            lows.append(l[j])
        if all(h[j] > h[k] for k in range(j - span, j + span + 1) if k != j):
            highs.append(h[j])
        if ts[i] < t0 or i <= used_until:
            continue
        a = i - n_box                                              # the box: the n_box minutes before this one
        bh, bl = float(h[a:i].max()), float(l[a:i].min())
        if bh - bl > k_width * float(atr[i - 1]) or atr[i - 1] <= 0:
            continue
        d = 1 if c[i] > bh else -1 if c[i] < bl else 0
        if not d:
            continue
        if d > 0 and not (len(lows) >= 2 and lows[-1] > lows[-2]):
            continue                                               # a buy needs «ما نزل تحت قاع عمله» -- a higher low
        if d < 0 and not (len(highs) >= 2 and highs[-1] < highs[-2]):
            continue
        end = ts[i] + 60
        inside, opened = red_lines.session_state(end, symbol)
        if not inside or (opened is not None and end - opened < red_lines.FIRST_SECONDS):
            continue
        entry = float(c[i])
        stop = bl - from_pips(1.0, symbol) if d > 0 else bh + from_pips(1.0, symbol)
        if abs(entry - stop) < min_stop_px:
            continue
        sigs.append({"at": end, "side": d, "entry": entry, "stop": stop, "box": (float(ts[a]), bh, bl)})
        used_until = i + n_box                                     # a new box must form after this one
    return sigs


def box_backtest(cfg: dict[str, Any], log=print) -> list[Path]:
    """Each variant x year: the signals traded one at a time with the owner's thirds (1R, 2R, 3R; stop to entry after the first,
    to 1R after the second), closed at the asset's red line, no entry around the red dollar news, a cost in points; the random
    side beside it on the same moments and distances. One test folder per variant and year, in the owner's format."""
    from shared import red_lines
    from shared.pips import from_pips, to_pips
    sym = cfg.get("symbol", "USTEC")
    outs = []
    for var in cfg["variants"]:
        for y0, y1 in [tuple(y) for y in cfg["years"]]:
            began = time.time()
            spec = merged({"symbol": sym, "from": y0, "to": y1, "name": "%s — %s — %s" % (cfg["name"], var["label"], y0[:4]),
                           "cost_pips": cfg.get("cost_pips", 1.5), "scale_with_price": False, "time_enough": False,
                           "direction": {"source": "random"}, "owner_method": var["label"]})
            t0, t1 = _epoch(y0), _epoch(y1)
            sigs = box_signals(sym, t0, t1, int(var.get("n_box", 5)), float(var.get("k_width", 2.0)), int(var.get("span", 3)),
                               float(var.get("min_stop", 0.0)))
            mins = load_minutes(sym, t0 - 86400, t1 + 3 * 86400)
            news = news_times(spec["news"], t0, t1)
            nb, na = float(spec["news"]["before_min"]) * 60, float(spec["news"]["after_min"]) * 60
            targets = [(1.0, 1 / 3), (2.0, 1 / 3), (3.0, 1 / 3)]
            trades = {"التوليفة": [], "مرجع: جهة عشوائيّة": []}
            skipped = {k: defaultdict(int) for k in trades}
            for lb in trades:
                rnd, busy = random.Random(SEED + 1), -1.0
                for s_ in sigs:
                    m = s_["at"]
                    if m < busy:
                        skipped[lb]["busy_or_waiting"] += 1
                        continue
                    k = np.searchsorted(news, m)
                    if [x for x in news[max(0, k - 1):k + 1] if -nb <= m - x <= na]:
                        skipped[lb]["news_window"] += 1
                        continue
                    risk = abs(s_["entry"] - s_["stop"])
                    side = s_["side"] if lb == "التوليفة" else rnd.choice((1, -1))
                    stop = s_["entry"] - side * risk
                    left = red_lines.seconds_to_red_line(m, sym, None)
                    nxt = news[k] if k < len(news) else float("inf")
                    end = m + min(float(left) if left and left > 0 else 86400.0, nxt - nb - m)
                    tr_ = Trade(lb, side, m, s_["entry"], stop, targets, 1, 2, 1.0, from_pips(float(spec["cost_pips"]), sym))
                    j = int(np.searchsorted(mins["t"], m, side="right"))
                    closed = False
                    while j < len(mins["t"]):
                        tt = mins["t"][j]
                        if tt > end:
                            tr_.close(tt, float(mins["c"][j - 1]), "session_end" if end - m < nxt - nb - m + 1 else "news")
                            closed = True
                            break
                        if tr_.minute(tt, mins["h"][j], mins["l"][j]):
                            closed = True
                            break
                        j += 1
                    if not closed:
                        tr_.close(float(mins["t"][-1]), float(mins["c"][-1]), "end_of_data")
                    trades[lb].append(_record(tr_, spec, to_pips))
                    busy = tr_.exit_at
            result = {"spec": spec, "moments": len(sigs), "candidates": len(sigs), "filtered": {}, "trades": trades,
                      "skipped": {k: dict(v) for k, v in skipped.items()}, "seconds": round(time.time() - began, 1),
                      "store": "شموع الدقيقة من قاعدة التاريخ (بلا مخزن حقائق)"}
            outs.append(write(result, {}))
            log("المربّعات: %s %s · إشارات %d · صفقات %d" % (var["label"], y0[:4], len(sigs), len(trades["التوليفة"])))
    return outs


# ── the owner's sideways range (owner, 2026-10-20, on two minute charts: «نطاق عرضيّ لمّا السعر يتذبذب بين قمّة وقاع
#    متساويين تقريبًا مع رينج سعريّ عم يتكرّر؛ أيّ كسر ما عم يثبت عليه بكون كسر كاذب» … «قيس») ──
RANGE_WINDOWS = (240, 210, 180, 150, 120, 105, 90, 75, 60, 50, 45, 40, 35, 30, 25, 20)
TR_CLOCK = 3 * 3600.0                                               # the owner's clock: Turkey, +3 all year


def _range_session(t: float) -> str:
    from zoneinfo import ZoneInfo
    ny = datetime.fromtimestamp(t, ZoneInfo("America/New_York"))
    ld = datetime.fromtimestamp(t, ZoneInfo("Europe/London"))
    m_ny, m_ld = ny.hour * 60 + ny.minute, ld.hour * 60 + ld.minute
    if 570 <= m_ny < 960:
        return "نيويورك"
    if m_ld >= 480 and m_ny < 570:
        return "لندن قبل نيويورك"
    return "آسيا والليل"


def _line50(symbol: str, ts: np.ndarray, c: np.ndarray, frame: str) -> tuple[np.ndarray, np.ndarray]:
    """The owner's 50 line of one frame at each minute (its last closed candle), and how far the price stands from it against
    the thirty days before that day (0-100: 97 = farther than 97 of every 100 minutes of that month). ts must start a month
    before the first minute that needs the second number."""
    sec = FRAME_S[frame]
    rows = _bars_db(symbol, PERIOD_OF[frame], float(ts[0]) - EMA_WARM_BARS * 3 * sec - 30 * 86400, float(ts[-1]) + 60)
    cl = np.array([r[4] for r in rows], dtype=np.float64)
    ends = np.array([r[0] + sec for r in rows], dtype=np.float64)
    a, acc, e = 2.0 / 51.0, 0.0, np.full(len(cl), np.nan)
    for k, x in enumerate(cl):
        acc = x if k == 0 else a * x + (1 - a) * acc
        if k + 1 >= EMA_WARM_BARS:
            e[k] = acc
    idx = np.searchsorted(ends, ts + 60, side="right") - 1
    line = np.where(idx >= 0, e[np.maximum(idx, 0)], np.nan)
    dist = np.abs(c - line)
    pct = np.full(len(ts), np.nan)
    first_day = math.floor((float(ts[0]) + TR_CLOCK) / 86400) + 30
    for dd in range(first_day, math.floor((float(ts[-1]) + TR_CLOCK) / 86400) + 1):
        t_day = dd * 86400.0 - TR_CLOCK
        i_a, i_b, i_c = np.searchsorted(ts, [t_day - 30 * 86400, t_day, t_day + 86400])
        ref = dist[i_a:i_b]
        ref = np.sort(ref[np.isfinite(ref)])
        if len(ref) >= 1000 and i_c > i_b:
            pct[i_b:i_c] = 100.0 * np.searchsorted(ref, dist[i_b:i_c]) / len(ref)
    return line, pct


def line_far_moments(symbol: str, t0: float, t1: float, frames: list[str]) -> dict[str, list[tuple]]:
    """The owner (21/10): «عرضيّ بكون بعيد عن خطّ كثير، لهيك بيجمّع، لا يرجع على خطّ أو يجيب خطّ لعنده». At every five-minute
    close, how far the price is from each frame's 50 line, then over the next hour: did it keep going away from the line,
    did a candle touch the line, how wide was the hour against the hour before, and how much of the gap closed by the price
    coming back and how much by the line coming up (or down) to it."""
    rows = _bars_db(symbol, "M1", t0 - 31 * 86400, t1 + 2 * 3600)
    ts = np.array([r[0] for r in rows], dtype=np.float64)
    h, l, c = (np.array([r[k] for r in rows], dtype=np.float64) for k in (2, 3, 4))
    picks = np.flatnonzero((ts >= t0) & (ts < t1) & ((ts + 60) % 300 == 0))
    out = {}
    for fr in frames:
        line, pct = _line50(symbol, ts, c, fr)
        with np.errstate(invalid="ignore"):
            cs = np.concatenate([[0], np.cumsum((l <= line) & (line <= h))])
        got = []
        for j in picks:
            j60, jp = j + 60, j - 59
            if j60 >= len(ts) or jp < 0 or ts[j60] - ts[j] != 3600 or ts[j] - ts[jp] != 3540:
                continue                                            # an hour without a gap on each side
            if not (np.isfinite(line[j]) and np.isfinite(pct[j]) and np.isfinite(line[j60])) or c[j] == line[j]:
                continue
            side = 1 if c[j] > line[j] else -1
            mv = float(c[j60] - c[j])
            got.append((float(pct[j]), side, mv, bool(cs[j60 + 1] - cs[j + 1] > 0),
                        float(h[j + 1:j60 + 1].max() - l[j + 1:j60 + 1].min()), float(h[jp:j + 1].max() - l[jp:j + 1].min()),
                        -mv * side, float(line[j60] - line[j]) * side))
        out[fr] = got
    return out


def range_scan(symbol: str, t0: float, t1: float, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """The range as he drew it, on the minute: a window's top and bottom, the price visiting the top band and the bottom band
    in turn (each band a quarter of the range's own height: «متساويين تقريبًا» is measured on the range itself -- 24 points
    on his quiet morning, 88 in New York); known at the minute the fourth visit lands. Each break (a close beyond an edge by a
    tenth of the height) is then followed until it runs one full height beyond the edge (held) or reaches the opposite edge
    (false). A false break leaves the range alive; a held one ends it."""
    zone, need = float(cfg.get("zone", 0.25)), int(cfg.get("visits", 4))
    min_h, buf = float(cfg.get("min_height_bars", 3.0)), float(cfg.get("break_buffer", 0.1))
    min_age, life = float(cfg.get("min_minutes", 10)) * 60, float(cfg.get("max_life_min", 240)) * 60
    frames = list(cfg.get("line_frames") or [])
    rows = _bars_db(symbol, "M1", t0 - (31 * 86400 if frames else 6 * 3600), t1 + 86400)
    if not rows:
        return []
    ts = np.array([r[0] for r in rows], dtype=np.float64)
    o, h, l, c = (np.array([r[k] for r in rows], dtype=np.float64) for k in (1, 2, 3, 4))
    n_all = len(ts)
    cum = np.concatenate([[0.0], np.cumsum(h - l)])
    fresh = np.concatenate([[True], np.diff(ts) > 300])               # a gap over five minutes starts a new run
    seg = np.maximum.accumulate(np.where(fresh, np.arange(n_all), 0))
    lines = {fr: _line50(symbol, ts, c, fr) for fr in frames}        # ٢١/١٠: the 50 line beside every range

    def found(i: int) -> dict[str, Any] | None:
        for n in RANGE_WINDOWS:
            a = i - n + 1
            if a < seg[i]:
                continue
            top, bot = float(h[a:i + 1].max()), float(l[a:i + 1].min())
            hgt = top - bot
            if hgt <= 0 or hgt < min_h * (cum[i + 1] - cum[a]) / n:
                continue
            lab = (h[a:i + 1] >= top - zone * hgt).astype(np.int8) + 2 * (l[a:i + 1] <= bot + zone * hgt).astype(np.int8)
            idx = np.flatnonzero(lab)
            if len(idx) < 2:
                continue
            seq = lab[idx]
            if (seq == 3).any():                                    # one minute in both bands: its open-to-close order
                order = []
                for k in idx:
                    v = int(lab[k])
                    order += ([2, 1] if c[a + k] >= o[a + k] else [1, 2]) if v == 3 else [v]
                seq = np.array(order)
            visits = int(np.count_nonzero(np.diff(seq))) + 1
            first = a + int(idx[0])
            if visits < need or ts[i] - ts[first] < min_age:
                continue
            back = max(int(seg[i]), first - 60)
            return {"start": float(ts[first]), "known": float(ts[i] + 60), "top": top, "bot": bot, "h": hgt,
                    "visits": visits, "window": n, "prior": int(np.sign(c[first] - c[back])), "first_i": first,
                    "far": {fr: float(lines[fr][1][first]) for fr in frames}}
        return None

    out, i, stop_i = [], int(np.searchsorted(ts, t0)), int(np.searchsorted(ts, t1))
    while i < stop_i:
        box = found(i) if i - seg[i] >= RANGE_WINDOWS[-1] - 1 else None
        if box is None:
            i += 1
            continue
        top, bot, hgt = box["top"], box["bot"], box["h"]
        box["breaks"], brk, last, j = [], None, box["known"], i + 1
        box["end_why"] = "life"
        while True:
            if j >= n_all or seg[j] != seg[i]:
                box["end_why"], j = "gap", j - 1                      # the range ends with the last minute before the gap
                break
            if (brk is None and ts[j] - last > life) or (brk is not None and ts[j] - brk["at"] > life):
                break
            if brk is None:
                d = 1 if c[j] > top + buf * hgt else -1 if c[j] < bot - buf * hgt else 0
                if d:
                    edge = top if d > 0 else bot
                    brk = {"at": float(ts[j] + 60), "side": d, "e0": float((c[j] - edge) * d / hgt), "exc": 0.0,
                           "first_leg": None, "depth": 0.0, "back_in": False, "new_ext": False, "rw_new_ext": None,
                           "cross_far": {}, "cross_back": {},
                           "session": _range_session(float(ts[j])), "with_prior": d == box["prior"],
                           "against_prior": d == -box["prior"],
                           "age_min": (float(ts[j]) - box["start"]) / 60.0, "i": j, "line": {}}
                    for fr in frames:                               # toward the line or away; did the line reach the range
                        ln = lines[fr][0]
                        if np.isfinite(ln[j]):
                            seen = ln[box["first_i"]:j + 1]
                            brk["line"][fr] = {"toward": d == (-1 if ln[j] < (top + bot) / 2 else 1),
                                               "far": box["far"][fr] >= 90.0,
                                               "line_in": bool(((seen >= bot) & (seen <= top)).any())}
            if brk is not None and j > brk["i"]:
                fresh_box = found(j)                                # a new range formed after the break: the old one is over
                if fresh_box is not None and fresh_box["start"] >= brk["at"] - 60:
                    box["end_why"], j = "new_range", j - 1
                    break
            if brk is not None:
                d = brk["side"]
                edge = top if d > 0 else bot
                # on the minute's close only: where the price stands after each minute is known exactly, so the random
                # price is judged from the very same point (a high or a low is a touch, not a place to stand)
                far = float(c[j] - edge) * d / hgt
                back = -far if j > brk["i"] else -1.0
                # where the price really was the minute it crossed each mark (a minute can jump past it): the random
                # price is judged from there, not from the mark
                for x in (0.25, 0.5, 0.75):
                    if far >= x and x not in brk["cross_far"]:
                        brk["cross_far"][x] = min(far, 1.0)
                for x in (0.0, 0.25, 0.5, 0.75):
                    if back > 0 and back >= x and x not in brk["cross_back"]:
                        brk["cross_back"][x] = min(back, 1.0)
                if brk["back_in"] and far > brk["first_leg"] and not brk["new_ext"]:
                    brk["new_ext"], brk["rw_new_ext"] = True, (1.0 + min(far, 1.0)) / 2.0
                brk["exc"] = max(brk["exc"], far)
                if back > 0 and not brk["back_in"]:
                    brk["back_in"], brk["first_leg"] = True, brk["exc"]
                brk["depth"] = max(brk["depth"], back)
                held, false = far >= 1.0, back >= 1.0
                if held or false:
                    brk["outcome"] = "same_minute" if held and false else "held" if held else "false"
                    brk["resolved"] = float(ts[j] + 60)
                    if brk["first_leg"] is None:
                        brk["first_leg"] = brk["exc"]
                    box["breaks"].append(brk)
                    brk, last = None, float(ts[j] + 60)
                    if box["breaks"][-1]["outcome"] != "false":
                        box["end_why"] = box["breaks"][-1]["outcome"]
                        break
            j += 1
        j = min(j, n_all - 1)
        if brk is not None:
            brk["outcome"], brk["resolved"], brk["why"] = "open", float(ts[j] + 60), box["end_why"]
            brk["first_leg"] = brk["exc"] if brk["first_leg"] is None else brk["first_leg"]
            box["breaks"].append(brk)
        box["end"] = float(ts[j] + 60)
        out.append(box)
        i = max(j + 1, i + 1)
    return out


def _tr_clock(t: float, fmt: str = "%H:%M") -> str:
    return datetime.fromtimestamp(t + TR_CLOCK, timezone.utc).strftime(fmt)


def owner_ranges(cfg: dict[str, Any], log=print) -> Path:
    """His two charts first (does the detector find his ranges and judge their breaks as he did?), then every range of each
    year: how many breaks were false and how many held, and whether what we saw on his charts tells them apart -- how far the
    break went, how deep the price came back, a new extreme after coming back, the side against the move before the range,
    the session. Beside each count: what a random price would give from the same point (the two ends are a height away)."""
    began = time.time()
    sym = cfg.get("symbol", "USTEC")
    folder = OUT_ROOT / date.today().isoformat() / safe("نطاقات المالك العرضيّة — " + cfg["name"])
    folder.mkdir(parents=True, exist_ok=True)
    pct = lambda a, b: round(100.0 * a / b, 1) if b else 0.0

    def brk_line(b: dict) -> str:
        word = {"held": "ثبت", "false": "كاذب", "same_minute": "الحدّان في دقيقة واحدة",
                "open": "بلا حسم، تكوّن بعده نطاقٌ جديد" if b.get("why") == "new_range" else "بلا حسم"}[b["outcome"]]
        return "كسرٌ %s عند %s، ابتعد %.2f من العرض، رجع داخله %.2f ⟵ %s (%s)" % (
            "فوق" if b["side"] > 0 else "تحت", _tr_clock(b["at"] - 60), b["exc"], max(0.0, b["depth"]), word,
            _tr_clock(b["resolved"] - 60))

    L = ["# نطاقات المالك العرضيّة — %s" % cfg["name"], "",
         "التعريف بكلامه: «السعر يتذبذب بين قمّة وقاع متساويين تقريبًا مع رينج سعريّ عم يتكرّر؛ أيّ كسر ما عم يثبت عليه بكون كسر كاذب».",
         "", "بالأرقام: على شموع الدقيقة، النطاق أعلى وأدنى نافذةٍ (20 إلى 240 دقيقة)، والسعر يزور شريط السقف وشريط الأرض بالتناوب "
         "%d زيارات على الأقلّ (كلّ شريط %d٪ من عرض النطاق نفسه)، وعرضه %.1f أضعاف مدى الدقيقة المعتاد فيه على الأقلّ، ويُعرف لحظة "
         "الزيارة الرابعة. الكسر إغلاقٌ خارج الحدّ بعُشر العرض. **ثبت** = ابتعد عرض النطاق كلّه خلف الحدّ، **كاذب** = بلغ الحدّ المقابل، "
         "أيّهما أوّلًا. الكاذب يُبقي النطاق، والثابت يُنهيه. الأوقات بساعة المالك." % (
             int(cfg.get("visits", 4)), int(100 * float(cfg.get("zone", 0.25))), float(cfg.get("min_height_bars", 3.0))), ""]
    for ex in cfg.get("examples", []):
        e0, e1 = (datetime.fromisoformat(x).replace(tzinfo=timezone.utc).timestamp() - TR_CLOCK for x in ex)
        L += ["## مثاله: %s — %s" % (ex[0], ex[1][11:]), ""]
        for bx in range_scan(sym, e0, e1, cfg):
            L.append("- نطاق من %s، عُرف %s · السقف %.1f · الأرض %.1f · العرض %.1f · زيارات %d" % (
                _tr_clock(bx["start"]), _tr_clock(bx["known"] - 60), bx["top"], bx["bot"], bx["h"], bx["visits"]))
            for b in bx["breaks"]:
                L.append("  - " + brk_line(b))
        L.append("")
    log("النطاقات: المثالان انتهيا")
    years_rows, allb, months = [], {}, {}
    frames, allbox, moms = list(cfg.get("line_frames") or []), {}, {}
    for y0, y1 in [tuple(y) for y in cfg["years"]]:
        t0, t1 = _epoch(y0), _epoch(y1)
        boxes = range_scan(sym, t0, t1, cfg)
        bl = [b for bx in boxes for b in bx["breaks"]]
        allb[y0[:4]], allbox[y0[:4]] = bl, boxes
        if frames:
            moms[y0[:4]] = line_far_moments(sym, t0, t1, frames)
        res = [b for b in bl if b["outcome"] in ("held", "false")]
        held = sum(b["outcome"] == "held" for b in res)
        rw = sum(min(1.0, (1.0 + b["e0"]) / 2.0) for b in res)
        inside, reach = 0.0, -1.0                                   # ranges overlap in their first minutes: the union
        for bx in sorted(boxes, key=lambda b_: b_["start"]):
            inside += max(0.0, bx["end"] - max(bx["start"], reach))
            reach = max(reach, bx["end"])
        market = float(len(load_minutes(sym, t0, t1)["t"])) * 60.0
        years_rows.append("| %s | %d | %s | %.1f | %d | %d | %d | %d | %s | %s | %s |" % (
            y0[:4], len(boxes), _span(np.median([bx["end"] - bx["start"] for bx in boxes]) if boxes else 0),
            float(np.median([bx["h"] for bx in boxes])) if boxes else 0.0, len(bl),
            sum(b["outcome"] == "false" for b in bl), held, sum(b["outcome"] in ("open", "same_minute") for b in bl),
            pct(held, len(res)), pct(rw, len(res)), pct(inside, market)))
        for bx in boxes:
            for b in bx["breaks"]:
                k = datetime.fromtimestamp(b["at"] + TR_CLOCK, timezone.utc).strftime("%Y-%m")
                m = months.setdefault(k, [0, 0, 0, 0])
                m[1] += 1
                m[2] += b["outcome"] == "false"
                m[3] += b["outcome"] == "held"
            k = datetime.fromtimestamp(bx["start"] + TR_CLOCK, timezone.utc).strftime("%Y-%m")
            months.setdefault(k, [0, 0, 0, 0])[0] += 1
        log("النطاقات: %s · نطاقات %d · كسور %d" % (y0[:4], len(boxes), len(bl)))
    if not allb:                                                    # his charts only: the detector checked on them first
        (folder / "النتيجة.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        return folder
    L += ["## كلّ سنة", "",
          "| السنة | نطاقات | مدّتها (الوسط) | عرضها بالنقاط (الوسط) | كسور | كاذب | ثابت | بلا حسم | ثبت من 100 (من المحسوم) | "
          "السعر العشوائيّ من النقطة نفسها | وقت النطاقات من وقت السوق ٪ |", "|---|---|---|---|---|---|---|---|---|---|---|"] + years_rows + [""]

    def cond_table(title: str, note: str, rows_: list[tuple[str, Any, Any]]) -> list[str]:
        T = ["## " + title, "", note, "", "| | " + " | ".join("%s: كسور · ثبت من 100 · العشوائيّ" % y for y in allb) + " |",
             "|---|" + "---|" * len(allb)]
        for label, pick, rwf in rows_:
            cells = []
            for y, bl in allb.items():
                s = [b for b in bl if b["outcome"] in ("held", "false") and pick(b)]
                hld = sum(b["outcome"] == "held" for b in s)
                cells.append("%d · %s · %s" % (len(s), pct(hld, len(s)), pct(sum(rwf(b) for b in s), len(s))))
            T.append("| %s | %s |" % (label, " | ".join(cells)))
        return T + [""]

    far_ = lambda x: (lambda b: x in b["cross_far"], lambda b: (1.0 + b["cross_far"][x]) / 2.0)
    back_ = lambda x: (lambda b: x in b["cross_back"], lambda b: (1.0 - b["cross_back"][x]) / 2.0)
    L += cond_table("كم ابتعد الكسر خلف الحدّ", "من الكسور التي بلغت هذا البعد (قبل أن تُحسم): كم منها ثبت. والعشوائيّ = (1 + البعد) ÷ 2، "
                    "والبعد حيث كان السعر فعلًا في الدقيقة التي بلغه فيها.",
                    [("بلغ ربع العرض",) + far_(0.25), ("بلغ نصف العرض",) + far_(0.5), ("بلغ ثلاثة أرباعه",) + far_(0.75)])
    L += cond_table("الرجعة إلى داخل النطاق", "من الكسور التي رجع السعر بعدها إلى داخل النطاق بهذا العمق (قبل أن تُحسم): كم منها ثبت "
                    "مع ذلك. والعشوائيّ = (1 − العمق) ÷ 2، والعمق حيث كان السعر فعلًا في تلك الدقيقة.",
                    [("رجع داخله",) + back_(0.0), ("رجع ربع العرض",) + back_(0.25), ("رجع نصف العرض",) + back_(0.5),
                     ("رجع ثلاثة أرباعه",) + back_(0.75)])
    L += cond_table("بعد الرجعة: قاعٌ أدنى (أو قمّةٌ أعلى) من أوّل الكسر", "رجع داخل النطاق ثمّ تجاوز أبعد نقطةٍ بلغها الكسر أوّلًا "
                    "(«ما نزل تحت قاع عمله» معكوسةً): كم منها ثبت. والعشوائيّ من حيث كان السعر لحظة التجاوز.",
                    [("رجع ثمّ تجاوز أوّل الكسر", lambda b: b["new_ext"], lambda b: b["rw_new_ext"] or 0.0)])
    L += cond_table("جهة الكسر والحركة قبل النطاق", "الحركة قبل النطاق = ساعةٌ قبل بدايته. والعشوائيّ من نقطة الكسر.",
                    [("الكسر في جهة الحركة قبله", lambda b: b["with_prior"], lambda b: min(1.0, (1 + b["e0"]) / 2)),
                     ("الكسر عكسها", lambda b: b["against_prior"], lambda b: min(1.0, (1 + b["e0"]) / 2))])
    L += cond_table("الجلسة", "جلسة لحظة الكسر.",
                    [(s, (lambda s_: lambda b: b["session"] == s_)(s), lambda b: min(1.0, (1 + b["e0"]) / 2))
                     for s in ("آسيا والليل", "لندن قبل نيويورك", "نيويورك")])
    fr_ar = {"1m": "الدقيقة", "5m": "الخمس دقائق", "15m": "الربع ساعة", "1h": "الساعة", "4h": "الأربع ساعات"}
    buckets = [("قريب (أقرب من نصف الشهر)", 0, 50), ("50–80", 50, 80), ("80–90", 80, 90), ("90–97", 90, 97),
               ("أبعد من 97 من 100", 97, 101)]
    for fr in frames:
        name = fr_ar.get(fr, fr)
        L += ["## خطّ 50 على %s — ما يفعله السعر بعد ساعة من كلّ إغلاق خمس دقائق" % name, "",
              "البعد عن الخطّ مقارنةً بالثلاثين يومًا قبله (90 = أبعد من 90 من كلّ 100 دقيقة في ذلك الشهر). «استمرّ بعيدًا» = بعد ساعة "
              "السعر أبعد في جهته (فوق الخطّ صعد، تحته نزل)، و«المتوقّع» ما يعطيه السوق نفسه في تلك السنة للجهة نفسها.", "",
              "| البعد | " + " | ".join("%s: لحظات · استمرّ بعيدًا من 100 · المتوقّع · لمس الخطّ خلال ساعة من 100" % y for y in moms) + " |",
              "|---|" + "---|" * len(moms)]
        for label, lo_, hi_ in buckets:
            cells = []
            for y, per in moms.items():
                allm = per[fr]
                p_up = float(np.mean([m[2] > 0 for m in allm])) if allm else 0.5
                s = [m for m in allm if lo_ <= m[0] < hi_]
                cells.append("%d · %s · %s · %s" % (len(s), pct(sum(m[2] * m[1] > 0 for m in s), len(s)),
                                                    pct(sum(p_up if m[1] > 0 else 1 - p_up for m in s), len(s)),
                                                    pct(sum(m[3] for m in s), len(s))))
            L.append("| %s | %s |" % (label, " | ".join(cells)))
        # a far price usually follows a wide hour, and the hour after a wide hour is narrower anyway: the fair look is among
        # the hours that followed a wide hour (the widest quarter of the year), far against near
        L += ["", "| البعد | " + " | ".join("%s: مدى الساعة التالية ÷ الساعة السابقة (الوسط) · نفسه بعد ساعةٍ سابقة كبيرة (أكبر ربع) · "
                                            "اقترب السعر من الخطّ (نقاط) · اقترب الخطّ من السعر (نقاط)" % y for y in moms) + " |",
              "|---|" + "---|" * len(moms)]
        for label, lo_, hi_ in buckets:
            cells = []
            for y, per in moms.items():
                q75 = float(np.percentile([m[5] for m in per[fr]], 75)) if per[fr] else 0.0
                s = [m for m in per[fr] if lo_ <= m[0] < hi_]
                ratio = float(np.median([m[4] / m[5] for m in s if m[5] > 0])) if s else 0.0
                wide = [m[4] / m[5] for m in s if m[5] >= q75 and m[5] > 0]
                cells.append("%.2f · %s · %+.1f · %+.1f" % (ratio, "%.2f (%d)" % (float(np.median(wide)), len(wide)) if wide else "—",
                                                          float(np.mean([m[6] for m in s])) if s else 0.0,
                                                          float(np.mean([m[7] for m in s])) if s else 0.0))
            L.append("| %s | %s |" % (label, " | ".join(cells)))
        started = " · ".join("%s: %s من 100" % (y, pct(sum(bx["far"].get(fr, 0) >= 90 for bx in bxs),
                                                       sum(np.isfinite(bx["far"].get(fr, np.nan)) for bx in bxs)))
                             for y, bxs in allbox.items())
        L += ["", "نطاقاتٌ بدأت والسعر أبعد من 90 من 100 عن خطّ %s: %s (لو كان البعد لا علاقة له بالنطاق لكانت نحو 10)." % (
            name, started), ""]
        has = lambda b, f=fr: f in b.get("line", {})
        rw0 = lambda b: min(1.0, (1 + b["e0"]) / 2)
        L += cond_table("كسر النطاق وخطّ 50 على %s" % name,
                        "«نحو الخطّ» = الكسر في الجهة التي فيها الخطّ (الخطّ تحت وسط النطاق والكسر هبوط، أو العكس). «بدأ بعيدًا» = السعر "
                        "عند أوّل النطاق أبعد من 90 من 100 عن الخطّ. «الخطّ دخل النطاق» = الخطّ صار بين سقفه وأرضه قبل الكسر.",
                        [("الكسر نحو الخطّ", lambda b, f=fr: has(b) and b["line"][f]["toward"], rw0),
                         ("الكسر بعيدًا عن الخطّ", lambda b, f=fr: has(b) and not b["line"][f]["toward"], rw0),
                         ("بدأ بعيدًا — الكسر نحو الخطّ", lambda b, f=fr: has(b) and b["line"][f]["far"] and b["line"][f]["toward"], rw0),
                         ("بدأ بعيدًا — الكسر بعيدًا عنه", lambda b, f=fr: has(b) and b["line"][f]["far"]
                          and not b["line"][f]["toward"], rw0),
                         ("الخطّ دخل النطاق قبل الكسر", lambda b, f=fr: has(b) and b["line"][f]["line_in"], rw0),
                         ("الخطّ لم يدخل النطاق", lambda b, f=fr: has(b) and not b["line"][f]["line_in"], rw0)])
    L += ["## الأشهر", "", "| الشهر | نطاقات | كسور | كاذب | ثابت | ثبت من 100 |", "|---|---|---|---|---|---|"]
    for k in sorted(months):
        m = months[k]
        L.append("| %s | %d | %d | %d | %d | %s |" % (k, m[0], m[1], m[2], m[3], pct(m[3], m[2] + m[3])))
    L += ["", "مدّة القياس %s." % _span(time.time() - began)]
    (folder / "النتيجة.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (folder / "الاختبار.md").write_text("# الاختبار\n\n```\n%s\n```\n" % json.dumps(cfg, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    return folder


def _span(sec: float) -> str:
    sec = int(max(0, sec))
    return "%d ساعة %d دقيقة" % (sec // 3600, sec % 3600 // 60) if sec >= 3600 else "%d دقيقة" % max(1, sec // 60)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ranges", default="", help="نطاقات المالك العرضيّة على الدقيقة: كم كسرٍ كاذب وكم ثابت")
    ap.add_argument("--box", default="", help="قياس مربّعات المالك على الدقيقة")
    ap.add_argument("--owner-draw", default="", help="رسم طريقة المالك على الشارت لأيّامٍ بعينها")
    ap.add_argument("--regime", default="", help="ملفّ حالة السوق: داو والمؤشّرات يقولون صاعد/هابط/عرضيّ ويُقاس ما فعله السعر")
    ap.add_argument("--grid", default="", help="ملفّ شبكة: توليفات كثيرة على كلّ زوج وسنة في مجلّدٍ واحد")
    ap.add_argument("--direction", default="", help="ملفّ اتّجاه الفريمات: كلّ فريم صاعد أو هابط بقاعدة المالك ويُقاس ما فعله السعر")
    ap.add_argument("--direction-fit", default="", help="ملفّ ضبط الاتّجاه على الماضي: أعدادٌ كثيرة ويُختار الأعلى")
    ap.add_argument("--direction-describe", default="", help="ملفّ معايرة الاتّجاه على موجات الماضي كما تراها العين")
    ap.add_argument("--direction-exam", default="", help="ملفّ امتحان الاتّجاه على سنةٍ لم يرها")
    ap.add_argument("--direction-learn", default="", help="ملفّ تعليم الاتّجاه: يتعلّم من شارت سنتين كاملًا ويُمتحن على سنةٍ لم يرها")
    ap.add_argument("--levels-plan", default="", help="ملفّ مستويات المتداول والسيناريوهين داخل التوليفة الحيّة")
    ap.add_argument("--session-detectors", default="", help="ملفّ الكواشف الثلاثة لتغيّر اتّجاه الجلسة")
    ap.add_argument("--system-plan", default="", help="ملفّ قياس المنظومة كما هي على أزواجها السبعة")
    ap.add_argument("--strategy-search", default="", help="ملفّ البحث عن استراتيجيّة رابحة: الجواب لكلّ لحظة وجهة، والتلميذ، وامتحان السنتين")
    ap.add_argument("--spec", default="", help="ملفّ التوليفة (يكتبه خادم الصفحة)")
    ap.add_argument("--done", default="", help="ملفٌّ يُكتب فيه مسار المجلّد عند الانتهاء")
    ap.add_argument("--wait-store", action="store_true", help="ينتظر اكتمال مخزن الحقائق ثمّ يشغّل (الجهاز وحده)")
    args = ap.parse_args()
    if args.ranges:
        folder = owner_ranges(json.loads(Path(args.ranges).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("النطاقات: انتهت · %s" % folder, flush=True)
        return 0
    if args.box:
        for folder in box_backtest(json.loads(Path(args.box).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True)):
            print("المربّعات: %s" % folder, flush=True)
        return 0
    if args.owner_draw:
        print("الرسم: %s" % owner_draw(json.loads(Path(args.owner_draw).read_text(encoding="utf-8"))), flush=True)
        return 0
    if args.regime:
        folder = regime(json.loads(Path(args.regime).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("حالة السوق: انتهت · %s" % folder, flush=True)
        return 0
    if args.system_plan:
        folder = system_plan(json.loads(Path(args.system_plan).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("المنظومة: انتهى · %s" % folder, flush=True)
        return 0
    if args.session_detectors:
        folder = session_detectors(json.loads(Path(args.session_detectors).read_text(encoding="utf-8")),
                                   log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("الكواشف: انتهى · %s" % folder, flush=True)
        return 0
    if args.levels_plan:
        folder = levels_plan(json.loads(Path(args.levels_plan).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("المستويات: انتهى · %s" % folder, flush=True)
        return 0
    if args.strategy_search:
        folder = strategy_search(json.loads(Path(args.strategy_search).read_text(encoding="utf-8")),
                                 log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("البحث: انتهى · %s" % folder, flush=True)
        return 0
    if args.direction_learn:
        folder = direction_learn(json.loads(Path(args.direction_learn).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("التعليم: انتهى · %s" % folder, flush=True)
        return 0
    if args.direction_exam:
        folder = direction_exam(json.loads(Path(args.direction_exam).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("الامتحان: انتهى · %s" % folder, flush=True)
        return 0
    if args.direction_describe:
        folder = direction_describe(json.loads(Path(args.direction_describe).read_text(encoding="utf-8")),
                                    log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("معايرة الاتّجاه: انتهت · %s" % folder, flush=True)
        return 0
    if args.direction_fit:
        folder = direction_fit(json.loads(Path(args.direction_fit).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("ضبط الاتّجاه: انتهى · %s" % folder, flush=True)
        return 0
    if args.direction:
        folder = direction(json.loads(Path(args.direction).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("اتّجاه الفريمات: انتهى · %s" % folder, flush=True)
        return 0
    if args.grid:
        folder = grid(json.loads(Path(args.grid).read_text(encoding="utf-8")), log=lambda s: print(s, flush=True))
        if args.done:
            Path(args.done).write_text(str(folder), encoding="utf-8")
        print("الشبكة: انتهت · %s" % folder, flush=True)
        return 0
    spec = merged(json.loads(Path(args.spec).read_text(encoding="utf-8")))
    if args.wait_store:
        index = Path(spec["store"]) / "index.json" if spec.get("store") else \
            STORE / spec["symbol"] / ("%s_%s" % (spec["from"], spec["to"])) / "index.json"
        while not index.exists():
            print("التوليفة: تنتظر اكتمال مخزن الحقائق …", flush=True)
            time.sleep(60)
    result = run(spec, log=lambda s: print(s, flush=True))
    names = Facts(Path(result["store"])).index.get("names", {})
    folder = write(result, names)
    if args.done:
        Path(args.done).write_text(str(folder), encoding="utf-8")
    print("التوليفة: انتهت · %s · %s ثانية" % (folder, result["seconds"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
