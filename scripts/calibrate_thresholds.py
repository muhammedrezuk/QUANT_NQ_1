"""معايرة العتبات بالتكرار — لا تُعتمد شريحةٌ إلّا إن ثبتت في أكثر النوافذ.

بُنيت بعد درسٍ دُفع ثمنه مرّتين في يومٍ واحد (٢٠٢٦-٠٩-١٨):
  · ٤٠٩ أعطى `EDGE` في ثلاث شرائح بعيّنة **٢٥٬٠٩١ إشارة** ثمّ سقط كلّه في
    النافذة الثانية. **الحجم ليس بديلًا عن التكرار** — العيّنة الكبيرة تضيّق
    الخطأ المعياريّ *داخل* النافذة ولا تقول شيئًا عمّا يحدث خارجها.
  · وقسم ٣٥٠-٣٩٩ وقع في النمط نفسه: `352 EDGE` على نافذة، `weak` على خمس.

فهذه الأداة تشغّل `threshold_sweep` على نوافذَ متعدّدة بإزاحة، وتعدّ لكلّ
(محلّل × شريحة) كم نافذةً أعطته `EDGE` وكم أعطته `NEGATIVE`. والحكم:
  · `EDGE` في ≥ ثلثي النوافذ ⟹ عتبةٌ مرشّحة — أدنى قوّةٍ في تلك الشرائح.
  · `NEGATIVE` في ≥ ثلثيها ⟹ شريحةٌ تضرّ، تُسمّى ولا تُترجم تلقائيًّا.
  · ما دون ذلك ⟹ **ضجيج**، ولا يُغيَّر له عيار.

⛔ لا تعدّل شيئًا. تقرأ وتطبع جدول قرار.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import threshold_sweep as sweep  # type: ignore  # noqa: E402


async def collect(symbol: str, limit: int, offsets: list[int]) -> list[dict]:
    rows: list[dict] = []
    for offset in offsets:
        prices, spread = sweep._prices(symbol, limit, offset)
        if len(prices) < limit // 2:
            print("  إزاحة %d: عيّنة ناقصة (%d) — تُتخطّى" % (offset, len(prices)))
            continue
        pip = sweep.PIP.get(symbol, 1e-2)
        spread_pips = spread / pip
        for atom_id in sweep.DIRECTIONAL:
            try:
                sigs = await sweep._signals(atom_id, prices, symbol)
            except Exception as exc:  # noqa: BLE001
                print("  %d تعذّر: %s" % (atom_id, str(exc)[:40]))
                continue
            if len(sigs) < sweep.MIN_BUCKET * 2:
                continue
            strengths = sorted(s for _, _, s in sigs)
            cuts = [strengths[int(k * len(strengths) / sweep.BUCKETS)]
                    for k in range(1, sweep.BUCKETS)]
            bands = ([(-1e18, cuts[0])]
                     + [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]
                     + [(cuts[-1], 1e18)])
            for index, (lo, hi) in enumerate(bands):
                inside = [(i, d) for i, d, s in sigs if lo <= s < hi]
                if len(inside) < sweep.MIN_BUCKET:
                    continue
                bias = sum(1.0 if d > 0 else -1.0 for _, d in inside) / len(inside)
                best = None
                for horizon in sweep.HORIZONS:
                    fwd = [((prices[i + horizon] - prices[i]) / pip)
                           * (1.0 if d > 0 else -1.0)
                           for i, d in inside if i + horizon < len(prices)]
                    mean, se, n = sweep._cell(fwd)
                    drift, drift_se = sweep._drift(prices, horizon, pip)
                    adj = mean - drift * bias
                    joint = (se ** 2 + (drift_se * abs(bias)) ** 2) ** 0.5
                    lower = adj - 2.0 * joint
                    if best is None or lower > best[2]:
                        best = (adj, joint, lower, n)
                if best is None:
                    continue
                adj, joint, lower, n = best
                verdict = ("EDGE" if lower > spread_pips else
                           "NEGATIVE" if adj + 2.0 * joint < 0 else "weak")
                rows.append({"offset": offset, "atom": atom_id, "band": index,
                             "lo": max(lo, 0.0), "n": n, "verdict": verdict,
                             "adjusted": adj, "lower": lower})
        print("  إزاحة %d ✓" % offset)
    return rows


def decide(rows: list[dict], windows: int) -> None:
    tally: dict[tuple[int, int], collections.Counter] = collections.defaultdict(
        collections.Counter)
    floors: dict[tuple[int, int], list[float]] = collections.defaultdict(list)
    for row in rows:
        key = (row["atom"], row["band"])
        tally[key][row["verdict"]] += 1
        floors[key].append(row["lo"])
    need = max(2, (windows * 2 + 2) // 3)
    print("\n%-6s %-6s %-9s %-8s %-8s %s" % (
        "ذرّة", "شريحة", "أدنى قوّة", "EDGE", "NEGATIVE", "الحكم"))
    verdicts: dict[int, list[float]] = collections.defaultdict(list)
    for (atom_id, band), counter in sorted(tally.items()):
        edge, bad = counter["EDGE"], counter["NEGATIVE"]
        low = min(floors[(atom_id, band)])
        if edge >= need:
            ruling = "عتبة مرشّحة"
            verdicts[atom_id].append(low)
        elif bad >= need:
            ruling = "تضرّ — تُسمّى"
        else:
            ruling = "ضجيج"
        print("%-6d %-6d %-9.1f %-8s %-8s %s" % (
            atom_id, band, low, "%d/%d" % (edge, windows),
            "%d/%d" % (bad, windows), ruling))
    print("\n=== العتبات المشتقّة (تُعتمد فيها %d نافذة من %d) ===" % (need, windows))
    if not verdicts:
        print("  لا عتبة ثبتت — لا يُغيَّر عيار.")
    for atom_id, lows in sorted(verdicts.items()):
        print("  %d  →  strength_threshold = %.1f" % (atom_id, min(lows)))


def main() -> None:
    parser = argparse.ArgumentParser(description="معايرة العتبات بالتكرار")
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--limit", type=int, default=60000)
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--atoms", default="",
                        help="أرقام الذرّات مفصولةً بفاصلة؛ الافتراضي 404-410")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if args.atoms:
        sweep.DIRECTIONAL = tuple(int(x) for x in args.atoms.split(",") if x.strip())
    offsets = [k * args.limit for k in range(args.windows)]
    print("=== %s · %d تِكّة × %d نوافذ ===" % (args.symbol, args.limit, args.windows))
    rows = asyncio.run(collect(args.symbol, args.limit, offsets))
    decide(rows, args.windows)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print("\nكُتب: %s" % args.out)


if __name__ == "__main__":
    main()
