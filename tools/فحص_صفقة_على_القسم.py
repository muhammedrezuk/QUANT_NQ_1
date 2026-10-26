# -*- coding: utf-8 -*-
"""صفقةٌ كاملة تمرّ على القسم كلّه — أمر المالك: «فحصلي ياهم كلّهم».

يُقلع كلّ ذرّة في النطاق على ناقلٍ معزول، ثمّ يمرّر عليها **دورة حياة
صفقة** مرحلةً مرحلةً — من الدخول إلى الهدف الثالث — ويسجّل **من يتدخّل
ومتى وبماذا**. فيُقرأ في جدولٍ واحد: أيّ ذرّةٍ لمست الصفقة في أيّ لحظة.

    python tools/فحص_صفقة_على_القسم.py                 500-599 · ذهب بيع
    python tools/فحص_صفقة_على_القسم.py 550 599         نطاق
    python tools/فحص_صفقة_على_القسم.py --شراء          الجهة الأخرى

وهو يكمّل `فحص_القسم_بره.py`: ذاك يسأل «أتُقلع وتستجيب؟» وهذا يسأل
«ماذا تفعل بصفقةٍ حيّة عبر مراحلها؟».
"""
from __future__ import annotations

import asyncio
import importlib.util
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

ACCOUNT, BROKER, SYMBOL, TICKET = "52992818", "Raw Trading Ltd", "XAUUSD", "1944615686"
ENTRY, STOP, TARGET, LOT = 4389.95, 4393.005, 4380.205, 0.29
VPU = 100.0


def stop_for(side: str) -> float:
    """الوقف على جهته: تحت الدخول للشراء وفوقه للبيع.

    ٢٠٢٦-٠٩-١٨ — أوّل تشغيلٍ للشراء أعطى «٥٧٢ لم يتدخّل»، وكاد يُقرأ
    عطبًا في الذرّة. والعلّة أنّ الفاحص كان يمرّر وقف البيع (فوق الدخول)
    في سيناريو شراء — أي مركزًا لا يصنعه أيّ أمرٍ سليم. **المقياس يُفحص
    قبل المقيس**، وهو الدرس نفسه الذي كلّفنا اليوم مرّتين.
    """
    distance = abs(STOP - ENTRY)
    return (ENTRY + distance) if side == "SELL" else (ENTRY - distance)


def build_stages(side: str):
    span = abs(TARGET - ENTRY)
    sign = -1.0 if side == "SELL" else 1.0
    return [
        ("قبل الدخول", ENTRY + sign * span * 0.10),
        ("نصف الطريق لهدف١", ENTRY + sign * span * (1.0 / 6.0)),
        ("هدف١", ENTRY + sign * span / 3.0),
        ("هدف٢", ENTRY + sign * span * 2.0 / 3.0),
        ("هدف٣", ENTRY + sign * span),
        ("ارتدّ إلى الوقف", stop_for(side)),
    ]


class _Log:
    def __getattr__(self, n):
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


SPEC_ROW = {"symbol": SYMBOL, "volume_min": 0.01, "volume_max": 100.0,
            "volume_step": 0.01, "tick_value": 1.0, "tick_size": 0.01,
            "point": 0.01, "digits": 2, "contract_size": 100.0,
            "stops_level": 0, "freeze_level": 0}


def warmup(side: str):
    """ما تحتاجه الذرّات قبل أن تحكم على شيء — حالةٌ لا حدث."""
    return [
        ("platform.account.state", {
            "account_id": ACCOUNT, "broker": BROKER, "equity": 7439.0,
            "balance": 7200.22, "margin_free": 5882.78, "currency": "USD",
            "connected": True, "trade_allowed": True, "expert_allowed": True}),
        ("platform.terminal_state", {
            "account_id": ACCOUNT, "connected": True, "trade_allowed": True,
            "expert_allowed": True}),
        ("market.symbol_specs", {
            "account_id": ACCOUNT, "broker": BROKER, "symbols": [SPEC_ROW]}),
        ("allowed.symbols.state", {
            "account_id": ACCOUNT, "broker": BROKER, "symbols": [SYMBOL],
            "allowed": [SYMBOL]}),
        ("risk.structure_stop.state", {
            "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
            "status": "READY", "stop_price": stop_for(side), "average_entry": ENTRY,
            "v_net": -LOT if side == "SELL" else LOT,
            "metadata": {"buy_stop": ENTRY - 2.0, "sell_stop": ENTRY + 2.0}}),
        ("SYS_SECOND", {"official_time": 1789756800.0,
                        "pulse_id": "SYS_SECOND|1", "bucket_start": 1789756800.0}),
    ]


def tick(price):
    return {"account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
            "bid": price - 0.05, "ask": price + 0.05, "price": price,
            "spread_pts": 10.0}


