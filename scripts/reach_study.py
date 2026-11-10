"""هل تبلغ إشاراتُ استراتيجيّاتي ١:٣ بما يكفي لتغطية الكلفة؟

بُني على تصحيحٍ من قسم ٢٠٠-٢٤٩ (٢٠٢٦-٠٩-١٨) نقض استنتاجي:
قلتُ إنّ ١:٣ مستحيل لأنّ **وسيط** نسبة (الحركة المواتية ÷ المعاكسة) يبقى حول
١٫٠ مهما أطلنا الاحتفاظ — وذاك افتراضُ مشيٍ عشوائيّ، لا قياس. والصواب أنّ
السؤال عن **التوزيع** لا الوسيط:

    ثلاثُ إشاراتٍ من عشرٍ تبلغ ١:٣ فعلًا، ونقطةُ التعادل عند ١:٣ هي ٢٥٪
    (3p − (1−p) = 0). فالسؤال: **أتفوق نسبةُ البلوغ التعادلَ بعد الكلفة؟**

وقياسهم على إشارة البنية قال: نعم على داو والذهب وناسداك، **ولا على بتكوين**.
فهذه الأداة تعيد السؤال نفسه على **استراتيجيّاتي السبع** — لأنّها هي التي
تُتداول، لا إشارة البنية.

الطريقة: لكلّ إشارة، أقصى حركةٍ مواتية ومعاكسة داخل الأفق. الوقف يُفترض عند
**وسيط الحركة المعاكسة** للرمز، والهدف ثلاثةُ أضعافه. ثمّ:

    التعادل = (١ + الكلفة) ÷ ٤        والكلفة = ٢×سبريد ÷ الوقف المفترَض

⛔ ولا يشمل انزلاقًا ولا عمولة — وكلاهما يخصم من الجميع ويقتل «على الحدّ».
"""
from __future__ import annotations

import argparse
import asyncio
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import threshold_sweep as sweep  # type: ignore  # noqa: E402


async def run(symbols: list[str], limit: int, horizon: int, windows: int,
              atoms: tuple[int, ...], top_only: float = 0.0) -> None:
    for symbol in symbols:
        pip = sweep.PIP.get(symbol, 1e-2)
        print("\n=== %s · أفق %d تِكّة · %d نوافذ ===" % (symbol, horizon, windows))
        print("  %-6s %8s %10s %10s %9s %s"
              % ("ذرّة", "إشارات", "تبلغ 1:3", "التعادل", "الهامش", "الحكم"))
        totals: dict[int, list[tuple[float, float]]] = {}
        for k in range(windows):
            series, spread = sweep._prices(symbol, limit, k * limit)
            if len(series) < horizon * 3:
                continue
            spread_pips = spread / pip
            for atom_id in atoms:
                try:
                    sigs = await sweep._signals(atom_id, series, symbol)
                except Exception:  # noqa: BLE001
                    continue
                if top_only:
                    cut = sorted(v for _, _, v in sigs)[int(top_only * len(sigs))]
                    sigs = [r for r in sigs if r[2] >= cut]
                    if sigs: print("      [%d] عتبة القوّة عند %.1f" % (atom_id, cut))
                rows = []
                for i, direction, _ in sigs:
                    if i + horizon >= len(series):
                        continue
                    window = series[i:i + horizon]
                    entry = series[i]
                    if direction > 0:
                        mae, mfe = entry - min(window), max(window) - entry
                    else:
                        mae, mfe = max(window) - entry, entry - min(window)
                    rows.append((mae / pip, mfe / pip))
                if len(rows) < 200:
                    continue
                stop = st.median(a for a, _ in rows) or spread_pips
                reach = sum(1 for a, f in rows if f >= 3.0 * stop) / len(rows)
                cost = 2.0 * spread_pips / stop
                breakeven = (1.0 + cost) / 4.0
                totals.setdefault(atom_id, []).append((reach, breakeven))
        for atom_id, rows in sorted(totals.items()):
            if len(rows) < windows:
                continue
            reach = st.median(r for r, _ in rows)
            breakeven = st.median(b for _, b in rows)
            margin = 100.0 * (reach - breakeven)
            wins = sum(1 for r, b in rows if r > b)
            ruling = ("يغطّي — %d/%d" % (wins, len(rows))) if wins >= max(
                2, (len(rows) * 2 + 2) // 3) else "لا"
            print("  %-6d %8d %9.1f%% %9.1f%% %+8.1f %s"
                  % (atom_id, len(rows), 100.0 * reach, 100.0 * breakeven,
                     margin, ruling))


def main() -> None:
    parser = argparse.ArgumentParser(description="نسبة بلوغ ١:٣ مقابل التعادل")
    parser.add_argument("--symbols", nargs="*", default=["BTCUSD", "US30", "XAUUSD"])
    parser.add_argument("--limit", type=int, default=60000)
    parser.add_argument("--horizon", type=int, default=3000)
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--atoms", default="404,405,406,407,408,409,410")
    parser.add_argument("--top", type=float, default=0.0,
                        help="نسبة القطع: 0.75 = الرُبع الأعلى · 0.5 = النصف الأعلى")
    args = parser.parse_args()
    atoms = tuple(int(x) for x in args.atoms.split(",") if x.strip())
    asyncio.run(run([s.upper() for s in args.symbols], args.limit,
                    args.horizon, args.windows, atoms, args.top))


if __name__ == "__main__":
    main()
