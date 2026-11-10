# -*- coding: utf-8 -*-
"""مشغّل اختبار الأسماء — العتبات التي تغيّر كلمةً منشورة لا رقمًا (ختم المالك «Nq» ١٠-١٤).

الإعدادات من إعادة الفحص بالنصوص: التذبذب (حدّا عالٍ/منخفض) · الشموع (العتبات الأربع لاسم النمط) · السرعة (حدّا سريع/بطيء) ·
التسارع (حدّه) · الضوضاء (حدّ الضوضاء). لكلٍّ الحيّ وستّ قيم (×0.25 … ×3)، بكود الذرّة الحيّ على تاريخ الناسداك كلّه، عشرةٌ معًا،
ولا يبدأ تشغيلٌ إن نقصت الذاكرة الحرّة عن 3000 ميغا. ثمّ الحكم ⟵ «تقرير معايرة الأسماء.md».
"""
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PYW = pathlib.Path(sys.executable).with_name("pythonw.exe")
PY = pathlib.Path(sys.executable).with_name("python.exe")
PAR = 10
MIN_FREE_MB = 3000
FLAGS = 0x08000000
DEST = "out_labels"
PARAMS = {"153": ("high_mult", "low_mult"), "156": ("doji_body_ratio", "marubozu_body_ratio", "pin_wick_ratio", "pin_body_ratio"),
          "162": ("slow_ratio", "fast_ratio"), "163": ("accel_ratio",), "165": ("noisy_max",)}
STATUS = HERE / "حال اختبار الأسماء.md"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "run_labels.log", "a", encoding="utf-8")


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


def path(j):
    return HERE / DEST / ("%s__%s__%s.json" % j)


def main():
    print(time.strftime("%m-%d %H:%M"), "بدء", flush=True)
    plan = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))["plan"]
    jobs = [(a, "live", "x") for a in ("153", "165", "156", "162", "163")]           # الأثقل أوّلًا
    for a in ("153", "165", "156", "162", "163"):
        for k in PARAMS[a]:
            jobs += [(a, k, fmt(x)) for x in plan[a][k]["grid"]]
    todo = [j for j in jobs if not path(j).exists()]
    procs = {}
    while todo or procs:
        while todo and len(procs) < PAR and free_mb() > MIN_FREE_MB:
            j = todo.pop(0)
            procs[j] = subprocess.Popen([str(PYW), str(HERE / "calib150.py"), "--atom", j[0], "--param", j[1], "--value", j[2],
                                         "--dest", DEST], cwd=str(HERE), creationflags=FLAGS)
        for j, p in list(procs.items()):
            if p.poll() is not None:
                del procs[j]
                if not path(j).exists():
                    print(time.strftime("%m-%d %H:%M"), "فشل", j, p.returncode, flush=True)
        STATUS.write_text("# حال اختبار الأسماء — %s\n\nانتهى %d من %d · ذاكرة حرّة %d ميغا\n\n%s\n" % (
            time.strftime("%Y-%m-%d %H:%M"), sum(path(j).exists() for j in jobs), len(jobs), free_mb(),
            "\n".join("- يعمل: %s · %s = %s" % j for j in procs)), encoding="utf-8")
        time.sleep(30)
    subprocess.run([str(PY), str(HERE / "judge_labels.py")], cwd=str(HERE), creationflags=0x08000000)
    STATUS.write_text("# حال اختبار الأسماء — %s\n\n**انتهى.** التقرير: «تقرير معايرة الأسماء.md»\n" % time.strftime("%Y-%m-%d %H:%M"),
                      encoding="utf-8")
    print(time.strftime("%m-%d %H:%M"), "انتهى", flush=True)


if __name__ == "__main__":
    main()
