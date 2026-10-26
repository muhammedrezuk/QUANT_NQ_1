# -*- coding: utf-8 -*-
"""احتمال نجاح البطاقة — المرحلة ٢: النسبة الأساسيّة + تقدير احتمالٍ بسيط يُلائَم على أوّل ٧٠٪ ويُقاس على آخر ٣٠٪.

الخطّة مكتوبةٌ قبل النظر في النتائج (لا تُغيَّر بعده):
  الهدف الأساسيّ  : بلوغ الهدف الأوّل (ثلث المسافة) قبل الوقف — «نجاح البطاقة» (بعده الوقف عند الدخول).
  الهدف الثانويّ  : بلوغ الهدف النهائيّ.
  النموذج ٠ (بلا اختيار): النسبة الشرطيّة على النافذة وحدها (لندن/نيويورك) من التعلّم.
  النموذج ١ (الأساسيّ) : انحدارٌ لوجستيّ بثلاث خصائص، تُختار على التعلّم وحده بأكبر |مساحة المنحنى − ٠٫٥|
                         من بين المرشّحات، معياريّةٌ بمتوسّط التعلّم وانحرافه، وتنظيمٌ تربيعيّ λ=10 (حساسيّة: 1 و100).
  التقييم على الاختبار: مساحة المنحنى · ترتيب الاختبار بالاحتمال المقدَّر: النصف الأعلى مقابل الأدنى (R/صفقة،
                         فوز الهدف الأوّل) · قيمة الاحتمال بالتبديل العشوائيّ (20,000) · درجة براير مقابل النسبة الأساسيّة.
  «يميّز» = الفرق (أعلى − أدنى) في R/صفقة موجبٌ واحتمال التبديل < 0.10، ومساحة المنحنى > 0.5 واحتمالها < 0.10،
             والتقدّم المتدحرج (إعادة الملاءمة قبل كلّ صفقة من الصفقة 100) في الجهة نفسها.
"""
import json
import math
from datetime import datetime, timezone

import numpy as np

D = json.load(open("card_prob_trades.json", encoding="utf-8"))
T = D["trades"]
SPLIT = D["meta"]["split"]
T.sort(key=lambda x: x["t"])
for x in T:
    x["is_ny"] = 1.0 if x["window"] == "ny_open" else 0.0
    x["is_buy"] = 1.0 if x["buy"] else 0.0

# المرشّحات للنموذج (كلّها وقت القرار). اليوم والساعة بغرينتش تُفحصان جداولَ فقط (ليستا رتيبتين) لكنّهما تُعدّان في التعدّد.
CANDS = ["is_ny", "min_in_window", "is_buy", "rr", "risk_bps", "risk_atr5", "tgt_atrd",
         "ext_nq_h1", "ext_nq_h4", "ext_sp_h1", "ext_sp_h4", "ext_dj_h1", "ext_dj_h4", "agree_min",
         "pull_depth_atr5", "pull_age_bars", "leg_age_bars", "vol_pct", "atrd_pct", "news_since_min", "news_to_min"]
TABLE_ONLY = ["weekday", "hour_utc", "vol_tercile"]
LOG = {"rr", "risk_bps", "risk_atr5", "pull_depth_atr5", "pull_age_bars", "leg_age_bars", "news_since_min", "news_to_min"}
RNG = np.random.default_rng(20261008)
NPERM = 20000


def val(x, k):
    v = float(x[k])
    return math.log1p(v) if k in LOG else v


def rankdata(a):
    a = np.asarray(a, float)
    order = np.argsort(a, kind="mergesort")
    sa, r, i = a[order], np.empty(len(a)), 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return r


def auc(s, y):
    y = np.asarray(y, bool)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return None
    r = rankdata(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def halves(rows):
    h = {}
    for x in rows:
        dt = datetime.fromtimestamp(x["t"], timezone.utc)
        key = "%d%s" % (dt.year, "أ" if dt.month <= 6 else "ب")
        h[key] = h.get(key, 0.0) + x["r"]
    return {k: round(v, 1) for k, v in sorted(h.items())}


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(100 * (c - w)), round(100 * (c + w))]


