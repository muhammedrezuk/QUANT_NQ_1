# -*- coding: utf-8 -*-
"""نظريّة داو كاملةً على إطارٍ واحد — ختم المالك «NQ» في ١٧/١٠: «على نظريّة داو كاملة» ثمّ «عملهم».

حقائق خام بلا حكم؛ القرار للاستراتيجيّة. وكلّ شيءٍ على **الإغلاقات** كما عدّها داو، لا على أطراف الشموع.
المبادئ الستّ وما يقابل كلًّا هنا:
  ١ السعر يخصم كلّ شيء            ⟸ لا حساب؛ هو سبب الاكتفاء بالسعر.
  ٢ ثلاثة اتّجاهات معًا             ⟸ الذرّة 209 تطبّق هذا الملفّ على ثلاثة أطر (يوميّ · ساعة · ربع ساعة).
     والتصحيح الثانويّ يستردّ ثلث الحركة إلى ثلثيها ⟸ `retracement` و`in_correction_zone`.
  ٣ أطوار الاتّجاه الثلاثة          ⟸ `legs`: عدد الموجات منذ بدأ الاتّجاه (تقريبٌ معلن؛ داو وصف الأطوار بالجمهور لا بالعدد).
  ٤ المؤشّرات يؤكّد بعضها بعضًا     ⟸ الذرّة 209 تقارن الناسداك بالإس آند بي والداو على الإطار الأساسيّ.
  ٥ الحجم يؤكّد الاتّجاه            ⟸ `volume_up_vs_down`: متوسّط حجم الشموع الصاعدة إلى الهابطة في آخر موجتين
     (حجمنا عدد تِكّات الوسيط، لا حجم البورصة).
  ٦ الاتّجاه قائم حتّى إشارة انعكاسٍ واضحة ⟸ `dow_trend` يبقى «صاعدًا» حتّى يُغلق السعر تحت آخر قاعٍ مؤكَّد
     (وعكسه)، فيصير «غير محدّد» حتّى يتكوّن الهيكل المعاكس على قمّةٍ أو قاعٍ جديد. و`last_break` يحفظ آخر كسر.
والصاعد: قمّتان آخرتان أعلى **و**قاعان آخران أعلى؛ والهابط عكسه.
القمّة/القاع: إغلاقٌ أعلى (أدنى) من `span` إغلاقات قبله وبعده، ويُؤكَّد بعد `span` شمعة؛ وقمّتان متتاليتان تبقى أعلاهما.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from shared.owner_windows import broker_day_offset_s, new_york_offset_h
except ImportError:  # noqa: BLE001
    broker_day_offset_s = new_york_offset_h = None

ADOPTED_PATH = Path(__file__).with_name("dow_adopted.json")
WEEK, MONTH = "1w", "1mo"
PIVOT_SPAN = 2
RETRACE_MIN = 1.0 / 3.0
RETRACE_MAX = 2.0 / 3.0
PIVOTS_FOR_STRUCTURE = 4            # two highs and two lows
RISING, FALLING, NONE = "rising", "falling", "none"
HH_HL, LH_LL, MIXED = "higher_highs_higher_lows", "lower_highs_lower_lows", "mixed"
BREAK_DOWN, BREAK_UP = "close_below_last_swing_low", "close_above_last_swing_high"
HIGH, LOW = "high", "low"
_CLOSE, _START, _OPEN, _VOLUME = 4, 0, 1, 5


def _pivot_at(closes: list[float], j: int, span: int) -> str | None:
    left, right = closes[j - span:j], closes[j + 1:j + 1 + span]
    if all(closes[j] > c for c in left + right):
        return HIGH
    if all(closes[j] < c for c in left + right):
        return LOW
    return None


def _add_pivot(pivots: list[tuple], pivot: tuple) -> bool:
    """Keeps highs and lows alternating: of two highs in a row the higher stays (of two lows the lower). True = a new swing."""
    if pivots and pivots[-1][1] == pivot[1]:
        keep_new = pivot[2] > pivots[-1][2] if pivot[1] == HIGH else pivot[2] < pivots[-1][2]
        if keep_new:
            pivots[-1] = pivot
        return False
    pivots.append(pivot)
    return True


def _last(pivots: list[tuple], kind: str, count: int) -> list[tuple]:
    return [p for p in pivots if p[1] == kind][-count:]


def _compare(older: float, newer: float) -> str:
    return "higher" if newer > older else "lower" if newer < older else "equal"


def structure(pivots: list[tuple]) -> tuple[str, str | None, str | None]:
    highs, lows = _last(pivots, HIGH, 2), _last(pivots, LOW, 2)
    if len(highs) < 2 or len(lows) < 2:
        return MIXED, None, None
    h, lo = _compare(highs[0][2], highs[1][2]), _compare(lows[0][2], lows[1][2])
    return (HH_HL if h == lo == "higher" else LH_LL if h == lo == "lower" else MIXED), h, lo


def frame_facts(bars: list[tuple], span: int = PIVOT_SPAN) -> dict[str, Any]:
    """bars: (start, open, high, low, close, volume) oldest first. Facts of one frame at its last close."""
    closes = [float(b[_CLOSE]) for b in bars]
    out: dict[str, Any] = {"bars": len(bars), "available": False}
    if len(bars) < span * 2 + 1:
        return out
    pivots: list[tuple] = []
    trend, since, legs, last_break = NONE, None, 0, None
    for i in range(len(bars)):
        j = i - span
        fresh = False
        if j >= span:
            kind = _pivot_at(closes, j, span)
            if kind:
                fresh = _add_pivot(pivots, (j, kind, closes[j], bars[j][_START]))
        lows, highs = _last(pivots, LOW, 1), _last(pivots, HIGH, 1)
        if trend == RISING and lows and closes[i] < lows[0][2]:
            trend, since, legs, last_break = NONE, None, 0, {"kind": BREAK_DOWN, "at": bars[i][_START], "level": lows[0][2]}
        elif trend == FALLING and highs and closes[i] > highs[0][2]:
            trend, since, legs, last_break = NONE, None, 0, {"kind": BREAK_UP, "at": bars[i][_START], "level": highs[0][2]}
        if fresh:
            shape, entered = structure(pivots)[0], False
            if shape == HH_HL and trend != RISING and lows and closes[i] >= lows[0][2]:
                trend, since, legs, entered = RISING, bars[i][_START], 1, True     # the leg that made the higher high
            elif shape == LH_LL and trend != FALLING and highs and closes[i] <= highs[0][2]:
                trend, since, legs, entered = FALLING, bars[i][_START], 1, True
            if not entered and ((trend == RISING and pivots[-1][1] == HIGH) or (trend == FALLING and pivots[-1][1] == LOW)):
                legs += 1
    shape, highs_vs, lows_vs = structure(pivots)
    last_high, last_low = _last(pivots, HIGH, 1), _last(pivots, LOW, 1)
    out.update({"available": len(pivots) >= PIVOTS_FOR_STRUCTURE, "close": closes[-1], "at": bars[-1][_START],
                "dow_trend": trend, "trend_since": since, "legs": legs, "structure": shape,
                "highs": highs_vs, "lows": lows_vs, "last_break": last_break,
                "last_swing_high": last_high[0][2] if last_high else None,
                "last_swing_low": last_low[0][2] if last_low else None,
                "swings": [{"kind": p[1], "close": p[2], "at": p[3]} for p in pivots[-PIVOTS_FOR_STRUCTURE:]]})
    out.update(_retracement(trend, pivots, closes[-1]))
    out["volume_up_vs_down"] = _volume_ratio(bars, pivots)
    return out


def trend_series(closes: list[float], span: int = PIVOT_SPAN) -> tuple[list[str], list[str | None]]:
    """The Dow trend after every close and the kind of the last break, by the same rules as `frame_facts` (its loop,
    without the legs) but in one pass with only the last two highs and lows kept -- so years of minutes run in seconds.
    Added 2026-10-22 for the backtest page (owner seal «NQ»: «مؤشّرات مع داو تقول صاعد أو هابط … مع شموع»); the live
    atom keeps `frame_facts`, and the tests prove both agree."""
    trends: list[str] = []
    breaks: list[str | None] = []
    highs: list[float] = []
    lows: list[float] = []
    last_kind: str | None = None
    trend, last_break = NONE, None
    for i, close in enumerate(closes):
        j = i - span
        fresh = False
        if j >= span:
            kind = _pivot_at(closes, j, span)
            if kind:
                value = closes[j]
                if last_kind == kind:
                    side = highs if kind == HIGH else lows
                    if (value > side[-1]) if kind == HIGH else (value < side[-1]):
                        side[-1] = value
                else:
                    side = highs if kind == HIGH else lows
                    side.append(value)
                    del side[:-2]
                    last_kind, fresh = kind, True
        if trend == RISING and lows and close < lows[-1]:
            trend, last_break = NONE, BREAK_DOWN
        elif trend == FALLING and highs and close > highs[-1]:
            trend, last_break = NONE, BREAK_UP
        if fresh and len(highs) == 2 and len(lows) == 2:
            h, lo = _compare(highs[0], highs[1]), _compare(lows[0], lows[1])
            if h == lo == "higher" and trend != RISING and close >= lows[-1]:
                trend = RISING
            elif h == lo == "lower" and trend != FALLING and close <= highs[-1]:
                trend = FALLING
        trends.append(trend)
        breaks.append(last_break)
    return trends, breaks


def _retracement(trend: str, pivots: list[tuple], close: float) -> dict[str, Any]:
    """How much of the last leg in the trend's way the price has given back (Dow's secondary correction: a third to two
    thirds). Rising: the last high and the low before it; falling: the last low and the high before it. Below zero = the
    price is already beyond the leg's end (a new extreme whose swing is not confirmed yet)."""
    empty = {"retracement": None, "in_correction_zone": None}
    if trend not in (RISING, FALLING):
        return empty
    end_kind, start_kind = (HIGH, LOW) if trend == RISING else (LOW, HIGH)
    end = _last(pivots, end_kind, 1)
    start = [p for p in pivots if p[1] == start_kind and end and p[0] < end[0][0]][-1:]
    if not end or not start or end[0][2] == start[0][2]:
        return empty
    given = (end[0][2] - close) / (end[0][2] - start[0][2])
    return {"retracement": round(given, 4), "in_correction_zone": RETRACE_MIN <= given <= RETRACE_MAX}


