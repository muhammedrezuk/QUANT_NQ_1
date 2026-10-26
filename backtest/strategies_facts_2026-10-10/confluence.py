# -*- coding: utf-8 -*-
"""الاستراتيجيّات السبع بعوامل متعدّدة لا عاملٍ واحد — قياسٌ فقط (أمر المالك «NQ قيس» ٢٠٢٦-١٠-١٠).

النقاش (ورقة عقل القرار، «نقاش ١٠-١٠ مساءً»): «الانعكاس على عامل واحد جريمة … لازم ينضاف لكلّ استراتيجيّة ما تحتاجه من
عوامل — ما بيصير عامل واحد». لكلّ استراتيجيّة: زنادها الأصليّ (strategies_facts.signal) شرطٌ، ومعه عواملها من الأقسام، وثلاث
طرق: «واحد» (الزناد وحده = ما يعمل حيًّا اليوم) · «الأغلبيّة» (الزناد + نصف العوامل فأكثر) · «الكلّ» (الزناد + كلّ العوامل).
الصفقة كما في strategies_facts: الدخول عند إغلاق الدقيقة، وقف 202 ضمن 15–45، أثلاث المالك، 3R، كلفة 1.5، الجلستان، 23 يومًا.

ما تغيّر عن اقتراح النقاش لأنّ الحقائق لا تسمح (موثّق): 207 لا تنشر جهة حيًّا ⟸ اتّجاه الساعة و4س من 151 · 156 لا تنشر جهة
⟸ الرفض = نمط (دبّوس/ابتلاع) وذيل الجهة أطول · «المستوى الكبير» = آخر قمّة/قاع خارجيّ على الساعة و4س من 202.
"""
import gzip
import json
import math
import pathlib
import pickle
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import strategies_facts as SF  # noqa: E402

D = pathlib.Path(__file__).resolve().parent
EXTRA_TUNES = ("153", "156", "163", "358")
HIGHER = {"1m": "5m", "5m": "15m", "15m": "1h", "1h": "4h", "tick": "5m"}
LEVEL_BPS = 10.0          # «عند المستوى»: ضمن 10 نقاط أساس (~30 نقطة ناسداك)
AHEAD_BPS = 20.0          # «لا مستوى أمامه»: لا قمّة/قاع كبير ضمن 20 نقطة أساس في الجهة
RECENT_MIN = 15           # حدثٌ «حديث»: خلال 15 دقيقة


class Facts(SF.Facts):
    def __init__(self, day, adopt):
        super().__init__(day, adopt)
        for tune in EXTRA_TUNES:
            blob = json.load(gzip.open(SF.SCRATCH / f"runs_{day}" / f"{tune}__{adopt.get(tune, 'live')}.json.gz",
                                       "rt", encoding="utf-8"))
            for t, aid, ev, tf, row in blob["rows"]:
                for k, v in row.items():
                    ts, vs = self.s[(aid, tf, k)]
                    ts.append(t)
                    vs.append(v)

    def recent(self, aid, tf, key, m, minutes=RECENT_MIN):
        ts, vs = self.s.get((aid, tf, key), ((), ()))
        out = []
        for i in range(len(ts) - 1, -1, -1):
            if ts[i] > m:
                continue
            if ts[i] <= m - minutes * 60:
                break
            out.append((ts[i], vs[i]))
        return out


def num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def trend_dir(f, tf, m):
    fast, slow = num(f.at("151", tf, "m.ema_fast", m)), num(f.at("151", tf, "m.ema_slow", m))
    fv, sv = num(f.at("151", tf, "m.ema_fast_value", m)), num(f.at("151", tf, "m.ema_slow_value", m))
    if None in (fast, slow, fv, sv) or fv == sv:
        return 0
    short, long_ = (fv, sv) if fast < slow else (sv, fv)
    return 1 if short > long_ else -1


def htf_trend(f, d, m):
    return trend_dir(f, "1h", m) == d and trend_dir(f, "4h", m) == d


def no_htf_trend(f, d, m):
    return trend_dir(f, "1h", m) != trend_dir(f, "4h", m)


def mom(f, tf, d, m):
    roc = num(f.at("152", tf, "m.roc", m))
    return roc is not None and roc * d > 0


def accel(f, tf, m):
    r = num(f.at("163", "5m" if tf == "tick" else tf, "m.ratio", m))
    return r is not None and r > 0


def decel(f, tf, m):
    r = num(f.at("163", "5m" if tf == "tick" else tf, "m.ratio", m))
    return r is not None and r < 0


def efficient(f, tf, m):
    e = num(f.at("165", "5m" if tf == "tick" else tf, "m.efficiency_ratio", m))
    return e is not None and e >= SF.RANGE_EFF


def choppy(f, tf, m):
    e = num(f.at("165", "5m" if tf == "tick" else tf, "m.efficiency_ratio", m))
    return e is not None and e < SF.RANGE_EFF


def vol_expanding(f, tf, m):
    r = num(f.at("153", "5m" if tf == "tick" else tf, "m.ratio", m))
    return r is not None and r > 1.0


