# -*- coding: utf-8 -*-
"""معايرة المنظومة كلّها على سنوات الناسداك — قياسٌ فقط (ختم المالك «Nq» ٢٠٢٦-١٠-١٣: «نعاير سستم بالكامل»).

تشغيلٌ واحد = عيارٌ واحد للذرّات على المدى كلّه بلا انقطاع (لا تسخين يوميّ): شموع الدقيقة من المخزن تُبنى منها
1m · 5m · 15m · 1h · 4h بدالّة 103 الحيّة، وتُغذّى بها ذرّات القرار بكودها الحيّ (السلسلة: 151 152 156 163 165 201 202
204 251–254 310 315 358)، وتُقيَّم الاستراتيجيّات السبع بالوحدة الحيّة نفسها `shared/facts_strategies.py` عند إغلاق كلّ
دقيقة (الزناد · العوامل · الوقف من 202) — بلا إعادة كتابةٍ لأيّ قاعدة.

الصفقة: صفقةٌ واحدة لكلّ (عيار · استراتيجيّة · إطار) في وقتها · إشارةٌ جديدة داخل الجلسة · الدخول إغلاق الدقيقة · الأثلاث
1R/2R/3R (الحيّ) والوقف أوّلًا إن التبست الشمعة · خروج الباقي بنهاية الجلسة.
السعر يتغيّر خمسة أضعاف عبر السنين ⟸ الوقف (15–45 نقطة) والهامش (نقطة) والكلفة (1.5 نقطة) تُقاس بالنسبة: أرقام اليوم
عند وسيط سعر السنة الأخيرة، مضروبةً في (سعر اليوم ÷ ذلك الوسيط).
الفروق عن الحيّ (معلنة): لا تِكّات قبل ٢٠٢٥ ⟸ الكنس 254 من مسار شمعة الدقيقة (فتح·أدنى·أعلى·إغلاق) · كلّ استراتيجيّة وإطار مستقلّ (الحيّ يمنع صفقةً
ثانية على الرمز نفسه) · لا مرشّح أخبار · لا حرّاس 5xx.

الناتج: لكلّ (عيار العتبات · استراتيجيّة · إطار · يوم): عدد الصفقات · مجموع R · الرابحة — في `out/<التشغيل>.csv`.

الاستعمال: python calib_system.py --run live            (ومعه عيارات العتبات كلّها)
           python calib_system.py --run 165:all×2       (نوافذ ذرّةٍ واحدة مضروبة)
           python calib_system.py --run best            (العيار المجمَّع من best.json)
           [--start 2014-07-17] [--end 2026-10-14] [--smoke]
"""
import argparse
import asyncio
import json
import os
import pathlib
import sqlite3
import sys
import time as _time
from collections import defaultdict, deque
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--run", default="live")
ap.add_argument("--start", default="2014-07-17")
ap.add_argument("--end", default="2026-10-14")
ap.add_argument("--smoke", action="store_true")
ap.add_argument("--strats", default="", help="استراتيجيّات بعينها (مثل 404,408) — تُشغَّل ذرّاتها وحدها")
ap.add_argument("--eval-from", default="", help="بداية التقييم (بعد التسخين) — لتقسيم المدى قطعًا بلا تداخل")
ap.add_argument("--tag", default="", help="اسم ملفّ الناتج (افتراضه اسم التشغيل)")
ARGS = ap.parse_args()
RUN_FILE = (ARGS.tag or ARGS.run).replace(":", "_")
WORK = HERE / "work" / RUN_FILE
WORK.mkdir(parents=True, exist_ok=True)
os.environ["CALIB_SCRATCH"] = str(WORK)
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(WORK / "run.log", "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(HERE.parent / "s150_calibration_2026-10-09"))
import calib_day as C  # noqa: E402  (يضبط ساعة البيانات _NOW ومخزن الإعدادات المسوّدة)
from core.contracts.atom import AtomContext  # noqa: E402
from shared import facts_strategies as FS  # noqa: E402

SYM = "USTEC"
FRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
DECISION_ATOMS = ("151", "152", "156", "163", "165", "202", "204", "254", "310", "315", "358")
#: ذرّات كلّ استراتيجيّة (الزناد · العوامل · الوقف من 202) — لتشغيلٍ مقصور على استراتيجيّاتٍ بعينها.
STRAT_ATOMS = {"404": ("151", "152", "202"), "405": ("310", "202"), "406": ("204", "202"), "407": ("151", "202"),
               "408": ("152", "163", "165", "310", "202"), "409": ("165", "315", "358", "151", "156", "202"),
               "410": ("254", "202")}
STRATS = tuple(s for s in FS.STRATEGIES if not ARGS.strats or s in ARGS.strats.split(","))
if ARGS.strats:
    DECISION_ATOMS = tuple(sorted({a for s in STRATS for a in STRAT_ATOMS[s]}))
LIVE = {"Z_TH": FS.Z_TH, "PULL_MIN": FS.PULL_MIN, "RANGE_EFF": FS.RANGE_EFF, "EDGE": FS.EDGE}
STOP_LIVE, PAD_LIVE, COST_LIVE = FS.STOP_PTS[SYM], FS.STOP_PAD_PTS[SYM], 1.5
MAX_AGE_S = 9 * 3600

#: عيارات العتبات والخروج (تُقاس في تشغيل «live» وحده) — المعلنة قبل البدء: الاسم ⟵ (التغيير، الاستراتيجيّات التي يمسّها).
THRESHOLDS = {
    "live": ({}, STRATS),
    "Z_TH=1.0": ({"Z_TH": 1.0}, ("405", "408")), "Z_TH=2.0": ({"Z_TH": 2.0}, ("405", "408")),
    "Z_TH=2.5": ({"Z_TH": 2.5}, ("405", "408")),
    "PULL_MIN=0": ({"PULL_MIN": 0.0}, ("407",)), "PULL_MIN=0.0005": ({"PULL_MIN": 0.0005}, ("407",)),
    "PULL_MIN=0.001": ({"PULL_MIN": 0.001}, ("407",)),
    "RANGE_EFF=0.25": ({"RANGE_EFF": 0.25}, ("408", "409")), "RANGE_EFF=0.5": ({"RANGE_EFF": 0.5}, ("408", "409")),
    "EDGE=0.15": ({"EDGE": 0.15}, ("409",)), "EDGE=0.35": ({"EDGE": 0.35}, ("409",)),
    "STOP=10-30": ({"STOP": 2 / 3}, STRATS), "STOP=20-60": ({"STOP": 4 / 3}, STRATS),
    "EXIT=1R": ({"EXIT": 1.0}, STRATS), "EXIT=2R": ({"EXIT": 2.0}, STRATS), "EXIT=3R": ({"EXIT": 3.0}, STRATS),
    "FACTORS=off": ({"FACTORS": False}, ("404", "408", "409")),
}
#: ١٠-١٦ (ختم المالك «قيس nq» بعد سؤاله: «قمّة وقاع من أيّ فريم … ليش ما عم يكونوا موزونين»): طريقة اختيار الوقف —
#: معلنةٌ قبل البدء. SEL = (ترتيب الإطارات، كم قاعًا/قمّةً أخيرة يُبحث فيها عن أقربها داخل المدى)؛ BAND = ضربُ طرفي المدى.
STOP_VARIANTS = {
    "live": ({}, STRATS),
    "SEL=1m-first": ({"SEL": (("1m", "5m", "15m"), 1)}, STRATS),
    "SEL=nearest5": ({"SEL": (("5m", "15m", "1m"), 5)}, STRATS),
    "SEL=1m-first+nearest5": ({"SEL": (("1m", "5m", "15m"), 5)}, STRATS),
    "BAND=10-60": ({"BAND": (10 / 15, 60 / 45)}, STRATS),
    "BAND=10-60+1m-first+nearest5": ({"BAND": (10 / 15, 60 / 45), "SEL": (("1m", "5m", "15m"), 5)}, STRATS),
}


class _Log:
    def __getattr__(self, _):
        return lambda *a, **k: None


def price_ref(db):
    """وسيط إغلاق الدقيقة في السنة الأخيرة من المخزن — عنده أرقام الحيّ (15–45 · 1 · 1.5) كما هي."""
    hi = db.execute("select max(period_start) from candles_history where symbol=? and period='M1'", (SYM,)).fetchone()[0]
    xs = [r[0] for r in db.execute("select close from candles_history where symbol=? and period='M1' and period_start>=? "
                                   "and period_start % 3600 = 0", (SYM, hi - 365 * 86400))]
    xs.sort()
    return xs[len(xs) // 2]


def atom_configs(cat):
    """عيار كلّ ذرّةٍ في هذا التشغيل."""
    cfg = {a: dict(cat[a]["config"]) for a in cat}
    if ARGS.run == "best":
        best = json.loads((HERE / "best.json").read_text(encoding="utf-8"))
        for a, tag in best["atoms"].items():
            cfg[a] = dict(next(c for t, c in C.grid(cat, a) if t == tag)) if tag != "live" else cfg[a]
    elif ":" in ARGS.run and "=" in ARGS.run:          # إعدادٌ واحد وحده: «152:roc_period=12»
        a, kv = ARGS.run.split(":", 1)
        k, v = kv.split("=", 1)
        cfg[a][k] = int(v) if v.isdigit() else float(v)
    elif ":" in ARGS.run:
        a, tag = ARGS.run.split(":", 1)
        cfg[a] = dict(next(c for t, c in C.grid(cat, a) if t == tag))
    return cfg


def variants():
    if ARGS.run == "stops":
        return STOP_VARIANTS
    if ARGS.run == "live":
        return {k: (p, tuple(s for s in ss if s in STRATS)) for k, (p, ss) in THRESHOLDS.items()}
    if ARGS.run == "best":
        best = json.loads((HERE / "best.json").read_text(encoding="utf-8"))
        patch = {}
        for name in best["thresholds"]:
            patch.update(THRESHOLDS[name][0])
        return {"best": (patch, STRATS)}
    return {"live": ({}, STRATS)}


class Trade:
    __slots__ = ("side", "entry", "risk", "st", "stage", "left", "got", "sess", "m0", "exit_r", "cost", "day")

    def __init__(self, side, entry, stop, risk, sess, m0, exit_r, cost, day):
        self.side, self.entry, self.risk, self.st = side, entry, risk, stop
        self.stage, self.left, self.got = 0, 1.0, 0.0
        self.sess, self.m0, self.exit_r, self.cost, self.day = sess, m0, exit_r, cost, day

    def bar(self, h, l):
        """شمعة دقيقةٍ بعد الدخول ⟵ True إن أُغلقت الصفقة (الأثلاث الحيّة، أو هدفٌ واحد في عيار الخروج)."""
        s, e, r = self.side, self.entry, self.risk
        if (l <= self.st) if s > 0 else (h >= self.st):
            self.got += self.left * (self.st - e) * s / r
            self.left = 0.0
            return True
        reach = h if s > 0 else l
        if self.exit_r:
            if (reach - (e + s * r * self.exit_r)) * s >= 0:
                self.got += self.left * self.exit_r
                self.left = 0.0
                return True
            return False
        if self.stage < 1 and (reach - (e + s * r)) * s >= 0:
            self.got += 1 / 3
            self.left -= 1 / 3
            self.st, self.stage = e, 1
        if self.stage < 2 and (reach - (e + s * r * 2)) * s >= 0:
            self.got += 2 / 3
            self.left -= 1 / 3
            self.st, self.stage = e + s * r, 2
        if self.stage < 3 and (reach - (e + s * r * 3)) * s >= 0:
            self.got += self.left * 3.0
            self.left = 0.0
            return True
        return False

    def close(self, c):
        self.got += self.left * (c - self.entry) * self.side / self.risk
        self.left = 0.0
        return self.got - self.cost / self.risk


async def main():
    tic = C._real_time()
    db = sqlite3.connect(C.HIST, uri=True)
    pref = price_ref(db)
    cat = C.catalog()
    names = []
    for a in DECISION_ATOMS:
        for x in C.chain(cat, a):
            if x not in names:
                names.append(x)
    cfgs = atom_configs(cat)
    handlers = {}
    book = FS.FactBook()
    watched = {e for e in FS.EVENT_ATOM}
    piv = defaultdict(lambda: deque(maxlen=5))    # (إطار، قاع/قمّة) ⟵ آخر خمسة مستوياتٍ من 202 — لعيار «أقرب صالح»

    def make_publish(aid):
        async def publish(name, payload):
            if not isinstance(payload, dict):
                return
            if name in watched and str(payload.get("symbol") or "").upper() == SYM:
                book.put(name, payload, C._NOW[0])
                if name == "structure.external.state":
                    md = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                    for side_key in ("swing_low", "swing_high"):
                        v = FS.num(md.get(side_key))
                        hist = piv[(str(payload.get("timeframe") or ""), side_key)]
                        if v and (not hist or hist[-1] != v):
                            hist.append(v)
            for h in list(handlers.get(name, ())):
                await h(payload)
        return publish

    atoms = []
    tick_h = []
    for aid in names:
        mod = C.load(cat, aid)
        ctx = AtomContext(atom_id=int(aid), config=dict(cfgs[aid]), logger=_Log(), publish=make_publish(aid),
                          subscribe=lambda n, h, _a=aid: (tick_h.append(h) if _a == "254" and n == "market.tick.validated"
                                                          else None, handlers.setdefault(n, []).append(h)))
        atom = mod.Atom()
        await atom.initialize(ctx)
        await atom.start()
        for kname in ("_candle_kernel", "_live_kernel"):
            k = getattr(atom, kname, None)
            if k is not None:
                k.stop()
        atoms.append(atom)
    ch = handlers.get("market_data.candle_closed", [])
    import importlib.util
    d103 = C.ROOT / "atoms" / "قسم 100-149" / "103_باني_الشموع"
    spec = importlib.util.spec_from_file_location("_cs103", d103 / "atom.py")
    m103 = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(d103))
    spec.loader.exec_module(m103)
    fps = m103.frame_period_start

    var = variants()
    prev = {}
    open_tr = {}
    agg = defaultdict(lambda: [0, 0.0, 0])     # (عيار، استراتيجيّة، إطار، يوم) ⟵ [صفقات، مجموع R، رابحة]

    def book_trade(key, tr, r):
        a = agg[(key[0], key[1], key[2], tr.day)]
        a[0] += 1
        a[1] += r
        a[2] += r > 0

    async def emit(t, fr, k, o, h, l, c):
        C._NOW[0] = t
        pl = {"account_id": "bench", "broker": "bench", "provider": "ctrader_history", "symbol": SYM, "open": o,
              "high": h, "low": l, "close": c, "volume": 0.0, "tick_count": 0, "fabric_gap": False, "timeframe": fr,
              "period_start": float(k), "timestamp": float(k)}
        for hd in ch:
            await hd(dict(pl))

    def pick_stop(side, entry, sel):
        """عيار الوقف: الإطارات بالترتيب المعطى، وفي كلٍّ أحدث «عمق» مستوياتٍ — أوّل ما يقع داخل المدى."""
        order, depth = sel
        lo, hi = FS.STOP_PTS[SYM]
        pad = FS.STOP_PAD_PTS[SYM]
        for tf in order:
            for lvl in reversed(list(piv[(tf, "swing_low" if side > 0 else "swing_high")])[-depth:]):
                stop = lvl - pad if side > 0 else lvl + pad
                risk = (entry - stop) * side
                if lo <= risk <= hi:
                    return stop, risk, tf
        return None

    def evaluate(m, close, scale):
        sess = FS.session_of(m, SYM)
        day = datetime.fromtimestamp(m, timezone.utc).strftime("%Y-%m-%d")
        for vname, (patch, strats) in var.items():
            for k2, v in LIVE.items():
                setattr(FS, k2, patch.get(k2, v))
            sf = patch.get("STOP", 1.0)
            blo, bhi = patch.get("BAND", (1.0, 1.0))
            FS.STOP_PTS[SYM] = (STOP_LIVE[0] * scale * sf * blo, STOP_LIVE[1] * scale * sf * bhi)
            FS.STOP_PAD_PTS[SYM] = PAD_LIVE * scale
            use_factors = patch.get("FACTORS", True)
            for strat in strats:
                for tf in FS.FRAMES:
                    key = (vname, strat, tf)
                    s = FS.signal(strat, book, SYM, tf, m, close)
                    p = prev.get(key, 0)
                    prev[key] = s
                    if s == 0 or s == p or sess is None or key in open_tr:
                        continue
                    if use_factors and not FS.confirmed(strat, book, SYM, tf, s, close)[0]:
                        continue
                    hit = pick_stop(s, close, patch["SEL"]) if "SEL" in patch else FS.stop_for(book, SYM, s, close)
                    if hit is None:
                        continue
                    stop, risk, _ = hit
                    open_tr[key] = Trade(s, close, stop, risk, sess, m, patch.get("EXIT"), COST_LIVE * scale, day)

    t0 = datetime.fromisoformat(ARGS.start).replace(tzinfo=timezone.utc).timestamp()
    t1 = datetime.fromisoformat(ARGS.end).replace(tzinfo=timezone.utc).timestamp()
    eval_from = (datetime.fromisoformat(ARGS.eval_from).replace(tzinfo=timezone.utc).timestamp() if ARGS.eval_from
                 else t0 + 150 * 86400)
    pend = {}                                   # الإطار ⟵ [بداية، فتح، أعلى، أدنى، إغلاق]
    last_close = None
    month = t0
    n_min = 0
    prog = WORK / "progress.txt"
    while month < t1:
        nxt = datetime.fromtimestamp(month, timezone.utc)
        nxt = (nxt.replace(year=nxt.year + 1, month=1, day=1) if nxt.month == 12 else nxt.replace(month=nxt.month + 1, day=1)).timestamp()
        rows = db.execute("select period_start, open, high, low, close from candles_history where symbol=? and period='M1' "
                          "and period_start>=? and period_start<? order by period_start", (SYM, int(month), int(min(nxt, t1)))).fetchall()
        for ps, o, h, l, c in rows:
            # إطارٌ انتهت فترته قبل هذه الدقيقة (فجوة) ⟵ يُغلق بزمن نهايته أوّلًا.
            for fr, sec in FRAMES.items():
                b = pend.get(fr)
                if b is not None and fps(ps, sec) != b[0]:
                    await emit(b[0] + sec, fr, *b)
                    del pend[fr]
            # الكنس (254) يكتشف من التِّكّ وحده ولا تِكّات قبل ٢٠٢٥ ⟵ مسار الشمعة: فتح ثمّ الأدنى ثمّ الأعلى ثمّ إغلاق
            # (الصاعدة) أو فتح ثمّ الأعلى ثمّ الأدنى ثمّ إغلاق (الهابطة) — تقريبٌ معلن.
            for dt, px in ((1, o), (20, l if c >= o else h), (40, h if c >= o else l), (59, c)):
                C._NOW[0] = ps + dt
                tk = {"account_id": "bench", "broker": "bench", "provider": "CTRADER", "symbol": SYM, "bid": px, "ask": px,
                      "price": px, "mid": px, "volume": 0.0, "timestamp": ps + dt, "source_timestamp": ps + dt, "ts": ps + dt}
                for hd in tick_h:
                    await hd(tk)
            m = ps + 60
            for fr, sec in FRAMES.items():
                k = fps(ps, sec)
                b = pend.get(fr)
                if b is None:
                    pend[fr] = [k, o, h, l, c]
                else:
                    b[2], b[3], b[4] = max(b[2], h), min(b[3], l), c
            # الصفقات المفتوحة: نهاية الجلسة أوّلًا ثمّ الشمعة.
            if open_tr:
                cur = FS.session_of(m, SYM)
                for key in list(open_tr):
                    tr = open_tr[key]
                    if cur != tr.sess or m - tr.m0 > MAX_AGE_S:
                        book_trade(key, tr, tr.close(last_close))
                        del open_tr[key]
                    elif tr.bar(h, l):
                        book_trade(key, tr, tr.got - tr.cost / tr.risk)
                        del open_tr[key]
            # الإطارات التي تنتهي عند هذه الدقيقة: الدقيقة أوّلًا ثمّ الأكبر (ترتيب 103).
            for fr, sec in FRAMES.items():
                b = pend[fr]
                if b[0] + sec == m:
                    await emit(m, fr, *b)
                    del pend[fr]
            last_close = c
            n_min += 1
            if m >= eval_from or ARGS.smoke:     # التقييم بعد تسخينٍ؛ والحكم يبدأ من ٢٠١٦ في الحكم وحده
                C._NOW[0] = m
                evaluate(m, c, c / pref)
        month = nxt
        prog.write_text("%s · دقائق %d · ثوانٍ %d" % (datetime.fromtimestamp(month, timezone.utc).strftime("%Y-%m"), n_min,
                                                     int(C._real_time() - tic)), encoding="utf-8")
        if ARGS.smoke and n_min > 20000:
            break
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    path = out / (RUN_FILE + (".smoke" if ARGS.smoke else "") + ".csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("variant,strategy,frame,day,n,sumR,wins\n")
        for (v, s, tf, d), (n, r, w) in sorted(agg.items()):
            f.write("%s,%s,%s,%s,%d,%.4f,%d\n" % (v, s, tf, d, n, r, w))
    (WORK / "done.txt").write_text("%d دقيقة · %d ثانية" % (n_min, int(C._real_time() - tic)), encoding="utf-8")
    for a in atoms:
        try:
            await a.stop()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
