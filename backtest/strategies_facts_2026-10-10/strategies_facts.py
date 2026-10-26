# -*- coding: utf-8 -*-
"""الاستراتيجيّات السبع المؤرشفة (404–410) على حقائق الأقسام وحدها — قياسٌ فقط (ختم المالك «NQ» ٢٠٢٦-١٠-١٠).

أمر المالك: «اختبرها مع المعايرة الجديدة، بس ما بيصير تحلّل لحالها — لازم تاخد كلّ التحليل من الأقسام، ما تعيد
تحليل مرّة ثانية» · «مو بس للناسداك، بتشتغل على أيّ زوج مفعّل».

كلّ استراتيجيّة قاعدتها هي قاعدة كودها المؤرشف (سطح المكتب ⟵ أرشيف QUANT_NQ ⟵ فكّ الأقسام عن القرار)، ومدخلها
حقيقة القسم بدل حساب التِّكّ — بعيار الذرّة المعتمد ١٠-١٠ (adopt_month.json):
  404 الاتّجاه   — الأقصر من متوسّطَي 151 فوق الأطول ⟸ شراء، تحته ⟸ بيع           (كان: متوسّط 12 مقابل 36 تِكّة)
  405 الانعكاس  — درجة Z من 310 ≥ 1.5 ⟸ بيع، ≤ −1.5 ⟸ شراء (عتبة البيان المؤرشف)     (كان: Z على 32 تِكّة)
  406 الاختراق  — كسرٌ من 204 فوق ⟸ شراء، تحت ⟸ بيع                                 (كان: كسر أعلى/أدنى 32 تِكّة)
  407 الارتداد  — ميل 151 صاعد والإغلاق تحت متوسّطه بـ0.01٪ ⟸ شراء، والعكس بيع         (كان: نصفا 32 تِكّة)
  408 الزخم     — إشارة معدّل التغيّر من 152                                        (كان: مجموع عوائد 20 تِكّة)
  409 المدى     — كفاءة 165 < 0.35 (سوقٌ عرضيّ) وموقع 315 ≤ 0.25 ⟸ شراء، ≥ 0.75 ⟸ بيع (كان: 32 تِكّة)
  410 السيولة   — كنسٌ من 254 لسيولة البيع ⟸ شراء، لسيولة الشراء ⟸ بيع                (كان: كسر واسترداد 600 تِكّة)
الحقيقة الإطاريّة تُقرأ على كلّ إطار (1m · 5m · 15m · 1h) وتُعطى نتيجة كلّ إطار وحده؛ وحقيقة التِّكّ (310 · 315) كما هي.

الصفقة (قوانين المالك المكتوبة): الدخول عند إغلاق الدقيقة التي ظهرت فيها إشارةٌ جديدة، داخل الجلسة، صفقةٌ واحدة
لكلّ (استراتيجيّة × إطار) · الوقف خلف آخر قاع/قمّة خارجيّة من 202 على 5د ثمّ 15د ثمّ 1د، بنقطةٍ، ضمن 15–45 نقطة
للناسداك (5–15 نقطة أساس لأيّ رمز) وإلّا لا صفقة · أثلاث المالك: عند 1R ثلثٌ والوقف إلى الدخول، عند 2R نصف الباقي
والوقف إلى الهدف الأوّل، عند 3R خروج · الوقف أوّلًا إن التبست الشمعة · خروج الباقي بنهاية الجلسة · كلفة 1.5 نقطة
للناسداك (0.5 نقطة أساس لغيره).
الجلستان: لندن 08:00⟵16:30 لندن · نيويورك 09:30⟵16:00 نيويورك. لا نظر في المستقبل: الحقيقة آخر قيمةٍ حتّى إغلاق
الدقيقة، والسعر إغلاقها.
الاستعمال: python strategies_facts.py [--symbol USTEC]
"""
import argparse
import bisect
import gzip
import json
import pathlib
import pickle
from collections import defaultdict
from datetime import datetime, timezone

D = pathlib.Path(__file__).resolve().parent
CALIB = pathlib.Path(__file__).resolve().parent.parent / "s150_calibration_2026-10-09"
SCRATCH = pathlib.Path(r"C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib_day")
FRAMES = ("1m", "5m", "15m", "1h")
STOP_FRAMES = ("5m", "15m", "1m")
SESSIONS = {"london": (7 * 3600, 15.5 * 3600), "ny": (13.5 * 3600, 20 * 3600)}
Z_TH, PULL_MIN, RANGE_EFF, EDGE = 1.5, 0.0001, 0.35, 0.25          # عتبات البيانات المؤرشفة نفسها
STOP_PTS = {"USTEC": (15.0, 45.0)}
COST_PTS = {"USTEC": 1.5}


