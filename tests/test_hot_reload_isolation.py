# -*- coding: utf-8 -*-
"""حارس العزل والتحميل الحارّ — لا تُقايَض بسرعة.

ختم المالك ٢٠٢٦-٠٩-١٨: «إذا بخسر نقطة من عزل أو تعديل أو تحميل حارّ بصير
مربوط مثل البنوك.» وهذه هي ميزة المشروع على SecDB و Athena: ذرّةٌ تُسحب
وتُعدَّل وتُعاد والنظام يعمل.

والخطر الذي كشفه هذا الحارس حقيقيّ: وحدةٌ شقيقة داخل مجلّد الذرّة تُخزَّن في
`sys.modules` بمفتاحٍ **خارج** بادئة الذرّة تبقى محجوزةً بعد إعادة التحميل —
فتعود الذرّة بكودٍ جديد ووحدةٍ شقيقةٍ قديمة. كسرٌ صامت للتحميل الحارّ.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.bootloader import Bootloader

ROOT = Path(__file__).resolve().parents[1]


def _atoms_with_siblings():
    """كلّ ذرّةٍ تحمّل وحدةً شقيقة من مجلّدها."""
    found = []
    for atom_py in (ROOT / "atoms").rglob("atom.py")  :
        source = atom_py.read_text(encoding="utf-8", errors="replace")
        if "spec_from_file_location" not in source:
            continue
        match = re.search(r"^id:\s*(\d+)", (atom_py.parent / "manifest.yaml")
                          .read_text(encoding="utf-8"), re.M)
        if match:
            found.append((int(match.group(1)), atom_py, source))
    return found


def test_the_core_still_declares_the_prefix_contract() -> None:
    assert Bootloader.atom_module_prefix(350) == "_atom_350_"
    assert Bootloader.atom_module_prefix(580) == "_atom_580_"


def test_hot_reload_purges_by_that_prefix() -> None:
    """العقد ليس ادّعاءً: خدمة التحميل الحارّ تطهّر بهذه البادئة بعينها."""
    service = (ROOT / "core" / "hot_reload_service.py").read_text(encoding="utf-8")
    assert "Bootloader.atom_module_prefix(atom_id)" in service
    assert "del sys.modules[_key]" in service


@pytest.mark.parametrize("atom_id, atom_py, source", _atoms_with_siblings(),
                         ids=lambda v: str(v) if isinstance(v, int) else "")
def test_every_sibling_key_lives_under_its_atom_prefix(atom_id, atom_py, source) -> None:
    """كلّ مفتاح وحدةٍ شقيقة تحت بادئة ذرّته — وإلّا لم يُطهَّر عند التحميل."""
    prefix = Bootloader.atom_module_prefix(atom_id)
    keys = re.findall(r'["\'](_?atom[_]?\d+[_a-z]*)["\']', source)
    assert keys, "لم يُعثر على مفتاح وحدةٍ شقيقة في %s" % atom_py
    for key in keys:
        assert key.startswith(prefix), (
            "%s يستعمل المفتاح %r خارج بادئته %r — التحميل الحارّ لن يطهّره"
            % (atom_py.parent.name, key, prefix))
