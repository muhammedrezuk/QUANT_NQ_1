"""جسور خفيفة إلى `shared/runtime_paths.py` لملفات الحوكمة القائمة بذاتها.

الملفات التي تُقرأ/تُشغَّل بلا حزمة (`governance/checks/*`, `governance/scripts/*`,
`governance/app.py`) تحتاج نفس الجذر القانوني بلا أن تكرّر حسابه — وهو تكرار كان
سبب الانفصال المقياس (فصل ٢٣ من تقرير المسارات). هذا الملفّ **لا يملك** منطقًا:
يعيد الاستدعاء إلى المالك في `shared/runtime_paths.py`.

``code_root`` هنا هو ``Path(__file__).resolve().parent.parent`` من داخل مجلّد
``governance/`` — أي ``ROOT.parent`` = **جذر المشروع**، وهو نفس ما يمرّره
``governance/server.py``، فاللوحة وهذه الأدوات تُقلع على مرسىً واحد.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent      # <ROOT>/governance → <ROOT>


def _owner():
    for base in (_PROJECT, _PROJECT.parent):
        try:
            from shared.runtime_paths import (core_state_root, project_root_of,
                                              runtime_root, runtime_var,
                                              settings_db_path)
            return type("_Owner", (), {
                "runtime_root": runtime_root, "runtime_var": runtime_var,
                "settings_db_path": settings_db_path,
                "project_root_of": project_root_of,
                "core_state_root": core_state_root,
            })
        except ModuleNotFoundError:
            if str(base) in sys.path:
                continue
            sys.path.insert(0, str(base))
    raise RuntimeError("shared/runtime_paths.py غير موجود — لا يمكن اشتقاق جذر التشغيل")


def _market() -> str:
    import os
    return str(os.environ.get("QUANT_GOV_MARKET", "")).strip().lower()


def runtime_var(*parts: str) -> Path:
    owner = _owner()
    return owner.runtime_var(*parts, code_root=_PROJECT, market=_market())


def runtime_root() -> Path:
    owner = _owner()
    return owner.runtime_root(code_root=_PROJECT, market=_market())


def settings_db_path() -> Path:
    owner = _owner()
    return owner.settings_db_path(code_root=_PROJECT, market=_market())


def telegram_conf_path() -> Path:
    """إعدادات المنصّة المتنقّلة تعيش مع بقيّة حالة الـruntime، لا في جذر المشروع."""
    return runtime_var("governance", "telegram.json")   # runtime_var يضيف var/ بنفسه


def core_state_root() -> Path:
    """مرسى حالة النواة (journal/snapshots) — نفس استدعاء run_core.py، لا نسخة منه."""
    owner = _owner()
    return owner.core_state_root(code_root=_PROJECT, market=_market())
