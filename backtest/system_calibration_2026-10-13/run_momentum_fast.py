# -*- coding: utf-8 -*-
"""مشغّل الزخم السريع (١٠-١٤ 00:08، المالك: «زرة وحدة بدها لا 5 او لا ستة صبح») — يحلّ محلّ run_momentum.py.

التشغيلات السبعة معًا (لا أربعة): ما يعمل منها من المشغّل السابق يُنتظر ولا يُعاد (تقدّمه كُتب في آخر عشر دقائق)، والباقي
يبدأ فورًا. وتشغيلات المنظومة تُخفَّض إلى «الخمول» حتّى ينتهي الزخم فتأخذ ما يفضل من الجهاز، ثمّ تُرجَع إلى المنخفضة. ثمّ الحكم.
"""
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PYW = pathlib.Path(sys.executable).with_name("pythonw.exe")
PY = pathlib.Path(sys.executable).with_name("python.exe")
FLAGS = 0x00004000 | 0x08000000          # أولويّة منخفضة · بلا نافذة
RUNS = ["152:roc_period=%d" % v for v in (25, 6, 12, 18, 37, 50, 100)]
STATUS = HERE / "حال معايرة الزخم.md"
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "run_momentum.log", "a", encoding="utf-8")


def done(run):
    return (HERE / "out" / (run.replace(":", "_") + ".csv")).exists()


def alive(run):
    p = HERE / "work" / run.replace(":", "_") / "progress.txt"
    return not done(run) and p.exists() and time.time() - p.stat().st_mtime < 600


def progress(run):
    p = HERE / "work" / run.replace(":", "_") / "progress.txt"
    return p.read_text(encoding="utf-8") if p.exists() else "—"


def system_priority(cls):
    """تشغيلات المنظومة (لا الزخم) ومشغّلها ⟵ درجة الأولويّة المعطاة."""
    cmd = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { ($_.CommandLine -match "
           "'calib_system|run_all') -and ($_.CommandLine -notmatch 'roc_period') } | ForEach-Object { try { "
           "(Get-Process -Id $_.ProcessId).PriorityClass = '%s' } catch {} }" % cls)
    subprocess.run([PS, "-NoProfile", "-Command", cmd], creationflags=0x08000000)


def main():
    print(time.strftime("%m-%d %H:%M"), "المشغّل السريع بدأ", flush=True)
    procs, failed = {}, []
    while True:
        system_priority("Idle")              # يُعاد كلّ دقيقة: تشغيلات المنظومة الجديدة تُخفَّض أيضًا
        for r in RUNS:
            if r not in procs and r not in failed and not done(r) and not alive(r):
                procs[r] = subprocess.Popen([str(PYW), str(HERE / "calib_system.py"), "--run", r, "--strats", "404,408"],
                                            cwd=str(HERE), creationflags=FLAGS)
        for r, p in list(procs.items()):
            if p.poll() is not None:
                del procs[r]
                if not done(r):
                    failed.append(r)
                    print(time.strftime("%m-%d %H:%M"), "فشل", r, "الرمز", p.returncode, flush=True)
        left = [r for r in RUNS if not done(r) and r not in failed]
        L = ["# حال معايرة الزخم — %s" % time.strftime("%Y-%m-%d %H:%M"), "",
             "انتهى %d من %d تشغيلات (السبعة معًا، والمنظومة مخفَّضة حتّى ينتهي الزخم)." % (sum(done(r) for r in RUNS), len(RUNS)), ""]
        L += ["- يعمل: %s ⟵ وصل %s" % (r, progress(r)) for r in left]
        L += ["- فشل: %s" % r for r in failed]
        STATUS.write_text("\n".join(L) + "\n", encoding="utf-8")
        if not left:
            break
        time.sleep(60)
    system_priority("BelowNormal")
    if all(done(r) for r in RUNS):
        subprocess.run([str(PY), str(HERE / "judge.py"), "momentum"], cwd=str(HERE), creationflags=0x08000000)
        STATUS.write_text("# حال معايرة الزخم — %s\n\n**انتهت.** التقرير: «تقرير معايرة الزخم.md»\n" % time.strftime("%Y-%m-%d %H:%M"),
                          encoding="utf-8")
    print(time.strftime("%m-%d %H:%M"), "انتهت", flush=True)


if __name__ == "__main__":
    main()