def _volume_ratio(bars: list[tuple], pivots: list[tuple]) -> float | None:
    """Mean volume of up-closing bars over down-closing bars across the last two legs (None without both kinds)."""
    if len(pivots) < 3:
        return None
    window = bars[pivots[-3][0] + 1:]
    up = [float(b[_VOLUME]) for b in window if b[_CLOSE] > b[_OPEN] and b[_VOLUME] is not None]
    down = [float(b[_VOLUME]) for b in window if b[_CLOSE] < b[_OPEN] and b[_VOLUME] is not None]
    if not up or not down or sum(down) == 0:
        return None
    return round((sum(up) / len(up)) / (sum(down) / len(down)), 4)


def broker_date(epoch_s: float) -> date:
    """The broker's trading date of an instant (the day closes with New York at 17:00; server clock = New York + 7)."""
    offset = broker_day_offset_s(epoch_s) if broker_day_offset_s else 0
    return datetime.fromtimestamp(epoch_s + offset, timezone.utc).date()


def _period_key(day: date, period: str) -> tuple[int, int]:
    return tuple(day.isocalendar()[:2]) if period == WEEK else (day.year, day.month)


def aggregate(day_rows: list[tuple], period: str, now_s: float) -> list[tuple]:
    """Week or month candles built from the day candles (the live feed has no week or month), the current unfinished
    one left out: (start, open, high, low, close, volume), oldest first."""
    current = _period_key(broker_date(now_s), period)
    groups: dict[tuple[int, int], list[tuple]] = {}
    for row in sorted(day_rows):
        groups.setdefault(_period_key(broker_date(row[_START]), period), []).append(row)
    out = []
    for key, rows in groups.items():
        if key == current:
            continue
        volumes = [r[_VOLUME] for r in rows if r[_VOLUME] is not None]
        out.append((rows[0][_START], rows[0][_OPEN], max(r[2] for r in rows), min(r[3] for r in rows), rows[-1][_CLOSE],
                    sum(volumes) if volumes else None))
    return out


