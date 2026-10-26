# -*- coding: utf-8 -*-
"""سلسلة البنية بكود الذرّات نفسه (151 · 201–208) على شموع ناسداك التاريخيّة — قياسٌ فقط.

كلّ ذرّة تُحمَّل من atom.py الحيّ بعيار بيانها (ومع تجاوز `lookback` لـ201 وحده)، وتُوصَل بناقلٍ صغير
متزامن بالترتيب نفسه الذي تشترك به حيًّا، ثمّ تُغذّى شموعٌ مغلقة بالحمولة التي يبنيها 103 حرفًا.
تُسجَّل كلّ حقيقة بوقت إغلاق الشمعة التي أطلقتها (لا نظر في المستقبل).

الاستعمال: python run_chain.py --frame 1h --lookback 2 --out out.jsonl [--from 2014-07-21] [--to 2026-10-06]
"""
import argparse
import asyncio
import importlib.util
import json
import pathlib
import sqlite3
import sys
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, str(ROOT))
import yaml  # noqa: E402
from core.contracts.atom import AtomContext  # noqa: E402

ATOMS = {
    151: "قسم 150-199/151_الاتجاه",
    201: "قسم 200-249/201_القمم_والقيعان",
    202: "قسم 200-249/202_الهيكل_الخارجي",
    203: "قسم 200-249/203_الهيكل_الداخلي",
    204: "قسم 200-249/204_كاشف_BOS",
    205: "قسم 200-249/205_كاشف_CHoCH",
    206: "قسم 200-249/206_تحول_الهيكل_MSS",
    207: "قسم 200-249/207_حالة_الاتجاه",
    208: "قسم 200-249/208_طور_السوق",
}
FRAME_SEC = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
FRAME_DB = {"1m": "M1", "5m": "M5", "15m": "M15", "1h": "H1", "4h": "H4", "1d": "D1"}
CAPTURE = {
    "structure.swing.state", "structure.external.state", "structure.internal.state",
    "structure.bos.state", "structure.choch.state", "structure.mss.state",
    "structure.trend.state", "structure.phase.state", "analysis.trend.state",
}


class _Log:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def critical(self, *a, **k): pass
    def exception(self, *a, **k): pass


class Bus:
    def __init__(self, sink):
        self.handlers = {}
        self.sink = sink
        self.now = 0.0

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        if name in CAPTURE:
            self.sink(name, payload, self.now)
        for h in self.handlers.get(name, ()):
            await h(payload)


def load_atom(atom_id, overrides):
    folder = ROOT / "atoms" / ATOMS[atom_id]
    spec = importlib.util.spec_from_file_location(f"_bench_{atom_id}", folder / "atom.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    sys.path.insert(0, str(folder))
    spec.loader.exec_module(mod)
    manifest = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8"))
    cfg = dict(manifest.get("config") or {})
    cfg.update(overrides.get(atom_id, {}))
    return mod.Atom(), cfg


def compact(name, p, t):
    meta = p.get("metadata") or {}
    rec = {"t": t, "e": name.split(".")[-2] if name.startswith("structure") else "trend151",
           "tf": p.get("timeframe"), "sig": p.get("signal"), "score": p.get("score")}
    for k in ("direction", "price", "level", "broken_level", "shift", "trend", "source",
              "swing_time", "prominence", "last_high", "last_low", "phase",
              "break_side", "close", "shift_type", "swing_high", "swing_low"):
        if k in meta:
            rec[k] = meta[k]
    for k in ("direction", "level"):
        if k in p and k not in rec:
            rec[k] = p[k]
    return rec


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True, choices=list(FRAME_SEC))
    ap.add_argument("--lookback", type=int, default=2)
    ap.add_argument("--from", dest="start", default="2014-07-21")
    ap.add_argument("--to", dest="end", default="2026-10-06")
    ap.add_argument("--out", required=True)
    ap.add_argument("--full", action="store_true", help="احفظ الحمولة كاملة (للفحص)")
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc).timestamp()
    t1 = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc).timestamp()
    out = open(a.out, "w", encoding="utf-8")
    counts = {}

    def sink(name, payload, t):
        if not a.full and name in ("structure.trend.state", "structure.phase.state", "analysis.trend.state"):
            return  # أحكامها منزوعة من الحمولة؛ حكم 207 يُقرأ من حالتها أدناه
        if payload.get("signal") in (None, "none") and not a.full:
            return
        counts[name] = counts.get(name, 0) + 1
        rec = dict(payload, t=t) if a.full else compact(name, payload, t)
        if a.full:
            rec["_event"] = name
        out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    bus = Bus(sink)
    overrides = {201: {"lookback": a.lookback}}
    atoms = []
    for atom_id in ATOMS:
        atom, cfg = load_atom(atom_id, overrides)
        ctx = AtomContext(atom_id=atom_id, config=cfg, logger=_Log(),
                          publish=bus.publish, subscribe=bus.subscribe)
        await atom.initialize(ctx)
        await atom.start()
        atoms.append(atom)
    db = sqlite3.connect(f"file:{ROOT / 'forex_runtime/var/history/ctrader_history.db'}?mode=ro", uri=True)
    rows = db.execute(
        "select period_start, open, high, low, close, tick_volume from candles_history "
        "where symbol='USTEC' and period=? and period_start between ? and ? order by period_start",
        (FRAME_DB[a.frame], int(t0), int(t1))).fetchall()
    sec = FRAME_SEC[a.frame]
    # عقد الحقائق (١٠-٠٧) ينزع حكم 207 («صاعد/هابط») من الحمولة؛ فيُقرأ حكمها من حالتها الداخليّة
    # (كودها نفسه) بعد كلّ شمعة، ويُسجَّل عند تغيّره وحده.
    a207 = atoms[list(ATOMS).index(207)]
    last207 = None
    tic = time.time()
    for i, (ps, o, h, l, c, v) in enumerate(rows):
        bus.now = ps + sec  # الحقيقة معروفة عند إغلاق الشمعة
        await bus.publish("market_data.candle_closed", {
            "account_id": "bench", "broker": "bench", "provider": "ctrader_history",
            "symbol": "USTEC", "open": o, "high": h, "low": l, "close": c,
            "volume": v or 0, "tick_count": v or 0, "fabric_gap": False,
            "timeframe": a.frame, "period_start": float(ps), "timestamp": float(ps)})
        st = a207._state.get(("USTEC", a.frame))
        if st is not None:
            cur = (st["official"], st["confirms"], st["has_mss"])
            if cur != last207:
                last207 = cur
                out.write(json.dumps({"t": bus.now, "e": "trend207", "tf": a.frame, "official": cur[0],
                                      "confirms": cur[1], "has_mss": cur[2]}, ensure_ascii=False) + "\n")
        if i and i % 50000 == 0:
            print(f"{a.frame} lb{a.lookback}: {i}/{len(rows)} شمعة · {time.time() - tic:.0f}ث", flush=True)
    out.close()
    print(json.dumps({"frame": a.frame, "lookback": a.lookback, "candles": len(rows),
                      "secs": round(time.time() - tic, 1), "events": counts}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
