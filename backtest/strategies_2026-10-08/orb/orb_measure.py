# -*- coding: utf-8 -*-
"""بطاقة «اختراق نطاق الافتتاح» على الناسداك — قياسٌ فقط، خارج المشروع، بمسطرة البطاقة 414 نفسها.

  النطاق  : أعلى قمّة وأدنى قاع لشموع 5 د التي تبدأ في أوّل D دقيقة من نافذة المالك
            (لندن من 08:00 بتوقيت لندن · أمريكا من 09:30 بتوقيت نيويورك). يُشترط اكتمال الشموع D/5 كلّها.
  الزناد  : أوّل شمعة 5 د تبدأ بعد اكتمال النطاق، وإغلاقها داخل النافذة (owner_window)، تُغلق خارجه
            ⟸ دخولٌ بإغلاقها في جهة الخروج. هذه الشمعة وحدها زناد النافذة: إن ردّها مرشِّح (مشغول · خبر · سياق ·
            لا هدف) فلا صفقة لهذه النافذة في ذلك اليوم. صفقة واحدة على الأكثر لكلّ نافذة في اليوم.
  الوقف   : الأبعد من (الطرف المقابل للنطاق | منتصفه) ومن (الدخول ∓ N × مدى 5 د) ومن 3 نقاط أساس.
  الهدف   : أقرب قمّة (للشراء) / قاع (للبيع) مؤكَّد على الساعة أو الأربع ساعات (سلّم الحيّ بعمقه)، أو قمّة/قاع
            اليوم السابق (آخر شمعة يوم مغلقة)، يعطي صافيًا ≥ 3 بعد السبريد: (المسافة − 1.5) ÷ (الخطر + 1.5) ≥ 3،
            وفي المتناول: المسافة ≤ C × مدى اليوم 14.
  السياق  : أيّ · الساعة والأربع ساعات في جهة الاختراق (CT.direction_of) · ومعهما الإس آند بي والداو.
  الإدارة : أثلاث المالك R.thirds من أوّل دقيقة بعد الإغلاق · مركزٌ واحد (busy = exit_t + 60) · منع الخبر ±15 د.
"""
import sys

sys.dont_write_bytecode = True
ROOT = r"C:\Users\NQ\QUANT_NQ"
CARD = ROOT + r"\backtest\card_414"
sys.path.insert(0, ROOT)
sys.path.insert(0, CARD)

import bisect
import itertools
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone

import card_replay as R
import card_replay_shared as S
import card_variants as V
from card_final_check import peer_fact
from shared import card_trend as CT
from shared.owner_windows import WINDOWS, local_time, owner_window

OUT = os.path.dirname(os.path.abspath(__file__))
SPREAD = 1.5            # = R.COST
MIN_BPS = 3.0           # أدنى وقف بنقاط الأساس
NET_RR = 3.0
CTX_NAMES = {0: "أيّ", 1: "ساعة+4س", 2: "ساعة+4س+مرتبطة"}
STOP_NAMES = {"opp": "الطرف_المقابل", "mid": "المنتصف"}


def build_events(D):
    """زناد كلّ نافذة: (t_close, j, النافذة, شراء؟, قمّة النطاق, قاعه, نهاية النطاق)."""
    groups = {}
    j0 = bisect.bisect_left(R.t5, R.START - 86400)
    for j in range(max(1, j0), len(R.m5)):
        t0 = R.m5[j][0]
        for name, fn, start, end in WINDOWS:
            lt = local_time(t0, fn)
            if lt.weekday() >= 5:
                continue
            m = lt.hour * 60 + lt.minute
            if start <= m < end:
                groups.setdefault((lt.date(), name), []).append((m, j))
    events, tally = [], Counter()
    for (day, name), rows in sorted(groups.items(), key=lambda kv: kv[1][0][1]):
        start = next(s for nm, _, s, _ in WINDOWS if nm == name)
        rng = [(m, j) for m, j in rows if start <= m < start + D]
        if [m for m, _ in rng] != list(range(start, start + D, 5)):
            tally["نطاق_ناقص"] += 1
            continue
        hi = max(R.m5[j][2] for _, j in rng)
        lo = min(R.m5[j][3] for _, j in rng)
        range_end = R.m5[rng[-1][1]][0] + 300
        ev = None
        for m, j in rows:
            if m < start + D:
                continue
            t_close = R.m5[j][0] + 300
            if owner_window(t_close) != name:
                continue
            assert R.m5[j][0] >= range_end      # لا نظر إلى المستقبل: النطاق أُغلق قبل بدء شمعة الزناد
            cl = R.m5[j][4]
            if cl > hi or cl < lo:
                ev = (t_close, j, name, cl > hi, hi, lo, range_end)
                break
        if ev is None:
            tally["بلا_اختراق"] += 1
            continue
        tally["زناد"] += 1
        events.append(ev)
    events.sort()
    return events, dict(tally)


