# -*- coding: utf-8 -*-
"""ماذا تنشر وحدات الإحصاء فعلًا — تِكّاتٌ حقيقيّة على ناقلٍ معزول.

البطاقة أظهرت السبعةَ عشرَ كلَّها `NOT_READY`. هذا يقرأ الحمولة المنشورة
نفسها بعد العقد الموحّد، فيُرى **أيُّ حقلٍ** يحجب الجاهزيّة — لا يُستنتج.

    python scripts/stats_probe.py --symbol BTCUSD --ticks 3000
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

ACCOUNT, BROKER = "52992818", "Raw Trading Ltd"
DB = ROOT / "forex_runtime" / "var" / "store" / "market_data.db"
SECTION = ROOT / "atoms" / "قسم 300-349"


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self, config):
        self.config = config
        self.logger = _Log()
        self.handlers: dict[str, list] = {}
        self.out: list[tuple[str, dict]] = []

    def subscribe(self, name, handler):
        self.handlers.setdefault(str(name), []).append(handler)

    async def publish(self, name, payload):
        self.out.append((str(name), payload if isinstance(payload, dict) else {}))


def _ticks(symbol: str, limit: int):
    connection = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True, timeout=10)
    try:
        rows = connection.execute(
            "SELECT bid,ask FROM market_data WHERE symbol=? ORDER BY rowid DESC LIMIT ?",
            (symbol, limit)).fetchall()
    finally:
        connection.close()
    rows.reverse()
    return [(b, a) for b, a in rows if b and a]


def _load(folder: Path):
    spec = importlib.util.spec_from_file_location("probe_%s" % folder.name.split("_")[0],
                                                  folder / "atom.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--ticks", type=int, default=3000)
    args = parser.parse_args()

    folders = sorted(p for p in SECTION.iterdir()
                     if p.is_dir() and p.name[:3].isdigit() and p.name[:3] != "300")
    units = []
    for folder in folders:
        manifest = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8"))
        config = dict(manifest.get("config") or {})
        scratch = tempfile.mkdtemp(prefix="stats_")
        for key, value in list(config.items()):
            if isinstance(value, str) and any(m in key for m in ("path", "dir", "file")):
                config[key] = str(Path(scratch) / (Path(str(value)).name or "p.db"))
        module = _load(folder)
        bus = _Bus(config)
        atom = module.Atom()
        await atom.initialize(bus)
        await atom.start()
        units.append((folder.name, atom, bus))

    rows = _ticks(args.symbol.upper(), args.ticks)
    print("تِكّات: %d" % len(rows))
    for index, (bid, ask) in enumerate(rows):
        payload = {"account_id": ACCOUNT, "broker": BROKER, "symbol": args.symbol.upper(),
                   "bid": bid, "ask": ask, "price": (bid + ask) / 2.0,
                   "sequence": index, "timestamp": 1789800000.0 + index,
                   "spread": ask - bid}
        for _, _, bus in units:
            for handlers in bus.handlers.values():
                pass
        for _, _, bus in units:
            for handler in bus.handlers.get("market.tick.validated", []):
                await handler(dict(payload))

    print("\n%-26s %-9s %-11s %-9s %-7s %s"
          % ("الوحدة", "نشرت", "الحالة", "اتّجاه", "عمق", "مجهول"))
    latest: dict[str, dict] = {}
    for name, _, bus in units:
        if not bus.out:
            print("%-26s %-9d %s" % (name[:26], 0, "— لا تنشر على التِكّة"))
            continue
        event, payload = bus.out[-1]
        unified = payload.get("unified") or {}
        unknown = [u for u in (unified.get("unknown_fields") or [])]
        key = event.replace("stats.", "").replace(".state", "")
        latest[key] = payload
        print("%-26s %-9d %-11s %-9s %-7s %s"
              % (name[:26], len(bus.out), unified.get("state"),
                 ("—" if "direction" in unknown else "%.1f" % unified.get("direction", 0.0)),
                 ("—" if "current_depth" in unknown
                  else "%.0f/%.0f" % (unified.get("current_depth", 0.0),
                                      unified.get("required_depth", 0.0))),
                 ",".join(unknown)))

    from shared.section_live import required_state, unit_opinion  # noqa: E402
    state, missing = required_state("300", latest)
    print("\n=== بطاقة القسم ===")
    print("الحالة: %s   الناقص: %s" % (state, missing or "—"))
    print("الرأي : %s" % unit_opinion(latest))


if __name__ == "__main__":
    asyncio.run(main())