def z_of(f, m):
    return num(f.at("310", "tick", "m.value", m))


def not_stretched(f, m):
    z = z_of(f, m)
    return z is not None and abs(z) < SF.Z_TH


def stretched(f, d, m):
    z = z_of(f, m)
    return z is not None and (z <= -SF.Z_TH if d > 0 else z >= SF.Z_TH)


def at_level(f, d, m, close):
    for tf in ("1h", "4h"):
        lvl = num(f.at("202", tf, "m.swing_low" if d > 0 else "m.swing_high", m))
        if lvl and abs(close - lvl) / close * 1e4 <= LEVEL_BPS:
            return True
    return False


def no_level_ahead(f, d, m, close):
    for tf in ("1h", "4h"):
        lvl = num(f.at("202", tf, "m.swing_high" if d > 0 else "m.swing_low", m))
        if lvl and 0 < (lvl - close) * d and (lvl - close) * d / close * 1e4 <= AHEAD_BPS:
            return False
    return True


def swept(f, d, m):
    want = "sell_side" if d > 0 else "buy_side"
    for tf in ("1m", "5m"):
        sig = dict(f.recent("254", tf, "signal", m, 5))
        for t, v in f.recent("254", tf, "m.direction", m, 5):
            if v == want and sig.get(t) == "sweep":
                return True
    return False


def rejection(f, d, m):
    for tf in ("1m", "5m"):
        pat = f.at("156", tf, "m.pattern", m)
        up, lo = num(f.at("156", tf, "m.upper_wick", m)), num(f.at("156", tf, "m.lower_wick", m))
        if pat in ("pin_bar", "engulfing") and up is not None and lo is not None and (lo > up if d > 0 else up > lo):
            return True
    return False


def choch(f, d, m, tfs=("1m", "5m")):
    want = "above" if d > 0 else "below"
    for tf in tfs:
        sig = dict(f.recent("205", tf, "signal", m))
        if any(v == want and sig.get(t) == "choch" for t, v in f.recent("205", tf, "m.break_side", m)):
            return True
    return False


def at_mean(f, tf, d, m, close):
    mean = num(f.at("151", tf, "m.ema_slow_value", m))
    return bool(mean) and (close - mean) * d <= 0


def hurst_reverting(f, m):
    h = num(f.at("358", "tick", "m.hurst", m))
    return h is not None and h < 0.5


def range_edge(f, d, m):
    p = num(f.at("315", "tick", "m.position", m))
    return p is not None and (p <= SF.EDGE if d > 0 else p >= 1 - SF.EDGE)


#: عوامل كلّ استراتيجيّة (اقتراح النقاش) — كلٌّ دالّة (f, tf, d, m, close) ⟶ صح/خطأ.
FACTORS = {
    "404": [("اتّجاه الساعة و4س", lambda f, tf, d, m, c: htf_trend(f, d, m)),
            ("زخم بالجهة", lambda f, tf, d, m, c: mom(f, tf, d, m)),
            ("لا مستوى أمامه", lambda f, tf, d, m, c: no_level_ahead(f, d, m, c))],
    "405": [("عند مستوى ساعة/4س", lambda f, tf, d, m, c: at_level(f, d, m, c)),
            ("كنس أو رفض", lambda f, tf, d, m, c: swept(f, d, m) or rejection(f, d, m)),
            ("تباطؤ", lambda f, tf, d, m, c: decel(f, tf, m)),
            ("كسر طابع صغير", lambda f, tf, d, m, c: choch(f, d, m))],
    "406": [("اتّجاه أكبر موافق", lambda f, tf, d, m, c: htf_trend(f, d, m)),
            ("زخم موافق", lambda f, tf, d, m, c: mom(f, tf, d, m)),
            ("تذبذب يتّسع", lambda f, tf, d, m, c: vol_expanding(f, tf, m)),
            ("حركة نظيفة", lambda f, tf, d, m, c: efficient(f, tf, m))],
    "407": [("اتّجاه أكبر", lambda f, tf, d, m, c: htf_trend(f, d, m)),
            ("عند المتوسّط", lambda f, tf, d, m, c: at_mean(f, tf, d, m, c)),
            ("لا كسر ضدّه", lambda f, tf, d, m, c: not choch(f, -d, m, (tf if tf != "tick" else "5m",))),
            ("زخم الدقيقة يعود", lambda f, tf, d, m, c: mom(f, "1m", d, m)),
            ("شمعة رفض", lambda f, tf, d, m, c: rejection(f, d, m))],
    "408": [("زخم الإطار الأكبر", lambda f, tf, d, m, c: mom(f, HIGHER[tf], d, m)),
            ("تسارع", lambda f, tf, d, m, c: accel(f, tf, m)),
            ("حركة نظيفة", lambda f, tf, d, m, c: efficient(f, tf, m)),
            ("غير ممطوط", lambda f, tf, d, m, c: not_stretched(f, m))],
    "409": [("سوقٌ يرتدّ (هيرست)", lambda f, tf, d, m, c: hurst_reverting(f, m)),
            ("لا اتّجاه أكبر", lambda f, tf, d, m, c: no_htf_trend(f, d, m)),
            ("شمعة رفض", lambda f, tf, d, m, c: rejection(f, d, m))],
    "410": [("عند مستوى ساعة/4س", lambda f, tf, d, m, c: at_level(f, d, m, c)),
            ("كسر طابع بعده", lambda f, tf, d, m, c: choch(f, d, m)),
            ("رفض", lambda f, tf, d, m, c: rejection(f, d, m))],
}
MODES = ("واحد", "الأغلبيّة", "الكلّ")