def positions(price, side, volume):
    profit = ((ENTRY - price) if side == "SELL" else (price - ENTRY)) * volume * VPU
    return {"account_id": ACCOUNT, "broker": BROKER,
            "usable_for_new_exposure": True, "usable_for_protection": True,
            "positions": [{"account_id": ACCOUNT, "broker": BROKER,
                           "ticket": TICKET, "symbol": SYMBOL, "side": side,
                           "volume": round(volume, 2), "entry_price": ENTRY,
                           "current_price": price, "stop_loss": stop_for(side),
                           "take_profit": TARGET, "profit": round(profit, 2),
                           "magic": 20260801}]}


def load(folder: Path, alias: str):
    spec = importlib.util.spec_from_file_location(alias, folder / "atom.py")
    module = importlib.util.module_from_spec(spec)
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    spec.loader.exec_module(module)
    return module


async def run_atom(folder: Path, side: str, stages):
    number = folder.name.split("_")[0]
    try:
        manifest = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8"))
        module = load(folder, "trade_%s" % number)
    except Exception:
        return number, folder.name, None
    config = dict(manifest.get("config") or {})
    scratch = tempfile.mkdtemp(prefix="trade_")
    for key, value in list(config.items()):
        if isinstance(value, str) and any(m in key for m in ("path", "dir", "file")):
            config[key] = os.path.join(scratch, "probe.db")
    bus = _Bus(config)
    atom_class = getattr(module, "Atom", None)
    if atom_class is None:
        return number, folder.name, None
    instance = atom_class()
    try:
        await instance.initialize(bus)
        await instance.start()
    except Exception:
        return number, folder.name, None

    async def feed(name, payload):
        for handler in list(bus.handlers.get(name, ())):
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    for name, payload in warmup(side):
        await feed(name, payload)
    bus.out.clear()

    touches = []
    volume = LOT
    for label, price in stages:
        before = len(bus.out)
        await feed("feed.mt5.tick", tick(price))
        await feed("market.tick.validated", tick(price))
        await feed("platform.positions.state", positions(price, side, volume))
        for event, body in bus.out[before:]:
            action = body.get("action")
            if action in ("CLOSE", "CLOSE_PARTIAL", "MODIFY_SL"):
                touches.append((label, action, body.get("volume"),
                                body.get("stop_loss"), body.get("reason")))
                # يُحاكى أثرُ الإغلاق الجزئيّ على الحجم، وإلّا قرأت المراحل
                # التالية مركزًا لم ينقص وهو ليس ما يراه الوسيط.
                if action == "CLOSE_PARTIAL":
                    closed = body.get("volume")
                    if isinstance(closed, (int, float)):
                        volume = max(0.0, round(volume - float(closed), 2))
                elif action == "CLOSE":
                    volume = 0.0
    try:
        await instance.stop()
    except Exception:
        pass
    return number, folder.name, touches


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    side = "BUY" if "--شراء" in sys.argv else "SELL"
    low = int(args[0]) if args else 500
    high = int(args[1]) if len(args) > 1 else 599
    stages = build_stages(side)

    print("صفقة الفحص: %s %s لوت %s · دخول %.2f · وقف %.2f · هدف %.2f"
          % (SYMBOL, side, LOT, ENTRY, stop_for(side), TARGET))
    for label, price in stages:
        print("   %-20s %.2f" % (label, price))
    print()

    folders = []
    for section in sorted((ROOT / "atoms").iterdir()):
        if not section.is_dir():
            continue
        for entry in sorted(section.iterdir()):
            head = entry.name.split("_")[0]
            if entry.is_dir() and head.isdigit() and low <= int(head) <= high \
                    and (entry / "atom.py").is_file():
                folders.append(entry)

    actors = []
    for folder in folders:
        number, name, touches = await run_atom(folder, side, stages)
        if touches:
            actors.append((number, name, touches))

    print("╔══ من لمس الصفقة ══")
    if not actors:
        print("  لا ذرّة تدخّلت.")
    for number, name, touches in actors:
        print("\n  ── %s ──" % name)
        for label, action, volume, stop, reason in touches:
            bits = []
            if volume is not None:
                bits.append("لوت=%s" % volume)
            if stop is not None:
                bits.append("وقف=%.5f" % float(stop))
            if reason:
                bits.append(str(reason))
            print("     %-20s %-14s %s" % (label, action, " · ".join(bits)))

    print()
    print("╔══ الحصيلة ══")
    print("  ذرّات فُحصت     : %d" % len(folders))
    print("  ذرّات تدخّلت    : %d   %s" % (len(actors), " ".join(a[0] for a in actors)))
    silent = [f.name.split("_")[0] for f in folders
              if f.name.split("_")[0] not in {a[0] for a in actors}]
    print("  لم تلمس الصفقة : %d" % len(silent))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
