# -*- coding: utf-8 -*-
"""معايرة ذرّة الزخم 152 وحدها — بلا استراتيجيّة (ختم المالك «nq» ٢٠٢٦-١٠-١٤: «هاد محطوط 25 هاد رقم غير صحيح بده معايرة
لازم مقيس عليه … عايرها لحالها»).

السؤال الوحيد لذرّةٍ بلا استراتيجيّة: أيّ نافذةٍ تجعل رقمها يسبق الحركة التي بعده؟
الأرقام الثلاثة بمعادلات الذرّة حرفًا (يُتحقَّق من التطابق مع كود الذرّة الحيّ قبل القياس، وبتقريبها المنشور):
  صافي الحركة(ن)    = (الإغلاق ÷ إغلاق ما قبل ن − 1) × 100            ⟵ يُقاس على عائد الشموع الخمس التالية.
  الاستمرار(ن)      = حصّة الشموع المتحرّكة في جهة صافي الحركة(25) من آخر ن ⟵ على عائد الخمس التالية في تلك الجهة.
  الدفعة المحاذية(ن) = |حركة آخر شمعة| ÷ متوسّط |الحركة| في آخر ن، موجبةً إن كانت مع جهة صافي الحركة(25) وسالبةً ضدّها
                       ⟵ على عائد الخمس التالية في تلك الجهة.
كلّ نافذةٍ تُعايَر وحدها والأخريان على 25 (الحيّ). الشموع: الناسداك، تُبنى من شموع الدقيقة بدالّة 103 الحيّة.
المقياس: ارتباط الرتب بين الرقم والعائد التالي (−1…+1؛ موجب = استمرار، سالب = انعكاس) على عيّناتٍ كلّ 5 شموع بلا تداخل،
لكلّ سنة. يُستبعد أفقٌ يعبر فجوةً أطول من 3 ساعات (العطلة).
النوافذ: 5 8 10 12 15 20 25 30 40 50 60 80 100 150 200 · الإطارات: 1د 5د 15د 1س 4س.

القواعد — مكتوبةٌ قبل النتائج:
  البناء 2016–2020: قوّة النافذة على إطار = متوسّط ارتباط سنواته إن ثبتت إشارته في 4 سنواتٍ من 5، وإلّا صفر.
  النافذة الواحدة للرقم (الذرّة تحمل نافذةً واحدة لكلّ الإطارات) = الأعلى بمتوسّط قوّتها المطلقة على الإطارات الخمسة.
  الامتحان 2021-01 ⟵ 2025-09 مرّةً واحدة: تُعتمد بدل 25 إن (أ) ثبتت إشارتها كما في البناء في 3 سنواتٍ من 5 على عددٍ من
  الإطارات لا يقلّ عن 25، و(ب) متوسّط قوّتها المطلقة على الإطارات في الامتحان أعلى من 25.
  المرجع 2025-10 ⟵ اليوم للعلم.
⚠️ معلن: الزخم قيس على هذا التاريخ سبع مرّات (١٠-١٣) ⟸ هذه المحاولة الثامنة، والامتحان رأته تلك القياسات بنافذة 25.
الجزء المعزول الوحيد هو المستقبل ⟸ النافذة المختارة تُضاف إلى السجلّ الأماميّ الليليّ بجانب 25، وهو الحكم الأخير.
والسبق ليس ربحًا: قيس ١٠-١٣ أنّ أثر الزخم أصغر من السبريد.

المحاولة التاسعة (١٠-١٤ 00:28، أمر المالك بعد رؤية الثامنة: «وسع نوافذ لا اكثر من 200»): الشبكة نفسها + 250 300 400 500 600
800 1000، والقواعد نفسها حرفًا، والاختيار من الشبكة كلّها (22 نافذة). تقرير الثامنة محفوظ باسمه.

الاستعمال: python calib152.py  ⟵ «تقرير معايرة ذرّة الزخم.md» + results.json بجانبه
"""
import importlib.util
import json
import pathlib
import sqlite3
import sys
import time
from collections import deque

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "run.log", "a", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, str(ROOT))
HIST = "file:%s?mode=ro" % (ROOT / "forex_runtime/var/history/ctrader_history.db").as_posix()
FRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
AR_FRAME = {"1m": "1د", "5m": "5د", "15m": "15د", "1h": "1س", "4h": "4س"}
WINDOWS = (5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200, 250, 300, 400, 500, 600, 800, 1000)
LIVE, H, STEP, GAP, MIN_CANDLES = 25, 5, 5, 3 * 3600, 120
NUMBERS = ("roc", "persistence", "impulse_aligned")
AR_NUM = {"roc": "صافي الحركة", "persistence": "الاستمرار", "impulse_aligned": "الدفعة المحاذية"}
BUILD_Y, TEST_Y = (2016, 2017, 2018, 2019, 2020), (2021, 2022, 2023, 2024, 2025)
TEST_END = 1759276800          # 2025-10-01 غرينتش — ما بعده مرجع


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