def month_candles(symbol: str, day_rows: list[tuple], now_s: float) -> list[tuple]:
    """Closed months: the stored ones (`dow_month_seed.json` -- 450 day candles reach back only ~21 months), then the
    months after the last stored one built from the day candles; the current month never."""
    current = _period_key(broker_date(now_s), MONTH)
    seed = [tuple(r) for r in _seed().get(str(symbol).upper(), [])]
    seed = [r for r in seed if _period_key(broker_date(r[_START]), MONTH) < current]
    last = _period_key(broker_date(seed[-1][_START]), MONTH) if seed else (0, 0)
    built = [r for r in aggregate(day_rows, MONTH, now_s) if _period_key(broker_date(r[_START]), MONTH) > last]
    return seed + built


_SEED: dict[str, Any] = {}


def _seed() -> dict[str, list]:
    if "symbols" not in _SEED:
        try:
            _SEED["symbols"] = json.loads(ADOPTED_PATH.with_name("dow_month_seed.json").read_text(encoding="utf-8"))["symbols"]
        except (OSError, ValueError, KeyError):
            _SEED["symbols"] = {}
    return _SEED["symbols"]


def adopted() -> dict[str, Any]:
    """The owner's adopted direction readings (frames that must agree) and their measured record -- `dow_adopted.json`."""
    try:
        return json.loads(ADOPTED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


ASK_FROM_MIN, ASK_TO_MIN, SESSION_CLOSE_MIN = 9 * 60 + 45, 15 * 60 + 45, 16 * 60
MINUTES_PER_HOUR, SECONDS_PER_DAY = 60, 86400


def ny_clock(epoch_s: float) -> tuple[str, int] | None:
    """(New York date, minute of the day) of an instant -- None without the time-zone rules."""
    if new_york_offset_h is None:
        return None
    local = epoch_s + new_york_offset_h(epoch_s) * 3600
    day = datetime.fromtimestamp(local, timezone.utc)
    return day.date().isoformat(), day.hour * MINUTES_PER_HOUR + day.minute


def score(asks: list[list], close: float) -> dict[str, dict[str, int]]:
    """The session close against every reading asked that day: [reading, trend, price when asked] -> right / wrong / flat."""
    out: dict[str, dict[str, int]] = {}
    for reading, trend, price in asks:
        cell = out.setdefault(reading, {"right": 0, "wrong": 0, "flat": 0})
        if close == price:
            cell["flat"] += 1
        else:
            cell["right" if (close > price) == (trend == RISING) else "wrong"] += 1
    return out


def agree(states: list[str]) -> str:
    """One trend when every frame carries it, otherwise none."""
    values = set(states)
    return values.pop() if len(values) == 1 and NONE not in values else NONE


def agreement(main: dict[str, Any], others: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Dow's principle 4: do the other averages carry the same trend on the same frame?"""
    trend = main.get("dow_trend")
    same = sorted(s for s, f in others.items() if f.get("available") and f.get("dow_trend") == trend)
    differ = sorted(s for s, f in others.items() if f.get("available") and f.get("dow_trend") != trend)
    missing = sorted(s for s, f in others.items() if not f.get("available"))
    return {"trend": trend, "same": same, "different": differ, "missing": missing,
            "all_same": bool(others) and not differ and not missing and trend != NONE}
