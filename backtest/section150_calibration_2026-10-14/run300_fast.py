# -*- coding: utf-8 -*-
"""(النسخة السريعة ١٠-١٤ 16:35 — التداول مطفأ والذاكرة واسعة: أحد عشر معًا بدل ثمانية، والتشغيلات الجارية من المشغّل السابق
تُعدّ ولا تُكرَّر.) معايرة قسم الإحصاء (أمر المالك ١٠-١٤ «القسم التالي» بعد البنية؛ قسم السيولة لا إعداد فيه يُعاير على التاريخ).

الذرّات: 301 المتوسّط · 302 الوسيط · 303 المنوال · 304 الانحراف · 305 التباين · 306 معامل الاختلاف · 308 الانحدار · 309 معامل التحديد ·
310 درجة Z · 311 الالتواء · 312 التفلطح · 313 الشذوذ · 314 التوزيع · 315 المدى · 318 مقارنة الفترات. خارجها: 307 (رموز أخرى) · 316 (تِكّ).
معلن: بلا إطار الدقيقة (سبعٌ منها تجمع آلاف القيم لكلّ شمعة؛ والنافذة الواحدة تُختار للإطارات كلّها)، وشبكة النوافذ أخشن:
5 10 20 30 50 100 200 300 500 1000 2000 3200 6000 (والحيّ). والعتبات ×0.25…×3.
١) فحصٌ سريع (أرقامٌ ونصوص) يكشف الميّت · ٢) الشبكة الكاملة للحيّ منها، ثمانيةٌ معًا مع حارسي الذاكرة · ٣) الحكم ⟵ «تقرير معايرة قسم الإحصاء.md».
"""
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PYW = pathlib.Path(sys.executable).with_name("pythonw.exe")
PY = pathlib.Path(sys.executable).with_name("python.exe")
PAR = 11
MIN_FREE_MB = 3000
EMERGENCY_MB = 1500
FLAGS = 0x08000000
ATOMS = ("309", "318", "302", "313", "304", "305", "306", "310", "301", "311", "314", "312", "303", "308", "315")   # الأثقل أوّلًا
WIN_GRID = (5, 10, 20, 30, 50, 100, 200, 300, 500, 1000, 2000, 3200, 6000)
FMULTS = (0.25, 0.5, 0.75, 1.5, 2.0, 3.0)
WINDOW_WORDS = ("window", "period", "lookback", "fast", "slow", "bars", "short", "long")
QDEST, FDEST = "quick300", "out300"
STATUS = HERE / "حال معايرة الإحصاء.md"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "run300.log", "a", encoding="utf-8")


def free_mb():
    import ctypes

    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1048576


def fmt(v):
    return str(v) if isinstance(v, int) else ("%g" % v)


def params(cfg):
    out = []
    for k, v in cfg.items():
        if k == "min_candles" or isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        if isinstance(v, int) and any(w in k for w in WINDOW_WORDS):
            g = WIN_GRID
        elif isinstance(v, int):
            g = tuple(sorted({max(1, int(round(v * m))) for m in FMULTS}))
        elif v == 0:
            g = (-0.001, 0.001)                         # عتبةٌ صفريّة: إلى جانبيها
        else:
            g = tuple(round(v * m, 6) for m in FMULTS)
        out.append((k, v, [x for x in sorted(set(g)) if x != v]))
    return out


def catalog():
    import yaml
    root = pathlib.Path(r"C:\Users\NQ\QUANT_NQ\atoms\قسم 300-349")
    cat = {}
    for d in sorted(root.iterdir()):
        m = d / "manifest.yaml"
        if m.exists() and d.name[:3] in ATOMS:
            cat[d.name[:3]] = (d.name, dict((yaml.safe_load(m.read_text(encoding="utf-8")) or {}).get("config") or {}))
    return {a: cat[a] for a in ATOMS if a in cat}


PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def running_jobs(dest):
    """التشغيلات الجارية لهذا المجلّد (من أيّ مشغّل) — من سطور أوامرها."""
    r = subprocess.run([PS, "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
                        "Where-Object { $_.CommandLine -match 'calib150' } | ForEach-Object { $_.CommandLine }"],
                       capture_output=True, text=True, encoding="utf-8", creationflags=0x08000000)
    out = set()
    for line in r.stdout.splitlines():
        parts = line.split()
        if "--dest" in parts and parts[parts.index("--dest") + 1] == dest and "--atom" in parts:
            out.add((parts[parts.index("--atom") + 1], parts[parts.index("--param") + 1], parts[parts.index("--value") + 1]))
    return out


