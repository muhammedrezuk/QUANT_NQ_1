# -*- coding: utf-8 -*-
"""التجميع النهائيّ ⟵ results.json: البيانات · (أ) الجهة · (ب) البطاقة (تعلّم/اختبار/الفترة الأقدم) · الدمج · فحوص التسريب."""
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ")
sys.path.insert(0, r"C:\Users\NQ\QUANT_NQ\backtest\card_414")
import glob
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone

import card_replay as R          # R.stats وحده (دالّةٌ صرفة)

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_FIRST, OLD_LAST = "2014-08-01", "2024-10-07"


def load(name):
    return json.load(open(os.path.join(HERE, name), encoding="utf-8"))


def as5(rows):
    return [(x[0], x[2], x[3], x[4], x[5]) for x in rows]


def owner(st):
    halves = st.get("أنصاف") or {}
    pos = sum(1 for v in halves.values() if v > 0)
    ch = {"R/صفقة>0": (st.get("R/صفقة") or -1) > 0, "معامل≥1.15": (st.get("معامل") or 0) >= 1.15,
          "أنصاف_موجبة≥نصفها": len(halves) > 0 and pos * 2 >= len(halves)}
    return {"شروط": ch, "أنصاف_موجبة": "%d/%d" % (pos, len(halves)), "يجتاز": all(ch.values()), "n": st.get("n", 0)}


