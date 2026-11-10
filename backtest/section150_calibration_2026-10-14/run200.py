# -*- coding: utf-8 -*-
"""معايرة قسم البنية (أمر المالك ١٠-١٤: «جهز قسم بنية نظبط اعداداته شغله بالكامل»).

في القسم إعدادٌ واحد: عدد الشموع على كلّ جانب لتأكيد القمّة والقاع في 201 (الحيّ 8)؛ والسبع الأخرى (202 الهيكل الخارجيّ · 203 الداخليّ ·
204 الكسر · 205 تغيّر الطابع · 206 التحوّل · 207 حالة الاتّجاه · 208 طور السوق) بلا إعداد وتبني كلّها عليه. فكلّ قيمةٍ تُشغَّل بالسلسلة
كلّها بكودها الحيّ (و151 لأنّ 207 تقرؤه) على تاريخ الناسداك كلّه، وتُقاس حقائق الذرّات الثماني أرقامًا وأسماءً.
القيم: 1 2 3 4 5 6 10 12 15 20 25 30 40 50 60 80 100 مقابل 8. عشرةٌ معًا، ولا تشغيل إن نقصت الذاكرة الحرّة عن 3000 ميغا.
⟵ «تقرير معايرة قسم البنية.md» (judge200.py).
"""
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PYW = pathlib.Path(sys.executable).with_name("pythonw.exe")
PY = pathlib.Path(sys.executable).with_name("python.exe")
PAR = 8                     # كان 10 فامتلأت الذاكرة (١٠-١٤ 12:37) من جداول الأسماء في الأداة لا من الذرّات؛ أُصلحت
MIN_FREE_MB = 3000
EMERGENCY_MB = 1500
FLAGS = 0x08000000
DEST = "out200"
GRID = (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100)
STATUS = HERE / "حال معايرة البنية.md"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "run200.log", "a", encoding="utf-8")


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


def path(j):
    return HERE / DEST / ("%s__%s__%s.json" % j)


def main():
    print(time.strftime("%m-%d %H:%M"), "بدء", flush=True)
    jobs = [("201", "live", "x")] + [("201", "lookback", str(v)) for v in GRID]
    todo = [j for j in jobs if not path(j).exists()]
    procs = {}
    par = PAR
    while todo or procs:
        # حارس الطوارئ (١٠-١٤ 12:37 نزلت الحرّة إلى 73 ميغا): أحدث تشغيلٍ يُوقف ويعود إلى الطابور، ويقلّ العدد معًا.
        if procs and free_mb() < EMERGENCY_MB:
            j = list(procs)[-1]
            procs.pop(j).kill()
            todo.insert(0, j)
            par = max(2, len(procs))
            print(time.strftime("%m-%d %H:%M"), "طوارئ ذاكرة: أُوقف", j, "والعدد", par, flush=True)
        while todo and len(procs) < par and free_mb() > MIN_FREE_MB:
            j = todo.pop(0)
            procs[j] = subprocess.Popen([str(PYW), str(HERE / "calib150.py"), "--atom", j[0], "--param", j[1], "--value", j[2],
                                         "--chain", "--dest", DEST], cwd=str(HERE), creationflags=FLAGS)
        for j, p in list(procs.items()):
            if p.poll() is not None:
                del procs[j]
                if not path(j).exists():
                    print(time.strftime("%m-%d %H:%M"), "فشل", j, p.returncode, flush=True)
        STATUS.write_text("# حال معايرة قسم البنية — %s\n\nانتهى %d من %d · ذاكرة حرّة %d ميغا\n\n%s\n" % (
            time.strftime("%Y-%m-%d %H:%M"), sum(path(j).exists() for j in jobs), len(jobs), free_mb(),
            "\n".join("- يعمل: %s · %s = %s" % j for j in procs)), encoding="utf-8")
        time.sleep(15)
    subprocess.run([str(PY), str(HERE / "judge200.py")], cwd=str(HERE), creationflags=0x08000000)
    STATUS.write_text("# حال معايرة قسم البنية — %s\n\n**انتهت.** التقرير: «تقرير معايرة قسم البنية.md»\n" % time.strftime("%Y-%m-%d %H:%M"),
                      encoding="utf-8")
    print(time.strftime("%m-%d %H:%M"), "انتهت", flush=True)


if __name__ == "__main__":
    main()
