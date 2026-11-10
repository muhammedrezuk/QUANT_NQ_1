"""مكنسة العتبات — هل تظهر حافّةُ المحلّل فوق قوّةٍ معيّنة؟

`edge_derivation.py` يسأل: هل لهذا المحلّل حافّة **على كلّ إشاراته**؟ وجوابه
اليوم «لا» على ثلاثة رموز من أربعة. وهذا السؤال ناقص: قد يكون المحلّل صادقًا
حين يتكلّم بقوّة وكاذبًا حين يهمس، فيضيع صدقُه داخل متوسّطٍ يبتلعه همسُه.

فهذه الأداة تقسّم إشاراته إلى شرائح بقوّتها، وتقيس الحافّة **داخل كلّ شريحة**.
والجواب إمّا «فوق القوّة س له حافّة» — فتلك عتبتُه المشتقّة — أو «لا شريحة
تغطّي السبريد» — فلا عتبة تنقذه، والمشكلة في المحلّل لا في معايرته.

⚠️ وحكمٌ سابق يُعاد فحصه: قِيس على ٤٠٤ (٢٠٢٦-٠٩-١١) أنّ ارتفاع القوّة يسوء
بالنتيجة — **لكنّه قِيس بمقياسٍ معطوب**. أُصلح جدول المقياس ٢٠٢٦-٠٩-١٨ (حركة
بتكوين ٣٥٫٥ ⟵ ٦٤٫٧، أي ‎+٩٥٪‎)، فالقوّة نفسها تغيّرت وحكمُها يُعاد.

🔴 **والانحراف يُطرح — وإلّا كانت الأداة ترى الموجة حافّة.** مقيس ٢٠٢٦-٠٩-١٨:
بتكوين ارتفع ٢٧١٬٢٣٥ نقطة داخل العيّنة، وشراءٌ أعمى عند أفق ألفٍ يكسب ٤٬٦٣١
نقطة — بينما أفضلُ شريحةٍ لـ٤٠٦ كسبت ٣٬٣٢٦، أي **دون الشراء الأعمى**. وكانت
الأداة تسمّيها `EDGE`. وعلى داو وناسداك (وقد هبطا) كانت تبخس من يقاوم التيّار.

والخطّ الصحيح ليس الصفر ولا الانحراف الخام، بل **الانحراف مضروبًا في ميل
الشريحة**: من يشتري دائمًا يُقاس على الانحراف كاملًا، ومن يوازن شراءه ببيعه
لا يُقاس عليه شيء. وخطأ الفرق يجمع خطأي الطرفين.

⛔ لا تعدّل شيئًا. تقرأ `market_data.db` قراءةً فقط وتطبع جدولًا.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.contracts.atom import AtomContext  # noqa: E402
from tests.learning_test_support import (  # noqa: E402
    load_atom, manifest_config, validated_tick)

DB = ROOT / "forex_runtime" / "var" / "store" / "market_data.db"
DIRECTIONAL = (404, 405, 406, 407, 408, 409, 410)
# ٢٠٢٦-٠٩-١٨ — أُضيف أفقا ٣٠٠٠ و٦٠٠٠: تقاطعَ طريقان مستقلّان على أنّ
# الإشارة تحتاج ~٢٥ دقيقة لتُعبّر — نافذة ٤٠٥ (٣٠٠٠ تِكّة) وقياس قسم
# البنية (أفق ١٥٠٠ث: حافّة ٤/٤ عند إطار العشر ثوانٍ، وصفرٌ عند خمس دقائق).
# ومن يقيس عند أفقٍ أقصر يلتقط صفرًا من إشارةٍ صادقة.
HORIZONS = (200, 1000, 3000, 6000)
#: أقلّ عيّنةٍ لشريحةٍ يُنطق بحكمها — دونها الوسيط يكذب بثقة (درسٌ مدفوع).
MIN_BUCKET = 150
BUCKETS = 4
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "AUDUSD": 1e-4, "XAUUSD": 1e-2,
       "BTCUSD": 1e-2, "USTEC": 1e-2, "US30": 1e-2, "US500": 1e-2}


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.out = []

    async def publish(self, name, payload):
        self.out.append(payload)

    def subscribe(self, name, handler):
        return None


def _prices(symbol: str, limit: int, offset: int = 0) -> tuple[list[float], float]:
    """نافذةٌ من التِكّات — و`offset` يزيحها إلى الوراء.

    نافذةٌ واحدة لا تُثبت عتبة. قِيس على قسم ٣٥٠-٣٩٩ (٢٠٢٦-٠٩-١٨) أنّ حكم
    `EDGE` على نافذةٍ صار `weak` على أخرى بالحجم نفسه — **الحجم لم يكن
    المشكلة، النافذة كانت**. فلا تُعلَن عتبةٌ حتى تثبت في نافذتين منفصلتين.
    """
    connection = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True, timeout=10)
    try:
        rows = connection.execute(
            "SELECT bid,ask FROM market_data WHERE symbol=? ORDER BY rowid DESC "
            "LIMIT ? OFFSET ?", (symbol, limit, offset)).fetchall()
    finally:
        connection.close()
    rows.reverse()
    mid = [(bid + ask) / 2.0 for bid, ask in rows if bid and ask]
    spreads = [ask - bid for bid, ask in rows if ask and bid and ask > bid]
    return mid, (st.median(spreads) if spreads else 0.0)


async def _feed(atom, tick) -> None:
    """يمرّر تِكّةً إلى الذرّة — عبر `_on_tick` أو عبر نواتها الحيّة.

    محلّلو ١٥٠-١٩٩ لا يملكون `_on_tick`: مزخرِفُهم `live_analyzer` يضع المنطق
    في `self._live_kernel` ويترك الذرّة بلا معالجٍ مباشر. فبلا هذا السطر
    تعمل الأداة على استراتيجيّات ٤٠٠ وحدها — وقد كُتبت لتُقاس بها كلّ ذرّة.
    (أبلغ به قسم ١٥٠-١٩٩ ٢٠٢٦-٠٩-١٨، وتشغيل السكربتات ممنوعٌ عندهم.)
    """
    kernel = getattr(atom, "_live_kernel", None)
    handler = getattr(kernel, "on_tick", None) if kernel is not None else None
    if handler is None:
        handler = atom._on_tick
    await handler(tick)


async def _signals(atom_id: int, prices: list[float], symbol: str):
    """(فهرس التِكّة، الاتّجاه، القوّة) لكلّ إشارة — القوّة المعلَنة لا المسموحة."""
    module = load_atom(atom_id)
    atom = module.Atom()
    bus = _Bus()
    await atom.initialize(AtomContext(
        atom_id, dict(manifest_config(atom_id)), _Log(), bus.publish, bus.subscribe))
    await atom.start()
    out = []
    for index, price in enumerate(prices):
        await _feed(atom, validated_tick(index, price=price, symbol=symbol))
        for card in bus.out:
            if not isinstance(card, dict):
                continue
            value = card.get("declared_direction")
            if value in (None, ""):
                value = card.get("direction")
            try:
                value = float(value)
                strength = float(card.get("strength") or 0.0)
            except (TypeError, ValueError):
                continue
            if value:
                out.append((index, value, strength))
        bus.out.clear()
    return out


def _drift(prices: list[float], horizon: int, pip: float) -> tuple[float, float]:
    """انحراف السوق نفسه عند هذا الأفق — ما يكسبه شراءٌ أعمى، بالنقاط."""
    steps = [(prices[i + horizon] - prices[i]) / pip
             for i in range(0, len(prices) - horizon, 10)]
    if len(steps) < 2:
        return (0.0, 0.0)
    return (st.mean(steps), st.stdev(steps) / (len(steps) ** 0.5))


def _cell(values: list[float]) -> tuple[float, float, int]:
    if len(values) < 2:
        return (0.0, 0.0, len(values))
    mean = st.mean(values)
    se = st.stdev(values) / (len(values) ** 0.5)
    return (mean, se, len(values))


async def run(symbols: list[str], limit: int, out_path: str | None,
              offset: int = 0) -> None:
    report = {"limit": limit, "min_bucket": MIN_BUCKET, "rows": []}
    for symbol in symbols:
        prices, spread = _prices(symbol, limit, offset)
        pip = PIP.get(symbol, 1e-2)
        spread_pips = spread / pip
        print("\n=== %s — %d تِكّة · سبريد %.2f نقطة ===" % (symbol, len(prices), spread_pips) + ("  [إزاحة %d]" % offset if offset else ""))
        print("%-5s %-13s %6s %5s %10s %10s %11s %11s %9s" % (
            "ذرّة", "شريحة القوّة", "عدد", "أفق", "الخام", "خطّ الميل",
            "بعد الضبط", "الحدّ الأدنى", "الحكم"))
        for atom_id in DIRECTIONAL:
            try:
                sigs = await _signals(atom_id, prices, symbol)
            except Exception as exc:  # noqa: BLE001 — محلّلٌ يسقط لا يوقف المسح
                print("%-5d تعذّر: %s" % (atom_id, str(exc)[:50]))
                continue
            if len(sigs) < MIN_BUCKET * 2:
                print("%-5d عيّنة صغيرة (%d إشارة)" % (atom_id, len(sigs)))
                continue
            strengths = sorted(s for _, _, s in sigs)
            edges = [strengths[int(k * len(strengths) / BUCKETS)] for k in range(1, BUCKETS)]
            bands = [(-1e18, edges[0])] + [(edges[i], edges[i + 1]) for i in
                                           range(len(edges) - 1)] + [(edges[-1], 1e18)]
            for lo, hi in bands:
                inside = [(i, d) for i, d, s in sigs if lo <= s < hi]
                if len(inside) < MIN_BUCKET:
                    continue
                # ميلُ الشريحة: إشارةٌ كلّها شراء تكسب الانحراف كاملًا،
                # وإشارةٌ متوازنة لا تكسب منه شيئًا. فالخطّ الذي يُقاس عليه
                # المحلّل هو **الانحراف مضروبًا في ميله**، لا الصفر.
                bias = sum(1.0 if d > 0 else -1.0 for _, d in inside) / len(inside)
                best = None
                for horizon in HORIZONS:
                    fwd = [((prices[i + horizon] - prices[i]) / pip)
                           * (1.0 if d > 0 else -1.0)
                           for i, d in inside if i + horizon < len(prices)]
                    mean, se, n = _cell(fwd)
                    drift, drift_se = _drift(prices, horizon, pip)
                    base = drift * bias
                    adj = mean - base
                    # خطأُ الفرق يجمع خطأي الطرفين — ولا يُنسى خطأ الخطّ.
                    joint = (se ** 2 + (drift_se * abs(bias)) ** 2) ** 0.5
                    lower = adj - 2.0 * joint
                    if best is None or lower > best[3]:
                        best = (horizon, adj, joint, lower, n, mean, base)
                if best is None:
                    continue
                horizon, mean, se, lower, n, raw, base = best
                verdict = "EDGE" if lower > spread_pips else (
                    "NEGATIVE" if mean + 2.0 * se < 0 else "weak")
                label = "%.1f–%.1f" % (max(lo, 0.0), min(hi, 999.9))
                print("%-5d %-13s %6d %5d %10.2f %10.2f %11.2f %11.2f %9s" % (
                    atom_id, label, n, horizon, raw, base, mean, lower, verdict))
                report["rows"].append({"symbol": symbol, "atom": atom_id,
                                       "band": label, "n": n, "horizon": horizon,
                                       "raw": raw, "drift_baseline": base,
                                       "adjusted": mean, "lower": lower,
                                       "spread_pips": spread_pips, "verdict": verdict})
    if out_path:
        Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print("\nكُتب: %s" % out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="مكنسة عتبات القوّة")
    parser.add_argument("--symbols", nargs="*", default=["BTCUSD"])
    parser.add_argument("--limit", type=int, default=60000)
    parser.add_argument("--out", default="")
    parser.add_argument("--offset", type=int, default=0,
                        help="إزاحة النافذة إلى الوراء بالتِكّات")
    args = parser.parse_args()
    asyncio.run(run([s.upper() for s in args.symbols], args.limit,
                    args.out or None, args.offset))


if __name__ == "__main__":
    main()
