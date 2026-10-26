# -*- coding: utf-8 -*-
"""هل تُحسّن قراءةٌ إحصائيّة صفقات الاستراتيجيّات التي تتداول فعلًا؟

قِيس ٢٠٢٦-٠٩-١٩ أنّ قسم ٣٠٠ **بلا حافّة اتّجاهيّة** على بتكوين: ست قراءات
في سبع نوافذ حجمٍ وثلاثة آفاق، والرابحُ منها كان وسيطًا يكذب — النافذة
الرابعة وحدها ابتلعت كسبَ الثلاث (‎−10,636‎ مقابل ‎+3,023‎ وسيطًا)، ومع
وقفٍ سقطت ‎4/4‎ (تبلغ ‎10.0%‎ مقابل تعادل ‎27.2%‎).

فالسؤال الباقي ليس «أتشتري الإحصاء أم تبيع؟» بل: **أتقول متى نثق؟**
تُؤخذ إشارات ٤٠٦ و٤١٠ — وهما مَن يبني المستويات فتُفتح بهما الصفقات —
وتُشرَّح بحسب رُبع القراءة الإحصائيّة لحظةَ الإشارة. والقراءة تستحقّ
مكانها إن تفوّق رُبعٌ منها على التعادل في ≥٣ من ٤ نوافذ.

⛔ ولا تعديل هنا. تقرأ وتطبع.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import threshold_sweep as sweep  # type: ignore  # noqa: E402

STAT_WINDOW = 600
HORIZON = 6000


def stats_at(series: list[float], index: int) -> dict[str, float]:
    """قراءات القسم عند تِكّةٍ بعينها — من نافذته الخلفيّة وحدها."""
    seg = series[index - STAT_WINDOW:index]
    mean = sum(seg) / len(seg)
    sd = st.pstdev(seg) or 1e-12
    diffs = [seg[k] - seg[k - 1] for k in range(1, len(seg))]
    var1 = st.pvariance(diffs) if len(diffs) > 2 else 0.0
    agg = [seg[k] - seg[k - 10] for k in range(10, len(seg), 10)]
    var10 = (st.pvariance(agg) / 10.0) if len(agg) > 2 else 0.0
    # ٣٠٩ معامل التحديد — جودة خطّ الاتّجاه على النافذة.
    n = len(seg)
    xs = list(range(n))
    mx = (n - 1) / 2.0
    sxx = sum((x - mx) ** 2 for x in xs) or 1e-12
    sxy = sum((x - mx) * (v - mean) for x, v in zip(xs, seg))
    slope = sxy / sxx
    ss_tot = sum((v - mean) ** 2 for v in seg) or 1e-12
    ss_res = sum((v - (mean + slope * (x - mx))) ** 2 for x, v in zip(xs, seg))
    return {
        "304_الانحراف": sd,
        "305_نسبة_التباين": (var10 / var1) if var1 > 0 else 1.0,
        "309_معامل_التحديد": max(0.0, 1.0 - ss_res / ss_tot),
        "312_التفلطح": (sum(((v - mean) / sd) ** 4 for v in seg) / n) - 3.0,
        "315_عرض_المدى": (max(seg) - min(seg)) / sd,
    }


async def run(symbol: str, limit: int, windows: int, atoms: tuple[int, ...]) -> None:
    pip = sweep.PIP.get(symbol, 1e-2)
    # (ذرّة، قراءة، رُبع) -> [(تبلغ، تعادل) لكلّ نافذة]
    table: dict[tuple[int, str, int], list[tuple[float, float]]] = collections.defaultdict(list)
    base: dict[int, list[tuple[float, float]]] = collections.defaultdict(list)
    for k in range(windows):
        series, spread = sweep._prices(symbol, limit, k * limit)
        if len(series) < limit // 2:
            continue
        spread_pips = spread / pip
        for atom_id in atoms:
            try:
                signals = await sweep._signals(atom_id, series, symbol)
            except Exception as exc:  # noqa: BLE001
                print("  %d تعذّر: %s" % (atom_id, str(exc)[:50]))
                continue
            rows = []
            for i, direction, _ in signals:
                if i < STAT_WINDOW + 1 or i + HORIZON >= len(series):
                    continue
                entry = series[i]
                seg = series[i:i + HORIZON]
                if direction > 0:
                    mae, mfe = entry - min(seg), max(seg) - entry
                else:
                    mae, mfe = max(seg) - entry, entry - min(seg)
                rows.append((i, mae / pip, mfe / pip))
            if len(rows) < 200:
                continue
            stop = st.median(r[1] for r in rows) or spread_pips
            breakeven = (1.0 + 2.0 * spread_pips / stop) / 4.0
            base[atom_id].append((
                sum(1 for r in rows if r[2] >= 3.0 * stop) / len(rows), breakeven))
            readings = {i: stats_at(series, i) for i, _, _ in rows}
            for name in next(iter(readings.values())):
                values = sorted(readings[i][name] for i, _, _ in rows)
                cuts = [values[len(values) * q // 4] for q in (1, 2, 3)]
                for quartile in range(4):
                    lo = -1e18 if quartile == 0 else cuts[quartile - 1]
                    hi = 1e18 if quartile == 3 else cuts[quartile]
                    inside = [r for r in rows if lo <= readings[r[0]][name] < hi]
                    if len(inside) < 60:
                        continue
                    reach = sum(1 for r in inside if r[2] >= 3.0 * stop) / len(inside)
                    table[(atom_id, name, quartile)].append((reach, breakeven))
        print("  إزاحة %d ✓" % (k * limit))

    need = max(2, (windows * 2 + 2) // 3)
    print("\n=== %s · %d نوافذ · أفق %d · نافذة الإحصاء %d · يلزم %d ==="
          % (symbol, windows, HORIZON, STAT_WINDOW, need))
    for atom_id in atoms:
        rows = base.get(atom_id) or []
        if not rows:
            continue
        reach = st.median(r for r, _ in rows)
        be = st.median(b for _, b in rows)
        print("\n  [%d] بلا تشريح: تبلغ %.1f%% · تعادل %.1f%% · الهامش %+.1f"
              % (atom_id, 100 * reach, 100 * be, 100 * (reach - be)))
        print("  %-20s %-6s %10s %10s %8s %s"
              % ("القراءة", "رُبع", "تبلغ", "تعادل", "تفوق", "الحكم"))
        found = False
        for (a, name, quartile), cells in sorted(table.items()):
            if a != atom_id or len(cells) < windows:
                continue
            wins = sum(1 for r, b in cells if r > b)
            if wins < need:
                continue
            found = True
            print("  %-20s %-6d %9.1f%% %9.1f%% %7d/%d %s"
                  % (name, quartile, 100 * st.median(r for r, _ in cells),
                     100 * st.median(b for _, b in cells), wins, windows, "يغطّي"))
        if not found:
            print("  لا رُبعَ ثبت — القراءة لا تُحسّن هذه الاستراتيجيّة.")


def main() -> None:
    parser = argparse.ArgumentParser(description="الإحصاء مشرِّطًا لا مصوِّتًا")
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--limit", type=int, default=40000)
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--atoms", default="406,410")
    args = parser.parse_args()
    atoms = tuple(int(x) for x in args.atoms.split(",") if x.strip())
    asyncio.run(run(args.symbol.upper(), args.limit, args.windows, atoms))


if __name__ == "__main__":
    main()
