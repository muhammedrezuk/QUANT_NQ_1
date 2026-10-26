# -*- coding: utf-8 -*-
"""حارس: ذرّةٌ معلَنة `startup: auto` يجب أن تكون قابلةً للتحميل فعلًا.

٢٠٢٦-٠٩-١٨ — الحادثة: عهدة `38fe0d5` رفعت نسخة الذرّة 516 (قاطع الأمان —
سلطة مخاطر لكلّ حساب) وكتبت الرقم نفسه فوق `core_version` بالخطأ:

    -version: "5.4.0"          +version: "5.5.0"
    -core_version: ">=1.0.0,<2.0.0"   +core_version: "5.5.0"

و`core_version` قيدُ توافقٍ مع **النواة** لا نسخةُ الذرّة، و`"5.5.0"` ليست
قيدًا صالحًا أصلًا. فرُفض المنيفست، **ولم تُحمَّل ذرّةُ أمانٍ منذ ذلك الحين**
— والنظام يعمل ويكتب السطر في السجلّ ولا يتوقّف أحد.

فهذا الحارس يمنع تكرار الصنف كلّه: كلّ منيفستٍ يُقرأ، وكلّ `core_version`
يجب أن يكون قيدًا صالحًا يقبل نسخة النواة الحاليّة.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def _core_version() -> str:
    source = (ROOT / "core" / "__version__.py").read_text(encoding="utf-8")
    import re
    match = re.search(r'["\'](\d+\.\d+\.\d+)["\']', source)
    assert match, "لم يُعثر على نسخة النواة"
    return match.group(1)


def _manifests():
    rows = []
    for path in (ROOT / "atoms").rglob("manifest.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            rows.append((path, None))
            continue
        rows.append((path, data))
    return rows


@pytest.mark.parametrize("path, data", _manifests(),
                         ids=lambda v: v.parent.name if isinstance(v, Path) else "")
def test_every_manifest_declares_a_valid_core_constraint(path, data) -> None:
    assert data is not None, "منيفست لا يُقرأ: %s" % path
    raw = str(data.get("core_version") or "")
    assert raw, "منيفست بلا core_version: %s" % path.parent.name
    try:
        spec = SpecifierSet(raw)
    except InvalidSpecifier as exc:
        pytest.fail("%s — core_version=%r ليس قيدًا صالحًا (%s). "
                    "هل كُتبت نسخة الذرّة مكان قيد النواة؟"
                    % (path.parent.name, raw, exc))
    assert Version(_core_version()) in spec, (
        "%s — قيده %r يرفض نواةً نسختها %s، فلن يُحمَّل أبدًا"
        % (path.parent.name, raw, _core_version()))


def test_atom_516_is_the_documented_regression() -> None:
    """الذرّة التي كشفت الصنف — تبقى مذكورةً بالاسم كي لا يُنسى الدرس."""
    directory = next(p for p in (ROOT / "atoms").glob("*/516_*") if p.is_dir())
    data = yaml.safe_load((directory / "manifest.yaml").read_text(encoding="utf-8"))
    assert data["core_version"] == ">=1.0.0,<2.0.0"
    assert data["startup_mode"] == "auto"
