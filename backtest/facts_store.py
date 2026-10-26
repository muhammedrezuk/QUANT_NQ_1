# -*- coding: utf-8 -*-
"""مخزن الحقائق — قلب أداة الباك تست الاحترافيّة (ورقة الخطوات ١٧/١٠، الخطوتان 1 و2؛ ختم المالك «NQ»).

قوله: «أيّ توليفة بدّي ياها بقدر أختبرها أنا بيدي … ولازم تكون سريعة بالاختبارات». فالذرّات الحقيقيّة (الأقسام 150 · 200 · 250
· 300 · 350) تُشغَّل بكودها الحيّ مرّةً واحدة على شموع الفترة، وتُحفظ كلّ حقيقةٍ نشرتها في مخزنٍ على القرص؛ ثمّ تُختبر أيّ توليفة
من المخزن في ثوانٍ (`backtest/combo_engine.py`).

The run: minute candles of one symbol over a period (plus warm-up) are built into 1m / 5m / 15m / 30m / 1h / 4h / 1d with
the live candle builder's alignment (atom 103), fed to every atom of the five sections (their chains resolve on the bus),
with a four-tick path per minute for atoms that listen to ticks (open, low/high, high/low, close -- declared). Every
published state event is flattened (top-level, metadata and nested scalars) and written to disk as it comes, per
(atom, event, frame): a folder with the times and one raw column per field (numbers float64, words int32 codes with a
vocabulary). The atoms read a copy of the live analysis settings and the data's clock. Output: <store>/<symbol>/
<from>_<to>/ -- one folder per group and index.json.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_NOW = [0.0]
_REAL_TIME = time.time
time.time = lambda: _NOW[0] or _REAL_TIME()

HISTORY_DB = ROOT / "forex_runtime" / "var" / "history" / "ctrader_history.db"
LIVE_SETTINGS = ROOT / "forex_runtime" / "var" / "store" / "analysis_settings.db"
STORE = ROOT / "forex_runtime" / "var" / "facts_store"
SECTIONS = ("قسم 150-199", "قسم 200-249", "قسم 250-299", "قسم 300-349", "قسم 350-399")
#: no history for these: the depth / order-book atoms need a live book; 360-368 learn from live outcomes.
EXCLUDED = {"261", "262", "263", "264", "265"} | {str(i) for i in range(360, 369)}
FRAMES = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
EVENT_CANDLE = "market_data.candle_closed"
EVENT_TICK = "market.tick.validated"
STATE_SUFFIX = ".state"
SKIP_KEYS = {"symbol", "timeframe", "id", "cycle_id", "account_id", "broker", "provider", "event_id", "trace_id",
             "parent_event_id", "source", "warnings", "contract", "schema"}


class _Quiet:
    def __getattr__(self, _):
        return lambda *a, **k: None


def catalog() -> dict[str, dict[str, Any]]:
    import yaml
    cat = {}
    for section in SECTIONS:
        for folder in sorted((ROOT / "atoms" / section).iterdir()):
            aid = folder.name[:3]
            if not (folder / "atom.py").exists() or aid in EXCLUDED:
                continue
            manifest = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8")) or {}
            cat[aid] = {"dir": folder, "name": folder.name[4:], "config": dict(manifest.get("config") or {}),
                        "sub": list(manifest.get("subscribes") or []), "pub": list(manifest.get("publishes") or [])}
    return cat


def load_atom(aid: str, folder: Path):
    spec = importlib.util.spec_from_file_location("_fs%s" % aid, folder / "atom.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    sys.path.insert(0, str(folder))
    spec.loader.exec_module(mod)
    return mod


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


FLAT_DEPTH = 4


def flatten(payload: dict[str, Any]) -> dict[str, Any]:
    """Scalars of a state event (numbers, words, flags): top level, `metadata` as «m.», and nested objects with dotted
    keys (atom 209 publishes `frames.15m.dow_trend`, `readings.four_hours.trend` ...). Lists are left out."""
    out: dict[str, Any] = {}

    def walk(prefix: str, body: dict[str, Any], depth: int) -> None:
        for k, v in body.items():
            if not prefix and (k in SKIP_KEYS or k == "metadata"):
                continue
            key = prefix + str(k)
            if isinstance(v, (bool, int, float, str)):
                out[key] = v
            elif isinstance(v, dict) and depth < FLAT_DEPTH:
                walk(key + ".", v, depth + 1)

    walk("", payload, 0)
    md = payload.get("metadata")
    if isinstance(md, dict):
        walk("m.", md, 1)
    return out


BATCH_ROWS = 4000


class GroupWriter:
    """One (atom, event, frame) on disk as it comes: `t.f64` and one raw column per field, appended batch by batch, so a
    year never sits in memory (a month of all atoms held as rows took 2 GB — measured 2026-10-17). A field first seen late
    is padded back; numbers are float64 (flags as 0/1), words int32 codes with a vocabulary that only grows."""

    def __init__(self, folder: Path) -> None:
        self.dir = folder
        self.dir.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.cols: dict[str, dict[str, Any]] = {}
        self.buffer: list[tuple[float, dict[str, Any]]] = []

    def _column(self, key: str, kind: str) -> dict[str, Any]:
        import numpy as np
        name = key if kind == "num" else key + "#w"
        if name not in self.cols:
            fname = "c%03d.%s" % (len(self.cols), "f64" if kind == "num" else "i32")
            col = {"key": key, "kind": kind, "file": fname, "vocab": {}}
            pad = np.full(self.n, np.nan, dtype=np.float64) if kind == "num" else np.full(self.n, -1, dtype=np.int32)
            with open(self.dir / fname, "ab") as fh:
                pad.tofile(fh)
            self.cols[name] = col
        return self.cols[name]

    def add(self, t: float, row: dict[str, Any]) -> None:
        self.buffer.append((t, row))
        if len(self.buffer) >= BATCH_ROWS:
            self.flush()

    def flush(self) -> None:
        import numpy as np
        if not self.buffer:
            return
        rows, self.buffer = self.buffer, []
        for _, r in rows:
            for k, v in r.items():
                self._column(k, "num" if isinstance(v, (bool, int, float)) else "word")
        with open(self.dir / "t.f64", "ab") as fh:
            np.array([t for t, _ in rows], dtype=np.float64).tofile(fh)
        for name, col in self.cols.items():
            k = col["key"]
            if col["kind"] == "num":
                vals = [r.get(k) for _, r in rows]
                arr = np.array([float(v) if isinstance(v, (bool, int, float)) else np.nan for v in vals], dtype=np.float64)
            else:
                vocab = col["vocab"]
                codes = []
                for _, r in rows:
                    v = r.get(k)
                    if isinstance(v, str):
                        codes.append(vocab.setdefault(v, len(vocab)))
                    else:
                        codes.append(-1)
                arr = np.array(codes, dtype=np.int32)
            with open(self.dir / col["file"], "ab") as fh:
                arr.tofile(fh)
        self.n += len(rows)

    def meta(self) -> list[dict[str, Any]]:
        self.flush()
        out = []
        for col in self.cols.values():
            vocab = [w for w, _ in sorted(col["vocab"].items(), key=lambda kv: kv[1])] if col["kind"] == "word" else None
            out.append({"key": col["key"], "kind": col["kind"], "file": col["file"], "vocab": vocab})
        return out


class Collector:
    """Every state event of one symbol, written to disk per (atom, event, frame) as it comes."""

    def __init__(self, symbol: str, owners: dict[str, str], folder: Path) -> None:
        self.symbol, self.owners, self.folder = symbol, owners, folder
        self.groups: dict[tuple[str, str, str], GroupWriter] = {}

    def put(self, event: str, payload: Any) -> None:
        if not event.endswith(STATE_SUFFIX) or not isinstance(payload, dict):
            return
        if str(payload.get("symbol") or "").upper() != self.symbol:
            return
        frame = str(payload.get("timeframe") or (payload.get("metadata") or {}).get("timeframe") or "")
        key = (self.owners.get(event, "?"), event, frame)
        if key not in self.groups:
            self.groups[key] = GroupWriter(self.folder / ("%s__%s__%s" % (key[0], event.replace(".", "_"), frame or "na")))
        self.groups[key].add(_NOW[0], flatten(payload))

    def save(self, folder: Path) -> dict[str, Any]:
        index = []
        for (aid, event, frame), w in sorted(self.groups.items()):
            fields = w.meta()
            index.append({"atom": aid, "event": event, "frame": frame, "dir": w.dir.name, "rows": w.n, "fields": fields})
        return {"groups": index}


REPORT_EVERY_S = 30


def eta_line(what: str, at: float, start: float, end: float, began: float) -> str:
    """«كم بقي ومتى ينتهي» (المالك ١٧/١٠: «مو معقول أشغّل اختبار وأنا ما بعرف إيمت بينتهي»): النسبة من مدى البيانات، والباقي
    بسرعة ما مضى، وساعة الانتهاء بساعة الجهاز."""
    done = min(1.0, max(0.0, (at - start) / max(1.0, end - start)))
    spent = _REAL_TIME() - began
    left = spent * (1 - done) / done if done > 0.01 else None
    finish = datetime.fromtimestamp(_REAL_TIME() + left).strftime("%H:%M") if left is not None else "—"
    def mins(s):
        return "—" if s is None else ("%d دقيقة" % round(s / 60) if s >= 60 else "أقلّ من دقيقة")
    return "%s: %d٪ · مضى %s · باقي %s · ينتهي نحو %s · البيانات عند %s" % (
        what, round(done * 100), mins(spent), mins(left), finish, datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%d"))


def _quotes(symbol: str, t0: float, t1: float):
    """Real cTrader quotes: the bid (side 1) and ask (side 2) tick tables merged by time; a quote once both are known."""
    import heapq
    q = "select ts_ms, price from ticks_history where symbol=? and side=? and ts_ms>=? and ts_ms<? order by ts_ms"

    def one(side: int):
        con = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
        for ts, px in con.execute(q, (symbol, side, int(t0 * 1000), int(t1 * 1000))):
            yield ts, side, px

    bid = ask = None
    for ts, side, px in heapq.merge(one(1), one(2)):
        if side == 1:
            bid = px
        else:
            ask = px
        if bid is not None and ask is not None:
            yield ts, bid, ask


async def run(symbol: str, t_from: float, t_to: float, warm_days: float, out: Path, atoms: list[str] | None,
              real_ticks: bool = False, settings_from: Path | None = None) -> dict:
    from core.contracts.atom import AtomContext
    if out.exists() and any(out.iterdir()):
        # the columns are appended: an older or half-built store here would be mixed in — it moves to the archive (no deletion)
        arch = ROOT / "archive" / ("facts_store_old_%s" % datetime.now().strftime("%Y-%m-%d"))
        arch.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out), str(arch / ("%s_%s_%s" % (symbol, out.name, datetime.now().strftime("%H%M%S")))))
    out.mkdir(parents=True, exist_ok=True)
    settings = out / "analysis_settings.db"
    source = settings_from if settings_from is not None and settings_from.exists() else LIVE_SETTINGS
    if source.exists() and not settings.exists():
        shutil.copyfile(source, settings)                         # the atoms read a copy, never the live store
    os.environ["QUANT_ANALYSIS_SETTINGS_DB"] = str(settings)
    cat = catalog()
    chosen = [a for a in cat if not atoms or a in atoms]
    owners = {e: a for a in chosen for e in cat[a]["pub"]}
    coll = Collector(symbol, owners, out)
    handlers: dict[str, list] = defaultdict(list)

    async def publish(name, payload):
        coll.put(name, payload)
        for h in list(handlers.get(name, ())):
            await h(payload)

    loaded, failed = [], {}
    for aid in chosen:
        try:
            mod = load_atom(aid, cat[aid]["dir"])
            ctx = AtomContext(atom_id=int(aid), config=dict(cat[aid]["config"]), logger=_Quiet(), publish=publish,
                              subscribe=lambda n, h: handlers[n].append(h), subscribe_all=lambda h: None)
            atom = mod.Atom()
            await atom.initialize(ctx)
            await atom.start()
            for kname in ("_candle_kernel", "_live_kernel"):
                kernel = getattr(atom, kname, None)
                if kernel is not None:
                    kernel.stop()
            loaded.append(aid)
        except Exception as exc:  # noqa: BLE001 -- an atom that cannot run on history is listed, not fatal
            failed[aid] = "%s: %s" % (type(exc).__name__, exc)
    folder = ROOT / "atoms" / "قسم 100-149" / "103_باني_الشموع"
    spec = importlib.util.spec_from_file_location("_fs103", folder / "atom.py")
    m103 = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(folder))
    spec.loader.exec_module(m103)
    fps = m103.frame_period_start
    candles, ticks = handlers.get(EVENT_CANDLE, []), handlers.get(EVENT_TICK, [])

    async def emit(end, frame, k, o, h, l, c):
        _NOW[0] = end
        payload = {"account_id": "bench", "broker": "bench", "provider": "ctrader_history", "symbol": symbol, "open": o,
                   "high": h, "low": l, "close": c, "volume": 0.0, "tick_count": 0, "fabric_gap": False,
                   "timeframe": frame, "period_start": float(k), "timestamp": float(k)}
        for hd in candles:
            await hd(dict(payload))

    db = sqlite3.connect("file:%s?mode=ro" % HISTORY_DB, uri=True)
    feed = _quotes(symbol, t_from - warm_days * 86400, t_to) if real_ticks else None
    nxt, n_ticks = (next(feed, None) if feed is not None else None), 0
    pend, n_min, began = {}, 0, _REAL_TIME()
    rows = db.execute("select period_start, open, high, low, close from candles_history where symbol=? and period='M1' "
                      "and period_start>=? and period_start<? order by period_start",
                      (symbol, t_from - warm_days * 86400, t_to))
    last_report = 0.0
    for ps, o, h, l, c in rows:
        for frame, sec in FRAMES.items():
            b = pend.get(frame)
            if b is not None and fps(ps, sec) != b[0]:
                await emit(b[0] + sec, frame, *b)
                del pend[frame]
        if ticks and feed is not None:
            # ١٩/١٠ (المالك: «كمّل على دخول بتِكّات حقيقيّة»): أسعار سي‑تريدر الحقيقيّة داخل الدقيقة، بترتيب وقتها.
            end_ms = (ps + 60) * 1000
            while nxt is not None and nxt[0] < end_ms:
                ts_s = nxt[0] / 1000.0
                _NOW[0] = ts_s
                tk = {"account_id": "bench", "broker": "bench", "provider": "CTRADER", "symbol": symbol, "bid": nxt[1],
                      "ask": nxt[2], "mid": (nxt[1] + nxt[2]) / 2.0, "volume": 0.0, "timestamp": ts_s,
                      "source_timestamp": ts_s, "ts": ts_s}
                for hd in ticks:
                    await hd(tk)
                n_ticks += 1
                nxt = next(feed, None)
        elif ticks:
            for dt_s, px in ((1, o), (20, l if c >= o else h), (40, h if c >= o else l), (59, c)):
                _NOW[0] = ps + dt_s
                tk = {"account_id": "bench", "broker": "bench", "provider": "CTRADER", "symbol": symbol, "bid": px,
                      "ask": px, "price": px, "mid": px, "volume": 0.0, "timestamp": ps + dt_s,
                      "source_timestamp": ps + dt_s, "ts": ps + dt_s}
                for hd in ticks:
                    await hd(tk)
        m = ps + 60
        for frame, sec in FRAMES.items():
            k = fps(ps, sec)
            b = pend.get(frame)
            if b is None:
                pend[frame] = [k, o, h, l, c]
            else:
                b[2], b[3], b[4] = max(b[2], h), min(b[3], l), c
        for frame, sec in FRAMES.items():
            b = pend[frame]
            if b[0] + sec == m:
                await emit(m, frame, *b)
                del pend[frame]
        n_min += 1
        now_real = _REAL_TIME()
        if now_real - last_report >= REPORT_EVERY_S:
            last_report = now_real
            print(eta_line("مخزن الحقائق", ps, t_from - warm_days * 86400, t_to, began), flush=True)
    db.close()
    index = coll.save(out)
    index.update({"symbol": symbol, "from": t_from, "to": t_to, "warm_days": warm_days, "minutes": n_min,
                  "ticks": "real" if real_ticks else "four_per_minute", "real_ticks_sent": n_ticks,
                  "seconds": round(_REAL_TIME() - began, 1), "atoms": loaded, "failed": failed,
                  "configs": {a: config_hash(cat[a]["config"]) for a in loaded},
                  "names": {a: cat[a]["name"] for a in loaded}})
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print("مخزن الحقائق: انتهت · مجموعات %d · %d ثانية" % (len(index["groups"]), index["seconds"]), flush=True)
    return index


RECOVER_REPLAY_DAYS = 31


def recover(symbol: str, t_from: float, warm_days: float, partial: Path, log=print) -> bool:
    """Rescue a store cut before its end (the owner, 2026-10-23: «حاول إنقاذ الـ92٪ المبنيّة»). The columns were on disk; the
    map of which column is which fact, and the words' codes, lived in memory until the end and were lost. The build is a
    deterministic replay, so the first month is built again beside it with the store's own settings copy: the same groups,
    the same column order, the same word codes. Every column of the replay must equal the cut store's first rows byte for
    byte -- then the map is proven and written as the cut store's index, its rows trimmed to what all its columns hold.
    A column first seen after the replay month, or a word first seen after it, stays unnamed and is left out; nothing is
    guessed. Returns whether the store can be read."""
    import numpy as np
    if (partial / "index.json").exists():
        return True
    replay = partial.parent / (partial.name + "__replay")
    if not (replay / "index.json").exists():
        log("الإنقاذ: يعيد الجهاز بناء الشهر الأوّل بجانب المخزن …")     # a half replay is moved aside by run() itself
        asyncio.run(run(symbol, t_from, t_from + RECOVER_REPLAY_DAYS * 86400, warm_days, replay, None,
                        settings_from=partial / "analysis_settings.db"))
    idx = json.loads((replay / "index.json").read_text(encoding="utf-8"))
    groups, unnamed, mismatch, empty, compared = [], 0, [], 0, 0
    for g in idx["groups"]:
        cut = partial / g["dir"]
        # 2026-10-23: a group whose rows never left the 4000-row buffer before the power-off has no file at all -- it
        # holds nothing to rescue, which is not a disagreement.
        if not (cut / "t.f64").exists():
            empty += 1
            continue
        t_r = np.fromfile(replay / g["dir"] / "t.f64", dtype=np.float64)
        t_c = np.fromfile(cut / "t.f64", dtype=np.float64)
        n = min(len(t_r), len(t_c))                               # the rows both have written
        if n == 0:
            empty += 1
            continue
        if not np.array_equal(t_r[:n].view(np.int64), t_c[:n].view(np.int64)):
            mismatch.append(g["dir"] + "/t")
            continue
        rows, kept = len(t_c), []
        for f in g["fields"]:
            if not (cut / f["file"]).exists():                    # first seen in rows the cut store never wrote
                continue
            dtype = np.float64 if f["kind"] == "num" else np.int32
            a = np.fromfile(replay / g["dir"] / f["file"], dtype=dtype)
            b = np.fromfile(cut / f["file"], dtype=dtype)
            m = min(n, len(a), len(b))
            if a[:m].tobytes() != b[:m].tobytes():
                mismatch.append("%s/%s" % (g["dir"], f["file"]))
            compared += m
            rows = min(rows, len(b))
            kept.append(f)
        known = {f["file"] for f in kept}
        unnamed += sum(1 for p in cut.glob("c*.*") if p.name not in known)
        groups.append({**g, "fields": kept, "rows": int(rows)})
    if mismatch:
        log("الإنقاذ: لا يتطابق في %d موضع (أوّلها %s) — لا يُستعمل المخزن المقطوع" % (len(mismatch), mismatch[0]))
        return False
    last = max(float(np.fromfile(partial / g["dir"] / "t.f64", dtype=np.float64)[g["rows"] - 1])
               for g in groups if g["rows"])
    index = {**{k: v for k, v in idx.items() if k != "groups"}, "groups": groups, "to": last,
             "recovered": {"replay_days": RECOVER_REPLAY_DAYS, "verified_groups": len(groups),
                           "values_compared": compared, "groups_without_data": empty,
                           "unnamed_columns_left_out": unnamed, "data_until": last}}
    (partial / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    log("الإنقاذ: تطابق %d مجموعة حرفًا (%d قيمة قورنت) · البيانات حتّى %s · مجموعات بلا بيانات %d · أعمدة بلا اسم تُركت %d" % (
        len(groups), compared, datetime.fromtimestamp(last, timezone.utc).strftime("%Y-%m-%d"), empty, unnamed))
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="USTEC")
    ap.add_argument("--from", dest="t_from", default="2023-01-01")
    ap.add_argument("--to", dest="t_to", default="2024-01-01")
    ap.add_argument("--warm-days", type=float, default=60.0)
    ap.add_argument("--atoms", default="", help="ذرّات بعينها (مثل 151,202) — والافتراض كلّها")
    ap.add_argument("--out", default="")
    ap.add_argument("--real-ticks", action="store_true", help="تِكّات سي‑تريدر الحقيقيّة بدل الأسعار الأربعة لكلّ دقيقة")
    ap.add_argument("--recover", action="store_true", help="إنقاذ مخزنٍ انقطع قبل آخره: يعيد الشهر الأوّل ويثبت الخريطة")
    args = ap.parse_args()
    t0 = datetime.fromisoformat(args.t_from).replace(tzinfo=timezone.utc).timestamp()
    t1 = datetime.fromisoformat(args.t_to).replace(tzinfo=timezone.utc).timestamp()
    out = Path(args.out) if args.out else STORE / args.symbol / ("%s_%s" % (args.t_from, args.t_to))
    if args.recover:
        return 0 if recover(args.symbol, t0, args.warm_days, out, log=lambda s: print(s, flush=True)) else 1
    asyncio.run(run(args.symbol, t0, t1, args.warm_days, out, [a for a in args.atoms.split(",") if a] or None,
                    real_ticks=args.real_ticks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
