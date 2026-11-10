#!/usr/bin/env python3
"""مفاتيح تجميد قسم 600-649 — توليد وتحقّق.

بأمر المالك ٢٠٢٦-٠٩-٠٧: القسم مجمّد، يُمنع لمسه أو تعديل حرف فيه.
هذه الأداة تُثبت التجميد بالقياس لا بالثقة:

    python3 governance/scripts/freeze_600_649.py --seal      # توليد المفاتيح
    python3 governance/scripts/freeze_600_649.py             # تحقّق

كل ملفّ يحمل بصمة SHA-256 مستقلّة، وفوقها بصمة جذر واحدة للقسم كلّه.
تعديل حرف واحد يكسر بصمة ملفّه وبصمة الجذر معًا، فيظهر الملفّ باسمه.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTION = ROOT / "atoms" / "قسم 600-649"
# ٢٠٢٦-٠٩-٢٤ (ختم Nq صلح): نقل المالك الورقَ كلّه إلى `ورق/` ٢٢:٥٦ فذهب
# `ورق/أختام/` إلى السلّة — والمكان الواحد للأختام قسم ١٢ من الورق.
KEYS = ROOT / "ورق" / "١٢_الأوامر_والأختام" / "أختام التجميد" / "أختام" / "تجميد_قسم_600-649.json"
SKIP = {"__pycache__", ".pytest_cache"}


def files() -> list[Path]:
    out = [p for p in SECTION.rglob("*")
           if p.is_file() and not any(part in SKIP for part in p.parts)
           # ٢٠٢٦-٠٩-٢٣: بقايا بايتكود `*.pyc.tmp` ليست من القسم (نظير ١٥٠-١٩٩).
           and not p.name.endswith(".pyc.tmp")]
    return sorted(out, key=lambda p: p.relative_to(SECTION).as_posix())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    entries = {p.relative_to(SECTION).as_posix(): digest(p) for p in files()}
    root = hashlib.sha256(
        "\n".join(f"{k}:{v}" for k, v in entries.items()).encode("utf-8")
    ).hexdigest()
    atoms = sorted(d.name for d in SECTION.iterdir()
                   if d.is_dir() and (d / "manifest.yaml").exists())
    return {"section": "قسم 600-649", "frozen": True,
            "authority": "أمر المالك المباشر ٢٠٢٦-٠٩-٠٧",
            "atom_count": len(atoms), "file_count": len(entries),
            "atoms": atoms, "root": root, "files": entries}


def seal() -> int:
    data = build()
    KEYS.parent.mkdir(parents=True, exist_ok=True)
    KEYS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print(f"🔒 خُتم قسم 600-649")
    print(f"   ذرّات : {data['atom_count']}")
    print(f"   ملفّات: {data['file_count']}")
    print(f"   الجذر : {data['root']}")
    print(f"   المفاتيح: {KEYS.relative_to(ROOT)}")
    return 0


def verify() -> int:
    if not KEYS.is_file():
        print("❌ لا مفاتيح — شغّل --seal أوّلًا")
        return 2
    saved = json.loads(KEYS.read_text(encoding="utf-8"))
    now = build()

    changed = [k for k, v in now["files"].items()
               if k in saved["files"] and saved["files"][k] != v]
    added = [k for k in now["files"] if k not in saved["files"]]
    removed = [k for k in saved["files"] if k not in now["files"]]

    if now["root"] == saved["root"]:
        print("🔒 قسم 600-649 مجمّد وسليم — مطابق للختم.")
        print(f"   {saved['atom_count']} ذرّة · {saved['file_count']} ملفًّا")
        print(f"   الجذر: {saved['root']}")
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
