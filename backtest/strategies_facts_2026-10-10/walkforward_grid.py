# -*- coding: utf-8 -*-
"""حكم المشي إلى الأمام على النوافذ والعوامل معًا (أمر المالك ١٠-١١ «قياس معمّق احترافي» + «NQ»).

لكلّ استراتيجيّة نافذةُ زنادها تتغيّر (ذرّة الزناد بكلّ نوافذها من grid_day) والوقف والعوامل بالعيار المعتمد. كلّ شهر k:
  أ) «الحيّ اليوم»: النافذة المعتمدة + قاعدة الحيّ (404 · 408 · 409 بأغلبيّة عواملها، والبقيّة الزناد)؛
  ب) «نافذة الشهر السابق»: النافذة الأعلى R للصفقة في الشهر k−1 (15 صفقة فأكثر)، بالزناد وحده؛
  ج) «نافذة وعوامل الشهر السابق»: تلك النافذة + عوامل اختيرت على k−1 (كلٌّ وحده يرفع R للصفقة) بالأغلبيّة.
يُحكم على الثلاث في الشهر k الذي لم يره الاختيار. يعمل على ما انتهى من الأيّام — يُعاد كلّ تقرير (9 صباحًا · 9 مساءً).
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
import walkforward as WF  # noqa: E402

D = pathlib.Path(__file__).resolve().parent
TRIGGER = {"404": "151", "405": "310", "406": "201", "407": "151", "408": "152", "409": "165", "410": "201"}
MIN_TRADES = 15


class VariantFacts(WF.YearFacts):
    """حقائق اليوم بالعيار المعتمد، وذرّة الزناد مستبدلةٌ بنافذةٍ أخرى (والوقف من 202 المعتمد دائمًا).
    تُبنى من حقائق اليوم المقروءة مرّة (`base`) — نسخةٌ سطحيّة تُستبدل فيها مفاتيح ذرّة الزناد وحدها."""

    def __init__(self, day, atom, tag, base):        # noqa: D401 — لا super(): لا قراءة ثانية للقرص
        self.s = defaultdict(lambda: ([], []), base.s)
        if tag == "live":
            return
        blob = json.load(gzip.open(SF.SCRATCH / f"runs_year_{day}" / f"{atom}__{tag}.json.gz", "rt", encoding="utf-8"))
        keep202 = {k: v for k, v in self.s.items() if k[0] == "202"}
        # كلّ ذرّةٍ في ملفّ النافذة تُستبدل كلّها (القوائم جديدة — لا تُمسّ قوائم `base` المشتركة)، عدا 202 (الوقف).
        aids = {row[1] for row in blob["rows"]} - {"202"}
        for k in [k for k in self.s if k[0] in aids]:
            del self.s[k]
        for t, aid, ev, tf, row in blob["rows"]:
            if atom == "201" and aid == "202":
                continue
            for k, v in row.items():
                ts, vs = self.s[(aid, tf, k)]
                ts.append(t)
                vs.append(v)
        self.s.update(keep202)


def tags_for(day, atom):
    base = SF.SCRATCH / f"runs_year_{day}"
    return ["live"] + sorted(p.name[len(atom) + 2:-8] for p in base.glob(f"{atom}__all×*.json.gz"))


def collect(days):
    sigs = []
    for day in days:
        d0 = datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
        try:
            ev = pickle.loads((SF.SCRATCH / f"candles_{day}.pkl").read_bytes())
        except FileNotFoundError:
            continue
        m1 = sorted((e[0], e[3]["high"], e[3]["low"], e[3]["close"]) for e in ev
                    if e[2] == "USTEC" and e[3]["timeframe"] == "1m" and d0 <= e[0] <= d0 + 86400)
        sess_bounds = WF.sessions_for(day)
        try:
            base = WF.YearFacts(day)
        except (FileNotFoundError, OSError, EOFError):
            continue
        cache = {}
        for strat, atom in TRIGGER.items():
            for tag in tags_for(day, atom):
                if (atom, tag) not in cache:
                    try:
                        cache[(atom, tag)] = VariantFacts(day, atom, tag, base)
                    except (FileNotFoundError, OSError, EOFError):
                        cache[(atom, tag)] = None
                f = cache[(atom, tag)]
                if f is None:
                    continue
                for sname, (s0, s1) in sess_bounds.items():
                    sess = [b for b in m1 if s0 < b[0] <= s1]
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
                            sigs.append({"day": day, "month": day[:7], "session": sname, "strat": strat, "tf": tf,
                                         "tag": tag, "m": m, "exit": exit_t or m, "R": r, "stage": stage,
                                         "bits": {k: bool(fn(f, tf, s, m, c)) for k, fn in C2.POOL.items()},
                                         "live": bool(WF.live_rule(strat, f, tf, s, m, c))})
        print(day, len(sigs), flush=True)
    return sigs


def main():
    days = sorted(p.name[len("runs_year_"):] for p in SF.SCRATCH.glob("runs_year_*")
                  if len(list(p.glob("*.json.gz"))) >= 11)
    sigs = collect(days)
    months = sorted({s["month"] for s in sigs})
    by = defaultdict(list)
    for s in sigs:
        by[(s["strat"], s["month"], s["tag"])].append(s)
    total = defaultdict(lambda: defaultdict(list))
    folds = []
    for k in range(1, len(months)):
        prev_m, cur_m = months[k - 1], months[k]
        fold = {"month": cur_m, "rows": {}}
        for strat in TRIGGER:
            tags = sorted({t for (s_, mo, t) in by if s_ == strat and mo == prev_m})
            best, best_per = "live", None
            for tag in tags:
                r = WF.st(WF.take(by[(strat, prev_m, tag)], lambda s: True))
                if r["n"] >= MIN_TRADES and (best_per is None or r["per"] > best_per):
                    best, best_per = tag, r["per"]
            a = by[(strat, prev_m, best)]
            base_a = WF.st(WF.take(a, lambda s: True))
            chosen = [key for key in C2.POOL
                      if (lambda r: r["n"] >= MIN_TRADES and base_a["n"] and r["per"] > base_a["per"])(
                          WF.st(WF.take(a, lambda s, key=key: s["bits"][key])))]
            need = math.ceil(len(chosen) / 2)
            ways = {"الحيّ اليوم": WF.take(by[(strat, cur_m, "live")], lambda s: s["live"]),
                    "نافذة الشهر السابق": WF.take(by[(strat, cur_m, best)], lambda s: True),
                    "نافذة وعوامل الشهر السابق": WF.take(by[(strat, cur_m, best)],
                                                       lambda s: (not chosen) or sum(s["bits"][c] for c in chosen) >= need)}
            fold["rows"][strat] = {"window": best, "factors": chosen, **{w: WF.st(ts) for w, ts in ways.items()}}
            for w, ts in ways.items():
                total[strat][w] += ts
        folds.append(fold)
    res = {"days": len(days), "months": months, "folds": folds, "total": {}}
    for strat, ways in total.items():
        res["total"][strat] = {}
        for w, ts in ways.items():
            bym = defaultdict(float)
            for t in ts:
                bym[t["month"]] += t["R"]
            res["total"][strat][w] = {**WF.st(ts), "months_pos": sum(v > 0 for v in bym.values()), "months": len(bym)}
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    (D / "reports").mkdir(exist_ok=True)
    (D / "reports" / f"walkforward_grid_{stamp}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# تقرير القياس المعمّق — {stamp} — {len(days)} يومًا · أشهر الحكم {len(months) - 1}\n",
             "كلّ شهرٍ يُحكم عليه بنافذةٍ وعوامل اختيرت على الشهر الذي قبله وحده · الناسداك · أثلاث المالك\n",
             "| الاستراتيجيّة | الطريقة | صفقات | رابحة من 100 | الهدف 3 | مجموع R | R للصفقة | أشهر موجبة |",
             "|---|---|---|---|---|---|---|---|"]
    for strat in TRIGGER:
        for w in ("الحيّ اليوم", "نافذة الشهر السابق", "نافذة وعوامل الشهر السابق"):
            x = res["total"].get(strat, {}).get(w)
            if not x or not x["n"]:
                lines.append(f"| {strat} {WF.NAMES[strat]} | {w} | 0 | — | — | — | — | — |")
                continue
            lines.append(f"| {strat} {WF.NAMES[strat]} | {w} | {x['n']} | {x['win']} | {x['t3']} | {x['R']:+} | "
                         f"{x['per']:+.3f} | {x['months_pos']}/{x['months']} |")
    lines.append("\n## النافذة التي اختيرت كلّ شهر\n")
    for fold in folds:
        lines.append(f"- {fold['month']}: " + " · ".join(f"{s} {r['window']}" for s, r in fold["rows"].items()))
    (D / "reports" / f"walkforward_grid_{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (D / "آخر تقرير.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("تمّ", stamp)


if __name__ == "__main__":
    main()
