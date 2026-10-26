"""أداة اشتقاق الحافّات — بأمر المالك ٢٠٢٦-٠٩-١١: «يشتقّ أرقام من نفسه،
لازم تنبنى أداة اشتقاق وحافّات».

تسأل سؤالًا واحدًا لكل (محلّل × رمز): **هل إشارته تسبق حركةً في اتجاهها
تكفي لتغطية السبريد؟** وتجيب برقمٍ من تِكّات المنصّة الحقيقية، لا بتقدير.

⛔ لا تعدّل شيئًا. تقرأ `market_data.db` للقراءة فقط وتطبع جدولًا.

ثلاث قواعد دُفع ثمنها قبل كتابة هذا الملفّ (٢٠٢٦-٠٩-١١):

١) **العيّنة الصغيرة تكذب بثقة.** أوّل تشغيل على 15,000 تِكّة أعطى 410 و407
   حافّةً على أربعة رموز من أربعة — وهما يتكلّمان أقلّ من 1%، أي ثلاثين
   إشارة. وبـ90,000 تِكّة سقط الحكمان إلى `weak`. لذلك `MIN_SIGNALS`.

٢) **المتوسّط بلا خطأ معياريّ ادّعاء لا قياس.** كل خانة تحمل `±2se`،
   والحكم `EDGE` لا يُمنح إلا إذا تجاوز **الحدّ الأدنى** للثقة السبريدَ —
   لا المتوسّط وحده.

٣) **القوّة ليست دليل صواب.** مقيس على 404: كلّما ارتفعت قوّته ساءت نتيجته
   (قوّة 10-30 ⇒ −1.44 نقطة مقابل −0.00 عند 0-1). فرفع عتبة القوّة كان
   سيزيد الخسارة — الحكم على الحافّة وحدها.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.contracts.atom import AtomContext  # noqa: E402
from tests.learning_test_support import (  # noqa: E402
    load_atom, manifest_config, validated_tick)

DB = ROOT / "forex_runtime" / "var" / "store" / "market_data.db"
DIRECTIONAL = (404, 405, 406, 407, 408, 409, 410)
HORIZONS = (50, 200, 1000)
MIN_SIGNALS = 200
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "AUDUSD": 1e-4,
       "XAUUSD": 1e-2, "BTCUSD": 1e-2, "USTEC": 1e-2,
       "US30": 1e-2, "US500": 1e-2}


class _Bus:
    def __init__(self):
        self.out = []

    async def publish(self, name, payload):
        self.out.append(payload)

    def subscribe(self, name, handler):
        pass


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


async def _signals(atom_id: int, prices: list[float], symbol: str):
    """كل إشارة اتجاهيّة ينشرها المحلّل، مقرونةً بفهرس التِكّة التي أنتجتها."""
    module = load_atom(atom_id)
    atom = module.Atom()
    bus = _Bus()
    await atom.initialize(AtomContext(
        atom_id, dict(manifest_config(atom_id)), _Log(), bus.publish, bus.subscribe))
    await atom.start()
    out = []
    for index, price in enumerate(prices):
        await atom._on_tick(validated_tick(index, price=price, symbol=symbol))
        for card in bus.out:
            if not isinstance(card, dict):
                continue
            # ⛔ حلقة مغلقة كُشفت ٢٠٢٦-٠٩-١١: من أُسكِت يخرج بـ`direction=0`
            # فلا يُنتج إشارة، فلا يُقاس، **فلا يُبرَّأ أبدًا** — حكمٌ أبديّ
            # بلا إعادة محاكمة. مقيس: 404 و406 و408 على BTCUSD أعطت صفر
            # إشارة في إعادة القياس لأنّ جدولًا سابقًا (بمقياس معطوب) كان
            # قد أسكتها. فالقياس يقرأ **الرأي المعلَن** لا الصوت المسموح.
            value = card.get("declared_direction")
            if value in (None, ""):
                value = card.get("direction")
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value:
                out.append((index, value))
        bus.out.clear()
    return out


def _forward(prices, sigs, horizon, pip):
    """العائد **المتّجه** بالنقاط: موجبٌ حين تصدق الإشارة، سالبٌ حين تكذب."""
    return [((prices[i + horizon] - prices[i]) / pip) * (1.0 if d > 0 else -1.0)
            for i, d in sigs if i + horizon < len(prices)]


def _cell(values):
    if len(values) < MIN_SIGNALS:
        return None
    mean = statistics.fmean(values)
    se = statistics.pstdev(values) / (len(values) ** 0.5) if len(values) > 1 else 0.0
    return {"mean": mean, "se": se, "n": len(values), "lower": mean - 2.0 * se}


def _verdict(cells, spread):
    usable = [c for c in cells if c]
    if not usable:
        return "INSUFFICIENT", None
    best = max(usable, key=lambda c: c["mean"])
    if best["lower"] > spread:
        return "EDGE", best          # يغطّي السبريد بثقة
    if best["mean"] > 0:
        return "weak", best          # موجبٌ ولا يُثبته الخطأ المعياريّ
    return "NEGATIVE", best          # يخسر حتّى قبل التكلفة


async def run(symbols, limit, out_path=None):
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    report = {"limit": limit, "min_signals": MIN_SIGNALS, "rows": []}
    print("%-5s %-8s %9s %8s | %-24s %-24s %-24s | %s" % (
        "atom", "symbol", "signals", "spread", "h=50", "h=200", "h=1000", "verdict"))
    for symbol in symbols:
        pip = PIP.get(symbol)
        if pip is None:
            print(f"  (skipping {symbol}: no pip size declared)")
            continue
        rows = db.execute(
            "select bid, ask from market_data where symbol=? order by id desc limit ?",
            (symbol, limit)).fetchall()
        rows.reverse()
        if len(rows) < limit // 2:
            print(f"  (skipping {symbol}: only {len(rows)} ticks)")
            continue
        prices = [(b + a) / 2.0 for b, a in rows]
        spread = statistics.median((a - b) / pip for b, a in rows)
        for atom_id in DIRECTIONAL:
            sigs = await _signals(atom_id, prices, symbol)
            cells = [_cell(_forward(prices, sigs, h, pip)) for h in HORIZONS]
            verdict, best = _verdict(cells, spread)
            text = ["  n/a" if c is None else
                    "%+9.2f ±%-5.2f n=%d" % (c["mean"], c["se"], c["n"]) for c in cells]
            print("%-5d %-8s %9d %8.2f | %-24s %-24s %-24s | %s" % (
                atom_id, symbol, len(sigs), spread, text[0], text[1], text[2], verdict))
            report["rows"].append({
                "atom": atom_id, "symbol": symbol, "signals": len(sigs),
                "spread_pips": spread, "verdict": verdict,
                "best": best, "horizons": dict(zip(map(str, HORIZONS), cells))})
    print("\n=== الوزن المشتقّ — صفرٌ لمن يخسر، ولا وزن لمن لم تكفِ عيّنته ===")
    print("%-5s %-10s %-10s %s" % ("atom", "EDGE", "NEGATIVE", "derived weight per symbol"))
    weights = {}
    for atom_id in DIRECTIONAL:
        mine = [r for r in report["rows"] if r["atom"] == atom_id]
        per = {}
        for r in mine:
            if r["verdict"] == "EDGE":
                per[r["symbol"]] = round(r["best"]["lower"] / r["spread_pips"], 3)
            elif r["verdict"] == "NEGATIVE":
                per[r["symbol"]] = 0.0
            else:
                per[r["symbol"]] = None      # لا حكم: يبقى على وزنه القائم
        weights[str(atom_id)] = per
        print("%-5d %-10d %-10d %s" % (
            atom_id, sum(1 for r in mine if r["verdict"] == "EDGE"),
            sum(1 for r in mine if r["verdict"] == "NEGATIVE"),
            ", ".join(f"{s}:{'-' if v is None else v}" for s, v in per.items())))
    report["derived_weights"] = weights
    if out_path:
        Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"\nwritten: {out_path}")
    return report


def main():
    ap = argparse.ArgumentParser(description="اشتقاق حافّة كل محلّل من تِكّات المنصّة")
    ap.add_argument("--symbols", nargs="*", default=["BTCUSD", "XAUUSD"])
    ap.add_argument("--limit", type=int, default=90000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    asyncio.run(run(args.symbols, args.limit, args.out))


if __name__ == "__main__":
    main()
