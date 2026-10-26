# هل ترسل 574 وقفًا أرخى من القائم عند الوسيط؟ نسخة في الذاكرة، لا حيّ.
import asyncio
import runpy
import sys

scn = runpy.run_path(r"C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\thirds_scenario.py",
                     run_name="not_main")


async def main():
    a, bus = await scn["new"]("USTEC", 0.1, 0.1)
    E, T = 20000.0, 20090.0

    def pos(price, vol, sl):
        return {"positions": [{"account_id": "A", "ticket": 1, "symbol": "USTEC", "side": "BUY", "volume": vol,
                               "entry_price": E, "current_price": price, "stop_loss": sl, "take_profit": T}]}
    await bus.deliver("feed.mt5.tick", {"account_id": "A", "symbol": "USTEC", "bid": 19999.0, "ask": 20000.0})
    # وقفٌ نقله المالك يدويًّا إلى 20010 (فوق الدخول) قبل الهدف الأوّل
    await a._on_positions(pos(20020.0, 3.3, 20010.0))
    await a._on_positions(pos(20030.0, 3.3, 20010.0))
    await a._on_positions(pos(20031.0, 2.2, 20010.0))
    for n, p in bus.published:
        if n == "execution.manage.intent":
            print(p["action"], p.get("volume"), p.get("stop_loss"), p.get("reason"))


asyncio.run(main())
