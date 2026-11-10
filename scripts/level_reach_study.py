# -*- coding: utf-8 -*-
"""هل يبلغ السعرُ المستوى التالي — وبأيّ نسبة؟

**طريقةُ المالك حرفيًّا**: التحليل على الإطار الكبير، والتنفيذ على الدقيقة،
والهدف **مستوًى** لا متوسّط. وما بنيناه حتّى اليوم عكسُها: ١١١ ذرّة تحليل
وسيطُ نافذتها ٢٠ تِكّة (نصف دقيقة)، ولا واحدة تنظر إلى شمعةٍ أكبر من
دقيقة — فأبعدُ هدفٍ نراه هو حدُّ نصف الدقيقة، و١:٤٠ مستحيلةٌ رياضيًّا لا
صعبة.

فهذا يقيس البديل قبل أن يُبنى منه سطر:

  ١) تُبنى شموعُ الساعة والأربع ساعات من التِكّات الحقيقيّة.
  ٢) تُستخرج المستويات: قمّةٌ/قاعٌ محوريّ (أعلى/أدنى من ك شمعةً جانبَيه).
  ٣) عند كلّ لمسةٍ لمستوى: دخولٌ عنده، ووقفٌ خلفه بتكلفة العبور المقيسة،
     وهدفٌ هو **المستوى التالي** في جهة الصفقة — لا رقمٌ مشتقّ.
  ٤) يُمشى بالسعر **حتّى الحسم** (لا سقفَ أفق — ذاك انحيازٌ قِيس وأُزيل).

والحكم بالمشي العشوائيّ: `1/(1+ر:م)`. فمطابقةُ نسبةِ الفوز له تعني أنّ
المستوى لا يقول شيئًا، مهما بدت النسبة جميلة.

    python scripts/level_reach_study.py --symbols US30 USTEC XAUUSD
"""
from __future__ import annotations

import argparse
import collections
import sqlite3
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "forex_runtime" / "var" / "store" / "market_data.db"


def ticks(symbol: str):
    connection = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True, timeout=20)
    try:
        rows = connection.execute(
            "SELECT occurred_at,bid,ask FROM market_data WHERE symbol=? ORDER BY rowid",
            (symbol,)).fetchall()
    finally:
        connection.close()
    return [(t, b, a) for t, b, a in rows if t and b and a and a > b]


