# -*- coding: utf-8 -*-
"""أين تسكن معلومةُ ٤٠٥ — وهل تمتدّ دون عتبته الحاليّة؟

٤٠٥ لا ينشر إعدادًا إلّا عند `|z| ≥ setup_z` (٣٫٠ اليوم)، فإعدادُه موجودٌ
في ‎3–20٪‎ من الوقت فقط ويُحجَب ‎305‎ من ‎426‎ طلبًا بـ`NO_STOP_FOR_SIDE`.
والحافّة مقيسة: ‎+5.7σ‎ على داو و‎+6.0σ‎ على ناسداك فوق المشي العشوائيّ.

**السؤال:** أهي حافّةُ الطرف المتطرّف وحده، أم تمتدّ إلى ما دونه؟
فإن امتدّت، خفضُ العتبة يزيد الصفقات **بحافّةٍ مقيسة لا بأمل**؛ وإن لم
تمتدّ، تبقى العتبة ويُطلَب مصدرٌ آخر.

⛔ ولا وقفَ مفترَض ولا هدفَ مفترَض: كلاهما من الإعداد الذي تنشره الذرّة.
والحكم بالمشي العشوائيّ: `1/(1+ر:م)` — فمطابقةُ نسبةِ الفوز له تعني
صفرَ معلومة مهما بدا التوقّع.

    python scripts/z_band_information.py --symbols US30 USTEC
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

import setup_outcome_study as sos  # type: ignore  # noqa: E402

#: ⛔ **الأفق المحدود ينحاز سلبًا ببنائه** — مقيس ٢٠٢٦-٠٩-٢٢: بأفق ٦٠٠٠
#: بقيت ٢٦١ من ٤٢٤ صفقة **معلّقة** (‎61٪‎). والوقفُ قريبٌ (‎1σ‎) والهدفُ بعيد
#: (‎3.5σ‎)، فما يُحسم داخل الأفق أكثرُه وقفٌ وما يُستبعَد أكثرُه هدفٌ لم
#: يبلغ بعد. وخطُّ المشي العشوائيّ `1/(1+ر:م)` محسوبٌ **لزمنٍ بلا حدّ**،
#: فمقارنةُ مقيسٍ مبتورٍ به تُظهر كلَّ شيءٍ مقلوبًا.
#: الصفر هنا يعني: امشِ حتّى نهاية البيانات — أو حتّى يُحسم.
HORIZON = 0
BANDS = ((1.5, 2.0), (2.0, 2.5), (2.5, 3.0), (3.0, 4.0), (4.0, 99.0))


async def _setups_with_z(symbol: str, rows, setup_z: float):
    """إعدادات ٤٠٥ بعتبةٍ مخفوضة — ومعها `|z|` الذي وُلد عنده كلُّ إعداد."""
    import importlib.util, yaml, time  # noqa: E401
    folder = sos._folder(405)
    manifest = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8"))
    config = dict(manifest.get("config") or {})
    config["setup_z"] = setup_z          # ⟵ المُعامِل الوحيد المغيَّر
    ctx = sos._Ctx(config)
    atom = sos._load(folder).Atom()
    await atom.initialize(ctx)
    await atom.start()
    out, seen, base = [], 0, time.time()
    for index, (bid, ask) in enumerate(rows):
        await list(ctx.handlers.get("market.tick.validated", []))[0](
            {"account_id": sos.ACCOUNT, "broker": sos.BROKER, "symbol": symbol,
             "bid": bid, "ask": ask, "price": (bid + ask) / 2.0, "sequence": index,
             "timestamp": base + index * 0.05, "spread": ask - bid})
        while seen < len(ctx.out):
            name, payload = ctx.out[seen]
            seen += 1
            if "setup" not in name or not payload.get("invalidation_price"):
                continue
            if float(payload.get("expires_at") or 0) <= float(payload.get("created_at") or 0):
                continue
            evidence = payload.get("evidence") or {}
            z = evidence.get("z_score")
            if z is None:
                # الوقف = الدخول ∓ انحرافٌ واحد، فـ|z| = |الدخول−المتوسّط|/الوقف
                entry = float(payload["entry_reference"])
                stop = abs(entry - float(payload["invalidation_price"]))
                mean = evidence.get("mean")
                z = (abs(entry - float(mean)) / stop) if (mean and stop) else None
            if z is None:
                continue
            out.append((index, payload, abs(float(z))))
    return out


async def run(symbols, limit: int, windows: int, setup_z: float) -> None:
    for symbol in symbols:
        symbol = symbol.upper()
        cells: dict[tuple[float, float], list[tuple[int, int, float]]] = collections.defaultdict(list)
        for k in range(windows):
            rows, spread = sos._prices(symbol, limit, k * limit)
            if len(rows) < limit // 2:
                continue
            try:
                setups = await _setups_with_z(symbol, rows, setup_z)
            except Exception as exc:  # noqa: BLE001
                print("  %s تعذّر: %s" % (symbol, str(exc)[:70]))
                break
            for index, setup, z in setups:
                entry = float(setup["entry_reference"])
                risk = abs(entry - float(setup["invalidation_price"]))
                reward = abs(float(setup["target_price"]) - entry)
                if risk <= 0:
                    continue
                result = sos._walk(rows, index, setup,
                                   HORIZON or (len(rows) - index))
                if result is None:
                    continue
                for lo, hi in BANDS:
                    if lo <= z < hi:
                        cells[(lo, hi)].append((1 if result else 0, 1, reward / risk))
                        break
        print("\n=== %s · %d نافذة · العتبة المخفوضة %.1f ===" % (symbol, windows, setup_z))
        print("  %-12s %-8s %-7s %-9s %-11s %-9s %s"
              % ("شريحة |z|", "صفقات", "ر:م", "فوز", "متوقَّع صدفةً", "الفرق", "الحكم"))
        for lo, hi in BANDS:
            rows_ = cells.get((lo, hi)) or []
            n = len(rows_)
            if n < 50:
                print("  %-12s %-8d عيّنةٌ صغيرة" % ("%.1f–%.1f" % (lo, hi), n))
                continue
            wins = sum(w for w, _, _ in rows_)
            ratio = st.median(r for _, _, r in rows_)
            predicted = 1.0 / (1.0 + ratio)
            measured = wins / n
            se = (predicted * (1 - predicted) / n) ** 0.5
            sigma = (measured - predicted) / se if se else 0.0
            verdict = ("▲ معلومة" if sigma > 2 else
                       "▼ مقلوبة" if sigma < -2 else "= صدفة")
            print("  %-12s %-8d %7.2f %8.1f%% %10.1f%% %+8.1f σ %s"
                  % ("%.1f–%.1f" % (lo, hi), n, ratio, 100 * measured,
                     100 * predicted, sigma, verdict))


def main() -> None:
    parser = argparse.ArgumentParser(description="معلومة ٤٠٥ بحسب شريحة |z|")
    parser.add_argument("--symbols", nargs="*", default=["US30", "USTEC"])
    parser.add_argument("--limit", type=int, default=25000)
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--setup-z", type=float, default=1.5)
    args = parser.parse_args()
    asyncio.run(run(args.symbols, args.limit, args.windows, args.setup_z))


if __name__ == "__main__":
    main()
