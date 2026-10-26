from __future__ import annotations

import json
from pathlib import Path

from build_registry import BuildRegistry


ROOT = Path(__file__).resolve().parents[1]


def _write_atom(root: Path, atom_id: int, relative: str | None = None) -> Path:
    directory = root / (relative or f"nested/{atom_id}_fixture")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.yaml").write_text(
        "\n".join([
            f"id: {atom_id}",
            "name: Fixture",
            "version: 1.0.0",
            'core_version: ">=1.0.0,<2.0.0"',
            "entrypoint: atom:Atom",
            "critical: false",
            "dependencies: []",
            "publishes: []",
            "subscribes: []",
            "startup_mode: auto",
            "config_schema: {type: object, additionalProperties: false}",
            "config: {}",
            "metadata: {}",
            "",
        ]),
        encoding="utf-8",
    )
    (directory / "atom.py").write_text(
        "from core.contracts.atom import AtomBase\n"
        "class Atom(AtomBase):\n"
        "    async def initialize(self, context): pass\n"
        "    async def start(self): pass\n"
        "    async def stop(self): pass\n",
        encoding="utf-8",
    )
    return directory


def _empty_project(root: Path) -> None:
    for directory in ("atoms", "shared", "governance", "core"):
        (root / directory).mkdir(parents=True, exist_ok=True)


def test_current_tree_is_discovered_recursively_and_execution_target_is_addressable() -> None:
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): 578 أُرشفت بأمر المالك (`25b0cbb`، ٢٠٢٦-٠٩-١٨)
    # فغيابها مشروع؛ والعقد المحروس — اكتشافٌ متداخل لهدف تنفيذ داخل مجلّد قسمه وعنونته
    # بالهويّة — يُقاس على خلفها في السلسلة نفسها: 581 محرّك فرق المركز (ناشر
    # execution.order.requested كما وثّقه الالتزام نفسه).
    # ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»): 581 أُرشفت مع فكّ الأقسام عن القرار، فغيابها مشروع كـ578؛
    # والعقد نفسه يُقاس على ناشر execution.order.requested اليوم: 555 طالب أمر الدخول
    # (السلسلة 414 ⟵ 467 ⟵ 555).
    registry = BuildRegistry(ROOT)
    snapshot = registry.refresh()
    assert snapshot.find_atom(578, scope="forex") == ()
    assert snapshot.find_atom(581, scope="forex") == ()
    found = snapshot.find_atom(555, scope="forex")
    assert len(found) == 1
    assert found[0].path.endswith("555_طالب_أمر_الدخول")
    assert Path(found[0].path).parent.name.startswith("قسم ")
    assert snapshot.find_execution_target(555, scope="forex")


def test_approved_build_metadata_resolves_without_using_counts() -> None:
    snapshot = BuildRegistry(ROOT).refresh()
    assert snapshot.build_contract_status == "RESOLVED"
    assert snapshot.build_id == "QUANT_NQ_COMPLETE_FULL"
    legacy = [source for source in snapshot.build_sources if source.value == "QUANT_NQ_FULL_212"]
    assert legacy
    assert all(source.status.startswith("legacy") or source.status == "legacy" for source in legacy)


# ٢٠٢٦-٠٩-٠٧ (قرار المالك): حُذفت شجرة الكريبتو — مشروع مستقلّ على
# جهاز آخر. الاختبارات التي تحرسها زالت معها؛ ما بقي يحرس الفوركس.


def test_empty_atom_roots_are_a_valid_registry_snapshot(tmp_path: Path) -> None:
    _empty_project(tmp_path)
    (tmp_path / "core" / "CORE.lock").write_text(json.dumps({"file_count": 0}), encoding="utf-8")
    snapshot = BuildRegistry(tmp_path).refresh()
    assert snapshot.manifests == ()
    assert snapshot.forex == ()
    assert snapshot.execution_targets == ()
    assert snapshot.integrity.core_lock_present is True
    assert snapshot.integrity.missing_roots == ()


def test_recursive_discovery_detects_duplicate_ids(tmp_path: Path) -> None:
    _empty_project(tmp_path)
    _write_atom(tmp_path / "atoms", 7, "one/7_first")
    _write_atom(tmp_path / "atoms", 7, "two/7_second")
    snapshot = BuildRegistry(tmp_path).refresh()
    assert snapshot.manifests == ()
    assert snapshot.integrity.duplicate_ids
    assert {item[1] for item in snapshot.integrity.duplicate_ids} == {7}


def test_orphan_atom_file_without_manifest_is_reported(tmp_path: Path) -> None:
    _empty_project(tmp_path)
    orphan = tmp_path / "atoms" / "deep" / "88_orphan"
    orphan.mkdir(parents=True)
    (orphan / "atom.py").write_text("class Atom: pass\n", encoding="utf-8")
    snapshot = BuildRegistry(tmp_path).refresh()
    assert any("manifest.yaml" in error for _, error in snapshot.integrity.discovery_failures)


def test_wrong_root_is_reported_without_crashing(tmp_path: Path) -> None:
    snapshot = BuildRegistry(tmp_path / "not_a_project").refresh()
    # ٢٠٢٦-٠٩-٠٧ — `crypto` لم يعد جذرًا مطلوبًا: شجرته حُذفت بقرار المالك،
    # فغيابها ليس نقصًا يُبلَّغ عنه.
    assert set(snapshot.integrity.missing_roots) == {"forex", "governance", "shared"}
    assert snapshot.manifests == ()


def test_registry_does_not_store_fixed_build_counts_in_its_contract() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "build_registry").glob("*.py"))
    assert "EXPECTED_ATOMS" not in source
    assert "QUANT_NQ_FULL_212" not in source
