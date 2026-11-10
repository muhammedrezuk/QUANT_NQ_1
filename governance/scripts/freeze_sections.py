#!/usr/bin/env python3
"""مفاتيح تجميد الأقسام التي لا أداة ختمٍ لها — توليد وتحقّق.

بأمر المالك ٢٠٢٦-١٠-٢٧ (ختم «إن كيو»): «اختم الأقسام الثمانية عشر كلّها على
حالها اليوم … وابنِ ختمًا لما لا ختم له بالطريقة نفسها».

    python governance/scripts/freeze_sections.py --seal            # توليد مفاتيح كلّ قسمٍ هنا
    python governance/scripts/freeze_sections.py                   # تحقّق
    python governance/scripts/freeze_sections.py 000-049 [--seal]  # قسمٌ واحدٌ أو أكثر

الخوارزمية نفسها المستعملة في ختم قسم 600-649 حرفًا بحرف، وصيغة ملفّ المفاتيح
نفسها — بصمة SHA-256 لكلّ ملفٍّ في القسم، وفوقها بصمة جذرٍ واحدة. تعديل حرفٍ
واحد يكسر بصمة ملفّه وبصمة الجذر معًا، فيظهر الملفّ باسمه.

والقسم الذي له أداته `freeze_<القسم>.py` في هذا المجلّد لا يُختم هنا، كي لا
تكتب أداتان ملفّ مفاتيحٍ واحدًا.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ATOMS = ROOT / "atoms"
HERE = Path(__file__).resolve().parent
KEYS_DIR = ROOT / "ورق" / "١٢_الأوامر_والأختام" / "أختام التجميد" / "أختام"
SKIP = {"__pycache__", ".pytest_cache"}
AUTHORITY = "أمر المالك المباشر ٢٠٢٦-١٠-٢٧ (ختم «إن كيو»)"


def dedicated(span: str) -> Path:
    return HERE / f"freeze_{span.replace('-', '_')}.py"


def all_sections() -> list[str]:
    return [found.group(1) for folder in sorted(ATOMS.iterdir())
            if folder.is_dir()
            and (found := re.fullmatch(r"قسم (\d{3}-\d{3})", folder.name))]


def sections() -> list[str]:
    return [span for span in all_sections() if not dedicated(span).is_file()]


def keys_path(span: str) -> Path:
    return KEYS_DIR / f"تجميد_قسم_{span}.json"


def files(section: Path) -> list[Path]:
    out = [p for p in section.rglob("*")
           if p.is_file() and not any(part in SKIP for part in p.parts)
           and not p.name.endswith(".pyc.tmp")]
    return sorted(out, key=lambda p: p.relative_to(section).as_posix())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(span: str) -> dict:
    section = ATOMS / f"قسم {span}"
    entries = {p.relative_to(section).as_posix(): digest(p) for p in files(section)}
    root = hashlib.sha256(
        "\n".join(f"{k}:{v}" for k, v in entries.items()).encode("utf-8")
    ).hexdigest()
    atoms = sorted(d.name for d in section.iterdir()
                   if d.is_dir() and (d / "manifest.yaml").exists())
    return {"section": f"قسم {span}", "frozen": True,
            "authority": AUTHORITY,
            "atom_count": len(atoms), "file_count": len(entries),
            "atoms": atoms, "root": root, "files": entries}


def seal(span: str) -> int:
    data = build(span)
    path = keys_path(span)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print(f"🔒 خُتم قسم {span} — {data['atom_count']} ذرّة · {data['file_count']} ملفًّا")
    print(f"   الجذر : {data['root']}")
    print(f"   المفاتيح: {path.relative_to(ROOT)}")
    return 0


def sealed_in_git(path: Path) -> bool:
    """هل يعرف المستودعُ هذا المفتاح؟ — يفصل «لم يُختم بعد» عن «زال الختم» (نظير 700-749)."""
    import subprocess
    try:
        done = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT))],
            cwd=str(ROOT), capture_output=True, text=True, timeout=20)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def verify(span: str) -> int:
    path = keys_path(span)
    if not path.is_file():
        # الحارس المنزوع أخطر من المكسور: المكسور يصرخ والمنزوع يسكت (حادثة ٢٠٢٦-٠٩-١٩).
        if sealed_in_git(path):
            print(f"🚨 قسم {span}: الختم زال من الشجرة — والمستودع يعرفه.")
            print("   استرجعه ثمّ تحقّق — ولا تختم من جديد قبل التحقّق:")
            print(f"      git checkout -- \"{path.relative_to(ROOT).as_posix()}\"")
            return 1
        print(f"❌ قسم {span}: لا مفاتيح ولا يعرفها المستودع — لم يُختم بعد. شغّل --seal")
        return 2
    saved = json.loads(path.read_text(encoding="utf-8"))
    now = build(span)

    changed = [k for k, v in now["files"].items()
               if k in saved["files"] and saved["files"][k] != v]
    added = [k for k in now["files"] if k not in saved["files"]]
    removed = [k for k in saved["files"] if k not in now["files"]]

    if now["root"] == saved["root"]:
        print(f"🔒 قسم {span} مجمّد وسليم — {saved['atom_count']} ذرّة · "
              f"{saved['file_count']} ملفًّا · الجذر {saved['root'][:16]}")
        return 0

    print(f"❌ قسم {span}: الختم مكسور — القسم مجمّد ولا يُمسّ.")
    print(f"   الجذر المختوم: {saved['root']}")
    print(f"   الجذر الحالي : {now['root']}")
    for label, items in (("تُغيّرت", changed), ("أُضيفت", added),
                         ("حُذفت", removed)):
        for item in items:
            print(f"   {label}: {item}")
    return 1


def orphans() -> int:
    """ملفّ مفاتيحٍ لا قسم له لا يُتحقَّق منه أبدًا — فيُسمّى."""
    present = set(all_sections())
    found = 0
    for path in sorted(KEYS_DIR.glob("تجميد_قسم_*.json")):
        span = path.stem.removeprefix("تجميد_قسم_")
        if span not in present:
            print(f"⚠️ مفاتيح بلا قسم: {path.relative_to(ROOT)}")
            found = 1
    return found


def main(argv: list[str]) -> int:
    spans = [a for a in argv if not a.startswith("--")]
    known = sections()
    for span in spans:
        if dedicated(span).is_file():
            print(f"❌ قسم {span} له أداته: {dedicated(span).relative_to(ROOT).as_posix()}")
            return 2
        if span not in known:
            print(f"❌ لا قسم باسم {span} — الأقسام هنا: {' · '.join(known)}")
            return 2
    action = seal if "--seal" in argv else verify
    codes = [action(span) for span in (spans or known)]
    if not spans and action is verify:
        codes.append(orphans())
    # الكسر يُقال أوّلًا: قسمٌ مكسور (1) لا يخفيه قسمٌ لم يُختم بعد (2).
    return 1 if 1 in codes else max(codes, default=0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
