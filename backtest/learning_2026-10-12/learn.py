# -*- coding: utf-8 -*-
"""العقل الجامع — امتحان بالمشي إلى الأمام (سجلّ التنفيذ، الخطوات 7–9؛ تفويض المالك الكامل ١٠-١٢) — قياسٌ فقط.

يقرأ جدول التعلّم. لكلّ شهر امتحان k: يتعلّم من كلّ الأشهر قبل k−1، ويختار عتبة الدخول على الشهر k−1، ثمّ يتعلّم من كلّ
ما قبل k ويُطبَّق على الشهر k وحده (خارج العيّنة). في كلّ لحظة يتوقّع أربع نتائج (شراء/بيع × وقف 15/30 نقطة) ويأخذ
أفضلها إن تجاوز العتبة — فاختيار الوقف إدارةٌ متعلَّمة (الخطوة 9)، وحقائق التذبذب والاتّجاه والضوضاء في المدخلات
هي حال السوق (الخطوة 8). صفقةٌ واحدة في وقتٍ واحد؛ والنتيجة بوحدة المخاطرة (خسارة الوقف = 1 = سقف المخاطرة 100$).
**ضبط الحظّ:** المسار نفسه بعد إزاحة النتائج دائريًّا بأسبوعين داخل التدريب — ما يربحه الحظّ لا يُحسب حافّة.
الناتج: تقريرٌ عربيّ في `M:\\QUANT_NQ_DATA\\learning\\تقرير العقل الجامع.md`.
"""
import os
import pathlib
import sys
import time
from datetime import datetime, timezone

import lightgbm as lgb
import numpy as np

LEARN = pathlib.Path(os.environ.get("LEARN_DIR", r"M:\QUANT_NQ_DATA\learning"))
QUANTS = (0.0, 0.05, 0.1, 0.2, 0.3)          # حدّ الربح المتوقَّع بوحدة المخاطرة
TARGETS = ((0, 2, 1, "شراء بوقف 15"), (1, 3, -1, "بيع بوقف 15"), (4, 6, 1, "شراء بوقف 30"), (5, 7, -1, "بيع بوقف 30"))
PARAMS = dict(objective="regression", learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.3,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, verbose=-1, num_threads=10)


def month_of(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m")


def fit_predict(X, y, tr, te_list):
    preds = []
    for col, _, _, _ in TARGETS:
        m = lgb.train(PARAMS, lgb.Dataset(X[tr], y[tr, col]), num_boost_round=200)
        preds.append([m.predict(X[te]) for te in te_list])
    return [np.column_stack([p[i] for p in preds]) for i in range(len(te_list))]


def trade(P, y, t, cut):
    """صفقةٌ واحدة في وقتٍ واحد: أفضل الأربع إن تجاوز العتبة."""
    out, busy = [], -1.0
    for i in np.argsort(t):
        if t[i] < busy:
            continue
        j = int(np.argmax(P[i]))
        if P[i, j] < cut:
            continue
        col, held, _, _ = TARGETS[j]
        out.append((float(y[i, col]), j))
        busy = t[i] + 60 * float(y[i, held])
    return out


def shifted(y, t, days=14):
    order = np.argsort(t)
    k = max(1, int(len(order) * days / 260))
    ys = y.copy()
    ys[order] = y[np.roll(order, k)]
    return ys


def run(X, y, t, months, luck):
    rows = []
    for k in range(3, len(months)):
        mk, mv = months[k], months[k - 1]
        tr_v = np.isin(month_of_arr, months[:k - 1])
        va = month_of_arr == mv
        te = month_of_arr == mk
        yt = shifted(y, t) if luck else y
        # نموذجٌ واحد للشهر: يُختار حدّ الربح المتوقَّع على الشهر السابق ويُطبَّق بالنموذج نفسه على شهر الامتحان (مقياسٌ واحد).
        Pv, Pt = fit_predict(X, yt, tr_v, [va, te])
        best = None
        for q in QUANTS:
            r = sum(x for x, _ in trade(Pv, y[va], t[va], q))
            if best is None or r > best[0]:
                best = (r, q)
        res = trade(Pt, y[te], t[te], best[1])
        rs = [x for x, _ in res]
        rows.append((mk, best[1], len(rs), sum(rs), float(np.mean(rs)) if rs else 0.0,
                     sum(1 for x in rs if x > 0), [sum(1 for _, j in res if j == n) for n in range(4)]))
        print("%s %s شهر %s: صفقات %d · مجموع %.1f" % ("حظّ" if luck else "حقيقيّ", time.strftime("%H:%M"), mk,
                                                      len(rs), sum(rs)), flush=True)
    return rows


def main():
    global month_of_arr
    d = np.load(LEARN / "table.npz")
    X, y, t = d["X"], d["y"].astype(np.float64), d["t"]
    month_of_arr = np.array([month_of(v) for v in t])
    months = sorted(set(month_of_arr))
    real = run(X, y, t, months, luck=False)
    luck = run(X, y, t, months, luck=True)
    lines = ["# تقرير العقل الجامع — امتحان المشي إلى الأمام (%s)" % time.strftime("%Y-%m-%d %H:%M"), "",
             "الجدول: %d لحظة قرار × %d عمود حقائق، أشهر %s ← %s. كلّ شهرٍ يُمتحن بما تعلّمه ممّا قبله وحده." % (
                 X.shape[0], X.shape[1], months[0], months[-1]), "",
             "النتيجة بوحدة المخاطرة: خسارة الوقف = 1 (= 100$ بسقف المالك)، والهدف ضعفا الوقف، بعد تكلفة السبريد.", "",
             "| الشهر | العتبة | صفقات | رابحة | المجموع | المتوسّط | الحظّ: صفقات | الحظّ: المجموع | الأنواع (شراء15·بيع15·شراء30·بيع30) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for a, b in zip(real, luck):
        lines.append("| %s | فوق %+.2f | %d | %d | %+.1f | %+.3f | %d | %+.1f | %s |" % (
            a[0], a[1], a[2], a[5], a[3], a[4], b[2], b[3], "·".join(map(str, a[6]))))
    n, s = sum(r[2] for r in real), sum(r[3] for r in real)
    nl, sl = sum(r[2] for r in luck), sum(r[3] for r in luck)
    pos = sum(1 for r in real if r[3] > 0)
    lines += ["", "**المجموع خارج العيّنة:** %d صفقة · %+.1f وحدة مخاطرة (≈ %+.0f$ بسقف 100$) · متوسّط %+.3f · أشهر رابحة %d من %d." % (
        n, s, s * 100, s / n if n else 0, pos, len(real)),
        "**ضبط الحظّ:** %d صفقة · %+.1f وحدة." % (nl, sl), "",
        "**الحكم:** حافّةٌ تُعرض للحيّ فقط إن كان المجموع موجبًا، وأغلب الأشهر رابحة، والحقيقيّ فوق الحظّ بوضوح."]
    path = LEARN / "تقرير العقل الجامع.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("✓", path, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