class Facts:
    """حقائق يومٍ واحد: لكلّ (ذرّة · إطار · حقل) سلسلة (زمن، قيمة) — آخر قيمةٍ في كلّ دقيقة."""

    def __init__(self, day, adopt):
        self.s = defaultdict(lambda: ([], []))
        tags = {"151": adopt.get("151", "live"), "152": adopt.get("152", "live"), "165": adopt.get("165", "live"),
                "201": adopt.get("201", "live"), "310": adopt.get("310", "live"), "315": adopt.get("315", "live")}
        for tune, tag in tags.items():
            blob = json.load(gzip.open(SCRATCH / f"runs_{day}" / f"{tune}__{tag}.json.gz", "rt", encoding="utf-8"))
            for t, aid, ev, tf, row in blob["rows"]:
                for k, v in row.items():
                    ts, vs = self.s[(aid, tf, k)]
                    ts.append(t)
                    vs.append(v)

    def at(self, aid, tf, k, m):
        ts, vs = self.s.get((aid, tf, k), ((), ()))
        i = bisect.bisect_right(ts, m) - 1
        return vs[i] if i >= 0 else None

    def event(self, aid, tf, k, m):
        """قيمةٌ نُشرت خلال هذه الدقيقة وحدها (الكسر والكنس حدثان لا حالة)."""
        ts, vs = self.s.get((aid, tf, k), ((), ()))
        i = bisect.bisect_right(ts, m) - 1
        return vs[i] if i >= 0 and ts[i] > m - 60 else None


def signal(strat, f, tf, m, close):
    if strat == "404":
        fast, slow = f.at("151", tf, "m.ema_fast", m), f.at("151", tf, "m.ema_slow", m)
        fv, sv = f.at("151", tf, "m.ema_fast_value", m), f.at("151", tf, "m.ema_slow_value", m)
        if None in (fast, slow, fv, sv) or fv == sv:
            return 0
        short, long_ = (fv, sv) if fast < slow else (sv, fv)
        return 1 if short > long_ else -1
    if strat == "405":
        z = f.at("310", "tick", "m.value", m)
        return 0 if z is None else (-1 if z >= Z_TH else 1 if z <= -Z_TH else 0)
    if strat == "406":
        if f.event("204", tf, "signal", m) != "bos":
            return 0
        side = f.event("204", tf, "m.break_side", m)
        return 1 if side == "above" else -1 if side == "below" else 0
    if strat == "407":
        slope, mean = f.at("151", tf, "m.ema_slope", m), f.at("151", tf, "m.ema_slow_value", m)
        if slope is None or not mean:
            return 0
        dev = close / mean - 1
        return 1 if slope > 0 and dev <= -PULL_MIN else -1 if slope < 0 and dev >= PULL_MIN else 0
    if strat == "408":
        roc = f.at("152", tf, "m.roc", m)
        return 0 if not roc else (1 if roc > 0 else -1)
    if strat == "409":
        eff, pos = f.at("165", tf, "m.efficiency_ratio", m), f.at("315", "tick", "m.position", m)
        if eff is None or pos is None or eff >= RANGE_EFF:
            return 0
        return 1 if pos <= EDGE else -1 if pos >= 1 - EDGE else 0
    if strat == "410":
        if f.event("254", tf, "signal", m) != "sweep":
            return 0
        d = f.event("254", tf, "m.direction", m)
        return 1 if d == "sell_side" else -1 if d == "buy_side" else 0
    return 0


def stop_for(f, side, entry, m, lo_pts, hi_pts):
    for tf in STOP_FRAMES:
        lvl = f.at("202", tf, "m.swing_low" if side > 0 else "m.swing_high", m)
        if lvl is None:
            continue
        stop = lvl - 1.0 if side > 0 else lvl + 1.0
        risk = (entry - stop) * side
        if lo_pts <= risk <= hi_pts:
            return stop, risk
    return None, None