try:
    from scipy.stats import rankdata
except ImportError:                                     # بلا مكتبة الإحصاء: رتبٌ متوسّطة للمتعادلات بالفرز
    def rankdata(x):
        x = np.asarray(x)
        order = np.argsort(x, kind="mergesort")
        xs = x[order]
        r = np.empty(len(x))
        i = 0
        while i < len(x):
            j = i
            while j + 1 < len(x) and xs[j + 1] == xs[i]:
                j += 1
            r[order[i:j + 1]] = (i + j) / 2.0 + 1
            i = j + 1
        return r


def spearman(x, y):
    if len(x) < 30:
        return None
    rx, ry = rankdata(x), rankdata(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def bars(t, c, sec, fps103):
    """شموع الإطار بدالّة 103: البداية والإغلاق (آخر دقيقةٍ فيها)."""
    if sec <= 3600:
        k = t - t % sec
    else:
        # فوق الساعة: بداية الفترة بيوم الوسيط وإزاحته ساعاتٌ كاملة ⟸ واحدةٌ لكلّ دقائق الساعة نفسها.
        hours, inv = np.unique(t // 3600, return_inverse=True)
        start = np.array([fps103(float(h * 3600), float(sec)) for h in hours], dtype=np.int64)
        k = start[inv]
    last = np.r_[np.nonzero(np.diff(k))[0], len(k) - 1]
    return k[last], c[last]


def numbers(C, w_roc, w_imp, w_per):
    """الأرقام الثلاثة لكلّ شمعة بمعادلات الذرّة وتقريبها المنشور (nan حيث لا تنشر الذرّة)."""
    n = len(C)
    need = max(w_roc, w_imp, w_per, MIN_CANDLES) + 1
    d = np.diff(C)                                      # d[j] = C[j+1] − C[j]
    idx = np.arange(n)
    ok = idx >= need - 1
    roc = np.full(n, np.nan)
    past = np.r_[np.full(w_roc, np.nan), C[:-w_roc]]
    roc[ok] = (C[ok] - past[ok]) / past[ok] * 100.0
    direction = np.sign(roc)
    # الدفعة: |d[i−1]| ÷ متوسّط |d[i−w … i−1]|
    ad = np.r_[0.0, np.cumsum(np.abs(d))]               # ad[j] = Σ|d[0…j−1]|
    imp = np.full(n, np.nan)
    i = idx[ok]
    avg = (ad[i] - ad[i - w_imp]) / w_imp
    last = np.abs(d[i - 1])
    imp[ok] = np.where(avg > 0, last / np.where(avg > 0, avg, 1), 0.0)
    lm = np.r_[np.nan, d]                               # حركة آخر شمعة عند i = d[i−1]
    al = np.full(n, np.nan)
    a = np.where((direction[ok] == 0) | (lm[ok] == 0), 0.0, np.where(lm[ok] * direction[ok] > 0, imp[ok], -imp[ok]))
    al[ok] = a
    up = np.r_[0, np.cumsum(d > 0)]
    dn = np.r_[0, np.cumsum(d < 0)]
    ups, dns = up[i] - up[i - w_per], dn[i] - dn[i - w_per]
    tot = ups + dns
    per = np.full(n, np.nan)
    dr = direction[ok]
    per[ok] = np.where((tot == 0) | (dr == 0), 0.5, np.where(dr > 0, ups, dns) / np.where(tot == 0, 1, tot))
    return {"roc": np.round(roc, 4), "impulse_aligned": np.round(al, 2), "persistence": np.round(per, 2),
            "_impulse": imp, "_dir": direction, "_roc_raw": roc, "_per_raw": per}


def self_check(K, C, atom_mod):
    """يطابق الحساب كود الذرّة الحيّ على 300 شمعةٍ عشوائيّة (قبل التقريب)."""
    atom = atom_mod.Atom()
    rng = np.random.default_rng(7)
    worst = 0.0
    for w in (8, 25, 60, 200):
        v = numbers(C, w, w, w)
        for i in rng.integers(260, len(C) - 1, size=75):
            dq = deque(C[i - 220:i + 1].tolist(), maxlen=221)
            r = atom._roc(dq, w)
            dirn = 1 if r > 0 else -1 if r < 0 else 0
            worst = max(worst, abs(r - v["_roc_raw"][i]), abs(atom._impulse(dq, w) - v["_impulse"][i]),
                        abs(atom._persistence(dq, w, dirn) - v["_per_raw"][i]))
    return worst


def main():
    tic = time.time()
    m103 = load_module(ROOT / "atoms" / "قسم 100-149" / "103_باني_الشموع" / "atom.py", "_c103")
    m152 = load_module(ROOT / "atoms" / "قسم 150-199" / "152_الزخم" / "atom.py", "_c152")
    con = sqlite3.connect(HIST, uri=True)
    a = np.array(con.execute("select period_start, close from candles_history where symbol='USTEC' and period='M1' "
                             "order by period_start").fetchall(), dtype=np.float64)
    con.close()
    t, c = a[:, 0].astype(np.int64), a[:, 1]
    lim = int(__import__("os").environ.get("CALIB152_LIMIT") or 0)     # تجربة قصيرة على آخر الدقائق
    if lim:
        t, c = t[-lim:], c[-lim:]
    print("دقائق", len(t), flush=True)
    res = {}
    check = None
    for fr, sec in FRAMES.items():
        K, C = bars(t, c, sec, m103.frame_period_start)
        if fr == "1h":
            check = self_check(K, C, m152)
            print("أسوأ فرقٍ عن كود الذرّة:", check, flush=True)
        years = K.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
        fwd = np.full(len(C), np.nan)
        j = np.arange(len(C) - H)
        good = (K[j + H] - K[j]) <= H * sec + GAP
        fwd[j[good]] = np.log(C[j[good] + H] / C[j[good]]) * 1e4
        live = numbers(C, LIVE, LIVE, LIVE)
        dir25 = live["_dir"]
        samp = np.arange(0, len(C), STEP)
        for num in NUMBERS:
            for w in WINDOWS:
                v = numbers(C, w if num == "roc" else LIVE, w if num == "impulse_aligned" else LIVE,
                            w if num == "persistence" else LIVE)[num]
                y = fwd if num == "roc" else fwd * dir25
                s = samp[np.isfinite(v[samp]) & np.isfinite(y[samp]) & ((num == "roc") | (dir25[samp] != 0))]
                per_year = {}
                for yr in sorted(set(years[s])):
                    m = s[(years[s] == yr) & ((K[s] < TEST_END) if yr == 2025 else True)]
                    ic = spearman(v[m], y[m])
                    if ic is not None:
                        per_year[int(yr)] = (round(ic, 4), int(len(m)))
                ref = s[K[s] >= TEST_END]
                res[(num, fr, w)] = {"years": per_year, "ref": spearman(v[ref], y[ref]), "ref_n": int(len(ref))}
        print(fr, "تمّ", int(time.time() - tic), "ث", flush=True)
    report(res, check, len(t), int(time.time() - tic))


def strength(cell, years, sign=None):
    ics = [cell["years"][y][0] for y in years if y in cell["years"]]
    if len(ics) < len(years):
        return 0.0, 0
    mean = float(np.mean(ics))
    sg = sign if sign is not None else np.sign(mean)
    same = sum(1 for x in ics if np.sign(x) == sg and x != 0)
    need = 4 if sign is None else 3
    return (mean if same >= need and np.sign(mean) == sg else 0.0), same


def report(res, check, n_min, secs):
    L = ["# تقرير معايرة ذرّة الزخم 152 وحدها — بلا استراتيجيّة (ختم المالك ١٠-١٤)", "",
         "السؤال: أيّ نافذةٍ تجعل رقم الذرّة يسبق حركة الشموع الخمس التالية؟ المقياس ارتباط الرتب (−1…+1) × 100 لسهولة القراءة: "
         "موجب = الحركة تستمرّ، سالب = تنعكس، وقرب الصفر = لا علاقة. القواعد كُتبت قبل النتائج (رأس الأداة).",
         "حساب الأداة يطابق كود الذرّة الحيّ (أسوأ فرقٍ على 300 شمعة: %.1e) · %d دقيقة ناسداك · %d ثانية." % (check, n_min, secs),
         "⚠️ **المحاولة التاسعة** على تاريخ الزخم (وُسّعت النوافذ فوق 200 بأمر المالك بعد رؤية الثامنة)، والامتحان رأته المحاولات قبلها ⟸ الحكم الأخير للسجلّ الأماميّ.", ""]
    picks = {}
    out = {}
    for num in NUMBERS:
        L += ["## %s" % AR_NUM[num], "", "**البناء 2016–2020** (متوسّط السنوات × 100؛ ✓ = ثبتت الإشارة في 4 سنواتٍ من 5):", "",
              "| النافذة | " + " | ".join(AR_FRAME[f] for f in FRAMES) + " | القوّة على الإطارات |", "|---" * (len(FRAMES) + 2) + "|"]
        score = {}
        for w in WINDOWS:
            cells, strs = [], []
            for fr in FRAMES:
                cell = res[(num, fr, w)]
                ics = [cell["years"][y][0] for y in BUILD_Y if y in cell["years"]]
                st, same = strength(cell, BUILD_Y)
                strs.append(abs(st))
                cells.append(("%+.1f%s" % (np.mean(ics) * 100, " ✓" if st else "")) if ics else "—")
            score[w] = float(np.mean(strs))
            L.append("| %d%s | %s | %.2f |" % (w, " (الحيّ)" if w == LIVE else "", " | ".join(cells), score[w] * 100))
        best = max(WINDOWS, key=lambda w: score[w])
        pick = best if score[best] > 0 else LIVE
        picks[num] = pick
        L += ["", "**المختار في البناء: %d**%s" % (pick, "" if score[best] > 0 else " — لا نافذة ثبتت إشارتها، فيبقى 25"), ""]
        # الامتحان: المختار مقابل 25، بإشارة البناء لكلّ إطار.
        rows, tot = [], {}
        for w in sorted({pick, LIVE}):
            stab, strs = 0, []
            cells = []
            for fr in FRAMES:
                cell = res[(num, fr, w)]
                bics = [cell["years"][y][0] for y in BUILD_Y if y in cell["years"]]
                bsign = np.sign(np.mean(bics)) if bics else 0
                st, same = strength(cell, TEST_Y, sign=bsign)
                tics = [cell["years"][y][0] for y in TEST_Y if y in cell["years"]]
                stab += 1 if st else 0
                strs.append(abs(st))
                cells.append("%+.1f (%d/5)" % (np.mean(tics) * 100, same) if tics else "—")
            tot[w] = (stab, float(np.mean(strs)))
            rows.append("| %d%s | %s | %d | %.2f |" % (w, " (الحيّ)" if w == LIVE else "", " | ".join(cells), stab, tot[w][1] * 100))
        L += ["**الامتحان 2021-01 ⟵ 2025-09** (متوسّط × 100، وبين القوسين سنواتٌ بإشارة البناء من 5):", "",
              "| النافذة | " + " | ".join(AR_FRAME[f] for f in FRAMES) + " | إطاراتٌ ثابتة | القوّة |", "|---" * (len(FRAMES) + 3) + "|"] + rows
        adopt = pick != LIVE and tot[pick][0] >= tot[LIVE][0] and tot[pick][1] > tot[LIVE][1]
        L += ["", "**الحكم: %s**" % (("تُعتمد النافذة %d بدل 25" % pick) if adopt else
                                     ("تبقى 25" + (" — المختار %d لم يتحقّق شرطاه في الامتحان" % pick if pick != LIVE else ""))), ""]
        ref = ["%s %+.1f" % (AR_FRAME[fr], (res[(num, fr, w)]["ref"] or 0) * 100) for w in (pick,) for fr in FRAMES]
        L += ["المرجع 2025-10 ⟵ اليوم للنافذة %d: %s" % (pick, " · ".join(ref)), ""]
        out[num] = {"pick": pick, "adopt": adopt, "score_build": {str(k): v for k, v in score.items()},
                    "test": {str(k): v for k, v in tot.items()}}
    L += ["## الخلاصة", ""]
    for num in NUMBERS:
        o = out[num]
        L.append("- %s: %s" % (AR_NUM[num], ("تُعتمد %d بدل 25" % o["pick"]) if o["adopt"] else "تبقى 25"))
    L += ["", "الخطوة التالية بالقانون: النافذة المختارة تُضاف إلى السجلّ الأماميّ الليليّ بجانب 25، والسبق ليس ربحًا بعد السبريد.", ""]
    (HERE / "تقرير معايرة ذرّة الزخم.md").write_text("\n".join(L), encoding="utf-8")
    serial = {"%s|%s|%d" % k: v for k, v in res.items()}
    (HERE / "results.json").write_text(json.dumps({"cells": serial, "summary": out}, ensure_ascii=False, indent=0),
                                       encoding="utf-8")
    print("انتهى", flush=True)


if __name__ == "__main__":
    main()
