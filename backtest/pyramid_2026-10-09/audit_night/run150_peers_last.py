# -*- coding: utf-8 -*-
"""محلّلو القسم 150–199 بكود الذرّات نفسه على شموع ناسداك التاريخيّة — قياسٌ فقط.

كلّ ذرّة تُحمَّل من atom.py الحيّ بعيار بيانها (مع تجاوزٍ اختياريّ لمفتاح نافذة واحد)، وتُغذّى شموعًا مغلقة
بالحمولة التي يبنيها 103 حرفًا على إطارٍ واحد، وتُسجَّل حقائقها الرقميّة بوقت إغلاق الشمعة (لا نظر في المستقبل).
الساعة (time.time) مثبّتةٌ على زمن الشمعة كي لا تحكم الذرّة بالتقادم على تاريخٍ قديم.

الاستعمال: python run150.py --atom 151 --frame 1h --out out.jsonl [--set ema_slow=50] [--from 2014-07-21]
"""
import argparse
import asyncio
import importlib.util
import json
import pathlib
import sqlite3
import sys
import time as _time
from datetime import datetime, timezone

ROOT = pathlib.Path(r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, str(ROOT))
import yaml  # noqa: E402

_NOW = [0.0]
_real_time = _time.time
_time.time = lambda: _NOW[0] or _real_time()  # ساعة الشمعة
from core.contracts.atom import AtomContext  # noqa: E402

FOLDERS = {p.name[:3]: p for p in (ROOT / "atoms" / "قسم 150-199").iterdir() if p.is_dir() and p.name[:3].isdigit()}
FRAME_SEC = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
FRAME_DB = {"1m": "M1", "5m": "M5", "15m": "M15", "1h": "H1", "4h": "H4", "1d": "D1"}
PEERS = ("US500", "US30", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")


class _Log:
    def __getattr__(self, _):
        return lambda *a, **k: None


def flat(prefix, obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            flat(f"{prefix}{k}.", v, out)
    elif isinstance(obj, bool):
        out[prefix[:-1]] = int(obj)
    elif isinstance(obj, (int, float)):
        out[prefix[:-1]] = obj
    elif isinstance(obj, str) and len(obj) <= 24:
        out[prefix[:-1]] = obj


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--atom", required=True)
    ap.add_argument("--frame", required=True, choices=list(FRAME_SEC))
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--from", dest="start", default="2014-07-21")
    ap.add_argument("--to", dest="end", default="2026-10-06")
    ap.add_argument("--peers", action="store_true", help="غذِّ رموز الأقران أيضًا (160 · 161)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()
    folder = FOLDERS[a.atom]
    spec = importlib.util.spec_from_file_location(f"_b{a.atom}", folder / "atom.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    sys.path.insert(0, str(folder))
    spec.loader.exec_module(mod)
    cfg = dict((yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8")) or {}).get("config") or {})
    for kv in a.set:
        k, v = kv.split("=", 1)
        cfg[k] = type(cfg.get(k, 0.0))(float(v)) if k in cfg and not isinstance(cfg[k], str) else v
    out = open(a.out, "w", encoding="utf-8")
    n_out = [0]

    async def publish(name, payload):
        if not name.startswith("analysis.") or name.endswith("setting.changed"):
            return
        if payload.get("symbol") != "USTEC" or payload.get("timeframe") not in (None, a.frame):
            return
        if a.full:
            rec = dict(payload, _event=name, t=_NOW[0])
        else:
            rec = {"t": _NOW[0], "status": payload.get("status")}
            flat("m.", payload.get("metadata") or {}, rec)
            for k in ("value", "values", "facts"):
                if k in payload:
                    flat(k + ".", payload[k], rec)
        out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        n_out[0] += 1

    handlers = {}
    ctx = AtomContext(atom_id=int(a.atom), config=cfg, logger=_Log(), publish=publish,
                      subscribe=lambda n, h: handlers.setdefault(n, []).append(h))
    atom = mod.Atom()
    await atom.initialize(ctx)
    await atom.start()
    t0 = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc).timestamp()
    t1 = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc).timestamp()
    db = sqlite3.connect(f"file:{ROOT / 'forex_runtime/var/history/ctrader_history.db'}?mode=ro", uri=True)
    syms = ("USTEC",) + (PEERS if a.peers else ())
    rows = []
    for s in syms:
        rows += [(ps, s, o, h, l, c, v) for ps, o, h, l, c, v in db.execute(
            "select period_start, open, high, low, close, tick_volume from candles_history "
            "where symbol=? and period=? and period_start between ? and ? order by period_start",
            (s, FRAME_DB[a.frame], int(t0), int(t1)))]
    # تدقيق: الأقران أوّلًا ثمّ الناسداك — كي يُرتَّب الناسداك على عوائد أقرانه للشمعة نفسها لا السابقة
    rows.sort(key=lambda r: (r[0], r[1] == "USTEC"))
    sec = FRAME_SEC[a.frame]
    tic = _real_time()
    hs = handlers.get("market_data.candle_closed", [])
    for ps, s, o, h, l, c, v in rows:
        _NOW[0] = ps + sec
        payload = {"account_id": "bench", "broker": "bench", "provider": "ctrader_history",
                   "symbol": s, "open": o, "high": h, "low": l, "close": c,
                   "volume": v or 0, "tick_count": v or 0, "fabric_gap": False,
                   "timeframe": a.frame, "period_start": float(ps), "timestamp": float(ps)}
        for hd in hs:
            await hd(payload)
    out.close()
    print(json.dumps({"atom": a.atom, "frame": a.frame, "set": a.set, "candles": len(rows),
                      "facts": n_out[0], "secs": round(_real_time() - tic, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
