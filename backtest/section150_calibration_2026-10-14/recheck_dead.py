# -*- coding: utf-8 -*-
"""إعادة فحص الإعدادات «الميّتة» بالحقائق النصّيّة أيضًا (١٠-١٤، بعد سؤال المالك عن ذرّة الشموع).

الفحص السريع الأوّل قارن الأرقام وحدها، فحكم على عتبات ذرّة الشموع بالموت وهي تغيّر اسم النمط (حقيقةٌ منشورة تقرؤها استراتيجيّة
المدى). هنا: كلّ إعدادٍ حُكم بموته يُعاد بأصغر قيمةٍ وأكبرها على آخر 60 ألف دقيقة، والبصمة تشمل الأرقام والنصوص، أربعةٌ معًا.
الناتج: «فحص الإعدادات الميّتة بالنصوص.md» — لكلّ إعداد: ميّتٌ فعلًا، أو أيّ حقيقةٍ يغيّرها.
"""
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PYW = pathlib.Path(sys.executable).with_name("pythonw.exe")
PAR = 4
FLAGS = 0x00004000 | 0x08000000
DEST = "quick_txt"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(HERE / "recheck_dead.log", "a", encoding="utf-8")


def fmt(v):
    return str(v) if isinstance(v, int) else ("%g" % v)


def path(j):
    return HERE / DEST / ("%s__%s__%s.json" % j)


def main():
    plan = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))
    jobs, dead = [], {}
    for a, params in plan["plan"].items():
        ks = [k for k, p in params.items() if not p["alive"]]
        if not ks:
            continue
        dead[a] = ks
        jobs.append((a, "live", "x"))
        for k in ks:
            g = params[k]["grid"]
            jobs += [(a, k, fmt(x)) for x in sorted({g[0], g[-1]})]
    todo = [j for j in jobs if not path(j).exists()]
    procs = {}
    while todo or procs:
        while todo and len(procs) < PAR:
            j = todo.pop(0)
            procs[j] = subprocess.Popen([str(PYW), str(HERE / "calib150.py"), "--atom", j[0], "--param", j[1], "--value", j[2],
                                         "--quick", "--dest", DEST], cwd=str(HERE), creationflags=FLAGS)
        for j, p in list(procs.items()):
            if p.poll() is not None:
                del procs[j]
        time.sleep(5)
    L = ["# فحص الإعدادات «الميّتة» بالحقائق النصّيّة أيضًا — %s" % time.strftime("%Y-%m-%d %H:%M"), "",
         "كلّ إعدادٍ حُكم بموته (لا يغيّر رقمًا) أُعيد بأصغر قيمةٍ وأكبرها، والمقارنة الآن على الأرقام **والنصوص** (اسم النمط · الحالة · الحدث).", ""]
    for a, ks in dead.items():
        L += ["## %s" % plan["names"].get(a, a), ""]
        lp = path((a, "live", "x"))
        base = json.loads(lp.read_text(encoding="utf-8"))["digest"] if lp.exists() else {}
        if not base:
            L += ["لا تنشر من الشموع شيئًا (لا أرقام ولا نصوص) ⟸ إعداداتها لا تُقاس هنا.", ""]
            continue
        for k in ks:
            changed = set()
            for x in sorted({plan["plan"][a][k]["grid"][0], plan["plan"][a][k]["grid"][-1]}):
                p = path((a, k, fmt(x)))
                if not p.exists():
                    continue
                dg = json.loads(p.read_text(encoding="utf-8"))["digest"]
                changed |= {key.split("|")[-1] for key in set(base) | set(dg) if base.get(key) != dg.get(key)}
            live_v = fmt(plan["plan"][a][k]["live"])
            L.append("- %s = %s: %s" % (k, live_v, ("**حيّ — يغيّر: %s**" % " · ".join(sorted(changed))) if changed else "ميّتٌ فعلًا"))
        L.append("")
    (HERE / "فحص الإعدادات الميّتة بالنصوص.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(time.strftime("%m-%d %H:%M"), "انتهى", flush=True)


if __name__ == "__main__":
    main()