def summary(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    rs = [x["r"] for x in rows]
    h1 = sum(x["hit1"] for x in rows); hf = sum(x["hit_final"] for x in rows)
    eq = peak = dd = 0.0
    for r in rs:
        eq += r; peak = max(peak, eq); dd = max(dd, peak - eq)
    return {"n": n, "الهدف_الأوّل%": round(100 * h1 / n, 1), "مجال95_الأوّل": wilson(h1, n),
            "النهائيّ%": round(100 * hf / n, 1), "مجال95_النهائيّ": wilson(hf, n),
            "فوز%": round(100 * sum(r > 0 for r in rs) / n, 1), "R/صفقة": round(sum(rs) / n, 3), "R": round(sum(rs), 1),
            "سحب_R": round(dd, 1), "مراحل": {s: sum(x["stage"] == s for x in rows) for s in range(4)}}


train = [x for x in T if x["t"] < SPLIT]
test = [x for x in T if x["t"] >= SPLIT]
out = {"عدد": {"كلّه": len(T), "تعلّم": len(train), "اختبار": len(test)}}

# ---------- ١) النسبة الأساسيّة لكلّ نافذة ----------
base = {}
for wname, wkey in (("الكلّ", None), ("لندن", "london_peak"), ("نيويورك", "ny_open")):
    sel = (lambda x: True) if wkey is None else (lambda x, w=wkey: x["window"] == w)
    base[wname] = {"كلّه": summary([x for x in T if sel(x)]), "تعلّم": summary([x for x in train if sel(x)]),
                   "اختبار": summary([x for x in test if sel(x)])}
    base[wname]["كلّه"]["أنصاف"] = halves([x for x in T if sel(x)])
out["النسبة_الأساسيّة"] = base

# ---------- ٢) الفحص خاصّةً خاصّة (التعلّم يختار، والاختبار يُعرض للشفافية) ----------
screen = []
for k in CANDS:
    s_tr = [val(x, k) for x in train]; s_te = [val(x, k) for x in test]
    a_tr = auc(s_tr, [x["hit1"] for x in train]); a_te = auc(s_te, [x["hit1"] for x in test])
    af_tr = auc(s_tr, [x["hit_final"] for x in train]); af_te = auc(s_te, [x["hit_final"] for x in test])
    med = float(np.median(s_tr))
    if k in ("is_ny", "is_buy"):
        med = 0.5
    def rr_split(rows, sv):
        hi = [x["r"] for x, v in zip(rows, sv) if v > med]; lo = [x["r"] for x, v in zip(rows, sv) if v <= med]
        return (round(sum(hi) / len(hi), 3) if hi else None, len(hi), round(sum(lo) / len(lo), 3) if lo else None, len(lo))
    screen.append({"خاصّة": k, "مساحة_تعلّم_الأوّل": round(a_tr, 3), "مساحة_اختبار_الأوّل": round(a_te, 3),
                   "مساحة_تعلّم_النهائيّ": round(af_tr, 3), "مساحة_اختبار_النهائيّ": round(af_te, 3),
                   "R/ص_فوق_وتحت_الوسيط_تعلّم": rr_split(train, s_tr), "R/ص_فوق_وتحت_الوسيط_اختبار": rr_split(test, s_te),
                   "نفس_الجهة": (a_tr - 0.5) * (a_te - 0.5) > 0})
out["الفحص"] = screen
out["الجهة_نفسها_في_الاختبار"] = "%d من %d" % (sum(s["نفس_الجهة"] for s in screen), len(screen))


def group_table(key):
    res = {}
    for part, rows in (("تعلّم", train), ("اختبار", test), ("كلّه", T)):
        g = {}
        for x in rows:
            g.setdefault(str(x[key]), []).append(x)
        res[part] = {kk: {"n": len(v), "الأوّل%": round(100 * sum(z["hit1"] for z in v) / len(v)),
                          "R/صفقة": round(sum(z["r"] for z in v) / len(v), 3)} for kk, v in sorted(g.items())}
    return res


out["جداول"] = {k: group_table(k) for k in TABLE_ONLY}
for x in T:
    x["half_window"] = "%s_%s" % (x["window"], "أوّل" if x["min_in_window"] < (90 if x["window"] == "london_peak" else 75) else "ثانٍ")
out["جداول"]["نصف_النافذة"] = group_table("half_window")


# ---------- ٣) النماذج ----------
def fit_logit(X, y, lam):
    n, k = X.shape
    Xb = np.hstack([np.ones((n, 1)), X]); w = np.zeros(k + 1)
    P = np.eye(k + 1) * lam; P[0, 0] = 0.0
    for _ in range(200):
        p = 1 / (1 + np.exp(-Xb @ w))
        g = Xb.T @ (p - y) + P @ w
        H = Xb.T @ (Xb * (p * (1 - p))[:, None]) + P
        step = np.linalg.solve(H, g); w -= step
        if np.abs(step).max() < 1e-10:
            break
    return w


def procedure(rows, target="hit1", k=3, lam=10.0, feats=None):
    """الاختيار + المعياريّة + الملاءمة — كلّه من `rows` وحدها. يُرجع دالّة احتمال ووصفها."""
    y = np.array([1.0 if x[target] else 0.0 for x in rows])
    if feats is None:
        sc = sorted(((abs(auc([val(x, c) for x in rows], y) - 0.5), c) for c in CANDS), reverse=True)
        feats = [c for _, c in sc[:k]]
    X = np.array([[val(x, c) for c in feats] for x in rows])
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    w = fit_logit((X - mu) / sd, y, lam)

    def prob(x):
        z = (np.array([val(x, c) for c in feats]) - mu) / sd
        return float(1 / (1 + math.exp(-(w[0] + z @ w[1:]))))
    return prob, {"خصائص": feats, "متوسّط": mu.round(6).tolist(), "انحراف": sd.round(6).tolist(),
                  "معاملات(ثابت أوّلًا)": w.round(6).tolist(), "λ": lam, "الهدف": target}


def perm_p_diff(r, p, n=NPERM):
    """احتمال أن يعطي ترتيبٌ عشوائيّ فرقَ (النصف الأعلى − الأدنى) في R/صفقة ≥ المرصود (جهةٌ واحدة)."""
    r = np.asarray(r); order = np.argsort(-np.asarray(p), kind="mergesort"); h = len(r) // 2
    top, bot = order[:h], order[len(r) - h:]
    obs = r[top].mean() - r[bot].mean()
    cnt = 0
    for _ in range(n):
        q = RNG.permutation(len(r))
        cnt += (r[q[:h]].mean() - r[q[len(r) - h:]].mean()) >= obs - 1e-12
    return float(obs), (cnt + 1) / (n + 1), top, bot


def perm_p_auc(p, y, n=NPERM):
    obs = auc(p, y); y = np.asarray(y, bool); r = rankdata(p); n1 = y.sum(); n0 = len(y) - n1
    cnt = 0
    for _ in range(n):
        yy = y[RNG.permutation(len(y))]
        cnt += ((r[yy].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) >= obs - 1e-12
    return obs, (cnt + 1) / (n + 1)


def evaluate(prob, rows, label, target="hit1"):
    p = [prob(x) for x in rows]
    y1 = [x["hit1"] for x in rows]; yf = [x["hit_final"] for x in rows]; r = [x["r"] for x in rows]
    diff, pd, top, bot = perm_p_diff(r, p)
    a1, pa1 = perm_p_auc(p, y1)
    yt = [x[target] for x in rows]
    br_tr = sum(x[target] for x in train) / len(train)          # النسبة الأساسيّة للهدف نفسه من التعلّم
    brier = float(np.mean([(pp - yy) ** 2 for pp, yy in zip(p, yt)]))
    brier0 = float(np.mean([(br_tr - yy) ** 2 for yy in yt]))
    T_ = [rows[i] for i in top]; B_ = [rows[i] for i in bot]
    return {"نموذج": label, "مساحة_الأوّل": round(a1, 3), "احتمال_التبديل_للمساحة": round(pa1, 4),
            "مساحة_النهائيّ": round(auc(p, yf), 3),
            "النصف_الأعلى": summary(T_), "النصف_الأدنى": summary(B_),
            "فرق_R/صفقة": round(diff, 3), "احتمال_التبديل_للفرق": round(pd, 4),
            "براير": round(brier, 4), "براير_بالنسبة_الأساسيّة_من_التعلّم": round(brier0, 4),
            "مدى_الاحتمال_المقدَّر": [round(min(p), 3), round(float(np.median(p)), 3), round(max(p), 3)]}


base_rate_tr = sum(x["hit1"] for x in train) / len(train)
models = []
# النموذج ٠: النافذة وحدها
rate = {w: sum(x["hit1"] for x in train if x["window"] == w) / max(1, sum(x["window"] == w for x in train))
        for w in ("london_peak", "ny_open")}
m0 = evaluate(lambda x: rate[x["window"]], test, "٠: النافذة وحدها (النصفان مختلطان عند التعادل — الجدول الأساسيّ أصدق)")
m0["الجدول"] = {k: round(v, 3) for k, v in rate.items()}
models.append(m0)
for lam in (10.0, 1.0, 100.0):
    for target in ("hit1", "hit_final"):
        prob, desc = procedure(train, target=target, lam=lam)
        e = evaluate(prob, test, "١: لوجستيّ ٣ خصائص · %s · λ=%g" % (target, lam), target)
        e["الوصف"] = desc
        e["على_التعلّم_نفسه"] = {k: v for k, v in evaluate(prob, train, "تعلّم", target).items() if k in ("مساحة_الأوّل", "مساحة_النهائيّ", "فرق_R/صفقة")}
        models.append(e)
out["النماذج_على_الاختبار"] = models

# ---------- ٤) التقدّم المتدحرج: الإجراء نفسه يُعاد قبل كلّ صفقة من الصفقة 100 ----------
wf = []
for i in range(100, len(T)):
    prob, desc = procedure(T[:i], target="hit1", lam=10.0)
    p_tr = [prob(x) for x in T[:i]]
    pi = prob(T[i])
    wf.append({"i": i, "p": pi, "عالٍ": pi > float(np.median(p_tr)), "r": T[i]["r"], "hit1": T[i]["hit1"],
               "خصائص": desc["خصائص"]})
hi_ = [w for w in wf if w["عالٍ"]]; lo_ = [w for w in wf if not w["عالٍ"]]
r_hi = np.array([w["r"] for w in hi_]); r_lo = np.array([w["r"] for w in lo_])
obs = r_hi.mean() - r_lo.mean()
allr = np.array([w["r"] for w in wf]); nh = len(hi_); cnt = 0
for _ in range(NPERM):
    q = RNG.permutation(len(allr))
    cnt += (allr[q[:nh]].mean() - allr[q[nh:]].mean()) >= obs - 1e-12
a_wf, pa_wf = perm_p_auc([w["p"] for w in wf], [w["hit1"] for w in wf])
feat_freq = {}
for w in wf:
    for f in w["خصائص"]:
        feat_freq[f] = feat_freq.get(f, 0) + 1
out["التقدّم_المتدحرج"] = {
    "عدد_خارج_العيّنة": len(wf), "مساحة_الأوّل": round(a_wf, 3), "احتمال_التبديل_للمساحة": round(pa_wf, 4),
    "عالٍ": {"n": len(hi_), "الأوّل%": round(100 * sum(w["hit1"] for w in hi_) / len(hi_), 1), "R/صفقة": round(float(r_hi.mean()), 3)},
    "منخفض": {"n": len(lo_), "الأوّل%": round(100 * sum(w["hit1"] for w in lo_) / len(lo_), 1), "R/صفقة": round(float(r_lo.mean()), 3)},
    "فرق": round(float(obs), 3), "احتمال_التبديل_للفرق": round((cnt + 1) / (NPERM + 1), 4),
    "تكرار_الخصائص_المختارة": dict(sorted(feat_freq.items(), key=lambda kv: -kv[1]))}

json.dump(out, open("card_prob_model.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def show(o, ind=0):
    print(json.dumps(o, ensure_ascii=False))


print("== العدد ==", out["عدد"])
print("== النسبة الأساسيّة ==")
for w, v in base.items():
    for part in ("كلّه", "تعلّم", "اختبار"):
        s = v[part]
        print("%-8s %-6s n=%3d الأوّل=%5.1f%% %s النهائيّ=%5.1f%% %s فوز=%5.1f%% R/ص=%+.3f R=%+.1f سحب=%.1f مراحل=%s" % (
            w, part, s["n"], s["الهدف_الأوّل%"], s["مجال95_الأوّل"], s["النهائيّ%"], s["مجال95_النهائيّ"], s["فوز%"],
            s["R/صفقة"], s["R"], s["سحب_R"], s["مراحل"]))
    print("         أنصاف:", v["كلّه"]["أنصاف"])
print("== الفحص (مساحة المنحنى للهدف الأوّل: تعلّم ⟵ اختبار) ==", out["الجهة_نفسها_في_الاختبار"])
for s in sorted(screen, key=lambda s: -abs(s["مساحة_تعلّم_الأوّل"] - 0.5)):
    print("%-16s تعلّم=%.3f اختبار=%.3f | نهائيّ تعلّم=%.3f اختبار=%.3f | R/ص فوق/تحت الوسيط تعلّم=%s اختبار=%s %s" % (
        s["خاصّة"], s["مساحة_تعلّم_الأوّل"], s["مساحة_اختبار_الأوّل"], s["مساحة_تعلّم_النهائيّ"], s["مساحة_اختبار_النهائيّ"],
        s["R/ص_فوق_وتحت_الوسيط_تعلّم"], s["R/ص_فوق_وتحت_الوسيط_اختبار"], "✓" if s["نفس_الجهة"] else "✗"))
print("== الجداول ==")
for k, v in out["جداول"].items():
    print(k); [print("  ", part, vv) for part, vv in v.items()]
print("== النماذج على الاختبار ==")
for m in models:
    print("%s | مساحة=%.3f (تبديل %.4f) نهائيّ=%.3f | أعلى n=%d الأوّل=%.1f%% R/ص=%+.3f | أدنى n=%d الأوّل=%.1f%% R/ص=%+.3f | فرق=%+.3f (تبديل %.4f) | براير=%.4f مقابل %.4f | مدى=%s" % (
        m["نموذج"], m["مساحة_الأوّل"], m["احتمال_التبديل_للمساحة"], m["مساحة_النهائيّ"],
        m["النصف_الأعلى"]["n"], m["النصف_الأعلى"]["الهدف_الأوّل%"], m["النصف_الأعلى"]["R/صفقة"],
        m["النصف_الأدنى"]["n"], m["النصف_الأدنى"]["الهدف_الأوّل%"], m["النصف_الأدنى"]["R/صفقة"],
        m["فرق_R/صفقة"], m["احتمال_التبديل_للفرق"], m["براير"], m["براير_بالنسبة_الأساسيّة_من_التعلّم"], m["مدى_الاحتمال_المقدَّر"]))
    if "الوصف" in m:
        print("     ", m["الوصف"]["خصائص"], m["الوصف"]["معاملات(ثابت أوّلًا)"], "| على التعلّم:", m["على_التعلّم_نفسه"])
print("== التقدّم المتدحرج ==")
show(out["التقدّم_المتدحرج"])
