# -*- coding: utf-8 -*-
"""تحديث جدول مقياس الرموز من تِكّات المنصّة — لا من رأي أحد.

`forex_runtime/var/telemetry/analysis_scale.json` يحكم شيئين معًا:
  * **مقياس القوّة** لكلّ رمز (`movement_scale` في `shared/strategy_contract.py`)
    — قوّة ١٠٠ تعني الحركة الوسيطة داخل نافذة المئة تِكّة.
  * **أرضيّة الوقف والهدف** (`_floor_frac` في `shared/trade_setup.py`).

وقد كُتب باليد ولم يكن له مولِّد. مقيس ٢٠٢٦-٠٩-١٨: آخر كتابةٍ له ٢٠٢٦-٠٩-١١،
وسعر بتكوين فيه ٧٧٬٠١٦ بينما السوق ٨٠٬٦٩٧، وحركته ٣٥٫٥ بينما المقيس ٦٢٫٩.
فعيارٌ يحكم كلّ صفقة كان بائتًا سبعة أيّام وهو صامت — والصمت أسوأ من الخطأ،
لأنّ الخطأ يُرى.

يقرأ من `market_data.db` قراءةً فقط، ويكتب الجدول بالحركة الوسيطة والسبريد
الوسيط والسعر الأخير. بلا `--write` يعرض الفرق ولا يمسّ شيئًا.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKET_DB = ROOT / "forex_runtime" / "var" / "store" / "market_data.db"
SCALE_PATH = ROOT / "forex_runtime" / "var" / "telemetry" / "analysis_scale.json"

WINDOW = 100
#: أقلّ عيّنةٍ يُكتب بها عيار: دون هذا العدد الوسيطُ يكذب بثقة (درسٌ مدفوع —
#: أوّل اشتقاق حافّة على ثلاثين إشارة أعطى حكمًا انهار عند تسعين ألفًا).
MIN_TICKS = 2000
MAX_TICKS = 40000


def median_range(series: list[float], window: int) -> float:
    if len(series) <= window:
        return 0.0
    step = max(1, window // 2)
    spans = [max(series[i:i + window]) - min(series[i:i + window])
             for i in range(0, len(series) - window, step)]
    return float(st.median(spans)) if spans else 0.0


def measure(symbols: list[str]) -> dict[str, dict[str, float]]:
    if not MARKET_DB.is_file():
        raise SystemExit("لا قاعدة سوق: %s" % MARKET_DB)
    connection = sqlite3.connect("file:%s?mode=ro" % MARKET_DB.as_posix(),
                                 uri=True, timeout=10.0)
    out: dict[str, dict[str, float]] = {}
    try:
        if not symbols:
            symbols = [row[0] for row in connection.execute(
                "SELECT DISTINCT symbol FROM market_data")]
        for symbol in sorted(symbols):
            rows = connection.execute(
                "SELECT bid,ask FROM market_data WHERE symbol=? "
                "ORDER BY rowid DESC LIMIT ?", (symbol, MAX_TICKS)).fetchall()
            if len(rows) < MIN_TICKS:
                print("  تخطّي %s — %d تِكّة فقط (الحدّ %d)"
                      % (symbol, len(rows), MIN_TICKS))
                continue
            rows.reverse()
            mid = [(bid + ask) / 2.0 for bid, ask in rows if bid and ask]
            spreads = [ask - bid for bid, ask in rows if ask and bid and ask > bid]
            if not mid or not spreads:
                continue
            price = mid[-1]
            movement = median_range(mid, WINDOW)
            if not (price > 0 and movement > 0):
                continue
            out[symbol] = {"movement": round(movement, 6),
                           "price": round(price, 6),
                           "frac": round(movement / price, 9),
                           "spread": round(float(st.median(spreads)), 6),
                           "window": WINDOW,
                           "ticks": len(mid)}
    finally:
        connection.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="تحديث جدول مقياس الرموز")
    parser.add_argument("--write", action="store_true", help="اكتب الجدول فعلًا")
    parser.add_argument("--symbol", action="append", default=[],
                        help="رمزٌ بعينه (يتكرّر)؛ الافتراضي كلّ ما في القاعدة")
    args = parser.parse_args()

    fresh = measure([s.upper() for s in args.symbol])
    if not fresh:
        print("لا رمز بعيّنةٍ كافية — لم يُكتب شيء.")
        return 1

    old: dict[str, dict] = {}
    if SCALE_PATH.is_file():
        try:
            old = json.loads(SCALE_PATH.read_text(encoding="utf-8")).get("symbols") or {}
        except (OSError, ValueError):
            old = {}

    print("%-9s %12s %12s %9s %12s" % ("الرمز", "حركة قديمة", "حركة جديدة",
                                       "التغيّر", "سبريد"))
    for symbol, row in fresh.items():
        before = (old.get(symbol) or {}).get("movement")
        ratio = ("%+.0f%%" % (100.0 * (row["movement"] / before - 1.0))
                 if isinstance(before, (int, float)) and before else "جديد")
        print("%-9s %12s %12.4f %9s %12.4f" % (
            symbol, ("%.4f" % before) if before else "—",
            row["movement"], ratio, row["spread"]))

    if not args.write:
        print("\nعرضٌ فقط — أضِف --write للكتابة.")
        return 0

    SCALE_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = {"window_ticks": WINDOW,
            "note": "قوّة 100 = الحركة الوسيطة داخل النافذة",
            "symbols": {**old, **fresh}}
    SCALE_PATH.write_text(json.dumps(body, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print("\nكُتب: %s" % SCALE_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
