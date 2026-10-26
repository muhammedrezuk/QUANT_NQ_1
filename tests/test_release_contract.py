from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import re
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
# ٢٠٢٦-٠٩-٠٧ — مرايا الإعداد زالت مع الكريبتو: كانت لخدمة سوقين، وبسوق
# واحد صارت تكرارًا يُزامَن يدويًّا (كُسر مرّتين في هذه النافذة وحدها).
CONFIG_MIRRORS = (ROOT / "config",)


def _json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_release_contract_matches_measured_architecture() -> None:
    release = _json(ROOT / "config/unified_release.json")
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العقد خُتم في `d28c421` (٢٠٢٦-٠٩-١٩، «release: seal
    # unified Forex release contract»: `release_state: SEALED`) على 1.34.0 و231 ذرّة، بعد إزالة
    # الكريبتو؛ والاختبار بقي على أرقام ما قبل الختم (1.31.0 · 237). يحرس الآن المختوم.
    assert release["release_state"] == "SEALED"
    # ٢٠٢٦-١٠-٢٣ (ختم المالك «NQ» بعد تدقيقٍ خارجيّ): الأرقام وُحّدت مع الحقيقة — إصدار النواة من شيفرتها (`core/__version__.py`
    # = ختم `core/CORE.lock`) وعدد الذرّات خارج الأرشيف كما يكتشفه `build_registry` (212 بعد حدود الحساب 509). فالعقد يُقرأ الآن
    # من مصدريهما لا من رقمٍ مكتوبٍ هنا يتقادم.
    from core.__version__ import CORE_VERSION
    from build_registry import BuildRegistry
    assert release["core_version"] == CORE_VERSION
    assert release["forex_atoms"] == len(BuildRegistry(ROOT).refresh().forex_all)


def test_official_buttons_use_independent_market_launcher() -> None:
    release = _json(ROOT / "config/unified_release.json")
    launchers = release["official_launchers"]
    # ٢٠٢٦-٠٩-٠٧ (قرار المالك): سوق واحد — مُقلِع واحد.
    assert set(launchers) == {"forex"}
    for market, relative in launchers.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert f"scripts\\launch_market.py --market {market}" in source
        assert "--both" not in source
        assert "launch_unified.py" not in source
        assert "governance\\app.py" not in source


