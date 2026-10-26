# -*- coding: utf-8 -*-
"""مشغّل معايرة المنظومة على الجهاز — يعمل وحده حتّى التقرير (ختم المالك «Nq» ٢٠٢٦-١٠-١٣).

33 تشغيلًا (الحيّ ومعه العتبات · ثمانِ ذرّات نوافذ × أربعة أضعاف)، عشرةٌ معًا بأولويّةٍ منخفضة؛ ثمّ اختيار البناء؛ ثمّ
تشغيل العيار المجمَّع؛ ثمّ الحكم والتقرير. ما انتهى لا يُعاد (يُستأنف بعد أيّ انقطاع). الحال كلّ دقيقة في «حال المعايرة.md».
"""
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PYW = pathlib.Path(sys.executable).with_name("pythonw.exe")
PAR = 10
FLAGS = 0x00004000 | 0x08000000          # أولويّة منخفضة · بلا نافذة
RUNS = ["live"] + ["%s:all×%s" % (a, m) for a in ("165", "310", "151", "152", "163", "201", "315", "358")
                   for m in ("0.25", "0.5", "2", "4")]
STATUS = HERE / "حال المعايرة.md"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "run_all.log", "a", encoding="utf-8")


def done(run):
    return (HERE / "out" / (run.replace(":", "_") + ".csv")).exists()


def progress(run):
    p = HERE / "work" / run.replace(":", "_") / "progress.txt"
    return p.read_text(encoding="utf-8") if p.exists() else "—"


def write_status(stage, running):
    L = ["# حال معايرة المنظومة — %s" % time.strftime("%Y-%m-%d %H:%M"), "", "المرحلة: **%s**" % stage, "",
         "انتهى %d من %d تشغيلًا." % (sum(done(r) for r in RUNS), len(RUNS)), ""]
    for r in running:
        L.append("- يعمل: %s ⟵ وصل %s" % (r, progress(r)))
    STATUS.write_text("\n".join(L) + "\n", encoding="utf-8")


def run_many(runs, stage):
    todo = [r for r in runs if not done(r)]
    procs = {}
    while todo or procs:
        while todo and len(procs) < PAR:
            r = todo.pop(0)
            procs[r] = subprocess.Popen([str(PYW), str(HERE / "calib_system.py"), "--run", r], cwd=str(HERE),
                                        creationflags=FLAGS)
        for r, p in list(procs.items()):
            if p.poll() is not None:
                del procs[r]
                if not done(r):
                    print(time.strftime("%m-%d %H:%M"), "فشل", r, "الرمز", p.returncode, flush=True)
        write_status(stage, list(procs))
        time.sleep(60)


def main():
    print(time.strftime("%m-%d %H:%M"), "بدء", flush=True)
    run_many(RUNS, "التشغيلات الثلاثة والثلاثون")
    py = str(pathlib.Path(sys.executable).with_name("python.exe"))
    subprocess.run([py, str(HERE / "judge.py"), "build"], cwd=str(HERE), creationflags=0x08000000)
    best = json.loads((HERE / "best.json").read_text(encoding="utf-8"))
    if best["atoms"] or best["thresholds"]:
        run_many(["best"], "تشغيل العيار المجمَّع على المدى كلّه")
    subprocess.run([py, str(HERE / "judge.py"), "final"], cwd=str(HERE), creationflags=0x08000000)
    STATUS.write_text("# حال معايرة المنظومة — %s\n\n**انتهت.** التقرير: «تقرير معايرة المنظومة.md» · الاختيار: «اختيار البناء.md»\n"
                      % time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
    print(time.strftime("%m-%d %H:%M"), "انتهت", flush=True)


if __name__ == "__main__":
    main()