def candles(rows, seconds: float):
    """شموعٌ حقيقيّة من التِكّات — بسلّةٍ زمنيّة لا بعدد تِكّات."""
    out = []
    bucket = None
    for t, b, a in rows:
        mid = (b + a) / 2.0
        start = int(t // seconds) * seconds
        if bucket is None or bucket["start"] != start:
            if bucket is not None:
                out.append(bucket)
            bucket = {"start": start, "open": mid, "high": mid, "low": mid, "close": mid}
        else:
            bucket["high"] = max(bucket["high"], mid)
            bucket["low"] = min(bucket["low"], mid)
            bucket["close"] = mid
    if bucket is not None:
        out.append(bucket)
    return out


def pivots(bars, side_bars: int):
    """قمّةٌ/قاعٌ محوريّ: أعلى (أدنى) من `side_bars` شمعةً على كلّ جانب.

    تعريفٌ قياسيّ لا مخترَع، ويُغلق بعد `side_bars` شمعةً — فلا يُقرأ
    مستقبلٌ: المستوى لا يُستعمل إلّا بعد أن يتأكّد.
    """
    highs, lows = [], []
    for i in range(side_bars, len(bars) - side_bars):
        window = bars[i - side_bars:i + side_bars + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((bars[i + side_bars]["start"], bars[i]["high"]))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((bars[i + side_bars]["start"], bars[i]["low"]))
    return highs, lows


def floor_for(symbol: str, price: float, spread: float) -> float:
    try:
        from shared import execution_costs as ec
        return float(ec.minimum_stop_distance(symbol, price, spread))
    except Exception:  # noqa: BLE001
        return spread * 2.0


def study(symbol: str, frame_s: float, side_bars: int, touch_frac: float) -> None:
    rows = ticks(symbol)
    if len(rows) < 5000:
        print("  %s عيّنةٌ ناقصة (%d)" % (symbol, len(rows)))
        return
    bars = candles(rows, frame_s)
    highs, lows = pivots(bars, side_bars)
    spread = st.median(a - b for _, b, a in rows[:20000])
    price0 = (rows[len(rows) // 2][1] + rows[len(rows) // 2][2]) / 2.0
    stop_floor = floor_for(symbol, price0, spread)
    levels = sorted([(t, p, "res") for t, p in highs] + [(t, p, "sup") for t, p in lows])
    if len(levels) < 4:
        print("  %s مستوياتٌ قليلة (%d)" % (symbol, len(levels)))
        return

    results = []
    used: dict[float, dict] = {}
    for index, (t, bid, ask) in enumerate(rows):
        mid = (bid + ask) / 2.0
        for lvl, state in used.items():
            if not state["away"] and abs(mid - lvl) > 2.0 * stop_floor:
                state["away"] = True
        # المستويات المؤكَّدة قبل هذه اللحظة وحدها
        live = [(p, kind) for lt, p, kind in levels if lt <= t]
        if len(live) < 3:
            continue
        near = [(abs(mid - p), p, kind) for p, kind in live
                if abs(mid - p) <= touch_frac * stop_floor]
        if not near:
            continue
        near.sort()
        _, level, kind = near[0]
        # زيارةٌ جديدة لا لمسةٌ واحدة: المستوى يُتداول مرّةً لكلّ اقتراب،
        # ويُفتح ثانيةً بعد أن يبتعد السعرُ عنه بضعفَي أدنى وقف. وبلا هذا
        # تُقاس ستُّ صفقاتٍ في خمسة أيّام — عيّنةٌ لا يُحكم منها.
        key = round(level, 6)
        gone = used.get(key)
        if gone is not None and not gone["away"]:
            continue
        buy = kind == "sup"
        stop = level - stop_floor if buy else level + stop_floor
        ahead = sorted({p for p, _ in live if (p > level if buy else p < level)})
        target = (ahead[0] if buy else ahead[-1]) if ahead else None
        if target is None:
            continue
        risk = abs(mid - stop)
        reward = abs(target - mid)
        if risk <= 0 or reward <= 0:
            continue
        used[key] = {"away": False}
        hit = None
        for t2, b2, a2 in rows[index + 1:]:
            if buy:
                if b2 <= stop:
                    hit = False; break
                if b2 >= target:
                    hit = True; break
            else:
                if a2 >= stop:
                    hit = False; break
                if a2 <= target:
                    hit = True; break
        if hit is None:
            continue
        results.append((hit, reward / risk))

    if len(results) < 30:
        print("  %-8s عيّنةٌ صغيرة (%d صفقة)" % (symbol, len(results)))
        return
    bands = ((1.0, 3.0), (3.0, 7.0), (7.0, 15.0), (15.0, 1e9))
    print("\n  %-8s %d صفقة · وقفٌ أدنى %.4f · سبريد %.4f" % (symbol, len(results), stop_floor, spread))
    print("    %-12s %-8s %-8s %-9s %-11s %s"
          % ("شريحة ر:م", "صفقات", "ر:م", "فوز", "صدفةً", "الفرق"))
    for lo, hi in bands:
        cell = [(w, r) for w, r in results if lo <= r < hi]
        if len(cell) < 20:
            continue
        ratio = st.median(r for _, r in cell)
        wins = sum(1 for w, _ in cell if w)
        predicted = 1.0 / (1.0 + ratio)
        measured = wins / len(cell)
        se = (predicted * (1 - predicted) / len(cell)) ** 0.5
        sigma = (measured - predicted) / se if se else 0.0
        print("    %-12s %-8d %7.2f %8.1f%% %10.1f%% %+7.1f σ %s"
              % ("%g–%g" % (lo, hi), len(cell), ratio, 100 * measured,
                 100 * predicted, sigma,
                 "▲ معلومة" if sigma > 2 else ("▼ مقلوبة" if sigma < -2 else "= صدفة")))
    ratio = st.median(r for _, r in results)
    wins = sum(1 for w, _ in results if w)
    predicted = 1.0 / (1.0 + ratio)
    measured = wins / len(results)
    se = (predicted * (1 - predicted) / len(results)) ** 0.5
    print("    %-12s %-8d %7.2f %8.1f%% %10.1f%% %+7.1f σ"
          % ("الكلّ", len(results), ratio, 100 * measured, 100 * predicted,
             (measured - predicted) / se if se else 0.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="بلوغُ المستوى التالي")
    parser.add_argument("--symbols", nargs="*",
                        default=["US30", "USTEC", "XAUUSD", "BTCUSD"])
    parser.add_argument("--frame", type=float, default=3600.0,
                        help="ثواني الشمعة: 3600=ساعة · 14400=أربع ساعات")
    parser.add_argument("--side", type=int, default=2,
                        help="شموعٌ على كلّ جانبٍ لتأكيد المحور")
    parser.add_argument("--touch", type=float, default=0.5,
                        help="اللمسة = هذا المضاعف × أدنى وقف")
    args = parser.parse_args()
    print("=== المستوى التالي هدفًا · شمعة %.0f ث · محورٌ بـ%d جانبًا ==="
          % (args.frame, args.side))
    for symbol in args.symbols:
        study(symbol.upper(), args.frame, args.side, args.touch)


if __name__ == "__main__":
    main()
