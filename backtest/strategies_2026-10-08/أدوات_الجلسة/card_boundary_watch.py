# -*- coding: utf-8 -*-
"""قياسٌ حيّ (قراءة فقط): بطاقة 414 عند حدود الساعة والأربع ساعات وبداية نافذة نيويورك —
هل تُقيَّم شمعة الخمس دقائق بحقيقة الإطار الأكبر الجديدة أم القديمة؟ وهل النافذة من وقت الشمعة؟"""
import asyncio
import json
import sys
import time
from datetime import datetime, timezone

import websockets

URL = "ws://127.0.0.1:8010/ws/events"
UNTIL = time.time() + float(sys.argv[1]) if len(sys.argv) > 1 else time.time() + 3600
OUT = sys.argv[2] if len(sys.argv) > 2 else "card_boundary_watch.jsonl"


def loc(ts):
    return datetime.fromtimestamp(float(ts) + 3 * 3600, timezone.utc).strftime("%H:%M:%S")


async def main():
    async with websockets.connect(URL, subprotocols=["quant-nq"], max_size=None) as ws:
        print("متّصل", flush=True)
        with open(OUT, "a", encoding="utf-8") as fh:
            while time.time() < UNTIL:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    continue
                msg = json.loads(raw)
                if msg.get("type") != "event":
                    continue
                name, p = msg.get("name"), msg.get("payload") or {}
                if name == "strategy.card.state" and str(p.get("symbol", "")).upper() == "USTEC":
                    f = p.get("facts") or {}
                    t1, t4 = f.get("151_trend_1h") or {}, f.get("151_trend_4h") or {}
                    row = {"recv": loc(time.time()), "at": loc(p.get("at", 0)), "status": p.get("status"),
                           "window": p.get("window"), "close": p.get("close"),
                           "t1h": [t1.get("close"), t1.get("ema_slow_value"), t1.get("age_s")],
                           "t4h": [t4.get("close"), t4.get("ema_slow_value"), t4.get("age_s")],
                           "win412": (f.get("412_window") or {}).get("window")}
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n"); fh.flush()
                    print(json.dumps(row, ensure_ascii=False), flush=True)


asyncio.run(main())
