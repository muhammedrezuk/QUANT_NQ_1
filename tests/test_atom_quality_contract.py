from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from build_registry.paths import RegistryAtomRoot
from governance.scripts import validate_atoms as validator


ROOT = Path(__file__).resolve().parents[1]
ATOM_ROOT = RegistryAtomRoot(ROOT)


def test_language_contract_ignores_comments_docstrings_and_human_messages() -> None:
    language_errors = []
    for manifest_path in ATOM_ROOT.rglob("manifest.yaml"):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        source_path = manifest_path.parent / "atom.py"
        if not source_path.is_file():
            continue
        tree = validator.ast.parse(source_path.read_text(encoding="utf-8"))
        language_errors.extend(validator._executable_language_findings(tree, source_path.read_text(encoding="utf-8")))
    assert language_errors == []


def test_all_reported_numeric_values_are_owned_without_moving_them() -> None:
    numeric_ids = {151, 152, 153, 154, 155, 162, 163, 164, 201, 262, 264, 618, 832, 870}
    for atom_id in numeric_ids:
        directory = next(path for path in ATOM_ROOT.iterdir() if path.name.startswith(f"{atom_id}_"))
        source = (directory / "atom.py").read_text(encoding="utf-8")
        numbers = validator.literal_numbers(validator.ast.parse(source))
        owned = validator._owned_numeric_values(atom_id)
        # 2026-08-28 (دمج الشريك): بعض الذرّات صارت ثوابتَ مسماة بالكامل فلا
        # أرقام حرفية — الشرط الملكيةُ لا الوجود.
        # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): الشرط نفسه بلا تغيير، والرسالة تسمّي الذرّة والرقم والسطر بدل «assert False» الصامت.
        unowned = [item for item in numbers if item[2] not in owned]
        assert not unowned, f"الذرّة {atom_id}: أرقام بلا ملكيّة معلنة {unowned}"


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _is_pending_card_bump(item: dict) -> bool:
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): عقد ٢٠٢٦-١٠-٠٢ (بوّابة سلامة التنفيذ): الإصلاح يرفع رقم الكود وحده ورفع البطاقة نشرٌ حيّ بيد المالك، فالكود الأحدث من البطاقة نشرٌ معلّق يُعلَن لا عيب جودة.
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): والعكس (بطاقة أحدث من الكود، أو رقمٌ غير مقروء) يبقى عيبًا حقيقيًّا يُسقط الاختبار.
    if item.get("check") != "نسخة مزدوجة":
        return False
    found = re.fullmatch(r"الكود (\d+\.\d+\.\d+) ≠ المنيفست (\d+\.\d+\.\d+)", str(item.get("detail", "")))
    return bool(found) and _version_tuple(found.group(1)) > _version_tuple(found.group(2))


def test_validator_json_leaves_only_real_quality_errors() -> None:
    import subprocess
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): المفسّر نفسه الذي يشغّل الاختبار، لا أيّ «python» يصادفه المسار.
    result = subprocess.run(
        [sys.executable, "governance/scripts/validate_atoms.py", "--json"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    errors = [item for item in payload["findings"] if item["severity"] == "ERROR"]
    # ٢٠٢٦-١٠-٠٨ (إصلاح الاختبارات القديمة بأمر المالك): المدقّق ما زال يعدّ النشر المعلّق مخالفةً ويخرج 1 — يُشترط اتّساق عدّه وخروجه مع ما وجد، والحكم على الحقيقيّ وحده.
    assert payload["errors"] == len(errors)
    assert result.returncode == (1 if errors else 0)
    real = [item for item in errors if not _is_pending_card_bump(item)]
    assert not real, "مخالفات جودة حقيقيّة:\n" + "\n".join(
        f"{item['atom_id']} {item['check']}: {item['detail']}" for item in real)
