# -*- coding: utf-8 -*-
"""فحوص ما بعد القياس (لا اختيار جديد):
  ١. المقبولان بنوافذ الحيّ الفعليّة: مفتاح السرعة 50 والرئيسي 38 ⟸ السرعة الفعّالة 38 ⟸ المعامل 50/38 = 1.316
     (151: ميل 4 شموع وحدّ أدنى 26 · 153: مدى 21 ÷ 42) — هل يصمدان بما سيحسبه الحيّ؟
  ٢. ضابط الحظّ لكلّ عيارٍ مختار: مرشِّحاتٌ عشوائيّة بنسبة السماح نفسها — حرّةً، وبكتل يومٍ كامل (أعدل للشرط الثابت يومًا).
  ٣. المقبولان مقسومين لندن/نيويورك وشراء/بيع (للعلم لا للاختيار).
  ٤. البطاقة الأساس نفسها بمتوسّط المدى الذي يحسبه 153 حيًّا (16 عند المعامل 1 · 21 عند 1.316) بدل 14 المقيس.
"""
import json
import random
from datetime import datetime, timezone

import analysts_roles as A
from analysts_roles import R, S, V, F, CT, owner_window, log, summary, replay, verdict, at, SEC, NQ, EVENTS, SPLIT

base = summary(replay())
out = {}

# ١. نوافذ الحيّ
F151_D1_live = A.a151(NQ["D1"], k=4, min_c=26)
F153_H1_live = A.a153(NQ["H1"], atr_w=21, base_w=42, min_c=21)
LIVE = {
    "151/يوم بنوافذ الحيّ (ميل 4 · حدّ 26)": lambda t, d: at(F151_D1_live, "D1", t) == d,
    "153/ساعة بنوافذ الحيّ (21 ÷ 42)": lambda t, d: (lambda r: r is not None and 0.7 < r < 1.35)(at(F153_H1_live, "H1", t)),
}
ACC = {
    "151/يوم": lambda t, d: at(A.F151["D1"], "D1", t) == d,
    "153/ساعة": lambda t, d: (lambda r: r is not None and 0.7 < r < 1.35)(at(A.F153["H1"], "H1", t)),
}
for name, cond in {**LIVE, "اجتماعهما بنوافذ الحيّ": lambda t, d: all(c(t, d) for c in LIVE.values())}.items():
    s = summary(replay(cond))
    ok, checks = verdict(s, base)
    out[name] = {"كلّه": s["كلّه"], "تعلّم": s["تعلّم"], "اختبار": s["اختبار"], "فحوص": checks, "يجتاز": ok}
    log(name, "| n=%s R=%s R/ص=%s سحب=%s أنصاف=%s | تعلّم %s | اختبار %s معامل=%s | %s" % (
        s["كلّه"]["n"], s["كلّه"]["R"], s["كلّه"]["R/صفقة"], s["كلّه"]["سحب_R"], s["كلّه"]["أنصاف"],
        s["تعلّم"]["R/صفقة"], s["اختبار"]["R/صفقة"], s["اختبار"]["معامل"], "يجتاز" if ok else checks))

# ٢. ضابط الحظّ لكلّ عيارٍ مختار (من نتيجة القياس الأوّل)
chosen = json.load(open("analysts_roles.json", encoding="utf-8"))["أحكام"]
by_key = {(t[0], t[3]): t for t in A.TESTS}
days = sorted({datetime.fromtimestamp(t, timezone.utc).date() for t, _ in EVENTS})


def control(rate, seeds=500, block=False):
    hits = 0
    for sd in range(seeds):
        rnd = random.Random(7000 + sd)
        if block:
            keep_days = {d for d in days if rnd.random() < rate}
            keep = {t for t, _ in EVENTS if datetime.fromtimestamp(t, timezone.utc).date() in keep_days}
        else:
            keep = {t for t, _ in EVENTS if rnd.random() < rate}
        hits += verdict(summary(replay(lambda t, d: t in keep)), base)[0]
    return hits / seeds


ctrl, exp_iid, exp_blk = {}, 0.0, 0.0
for row in chosen:
    if row["الدور"] == "ملحق":
        continue
    test = by_key[(row["الرقم"], row["العيار_المختار_على_التعلّم"])]
    cond = test[5]
    rate = sum(1 for t, c in EVENTS if cond(t, 1 if c["side"] == CT.BUY else -1)) / len(EVENTS)
    p_iid, p_blk = control(rate), control(rate, block=True)
    exp_iid += p_iid
    exp_blk += p_blk
    ctrl["%s/%s" % (row["الرقم"], row["العيار_المختار_على_التعلّم"])] = {
        "نسبة_السماح": round(rate, 3), "عشوائيّ_حرّ": p_iid, "عشوائيّ_بكتل_يوم": p_blk, "قُبل_فعلًا": row["يُقبل"]}
    log("ضابط %s/%s سماح %.2f ⟸ حرّ %.1f٪ · كتل يوم %.1f٪ (قُبل فعلًا: %s)" % (
        row["الرقم"], row["العيار_المختار_على_التعلّم"], rate, 100 * p_iid, 100 * p_blk, row["يُقبل"]))
