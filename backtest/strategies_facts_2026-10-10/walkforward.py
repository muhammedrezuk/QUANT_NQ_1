# -*- coding: utf-8 -*-
"""سنة المشي إلى الأمام — الاستراتيجيّات السبع وعواملها (أمر المالك ١٠-١٠ «عيد قياس بطريقة مختلفة وأطول» + «NQ»).

الطريقة: لكلّ شهر k: تُختار عوامل كلّ استراتيجيّة على الشهر k−1 وحده (كلّ عاملٍ من 17 وحده فوق الزناد؛ يُبقى ما رفع R للصفقة
وفيه 15 صفقة فأكثر)، ويُحكم على الجمع (بالأغلبيّة) في الشهر k الذي لم يره الاختيار — ثمّ يتقدّم شهرًا. ومعها في كلّ شهر:
الزناد وحده، وقاعدة الحيّ اليوم (404 · 408 · 409 بأغلبيّة عواملها الثابتة؛ والأربع الأخرى = الزناد).
كلّ إشارةٍ جديدة تُحاكى مرّةً (أثلاث المالك، وقف 202 ضمن 15–45، 3R، كلفة 1.5، الجلستان) وتُحفظ معها حالة العوامل كلّها،
ثمّ يُطبَّق كلّ مرشّح على الإشارات بترتيبها الزمنيّ مع «صفقة واحدة في وقتها» لكلّ (استراتيجيّة · إطار · جلسة).
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
import confluence as CF  # noqa: E402
import confluence2 as C2  # noqa: E402
import strategies_facts as SF  # noqa: E402

D = pathlib.Path(__file__).resolve().parent
TAGS = {"151": "live", "152": "live", "153": "live", "156": "live", "163": "live", "165": "live", "201": "live",
        "310": "live", "315": "live", "358": "live"}
LIVE_RULE = {"404": [CF.FACTORS["404"][i][1] for i in range(3)]}
NAMES = {"404": "الاتّجاه", "405": "الانعكاس", "406": "الاختراق", "407": "الارتداد", "408": "الزخم", "409": "المدى",
         "410": "السيولة"}


class YearFacts(CF.Facts):
    def __init__(self, day):                         # noqa: D401 — لا super(): ملفّات السنة بأسمائها
        self.s = defaultdict(lambda: ([], []))
        base = SF.SCRATCH / f"runs_year_{day}"
        for tune, tag in TAGS.items():
            self._load(base / f"{tune}__{tag}.json.gz", None)
        self._load(base / "165__all×0.1.json.gz", "165s")

    def _load(self, path, alias):
        blob = json.load(gzip.open(path, "rt", encoding="utf-8"))
        for t, aid, ev, tf, row in blob["rows"]:
            if alias and aid != "165":
                continue
            for k, v in row.items():
                ts, vs = self.s[(alias or aid, tf, k)]
                ts.append(t)
                vs.append(v)


sys.path.insert(0, str(SF.CALIB.parent.parent))
from shared.market_clock import CITY_LONDON, CITY_NEW_YORK, local_to_utc  # noqa: E402


def sessions_for(day):
    """حدود الجلستين لليوم بساعة المشروع (الصيفيّ والشتويّ) — السنة تعبر تغيير الساعة مرّتين."""
    dd = datetime.fromisoformat(day).date()
    return {"london": (local_to_utc(dd, 8 * 60, CITY_LONDON), local_to_utc(dd, 16 * 60 + 30, CITY_LONDON)),
            "ny": (local_to_utc(dd, 9 * 60 + 30, CITY_NEW_YORK), local_to_utc(dd, 16 * 60, CITY_NEW_YORK))}


def live_rule(strat, f, tf, d, m, c):
    """قاعدة الحيّ اليوم: عوامل confluence.FACTORS بالأغلبيّة لـ404 · 408 · 409، والزناد لغيرها."""
    if strat not in ("404", "408", "409"):
        return True
    fs = CF.FACTORS[strat]
    return sum(1 for _, fn in fs if fn(f, tf, d, m, c)) >= math.ceil(len(fs) / 2)


def collect(days):
    sigs = []
    for day in days:
        try:
            f = YearFacts(day)
        except FileNotFoundError:
            print("ناقص", day, flush=True)
            continue
        d0 = datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
        ev = pickle.loads((SF.SCRATCH / f"candles_{day}.pkl").read_bytes())
        m1 = sorted((e[0], e[3]["high"], e[3]["low"], e[3]["close"]) for e in ev
                    if e[2] == "USTEC" and e[3]["timeframe"] == "1m" and d0 <= e[0] <= d0 + 86400)
        for sname, (s0, s1) in sessions_for(day).items():
            sess = [b for b in m1 if s0 < b[0] <= s1]
            for strat in NAMES:
                for tf in (("tick",) if strat == "405" else SF.FRAMES):
                    prev = 0
                    for i, (m, h, l, c) in enumerate(sess):
                        s = SF.signal(strat, f, tf, m, c)
                        fresh = s != 0 and s != prev
                        prev = s
                        if not fresh or i >= len(sess) - 1:
                            continue
                        stop, risk = SF.stop_for(f, s, c, m, *SF.STOP_PTS["USTEC"])
                        if stop is None:
                            continue
                        r, exit_t, stage = SF.simulate(s, c, stop, risk, sess[i + 1:], SF.COST_PTS["USTEC"])
                        sigs.append({"day": day, "month": day[:7], "session": sname, "strat": strat, "tf": tf, "m": m,
                                     "exit": exit_t or m, "R": r, "stage": stage,
                                     "bits": {k: bool(fn(f, tf, s, m, c)) for k, fn in C2.POOL.items()},
                                     "live": bool(live_rule(strat, f, tf, s, m, c))})
        print(day, len(sigs), flush=True)
    return sigs


def take(sigs, keep):
    """صفقةٌ واحدة في وقتها لكلّ (استراتيجيّة · إطار · جلسة · يوم)."""
    out, busy = [], {}
    for s in sorted(sigs, key=lambda x: x["m"]):
        if not keep(s):
            continue
        k = (s["strat"], s["tf"], s["session"], s["day"])
        if s["m"] < busy.get(k, 0):
            continue
        busy[k] = s["exit"]
        out.append(s)
    return out


def st(ts):
    n = len(ts)
    tot = sum(t["R"] for t in ts)
    return {"n": n, "R": round(tot, 1), "per": round(tot / n, 3) if n else None,
            "win": round(100 * sum(t["R"] > 0 for t in ts) / n) if n else None, "t3": sum(t["stage"] == 3 for t in ts)}


def main():
    days = sorted(p.name[len("runs_year_"):] for p in SF.SCRATCH.glob("runs_year_*"))
    sigs = collect(days)
    pickle.dump(sigs, open(SF.SCRATCH / "year_signals.pkl", "wb"))
    months = sorted({s["month"] for s in sigs})
    res = {"months": months, "folds": []}
    total = defaultdict(lambda: defaultdict(list))
    for k in range(1, len(months)):
        prev_m, cur_m = months[k - 1], months[k]
        fold = {"month": cur_m, "chosen_on": prev_m, "rows": {}}
        for strat in NAMES:
            a = [s for s in sigs if s["strat"] == strat and s["month"] == prev_m]
            base_a = st(take(a, lambda s: True))
            chosen = []
            for key in C2.POOL:
                r = st(take(a, lambda s, key=key: s["bits"][key]))
                if r["n"] >= C2.MIN_TRADES and base_a["n"] and r["per"] > base_a["per"]:
                    chosen.append(key)
            b = [s for s in sigs if s["strat"] == strat and s["month"] == cur_m]
            need = math.ceil(len(chosen) / 2)
            ways = {"الزناد وحده": take(b, lambda s: True),
                    "عوامل الشهر السابق": take(b, lambda s: (not chosen) or sum(s["bits"][c] for c in chosen) >= need),
                    "قاعدة الحيّ اليوم": take(b, lambda s: s["live"])}
            fold["rows"][strat] = {"chosen": chosen, **{w: st(ts) for w, ts in ways.items()}}
            for w, ts in ways.items():
                total[strat][w] += ts
        res["folds"].append(fold)
        print("شهر", cur_m, flush=True)
    res["total"] = {}
    for strat, ways in total.items():
        res["total"][strat] = {}
        for w, ts in ways.items():
            bym = defaultdict(float)
            for t in ts:
                bym[t["month"]] += t["R"]
            res["total"][strat][w] = {**st(ts), "months_pos": sum(v > 0 for v in bym.values()), "months": len(bym)}
        base_all = [s for s in sigs if s["strat"] == strat and s["month"] != months[0]]
        bys = defaultdict(list)
        for s in take(base_all, lambda s: True):
            bys[(s["session"], s["tf"])].append(s)
        res["total"][strat]["by_session_frame"] = {f"{a}|{b}": st(v) for (a, b), v in bys.items()}
    (D / "walkforward_USTEC.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# سنة المشي إلى الأمام — الناسداك — {months[1]} ⟵ {months[-1]} ({len(months) - 1} شهر حكم)\n",
             "كلّ شهرٍ يُحكم عليه بعوامل اختيرت على الشهر الذي قبله وحده · «أشهر موجبة» = عدد الأشهر التي ربحت فيها\n",
             "| الاستراتيجيّة | الطريقة | صفقات | رابحة من 100 | الهدف 3 | مجموع R | R للصفقة | أشهر موجبة |", "|---|---|---|---|---|---|---|---|"]
    for strat in NAMES:
        for w in ("الزناد وحده", "عوامل الشهر السابق", "قاعدة الحيّ اليوم"):
            x = res["total"][strat][w]
            lines.append(f"| {strat} {NAMES[strat]} | {w} | {x['n']} | {x['win']} | {x['t3']} | {x['R']:+} | "
                         f"{x['per'] if x['per'] is None else format(x['per'], '+.3f')} | {x['months_pos']}/{x['months']} |")
    lines.append("\n## الزناد وحده لكلّ جلسة وإطار (كلّ أشهر الحكم)\n")
    lines.append("| الاستراتيجيّة | الجلسة · الإطار | صفقات | R | R للصفقة |")
    lines.append("|---|---|---|---|---|")
    for strat in NAMES:
        for k, x in sorted(res["total"][strat]["by_session_frame"].items()):
            a, b = k.split("|")
            lines.append(f"| {strat} {NAMES[strat]} | {'لندن' if a == 'london' else 'نيويورك'} · {b} | {x['n']} | {x['R']:+} | "
                         f"{x['per'] if x['per'] is None else format(x['per'], '+.3f')} |")
    (D / "walkforward_summary_USTEC.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("تمّ")


if __name__ == "__main__":
    main()
