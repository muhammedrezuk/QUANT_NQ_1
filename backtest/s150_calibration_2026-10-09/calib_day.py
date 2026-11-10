# -*- coding: utf-8 -*-
"""معايرة يومٍ واحد لكلّ ذرّات التحليل — قياسٌ فقط (ختم المالك «NQ» ٢٠٢٦-١٠-٠٩ مساءً).

أمر المالك: «كلّ محلّل أو إحصاء أو بنية ياخد كلّ النوافذ والتركيبات والأرقام والفريمات … تشتغل على يوم واحد بس
وبدي نتيجة هاليوم» · اليوم: الخميس 2026-10-08 · لندن 08:00⟵16:30 لندن · نيويورك 09:30⟵16:00 نيويورك ·
«في منهم بدهم تِكّ … عطيه» · «20 تِكّة وسّعها».

كلّ تشغيل: ذرّةٌ واحدة تُعاير (`--tune`) بعيارٍ من الشبكة، ومعها الذرّات التي تغذّيها بعيارها الحيّ (السلسلة من
اشتراكات البيانات)، بكود atom.py الحيّ نفسه، على حافلةٍ صغيرة بترتيب الوصول. تُسجَّل حقائق كلّ ذرّةٍ في السلسلة
في نافذة الحكم (06:00⟵20:00 غرينتش يوم الخميس) — الحقائق كما ينشرها عقد الحقائق، ومعها حكم الذرّة قبل نزعه
(`bench_signal`، للعلم).

التغذية:
  الشموع — 1m · 5m · 15m · 1h · 4h · 1d للناسداك (والإس آند بي للأقران)، مبنيّةً بدالّة 103 الحيّة نفسها
           (`frame_period_start`: غرينتش للساعة وما دونها، ويوم الوسيط فوقها) من شموع الدقيقة في المخزن ثمّ من
           تِكّات العرض بعد نهايتها؛ تسخينٌ يكفي أوسع نافذة (اليوميّ من 2024). حجمٌ صفر كما يبنيها 103 حيًّا.
  التِّكّ  — تِكّات سي‑تريدر الحقيقيّة (عرض/طلب مدموجان) من 05:00 غرينتش يوم الخميس — للذرّات المشتركة فيه
           وحدها (300 · 350)؛ المسار التِّكّيّ لقسم 150 منزوعٌ بعقد الحقائق فلا يُغذّى.
مخزن الحيّ لا يُفتح (مخزن المعايرة محوَّل إلى المسوّدة)، والساعة على زمن البيانات.

الاستعمال:  python calib_day.py --tune 152 [--probe] [--out DIR] [--part i/n]
"""
import argparse
import asyncio
import gzip
import importlib.util
import json
import os
import pathlib
import pickle
import sqlite3
import sys
import time as _time
from datetime import datetime, timezone

ROOT = pathlib.Path(r"C:\Users\NQ\QUANT_NQ")
SCRATCH = pathlib.Path(os.environ.get(
    "CALIB_SCRATCH", r"C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib_day"))
SCRATCH.mkdir(parents=True, exist_ok=True)
os.environ["QUANT_ANALYSIS_SETTINGS_DB"] = str(SCRATCH / "settings_bench.db")
sys.path.insert(0, str(ROOT))
import yaml  # noqa: E402

_NOW = [0.0]
_real_time = _time.time
_time.time = lambda: _NOW[0] or _real_time()
from core.contracts.atom import AtomContext  # noqa: E402
import shared.section_contract as _SC  # noqa: E402

_orig_stamp = _SC.stamp_section


def _bench_stamp(payload, **kw):
    if isinstance(payload, dict) and "signal" in payload:
        md = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        payload = dict(payload, metadata=dict(md, bench_signal=payload["signal"]))
    return _orig_stamp(payload, **kw)


_SC.stamp_section = _bench_stamp