out["ضابط_الحظّ"] = ctrl
out["المتوقَّع_قبوله_بالحظّ_من_12"] = {"حرّ": round(exp_iid, 2), "بكتل_يوم": round(exp_blk, 2)}
log("المتوقَّع قبوله بالحظّ وحده من 12 محلّلًا: حرّ %.2f · بكتل يوم %.2f" % (exp_iid, exp_blk))

# ٣. التقسيم
for name, cond in ACC.items():
    tr = replay(cond)
    out["تقسيم " + name] = {
        "لندن": R.stats([x for x in tr if x[2] == "london_peak"]),
        "نيويورك": R.stats([x for x in tr if x[2] == "ny_open"]),
        "شراء": R.stats([x for x in tr if x[3]]), "بيع": R.stats([x for x in tr if not x[3]])}
    for k, v in out["تقسيم " + name].items():
        log("تقسيم %s %s: n=%s R=%s R/ص=%s" % (name, k, v.get("n"), v.get("R"), v.get("R/صفقة")))
btr = replay()
out["تقسيم المرجع"] = {"لندن": R.stats([x for x in btr if x[2] == "london_peak"]),
                       "نيويورك": R.stats([x for x in btr if x[2] == "ny_open"]),
                       "شراء": R.stats([x for x in btr if x[3]]), "بيع": R.stats([x for x in btr if not x[3]])}


# ٤. البطاقة الأساس بمتوسّط المدى الذي يحسبه 153 حيًّا
def collect_atr(n):
    a5, ad1 = R.atr(R.m5, n), R.atr(R.d1, n)
    ev = []
    for j in range(1, len(R.m5)):
        t_close = R.m5[j][0] + 300
        if t_close < R.START:
            continue
        win = owner_window(t_close)
        if not win:
            continue
        idd = R.closed_index(R.td1, 86400, t_close)
        peers = {sym: (F.peer_fact(h1, 3600, t_close), F.peer_fact(h4, 14400, t_close)) for sym, (h1, h4) in V.REF.items()}
        card = CT.evaluate(at=t_close, close=R.m5[j][4], prev_close=R.m5[j - 1][4],
                           trend_1h=S.fact_trend(R.h1, R.e_h1, R.th1, 3600, t_close),
                           trend_4h=S.fact_trend(R.h4, R.e_h4, R.th4, 14400, t_close),
                           atr_5m=a5[j], atr_1d=ad1[idd] if idd >= 0 else None,
                           ladder=S.ladder_at(t_close, S.frames), window=win,
                           news_blocked=R.news_block(t_close), peers=peers)
        if card["status"] == CT.OPEN:
            ev.append((t_close, card))
    return ev


for n in (16, 21):
    A.EVENTS[:] = collect_atr(n)
    A.SIM.clear()
    s = summary(replay())
    out["البطاقة بمتوسّط مدى %d" % n] = {"كلّه": s["كلّه"], "تعلّم": s["تعلّم"], "اختبار": s["اختبار"]}
    log("البطاقة بمتوسّط مدى %d: n=%s R=%s R/ص=%s سحب=%s أنصاف=%s | تعلّم %s | اختبار %s معامل=%s" % (
        n, s["كلّه"]["n"], s["كلّه"]["R"], s["كلّه"]["R/صفقة"], s["كلّه"]["سحب_R"], s["كلّه"]["أنصاف"],
        s["تعلّم"]["R/صفقة"], s["اختبار"]["R/صفقة"], s["اختبار"]["معامل"]))
    for name, cond in ACC.items():
        s2 = summary(replay(cond))
        ok2, ch2 = verdict(s2, s)
        out["البطاقة بمتوسّط مدى %d + %s" % (n, name)] = {"كلّه": s2["كلّه"], "تعلّم": s2["تعلّم"], "اختبار": s2["اختبار"],
                                                        "فحوص_أمام_أساسه": ch2, "يجتاز_أمام_أساسه": ok2}
        log("  + %s: n=%s R=%s R/ص=%s سحب=%s أنصاف=%s | تعلّم %s | اختبار %s معامل=%s | أمام أساسه: %s" % (
            name, s2["كلّه"]["n"], s2["كلّه"]["R"], s2["كلّه"]["R/صفقة"], s2["كلّه"]["سحب_R"], s2["كلّه"]["أنصاف"],
            s2["تعلّم"]["R/صفقة"], s2["اختبار"]["R/صفقة"], s2["اختبار"]["معامل"], "يجتاز" if ok2 else ch2))

json.dump(out, open("analysts_roles_check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
log("تمّ — analysts_roles_check.json")
