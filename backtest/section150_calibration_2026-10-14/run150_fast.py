# -*- coding: utf-8 -*-
"""(النسخة السريعة ١٠-١٤ 01:03 — المالك: «طفيت تداول سرعها»: اثنا عشر معًا بأولويّةٍ عاديّة، وتنتظر أوّلًا انتهاء تشغيلات المشغّل
السابق فلا تكرّرها.) مشغّل معايرة قسم التحليل — يعمل وحده حتّى التقرير (أمر المالك ١٠-١٤: «خود باقي زرات قسم تحليل وعملهم نفس اختبار لا كلهم»).

١) فحصٌ سريع لكلّ إعداد (آخر 60 ألف دقيقة، بأصغر قيمةٍ وأكبرها): هل يغيّر أيّ رقمٍ تنشره الذرّة؟ إعدادٌ لا يغيّر شيئًا (يصنع حكمًا
   ينزعه عقد الحقائق) يُعلَن «ميّتًا» ولا يُشغَّل كاملًا.
٢) التشغيل الكامل لكلّ قيمةٍ من شبكة كلّ إعدادٍ حيّ (الأثقل أوّلًا)، تسعةٌ معًا بأولويّةٍ منخفضة؛ ما انتهى لا يُعاد.
٣) الحكم ⟵ «تقرير معايرة قسم التحليل.md». الحال كلّ دقيقة في «حال المعايرة.md».
خارج الاختبار (معلن في التقرير): 160 الارتباط و161 القوّة النسبيّة (تحتاجان رموزًا غير الناسداك) · 158 الجلسات و159 أثر الوقت
(لا إعداد رقميّ) · 152 الزخم (عويرت قبلها).
"""
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PYW = pathlib.Path(sys.executable).with_name("pythonw.exe")
PY = pathlib.Path(sys.executable).with_name("python.exe")
PAR = 12
FLAGS = 0x08000000                      # أولويّة عاديّة (التداول مطفأ) · بلا نافذة
ATOMS = ("153", "165", "151", "162", "163", "157", "156", "155")        # الأثقل أوّلًا
WIN_GRID = (5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200, 250, 300, 400, 500, 600, 800, 1000)
BIG = (1600, 2000, 3200)
SMALL = (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30)
FMULTS = (0.25, 0.5, 0.75, 1.5, 2.0, 3.0)
WINDOW_WORDS = ("window", "period", "lookback", "fast", "slow", "bars", "short", "long")
STATUS = HERE / "حال المعايرة.md"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "run150.log", "a", encoding="utf-8")
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def others_running():
    """تشغيلات أداة المعايرة الجارية من المشغّل السابق."""
    r = subprocess.run([PS, "-NoProfile", "-Command", "@(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
                        "Where-Object { $_.CommandLine -match 'calib150' }).Count"], capture_output=True, text=True,
                       creationflags=0x08000000)
    try:
        return int(r.stdout.strip() or 0)
    except ValueError:
        return 0


def fmt(v):
    return str(v) if isinstance(v, int) else ("%g" % v)


def params(cfg):
    """(الإعداد · الحيّ · الشبكة بلا الحيّ) لكلّ إعدادٍ رقميّ عدا الإحماء."""
    out = []
    for k, v in cfg.items():
        if k == "min_candles" or isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        if isinstance(v, int) and any(w in k for w in WINDOW_WORDS):
            g = SMALL if v <= 5 else WIN_GRID + (BIG if v > 1000 else ())
        elif isinstance(v, int):
            g = tuple(sorted({max(1, int(round(v * m))) for m in FMULTS}))
        else:
            g = tuple(round(v * m, 6) for m in FMULTS)
        out.append((k, v, [x for x in sorted(set(g)) if x != v]))
    return out


def catalog():
    import yaml
    root = pathlib.Path(r"C:\Users\NQ\QUANT_NQ\atoms\قسم 150-199")
    cat = {}
    for d in sorted(root.iterdir()):
        m = d / "manifest.yaml"
        if m.exists() and d.name[:3] in ATOMS:
            cat[d.name[:3]] = (d.name, dict((yaml.safe_load(m.read_text(encoding="utf-8")) or {}).get("config") or {}))
    return cat


def path(job, quick=False):
    return HERE / ("quick" if quick else "out") / ("%s__%s__%s.json" % job)


def pool(jobs, quick, stage):
    todo = [j for j in jobs if not path(j, quick).exists()]
    procs = {}
    while todo or procs:
        while todo and len(procs) < PAR:
            j = todo.pop(0)
            args = [str(PYW), str(HERE / "calib150.py"), "--atom", j[0], "--param", j[1], "--value", j[2]] + (["--quick"] if quick else [])
            procs[j] = subprocess.Popen(args, cwd=str(HERE), creationflags=FLAGS)
        for j, p in list(procs.items()):
            if p.poll() is not None:
                del procs[j]
                if not path(j, quick).exists():
                    print(time.strftime("%m-%d %H:%M"), "فشل", j, p.returncode, flush=True)
        done = sum(path(j, quick).exists() for j in jobs)
        STATUS.write_text("# حال معايرة قسم التحليل — %s\n\nالمرحلة: **%s** · انتهى %d من %d\n\n%s\n" % (
            time.strftime("%Y-%m-%d %H:%M"), stage, done, len(jobs), "\n".join("- يعمل: %s · %s = %s" % j for j in procs)),
            encoding="utf-8")
        time.sleep(15 if quick else 60)


def main():
    print(time.strftime("%m-%d %H:%M"), "بدء السريعة", flush=True)
    while others_running():
        time.sleep(10)
    cat = catalog()
    quick = []
    for a, (_, cfg) in cat.items():
        quick.append((a, "live", "x"))
        for k, v, g in params(cfg):
            for x in {g[0], g[-1]}:
                quick.append((a, k, fmt(x)))
    pool(quick, True, "الفحص السريع: أيّ إعدادٍ يغيّر رقمًا منشورًا")
    alive, plan = {}, {}
    for a, (_, cfg) in cat.items():
        base = json.loads(path((a, "live", "x"), True).read_text(encoding="utf-8"))["digest"]
        alive[a] = []
        for k, v, g in params(cfg):
            changed = any(json.loads(path((a, k, fmt(x)), True).read_text(encoding="utf-8"))["digest"] != base
                          for x in {g[0], g[-1]} if path((a, k, fmt(x)), True).exists())
            plan.setdefault(a, {})[k] = {"live": v, "grid": g, "alive": bool(changed and base)}
            if changed and base:
                alive[a].append(k)
    (HERE / "plan.json").write_text(json.dumps({"plan": plan, "names": {a: n for a, (n, _) in cat.items()}},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    full = []
    for a, (_, cfg) in cat.items():
        if alive[a]:
            full.append((a, "live", "x"))
            for k, v, g in params(cfg):
                if k in alive[a]:
                    full += [(a, k, fmt(x)) for x in g]
    pool(full, False, "التشغيل الكامل على تاريخ الناسداك")
    subprocess.run([str(PY), str(HERE / "judge150.py")], cwd=str(HERE), creationflags=0x08000000)
    STATUS.write_text("# حال معايرة قسم التحليل — %s\n\n**انتهت.** التقرير: «تقرير معايرة قسم التحليل.md»\n" % time.strftime("%Y-%m-%d %H:%M"),
                      encoding="utf-8")
    print(time.strftime("%m-%d %H:%M"), "انتهت", flush=True)


if __name__ == "__main__":
    main()
