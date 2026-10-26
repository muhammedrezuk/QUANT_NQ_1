# -*- coding: utf-8 -*-
"""معايرة الذرّة 151 (الاتّجاه) وحدها — قياسٌ فقط، بكودها الحيّ نفسه (ختم المالك «NQ» ٢٠٢٦-١٠-٠٩).

ما يخرج من الذرّة حيًّا اليوم (مقيسٌ بتشغيلها هنا، عقد الحقائق منذ ١٠-٠٧):
  على الشمعة المغلقة — metadata: ema_distance (٪ السريع عن البطيء) · ema_slope (٪ ميل البطيء لكلّ شمعة) ·
    price_position (الإغلاق من السريع) · close · ema_fast_value · ema_slow_value — ومعها pattern (حكم الذرّة
    القديم «up/down/sideways»، باقٍ في metadata لأنّ العقد لا ينزع إلّا metadata.direction).
  على التِّكّ — لا حقيقة اتّجاهيّة (يبقى integrity · data_completeness) ⟸ لا شيء يُعاير.
فالمعايرة على حقائق الشمعة، وعياراتها ثلاثة مفاتيح من البيان تغيّر الحقيقة: ema_fast · ema_slow · slope_lookback
(min_candles تسخينٌ وحده؛ عتبات التسطّح والقوّة لا تمسّ إلّا pattern — يُقاس pattern بالعيار الحيّ).

الشموع من مخزن سي‑تريدر (قراءة فقط) للناسداك، بحجمٍ صفر كما يبنيها 103 حيًّا. الساعة على زمن الشمعة.
مخزن المعايرة محوَّل إلى ملفّ في المسوّدة (لا يُفتح مخزن الحيّ). تسخين من 2017، والحكم من 2018.

الناتج: npz لكلّ (إطار × عيار): t (زمن الإغلاق) · close · dist · slope · pos · above_slow · pattern.
الاستعمال:  python calib151.py --frame 1h [--out DIR]
"""
import argparse
import asyncio
import importlib.util
import json
import os
import pathlib
import sqlite3
import sys
import time as _time
from datetime import datetime, timezone

import numpy as np

ROOT = pathlib.Path(r"C:\Users\NQ\QUANT_NQ")
SCRATCH = pathlib.Path(os.environ.get(
    "CALIB_SCRATCH", r"C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib151"))
SCRATCH.mkdir(parents=True, exist_ok=True)
os.environ["QUANT_ANALYSIS_SETTINGS_DB"] = str(SCRATCH / "settings_bench.db")   # لا يُلمس مخزن الحيّ
sys.path.insert(0, str(ROOT))
import yaml  # noqa: E402

_NOW = [0.0]
_real_time = _time.time
_time.time = lambda: _NOW[0] or _real_time()
from core.contracts.atom import AtomContext  # noqa: E402
import shared.section_contract as _SC  # noqa: E402

# حكم الذرّة (signal) يُنزع بعقد الحقائق قبل النشر، وكان لا يصل الأداة إلّا عبر التوأم (metadata.pattern).
# في الأداة وحدها: يُنسخ قبل النزع إلى metadata.bench_signal — فيُقاس لكلّ عيار ويُطفأ التوأم البطيء.
_orig_stamp = _SC.stamp_section


def _bench_stamp(payload, **kw):
    if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) and "signal" in payload:
        payload = dict(payload, metadata=dict(payload["metadata"], bench_signal=payload["signal"]))
    return _orig_stamp(payload, **kw)


_SC.stamp_section = _bench_stamp

FOLDER = ROOT / "atoms" / "قسم 150-199" / "151_الاتجاه"
FRAME_SEC = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
FRAME_DB = {"5m": "M5", "15m": "M15", "1h": "H1", "4h": "H4", "1d": "D1"}
WARM_FROM = "2017-01-01"
END = "2026-10-06"
SIG = {"up": 1, "down": -1, "sideways": 0}
POS = {"above_fast": 1, "below_fast": -1, "at_fast": 0}
#: الشبكة: أزواج المتوسّطين (الحيّ 10/20) × ميل البطيء (الحيّ 3).
EMA_PAIRS = [(5, 20), (10, 20), (10, 50), (20, 50), (5, 50), (20, 100), (10, 100), (50, 200)]
SLOPES = [1, 3, 5, 10]


class _Log:
    def __getattr__(self, _):
        return lambda *a, **k: None


def candles(frame):
    t0 = datetime.fromisoformat(WARM_FROM).replace(tzinfo=timezone.utc).timestamp()
    t1 = datetime.fromisoformat(END).replace(tzinfo=timezone.utc).timestamp()
    db = sqlite3.connect(f"file:{ROOT / 'forex_runtime/var/history/ctrader_history.db'}?mode=ro", uri=True)
    rows = db.execute("select period_start, open, high, low, close from candles_history where symbol='USTEC' "
                      "and period=? and period_start between ? and ? order by period_start",
                      (FRAME_DB[frame], int(t0), int(t1))).fetchall()
    return np.array(rows, dtype=np.float64)


