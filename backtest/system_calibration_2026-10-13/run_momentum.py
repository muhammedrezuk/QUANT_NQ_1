# -*- coding: utf-8 -*-
"""مشغّل معايرة الزخم وحده — بجانب مشغّل المنظومة لا بدلًا منه (أمر المالك ١٠-١٤ فجرًا: «هات زخم بس نعاير اعداداته بشكل منفصل»).

سبعة تشغيلاتٍ مقصورة على 404 و408 وذرّاتهما: نافذة صافي الحركة في 152 = 25 (الحيّ) · 6 · 12 · 18 · 37 · 50 · 100؛ أربعةٌ معًا
بأولويّةٍ منخفضة (مشغّل المنظومة يشغّل عشرة). ثمّ الحكم (judge.py momentum) ⟵ «تقرير معايرة الزخم.md». ما انتهى لا يُعاد.
"""
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PYW = pathlib.Path(sys.executable).with_name("pythonw.exe")
PY = pathlib.Path(sys.executable).with_name("python.exe")
PAR = 4
FLAGS = 0x00004000 | 0x08000000          # أولويّة منخفضة · بلا نافذة
RUNS = ["152:roc_period=%d" % v for v in (25, 6, 12, 18, 37, 50, 100)]
STATUS = HERE / "حال معايرة الزخم.md"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "run_momentum.log", "a", encoding="utf-8")


def done(run):
    return (HERE / "out" / (run.replace(":", "_") + ".csv")).exists()


def progress(run):
    p = HERE / "work" / run.replace(":", "_") / "progress.txt"
    return p.read_text(encoding="utf-8") if p.exists() else "—"


def main():
    print(time.strftime("%m-%d %H:%M"), "بدء", flush=True)
    todo = [r for r in RUNS if not done(r)]
    procs, failed = {}, []
    while todo or procs:
        while todo and len(procs) < PAR:
            r = todo.pop(0)
            procs[r] = subprocess.Popen([str(PYW), str(HERE / "calib_system.py"), "--run", r, "--strats", "404,408"],
                                        cwd=str(HERE), creationflags=FLAGS)
        for r, p in list(procs.items()):
            if p.poll() is not None:
                del procs[r]
                if not done(r):
                    failed.append(r)
                    print(time.strftime("%m-%d %H:%M"), "فشل", r, "الرمز", p.returncode, flush=True)
        L = ["# حال معايرة الزخم — %s" % time.strftime("%Y-%m-%d %H:%M"), "",
             "انتهى %d من %d تشغيلات." % (sum(done(r) for r in RUNS), len(RUNS)), ""]
        L += ["- يعمل: %s ⟵ وصل %s" % (r, progress(r)) for r in procs]
        L += ["- فشل: %s" % r for r in failed]
        STATUS.write_text("\n".join(L) + "\n", encoding="utf-8")
        time.sleep(60)
    if all(done(r) for r in RUNS):
        subprocess.run([str(PY), str(HERE / "judge.py"), "momentum"], cwd=str(HERE), creationflags=0x08000000)
        STATUS.write_text("# حال معايرة الزخم — %s\n\n**انتهت.** التقرير: «تقرير معايرة الزخم.md»\n" % time.strftime("%Y-%m-%d %H:%M"),
                          encoding="utf-8")
    print(time.strftime("%m-%d %H:%M"), "انتهت", flush=True)


if __name__ == "__main__":
    main()
