"""فحص قراءة فقط: ماذا تفعل 555 حين تصل حمولة حجمٍ بلا سعر وقرارٌ بمستوياته؟"""
import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\NQ\QUANT_NQ")
FOLDER = next((ROOT / "atoms" / "قسم 550-599").glob("555_*"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FOLDER))
spec = importlib.util.spec_from_file_location("probe555", FOLDER / "atom.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
from core.contracts.atom import AtomContext

events = []


async def publish(name, payload=None):
    events.append((name, payload))


async def main():
    atom = mod.Atom()
    await atom.initialize(AtomContext(atom_id=555, config={
        "size_stale_after_s": 30.0, "target_stale_after_s": 30.0, "max_open_per_symbol": 0,
        "inflight_ttl_s": 90.0, "min_reward_multiple": 3.0}, logger=None, publish=publish,
        subscribe=lambda *a: None, subscribe_all=lambda h: None))
    await atom.start()
    await atom._on_account({"account_id": "ACC", "broker": "BR"})
    await atom._on_positions({"positions": []})
    await atom._on_size({"account_id": "ACC", "broker": "BR", "symbol": "BTCUSD",
                         "metadata": {"lot": 0.3, "tick_value": 0.01, "tick_size": 0.01,
                                      "max_trade_loss": 100.0, "risk_amount": 100.0}})
    try:
        await atom._on_decision({"account_id": "ACC", "broker": "BR", "symbol": "BTCUSD",
                                 "decision_side": "buy", "decision_id": "D1",
                                 "invalidation_price": 99.0, "target_price": 110.0})
        print("no exception; events:", events)
    except Exception as exc:  # noqa
        print("EXCEPTION:", type(exc).__name__, exc)
    print("seen", atom._seen, "blocked", atom._blocked, "emitted", atom._emitted,
          "last_reason", atom._last_reason)


asyncio.run(main())
