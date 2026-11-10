#!/usr/bin/env python3
"""فحص حوكمة: قسم 600-649 مجمّد ولا يُمسّ.

بأمر المالك ٢٠٢٦-٠٩-٠٧. القسم هو مدخل كل بيانات النظام، وعقده مبنيّ على:
المصدر يُسلّم ولا يحكم · الموزّع يوجّه ولا يدقّق · المدقّق يحكم ويُعلن سببه.
أيّ تعديل هنا يعيد الخلل إلى المدخل حيث لا يُرى أثره إلّا بعد سلسلة كاملة.

الأمر يُثبَت بالقياس لا بالثقة: بصمة SHA-256 لكل ملفّ، وبصمة جذر فوقها.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTION = ROOT / "atoms" / "قسم 600-649"
# ٢٠٢٦-٠٩-٢٤ (ختم Nq صلح): الورق كلّه صار `ورق/` (نقل المالك ٢٢:٥٦) —
# الأختام في قسم ١٢، وورقة التجميد في قسم ١٣.
KEYS = ROOT / "ورق" / "١٢_الأوامر_والأختام" / "أختام التجميد" / "أختام" / "تجميد_قسم_600-649.json"
# ٢٠٢٦-١٠-٢٦ (ختم المالك «nq»): فُكّت مجلّدات «مشترك» في الورق، وصعد محتواها إلى المجلّد الأب.
PAPER = "ورق/١٣_المفتوح_والمعلّق/تجميد_قسم_600-649.md"
SKIP = {"__pycache__", ".pytest_cache"}


def _fingerprint() -> tuple[str, dict[str, str]]:
    files = sorted((p for p in SECTION.rglob("*")
                    if p.is_file() and not any(s in p.parts for s in SKIP)),
                   key=lambda p: p.relative_to(SECTION).as_posix())
    entries = {p.relative_to(SECTION).as_posix():
               hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    root = hashlib.sha256(
        "\n".join(f"{k}:{v}" for k, v in entries.items()).encode("utf-8")
    ).hexdigest()
    return root, entries


def inspect() -> tuple[bool, list[str]]:
    problems: list[str] = []
    if not SECTION.is_dir():
        return False, ["قسم 600-649 غير موجود"]
    if not KEYS.is_file():
        return False, [f"مفاتيح التجميد مفقودة: {KEYS.relative_to(ROOT)}"]

    saved = json.loads(KEYS.read_text(encoding="utf-8"))
    root, entries = _fingerprint()
    if root == saved.get("root"):
        return True, []

    for name, value in entries.items():
        if name not in saved["files"]:
            problems.append(f"أُضيف بلا فكّ تجميد: {name}")
        elif saved["files"][name] != value:
            problems.append(f"تُغيّر بلا فكّ تجميد: {name}")
    for name in saved["files"]:
        if name not in entries:
            problems.append(f"حُذف بلا فكّ تجميد: {name}")
    if not problems:
        problems.append("الجذر لا يطابق الختم بلا فرق ملفّات — أعِد الفحص")
    return False, problems


def main() -> int:
    ok, problems = inspect()
    print("فحص تجميد قسم 600-649")
    print("SECTION_600_649=" + ("FROZEN_INTACT" if ok else "SEAL_BROKEN"))
    if ok:
        print("🔒 مطابق للختم — لا لمس.")
        return 0
    for problem in problems:
        print("  ❌ " + problem)
    print(f"القاعدة وشروط فكّ التجميد في: {PAPER}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
