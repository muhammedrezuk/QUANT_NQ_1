# -*- coding: utf-8 -*-
"""المنظومة كاملةً على تِكّات سي‑تريدر الحقيقيّة، يومًا يومًا في نافذتَي المالك، وتقريرٌ لكلّ شهر — أمر المالك:
«شغّل على 5 أنوية لندن ونيويورك … خلّيه كلّ شهر يعطيك تقرير، مو يشتغل أيّام وبالأخير يطلع فارغ بسبب خطأ مطبعيّ».

كلّ يوم عملٍ تشغيلٌ مستقلّ لـ `backtest.full_replay` من 06:30 إلى 18:15 غرينتش (يغطّي لندن 08:15 ونيويورك حتّى 13:00
صيفًا وشتاءً) بإحماء ساعة، والأيّام متوازية على الأنوية. بعد كلّ شهر: تقريرٌ بالصفقات والنتيجة والأعطال.
**حارس الفراغ:** إن انتهى الشهر الأوّل بلا صفقةٍ واحدة أو بأعطالٍ في أكثر من ربع أيّامه، يتوقّف كلّ شيء ويكتب السبب.

الاستعمال: python monthly_replay.py --from 2025-10-13 --to 2026-10-05 --parallel 5 [--smoke 5]
"""
import argparse
import csv
import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import date, datetime, timedelta

ROOT = pathlib.Path(r"C:\Users\NQ\QUANT_NQ")
VPY = ROOT / "vendor" / "python" / "runtime" / "python.exe"
OUT = pathlib.Path(__file__).resolve().parent / "runs"
REP = pathlib.Path(__file__).resolve().parent / "reports"
BELOW_NORMAL = 0x00004000


def days(a, b):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def launch(d):
    run = OUT / d.isoformat()
    run.mkdir(parents=True, exist_ok=True)
    log = open(run / "stdout.log", "w", encoding="utf-8")
    err = open(run / "stderr.log", "w", encoding="utf-8")
    cmd = [str(VPY), "-m", "backtest.full_replay", "--from", f"{d.isoformat()}T06:30", "--to", f"{d.isoformat()}T18:15",
           # الإس آند بي قرين البطاقة 414 (لا تتداول بلا اتّفاق جهته) — تجربة الأيّام الخمسة بالناسداك وحده خرجت بلا صفقة.
           "--symbols", "USTEC,US500", "--source", "ctrader", "--warmup-hours", "1", "--out", str(run / "run"), "--name", d.isoformat()]
    return subprocess.Popen(cmd, cwd=str(ROOT), stdout=log, stderr=err, creationflags=BELOW_NORMAL), run


def day_result(run):
    s = run / "run" / "summary.json"
    if not s.exists():
        tail = (run / "stderr.log").read_text(encoding="utf-8", errors="replace")[-600:]
        return {"ok": False, "why": "بلا ملخّص", "tail": tail}
    j = json.loads(s.read_text(encoding="utf-8"))
    trades = []
    tc = run / "run" / "trades.csv"
    if tc.exists():
        with open(tc, encoding="utf-8") as fh:
            trades = list(csv.DictReader(fh))
    bal = j.get("الرصيد") or {}
    return {"ok": True, "ticks": j.get("تِكّات"), "secs": j.get("زمن_التشغيل_ث"), "closed": j.get("صفقات_مغلقة"),
            "partials": j.get("إغلاقات_جزئيّة"), "net": bal.get("صافي"), "dd": bal.get("أقصى_سحب"),
            "failed_atoms": j.get("ذرّات_فشلت") or {}, "rejects": j.get("رفض_الأوامر_داخل_النظام") or {},
            "trades": trades}


def month_report(month, results):
    lines = [f"# تقرير شهر {month} — المنظومة كاملةً على تِكّات سي‑تريدر (نافذتا المالك)", ""]
    ok = [r for r in results.values() if r.get("ok")]
    bad = {d: r for d, r in results.items() if not r.get("ok")}
    closed = sum(r["closed"] or 0 for r in ok)
    net = sum(r["net"] or 0 for r in ok)
    rejects = {}
    for r in ok:
        for k, v in r["rejects"].items():
            rejects[k] = rejects.get(k, 0) + (v if isinstance(v, (int, float)) else 1)
    lines += [f"- أيّام: {len(results)} · سليمة {len(ok)} · معطوبة {len(bad)}",
              f"- صفقات مغلقة: {closed} · صافي: {net:+.2f}$",
              f"- رفض أوامر داخل النظام: {json.dumps(rejects, ensure_ascii=False)}", ""]
    lines.append("| اليوم | تِكّات | صفقات | صافي $ | أقصى سحب |")
    lines.append("|---|---|---|---|---|")
    for d in sorted(results):
        r = results[d]
        if r.get("ok"):
            lines.append(f"| {d} | {r['ticks']} | {r['closed']} | {r['net']} | {r['dd']} |")
        else:
            lines.append(f"| {d} | ✗ {r['why']} | | | |")
    if bad:
        lines += ["", "## الأعطال"] + [f"- {d}: {r.get('why')} — `{(r.get('tail') or '')[-300:]}`" for d, r in bad.items()]
    REP.mkdir(parents=True, exist_ok=True)
    (REP / f"{month}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    json.dump(results, open(REP / f"{month}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    return closed, len(bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--parallel", type=int, default=5)
    ap.add_argument("--smoke", type=int, default=0, help="أوّل N يومًا وحدها (تجربة)")
    a = ap.parse_args()
    all_days = list(days(date.fromisoformat(a.start), date.fromisoformat(a.end)))
    if a.smoke:
        all_days = all_days[:a.smoke]
    by_month = {}
    for d in all_days:
        by_month.setdefault(d.strftime("%Y-%m"), []).append(d)
    first = True
    for month, ds in by_month.items():
        results, queue, running = {}, list(ds), []
        t0 = time.time()
        while queue or running:
            while queue and len(running) < a.parallel:
                d = queue.pop(0)
                p, run = launch(d)
                running.append((d, p, run))
            time.sleep(5)
            for item in list(running):
                d, p, run = item
                if p.poll() is not None:
                    results[d.isoformat()] = day_result(run)
                    running.remove(item)
        closed, nbad = month_report(month, results)
        print(f"{month}: أيّام {len(ds)} · صفقات {closed} · معطوبة {nbad} · {time.time() - t0:.0f}ث", flush=True)
        if first and not a.smoke and (closed == 0 or nbad > len(ds) / 4):
            (REP / "STOPPED.md").write_text(
                f"# توقّف بعد الشهر الأوّل {month}\n\nصفقات {closed} · أيّام معطوبة {nbad} من {len(ds)} — "
                "حارس الفراغ أوقف التشغيل كي لا يجري أيّامًا ويخرج فارغًا. التفاصيل في تقرير الشهر.\n", encoding="utf-8")
            print("توقّف: حارس الفراغ", flush=True)
            return
        first = False


if __name__ == "__main__":
    main()