TS = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()  # noqa: E731
#: اليوم المقيس — CALIB_DAY (شهر المالك ١٠-١٠: «شهر كامل … وسّع وضيّق NQ»)، والافتراض الخميس 10-08.
DAY = os.environ.get("CALIB_DAY", "2026-10-08")
#: ٢٠٢٦-١٠-١٠ (سنة المشي إلى الأمام): حتّى 21:30 غرينتش — نيويورك تنتهي 21:00 غرينتش شتاءً (20:00 صيفًا).
JUDGE_FROM, JUDGE_TO = TS(DAY) + 6 * 3600, TS(DAY) + 21.5 * 3600
TICKS_FROM = TS(DAY) + 5 * 3600
FRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
#: التسخين بالأيّام قبل اليوم المقيس — يكفي أوسع نافذة (×10) على كلّ إطار.
WARM_DAYS = {"1m": 14, "5m": 70, "15m": 130, "1h": 280, "4h": 480, "1d": 1000}
WARM = {fr: datetime.fromtimestamp(TS(DAY) - n * 86400, timezone.utc).strftime("%Y-%m-%d") for fr, n in WARM_DAYS.items()}
SYMBOLS = ("USTEC", "US500")
SECTIONS = ("قسم 150-199", "قسم 200-249", "قسم 250-299", "قسم 300-349", "قسم 350-399")
EXCLUDE = {str(i) for i in range(360, 369)} | {"261", "262", "263", "264"}   # التعلّم · الدفتر (لا تاريخ له)
FEED_EVENTS = {"market_data.candle_closed", "market.tick.validated"}
HIST = f"file:{ROOT / 'forex_runtime/var/history/ctrader_history.db'}?mode=ro"


class _Log:
    def __getattr__(self, _):
        return lambda *a, **k: None


# ── الذرّات ──────────────────────────────────────────────────────────────────
def catalog():
    cat = {}
    for s in SECTIONS:
        for d in sorted((ROOT / "atoms" / s).iterdir()):
            if not (d / "atom.py").exists() or d.name[:3] in EXCLUDE:
                continue
            y = yaml.safe_load((d / "manifest.yaml").read_text(encoding="utf-8")) or {}
            cat[d.name[:3]] = {"dir": d, "sub": [x for x in y.get("subscribes") or [] if x],
                               "pub": [x for x in y.get("publishes") or [] if x], "config": dict(y.get("config") or {})}
    return cat


def chain(cat, aid):
    """الذرّة ومن يغذّيها (عبر الأحداث التي تشترك فيها) — بلا حلقات."""
    by_pub = {}
    for k, v in cat.items():
        for e in v["pub"]:
            by_pub.setdefault(e, []).append(k)
    need, todo = [], [aid]
    while todo:
        a = todo.pop()
        if a in need:
            continue
        need.append(a)
        for e in cat[a]["sub"]:
            if e not in FEED_EVENTS:
                todo += [p for p in by_pub.get(e, []) if p not in need]
    return list(reversed(need))


def downstream(cat, aid):
    """من يتغذّى من الذرّة المعايرة (تُسجَّل حقائقه أيضًا: 201 ⟵ البنية والسيولة)."""
    out, todo = [aid], [aid]
    while todo:
        a = todo.pop()
        for k, v in cat.items():
            if k not in out and any(e in cat[a]["pub"] for e in v["sub"]):
                out.append(k)
                todo.append(k)
    return out


