"""هل الدخول عند اختبار الحدّ يعطي ١:٣؟ — قياسٌ من التِكّات، بلا هندسةٍ مفترضة.

السؤال وُلد من قياسٍ سابق (٢٠٢٦-٠٩-١٨): اختراقُ مدًى، دخولًا عند حدّه
وإبطالًا عند طرفه المقابل، صفقةُ **١:١ بنيويًّا** — لا قالبَ يصلحها. والحلّ
المقترَح أن يُنقل **الدخول** لا الوقف: لا ندخل عند الكسر بل عند عودة السعر
يختبر الحدّ.

⛔ ولا تُفترض هندسةٌ هنا ولا يُخترع وقف. يُقاس ما يسمح به السوق نفسه:
من لحظة الدخول، كم يبتعد السعر **ضدّنا** قبل أن يذهب معنا (`MAE`)، وكم
يبلغ **لصالحنا** (`MFE`). والنسبة المتاحة = ``MFE ÷ MAE`` — رقمٌ يقوله
السوق لا نحن. فإن كان وسيطها دون الثلاثة، فالفكرة لا تحتمل ١:٣ مهما
عُويرت، وإن كان فوقها فالمشكلة في موضع الدخول لا في الفكرة.

ويُقاس الطريقان جنبًا إلى جنب على الاختراقات نفسها: **الدخول عند الكسر**
و**الدخول عند الاختبار** — فالفرق بينهما هو قيمة الانتظار، مقيسةً.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics as st
import sys
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
    mid = [(bid + ask) / 2.0 for bid, ask in rows if bid and ask]
    spreads = [ask - bid for bid, ask in rows if ask and bid and ask > bid]
    return mid, (st.median(spreads) if spreads else 0.0)


def excursions(series: list[float], start: int, horizon: int, buy: bool,
               entry: float) -> tuple[float, float]:
    window = series[start:start + horizon]
    if len(window) < 2:
        return (0.0, 0.0)
    if buy:
        return (entry - min(window), max(window) - entry)
    return (max(window) - entry, entry - min(window))


def study(symbol: str, limit: int, window: int, horizon: int,
          retest_within: int) -> None:
    series, spread = prices(symbol, limit)
    if len(series) < window * 4:
        print("%s: عيّنة صغيرة (%d)" % (symbol, len(series)))
        return
    cost = spread
    at_break: list[tuple[float, float]] = []
    at_retest: list[tuple[float, float]] = []
    breaks = retests = 0
    index = window
    while index < len(series) - horizon - retest_within:
        past = series[index - window:index]
        high, low = max(past), min(past)
        price = series[index]
        buy = price > high + cost
        sell = price < low - cost
        if not (buy or sell):
            index += 1
            continue
        breaks += 1
        level = high if buy else low
        at_break.append(excursions(series, index, horizon, buy, price))
        # الاختبار: عودةُ السعر إلى الحدّ خلال نافذة الانتظار
        hit = None
        for step in range(1, retest_within):
            probe = series[index + step]
            if (buy and probe <= level) or (sell and probe >= level):
                hit = index + step
                break
        if hit is not None:
            retests += 1
            at_retest.append(excursions(series, hit, horizon, buy, series[hit]))
        index += window // 2

    def report(name: str, rows: list[tuple[float, float]]) -> None:
        if len(rows) < 20:
            print("  %-22s عيّنة صغيرة (%d)" % (name, len(rows)))
            return
        mae = [max(a, cost) for a, _ in rows]
        mfe = [b for _, b in rows]
        ratios = [f / a for a, f in zip(mae, mfe)]
        reach = 100.0 * sum(1 for r in ratios if r >= 3.0) / len(ratios)
        print("  %-22s n=%-5d  MAE وسيط=%-8.3f  MFE وسيط=%-9.3f  "
              "نسبة وسيطة=%-6.2f  تبلغ 1:3 في %.0f%%"
              % (name, len(rows), st.median(mae), st.median(mfe),
                 st.median(ratios), reach))

    print("\n=== %s — %d تِكّة · نافذة المدى %d · أفق %d · انتظار %d ==="
          % (symbol, len(series), window, horizon, retest_within))
    print("  سبريد=%.4f · اختراقات=%d · منها اختُبر %d (%.0f%%)"
          % (spread, breaks, retests, 100.0 * retests / max(1, breaks)))
    report("الدخول عند الكسر", at_break)
    report("الدخول عند الاختبار", at_retest)


def main() -> None:
    parser = argparse.ArgumentParser(description="قياس الدخول عند الاختبار")
    parser.add_argument("--symbols", nargs="*", default=["XAUUSD", "BTCUSD"])
    parser.add_argument("--limit", type=int, default=120000)
    parser.add_argument("--window", type=int, default=500)
    parser.add_argument("--horizon", type=int, default=2000)
    parser.add_argument("--retest-within", type=int, default=1000)
    args = parser.parse_args()
    for symbol in args.symbols:
        study(symbol.upper(), args.limit, args.window, args.horizon,
              args.retest_within)


if __name__ == "__main__":
    main()
