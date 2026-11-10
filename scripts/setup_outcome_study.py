# -*- coding: utf-8 -*-
"""أتربح إعداداتُ القسم؟ — بوقفها وهدفها هي.

⛔ **حكم المالك ٢٠٢٦-٠٩-١٩: «بوقفٍ افتراضيّ ممنوع».** وكلُّ قياسٍ سابق في
هذا القسم افترض وقفًا (وسيط الحركة المعاكسة) وهدفًا (ثلاثة أضعافه) —
فكان يقيس **الإشارة** لا **الصفقة**، وحكمُه ساقط. ومنها قولي إنّ ٤٠٦
يبلغ ١:٣ في صفر بالمئة: رقمٌ عن وقفٍ لا وجود له.

الطريقة هنا: تُعاد الاستراتيجيّة على تِكّاتٍ حقيقيّة، ويُلتقط كلُّ إعدادٍ
**تنشره هي** بمستوياته الثلاثة، ثمّ يُمشى بالسعر تِكّةً تِكّة حتّى يبلغ
إبطالَه أو هدفَه — أيّهما أوّلًا.

    التوقّع/ر = p × (الهدف÷الوقف) − (1−p) − كلفة العبور÷الوقف

والقاعدة نفسها: أربع نوافذ منفصلة، وكلُّ نافذةٍ تُعلَن بأرقامها، ولا حكم
من وسيطٍ وحده — النافذة الشاذّة تُرى ولا تُبتلع.

    python scripts/setup_outcome_study.py --atoms 405,406,410
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import importlib.util
import sqlite3
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

DB = ROOT / "forex_runtime" / "var" / "store" / "market_data.db"
SECTION = ROOT / "atoms" / "قسم 400-449"
ACCOUNT, BROKER = "52992818", "Raw Trading Ltd"


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Ctx:
    def __init__(self, config):
        self.config = config
        self.logger = _Log()
        self.handlers: dict[str, list] = {}
        self.out: list[tuple[str, dict]] = []

    def subscribe(self, name, handler):
        self.handlers.setdefault(str(name), []).append(handler)

    async def publish(self, name, payload):
        self.out.append((str(name), payload if isinstance(payload, dict) else {}))


def _prices(symbol: str, limit: int, offset: int):
    connection = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True, timeout=10)
    try:
        rows = connection.execute(
            "SELECT bid,ask FROM market_data WHERE symbol=? ORDER BY rowid DESC "
            "LIMIT ? OFFSET ?", (symbol, limit, offset)).fetchall()
    finally:
        connection.close()
    rows.reverse()
    rows = [(b, a) for b, a in rows if b and a]
    spreads = [a - b for b, a in rows if a > b]
    return rows, (st.median(spreads) if spreads else 0.0)


def _floor(symbol: str, rows, spread: float) -> float:
    """أرضيّة العبور المقيسة للرمز — الحدّ الذي دونه الوقف ضجيج."""
    try:
        from shared import execution_costs as _ec
        price = (rows[len(rows) // 2][0] + rows[len(rows) // 2][1]) / 2.0
        return float(_ec.minimum_stop_distance(symbol, price, spread))
    except Exception:  # noqa: BLE001
        return 0.0


def _folder(atom_id: int) -> Path:
    for path in sorted(SECTION.iterdir()):
        if path.is_dir() and path.name.startswith(str(atom_id)):
            return path
    raise FileNotFoundError(str(atom_id))


def _load(folder: Path):
    spec = importlib.util.spec_from_file_location("so_%s" % folder.name[:3],
                                                  folder / "atom.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _setups(atom_id: int, rows, symbol: str):
    """(فهرس التِكّة، الإعداد) لكلّ إعدادٍ نشرته الذرّة نفسها."""
    folder = _folder(atom_id)
    manifest = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8"))
    ctx = _Ctx(dict(manifest.get("config") or {}))
    atom = _load(folder).Atom()
    await atom.initialize(ctx)
    await atom.start()
    out = []
    seen = 0
    # ⛔ طابعٌ زمنيّ ثابتٌ في الماضي يجعل `StrategyRuntime` يرفض التِكّة
    #    فلا يخرج إعدادٌ قطّ — والأداة تقول «لا حافّة» وهي لم تُشغّل شيئًا.
    base = time.time()
    for index, (bid, ask) in enumerate(rows):
        payload = {"account_id": ACCOUNT, "broker": BROKER, "symbol": symbol,
                   "bid": bid, "ask": ask, "price": (bid + ask) / 2.0,
                   "sequence": index, "timestamp": base + index * 0.05,
                   "spread": ask - bid}
        for handler in ctx.handlers.get("market.tick.validated", []):
            await handler(dict(payload))
        while seen < len(ctx.out):
            name, setup = ctx.out[seen]
            seen += 1
            if "setup" not in name or not setup.get("invalidation_price"):
                continue
            created = float(setup.get("created_at") or 0.0)
            expires = float(setup.get("expires_at") or 0.0)
            # الإعدادُ المسحوب (يُنشَر منتهيَ الأجل) ليس دخولًا — يُستثنى.
            if expires <= created:
                continue
            out.append((index, setup))
    return out


def _walk(rows, index: int, setup: dict, horizon: int):
    """أيّهما أوّلًا — الإبطال أم الهدف؟ `None` إن لم يبلغ أيًّا منهما.

    والعبور يُقاس على السعر القابل للتنفيذ لا على الوسط: البيع يُغلق على
    `ask` ويُجنى على `bid`، والعكس للشراء. وهذا يجعل السبريد يُدفع مرّتين
    كما في الحقيقة، لا مرّةً مخفَّفة.
    """
    entry = float(setup["entry_reference"])
    stop = float(setup["invalidation_price"])
    target = float(setup["target_price"])
    buy = str(setup.get("side")).lower() == "buy"
    for bid, ask in rows[index + 1:index + 1 + horizon]:
        if buy:
            if bid <= stop:
                return False
            if bid >= target:
                return True
        else:
            if ask >= stop:
                return False
            if ask <= target:
                return True
    return None


async def run(symbol: str, limit: int, windows: int, horizon: int,
              atoms: tuple[int, ...]) -> None:
    print("=== %s · %d تِكّة × %d نوافذ · أفق %d · وقفٌ حقيقيّ ==="
          % (symbol, limit, windows, horizon))
    tally: dict[int, list[dict]] = collections.defaultdict(list)
    buckets: dict[tuple[int, int], dict] = collections.defaultdict(dict)
    for k in range(windows):
        rows, spread = _prices(symbol, limit, k * limit)
        if len(rows) < limit // 2:
            continue
        for atom_id in atoms:
            try:
                setups = await _setups(atom_id, rows, symbol)
            except Exception as exc:  # noqa: BLE001
                print("  %d تعذّر: %s" % (atom_id, str(exc)[:60]))
                continue
            wins = losses = open_ended = 0
            ratios, stops = [], []
            # ⚖️ الوقف مقيسًا بأرضيّة العبور — السؤال: **متى يخرج الوقف من
            #    الضجيج؟** لا يُوسَّع وقفٌ (حكم المالك) بل تُنتقى الأفكار
            #    التي وُلد إبطالُها بعيدًا بما يكفي أصلًا.
            floor = _floor(symbol, rows, spread)
            for index, setup in setups:
                entry = float(setup["entry_reference"])
                risk = abs(entry - float(setup["invalidation_price"]))
                reward = abs(float(setup["target_price"]) - entry)
                if risk <= 0:
                    continue
                result = _walk(rows, index, setup, horizon)
                if result is None:
                    open_ended += 1
                    continue
                stops.append(risk)
                ratios.append(reward / risk)
                wins += 1 if result else 0
                losses += 0 if result else 1
                if floor > 0:
                    band = min(5, int(risk / floor))
                    cell = buckets[(atom_id, band)].setdefault(
                        k, {"w": 0, "l": 0, "rr": []})
                    cell["w" if result else "l"] += 1
                    cell["rr"].append(reward / risk)
            settled = wins + losses
            tally[atom_id].append({
                "window": k, "n": len(setups), "settled": settled,
                "wins": wins, "open": open_ended,
                "rr": st.median(ratios) if ratios else 0.0,
                "stop": st.median(stops) if stops else 0.0,
                "spread": spread, "floor": floor})
        print("  إزاحة %d ✓" % (k * limit))
    print("\n  %-5s %-7s %-8s %-7s %-7s %-6s %-10s %-8s %-9s %s"
          % ("ذرّة", "نافذة", "إعدادات", "حُسمت", "معلّقة", "رابحة",
             "نسبة الفوز", "ر:م", "الوقف", "التوقّع/ر"))
    for atom_id in atoms:
        cells = tally.get(atom_id) or []
        if not cells:
            print("  %-5d لا إعداد" % atom_id)
            continue
        expectancies = []
        for row in cells:
            if not row["settled"]:
                print("  %-5d %-7d %-8d %-7d %-7d  — لم يُحسم شيء"
                      % (atom_id, row["window"], row["n"], 0, row["open"]))
                continue
            p = row["wins"] / row["settled"]
            cost = (2.0 * row["spread"] / row["stop"]) if row["stop"] else 0.0
            expectancy = p * row["rr"] - (1.0 - p) - cost
            expectancies.append(expectancy)
            print("  %-5d %-7d %-8d %-7d %-7d %-6d %9.1f%% %8.2f %9.2f %+9.3f"
                  % (atom_id, row["window"], row["n"], row["settled"],
                     row["open"], row["wins"], 100 * p, row["rr"],
                     row["stop"], expectancy))
        if not expectancies:
            print("  %-5s ⟹ لا حكم — لا إعداد حُسم\n" % atom_id)
            continue
        need = max(2, (len(expectancies) * 2 + 2) // 3)
        good = sum(1 for e in expectancies if e > 0)
        print("  %-5s ⟹ التوقّع موجبٌ في %d من %d · الوسيط %+.3f ر  %s\n"
              % (atom_id, good, len(expectancies), st.median(expectancies),
                 "✅ حافّة" if good >= need else "❌ لا"))
    _report_buckets(buckets, windows, atoms)


def _report_buckets(buckets: dict, windows: int, atoms) -> None:
    print()
    print("=== الوقف بمضاعفات أرضيّة العبور — أين يبدأ الربح؟ ===")
    print("  %-5s %-12s %-8s %-8s %-9s %-8s %s"
          % ("ذرّة", "الشريحة", "حُسمت", "رابحة", "نسبة الفوز", "ر:م", "التوقّع/ر"))
    need = max(2, (windows * 2 + 2) // 3)
    for atom_id in atoms:
        printed = False
        for band in range(6):
            cells = buckets.get((atom_id, band))
            if not cells:
                continue
            good = settled = wins = 0
            rrs, exps = [], []
            for cell in cells.values():
                n = cell["w"] + cell["l"]
                if n < 15:
                    continue
                p = cell["w"] / n
                rr = st.median(cell["rr"])
                expectancy = p * rr - (1.0 - p)
                exps.append(expectancy)
                rrs.append(rr)
                settled += n
                wins += cell["w"]
                good += 1 if expectancy > 0 else 0
            if not exps:
                continue
            printed = True
            label = ("%d–%d×" % (band, band + 1)) if band < 5 else "≥5×"
            print("  %-5d %-12s %-8d %-8d %8.1f%% %8.2f %+9.3f   %s"
                  % (atom_id, label, settled, wins, 100 * wins / settled,
                     st.median(rrs), st.median(exps),
                     ("✅ %d/%d" % (good, len(exps))) if good >= min(need, len(exps))
                     and len(exps) >= need else "%d/%d" % (good, len(exps))))
        if not printed:
            print("  %-5d لا شريحة بعيّنةٍ كافية" % atom_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="مصير إعدادات القسم الحقيقيّة")
    parser.add_argument("--symbols", nargs="*", default=["BTCUSD"])
    parser.add_argument("--limit", type=int, default=40000)
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--horizon", type=int, default=6000)
    parser.add_argument("--atoms", default="405,406,410")
    args = parser.parse_args()
    atoms = tuple(int(x) for x in args.atoms.split(",") if x.strip())
    for symbol in args.symbols:
        asyncio.run(run(symbol.upper(), args.limit, args.windows,
                        args.horizon, atoms))


if __name__ == "__main__":
    main()
