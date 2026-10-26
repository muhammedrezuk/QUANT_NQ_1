# -*- coding: utf-8 -*-
"""الحركة وخريطة المستويات الستّ — خطّة المالك ١٠-١٧ (المرحلة 3، الخطوات 16 و18 و19؛ ختم «NQ»).

من شموع ربع الساعة وشموع اليوم (حيّةً وتاريخيّة)، لكلّ أصلٍ على نافذة بورصته (``shared.red_lines``):
  المستويات الستّ (الخطوة الثانية «المكان» كما أقرّها المالك): ١ جلسة الأمس (افتتاح · أعلى · أدنى · إغلاق) · ٢ ما قبل
  الافتتاح (للمؤشّرات الأمريكيّة: 04:00–09:30 نيويورك — **من عقد الوسيط الذي يتبع العقود الآجلة لا من الأسهم**) · ٣ الليل
  (من إغلاق الأمس إلى افتتاح اليوم) · ٤ الافتتاح وأوّل ربع ساعة · ٥ الفجوة (وهل امتلأت) · ٦ الأسبوع والشهر والسابقان.
  والحركة (الخطوة 16): مدى جلسة اليوم حتّى الآن وجلسة الأمس · مدى الأيّام الخمس السابقة · الأسبوع والشهر.
لكلّ مستوى بُعده بالبِب عن آخر سعر. و«هل يقع داخل الحركة المتوقّعة لليوم» يُملأ بعد قياس المرحلة 4 (الخطوة 24).
دوالّ صافية: الشموع واللحظة تُعطى لها.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from shared import red_lines
from shared.pips import to_pips

try:
    from zoneinfo import ZoneInfo
except ImportError:  # noqa: BLE001
    ZoneInfo = None

M15 = 15 * 60
PREMARKET_NY = ((4, 0), (9, 30))
PREVIOUS_DAYS = 5
WEEKDAYS = 5
MAX_WINDOW_BACK = 10
#: شمعة اليوم تبدأ مع يوم الوسيط (17:00 نيويورك من مساء اليوم السابق)؛ +12 ساعة تُوقعها على تاريخ يوم التداول نفسه.
DAY_CANDLE_SHIFT_S = 12 * 3600


def _trading_date(start: float):
    return datetime.fromtimestamp(start + DAY_CANDLE_SHIFT_S, timezone.utc).date()


def _zone(name: str):
    return ZoneInfo(name) if ZoneInfo is not None else None


def _ohlc(rows: list[tuple[float, float, float, float, float]]) -> dict[str, float] | None:
    """(start, o, h, l, c) مرتّبة ⟵ افتتاح · أعلى · أدنى · إغلاق."""
    if not rows:
        return None
    return {"open": rows[0][1], "high": max(r[2] for r in rows), "low": min(r[3] for r in rows), "close": rows[-1][4]}


def _signed_pips(distance: float, symbol: Any) -> float:
    """البُعد بالبِب بإشارته: موجبٌ فوق، سالبٌ تحت."""
    return to_pips(distance, symbol) * (1.0 if distance >= 0 else -1.0)


def _between(m15: list, start: float, end: float) -> list:
    return [r for r in m15 if start <= r[0] < end]


def windows(epoch: float, symbol: Any, count: int = PREVIOUS_DAYS + 1) -> list[tuple[float, float]]:
    """نوافذ الأصل (افتتاح · إغلاق) من الأحدث إلى الأقدم: الحاليّة أو الأخيرة أوّلًا."""
    name = red_lines.session_of(symbol)
    out: list[tuple[float, float]] = []
    if name == red_lines.GENERAL:
        oz, ohm = red_lines.GENERAL_OPEN
        cz, chm = red_lines.GENERAL_CLOSE
        opened = red_lines._last_at(epoch, oz, ohm)
        for _ in range(count):
            local_close = datetime.fromtimestamp(opened, _zone(cz)).replace(hour=chm[0], minute=chm[1], second=0, microsecond=0)
            while local_close.timestamp() <= opened:
                local_close += timedelta(days=1)
            out.append((opened, local_close.timestamp()))
            opened = red_lines._last_at(opened - 1, oz, ohm)
        return out
    zone_name, open_hm, close_hm = red_lines.SESSIONS[name]
    day = datetime.fromtimestamp(epoch, _zone(zone_name))
    for _ in range(count + MAX_WINDOW_BACK):
        if day.weekday() < WEEKDAYS:
            opened = day.replace(hour=open_hm[0], minute=open_hm[1], second=0, microsecond=0)
            if opened.timestamp() <= epoch:
                closes = day.replace(hour=close_hm[0], minute=close_hm[1], second=0, microsecond=0)
                out.append((opened.timestamp(), closes.timestamp()))
                if len(out) == count:
                    break
        day = (day - timedelta(days=1)).replace(hour=23, minute=59)
    return out


def _period_ohlc(d1: list, key) -> tuple[dict | None, dict | None]:
    """الحاليّة والسابقة لمفتاح فترةٍ على شموع اليوم (الأسبوع أو الشهر)."""
    groups: dict[Any, list] = {}
    for row in d1:
        groups.setdefault(key(row[0]), []).append(row)
    ordered = sorted(groups)
    current = _ohlc(groups[ordered[-1]]) if ordered else None
    previous = _ohlc(groups[ordered[-2]]) if len(ordered) > 1 else None
    return current, previous


def levels(symbol: Any, epoch: float, m15: list, d1: list) -> dict[str, Any]:
    """خريطة المستويات والحركة لأصلٍ عند لحظة. m15 و d1: قوائم (بداية · افتتاح · أعلى · أدنى · إغلاق) مرتّبة."""
    if red_lines.zones_available() is False or not m15:
        return {"available": False, "reason": "NO_ZONES" if not red_lines.zones_available() else "NO_CANDLES"}
    m15 = sorted(m15)
    last = m15[-1][4]
    wins = windows(epoch, symbol)
    (t_open, t_close), prev = wins[0], (wins[1] if len(wins) > 1 else None)
    today = _ohlc(_between(m15, t_open, min(epoch, t_close)))
    yesterday = _ohlc(_between(m15, prev[0], prev[1])) if prev else None
    overnight = _ohlc(_between(m15, prev[1], t_open)) if prev else None
    first = [r for r in m15 if r[0] == t_open]
    opening = {"price": first[0][1], "first15_high": first[0][2], "first15_low": first[0][3]} if first else None
    premarket = None
    if red_lines.session_of(symbol) == "NEW_YORK":
        zone = _zone(red_lines.NEW_YORK)
        day = datetime.fromtimestamp(t_open, zone)
        pm_start = day.replace(hour=PREMARKET_NY[0][0], minute=PREMARKET_NY[0][1]).timestamp()
        premarket = _ohlc(_between(m15, pm_start, t_open))
    gap = None
    if yesterday and opening:
        size = opening["price"] - yesterday["close"]
        low = today["low"] if today else opening["price"]
        high = today["high"] if today else opening["price"]
        gap = {"size": size, "pips": _signed_pips(size, symbol), "opened": "above_yesterday_close" if size > 0 else "below_yesterday_close" if size < 0 else "at_yesterday_close",
               "filled": (low <= yesterday["close"] <= high) if size else True}
    week, prev_week = _period_ohlc(sorted(d1), lambda s: tuple(_trading_date(s).isocalendar())[:2])
    month, prev_month = _period_ohlc(sorted(d1), lambda s: (_trading_date(s).year, _trading_date(s).month))
    ranges = []
    for o, c in wins[1:PREVIOUS_DAYS + 1]:
        day_ohlc = _ohlc(_between(m15, o, c))
        if day_ohlc:
            ranges.append(round(to_pips(day_ohlc["high"] - day_ohlc["low"], symbol), 1))
    marks: list[dict[str, Any]] = []

    def mark(name: str, price: float | None) -> None:
        if price is not None:
            marks.append({"name": name, "price": price, "pips_from_last": round(_signed_pips(price - last, symbol), 1),
                          "side": "above" if price > last else "below" if price < last else "at",
                          "within_expected_move": None})

    for prefix, block in (("yesterday", yesterday), ("premarket", premarket), ("overnight", overnight),
                          ("week", week), ("prev_week", prev_week), ("month", month), ("prev_month", prev_month)):
        if block:
            mark(prefix + "_high", block["high"])
            mark(prefix + "_low", block["low"])
    if yesterday:
        mark("yesterday_close", yesterday["close"])
    if opening:
        mark("open", opening["price"])
        mark("first15_high", opening["first15_high"])
        mark("first15_low", opening["first15_low"])
    above = sorted((m for m in marks if m["side"] == "above"), key=lambda m: m["price"])
    below = sorted((m for m in marks if m["side"] == "below"), key=lambda m: -m["price"])

    def rng(block: dict | None) -> float | None:
        return None if not block else round(to_pips(block["high"] - block["low"], symbol), 1)

    return {"available": True, "symbol": str(symbol), "session": red_lines.session_of(symbol), "last": last,
            "window": {"open": t_open, "close": t_close, "inside": t_open <= epoch < t_close},
            "today": today, "yesterday": yesterday, "premarket": premarket, "premarket_source": "broker_cfd_futures"
            if premarket is not None else None, "overnight": overnight, "opening": opening, "gap": gap,
            "week": week, "prev_week": prev_week, "month": month, "prev_month": prev_month,
            "movement_pips": {"today": rng(today), "yesterday": rng(yesterday), "previous_days": ranges,
                              "week": rng(week), "month": rng(month)},
            "nearest_above": above[:3], "nearest_below": below[:3], "levels": marks}