def passes(strat, f, tf, d, m, c, mode):
    if mode == "واحد":
        return True
    got = sum(1 for _, fn in FACTORS[strat] if fn(f, tf, d, m, c))
    need = len(FACTORS[strat]) if mode == "الكلّ" else math.ceil(len(FACTORS[strat]) / 2)
    return got >= need


def main():
    adopt = {o["atom"]: o["cfg"] for o in json.loads((SF.CALIB / "adopt_month.json").read_text(encoding="utf-8"))}
    days = sorted(p.name[len("runs_"):] for p in SF.SCRATCH.glob("runs_2026-*"))
    sym = "USTEC"
    trades = []
    for day in days:
        d0 = datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
        ev = pickle.loads((SF.SCRATCH / f"candles_{day}.pkl").read_bytes())
        m1 = sorted((e[0], e[3]["high"], e[3]["low"], e[3]["close"]) for e in ev
                    if e[2] == sym and e[3]["timeframe"] == "1m" and d0 <= e[0] <= d0 + 86400)
        lo_pts, hi_pts = SF.STOP_PTS[sym]
        cost = SF.COST_PTS[sym]
        f = Facts(day, adopt)
        for sname, (s0, s1) in SF.SESSIONS.items():
            sess = [b for b in m1 if d0 + s0 < b[0] <= d0 + s1]
            for strat in FACTORS:
                for tf in (("tick",) if strat == "405" else SF.FRAMES):
                    for mode in MODES:
                        prev, busy = 0, 0
                        for i, (m, h, l, c) in enumerate(sess):
                            s = SF.signal(strat, f, tf, m, c)
                            fresh = s != 0 and s != prev
                            prev = s
                            if not fresh or m < busy or i >= len(sess) - 1 or not passes(strat, f, tf, s, m, c, mode):
                                continue
                            stop, risk = SF.stop_for(f, s, c, m, lo_pts, hi_pts)
                            if stop is None:
                                continue
                            r, exit_t, stage = SF.simulate(s, c, stop, risk, sess[i + 1:], cost)
                            busy = exit_t or m
                            trades.append({"day": day, "session": sname, "strategy": strat, "frame": tf, "mode": mode,
                                           "R": round(r, 3), "pts": round(r * risk, 2), "stage": stage})
        print(day, len(trades), flush=True)
    (D / "confluence_trades_USTEC.json").write_text(json.dumps(trades, ensure_ascii=False), encoding="utf-8")
    names = {"404": "الاتّجاه", "405": "الانعكاس", "406": "الاختراق", "407": "الارتداد", "408": "الزخم", "409": "المدى",
             "410": "السيولة"}
    agg = defaultdict(list)
    for t in trades:
        if t["strategy"] == "409" and t["frame"] != "5m":
            continue                                   # 409 تتكرّر على الأطر (كفاءة 165 بنافذة 1600)
        agg[(t["strategy"], t["mode"])].append(t)
    lines = ["# العامل الواحد مقابل العوامل المتعدّدة — الناسداك، 23 يومًا (09-08 ⟵ 10-08)\n",
             "الزناد الأصليّ شرطٌ في الطرق الثلاث · «الأغلبيّة» = نصف العوامل فأكثر · كلّ الأطر والجلستين معًا\n",
             "| الاستراتيجيّة | الطريقة | صفقات | رابحة من 100 | الهدف 3 | الهدف 2 | الهدف 1 | بلا هدف | مجموع R | R للصفقة | أيّام موجبة |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for strat in FACTORS:
        for mode in MODES:
            ts = agg.get((strat, mode), [])
            if not ts:
                lines.append(f"| {strat} {names[strat]} | {mode} | 0 | — | — | — | — | — | — | — | — |")
                continue
            st = defaultdict(int)
            byday = defaultdict(float)
            for t in ts:
                st[t["stage"]] += 1
                byday[t["day"]] += t["R"]
            n = len(ts)
            tot = sum(t["R"] for t in ts)
            lines.append(f"| {strat} {names[strat]} | {mode} | {n} | {100 * sum(t['R'] > 0 for t in ts) / n:.0f} | {st[3]} | "
                         f"{st[2]} | {st[1]} | {st[0]} | {tot:+.1f} | {tot / n:+.3f} | {sum(v > 0 for v in byday.values())}/{len(byday)} |")
    lines.append("\nالعوامل: " + " · ".join(f"{s}: " + "، ".join(n for n, _ in FACTORS[s]) for s in FACTORS))
    (D / "confluence_summary_USTEC.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("صفقات", len(trades))


if __name__ == "__main__":
    main()
