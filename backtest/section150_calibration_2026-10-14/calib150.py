# -*- coding: utf-8 -*-
"""معايرة ذرّات قسم التحليل كلّ واحدةٍ وحدها — بلا استراتيجيّة (أمر المالك ١٠-١٤ بعد ذرّة الزخم: «خود باقي زرات قسم تحليل وعملهم
نفس اختبار لا كلهم»). الاختبار نفسه الذي عويرت به 152، لكن بكود الذرّة الحيّ نفسه (لا إعادة كتابة لمعادلاتها).

تشغيلٌ واحد = ذرّةٌ واحدة بإعدادٍ واحد مغيَّر (والبقيّة على الحيّ): شموع الناسداك من شموع الدقيقة (2014-07 ⟵ اليوم) تُبنى منها
1د 5د 15د 1س 4س بدالّة 103 الحيّة، وتُغذّى بها الذرّة بترتيب إغلاقها. كلّ رقمٍ تنشره الذرّة (بعد عقد الحقائق) يُحفظ كلّ 5 شموع،
ثمّ يُقاس ارتباط رتبه بعائد الشموع الخمس التالية سنةً بسنة:
  رقمٌ بإشارتين (موجب وسالب)       ⟵ على العائد نفسه (هل يسبق الجهة).
  رقمٌ بإشارةٍ واحدة (حجم/نسبة)      ⟵ على |العائد| (هل يسبق حجم الحركة).
  رقمٌ بمستوى السعر (وسيط بُعده عن الإغلاق < 5٪، كالمتوسّط) ⟵ يُقرأ بُعدَ الإغلاق عنه ٪ ⟵ على العائد.
  رقمٌ ثابتٌ لا يتغيّر (صدى إعداد) يُترك.
يُستبعد أفقٌ يعبر فجوةً أطول من 3 ساعات. التذبذب 153 بلا إطار الدقيقة (كوده يجمع آلاف القيم لكلّ شمعة — معلن).

الاستعمال: python calib150.py --atom 165 --param window --value 400 [--quick]
  --quick: آخر 60 ألف دقيقة فقط — لفحص «هل يغيّر هذا الإعداد أيّ رقمٍ منشور؟» قبل التشغيل الكامل.
الناتج: out/<الذرّة>__<الإعداد>__<القيمة>.json (أو quick/…)
"""
import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--atom", required=True)
ap.add_argument("--param", required=True)
ap.add_argument("--value", required=True)
ap.add_argument("--quick", action="store_true")
ap.add_argument("--prep", action="store_true", help="يبني مخزن الشموع المشترك ويخرج")
ap.add_argument("--dest", default="", help="مجلّد الناتج (افتراضه quick أو out)")
ap.add_argument("--chain", action="store_true", help="الذرّة ومن يبني عليها في قسمها، وتُسجَّل حقائقهم كلّهم")
ap.add_argument("--no1m", action="store_true", help="بلا إطار الدقيقة (قسم الإحصاء ١٠-١٤: ثقل الكود)")
ARGS = ap.parse_args()
TAG = "%s__%s__%s" % (ARGS.atom, ARGS.param, ARGS.value)
WORK = HERE / "work" / (("q_" if ARGS.quick else "") + TAG)
WORK.mkdir(parents=True, exist_ok=True)
os.environ["CALIB_SCRATCH"] = str(WORK)
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(WORK / "run.log", "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(HERE.parent / "s150_calibration_2026-10-09"))
sys.path.insert(0, str(HERE.parent / "momentum_atom_calibration_2026-10-14"))
import calib_day as C  # noqa: E402  (ساعة البيانات _NOW ومخزن الإعدادات المسوّدة)
from calib152 import spearman  # noqa: E402
from core.contracts.atom import AtomContext  # noqa: E402

FRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
NO_1M = {"153"}
H, STEP, GAP = 5, 5, 3 * 3600
TEST_END = 1759276800          # 2025-10-01 غرينتش
SKIP = {"period_start", "candles", "close", "count", "points", "timestamp", "computed_on"}
QUICK_MINUTES = int(os.environ.get("CALIB150_QUICK_MINUTES") or 60000)
#: حقول رأس الحمولة النصّيّة التي تبقى بعد عقد الحقائق (أسماء الأحداث والحالة) — تدخل بصمة الفحص السريع.
TEXT_TOP = ("signal", "state", "phase", "level", "status")
#: أسماءٌ جهتها في معناها (قسم البنية): قمّةٌ/قمّةٌ أعلى/قاعٌ أعلى = +1، قاعٌ/قاعٌ أدنى/قمّةٌ أدنى = −1 — فموجبٌ في «الجهة» = استمرار.
DIR_WORDS = {"above": 1, "below": -1, "swing_high": 1, "swing_low": -1, "HH": 1, "HL": 1, "LL": -1, "LH": -1}


def parse_value(live, raw):
    if isinstance(live, bool):
        return raw.lower() in ("1", "true")
    if isinstance(live, int):
        return int(float(raw))
    return float(raw)


def frame_bars(t, o, h, l, c, sec, fps):
    if sec <= 3600:
        k = t - t % sec
    else:
        hours, inv = np.unique(t // 3600, return_inverse=True)
        k = np.array([fps(float(x * 3600), float(sec)) for x in hours], dtype=np.int64)[inv]
    st = np.r_[0, np.nonzero(np.diff(k))[0] + 1]
    end = np.r_[st[1:] - 1, len(k) - 1]
    return k[st], o[st], np.maximum.reduceat(h, st), np.minimum.reduceat(l, st), c[end]


CHUNK = 200000
CACHE = HERE / "cache"
#: حارس الذاكرة داخل التشغيل (١٠-١٤ بعد امتلاء الذاكرة مرّتين): يتوقّف التشغيل وحده إن تجاوز هذا الحدّ، فلا يتجمّد الجهاز.
MAX_RSS_MB = int(os.environ.get("CALIB150_MAX_MB") or 2000)


def rss_mb():
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]
    c = PMC()
    c.cb = ctypes.sizeof(PMC)
    # مقبض العمليّة الوهميّ (−1) يجب أن يُعرَّف مقبضًا كاملًا — بلا ذلك يُبتر إلى 32 بتًّا فيفشل السؤال ويعود صفرًا (١٠-١٤).
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    ps = ctypes.WinDLL("psapi")
    ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    ps.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.PagefileUsage / 1048576


def load_bars(frames, fps):
    """شموع الإطارات وترتيب أحداثها من مخزنٍ مشترك على القرص يُقرأ بلا نسخ — لا يحمّل كلّ تشغيلٍ ملايين الدقائق في ذاكرته
    (اثنا عشر تشغيلًا فعلت ذلك فجمّد الجهاز ١٠-١٤ 01:05). يبنيه «--prep» مرّةً؛ والفحص السريع يبني آخر 60 ألف دقيقة في الذاكرة."""
    names = list(frames)
    key = "_".join(names)
    if not ARGS.quick and (CACHE / ("ev_%s_t.npy" % key)).exists():
        bars = {fr: tuple(np.load(CACHE / ("%s_%s.npy" % (fr, c)), mmap_mode="r") for c in "KOHLC") for fr in names}
        ev = tuple(np.load(CACHE / ("ev_%s_%s.npy" % (key, c)), mmap_mode="r") for c in "tfi")
        return bars, ev, names
    db = sqlite3.connect(C.HIST, uri=True)
    q = "select period_start, open, high, low, close from candles_history where symbol='USTEC' and period='M1' "
    if ARGS.quick:                                   # آخر الدقائق وحدها من المخزن (لا تحميل التاريخ كلّه لكلّ فحصٍ سريع)
        a = np.array(db.execute(q + "order by period_start desc limit ?", (QUICK_MINUTES,)).fetchall(), dtype=np.float64)[::-1]
    else:
        a = np.array(db.execute(q + "order by period_start").fetchall(), dtype=np.float64)
    db.close()
    t = a[:, 0].astype(np.int64)
    bars = {fr: frame_bars(t, a[:, 1], a[:, 2], a[:, 3], a[:, 4], sec, fps) for fr, sec in frames.items()}
    del a, t
    ev_t, ev_f, ev_i = [], [], []
    for n, (fr, sec) in enumerate(frames.items()):
        K = bars[fr][0]
        ev_t.append(K + sec)
        ev_f.append(np.full(len(K), n, dtype=np.int8))
        ev_i.append(np.arange(len(K), dtype=np.int64))
    ev_t, ev_f, ev_i = np.concatenate(ev_t), np.concatenate(ev_f), np.concatenate(ev_i)
    order = np.lexsort((ev_f, ev_t))                 # زمن الإغلاق ثمّ الإطار الأصغر أوّلًا (ترتيب 103)
    ev = (ev_t[order], ev_f[order], ev_i[order])
    if not ARGS.quick:
        CACHE.mkdir(exist_ok=True)
        for fr in names:
            for c, arr in zip("KOHLC", bars[fr]):
                np.save(CACHE / ("%s_%s.npy" % (fr, c)), arr)
        for c, arr in zip("tfi", ev):
            np.save(CACHE / ("ev_%s_%s.npy" % (key, c)), arr)
    return bars, ev, names


def _yearly(x, y, years, ks):
    m = np.isfinite(x) & np.isfinite(y)
    per_year = {}
    for yr in sorted(set(years[m].tolist())):
        sel = m & (years == yr) & ((ks < TEST_END) if yr == 2025 else True)
        ic = spearman(x[sel], y[sel])
        if ic is not None:
            per_year[int(yr)] = [round(ic, 4), int(sel.sum())]
    ref = m & (ks >= TEST_END)
    return {"years": per_year, "ref": spearman(x[ref], y[ref])}


def labels(txt_fr, bar, idx, fwd, years, ks):
    """اختبار الأسماء (١٠-١٤، ختم المالك «Nq»): لكلّ اسمٍ تنشره الذرّة (اسم النمط · كلمة الحالة) مؤشّرٌ 1/0 على شموع العيّنة،
    وارتباط رتبه سنةً بسنة مع (أ) حجم الشموع الخمس التالية، و(ب) عائدها في جهة الشمعة نفسها (جهة الجسم؛ وللدبّوس جهة ذيله
    الأطول) — هل يسبق الاسم حركةً أكبر/أصغر، وهل تستمرّ الشمعة أو تنعكس."""
    _, O, Hh, L, Cc = bar
    o, h, l, c = O[idx], Hh[idx], L[idx], Cc[idx]
    body = np.sign(c - o)
    wick = np.sign((np.minimum(o, c) - l) - (h - np.maximum(o, c)))
    out, seen = {}, set()
    for field, (vocab, codes) in txt_fr.items():
        if field.endswith("^status") or field.endswith("bench_signal") or not vocab:
            continue
        names = sorted(vocab, key=vocab.get)
        sig = hashlib.md5(codes.tobytes() + json.dumps(names).encode("utf-8")).hexdigest()
        if sig in seen:
            continue                                   # الاسم نفسه في حقلين (النمط ورأس الحمولة) يُعدّ مرّةً
        seen.add(sig)
        known = codes >= 0
        if known.sum() < 1000:
            continue
        for lab in sorted(vocab):
            ind = np.where(known, (codes == vocab[lab]).astype(float), np.nan)
            share = float(np.nanmean(ind))
            if not 0.005 <= share <= 0.995:
                continue
            # جهة الاسم: كلمة جهةٍ صريحة (كسرٌ فوق/تحت) تُقرأ كما هي؛ والدبّوس جهة ذيله؛ وغيرهما جهة جسم الشمعة.
            side = (np.full(len(idx), float(DIR_WORDS[lab])) if lab in DIR_WORDS else wick if lab == "pin_bar" else body)
            out.setdefault(field, {})[lab] = {"share": round(share, 4),
                                               "size": _yearly(ind, np.abs(fwd), years, ks),
                                               "dir": _yearly(ind * side, fwd, years, ks)}
    return out


async def main():
    tic = C._real_time()
    cat = C.catalog()
    aid = ARGS.atom
    cfg = dict(cat[aid]["config"])
    if ARGS.param != "live":
        live_v = cfg[ARGS.param]
        v = parse_value(live_v, ARGS.value)
        cfg[ARGS.param] = v
        if "min_candles" in cfg and isinstance(v, int) and not isinstance(v, bool) and v > cfg["min_candles"]:
            cfg["min_candles"] = v             # الإحماء لا يقلّ عن النافذة المجرَّبة
    import importlib.util
    d103 = C.ROOT / "atoms" / "قسم 100-149" / "103_باني_الشموع"
    spec = importlib.util.spec_from_file_location("_c103", d103 / "atom.py")
    m103 = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(d103))
    spec.loader.exec_module(m103)
    frames = {fr: s for fr, s in FRAMES.items() if not ((aid in NO_1M or ARGS.no1m) and fr == "1m")}
    bars, (ev_t, ev_f, ev_i), names = load_bars(frames, m103.frame_period_start)
    if ARGS.prep:
        print("المخزن جاهز", flush=True)
        return
    rec = {fr: {} for fr in frames}
    txt = {fr: {} for fr in frames}
    nsamp = {fr: (len(bars[fr][0]) + STEP - 1) // STEP for fr in frames}
    cur = [None, -1]

    handlers = {}
    # ١٠-١٤ (قسم البنية): «--chain» يشغّل الذرّة ومن يبني عليها في قسمها (ومن يغذّيهم)، ويسجّل حقائق ذرّات القسم كلّها
    # بأسماءٍ مسبوقةٍ برقم الذرّة — فالإعداد الواحد يُحكم عليه بكلّ ما يغيّره في القسم.
    if ARGS.chain:
        section = [a for a in C.downstream(cat, aid) if a[:2] == aid[:2]]
        run_ids = []
        for a in section:
            for x in C.chain(cat, a):
                if x not in run_ids:
                    run_ids.append(x)
        record = set(section)
    else:
        run_ids, record = [aid], {aid}

    def make_publish(src):
        async def publish(name, payload):
            await keep(src, payload)
            for h in list(handlers.get(name, ())):
                await h(payload)
        return publish

    async def keep(src, payload):
        fr, i = cur
        if src not in record or fr is None or i % STEP or not isinstance(payload, dict) \
                or str(payload.get("timeframe") or "") != fr:
            return
        pre = (src + ".") if ARGS.chain else ""
        md = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        # «bench_signal» حكم الذرّة قبل نزعه (أداة القياس تضيفه للعلم) — لا يُنشر حيًّا فلا يُقاس؛ وحقول الوقت ليست حقائق سوق.
        for k2, v2 in [(pre + k, v) for k, v in md.items()
                       if k not in SKIP and k != "bench_signal" and not k.endswith("_time")] + \
                [(pre + "^" + k, v) for k, v in payload.items() if k in TEXT_TOP]:
            if isinstance(v2, str) and k2 not in SKIP and len(v2) <= 32:
                # ١٠-١٤: الحقائق النصّيّة (اسم النمط · الحالة) تُحفظ لبصمة «هل يغيّر الإعداد شيئًا» — كان الفحص على الأرقام
                # وحدها فحكم على عتبات ذرّة الشموع بالموت وهي تغيّر اسم النمط.
                # رمزٌ صغير لكلّ اسم في مصفوفة (لا قاموس بملايين المدخلات — سلسلة البنية ملأت الذاكرة ١٠-١٤ 12:37).
                slot = txt[fr].get(k2)
                if slot is None:
                    slot = txt[fr][k2] = ({}, np.full(nsamp[fr], -1, dtype=np.int16))
                code = slot[0].get(v2)
                if code is None and len(slot[0]) < 1000:      # نصٌّ بقيمٍ لا تُحصى ليس اسمًا
                    code = slot[0][v2] = len(slot[0])
                slot[1][i // STEP] = -1 if code is None else code
                continue
            if k2 in SKIP or isinstance(v2, bool) or not isinstance(v2, (int, float)):
                continue
            arr = rec[fr].get(k2)
            if arr is None:
                arr = rec[fr][k2] = np.full(nsamp[fr], np.nan)
            arr[i // STEP] = v2

    atoms = []
    for a in run_ids:
        mod = C.load(cat, a)
        ctx = AtomContext(atom_id=int(a), config=cfg if a == aid else dict(cat[a]["config"]), logger=C._Log(),
                          publish=make_publish(a), subscribe=lambda n, h: handlers.setdefault(n, []).append(h))
        atom = mod.Atom()
        await atom.initialize(ctx)
        await atom.start()
        for kname in ("_candle_kernel", "_live_kernel"):
            k = getattr(atom, kname, None)
            if k is not None:
                k.stop()
        atoms.append(atom)
    ch = handlers.get("market_data.candle_closed", [])
    peak = 0.0
    for s0 in range(0, len(ev_t), CHUNK):           # على دفعات: لا قوائم ضخمة في الذاكرة (جمّد الجهاز ١٠-١٤ 01:05)
        peak = max(peak, rss_mb())
        if peak > MAX_RSS_MB:
            print(TAG, "توقّف: الذاكرة %d ميغا فوق الحدّ %d" % (peak, MAX_RSS_MB), flush=True)
            sys.exit(3)
        for tt, ff, i in zip(ev_t[s0:s0 + CHUNK].tolist(), ev_f[s0:s0 + CHUNK].tolist(), ev_i[s0:s0 + CHUNK].tolist()):
            fr = names[ff]
            K, O, Hh, L, Cc = bars[fr]
            C._NOW[0] = float(tt)
            cur[0], cur[1] = fr, i
            pl = {"account_id": "bench", "broker": "bench", "provider": "ctrader_history", "symbol": "USTEC",
                  "open": float(O[i]), "high": float(Hh[i]), "low": float(L[i]), "close": float(Cc[i]), "volume": 0.0,
                  "tick_count": 0, "fabric_gap": False, "timeframe": fr, "period_start": float(K[i]),
                  "timestamp": float(K[i])}
            for hd in ch:
                await hd(pl)
    for atom in atoms:
        try:
            await atom.stop()
        except Exception:
            pass
    # الحكم لكلّ رقم.
    out = {"atom": aid, "param": ARGS.param, "value": ARGS.value, "frames": {}, "digest": {}}
    for fr, sec in frames.items():
        K, _, _, _, Cc = bars[fr]
        idx = np.arange(0, len(K), STEP)
        fwd = np.full(len(idx), np.nan)
        ok = idx + H < len(K)
        j = idx[ok]
        good = (K[j + H] - K[j]) <= H * sec + GAP
        fwd[np.nonzero(ok)[0][good]] = np.log(Cc[j[good] + H] / Cc[j[good]]) * 1e4
        years = K[idx].astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
        ks = K[idx]
        cs = Cc[idx]
        res = {}
        for field, v in rec[fr].items():
            fin = np.isfinite(v)
            if fin.sum() < 100:
                continue
            out["digest"]["%s|%s" % (fr, field)] = hashlib.md5(np.round(np.nan_to_num(v, nan=-9e9), 6).tobytes()).hexdigest()
            vv = v[fin]
            if np.nanstd(vv) == 0:
                continue                                   # صدى إعدادٍ ثابت
            kind = "signed"
            x = v.copy()
            if np.nanmedian(np.abs(v / cs - 1.0)) < 0.05:     # يلاصق السعر (متوسّطٌ مثلًا) — لا حجمٌ صادف قربه
                x = (cs - v) / v * 100.0                  # مستوى سعر ⟵ بُعد الإغلاق عنه ٪
                kind = "level"
            elif not ((vv < 0).mean() >= 0.01 and (vv > 0).mean() >= 0.01):
                kind = "size"
            y = np.abs(fwd) if kind == "size" else fwd
            m = np.isfinite(x) & np.isfinite(y)
            per_year = {}
            for yr in sorted(set(years[m].tolist())):
                sel = m & (years == yr) & ((ks < TEST_END) if yr == 2025 else True)
                ic = spearman(x[sel], y[sel])
                if ic is not None:
                    per_year[int(yr)] = [round(ic, 4), int(sel.sum())]
            ref = m & (ks >= TEST_END)
            res[field] = {"kind": kind, "years": per_year, "ref": spearman(x[ref], y[ref]), "ref_n": int(ref.sum())}
        out["frames"][fr] = res
        for field, (vocab, codes) in txt[fr].items():
            out["digest"]["txt|%s|%s" % (fr, field)] = hashlib.md5(
                codes.tobytes() + json.dumps(sorted(vocab, key=vocab.get)).encode("utf-8")).hexdigest()
        out.setdefault("labels", {})[fr] = labels(txt[fr], bars[fr], idx, fwd, years, ks)
    out["secs"] = int(C._real_time() - tic)
    out["peak_mb"] = int(max(peak, rss_mb()))
    dest = HERE / (ARGS.dest or ("quick" if ARGS.quick else "out"))
    dest.mkdir(exist_ok=True)
    (dest / (TAG + ".json")).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(TAG, "تمّ", out["secs"], "ث", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