def simulate(side, entry, stop, risk, bars, cost):
    """أثلاث المالك على شموع الدقيقة بعد الدخول؛ الناتج R صافٍ بعد الكلفة."""
    t1, t2, t3 = (entry + side * risk * k for k in (1, 2, 3))
    left, got, st, stage = 1.0, 0.0, stop, 0
    exit_t = None
    for t, h, l, c in bars:
        hit_stop = (l <= st) if side > 0 else (h >= st)
        if hit_stop:
            got += left * (st - entry) * side / risk
            left, exit_t = 0.0, t
            break
        reach = h if side > 0 else l
        if stage < 1 and (reach - t1) * side >= 0:
            got += (1 / 3) * 1.0
            left -= 1 / 3
            st, stage = entry, 1
        if stage < 2 and (reach - t2) * side >= 0:
            got += (1 / 3) * 2.0
            left -= 1 / 3
            st, stage = t1, 2
        if stage < 3 and (reach - t3) * side >= 0:
            got += left * 3.0
            left, exit_t, stage = 0.0, t, 3
            break
    if left > 0 and bars:
        t, h, l, c = bars[-1]
        got += left * (c - entry) * side / risk
        exit_t = t
    return got - cost / risk, exit_t, stage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="USTEC")
    a = ap.parse_args()
    adopt = {o["atom"]: o["cfg"] for o in json.loads((CALIB / "adopt_month.json").read_text(encoding="utf-8"))}
    days = sorted(p.name[len("runs_"):] for p in SCRATCH.glob("runs_2026-*"))
    sym = a.symbol
    trades = []
    for day in days:
        d0 = datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
        ev = pickle.loads((SCRATCH / f"candles_{day}.pkl").read_bytes())
        m1 = sorted((e[0], e[3]["high"], e[3]["low"], e[3]["close"]) for e in ev
                    if e[2] == sym and e[3]["timeframe"] == "1m" and d0 <= e[0] <= d0 + 86400)
        if not m1:
            continue
        px = m1[0][3]
        lo_pts, hi_pts = STOP_PTS.get(sym, (px * 5e-4, px * 15e-4))
        cost = COST_PTS.get(sym, px * 5e-5)
        f = Facts(day, adopt)
        for sname, (s0, s1) in SESSIONS.items():
            sess = [b for b in m1 if d0 + s0 < b[0] <= d0 + s1]
            for strat in ("404", "405", "406", "407", "408", "409", "410"):
                for tf in (("tick",) if strat == "405" else FRAMES):
                    prev, busy_until = 0, 0
                    for i, (m, h, l, c) in enumerate(sess):
                        s = signal(strat, f, tf, m, c)
                        fresh = s != 0 and s != prev
                        prev = s
                        if not fresh or m < busy_until or i >= len(sess) - 1:
                            continue
                        stop, risk = stop_for(f, s, c, m, lo_pts, hi_pts)
                        if stop is None:
                            continue
                        r, exit_t, stage = simulate(s, c, stop, risk, sess[i + 1:], cost)
                        busy_until = exit_t or m
                        trades.append({"day": day, "session": sname, "strategy": strat, "frame": tf,
                                       "t": datetime.fromtimestamp(m, timezone.utc).strftime("%H:%M"), "side": s,
                                       "entry": c, "stop": round(stop, 2), "risk_pts": round(risk, 2), "R": round(r, 3),
                                       "pts": round(r * risk, 2), "stage": stage})
        print(day, len(trades), flush=True)
    (D / f"trades_{sym}.json").write_text(json.dumps(trades, ensure_ascii=False, indent=0), encoding="utf-8")
    agg = defaultdict(list)
    for t in trades:
        agg[(t["strategy"], t["frame"], t["session"])].append(t)
    names = {"404": "الاتّجاه", "405": "الانعكاس", "406": "الاختراق", "407": "الارتداد", "408": "الزخم",
             "409": "المدى", "410": "السيولة"}
    lines = [f"# الاستراتيجيّات على حقائق الأقسام — {sym} — {days[0]} ⟵ {days[-1]} ({len(days)} يومًا)\n",
             "أثلاث المالك · وقفٌ من 202 ضمن 15–45 نقطة · كلفة 1.5 · بأرقام المعايرة المعتمدة ١٠-١٠\n",
             "| الاستراتيجيّة | الإطار | الجلسة | صفقات | رابحة من 100 | متوسّط R | مجموع R | مجموع النقاط | أيّام موجبة |",
             "|---|---|---|---|---|---|---|---|---|"]
    for (st, tf, ss), ts in sorted(agg.items()):
        byday = defaultdict(float)
        for t in ts:
            byday[t["day"]] += t["R"]
        n = len(ts)
        lines.append(f"| {st} {names[st]} | {tf} | {'لندن' if ss == 'london' else 'نيويورك'} | {n} | "
                     f"{100 * sum(t['R'] > 0 for t in ts) / n:.0f} | {sum(t['R'] for t in ts) / n:+.3f} | "
                     f"{sum(t['R'] for t in ts):+.1f} | {sum(t['pts'] for t in ts):+.0f} | "
                     f"{sum(v > 0 for v in byday.values())}/{len(byday)} |")
    (D / f"summary_{sym}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("صفقات", len(trades))


if __name__ == "__main__":
    main()
