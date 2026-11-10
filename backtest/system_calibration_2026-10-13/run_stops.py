# -*- coding: utf-8 -*-
"""مشغّل قياس طريقة الوقف (١٠-١٦، ختم المالك «قيس nq»): خمس قطعٍ من التاريخ معًا، كلٌّ بتسخين ستّة أشهر وتقييمٍ بلا تداخل،
بأولويّةٍ منخفضة (المنظومة الحيّة تعمل)، ثمّ الحكم ⟵ «تقرير طريقة الوقف.md». ما انتهى لا يُعاد."""
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PYW = pathlib.Path(sys.executable).with_name("pythonw.exe")
PY = pathlib.Path(sys.executable).with_name("python.exe")
FLAGS = 0x00004000 | 0x08000000
CHUNKS = (("c1", "2015-07-01", "2016-01-01", "2018-01-01"), ("c2", "2017-07-01", "2018-01-01", "2020-01-01"),
          ("c3", "2019-07-01", "2020-01-01", "2022-01-01"), ("c4", "2021-07-01", "2022-01-01", "2024-01-01"),
          ("c5", "2023-07-01", "2024-01-01", "2026-10-17"))
STATUS = HERE / "حال قياس الوقف.md"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "run_stops.log", "a", encoding="utf-8")


def done(tag):
    return (HERE / "out" / ("stops_%s.csv" % tag)).exists()


def main():
    procs = {}
    for tag, start, ev, end in CHUNKS:
        if not done(tag):
            procs[tag] = subprocess.Popen([str(PYW), str(HERE / "calib_system.py"), "--run", "stops", "--tag", "stops_" + tag,
                                           "--start", start, "--eval-from", ev, "--end", end], cwd=str(HERE), creationflags=FLAGS)
    while procs:
        for tag, p in list(procs.items()):
            if p.poll() is not None:
                del procs[tag]
        lines = []
        for tag, *_ in CHUNKS:
            pf = HERE / "work" / ("stops_" + tag) / "progress.txt"
            lines.append("- %s: %s" % (tag, "انتهت" if done(tag) else (pf.read_text(encoding="utf-8") if pf.exists() else "—")))
        STATUS.write_text("# حال قياس طريقة الوقف — %s\n\n%s\n" % (time.strftime("%Y-%m-%d %H:%M"), "\n".join(lines)), encoding="utf-8")
        time.sleep(30)
    subprocess.run([str(PY), str(HERE / "judge_stops.py")], cwd=str(HERE), creationflags=0x08000000)
    STATUS.write_text("# حال قياس طريقة الوقف — %s\n\n**انتهى.** التقرير: «تقرير طريقة الوقف.md»\n" % time.strftime("%Y-%m-%d %H:%M"),
                      encoding="utf-8")


if __name__ == "__main__":
    main()
