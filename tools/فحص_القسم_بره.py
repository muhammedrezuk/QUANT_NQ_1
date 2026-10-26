# -*- coding: utf-8 -*-
"""فحص القسم خارج المنصّة — أمر المالك ٢٠٢٦-٠٩-١٨: «خود قسم كلّو اختبره برّه».

يُقلع كلّ ذرّة في النطاق على **ناقلٍ معزول** بإعدادها من مانيفستها، ثمّ
يمرّر عليها أحداثًا حقيقيّة الشكل ويسجّل ما تفعله: أتُقلع؟ أتسمع؟ أتنشر؟
أتسقط؟ لا نواة ولا مخزنٌ حيّ — كلّ مسار حالةٍ يُحوَّل إلى مجلّد مؤقّت.

    python tools/فحص_القسم_بره.py                النطاق 500-599
    python tools/فحص_القسم_بره.py 550 599        نطاق بعينه
    python tools/فحص_القسم_بره.py 574 574 -v     ذرّة واحدة بتفصيل

وهو يقيس **السلوك** لا الشكل: ذرّةٌ تُقلع ولا تستجيب لحدثٍ تشترك فيه
تظهر هنا، ولا يظهر ذلك في أيّ عقدٍ ساكن.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

ACCOUNT, BROKER, SYMBOL = "52992818", "Raw Trading Ltd", "XAUUSD"
TICKET = "1944615686"
ENTRY, STOP, TARGET, LOT = 4389.95, 4393.005, 4380.205, 0.29
PRICE = 4386.70


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Bus:
    """ناقلٌ معزول: يلتقط كلّ نشرٍ ولا يمسّ نواةً ولا مخزنًا."""

    def __init__(self, config):
        self.config = config
        self.logger = _Log()
        self.handlers: dict[str, list] = {}
        self.out: list[tuple[str, dict]] = []

    def subscribe(self, name, handler):
        self.handlers.setdefault(str(name), []).append(handler)

    async def publish(self, name, payload):
        self.out.append((str(name), payload if isinstance(payload, dict) else {}))


def _specs_row():
    return {"symbol": SYMBOL, "volume_min": 0.01, "volume_max": 100.0,
            "volume_step": 0.01, "tick_value": 1.0, "tick_size": 0.01,
            "point": 0.01, "digits": 2, "contract_size": 100.0,
            "stops_level": 0, "freeze_level": 0}


def _position():
    return {"account_id": ACCOUNT, "broker": BROKER, "ticket": TICKET,
            "symbol": SYMBOL, "side": "SELL", "volume": LOT,
            "entry_price": ENTRY, "current_price": PRICE, "stop_loss": STOP,
            "take_profit": TARGET, "profit": (ENTRY - PRICE) * LOT * 100.0,
            "magic": 20260801}


#: حمولاتٌ حقيقيّة الشكل — مبنيّةٌ من حمولات النظام لا مخترَعة.
FEED = {
    "platform.account.state": {
        "account_id": ACCOUNT, "broker": BROKER, "equity": 7439.0,
        "balance": 7200.22, "margin_free": 5882.78, "currency": "USD",
        "connected": True, "trade_allowed": True, "expert_allowed": True},
    "platform.terminal_state": {
        "account_id": ACCOUNT, "connected": True, "trade_allowed": True,
        "expert_allowed": True},
    "market.symbol_specs": {
        "account_id": ACCOUNT, "broker": BROKER, "symbols": [_specs_row()],
        "published_at": 0.0},
    "market.ctrader.symbol_specs": {
        "account_id": ACCOUNT, "broker": BROKER, "symbols": [_specs_row()]},
    "feed.mt5.tick": {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "bid": 4386.65, "ask": 4386.75, "price": 4386.70, "spread_pts": 10.0},
    "market.tick.validated": {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "bid": 4386.65, "ask": 4386.75, "price": 4386.70},
    "platform.positions.state": {
        "account_id": ACCOUNT, "broker": BROKER, "positions": [_position()],
        "usable_for_new_exposure": True, "usable_for_protection": True},
    "platform.trade_event": {
        "account_id": ACCOUNT, "broker": BROKER, "event_type": "CLOSED",
        "ticket": TICKET, "symbol": SYMBOL, "side": "SELL", "volume": LOT,
        "entry_price": ENTRY, "exit_price": 4383.91, "profit": 114.76,
        "reason": "SL", "source_row_id": "probe-1", "event_id": "probe-1",
        "request_id": "555-4aea83789011"},
    "SYS_SECOND": {"official_time": 1789756800.0, "pulse_id": "SYS_SECOND|1",
                   "bucket_start": 1789756800.0},
    "SYS_DAY": {"official_time": 1789756800.0, "pulse_id": "SYS_DAY|1789689600",
                "bucket_start": 1789689600.0},
    "decision.gate.passed": {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "decision_side": "sell", "decision_id": "probe:dec", "approved": True,
        "gate_request_id": "probe:dec:req1", "cycle_id": "probe|1"},
    "risk.position_size.state": {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "status": "OK", "approved": True,
        "metadata": {"lot": LOT, "price": ENTRY, "stop_distance": abs(ENTRY - STOP),
                     "sell_stop": STOP, "buy_stop": STOP, "max_trade_loss": 100.0,
                     "risk_amount": 100.0, "tick_value": 1.0, "tick_size": 0.01,
                     "volume_step": 0.01, "volume_min": 0.01, "spread": 0.10,
                     "slippage_reserve": 0.20, "commission_per_lot": 0.0}},
    "risk.take_profit.price": {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "take_profit": TARGET, "computable": True, "reward_multiple": 3.0,
        "stop_price": STOP, "reference_price": ENTRY, "v_net": -LOT},
    "execution.order.legal": {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "request_id": "probe-req", "action": "OPEN", "side": "SELL",
        "volume": LOT, "reference_price": ENTRY, "stop_loss": STOP,
        "take_profit": TARGET, "decision_id": "probe:dec",
        "gate_request_id": "probe:dec:req1", "risk_budget": 100.0,
        "protection_mode": "STOP_TARGET", "origin": "entry-555"},
    "execution.order.requested": {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "request_id": "probe-req", "action": "OPEN", "side": "SELL",
        "volume": LOT, "reference_price": ENTRY, "stop_loss": STOP,
        "take_profit": TARGET, "decision_id": "probe:dec",
        "gate_request_id": "probe:dec:req1", "risk_budget": 100.0},
    "trading.final_decision": {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "request_id": "probe-req", "action": "OPEN", "side": "SELL",
        "volume": LOT, "reference_price": ENTRY, "stop_loss": STOP,
        "take_profit": TARGET, "decision_id": "probe:dec"},
    "risk.structure_stop.state": {
        "account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
        "status": "READY", "stop_price": STOP, "average_entry": ENTRY,
        "v_net": -LOT, "metadata": {"buy_stop": 4385.0, "sell_stop": 4392.0}},
    "risk.margin.validation.completed": {
        "account_id": ACCOUNT, "broker": BROKER, "request_id": "probe-req",
        "approved": True, "required_margin": 120.0, "free_margin": 5882.78},
    "allowed.symbols.state": {
        "account_id": ACCOUNT, "broker": BROKER, "symbols": [SYMBOL],
        "allowed": [SYMBOL]},
    "execution.manage.intent": {
        "account_id": ACCOUNT, "broker": BROKER, "ticket": TICKET,
        "symbol": SYMBOL, "side": "SELL", "action": "MODIFY_SL",
        "stop_loss": ENTRY, "reason": "probe"},
}
#: حمولةٌ عامّة لحدثٍ لا وصف له. تحمل الهويّة الكاملة عمدًا: حمولةٌ ناقصة
#: تجعل كلّ حارسٍ سليم يبدو رافضًا، فيختلط عطبُ الذرّة بعطب الفاحص —
#: وقد وقع ذلك أوّل تشغيل (٥٥٠ أعلن `dropped=7` وكان محقًّا).
GENERIC = {"account_id": ACCOUNT, "broker": BROKER, "symbol": SYMBOL,
           "request_id": "probe-req", "ticket": TICKET,
           "decision_id": "probe:dec", "gate_request_id": "probe:dec:req1",
           "side": "SELL", "volume": LOT, "action": "MODIFY_SL",
           "reference_price": ENTRY, "stop_loss": STOP, "take_profit": TARGET}


def load_atom(folder: Path, alias: str):
    target = folder / "atom.py"
    spec = importlib.util.spec_from_file_location(alias, target)
    module = importlib.util.module_from_spec(spec)
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    spec.loader.exec_module(module)
    return module


def isolated_config(manifest: dict) -> dict:
    config = dict(manifest.get("config") or {})
    scratch = tempfile.mkdtemp(prefix="probe_")
    for key, value in list(config.items()):
        if isinstance(value, str) and any(
                mark in key for mark in ("path", "dir", "file")):
            config[key] = os.path.join(scratch, os.path.basename(str(value)) or "probe.db")
    return config


async def probe(folder: Path, verbose: bool) -> dict:
    number = folder.name.split("_")[0]
    row = {"id": number, "folder": folder.name, "boot": "-", "heard": 0,
           "published": 0, "errors": [], "events": []}
    try:
        manifest = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8"))
    except Exception as exc:
        row["boot"] = "مانيفست:%s" % type(exc).__name__
        return row
    try:
        module = load_atom(folder, "probe_%s" % number)
    except Exception as exc:
        row["boot"] = "استيراد:%s" % type(exc).__name__
        row["errors"].append(traceback.format_exc(limit=2))
        return row
    bus = _Bus(isolated_config(manifest))
    atom = getattr(module, "Atom", None)
    if atom is None:
        row["boot"] = "لا صنف Atom"
        return row
    instance = atom()
    try:
        await instance.initialize(bus)
        await instance.start()
        row["boot"] = "أقلعت"
    except Exception as exc:
        row["boot"] = "إقلاع:%s" % type(exc).__name__
        row["errors"].append(traceback.format_exc(limit=3))
        return row

    # ترتيبٌ مقصود: الحالة قبل الأحداث، فذرّةٌ تنتظر حسابًا أو مواصفات
    # تكون قد استلمتهما قبل أن يصلها ما تحكم عليه.
    order = ["platform.account.state", "platform.terminal_state",
             "market.symbol_specs", "market.ctrader.symbol_specs",
             "allowed.symbols.state", "SYS_SECOND", "SYS_DAY"]
    names = list(bus.handlers)
    ordered = [n for n in order if n in bus.handlers] + \
              [n for n in names if n not in order]
    for name in ordered:
        payload = FEED.get(name, dict(GENERIC))
        for handler in list(bus.handlers.get(name, ())):
            row["heard"] += 1
            before = len(bus.out)
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                row["errors"].append("%s ⟹ %s: %s" % (name, type(exc).__name__, exc))
                continue
            for event, body in bus.out[before:]:
                row["events"].append((name, event, body.get("action"),
                                      body.get("reason") or body.get("status")))
    row["published"] = len(bus.out)
    try:
        health = await instance.health_check()
        row["health"] = getattr(health, "message", "")[:70]
        row["state"] = getattr(getattr(health, "state", None), "name", "?")
    except Exception as exc:
        row["health"] = "صحّة:%s" % type(exc).__name__
        row["state"] = "✗"
        row["errors"].append("health_check ⟹ %s" % traceback.format_exc(limit=2))
    try:
        await instance.stop()
    except Exception:
        pass
    return row


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "-v" in sys.argv
    low = int(args[0]) if args else 500
    high = int(args[1]) if len(args) > 1 else 599
    folders = []
    for section in sorted((ROOT / "atoms").iterdir()):
        if not section.is_dir():
            continue
        for entry in sorted(section.iterdir()):
            head = entry.name.split("_")[0]
            if entry.is_dir() and head.isdigit() and low <= int(head) <= high \
                    and (entry / "atom.py").is_file():
                folders.append(entry)
    print("فحص %d ذرّة في النطاق %d–%d — معزولةً عن المنصّة\n" % (len(folders), low, high))
    print("%-5s %-26s %-12s %-6s %-6s %-6s %s"
          % ("رقم", "المجلّد", "الإقلاع", "سمعت", "نشرت", "أخطاء", "الحالة"))
    print("-" * 92)
    rows = []
    for folder in folders:
        row = await probe(folder, verbose)
        rows.append(row)
        print("%-5s %-26s %-12s %-6d %-6d %-6d %s"
              % (row["id"], row["folder"][:26], row["boot"], row["heard"],
                 row["published"], len(row["errors"]), row.get("state", "-")))
        if verbose:
            for name, event, action, reason in row["events"]:
                print("        %s ⟶ %s  action=%s reason=%s" % (name, event, action, reason))
            for err in row["errors"]:
                print("        ⚠ %s" % str(err).strip().replace("\n", "\n          ")[:400])
            if row.get("health"):
                print("        شارة: %s" % row["health"])

    print()
    failed = [r for r in rows if r["boot"] != "أقلعت"]
    erred = [r for r in rows if r["errors"]]
    silent = [r for r in rows if r["boot"] == "أقلعت" and r["published"] == 0]
    print("╔══ الحصيلة ══")
    print("  أقلعت            : %d من %d" % (len(rows) - len(failed), len(rows)))
    print("  لم تُقلع          : %d   %s" % (len(failed), " ".join(r["id"] for r in failed)))
    print("  رمت استثناءً      : %d   %s" % (len(erred), " ".join(r["id"] for r in erred)))
    print("  أقلعت ولم تنشر   : %d   %s" % (len(silent), " ".join(r["id"] for r in silent)))
    return 1 if failed or erred else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
