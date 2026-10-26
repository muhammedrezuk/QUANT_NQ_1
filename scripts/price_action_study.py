"""أيُّ سلوكٍ سعريّ يفصل الصفقة التي تبلغ ١:٣ عن التي لا تبلغها؟

قِيس قبلها (٢٠٢٦-٠٩-١٨) أنّ اختراق المدى يعطي نسبةً وسيطةً ‎1.00‎ وأنّ ١:٣
تُبلَغ في ٢٥–٣٣٪ — وهو ما تعطيه حركةٌ عشوائيّة. فالفكرة بلا حافّةٍ هندسيّة،
**ولكنّ الثلث الذي يبلغها موجود**. والسؤال الوحيد الذي يستحقّ: هل يُعرَف قبل
وقوعه؟

فتُقاس هنا خصائصُ **سلوك السعر** لحظةَ الدخول — لا مؤشّرات ولا معاملات — ثمّ
يُقارَن كلٌّ منها بين المجموعتين. والخاصّة التي لا تفصل تُعلَن ولا تُدفن:
أكثرُ ما يُتعلَّم من قياسٍ كهذا هو ما **لا** ينفع.

⛔ لا تعدّل شيئًا. تقرأ `market_data.db` وتطبع جدول فصل.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "forex_runtime" / "var" / "store" / "market_data.db"


def prices(symbol: str, limit: int) -> tuple[list[float], float]:
    connection = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True, timeout=10)
    try:
        rows = connection.execute(
            "SELECT bid,ask FROM market_data WHERE symbol=? ORDER BY rowid DESC LIMIT ?",
            (symbol, limit)).fetchall()
    finally:
        connection.close()
    rows.reverse()
    mid = [(b + a) / 2.0 for b, a in rows if b and a]
    spreads = [a - b for b, a in rows if a and b and a > b]
    return mid, (st.median(spreads) if spreads else 0.0)


def features(series: list[float], i: int, window: int, buy: bool,
             level: float, width: float) -> dict[str, float]:
    """سلوك السعر لحظة الكسر — كلّه مشتقٌّ من السلسلة نفسها."""
    past = series[i - window:i]
    half = past[len(past) // 2:]
    opposite = min(past) if buy else max(past)
    recent_extreme = min(half) if buy else max(half)

    # ١) كنسُ الطرف المقابل قبل الكسر: هل أُخذت سيولةُ الجهة الأخرى حديثًا؟
    swept = 1.0 if ((buy and recent_extreme <= opposite + width * 0.05)
                    or (not buy and recent_extreme >= opposite - width * 0.05)) else 0.0

    # ٢) الاندفاع: سرعةُ آخر خمسين تِكّة إلى سرعة النافذة كلّها.
    def speed(rows: list[float]) -> float:
        if len(rows) < 2:
            return 0.0
        return sum(abs(rows[k] - rows[k - 1]) for k in range(1, len(rows))) / (len(rows) - 1)
    base = speed(past)
    impulse = (speed(series[i - 50:i]) / base) if base > 0 else 0.0

    # ٣) نضجُ الحدّ: كم مرّةً لامسه السعر قبل كسره.
    band = width * 0.05
    touches = float(sum(1 for p in past if abs(p - level) <= band))

    # ٤) موضعُ الكسر داخل مدى النافذة الأكبر — كسرٌ من قاعٍ غير كسرٍ من قمّة.
    lo, hi = min(past), max(past)
    place = ((series[i] - lo) / (hi - lo)) if hi > lo else 0.5
    if not buy:
        place = 1.0 - place

    # ٥) اتّساعُ المدى نسبةً إلى ضجيج السوق (المدى / متوسّط خطوة التِكّة).
    tightness = (width / base) if base > 0 else 0.0
    return {"كنس_مقابل": swept, "اندفاع": impulse, "لمسات_الحدّ": touches,
            "موضع_الكسر": place, "اتّساع_المدى": tightness}


def study(symbol: str, limit: int, window: int, horizon: int, target_r: float) -> None:
    series, spread = prices(symbol, limit)
    if len(series) < window * 4:
        print("%s: عيّنة صغيرة" % symbol)
        return
    rows: list[tuple[dict[str, float], bool]] = []
    i = window
    while i < len(series) - horizon:
        past = series[i - window:i]
        hi, lo = max(past), min(past)
        price = series[i]
        buy = price > hi + spread
        sell = price < lo - spread
        if not (buy or sell):
            i += 1
            continue
        width = hi - lo
        level = hi if buy else lo
        forward = series[i:i + horizon]
        if buy:
            mae, mfe = price - min(forward), max(forward) - price
        else:
            mae, mfe = max(forward) - price, price - min(forward)
        mae = max(mae, spread)
        rows.append((features(series, i, window, buy, level, width),
                     (mfe / mae) >= target_r))
        i += window // 2

    win = [f for f, ok in rows if ok]
    lose = [f for f, ok in rows if not ok]
    print("\n=== %s — %d اختراقًا · بلغ 1:%.0f منها %d (%.0f%%) ==="
          % (symbol, len(rows), target_r, len(win),
             100.0 * len(win) / max(1, len(rows))))
    if len(win) < 20 or len(lose) < 20:
        print("  عيّنة صغيرة للفصل")
        return
    print("  %-14s %10s %10s %9s %s" % ("الخاصّة", "بلغت", "لم تبلغ", "الفرق", "الحكم"))
    for key in win[0]:
        a, b = st.median(f[key] for f in win), st.median(f[key] for f in lose)
        pool = list(f[key] for f in win) + list(f[key] for f in lose)
        spread_all = (st.pstdev(pool) or 1.0)
        gap = (a - b) / spread_all
        ruling = ("يفصل" if abs(gap) >= 0.30 else
                  "ميلٌ ضعيف" if abs(gap) >= 0.15 else "لا يفصل")
        print("  %-14s %10.3f %10.3f %+9.2f %s" % (key, a, b, gap, ruling))


def main() -> None:
    parser = argparse.ArgumentParser(description="فصلُ الرابح بسلوك السعر")
    parser.add_argument("--symbols", nargs="*", default=["XAUUSD", "BTCUSD", "US30"])
    parser.add_argument("--limit", type=int, default=120000)
    parser.add_argument("--window", type=int, default=500)
    parser.add_argument("--horizon", type=int, default=2000)
    parser.add_argument("--target-r", type=float, default=3.0)
    args = parser.parse_args()
    for symbol in args.symbols:
        study(symbol.upper(), args.limit, args.window, args.horizon, args.target_r)


if __name__ == "__main__":
    main()
