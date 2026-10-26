# -*- coding: utf-8 -*-
"""أين تسكن حافّة الإحصاء — نافذةً وأفقًا؟

قسم ٣٠٠ كلّه يقيس على **٢٠ تِكّة** (ثانيتان على بتكوين)، والحافّة الوحيدة
التي ظهرت في `quant_feature_study` كانت عند نافذة ٦٠٠ وأفق ٦٠٠٠. فالسؤال
ليس «أللإحصاء حافّة؟» بل «عند أيّ نافذةٍ وأيّ أفق؟» — ولا يُجاب بالرأي.

الطريقة هي طريقة القسم المعتمَدة، بلا تخفيف:
  · الطرفان لا الوسط (الرُبع الأعلى ناقص الأدنى).
  · ضبط الانحراف: يُطرح انحراف السوق × ميل الإشارة.
  · أربع نوافذ بإزاحة — ولا حكم دون ثلاثٍ منها.
  · والحدّ هو السبريد، و٢σ.

    python scripts/stats_window_study.py --symbol BTCUSD
"""
from __future__ import annotations

import argparse
import collections
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import quant_feature_study as qfs  # type: ignore  # noqa: E402

WINDOWS = (20, 60, 150, 300, 600, 1200, 2400)
HORIZONS = (1000, 3000, 6000)


def readings(series: list[float], window: int, step: int) -> dict[str, list[tuple[int, float]]]:
    """قراءةٌ موقّعة لكلّ وحدةٍ إحصائيّة من نافذتها — موجبها «اشترِ»."""
    out: dict[str, list[tuple[int, float]]] = collections.defaultdict(list)
    n = len(series)
    start = max(window + 1, 1200)
    for i in range(start, n - max(HORIZONS), step):
        seg = series[i - window:i]
        mean = sum(seg) / len(seg)
        sd = st.pstdev(seg) or 1e-12
        z = (series[i] - mean) / sd
        # ٣١٠ درجة Z — الارتداد: البُعد عن المتوسّط يُقرأ عكسيًّا.
        out["310_ارتداد_z"].append((i, -z))
        # ٣٠١ المتوسّط — الموقع منه، بلا تعيير بالتقلّب.
        out["301_موقع_المتوسّط"].append((i, -(series[i] - mean) / max(abs(mean), 1e-9)))
        # ٣٠٢ الوسيط — الموقع من الوسيط (أمتنُ للقيم الشاذّة).
        median = st.median(seg)
        out["302_موقع_الوسيط"].append((i, -(series[i] - median) / sd))
        # ٣٠٨ الانحدار — الميل، إشارةُ استمرار.
        half = len(seg) // 2
        slope = (sum(seg[half:]) / (len(seg) - half)) - (sum(seg[:half]) / half)
        out["308_ميل_الانحدار"].append((i, slope / sd))
        # ٣١٥ المدى — الموقع داخله، يُقرأ ارتدادًا.
        low, high = min(seg), max(seg)
        span = high - low
        position = ((series[i] - low) / span) if span > 0 else 0.5
        out["315_موقع_المدى"].append((i, -(position - 0.5) * 2.0))
        # ٣١١ الالتواء — أيّ الذيلين أثقل.
        m = sum(seg) / len(seg)
        s = st.pstdev(seg) or 1e-12
        out["311_التواء"].append((i, sum(((x - m) / s) ** 3 for x in seg) / len(seg)))
        # ٣١٨ مقارنة الفترات — انجراف النصف الأحدث عن الأقدم، ارتدادًا.
        out["318_انجراف_النصفين"].append((i, -slope / sd))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="نافذة الإحصاء وأفقها")
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--limit", type=int, default=60000)
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--step", type=int, default=25)
    args = parser.parse_args()
    symbol = args.symbol.upper()
    pip = qfs.PIP.get(symbol, 1e-2)
    qfs.HORIZONS = HORIZONS
    score: dict[tuple[str, int, int], list[tuple[float, float]]] = collections.defaultdict(list)
    spread_pips = 0.0
    for k in range(args.windows):
        series, spread = qfs.prices(symbol, args.limit, k * args.limit)
        if len(series) < args.limit // 2:
            continue
        spread_pips = spread / pip
        for window in WINDOWS:
            table = readings(series, window, args.step)
            for name, rows in table.items():
                for horizon in HORIZONS:
                    adjusted, se, n = qfs.evaluate(series, rows, pip, horizon)
                    if n:
                        score[(name, window, horizon)].append((adjusted, se))
        print("  إزاحة %d ✓" % (k * args.limit))
    need = max(2, (args.windows * 2 + 2) // 3)
    print("\n=== %s · سبريد %.0f نقطة · %d نوافذ · يلزم %d ==="
          % (symbol, spread_pips, args.windows, need))
    print("  %-20s %7s %7s %11s %11s %7s %s"
          % ("القراءة", "نافذة", "أفق", "وسيط الفرق", "أدنى نافذة", "تغطّي", "الحكم"))
    kept = []
    for (name, window, horizon), rows in sorted(score.items()):
        if len(rows) < args.windows:
            continue
        lowers = [a - 2.0 * s for a, s in rows]
        wins = sum(1 for low in lowers if low > spread_pips)
        if wins < need:
            continue
        kept.append((wins, st.median(a for a, _ in rows), name, window, horizon, min(lowers)))
    if not kept:
        print("  لا قراءة ثبتت — لا يُمنح اتّجاهٌ لأحد.")
    for wins, median, name, window, horizon, low in sorted(kept, reverse=True):
        print("  %-20s %7d %7d %11.1f %11.1f %6d/%d %s"
              % (name, window, horizon, median, low, wins, args.windows,
                 "حافّة"))


if __name__ == "__main__":
    main()