def path(job, dest):
    return HERE / dest / ("%s__%s__%s.json" % job)


def pool(jobs, quick, stage):
    dest = QDEST if quick else FDEST
    todo = [j for j in jobs if not path(j, dest).exists()]
    procs, par = {}, PAR
    while todo or procs or running_jobs(dest):
        if procs and free_mb() < EMERGENCY_MB:            # حارس الطوارئ: الأحدث يُوقف ويعود، ويقلّ العدد
            j = list(procs)[-1]
            procs.pop(j).kill()
            todo.insert(0, j)
            par = max(2, len(procs))
            print(time.strftime("%m-%d %H:%M"), "طوارئ ذاكرة: أُوقف", j, "والعدد", par, flush=True)
        others = running_jobs(dest) - set(procs)
        todo = [j for j in todo if j not in others and not path(j, dest).exists()]
        while todo and len(procs) + len(others) < par and free_mb() > MIN_FREE_MB:
            j = todo.pop(0)
            args = [str(PYW), str(HERE / "calib150.py"), "--atom", j[0], "--param", j[1], "--value", j[2], "--no1m",
                    "--dest", dest] + (["--quick"] if quick else [])
            procs[j] = subprocess.Popen(args, cwd=str(HERE), creationflags=FLAGS)
        for j, p in list(procs.items()):
            if p.poll() is not None:
                del procs[j]
                if not path(j, dest).exists():
                    print(time.strftime("%m-%d %H:%M"), "فشل", j, p.returncode, flush=True)
        STATUS.write_text("# حال معايرة قسم الإحصاء — %s\n\nالمرحلة: **%s** · انتهى %d من %d · ذاكرة حرّة %d ميغا\n\n%s\n" % (
            time.strftime("%Y-%m-%d %H:%M"), stage, sum(path(j, dest).exists() for j in jobs), len(jobs), free_mb(),
            "\n".join("- يعمل: %s · %s = %s" % j for j in procs)), encoding="utf-8")
        time.sleep(10 if quick else 30)


def main():
    print(time.strftime("%m-%d %H:%M"), "بدء", flush=True)
    cat = catalog()
    quick = []
    for a, (_, cfg) in cat.items():
        quick.append((a, "live", "x"))
        for k, v, g in params(cfg):
            quick += [(a, k, fmt(x)) for x in sorted({g[0], g[-1]})]
    pool(quick, True, "الفحص السريع (أرقامٌ ونصوص)")
    plan, full = {}, []
    for a, (_, cfg) in cat.items():
        base = json.loads(path((a, "live", "x"), QDEST).read_text(encoding="utf-8"))["digest"]
        plan[a] = {}
        for k, v, g in params(cfg):
            changed = set()
            for x in sorted({g[0], g[-1]}):
                p = path((a, k, fmt(x)), QDEST)
                if p.exists():
                    dg = json.loads(p.read_text(encoding="utf-8"))["digest"]
                    changed |= {key.split("|")[-1] for key in set(base) | set(dg) if base.get(key) != dg.get(key)}
            plan[a][k] = {"live": v, "grid": g, "alive": bool(changed and base), "changes": sorted(changed)}
        if any(p["alive"] for p in plan[a].values()):
            full.append((a, "live", "x"))
            for k, p in plan[a].items():
                if p["alive"]:
                    full += [(a, k, fmt(x)) for x in p["grid"]]
    (HERE / "plan300.json").write_text(json.dumps({"plan": plan, "names": {a: n for a, (n, _) in cat.items()}},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    pool(full, False, "الشبكة الكاملة على تاريخ الناسداك")
    subprocess.run([str(PY), str(HERE / "judge300.py")], cwd=str(HERE), creationflags=0x08000000)
    STATUS.write_text("# حال معايرة قسم الإحصاء — %s\n\n**انتهت.** التقرير: «تقرير معايرة قسم الإحصاء.md»\n" % time.strftime("%Y-%m-%d %H:%M"),
                      encoding="utf-8")
    print(time.strftime("%m-%d %H:%M"), "انتهت", flush=True)


if __name__ == "__main__":
    main()
