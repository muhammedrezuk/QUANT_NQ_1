# -*- coding: utf-8 -*-
"""إعادة قياس الأربع التي لم تتحسّن بعواملي (405 · 406 · 407 · 410) بطريقةٍ أخرى — قياسٌ فقط (أمر المالك ١٠-١٠
«الّي تحسّن ضيفه، والّي ما تحسّن عيد قياس بغير طريقة NQ»).

الطريقة: البيانات تختار العوامل لا الاقتراح. لكلّ استراتيجيّة (زنادها شرط):
 ١) كلّ عاملٍ من المجموعة كلّها (16) وحده فوق الزناد — على أيّام الاختيار (أوّل 12 يومًا) فقط؛
 ٢) يُبقى العامل الذي يرفع R للصفقة عن الزناد وحده وفيه 15 صفقة فأكثر؛
 ٣) الباقية تُجمع بالأغلبيّة، ويُحكم على الجمع وعلى الزناد وحده في أيّام الحكم (آخر 11 يومًا) — لم يرها الاختيار.
و«حركة نظيفة» تُقرأ هنا من الضوضاء 165 بنافذتها السابقة 160 (عيار 1600 المعتمد يجعلها ميّتة — قيس في confluence.py).
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
import strategies_facts as SF  # noqa: E402

D = pathlib.Path(__file__).resolve().parent
TARGETS = ("405", "406", "407", "410")
MIN_TRADES = 15


class Facts(CF.Facts):
    def __init__(self, day, adopt):
        super().__init__(day, adopt)
        blob = json.load(gzip.open(SF.SCRATCH / f"runs_{day}" / "165__live.json.gz", "rt", encoding="utf-8"))
        for t, aid, ev, tf, row in blob["rows"]:
            if aid == "165":
                for k, v in row.items():
                    ts, vs = self.s[("165s", tf, k)]
                    ts.append(t)
                    vs.append(v)


def eff160(f, tf, m, clean):
    e = CF.num(f.at("165s", "5m" if tf == "tick" else tf, "m.efficiency_ratio", m))
    return e is not None and (e >= SF.RANGE_EFF if clean else e < SF.RANGE_EFF)


POOL = {
    "اتّجاه الساعة و4س معه": lambda f, tf, d, m, c: CF.htf_trend(f, d, m),
    "اتّجاه الساعة و4س ضدّه": lambda f, tf, d, m, c: CF.htf_trend(f, -d, m),
    "لا اتّجاه أكبر": lambda f, tf, d, m, c: CF.no_htf_trend(f, d, m),
    "زخم الإطار معه": lambda f, tf, d, m, c: CF.mom(f, "5m" if tf == "tick" else tf, d, m),
    "زخم الإطار الأكبر معه": lambda f, tf, d, m, c: CF.mom(f, CF.HIGHER[tf], d, m),
    "تسارع": lambda f, tf, d, m, c: CF.accel(f, tf, m),
    "تباطؤ": lambda f, tf, d, m, c: CF.decel(f, tf, m),
    "حركة نظيفة (160)": lambda f, tf, d, m, c: eff160(f, tf, m, True),
    "حركة متعرّجة (160)": lambda f, tf, d, m, c: eff160(f, tf, m, False),
    "تذبذب يتّسع": lambda f, tf, d, m, c: CF.vol_expanding(f, tf, m),
    "غير ممطوط": lambda f, tf, d, m, c: CF.not_stretched(f, m),
    "عند مستوى ساعة/4س": lambda f, tf, d, m, c: CF.at_level(f, d, m, c),
    "لا مستوى أمامه": lambda f, tf, d, m, c: CF.no_level_ahead(f, d, m, c),
    "كنس": lambda f, tf, d, m, c: CF.swept(f, d, m),
    "شمعة رفض": lambda f, tf, d, m, c: CF.rejection(f, d, m),
    "كسر طابع معه": lambda f, tf, d, m, c: CF.choch(f, d, m),
    "هيرست < 0.5": lambda f, tf, d, m, c: CF.hurst_reverting(f, m),
}


def run(days, adopt, filt):
    """يعيد الصفقات لكلّ (استراتيجيّة · مفتاح المرشّح) — filt: dict مفتاح ⟶ دالّة(strat, f, tf, d, m, c) ⟶ صح/خطأ."""
    out = defaultdict(list)
    for day in days:
        d0 = datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
        ev = pickle.loads((SF.SCRATCH / f"candles_{day}.pkl").read_bytes())
        m1 = sorted((e[0], e[3]["high"], e[3]["low"], e[3]["close"]) for e in ev
                    if e[2] == "USTEC" and e[3]["timeframe"] == "1m" and d0 <= e[0] <= d0 + 86400)
        f = Facts(day, adopt)
        for sname, (s0, s1) in SF.SESSIONS.items():
            sess = [b for b in m1 if d0 + s0 < b[0] <= d0 + s1]
            for strat in TARGETS:
                for tf in (("tick",) if strat == "405" else SF.FRAMES):
                    sigs = []
                    prev = 0
                    for i, (m, h, l, c) in enumerate(sess):
                        s = SF.signal(strat, f, tf, m, c)
                        if s != 0 and s != prev and i < len(sess) - 1:
                            sigs.append((i, m, c, s))
                        prev = s
                    for key, fn in filt.items():
                        busy = 0
                        for i, m, c, s in sigs:
                            if m < busy or not fn(strat, f, tf, s, m, c):
                                continue
                            stop, risk = SF.stop_for(f, s, c, m, *SF.STOP_PTS["USTEC"])
                            if stop is None:
                                continue
                            r, exit_t, stage = SF.simulate(s, c, stop, risk, sess[i + 1:], SF.COST_PTS["USTEC"])
                            busy = exit_t or m
                            out[(strat, key)].append({"day": day, "R": r, "stage": stage})
        print(day, flush=True)
    return out


def stats(ts):
    if not ts:
        return {"n": 0}
    st = defaultdict(int)
    for t in ts:
        st[t["stage"]] += 1
    tot = sum(t["R"] for t in ts)
    return {"n": len(ts), "win": round(100 * sum(t["R"] > 0 for t in ts) / len(ts)), "R": round(tot, 1),
            "per": round(tot / len(ts), 3), "t3": st[3]}


def main():
    adopt = {o["atom"]: o["cfg"] for o in json.loads((SF.CALIB / "adopt_month.json").read_text(encoding="utf-8"))}
    days = sorted(p.name[len("runs_"):] for p in SF.SCRATCH.glob("runs_2026-*"))
    pick, judge = days[:12], days[12:]
    filt = {"زناد": lambda st, f, tf, d, m, c: True}
    filt.update({k: (lambda fn: lambda st, f, tf, d, m, c: fn(f, tf, d, m, c))(fn) for k, fn in POOL.items()})
    first = run(pick, adopt, filt)
    chosen = {}
    report = {"pick_days": pick, "judge_days": judge, "single": {}, "chosen": {}, "judge": {}}
    for strat in TARGETS:
        base = stats(first[(strat, "زناد")])
        rows = {k: stats(first[(strat, k)]) for k in POOL}
        report["single"][strat] = {"زناد": base, **rows}
        keep = [k for k, r in rows.items() if r["n"] >= MIN_TRADES and base["n"] and r["per"] > base["per"]]
        chosen[strat] = keep
        report["chosen"][strat] = keep

    def combo(st, f, tf, d, m, c):
        keep = chosen[st]
        if not keep:
            return True
        got = sum(1 for k in keep if POOL[k](f, tf, d, m, c))
        return got >= math.ceil(len(keep) / 2)
    second = run(judge, adopt, {"زناد": lambda st, f, tf, d, m, c: True, "مختارة": combo})
    for strat in TARGETS:
        report["judge"][strat] = {"زناد": stats(second[(strat, "زناد")]), "مختارة": stats(second[(strat, "مختارة")])}
    (D / "confluence2_USTEC.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    names = {"405": "الانعكاس", "406": "الاختراق", "407": "الارتداد", "410": "السيولة"}
    lines = [f"# إعادة القياس بطريقةٍ أخرى — الاختيار {pick[0]}⟵{pick[-1]} · الحكم {judge[0]}⟵{judge[-1]}\n",
             "| الاستراتيجيّة | العوامل التي اختارتها البيانات | الحكم: الزناد وحده | الحكم: الزناد + المختارة |", "|---|---|---|---|"]
    f = lambda s: f"{s['n']} صفقة · {s['win']} من 100 · {s['R']:+}R · {s['per']:+} للصفقة · الهدف3 {s['t3']}" if s["n"] else "لا صفقات"  # noqa: E731
    for strat in TARGETS:
        j = report["judge"][strat]
        lines.append(f"| {strat} {names[strat]} | {'، '.join(chosen[strat]) or '— (لا عامل حسّنها)'} | {f(j['زناد'])} | {f(j['مختارة'])} |")
    (D / "confluence2_summary_USTEC.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