def main():
    ev, a, b = load("events.json"), load("results_a.json"), load("results_b_2y.json")
    out = {"التصميم": "التصميم.md", "البيانات": {}, "أ": a, "ب": {}, "الدمج_مع_414": b.get("الدمج"), "فحوص": {}}
    # ── البيانات ──
    comps = ev["components"]
    cnt = {}
    for c in comps:
        k = "%s|%s" % (c["cat"], c["src"])
        d = cnt.setdefault(k, {"بإجماع": 0, "بـz": 0, "مكوّنات": Counter()})
        d["بإجماع"] += 1
        d["بـz"] += c["z"] is not None
        d["مكوّنات"][c["comp"]] += 1
    out["البيانات"]["مكوّنات_بإجماع_لكلّ_فئة"] = {k: {**v, "مكوّنات": dict(v["مكوّنات"])} for k, v in sorted(cnt.items())}
    out["البيانات"]["إصدارات(دقائق)_بـz"] = dict(Counter(c["src"] for c in ev["clusters"] if c["cats"]))
    out["فحوص"] = ev["checks"]
    # صلاحيّة سنوات الفترة الأقدم (القاعدة المثبتة في التصميم)
    scan = ev["checks"]["مسح_الإزاحة_بالدقائق"]
    valid = {}
    for y, d in scan.items():
        # ±60 مستثناة: إصدارات 08:30 يقع +60 منها على افتتاح 09:30 (التصميم: التصحيح ١)
        best_off = max((o for o in d if abs(int(o)) != 60), key=lambda o: d[o])
        valid[int(y)] = {"أعلى_إزاحة_د": int(best_off), "قفزة_0": d.get("0"), "صالحة": int(best_off) in (0, 1) and d[best_off] >= 2.0}
    out["فحوص"]["صلاحيّة_السنوات"] = valid
    ok_years = {y for y, v in valid.items() if v["صالحة"]}
    # ── (ب) السنتان ──
    sel = b.get("المختارة")
    out["ب"]["السنتان"] = {"حدّ_التعلّم": b["حدّ_التعلّم"], "المختارة": sel, "ثبات_الشبكة": b.get("ثبات_الشبكة"),
                           "الشبكة_مختصرة": [{"ك": r["ك"], "الجهة": r["الجهة"], "الفئات": r["الفئات"], "ج": r["ج"], "و_د": r["و_د"],
                                               "تعلّم": [r["تعلّم"].get("n"), r["تعلّم"].get("R/صفقة")],
                                               "اختبار": [r["اختبار"].get("n"), r["اختبار"].get("R/صفقة"), r["اختبار"].get("معامل")],
                                               "كلّه": [r["كلّه"].get("n"), r["كلّه"].get("R"), r["كلّه"].get("سحب_R")]}
                                              for r in b["التركيبات"]]}
    # ── (ب) الفترة الأقدم ──
    chunks = sorted(glob.glob(os.path.join(HERE, "old_*.json")))
    per_g = {}
    tallies = {}
    for f in chunks:
        ch = json.load(open(f, encoding="utf-8"))
        for row in ch["التركيبات"]:
            key = tuple(row["g"])
            per_g.setdefault(key, []).extend(row["صفقات"])
            t = tallies.setdefault(key, Counter())
            t.update(row["عدّاد"])
    t0 = datetime.strptime(OLD_FIRST, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    t1 = datetime.strptime(OLD_LAST, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() + 86400
    months_valid = 0.0
    for y in ok_years:
        ya = max(t0, datetime(y, 1, 1, tzinfo=timezone.utc).timestamp())
        yb = min(t1, datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp())
        if yb > ya:
            months_valid += (yb - ya) / (86400 * 30.4375)
    old = {"قطع": [os.path.basename(f) for f in chunks], "سنوات_صالحة": sorted(ok_years),
           "أشهر_صالحة": round(months_valid, 1)}
    grid_old = []
    for key, rows in sorted(per_g.items(), key=lambda kv: str(kv[0])):
        rows = sorted(r for r in rows if datetime.fromtimestamp(r[0], timezone.utc).year in ok_years)
        st = R.stats(as5(rows))
        grid_old.append({"ك": key[0], "الجهة": key[1], "الفئات": key[2], "ج": key[3], "و_د": key[4],
                         "n": st.get("n"), "R/صفقة": st.get("R/صفقة"), "معامل": st.get("معامل"), "R": st.get("R"),
                         "سحب_R": st.get("سحب_R")})
    vals = [g["R/صفقة"] for g in grid_old if g["n"] and g["n"] >= 20]
    old["ثبات_الشبكة"] = {"تركيبات_بـ≥20": len(vals), "موجبة": sum(1 for v in vals if v > 0),
                          "وسيط_R/صفقة": sorted(vals)[len(vals) // 2] if vals else None}
    old["الشبكة"] = grid_old
    if sel:
        key = (sel["ك"], sel["الجهة"], sel["الفئات"], sel["ج"], sel["و_د"])
        rows = sorted(r for r in per_g.get(key, []) if datetime.fromtimestamp(r[0], timezone.utc).year in ok_years)
        st = R.stats(as5(rows))
        by_year = {}
        for r in rows:
            y = datetime.fromtimestamp(r[0], timezone.utc).year
            by_year[y] = round(by_year.get(y, 0.0) + r[2], 2)
        by_cat = {}
        for r in rows:
            for cat in r[3].split("+"):
                by_cat.setdefault(cat, []).append(r)
        old["المختارة"] = {"كلّه": st, "معيار_المالك": owner(st), "حسب_السنة_R": by_year,
                           "صفقات/شهر": round(len(rows) / months_valid, 2) if months_valid else None,
                           "شراء": R.stats(as5([r for r in rows if r[4]])), "بيع": R.stats(as5([r for r in rows if not r[4]])),
                           "حسب_الفئة": {k: R.stats(as5(v)) for k, v in by_cat.items()},
                           "عدّاد": dict(tallies.get(key, {}))}
        json.dump(rows, open(os.path.join(HERE, "trades_best_old.json"), "w", encoding="utf-8"), ensure_ascii=False)
    out["ب"]["الفترة_الأقدم"] = old
    # ── الحكم ──
    if sel:
        t_ok = sel["معيار_المالك_على_الاختبار"]
        o_ok = old.get("المختارة", {}).get("معيار_المالك", {})
        out["الحكم"] = {"التعلّم_R/صفقة": sel["تعلّم"].get("R/صفقة"), "الاختبار": t_ok, "الفترة_الأقدم": o_ok,
                        "يجتاز_المعيار": bool(t_ok.get("يجتاز") and t_ok.get("عدد_كافٍ(≥20)") and o_ok.get("يجتاز")
                                              and (sel["تعلّم"].get("R/صفقة") or -1) > 0)}
    json.dump(out, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # ── ملخّص مطبوع ──
    print("صلاحيّة السنوات:", json.dumps(valid, ensure_ascii=False))
    print("المختارة على الفترة الأقدم:", json.dumps({k: old.get("المختارة", {}).get(k) for k in
                                                   ("كلّه", "معيار_المالك", "حسب_السنة_R", "صفقات/شهر")}, ensure_ascii=False))
    print("ثبات الشبكة الأقدم:", json.dumps(old["ثبات_الشبكة"], ensure_ascii=False))
    print("الحكم:", json.dumps(out.get("الحكم"), ensure_ascii=False))


if __name__ == "__main__":
    main()