def load_atom_module():
    spec = importlib.util.spec_from_file_location("_calib151", FOLDER / "atom.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    sys.path.insert(0, str(FOLDER))
    spec.loader.exec_module(mod)
    return mod


def payload_of(row, frame):
    ps, o, h, l, c = row
    return {"account_id": "bench", "broker": "bench", "provider": "ctrader_history", "symbol": "USTEC",
            "open": o, "high": h, "low": l, "close": c, "volume": 0.0, "tick_count": 0,
            "fabric_gap": False, "timeframe": frame, "period_start": float(ps), "timestamp": float(ps)}


#: توسيعٌ بطلب المالك (١٠-٠٩ مساءً: «هدول بدهم تغيير وتوسيع وتضييق»): أضيق من الحيّ وأوسع من 50/200.
WIDE_PAIRS = [(3, 6), (3, 10), (5, 10), (20, 40), (30, 60), (50, 100), (100, 200), (100, 400)]
WIDE_SLOPES = [1, 3, 6, 12]


def grid(base):
    """الشبكة الأولى، أو الموسّعة (CALIB_WIDE)؛ و CALIB_PART=0..3 يقسمها على أربع عمليّات."""
    part = os.environ.get("CALIB_PART")
    combos = ([(p, k) for p in WIDE_PAIRS for k in WIDE_SLOPES] if os.environ.get("CALIB_WIDE")
              else [(p, k) for p in EMA_PAIRS for k in SLOPES])
    items = [] if os.environ.get("CALIB_WIDE") else [("live", dict(base))]
    for (f, s), k in combos:
        if (f, s, k) == (base["ema_fast"], base["ema_slow"], base["slope_lookback"]):
            continue
        items.append((f"f{f}_s{s}_k{k}", dict(base, ema_fast=f, ema_slow=s, slope_lookback=k,
                                              min_candles=max(int(base["min_candles"]), s))))
    for n, item in enumerate(items):
        if part is None or n % 4 == int(part):
            yield item


async def run(frame, out):
    mod = load_atom_module()
    base = dict((yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8")) or {}).get("config") or {})
    rows = candles(frame)
    sec = FRAME_SEC[frame]
    for tag, cfg in grid(base):
        path = out / f"{frame}_{tag}.npz"
        if path.exists():
            continue
        n = len(rows)
        dist = np.full(n, np.nan, np.float32)
        slope = np.full(n, np.nan, np.float32)
        pos = np.zeros(n, np.int8)
        above_slow = np.zeros(n, np.int8)
        pattern = np.zeros(n, np.int8)
        idx = [0]

        async def publish(name, p):
            if name != "analysis.trend.state" or p.get("timeframe") != frame:
                return
            md = p.get("metadata") or {}
            if md.get("ema_distance") is None:
                return                                   # تسخين (insufficient_data)
            i = idx[0]
            dist[i] = md["ema_distance"]
            slope[i] = md["ema_slope"]
            pos[i] = POS.get(md.get("price_position"), 0)
            above_slow[i] = 1 if md["close"] > md["ema_slow_value"] else (-1 if md["close"] < md["ema_slow_value"] else 0)
            pattern[i] = SIG.get(md.get("bench_signal"), 0)

        handlers = {}
        ctx = AtomContext(atom_id=151, config=dict(cfg), logger=_Log(), publish=publish,
                          subscribe=lambda nme, h: handlers.setdefault(nme, []).append(h))
        atom = mod.Atom()
        await atom.initialize(ctx)
        await atom.start()
        atom._candle_kernel.stop()   # التوأم لا يغيّر حقيقةً واحدة (رقمه يُنزع)؛ الحكم من bench_signal
        hs = handlers["market_data.candle_closed"]
        tic = _real_time()
        for i, row in enumerate(rows):
            idx[0] = i
            _NOW[0] = row[0] + sec
            pl = payload_of(row, frame)
            for hd in hs:
                await hd(pl)
        await atom.stop()
        np.savez_compressed(path, t=rows[:, 0] + sec, close=rows[:, 4], high=rows[:, 2], low=rows[:, 3],
                            dist=dist, slope=slope, pos=pos, above_slow=above_slow, pattern=pattern,
                            cfg=json.dumps(cfg))
        print(json.dumps({"frame": frame, "tag": tag, "n": n, "facts": int(np.isfinite(dist).sum()),
                          "secs": round(_real_time() - tic, 1)}, ensure_ascii=False), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True, choices=list(FRAME_SEC))
    ap.add_argument("--out", default=str(SCRATCH / "out"))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    asyncio.run(run(a.frame, out))


if __name__ == "__main__":
    main()
