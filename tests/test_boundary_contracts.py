from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from build_registry import BuildRegistry, core_boot_from_report, evaluate_release
from governance.control_adapter import build_control_event_publisher


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _Report:
    booted: list[int]
    failed: list[int]
    excluded: list[int]
    scan_failures: list
    abort_reason: str | None = None


class _Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str]] = []

    async def publish(self, name: str, payload: dict, *, publisher: str) -> None:
        self.events.append((name, payload, publisher))


def test_core_boot_contract_is_not_atom_count_contract() -> None:
    result = core_boot_from_report(_Report([], [], [], []), core_version="1.25.0")
    assert result.reached_bootloader is True
    assert result.core_success is True
    assert result.atom_boot is not None
    assert result.atom_boot.success is True


def test_atom_failure_is_reported_separately_from_core_reachability() -> None:
    result = core_boot_from_report(_Report([1], [2], [3], []), core_version="1.25.0")
    assert result.reached_bootloader is True
    assert result.core_success is True
    assert result.atom_boot is not None
    assert result.atom_boot.success is False


def test_release_contract_uses_explicitly_approved_build_id() -> None:
    snapshot = BuildRegistry(ROOT).refresh()
    result = evaluate_release(snapshot)
    assert result.status == "READY"
    assert result.ok is True


# ٢٠٢٦-٠٩-٠٧ (قرار المالك): حُذف اختبار سياسة الكريبتو مع شجرته.


def test_core_api_has_no_crypto_event_vocabulary() -> None:
    source = (ROOT / "core" / "api" / "app.py").read_text(encoding="utf-8")
    assert "crypto.universe" not in source
    assert "1001" not in source