def load(cat, aid):
    d = cat[aid]["dir"]
    spec = importlib.util.spec_from_file_location(f"_cd{aid}", d / "atom.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    sys.path.insert(0, str(d))
    spec.loader.exec_module(mod)
    return mod


# ── الشبكة ───────────────────────────────────────────────────────────────────
JUDGMENT_KEYS = {"weight", "required_depth", "confidence_threshold", "strength_threshold", "min_candles",
                 "required_ticks", "strong_score", "moderate_score", "medium_score"}
WINDOW_WORDS = ("window", "period", "lookback", "fast", "slow", "short", "long", "ticks", "bars", "emerging")


def is_window(k, v):
    return isinstance(v, int) and not isinstance(v, bool) and any(w in k for w in WINDOW_WORDS)


def grid(cat, aid):
    """العيار الحيّ · النوافذ كلّها معًا أضيق وأوسع · كلّ رقمٍ وحده أضيق وأوسع."""
    base = cat[aid]["config"]
    tick = "market.tick.validated" in cat[aid]["sub"] and "market_data.candle_closed" not in cat[aid]["sub"]
    wins = [k for k, v in base.items() if is_window(k, v) and k not in JUDGMENT_KEYS]
    if tick:
        # التِّكّ: أضيق وأوسع حول البيان أيًّا كان (بعد اعتماد ١٠-٠٩ صار بعضه 6000) — أطول نافذةٍ فيه تمرّ على
        # 20 · 60 · 200 · 600 · 2000 · 6000 تِكّة، والنوافذ الأخرى بالنسبة نفسها.
        ref = max([base[k] for k in wins] or [1])
        mults = tuple(sorted({round(v / ref, 6) for v in (20, 60, 200, 600, 2000, 6000)}))
    else:
        mults = (0.1, 0.25, 0.5, 2, 4, 10)
    ths = [k for k, v in base.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
           and k not in wins and k not in JUDGMENT_KEYS]
    out = [("live", dict(base))]

    def fix(cfg):
        top = max([cfg[k] for k in wins] or [0])
        for k in ("min_candles", "required_ticks"):
            if k in cfg:
                cfg[k] = max(int(base[k]), int(top)) if k == "min_candles" else min(int(base[k]), max(2, int(top)))
        return cfg

    def scaled(v, m):
        return max(1, int(round(v * m)))
    if wins:
        for m in mults:
            if m != 1:
                out.append((f"all×{m}", fix(dict(base, **{k: scaled(base[k], m) for k in wins}))))
        if len(wins) > 1:
            for k in wins:
                for m in mults:
                    if m != 1:
                        out.append((f"{k}×{m}", fix(dict(base, **{k: scaled(base[k], m)}))))
    for k in ths:
        for m in (0.5, 2.0):
            v = base[k] * m if base[k] else (0.5 if m == 2.0 else -0.5)
            out.append((f"{k}×{m}", dict(base, **{k: type(base[k])(v) if isinstance(base[k], float) else int(round(v)) or 1})))
    seen, uniq = set(), []
    for tag, cfg in out:
        key = json.dumps(cfg, sort_keys=True)
        if key not in seen:
            seen.add(key)
            uniq.append((tag, cfg))
    return uniq


# ── البيانات (تُبنى مرّةً وتُحفظ) ─────────────────────────────────────────────
def candle_stream():
    cache = SCRATCH / f"candles_{DAY}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    b103 = importlib.util.spec_from_file_location("_cd103", ROOT / "atoms" / "قسم 100-149" / "103_باني_الشموع" / "atom.py")
    m103 = importlib.util.module_from_spec(b103)
    sys.path.insert(0, str(ROOT / "atoms" / "قسم 100-149" / "103_باني_الشموع"))
    b103.loader.exec_module(m103)
    fps = m103.frame_period_start
    db = sqlite3.connect(HIST, uri=True)
    end = TS(DAY) + 86400
    events = []
    for sym in SYMBOLS:
        start = TS(min(WARM.values()))
        m1 = db.execute("select period_start, open, high, low, close from candles_history where symbol=? and period='M1' "
                        "and period_start >= ? and period_start < ? order by period_start", (sym, int(start), int(end))).fetchall()
        last = m1[-1][0] + 60 if m1 else start
        # بعد نهاية مخزن الدقيقة: دقائق من تِكّات العرض (الجهة 1).
        cur = None
        for ts_ms, px in db.execute("select ts_ms, price from ticks_history where symbol=? and side=1 and ts_ms >= ? "
                                    "and ts_ms < ? order by ts_ms", (sym, int(last * 1000), int(end * 1000))):
            t = ts_ms / 1000.0
            ps = t - t % 60
            if cur is None or cur[0] != ps:
                if cur:
                    m1.append(tuple(cur))
                cur = [ps, px, px, px, px]
            else:
                cur[2] = max(cur[2], px)
                cur[3] = min(cur[3], px)
                cur[4] = px
        if cur:
            m1.append(tuple(cur))
        for fr, sec in FRAMES.items():
            w0 = TS(WARM[fr])
            bars = {}
            for ps, o, h, l, c in m1:
                if ps < w0:
                    continue
                k = fps(ps, sec)
                b = bars.get(k)
                if b is None:
                    bars[k] = [k, o, h, l, c]
                else:
                    b[2] = max(b[2], h)
                    b[3] = min(b[3], l)
                    b[4] = c
            for k, o, h, l, c in bars.values():
                close_t = min(k + sec, end) if fr != "1d" else k + sec
                if close_t > end:
                    continue                          # الشمعة الأخيرة لم تُغلق بعد نهاية اليوم
                events.append((close_t, sec, sym, {"account_id": "bench", "broker": "bench", "provider": "ctrader_history",
                                                   "symbol": sym, "open": o, "high": h, "low": l, "close": c, "volume": 0.0,
                                                   "tick_count": 0, "fabric_gap": False, "timeframe": fr,
                                                   "period_start": float(k), "timestamp": float(k)}))
    events.sort(key=lambda e: (e[0], e[1], e[2] != "USTEC"))
    cache.write_bytes(pickle.dumps(events))
    return events


def tick_stream():
    cache = SCRATCH / f"ticks_{DAY}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    db = sqlite3.connect(HIST, uri=True)
    out = []
    for sym in SYMBOLS:
        bid = ask = None
        for ts_ms, side, px in db.execute("select ts_ms, side, price from ticks_history where symbol=? and ts_ms >= ? "
                                          "and ts_ms < ? order by ts_ms, side",
                                          (sym, int(TICKS_FROM * 1000), int(JUDGE_TO * 1000))):
            if side == 1:
                bid = px
            else:
                ask = px
            if bid is None or ask is None or ask <= bid:
                continue
            out.append((ts_ms / 1000.0, sym, bid, ask))
    out.sort()
    # تِكّتان بالطابع نفسه تُدمجان (حارس الرتابة في المحلّلين يرفض المتساوي).
    merged = []
    for t, sym, b, a in out:
        if merged and merged[-1][0] == t and merged[-1][1] == sym:
            merged[-1] = (t, sym, b, a)
        else:
            merged.append((t, sym, b, a))
    cache.write_bytes(pickle.dumps(merged))
    return merged


# ── التشغيل ──────────────────────────────────────────────────────────────────
def flat(prefix, obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            flat(f"{prefix}{k}.", v, out)
    elif isinstance(obj, bool):
        out[prefix[:-1]] = int(obj)
    elif isinstance(obj, (int, float)):
        out[prefix[:-1]] = obj
    elif isinstance(obj, str) and len(obj) <= 32:
        out[prefix[:-1]] = obj


SKIP_TOP = {"symbol", "id", "cycle_id", "account_id", "broker", "as_of", "computed_on", "section_id", "atom_id",
            "contract", "asset", "analyzer_id", "analysis_mode", "live_contract_version", "source_timestamp",
            "timestamp", "sequence", "settings_revision", "freshness_age_s", "stale_after_effective_s", "provider"}


async def run_one(cat, tune, cfg, record, candles, ticks, probe=False):
    names = []
    for a in record:
        for x in chain(cat, a):
            if x not in names:
                names.append(x)
    handlers = {}
    rec = []
    rec_idx = {}
    atoms = []

    def make_publish(aid):
        async def publish(name, payload):
            if not isinstance(payload, dict):
                return
            if aid in record and _NOW[0] >= JUDGE_FROM and payload.get("symbol", "USTEC") == "USTEC":
                row = {}
                flat("", {k: v for k, v in payload.items() if k not in SKIP_TOP and k != "metadata"}, row)
                flat("m.", payload.get("metadata") or {}, row)
                # آخر قيمةٍ في كلّ دقيقة تكفي الحكم (يقرأ آخر قيمةٍ حتّى إغلاق الدقيقة) — الدقيقة تُعدّ بنهايتها
                # فلا تدخلها قيمةٌ بعد إغلاقها. يحفظ ذرّات التِّكّ من مئات آلاف الأسطر.
                key = (aid, name, payload.get("timeframe"), -int(-_NOW[0] // 60))
                if key in rec_idx:
                    rec[rec_idx[key]] = (_NOW[0], aid, name, payload.get("timeframe"), row)
                else:
                    rec_idx[key] = len(rec)
                    rec.append((_NOW[0], aid, name, payload.get("timeframe"), row))
                if probe and len(rec) < 4:
                    print(aid, name, json.dumps(payload, ensure_ascii=False, default=str)[:900])
            for h in list(handlers.get(name, ())):
                await h(payload)
        return publish

    for aid in names:
        mod = load(cat, aid)
        c = dict(cfg) if aid == tune else dict(cat[aid]["config"])
        ctx = AtomContext(atom_id=int(aid), config=c, logger=_Log(), publish=make_publish(aid),
                          subscribe=lambda n, h: handlers.setdefault(n, []).append(h))
        atom = mod.Atom()
        await atom.initialize(ctx)
        await atom.start()
        for kname in ("_candle_kernel", "_live_kernel"):
            k = getattr(atom, kname, None)
            if k is not None:
                k.stop()          # أرقام النواة تُنزع بعقد الحقائق؛ لا تمسّ حقيقة
        atoms.append(atom)
    wants_tick = any("market.tick.validated" in cat[a]["sub"] and not a.startswith("15") for a in names)
    ch = handlers.get("market_data.candle_closed", [])
    th = handlers.get("market.tick.validated", []) if wants_tick else []
    if not th:
        ticks = []
    i = j = 0
    while i < len(candles) or j < len(ticks):
        if j >= len(ticks) or (i < len(candles) and candles[i][0] <= ticks[j][0]):
            t, _, _, pl = candles[i]
            i += 1
            _NOW[0] = t
            for h in ch:
                await h(dict(pl))
        else:
            t, sym, b, a = ticks[j]
            j += 1
            _NOW[0] = t
            pl = {"account_id": "bench", "broker": "bench", "provider": "CTRADER", "symbol": sym, "bid": b, "ask": a,
                  "price": (b + a) / 2.0, "mid": (b + a) / 2.0, "volume": 0.0, "timestamp": t, "source_timestamp": t,
                  "ts": t}
            for h in th:
                await h(pl)
    for a in atoms:
        try:
            await a.stop()
        except Exception:
            pass
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", default="")
    ap.add_argument("--out", default=str(SCRATCH / "runs"))
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--part", default="0/1")
    ap.add_argument("--only", default="", help="أسماء عيارات مفصولة بفواصل")
    ap.add_argument("--prep", action="store_true", help="يبني شموع اليوم وتِكّاته ويخرج")
    a = ap.parse_args()
    candles = candle_stream()
    ticks = tick_stream()
    if a.prep:
        print(json.dumps({"day": DAY, "candles": len(candles), "ticks": len(ticks)}), flush=True)
        return
    cat = catalog()
    record = downstream(cat, a.tune)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pi, pn = (int(x) for x in a.part.split("/"))
    cfgs = grid(cat, a.tune)
    if a.only:
        cfgs = [c for c in cfgs if c[0] in a.only.split(",")]
    if a.probe:
        cfgs = cfgs[:1]
        print("سلسلة:", [chain(cat, r) for r in record], "| تُسجَّل:", record, "| عيارات:", len(grid(cat, a.tune)))
        print("شموع", len(candles), "تِكّات", len(ticks))
    for n, (tag, cfg) in enumerate(cfgs):
        if n % pn != pi:
            continue
        path = out / f"{a.tune}__{tag}.json.gz"
        if path.exists() and not a.probe:
            continue
        tic = _real_time()
        try:
            rec = asyncio.run(run_one(cat, a.tune, cfg, record, candles, ticks, probe=a.probe))
        except Exception as exc:                     # عيارٌ ترفضه الذرّة لا يوقف بقيّة الشبكة
            print(json.dumps({"tune": a.tune, "tag": tag, "error": f"{type(exc).__name__}: {exc}"[:300]},
                             ensure_ascii=False), flush=True)
            continue
        if not a.probe:
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump({"tune": a.tune, "tag": tag, "cfg": cfg, "record": record, "rows": rec}, f, ensure_ascii=False,
                          default=str)
        print(json.dumps({"tune": a.tune, "tag": tag, "rows": len(rec), "secs": round(_real_time() - tic, 1)},
                         ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
