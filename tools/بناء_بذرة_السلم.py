# -*- coding: utf-8 -*-
"""بذرة سلّم المستويات العميقة للحيّ — من شموع سي‑تريدر المخزَّنة.

ختم المالك ٢٠٢٦-١٠-٠٦ «NQ صلاحية كاملة» على الخطوة الأولى من «أكبر هدف»: كانت البذرة
الحيّة مبنيّةً مرّةً واحدة في ٢٠٢٦-٠٩-٢٨ من تِكّاتٍ قليلة (الذهب: يومان وعشر شموع أربع
ساعات)، فيبحث «أبعد مستوى» في سلّمٍ ضحل ويبقى الهدف قريبًا.

· تُبنى بـ`shared/ladder_seed.build_seed` — المنطق نفسه الذي يبذر به الاختبار التاريخيّ.
· البذرة القديمة تُنسخ إلى `telemetry/أرشيف_البذرة/` قبل الاستبدال — لا حذف.
· تُقرأ عند الإقلاع وحده، وتُدمج تحت لقطة 201 (201 من 1.5.0) — فلا أثر لها قبل إقلاع.

التشغيل (من جذر المشروع):
    vendor\\python\\runtime\\python.exe tools\\بناء_بذرة_السلم.py --dry     عدٌّ بلا كتابة
    vendor\\python\\runtime\\python.exe tools\\بناء_بذرة_السلم.py           يكتب البذرة الحيّة
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.ladder_seed import build_seed, fractal_levels, write_seed  # noqa: E402
from shared.structure_exits import SEED_PATH  # noqa: E402

DB_PATH = ROOT / "forex_runtime" / "var" / "history" / "ctrader_history.db"
SYMBOLS = ("XAUUSD", "BTCUSD", "USTEC", "US30", "US500", "EURUSD", "GBPUSD")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="بذرة سلّم المستويات العميقة من شموع سي‑تريدر")
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--out", default=str(SEED_PATH))
    ap.add_argument("--dry", action="store_true", help="عدٌّ بلا كتابة")
    ap.add_argument("--bars", default="", help="عمقٌ لكلّ الرموز، مثل 15m=139,1h=35,4h=10,1d=2 (الافتراض العميقة)")
    ap.add_argument("--bars-symbol", action="append", default=[],
                    help="عمقُ رمزٍ بعينه: BTCUSD:15m=332,1h=84,4h=21,1d=3 (يتكرّر)")
    args = ap.parse_args(argv)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    def parse(text: str) -> dict[str, int]:
        return {k.strip(): int(v) for k, v in (item.split("=", 1) for item in text.split(",") if "=" in item)}
    from shared.ladder_seed import SEED_BARS
    default = {**SEED_BARS, **parse(args.bars)}
    per_symbol = {}
    for item in args.bars_symbol:
        name, _, spec = item.partition(":")
        per_symbol[name.strip().upper()] = {**default, **parse(spec)}
    # ٢٠٢٦-١٠-٠٦: العمق لكلّ رمز — يُبنى كلّ رمزٍ بعمقه ثمّ تُجمع البذرة واحدة.
    now = time.time()
    seed: dict = {}
    counts: dict = {}
    for symbol in symbols:
        part, part_counts = build_seed(args.db, [symbol], now, bars=per_symbol.get(symbol, default))
        if not seed:
            seed = {**part, "symbols": {}}
        seed["symbols"].update(part["symbols"])
        counts.update(part_counts)
    seed["bars"] = counts
    for symbol in symbols:
        frames = seed["symbols"].get(symbol)
        if not frames:
            print("%s: لا شموع في المخزن — يبقى سلّمه على الحيّ" % symbol)
            continue
        parts = []
        for frame, rows in frames.items():
            highs, lows = fractal_levels(rows)
            first = time.strftime("%Y-%m-%d", time.gmtime(rows[0][0])) if rows else "-"
            parts.append("%s=%d شمعة (قمم %d · قيعان %d · من %s)" % (frame, len(rows), highs, lows, first))
        print("%s: %s" % (symbol, " | ".join(parts)))
    if args.dry:
        return 0
    out = Path(args.out)
    if out.exists():
        archive = out.parent / "أرشيف_البذرة"
        archive.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(out.stat().st_mtime))
        kept = archive / ("%s_%s%s" % (out.stem, stamp, out.suffix))
        shutil.copy2(out, kept)
        print("البذرة السابقة محفوظة: %s" % kept)
    write_seed(out, seed)
    print("كُتبت البذرة: %s (%d رمز)" % (out, len(seed["symbols"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
