#!/usr/bin/env python3
"""مفاتيح تجميد قسم 700-749 (المخازن) — توليد وتحقّق.

بأمر المالك ٢٠٢٦-٠٩-١٩: القسم مختومٌ ومجمّد، يُمنع لمسه أو تعديل حرف فيه.
هذه الأداة تُثبت التجميد بالقياس لا بالثقة:

    python governance/scripts/freeze_700_749.py --seal   # توليد المفاتيح
    python governance/scripts/freeze_700_749.py          # تحقّق

كل ملفّ يحمل بصمة SHA-256 مستقلّة، وفوقها بصمة جذر واحدة للقسم كلّه.
تعديل حرف واحد يكسر بصمة ملفّه وبصمة الجذر معًا، فيظهر الملفّ باسمه.

⚠️ **والبصمة لا تعرف الحياة.** ملفٌّ مختومٌ سليم قد يكون حيًّا بإصدارٍ آخر:
أقسام `cold_process` (‎700-749‎ و‎800-949‎) **لا تُحمَّل ساخنةً** — مقيس
٢٠٢٦-٠٩-١٩: شوكة العمليّة بدأت ‎14:02:01‎ وحُفظ ‎707/atom.py‎ ‎14:36:22‎ وبقي
الحيُّ على الإصدار القديم ٩٣ دقيقة. فالختم يُؤخذ **بعد** إقلاعٍ يُثبت أنّ
المحفوظ هو العامل، ويُسجَّل معه الإصدار الحيّ لكلّ ذرّة من لقطتها.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTION = ROOT / "atoms" / "قسم 700-749"
# ٢٠٢٦-٠٩-٢٤ (ختم Nq صلح): نقل المالك الورقَ كلّه إلى `ورق/` ٢٢:٥٦ فذهب
# `ورق/أختام/` إلى السلّة — والمكان الواحد للأختام قسم ١٢ من الورق.
KEYS = ROOT / "ورق" / "١٢_الأوامر_والأختام" / "أختام التجميد" / "أختام" / "تجميد_قسم_700-749.json"
SNAPSHOTS = ROOT / "forex_runtime" / "var" / "forex" / "snapshots"
SKIP = {"__pycache__", ".pytest_cache"}


def files() -> list[Path]:
    out = [p for p in SECTION.rglob("*")
           if p.is_file() and not any(part in SKIP for part in p.parts)
           # ٢٠٢٦-٠٩-٢٣: بقايا بايتكود `*.pyc.tmp` ليست من القسم (نظير ١٥٠-١٩٩).
           and not p.name.endswith(".pyc.tmp")]
    return sorted(out, key=lambda p: p.relative_to(SECTION).as_posix())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def live_versions() -> dict:
    """الإصدار العامل فعلًا لكلّ ذرّة — من لقطتها لا من كودها.

    يُكتب داخل الختم كي لا يُقرأ «مختومٌ سليم» على أنّه «مختومٌ حيّ».

    ⚠️ **وذرّةٌ بلا `snapshot()` لا لقطةَ لها بحكم التصميم** — ٧١٧ و٧١٩ منها.
    فلا تُعدّ غيابَ لقطتهما انحرافًا: أوّل صياغةٍ لهذه الأداة صرخت عليهما
    صرخةً كاذبة، وحارسٌ يكذب مرّةً يُدرَّب على تجاهله في الثانية.
    """
    out: dict[str, str] = {}
    for folder in sorted(SECTION.iterdir()):
        if not folder.is_dir() or not (folder / "manifest.yaml").exists():
            continue
        atom_id = folder.name.split("_")[0]
        source = folder / "atom.py"
        has_snapshot = (source.is_file()
                        and "async def snapshot" in source.read_text(
                            encoding="utf-8", errors="replace"))
        if not has_snapshot:
            out[atom_id] = "بلا لقطة بالتصميم"
            continue
        snap = SNAPSHOTS / ("%s.json" % atom_id)
        if not snap.is_file():
            out[atom_id] = "⛔ لقطةٌ مفقودة"
            continue
        try:
            out[atom_id] = str(json.loads(snap.read_text(encoding="utf-8"))
                               .get("version", "؟"))
        except (OSError, ValueError):
            out[atom_id] = "⛔ لقطة لا تُقرأ"
    return out


#: ما لا يُعدّ انحرافًا في الإصدار — غيابٌ مقصود لا خلل
_EXPECTED_NO_LIVE = ("بلا لقطة بالتصميم",)


def code_versions() -> dict:
    """الإصدار المكتوب في `atom.py` — يُقارَن بالحيّ فيظهر فارقٌ إن وُجد."""
    import re
    out: dict[str, str] = {}
    for folder in sorted(SECTION.iterdir()):
        source = folder / "atom.py"
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'^ATOM_VERSION\s*=\s*"([^"]+)"', text, re.M)
        out[folder.name.split("_")[0]] = match.group(1) if match else "؟"
    return out


def build() -> dict:
    entries = {p.relative_to(SECTION).as_posix(): digest(p) for p in files()}
    root = hashlib.sha256(
        "\n".join(f"{k}:{v}" for k, v in entries.items()).encode("utf-8")
    ).hexdigest()
    atoms = sorted(d.name for d in SECTION.iterdir()
                   if d.is_dir() and (d / "manifest.yaml").exists())
    return {"section": "قسم 700-749", "frozen": True,
            "authority": "أمر المالك المباشر ٢٠٢٦-٠٩-١٩",
            "atom_count": len(atoms), "file_count": len(entries),
            "atoms": atoms, "root": root, "files": entries}


def seal() -> int:
    data = build()
    live = live_versions()
    code = code_versions()
    data["code_versions"] = code
    data["live_versions"] = live
    drift = {a: {"كود": code.get(a), "حيّ": live.get(a)}
             for a in code
             if live.get(a) not in (code.get(a), None) + _EXPECTED_NO_LIVE}
    data["version_drift"] = drift
    KEYS.parent.mkdir(parents=True, exist_ok=True)
    KEYS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print("🔒 خُتم قسم 700-749")
    print(f"   ذرّات : {data['atom_count']}")
    print(f"   ملفّات: {data['file_count']}")
    print(f"   الجذر : {data['root']}")
    print(f"   المفاتيح: {KEYS.relative_to(ROOT)}")
    if drift:
        print("   ⚠️ إصداراتٌ على القرص لا تعمل حيًّا — الختم يسجّلها ولا يخفيها:")
        for atom_id, pair in drift.items():
            print(f"      {atom_id}: كود {pair['كود']} · حيّ {pair['حيّ']}")
    else:
        print("   ✔ كلّ إصدارٍ مختومٍ هو العامل حيًّا")
    return 0


def sealed_in_git() -> bool:
    """هل يعرف المستودعُ هذا المفتاح؟ — يفصل «لم يُختم بعد» عن «زال الختم»."""
    import subprocess
    try:
        done = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(KEYS.relative_to(ROOT))],
            cwd=str(ROOT), capture_output=True, text=True, timeout=20)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def verify() -> int:
    if not KEYS.is_file():
        # ⚠️ **الحارس المنزوعُ أخطرُ من المكسور: المكسور يصرخ والمنزوع يسكت.**
        # مقيس ٢٠٢٦-٠٩-١٩: مُحي مفتاحُ هذا القسم ومفاتيحُ ثلاثة أقسام أخرى من
        # الشجرة بلا التزامٍ يحذفها (`git log --diff-filter=D` فارغ)، وكانت
        # الأداة تردّ «لا مفاتيح — شغّل --seal» فتُقرأ «لم يُختم بعد» — وهي
        # دعوةٌ إلى `--seal` يثبّت حالةً لم تُراجَع ويدفن ما تغيّر. فيُسأل
        # المستودعُ أوّلًا: إن كان يعرف المفتاح فالختم **زال** لا غاب.
        if sealed_in_git():
            print("🚨 الختم زال من الشجرة — والمستودع يعرفه.")
            print("   القسم كان مختومًا ومفتاحه مُحي. هذا فقدُ حارسٍ لا غيابُ ختم.")
            print("   استرجعه ثمّ تحقّق — **ولا تختم من جديد قبل التحقّق**:")
            print(f"      git checkout -- \"{KEYS.relative_to(ROOT).as_posix()}\"")
            print(f"      python {Path(__file__).relative_to(ROOT).as_posix()}")
            return 1
        print("❌ لا مفاتيح ولا يعرفها المستودع — القسم لم يُختم بعد. شغّل --seal")
        return 2
    saved = json.loads(KEYS.read_text(encoding="utf-8"))
    now = build()

    changed = [k for k, v in now["files"].items()
               if k in saved["files"] and saved["files"][k] != v]
    added = [k for k in now["files"] if k not in saved["files"]]
    removed = [k for k in saved["files"] if k not in now["files"]]

    if now["root"] == saved["root"]:
        print("🔒 قسم 700-749 مجمّد وسليم — مطابق للختم.")
        print(f"   {saved['atom_count']} ذرّة · {saved['file_count']} ملفًّا")
        print(f"   الجذر: {saved['root']}")
        # والبصمة لا تعرف الحياة: يُقارَن المختوم بالعامل الآن
        live = live_versions()
        drift = {a: (v, live.get(a))
                 for a, v in (saved.get("code_versions") or {}).items()
                 if live.get(a) not in (v, None) + _EXPECTED_NO_LIVE}
        if drift:
            print("   ⚠️ الملفّات مطابقة لكنّ الحيّ يعمل بإصدارٍ آخر:")
            for atom_id, (sealed_v, live_v) in drift.items():
                print(f"      {atom_id}: مختوم {sealed_v} · حيّ {live_v}")
        return 0

    print("❌ الختم مكسور — القسم مجمّد ولا يُمسّ.")
    print(f"   الجذر المختوم: {saved['root']}")
    print(f"   الجذر الحالي : {now['root']}")
    for label, items in (("تُغيّرت", changed), ("أُضيفت", added),
                         ("حُذفت", removed)):
        for item in items:
            print(f"   {label}: {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(seal() if "--seal" in sys.argv else verify())
