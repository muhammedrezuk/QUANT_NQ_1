"""بروتوكول انتقال القسم — §٧ من ورقة المصنع.

    إيقاف قبول عمل جديد → إنهاء الجاري → تثبيت لقطة الحالة
    → تسليم الحالة → تسجيل الملكية الجديدة → إعادة تشغيل القسم

    «ممنوع: نقل حيّ وعشوائيّ»
    «ممنوع: نقل قسم عند وجود مركز مفتوح»

قبل هذا البروتوكول كانت `reassign` تنقل المالك فورًا بلا تصريف ولا لقطة —
أي بالضبط النقل الحيّ العشوائيّ الذي تمنعه الورقة. والحالة التي تُفقد ليست
صغيرة: المحلّلات تحمل ٨٬١٩٢ عيّنة سعر لكلّ رمز.
"""

from __future__ import annotations

import pytest

from transport.ownership import (
    PARTITION_ACTIVE,
    PARTITION_DRAINING,
    PARTITION_HANDOVER,
    PARTITION_PINNED,
    MigrationRefused,
    OwnershipKey,
    OwnershipRegistry,
)

KEY = OwnershipKey("52992818", "EURUSD")


def _registry(workers: int = 4) -> OwnershipRegistry:
    registry = OwnershipRegistry(workers)
    registry.owner_for(KEY)          # يُسنَد المالك الأوّل
    return registry


def test_full_handover_moves_the_owner_only_at_the_end() -> None:
    """الخطوات الستّ بالترتيب — والمالك لا يتحرّك قبل الخطوة الأخيرة."""
    registry = _registry()
    partition = OwnershipRegistry.partition_for(KEY)
    origin = registry.owner_for(KEY)
    target = (origin + 1) % registry.worker_count

    registry.begin_migration(KEY, target)
    assert registry.state_of(partition) == PARTITION_DRAINING
    assert registry.owner_for(KEY) == origin, "تحرّك المالك قبل تثبيت اللقطة"

    registry.mark_snapshot_taken(partition)
    assert registry.state_of(partition) == PARTITION_HANDOVER
    assert registry.owner_for(KEY) == origin, "تحرّك المالك قبل اكتمال التسليم"

    assert registry.complete_migration(partition) == target
    assert registry.owner_for(KEY) == target
    assert registry.state_of(partition) == PARTITION_ACTIVE


def test_a_partition_with_an_open_position_cannot_move() -> None:
    """§٧: «قسم مرتبط بمركز مفتوح ⟵ تثبيت مكانه» — حراسة مال لا بنية."""
    registry = _registry()
    origin = registry.owner_for(KEY)
    registry.pin(KEY)

    with pytest.raises(MigrationRefused):
        registry.begin_migration(KEY, (origin + 1) % registry.worker_count)
    with pytest.raises(MigrationRefused):
        registry.reassign(KEY, (origin + 1) % registry.worker_count)

    assert registry.owner_for(KEY) == origin
    registry.unpin(KEY)
    assert registry.begin_migration(KEY, (origin + 1) % registry.worker_count) >= 0


def test_new_work_is_refused_only_after_the_snapshot_is_frozen() -> None:
    """أثناء التصريف يواصل المالك القديم؛ وبعد تجميد اللقطة يُمنع الابتلاع.

    لو قَبِل المالك القديم عملًا بعد تثبيت لقطته، ضاع ذلك العمل من حالة
    المالك الجديد — وهذا فقدُ حالةٍ صامت لا يظهر في أيّ عدّاد.
    """
    registry = _registry()
    partition = OwnershipRegistry.partition_for(KEY)
    assert registry.accepts_new_work(partition)

    registry.begin_migration(KEY, (registry.owner_for(KEY) + 1) % registry.worker_count)
    assert registry.accepts_new_work(partition), "التصريف يعني إنهاء الجاري لا رفضه"

    registry.mark_snapshot_taken(partition)
    assert not registry.accepts_new_work(partition)

    registry.complete_migration(partition)
    assert registry.accepts_new_work(partition)


def test_steps_cannot_be_skipped() -> None:
    """آلة الحالة لا تقبل قفزًا — لا تسليم بلا لقطة، ولا لقطة بلا تصريف."""
    registry = _registry()
    partition = OwnershipRegistry.partition_for(KEY)

    with pytest.raises(MigrationRefused):
        registry.mark_snapshot_taken(partition)
    with pytest.raises(MigrationRefused):
        registry.complete_migration(partition)

    registry.begin_migration(KEY, (registry.owner_for(KEY) + 1) % registry.worker_count)
    with pytest.raises(MigrationRefused):
        registry.complete_migration(partition)
    with pytest.raises(MigrationRefused):
        registry.begin_migration(KEY, 0)


def test_abort_returns_the_partition_untouched() -> None:
    registry = _registry()
    partition = OwnershipRegistry.partition_for(KEY)
    origin = registry.owner_for(KEY)

    registry.begin_migration(KEY, (origin + 1) % registry.worker_count)
    registry.mark_snapshot_taken(partition)
    registry.abort_migration(partition)

    assert registry.state_of(partition) == PARTITION_ACTIVE
    assert registry.owner_for(KEY) == origin
    assert registry.accepts_new_work(partition)


def test_pinning_during_a_live_migration_is_refused() -> None:
    """لا يُثبَّت قسم يتحرّك — يُنهى انتقاله أو يُلغى أوّلًا."""
    registry = _registry()
    registry.begin_migration(KEY, (registry.owner_for(KEY) + 1) % registry.worker_count)
    with pytest.raises(MigrationRefused):
        registry.pin(KEY)


def test_target_worker_must_exist() -> None:
    registry = _registry(workers=3)
    with pytest.raises(ValueError):
        registry.begin_migration(KEY, 7)


def test_layout_declares_migration_state() -> None:
    """§٣٠ — الانتقال حدثٌ في الملكية، فيُعلَن مع «مَن يملك ماذا»."""
    registry = _registry()
    partition = OwnershipRegistry.partition_for(KEY)
    target = (registry.owner_for(KEY) + 1) % registry.worker_count

    assert registry.layout()["partition_states"] == {}

    registry.begin_migration(KEY, target)
    layout = registry.layout()
    assert layout["partition_states"][str(partition)] == PARTITION_DRAINING
    assert layout["migrating_to"][str(partition)] == target

    registry.abort_migration(partition)
    registry.pin(KEY)
    assert registry.layout()["partition_states"][str(partition)] == PARTITION_PINNED
