# -*- coding: utf-8 -*-
"""جدول التعلّم (سجلّ التنفيذ، الخطوة 7؛ تفويض المالك الكامل ١٠-١٢ — «فريق محلّلين» على طريقة سيمونز) — قياسٌ فقط.

لكلّ دقيقةٍ من نافذة الحكم (06:00–21:30 غرينتش) في كلّ يومٍ من سنة الحقائق المسجّلة (259 يومًا، ناسداك):
- **المدخلات:** آخر حقيقةٍ رقميّة لكلّ (ذرّة · عيار · إطار) حتى تلك اللحظة — من سجلّات سنة المشي إلى الأمام
  (`M:\\QUANT_NQ_DATA\\facts_year\\runs_year_<يوم>`)؛ مع الوقت (دقيقة اليوم، يوم الأسبوع) والمعرفة
  (أخبار أمريكا في آخر 15 دقيقة: عددها ومفاجأتها النسبيّة من تقويم الجسر).
- **النتيجة:** صفقة شراء وصفقة بيع من إغلاق الدقيقة بوقفٍ ثابت (15 و30 نقطة) وهدفٍ ضعفه، خلال 120 دقيقة على شموع
  سي‑تريدر الدقيقيّة؛ إن لمس الوقف والهدف في الشمعة نفسها يُحسب الوقف (تحفّظ)؛ وإن لم يُلمس أحدهما فالإغلاق بسعر
  نهاية المهلة. التكلفة 1.5 نقطة (السبريد). النتيجة بالمخاطرة (خسارة الوقف = 1)، فسقف المخاطرة بالدولار حجمٌ فقط.
الناتج: `M:\\QUANT_NQ_DATA\\learning\\table.npz` (مصفوفةٌ وأسماء أعمدتها).
"""
import gzip
import json
import math
import os
import pathlib
import sqlite3
import sys
import time
from datetime import datetime, timezone

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
FACTS = pathlib.Path(os.environ.get("FACTS_DIR", r"M:\QUANT_NQ_DATA\facts_year"))
OUT = pathlib.Path(os.environ.get("LEARN_DIR", r"M:\QUANT_NQ_DATA\learning"))
HISTORY = ROOT / "forex_runtime" / "var" / "history" / "ctrader_history.db"
BRIDGE = pathlib.Path(os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_brain.db"))
SYMBOL = "USTEC"
STOPS = (15.0, 30.0)
RR, HORIZON, COST = 2.0, 120, 1.5
STEP = int(os.environ.get("STEP_MIN", "5"))           # لحظة قرارٍ كلّ خمس دقائق (حجم الجدول)
WORDS = {"up": 1, "bullish": 1, "long": 1, "buy": 1, "higher": 1, "down": -1, "bearish": -1, "short": -1,
         "sell": -1, "lower": -1, "sideways": 0, "neutral": 0, "flat": 0, "none": 0}


def day_ts(day):
    return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def value(v):
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        w = WORDS.get(v.strip().lower())
        return None if w is None else float(w)
    return None


def load_day(folder):
    rows = []
    for f in sorted(folder.glob("*.json.gz")):
        d = json.load(gzip.open(f, "rt", encoding="utf-8"))
        tag = "%s@%s" % (d["tune"], d["tag"])
        for ts, atom, _event, frame, facts in d["rows"]:
            rows.append((float(ts), "%s|%s|%s" % (tag, atom, frame), facts))
    rows.sort(key=lambda r: r[0])
    return rows


def minute_bars(con, lo, hi):
    got = con.execute("SELECT period_start, high, low, close FROM candles_history WHERE symbol=? AND period='M1' "
                      "AND period_start>=? AND period_start<? ORDER BY period_start", (SYMBOL, int(lo), int(hi))).fetchall()
    return {int(r[0]): r[1:] for r in got}


def outcomes(bars, m, stop):
    """النتيجة بالمخاطرة لصفقة شراء وصفقة بيع من إغلاق الدقيقة المنتهية عند m، ومدّة الإمساك بالدقائق."""
    first = bars.get(int(m) - 60)
    if first is None:
        return None
    entry = first[2]
    res = []
    for side in (1, -1):
        sl, tp = entry - side * stop, entry + side * stop * RR
        r, held, last = None, HORIZON, entry
        for k in range(HORIZON):
            b = bars.get(int(m) + 60 * k)
            if b is None:
                continue
            hi, lo, last = b
            hit_sl = lo <= sl if side == 1 else hi >= sl
            hit_tp = hi >= tp if side == 1 else lo <= tp
            if hit_sl:
                r, held = -1.0, k + 1
                break
            if hit_tp:
                r, held = RR, k + 1
                break
        if r is None:
            r = side * (last - entry) / stop
        res.append((r - COST / stop, held))
    return res


def calendar_events():
    if not BRIDGE.exists():
        return []
    con = sqlite3.connect("file:%s?mode=ro" % BRIDGE, uri=True)
    out = []
    for at, country, actual, cons in con.execute(
            "SELECT scheduled_at, country, actual, consensus FROM econ_calendar WHERE scheduled_at IS NOT NULL"):
        if "United States" not in str(country) and "الولايات" not in str(country):
            continue
        a, c = num(actual), num(cons)
        surprise = 0.0 if a is None or c is None else max(-3.0, min(3.0, (a - c) / max(abs(c), 1e-6)))
        out.append((float(at), surprise))
    con.close()
    out.sort()
    return out


def num(text):
    try:
        t = str(text).replace("%", "").replace(",", "").strip()
        mult = 1.0
        if t[-1:] in "KMBT" and t:
            mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[t[-1]]
            t = t[:-1]
        return float(t) * mult if t else None
    except (ValueError, IndexError):
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    days = sorted(p for p in FACTS.glob("runs_year_*") if p.is_dir())[-int(os.environ.get("LIMIT_DAYS", "100000")):]
    hist = sqlite3.connect("file:%s?mode=ro" % HISTORY, uri=True)
    cal = calendar_events()
    cal_t = np.array([c[0] for c in cal]) if cal else np.zeros(0)
    columns, blocks, meta, labels, day_rows = {}, [], [], [], []
    t0 = time.time()
    for n, folder in enumerate(days, 1):
        day = folder.name.replace("runs_year_", "")
        base = day_ts(day)
        minutes = np.arange(base + 6 * 3600 + 60, base + 21.5 * 3600 + 1, 60)
        bars = minute_bars(hist, base, base + 86400 + HORIZON * 60)
        rows = load_day(folder)
        state, i = {}, 0
        for m in minutes:
            while i < len(rows) and rows[i][0] <= m:
                _, key, facts = rows[i]
                for k, v in facts.items():
                    x = value(v)
                    if x is not None:
                        state[key + "|" + k] = x
                i += 1
            ys = []
            for stop in STOPS:
                o = outcomes(bars, m, stop)
                if o is None:
                    break
                ys.extend([o[0][0], o[1][0], o[0][1], o[1][1]])
            if len(ys) != 4 * len(STOPS) or not state:
                continue
            j = np.searchsorted(cal_t, m - 900) if cal else 0
            k = np.searchsorted(cal_t, m, side="right") if cal else 0
            recent = cal[j:k]
            dt = datetime.fromtimestamp(m, timezone.utc)
            extra = {"time|minute_utc": dt.hour * 60 + dt.minute, "time|weekday": dt.weekday(),
                     "news|us_count_15m": len(recent), "news|us_surprise_15m": sum(s for _, s in recent)}
            if int(m // 60) % STEP:
                continue
            row = dict(state)
            row.update(extra)
            for c in row:
                if c not in columns:
                    columns[c] = len(columns)
            vec = np.full(len(columns), np.nan, dtype=np.float32)
            for c, v in row.items():
                vec[columns[c]] = v
            day_rows.append(vec)
            meta.append(m)
            labels.append(ys)
        width = len(columns)
        for vec in day_rows:
            blocks.append(np.pad(vec, (0, width - len(vec)), constant_values=np.nan) if len(vec) < width else vec)
        day_rows = []
        if n % 20 == 0:
            print("يوم %d/%d · صفوف %d · أعمدة %d · %.0f ث" % (n, len(days), len(blocks), len(columns), time.time() - t0),
                  flush=True)
    width = len(columns)
    X = np.full((len(blocks), width), np.nan, dtype=np.float32)
    for r, vec in enumerate(blocks):
        X[r, :len(vec)] = vec
    names = sorted(columns, key=columns.get)
    ylab = ["%s_%d" % (kind, int(s)) for s in STOPS for kind in ("long_r", "short_r", "long_held", "short_held")]
    np.savez_compressed(OUT / "table.npz", X=X, y=np.array(labels, dtype=np.float32), t=np.array(meta),
                        names=np.array(names), ylab=np.array(ylab))
    print("✓ الجدول: %d صفًّا × %d عمودًا ⟵ %s" % (X.shape[0], X.shape[1], OUT / "table.npz"), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