def side_ok(t_close, d, ctx):
    if ctx >= 1:
        own = CT.direction_of(S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                              S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close))
        if own != d:
            return "سياق_الناسداك"
    if ctx >= 2:
        for sym, (h1, h4) in V.REF.items():
            if CT.direction_of(peer_fact(h1, 3600, t_close), peer_fact(h4, 14400, t_close)) != d:
                return "سياق_المرتبطة"
    return None


def run(events, stop_mode, n, ctx, c):
    trades, busy, why = [], 0.0, Counter()
    for t_close, j, name, buy, hi, lo, range_end in events:
        if t_close < R.START:
            continue
        if t_close < busy:
            why["مشغول"] += 1
            continue
        if R.news_block(t_close):
            why["خبر"] += 1
            continue
        d = 1 if buy else -1
        rej = side_ok(t_close, d, ctx)
        if rej:
            why[rej] += 1
            continue
        entry, a5 = R.m5[j][4], R.a5[j]
        base = (lo if buy else hi) if stop_mode == "opp" else (hi + lo) / 2.0
        floor = MIN_BPS * 1e-4 * entry
        if buy:
            cands = {"بنية": base, "ضجيج": entry - n * a5, "أرضيّة": entry - floor}
            src = min(cands, key=cands.get)
        else:
            cands = {"بنية": base, "ضجيج": entry + n * a5, "أرضيّة": entry + floor}
            src = max(cands, key=cands.get)
        stop = cands[src]
        risk = abs(entry - stop)
        if risk <= 0:
            why["خطر_غير_موجب"] += 1
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        if idd < 0:
            why["بلا_يوم"] += 1
            continue
        reach = c * R.ad1[idd]
        key = "highs" if buy else "lows"
        lad = S.ladder_at(t_close, S.frames)
        levels = list(lad["1h"][key]) + list(lad["4h"][key])
        pd_conf = R.td1[idd] + 86400                      # وقت إغلاق اليوم السابق (≤ t_close)
        levels.append([R.d1[idd][2] if buy else R.d1[idd][3], pd_conf])
        target = CT.nearest_target(levels, buy, entry, risk, reach, t_close,
                                   rr=NET_RR + 4.0 * SPREAD / risk)
        if target is None:
            why["لا_هدف"] += 1
            continue
        net = (abs(target - entry) - SPREAD) / (risk + SPREAD)
        assert net >= NET_RR - 1e-6 and abs(target - entry) <= reach + 1e-9
        k1 = bisect.bisect_right(R.t1, t_close - 60)
        assert k1 >= len(R.t1) or R.t1[k1] >= t_close
        r, exit_t = R.thirds(entry, stop, target, buy, k1)
        if r is None:
            why["نهاية_البيانات"] += 1
            break
        why["مفتوحة"] += 1
        why["وقف_" + src] += 1
        trades.append((t_close, r, name, buy, risk / entry * 1e4, exit_t))
        busy = exit_t + 60
    return trades, dict(why)


def weekdays(a, b):
    n, t = 0, a
    while t < b:
        if datetime.fromtimestamp(t, timezone.utc).weekday() < 5:
            n += 1
        t += 86400
    return n


def owner_pass(test, allst):
    halves = list((allst.get("أنصاف") or {}).values())
    pos = sum(v > 0 for v in halves)
    ok = (test.get("n", 0) >= 30 and (test.get("R/صفقة") or 0) > 0 and (test.get("معامل") or 0) >= 1.15
          and pos >= 4)
    return ok, "%d/%d" % (pos, len(halves))


