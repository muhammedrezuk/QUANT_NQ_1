# -*- coding: utf-8 -*-
"""بذرة سلّم المستويات (201) من شموع سي‑تريدر المخزَّنة — مصدرٌ واحد للحيّ والاختبار التاريخيّ.

ختم المالك ٢٠٢٦-١٠-٠٦ (الخطوة الأولى من «أكبر هدف»، اقتبسها وختمها «NQ صلاحية كاملة»):
«البذرة العميقة: أكتبها من شموع سي‑تريدر بأقصى ما يحفظه السلّم: 100 ربع ساعة، و200 ساعة،
و200 أربع ساعات، و200 يوم. ولا تدخلها إلا شموع مغلقة».

· الربع ساعة والساعة من شموعهما في المخزن (`candles_history` — أداة `tools/جلب_تاريخ_سي_تريدر.py`).
· الأربع ساعات واليوم بتجميع الساعة على حدود غرينتش كما يبني 103 شموعه حيًّا — شموع الوسيط
  الكبيرة على منتصف ليل خادمه، فلو أُخذت لاختلفت بداياتها عن شموع 103 ولتكرّر المستوى نفسه.
· لا تدخل إلّا شمعةٌ أُغلقت قبل `until`، ولا الدلو الأوّل من التجميع (قد يبدأ في منتصفه).
· المخزن يُفتح للقراءة وحدها.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

#: عدد الشموع لكلّ فريم (نصّ الختم) — بعدد `LADDER_KEEP` في 201 و`DEPTH` في `structure_exits`.
#: ٢٠٢٦-١٠-٠٦ 17:1x — **و300 خمس دقائق (≈25 ساعة)** بختم المالك «NQ» على سؤاله «ليش ما بيقرا شموع ماضية
#: لا 5 دقايق… يستنا 5 شموع جديدة… ما يقرا الشارت كله»: وقف الناسداك وتتبّعه على الخمس دقائق انتظرا بعد
#: إقلاع 16:04 حتّى 16:50 أوّل قاعٍ مؤكَّد من الحيّ، لأنّ البذرة لم يكن فيها هذا الفريم.
SEED_BARS = {"5m": 300, "15m": 100, "1h": 200, "4h": 200, "1d": 200}
#: نافذة الساعات المقروءة للتجميع: مئتا يومِ تداولٍ لرمزٍ يتداول خمسة أيّامٍ ≈ 280 يومًا تقويميًّا.
HOURS_BACK_DAYS = 400
_DIRECT = {"5m": ("M5", 300), "15m": ("M15", 900), "1h": ("H1", 3600)}
_GROUPED = {"4h": 14400, "1d": 86400}


def _closed(db: sqlite3.Connection, symbol: str, period: str, seconds: int, until: float,
            limit: int) -> list[list[float]]:
    rows = db.execute("SELECT period_start, high, low, close FROM candles_history WHERE symbol=? AND period=? "
                      "AND period_start + ? <= ? ORDER BY period_start DESC LIMIT ?",
                      (symbol, period, seconds, int(until), int(limit))).fetchall()
    return [[float(t), float(h), float(lo), float(c)] for t, h, lo, c in sorted(rows)]


def _grouped(hours: list[list[float]], seconds: int, until: float, limit: int) -> list[list[float]]:
    buckets: dict[int, list[float]] = {}
    for t, high, low, close in hours:
        key = int(t) // seconds * seconds
        if key + seconds > until:
            continue                                    # الدلو الذي لم يُغلق قبل `until` لا يدخل
        b = buckets.setdefault(key, [high, low, close])
        b[0], b[1], b[2] = max(b[0], high), min(b[1], low), close   # الساعات مرتّبة: الأخير إغلاق الدلو
    keys = sorted(buckets)[1:]                          # الأوّل قد يبدأ في منتصفه
    return [[float(k), buckets[k][0], buckets[k][1], buckets[k][2]] for k in keys][-limit:]


def build_seed(db_path: Path | str, symbols: Iterable[str], until: float | None = None,
               bars: dict[str, int] | None = None, label: str = "") -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    """البذرة `{symbols: {رمز: {فريم: [[البداية، الأعلى، الأدنى، الإغلاق]…]}}}` وعدد شموع كلّ فريم.

    ٢٠٢٦-١٠-٠٦: الإغلاق عنصرٌ رابع (لإذن الاتّجاه اليوميّ في 201/`structure_exits`) — و201 يقرأ الثلاثة الأولى.

    رمزٌ لا شموع له في المخزن لا يدخل البذرة — فيبقى سلّمه على ما يبنيه الحيّ.
    """
    until = float(until if until is not None else time.time())
    depth = dict(SEED_BARS if bars is None else bars)
    uri = "file:%s?mode=ro" % Path(db_path).as_posix()
    db = sqlite3.connect(uri, uri=True)
    seed: dict[str, Any] = {"symbols": {}, "built_at": until,
                            "built_at_text": label or time.strftime("%Y-%m-%d %H:%M", time.gmtime(until)) + " غرينتش",
                            "source": "شموع سي‑تريدر المخزَّنة (%s)" % Path(db_path).name}
    counts: dict[str, dict[str, int]] = {}
    try:
        for symbol in symbols:
            frames: dict[str, list[list[float]]] = {}
            for frame, (period, seconds) in _DIRECT.items():
                frames[frame] = _closed(db, symbol, period, seconds, until, depth[frame])
            hours = [[float(t), float(h), float(lo), float(c)] for t, h, lo, c in db.execute(
                "SELECT period_start, high, low, close FROM candles_history WHERE symbol=? AND period='H1' "
                "AND period_start >= ? AND period_start + 3600 <= ? ORDER BY period_start",
                (symbol, int(until - HOURS_BACK_DAYS * 86400), int(until)))]
            for frame, seconds in _GROUPED.items():
                frames[frame] = _grouped(hours, seconds, until, depth[frame])
            counts[symbol] = {k: len(v) for k, v in frames.items()}
            if any(frames.values()):
                seed["symbols"][symbol] = frames
    finally:
        db.close()
    seed["bars"] = counts
    return seed, counts


#: أطر تسخين المحلّلين — الخمسة التي يزنها 166 في بطاقته البطيئة (`_FRAME_WEIGHT`).
WARM_DIRECT = {"5m": ("M5", 300), "15m": ("M15", 900), "1h": ("H1", 3600)}


def history_candles(db_path: Path | str, symbols: Iterable[str], until: float,
                    bars: int = 300) -> list[tuple[float, int, dict[str, Any]]]:
    """شموعٌ مغلقة قبل `until` بحقول `market_data.candle_closed` كما ينشرها 103 — لتسخين المحلّلين.

    `(لحظة الإغلاق، طول الفريم، الحمولة)` مرتّبةً بالإغلاق ثمّ الأصغر أوّلًا — كما يغلق 103 أطره عند
    الحدّ الواحد. الهويّة (الحساب والوسيط) تُضاف عند النشر. حدٌّ معلن: شموع سي‑تريدر بسعر العرض،
    و103 يبني بالمتوسّط — الفرق نصف فرق السعر.
    """
    uri = "file:%s?mode=ro" % Path(db_path).as_posix()
    db = sqlite3.connect(uri, uri=True)
    out: list[tuple[float, int, dict[str, Any]]] = []

    def candle(symbol: str, frame: str, seconds: int, row: tuple) -> tuple[float, int, dict[str, Any]]:
        start, o, h, lo, c, v = row
        # ٢٠٢٦-١٠-٠٦: الحجم صفر كشموع 103 الحيّة — تِكّات سي‑تريدر الحيّة بلا حجم، فدليل الحجم عند
        # المحلّلين 45 لا 100 (`shared/live_analysis` §٦). حجمُ الشمعة التاريخيّ كان يرفع العمق في الإعادة
        # فوق ما يبلغه الحيّ (مقيس: ساعة الذهب حيًّا 71.75 مقابل 80 في الإعادة صباح الاثنين).
        return (float(start) + seconds, seconds, {
            "provider": "CTRADER", "symbol": symbol, "open": float(o), "high": float(h), "low": float(lo),
            "close": float(c), "volume": 0.0, "tick_count": int(v or 0), "fabric_gap": False,
            "timeframe": frame, "period_start": float(start), "timestamp": float(start)})
    try:
        for symbol in symbols:
            for frame, (period, seconds) in WARM_DIRECT.items():
                rows = db.execute("SELECT period_start, open, high, low, close, tick_volume FROM candles_history "
                                  "WHERE symbol=? AND period=? AND period_start + ? <= ? "
                                  "ORDER BY period_start DESC LIMIT ?",
                                  (symbol, period, seconds, int(until), int(bars))).fetchall()
                out.extend(candle(symbol, frame, seconds, r) for r in sorted(rows))
            days = max(HOURS_BACK_DAYS, int(bars * 1.5))
            hours = db.execute("SELECT period_start, open, high, low, close, tick_volume FROM candles_history "
                               "WHERE symbol=? AND period='H1' AND period_start >= ? AND period_start + 3600 <= ? "
                               "ORDER BY period_start", (symbol, int(until - days * 86400), int(until))).fetchall()
            for frame, seconds in _GROUPED.items():
                buckets: dict[int, list[float]] = {}
                for t, o, h, lo, c, v in hours:
                    key = int(t) // seconds * seconds
                    if key + seconds > until:
                        continue
                    b = buckets.get(key)
                    if b is None:
                        buckets[key] = [float(o), float(h), float(lo), float(c), float(v or 0)]
                    else:
                        b[1], b[2], b[3], b[4] = max(b[1], h), min(b[2], lo), float(c), b[4] + float(v or 0)
                keys = sorted(buckets)[1:][-int(bars):]
                out.extend(candle(symbol, frame, seconds, (k, *buckets[k])) for k in keys)
    finally:
        db.close()
    out.sort(key=lambda item: (item[0], item[1]))
    return out


def fractal_levels(rows: list[list[float]], side: int = 2) -> tuple[int, int]:
    """كم قمّةً وقاعًا تؤكّدها هذه الشموع بتعريف 201 نفسه (أعلى/أدنى بصرامة من شمعتين كلّ جهة)."""
    highs = lows = 0
    for i in range(side, len(rows) - side):
        others = rows[i - side:i] + rows[i + 1:i + side + 1]
        highs += all(rows[i][1] > o[1] for o in others)
        lows += all(rows[i][2] < o[2] for o in others)
    return highs, lows


def write_seed(path: Path | str, seed: dict[str, Any]) -> Path:
    """كتابةٌ ذرّيّة: ملفٌّ مؤقّت ثمّ استبدال — فلا يقرأ إقلاعٌ بذرةً نصف مكتوبة."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path