if __name__ == "__main__":
    t_start = time.time()
    split = R.START + 0.7 * (R.END - R.START)
    fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")
    days_all, days_learn, days_test = weekdays(R.START, R.END), weekdays(R.START, split), weekdays(split, R.END)
    print("البداية %s · الفاصل %s · النهاية %s · أيّام عمل: كلّه %d تعلّم %d اختبار %d" % (
        fmt(R.START), fmt(split), fmt(R.END), days_all, days_learn, days_test), flush=True)
    EV = {}
    for D in (15, 30):
        EV[D] = build_events(D)
        print("D=%d · %s" % (D, EV[D][1]), flush=True)
    rows = []
    grid = list(itertools.product((15, 30), ("opp", "mid"), (1.0, 2.0), (0, 1, 2), (1.0, 1.5)))
    assert len(grid) <= 48
    all_trades = {}
    for D, sm, n, ctx, c in grid:
        tr, why = run(EV[D][0], sm, n, ctx, c)
        L = R.stats([x for x in tr if x[0] < split]); T = R.stats([x for x in tr if x[0] >= split]); A = R.stats(tr)
        ok, pos = owner_pass(T, A)
        row = {"D": D, "الوقف": STOP_NAMES[sm], "N": n, "السياق": CTX_NAMES[ctx], "C": c,
               "تعلّم": L, "اختبار": T, "كلّه": A,
               "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
               "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"]),
               "صفقات/يوم": round(len(tr) / days_all, 3), "أسباب": why,
               "أنصاف_موجبة": pos, "يجتاز_معيار_المالك": ok}
        rows.append(row)
        all_trades[(D, sm, n, ctx, c)] = tr
        print("D=%d وقف=%-4s N=%.0f سياق=%d C=%.1f | تعلّم n=%s R/ص=%s | اختبار n=%s R/ص=%s معامل=%s | كلّه n=%s R=%s سحب=%s أنصاف=%s %s" % (
            D, sm, n, ctx, c, L.get("n"), L.get("R/صفقة"), T.get("n"), T.get("R/صفقة"), T.get("معامل"),
            A.get("n"), A.get("R"), A.get("سحب_R"), A.get("أنصاف"), "✓" if ok else ""), flush=True)

    eligible = [i for i, r in enumerate(rows) if r["تعلّم"].get("n", 0) >= 60]
    best_i = max(eligible, key=lambda i: rows[i]["تعلّم"]["R/صفقة"]) if eligible else None
    out = {"تعريف": __doc__, "البداية": fmt(R.START), "الفاصل": fmt(split), "النهاية": fmt(R.END),
           "أيّام_عمل": {"كلّه": days_all, "تعلّم": days_learn, "اختبار": days_test},
           "زنادات": {str(D): EV[D][1] for D in EV}, "قاعدة_الاختيار": "أعلى R/صفقة في التعلّم بشرط ≥ 60 صفقة تعلّم",
           "المختارة": best_i, "تركيبات": rows}
    json.dump(out, open(os.path.join(OUT, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if best_i is not None:
        b = rows[best_i]
        key = grid[best_i]
        tr = all_trades[key]
        json.dump([[t, ex, r, w, buy, bps] for t, r, w, buy, bps, ex in tr],
                  open(os.path.join(OUT, "trades_best.json"), "w", encoding="utf-8"), ensure_ascii=False)
        print("\nالمختارة #%d: %s" % (best_i, json.dumps({k: b[k] for k in ("D", "الوقف", "N", "السياق", "C")}, ensure_ascii=False)))
        for part in ("تعلّم", "اختبار", "كلّه", "لندن", "نيويورك"):
            print("  %s: %s" % (part, json.dumps(b[part], ensure_ascii=False)))
        print("  صفقات/يوم=%s · أسباب=%s · أنصاف موجبة=%s · يجتاز=%s" % (
            b["صفقات/يوم"], b["أسباب"], b["أنصاف_موجبة"], b["يجتاز_معيار_المالك"]))
    print("الزمن %.0f ث" % (time.time() - t_start), flush=True)
