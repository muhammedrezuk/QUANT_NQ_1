"""الموازنة بالحِمل لا بعدد المفاتيح.

⛔ المقيس على النواة الحيّة ٢٠٢٦-٠٩-١٠ **بعد** موازنة العدد: المفاتيح
موزّعة بالتساوي عدديًّا، **والطوابير تباعدت**:

    عمّال 1 · 4 · 5   طوابيرهم    1 – 333        DEGRADED
    عمّال 0 · 2 · 3   طوابيرهم  15,055 – 20,213  OVERLOAD

لأنّ رمزًا نشطًا يساوي عدّة رموز هادئة. والعلاقة بين الطابور وعمر التِكّة
رتيبة بلا استثناء واحد (2 ⟵ 0.2ث · 333 ⟵ 0.6ث · 20,213 ⟵ 238.9ث)، فاختلال
الحِمل يترجَم تأخّرًا مباشرًا في القرار — وهو مالُ المالك.

والنقل يمرّ ببروتوكول §٧ لا بالدهس، ولا يمسّ قسمًا مثبَّتًا لمركز مفتوح.
"""

from __future__ import annotations

import pytest

from transport.ownership import (
    MigrationRefused,
    OwnershipKey,
    OwnershipRegistry,
)

ACCOUNT = "52992818"


def _registry(workers: int = 3) -> OwnershipRegistry:
    return OwnershipRegistry(workers)


def _drive(registry: OwnershipRegistry, symbol: str, hits: int) -> None:
    key = OwnershipKey(ACCOUNT, symbol)
    for _ in range(hits):
        registry.owner_for(key)


def test_load_is_counted_by_traffic_not_by_key_count() -> None:
    registry = _registry(2)
    _drive(registry, "BUSY", 1000)
    _drive(registry, "QUIET", 5)

    load = registry.worker_load()
    assert sum(load.values()) == 1005
    assert max(load.values()) >= 1000, "الحِمل يُقاس بالورود لا بعدد المفاتيح"


def test_rebalance_moves_the_heavy_partition_off_the_heavy_worker() -> None:
    registry = _registry(2)
    # ثلاثة رموز هادئة ورمز نشط — قد يقعان معًا على عامل واحد.
    for symbol in ("Q1", "Q2", "Q3"):
        _drive(registry, symbol, 3)
    _drive(registry, "BUSY", 900)

    before = registry.worker_load()
    spread_before = max(before.values()) - min(before.values())

    moves = registry.rebalance(max_moves=2)
    after = registry.worker_load()
    spread_after = max(after.values()) - min(after.values())

    if spread_before > 0.15 * sum(before.values()):
        assert moves, "اختلال واضح ولم يُنقل شيء"
        assert spread_after < spread_before, (
            "النقل لم يقرّب الحِمل: %s ← %s" % (before, after)
        )


def test_rebalance_never_moves_a_pinned_partition() -> None:
    """§٧ — قسمٌ لمركز مفتوح يُثبَّت مكانه مهما اختلّ التوازن."""
    registry = _registry(2)
    busy = OwnershipKey(ACCOUNT, "BUSY")
    _drive(registry, "BUSY", 900)
    _drive(registry, "QUIET", 2)

    origin = registry.owner_for(busy)
    registry.pin(busy)
    registry.rebalance(max_moves=3)

    assert registry.owner_for(busy) == origin, "نُقل قسمٌ مثبَّت لمركز مفتوح"


def test_rebalance_is_quiet_when_the_load_is_already_even() -> None:
    """هامش يمنع التذبذب: لا نقل بلا مكسب حقيقيّ."""
    registry = _registry(2)
    for symbol in ("A", "B", "C", "D"):
        _drive(registry, symbol, 50)
    assert registry.rebalance(max_moves=3) == []


def test_rebalance_does_nothing_on_a_single_worker() -> None:
    registry = _registry(1)
    _drive(registry, "BUSY", 500)
    assert registry.rebalance() == []


def test_layout_shows_load_beside_key_count() -> None:
    """§٣٠ — عدد المفاتيح وحده يخفي الاختلال، فيُعرض الحِمل معه."""
    registry = _registry(2)
    _drive(registry, "BUSY", 400)
    _drive(registry, "QUIET", 4)

    layout = registry.layout()
    assert "load_per_worker" in layout
    assert sum(layout["load_per_worker"].values()) == 404
    assert sum(layout["keys_per_worker"].values()) == 2


def test_moved_partition_keeps_its_identity() -> None:
    """§٢١ — ينتقل العامل، ولا ينتقل القسم: المفتاح يبقى في قسمه."""
    registry = _registry(2)
    key = OwnershipKey(ACCOUNT, "BUSY")
    _drive(registry, "BUSY", 900)
    _drive(registry, "QUIET", 2)
    partition_before = OwnershipRegistry.partition_for(key)

    registry.rebalance(max_moves=2)

    assert OwnershipRegistry.partition_for(key) == partition_before


def test_traffic_decays_so_the_balancer_follows_the_present() -> None:
    """⛔ عدّاد تراكميّ من الإقلاع يجعل الموازنة تحكم على ماضٍ ميت.

    مقيس ٢٠٢٦-٠٩-١٠: طابور العامل ٢ نما 21,299 ⟵ 21,691 بينما انكمش
    الخامس 1,280 ⟵ 50 — والموازنة لم تتحرّك، لأنّ وزن دفقةِ الإقلاع كان
    يغلب كلّ ما جرى بعدها.
    """
    registry = _registry(2)
    _drive(registry, "WAS_BUSY", 1000)      # نشِط قديمًا
    for _ in range(4):
        registry.decay_traffic()
    _drive(registry, "NOW_BUSY", 200)       # النشِط الآن

    load_by_partition = registry._traffic
    old = load_by_partition[OwnershipRegistry.partition_for(OwnershipKey(ACCOUNT, "WAS_BUSY"))]
    new = load_by_partition[OwnershipRegistry.partition_for(OwnershipKey(ACCOUNT, "NOW_BUSY"))]
    assert new > old, "الماضي ما زال يغلب الحاضر: قديم=%d حديث=%d" % (old, new)


def test_decay_drops_partitions_that_went_quiet() -> None:
    """قسمٌ صمت لا يبقى ثقيلًا في الحساب إلى الأبد."""
    registry = _registry(2)
    _drive(registry, "GONE", 4)
    for _ in range(6):
        registry.decay_traffic()
    assert registry._traffic == {}


def test_decay_factor_must_be_a_real_fraction() -> None:
    registry = _registry(2)
    for bad in (0.0, 1.0, -0.5, 2.0):
        with pytest.raises(ValueError):
            registry.decay_traffic(factor=bad)


# ══ §١٤ — الموازنة والوحدة المقسَّمة `(مفتاح، مجموعة)` ═══════════════════════
#
# ⛔ **العطب المقيس على النواة الحيّة ٢٠٢٦-٠٩-١٦:**
#
#     load_per_worker   0: 2,781 · 1: 4,938 · 2: 3,743
#                       3: **10,381** · 4: 3,928 · 5: 4,404
#     rebalanced = 0
#
# عاملٌ يحمل أربعة أضعاف أخفّهم، والموازنة «لا تنقل». وقراءة `rebalanced = 0`
# تُفهَم «لا حاجة»، وحقيقتها كانت **«لا أستطيع»**:
#
#     key = next(k for k in self._owners if self.partition_for(k) == chosen)
#
# بعد §١٤ صار `_owners` يحمل `(مفتاح، مجموعة)`، فترمي
# `AttributeError: 'tuple' object has no attribute 'text'` — و`_maybe_rebalance`
# يبتلع كلّ استثناء («الموازنة تحسين، لا تُسقط التوجيه») فلا يظهر خطأ قطّ.
#
# **ولماذا عاش:** كلّ اختبارات هذا الملفّ تنادي `owner_for(key)` بلا مجموعة،
# فلا تمسّ المسار الجديد إطلاقًا. والحارس لا يُكتب عند حدود الدالّة بل عند
# **حدود الحالة**: وحدةٌ مقسَّمة، واختلالٌ يتجاوز العتبة، ونقلةٌ تُختار فعلًا.


def _drive_group(registry: OwnershipRegistry, symbol: str, group: int,
                 hits: int) -> None:
    key = OwnershipKey(ACCOUNT, symbol)
    for _ in range(hits):
        registry.owner_for(key, group)


def _skewed(groups: int, workers: int = 6) -> OwnershipRegistry:
    """حالة اختلالٍ تتجاوز عتبة الـ15% ويوجد فيها ما يُنقَل."""
    registry = _registry(workers)
    for index in range(10):
        for group in range(groups):
            _drive_group(registry, "Q%02d" % index, group, 50)
    for group in range(groups):
        _drive_group(registry, "BUSY", group, 4000)
    load = registry.worker_load()
    heaviest = max(load, key=lambda w: load[w])
    for index in range(40):
        key = OwnershipKey(ACCOUNT, "T%02d" % index)
        for group in range(groups):
            registry.owner_for(key, group)
            owner_key = key if not group else (key, group)
            if registry._owners.get(owner_key) == heaviest:
                _drive_group(registry, "T%02d" % index, group, 200)
    return registry


def test_rebalance_survives_a_split_scope() -> None:
    """⛔ الحارس الذي كان غائبًا — ولولا التقسيم لما وُجد العطب أصلًا."""
    registry = _skewed(groups=4)
    load = registry.worker_load()
    spread = max(load.values()) - min(load.values())
    assert spread > 0.15 * sum(load.values()), "الحالة ليست مختلّة فلا تختبر شيئًا"
    moves = registry.rebalance(max_moves=1)
    assert moves, "اختلالٌ فوق العتبة ولم يُنقل شيء"


def test_a_split_scope_rebalances_exactly_like_an_unsplit_one() -> None:
    """التقسيم يغيّر عدد الوحدات لا قدرة الموازنة."""
    for groups in (1, 2, 4, 8):
        registry = _skewed(groups=groups)
        load = registry.worker_load()
        if max(load.values()) - min(load.values()) <= 0.15 * sum(load.values()):
            continue
        assert registry.rebalance(max_moves=1), "سقطت عند %d مجموعة" % groups


def test_the_partition_of_a_split_owner_is_readable() -> None:
    key = OwnershipKey(ACCOUNT, "XAUUSD")
    for group in range(4):
        expected = OwnershipRegistry.partition_for(key, group)
        assert OwnershipRegistry.partition_of_owner((key, group)) == expected
    assert OwnershipRegistry.partition_of_owner(key) == \
        OwnershipRegistry.partition_for(key)


def test_a_completed_migration_moves_every_group_of_that_partition() -> None:
    """الانتقال يسجّل الملكية الجديدة — والوحدة المقسَّمة ليست استثناءً."""
    registry = _registry(4)
    key = OwnershipKey(ACCOUNT, "XAUUSD")
    registry.owner_for(key, 2)
    owner_key = (key, 2)
    before = registry._owners[owner_key]
    target = (before + 1) % 4
    partition = registry.begin_migration(owner_key, target)
    registry.mark_snapshot_taken(partition)
    registry.complete_migration(partition)
    assert registry._owners[owner_key] == target, "الملكية لم تُسجَّل بعد الانتقال"


def test_a_failed_rebalance_is_counted_not_swallowed() -> None:
    """⛔ حارسٌ يموت بلا صوتٍ أسوأ من غيابه.

    `rebalanced = 0` وحده لا يميّز «لا حاجة للنقل» من «لا أستطيع النقل» —
    وهذا التمييز بالضبط هو ما أخفى العطب ساعاتٍ على نواةٍ حيّة.
    """
    import asyncio

    from transport.ownership import OwnershipRuntime

    async def _dispatch(_handler_id, _item) -> None:
        return None

    runtime = OwnershipRuntime(
        worker_count=3, mailbox_max_events=8, dispatch=_dispatch,
        is_active=lambda _h: True, scope_groups=2)
    assert runtime.stats()["rebalance_failures"] == 0
    assert runtime.stats()["last_rebalance_error"] == ""

    def _boom(**_kwargs):
        raise RuntimeError("انفجار مصطنع")

    runtime.registry.rebalance = _boom
    runtime._routed_since_balance = runtime.rebalance_every
    runtime._maybe_rebalance()

    stats = runtime.stats()
    assert stats["rebalance_failures"] == 1, "السقوط ابتُلع بلا عدّ"
    assert "انفجار مصطنع" in stats["last_rebalance_error"]
    asyncio.run(runtime.close())


# ══ فجواتٌ كشفها التعطيب المتعمَّد — لا القراءة ═══════════════════════════════
#
# ٢٠٢٦-٠٩-١٦: عُطِّب الكود عمدًا سطرًا سطرًا (تبديل `>=`↔`>` و`==`↔`!=`
# و`True`↔`False` و`max`↔`min`)، ثمّ سُئل: **هل سقط اختبار؟**
#
#     ٧٠ طفرة · نجت ٢٢ (٣١٪)
#
# أي أنّ ثلث ما كُتب يمكن تعطيبه بلا أن يصرخ شيء. والخضراء لا تقول «الكود
# صحيح» — تقول «الكود لا ينفجر». وهذه الحرّاس مكتوبةٌ لطفراتٍ **بعينها**
# نجت، كلٌّ منها يحرس مالًا أو ترتيبًا.


def test_reassign_refuses_a_pinned_partition() -> None:
    """⛔ طفرةٌ نجت: `state_of(p) == PINNED` في `reassign` (سطر 347).

    القسم المثبَّت = مركزٌ مفتوح عند الوسيط. ولو انقلب الشرط لصار `reassign`
    يرفض **غير** المثبَّت ويمرّر المثبَّت — أي ينقل ملكية صفقةٍ حيّة. §٧
    تسمّيها «حراسة مال لا حراسة بنية»، ولم يكن يحرسها اختبار.
    """
    registry = _registry(3)
    key = OwnershipKey(ACCOUNT, "XAUUSD")
    registry.owner_for(key)
    registry.pin(key)
    with pytest.raises(MigrationRefused):
        registry.reassign(key, 2)


def test_reassign_moves_an_unpinned_partition() -> None:
    """والوجه الآخر: غير المثبَّت **يُنقل** — وإلّا مرّ الانقلاب صامتًا."""
    registry = _registry(3)
    key = OwnershipKey(ACCOUNT, "XAUUSD")
    before = registry.owner_for(key)
    target = (before + 1) % 3
    registry.reassign(key, target)
    assert registry._owners[key] == target


def test_reassign_rejects_a_worker_outside_the_range() -> None:
    """⛔ طفرةٌ نجت: حارس المدى في `reassign` (سطر 412)."""
    registry = _registry(3)
    key = OwnershipKey(ACCOUNT, "XAUUSD")
    registry.owner_for(key)
    for bad in (-1, 3, 99):
        with pytest.raises(ValueError):
            registry.reassign(key, bad)
    registry.reassign(key, 2)          # الحدّ الأعلى الصالح يمرّ
    assert registry._owners[key] == 2


def test_rebalance_picks_the_heaviest_move_that_does_not_flip_the_balance() -> None:
    """⛔ طفرةٌ نجت: `movable.sort(..., reverse=True)` (سطر 245).

    والاختبار الأوّل الذي كتبتُه هنا **سقط وعلّمني العقد**: ظننتُ القاعدة
    «انقل الأثقل»، فإذا هي «انقل **أثقل ما لا يقلب الميزان**» — الحارس
    `load[lightest] + traffic[p] < load[heaviest]` يمنع التذبذب. فقسمٌ يحمل
    900 من 906 لا يُنقل أبدًا، لأنّ نقله يبدّل المثقَل بالمخفَّف ولا يوازن.

    ولإسقاط الطفرة لا بدّ من **مرشَّحين صالحين مختلفي الوزن** — وإلّا اتّفق
    الترتيبان على الخيار نفسه ونجت. وهذا ما تبنيه هذه الحالة.
    """
    registry = _registry(2)
    # ⛔ لا تُترك الشكل للقسمة: اختبارٌ يتخطّى نفسه لا يحرس شيئًا. تُجمَع
    # ثلاثة أقسام (120 · 60 · 12) على عاملٍ واحد صراحةً، فالترتيب وحده
    # يحسم الاختيار في كلّ تشغيلة.
    weights = {"H1": 120, "H2": 60, "H3": 12}
    for symbol, hits in weights.items():
        _drive(registry, symbol, hits)
    for symbol in weights:
        registry.reassign(OwnershipKey(ACCOUNT, symbol), 0)
    _drive(registry, "LIGHT", 1)
    registry.reassign(OwnershipKey(ACCOUNT, "LIGHT"), 1)

    load = registry.worker_load()
    heaviest = max(load, key=lambda w: load[w])
    lightest = min(load, key=lambda w: load[w])
    movable = {p: registry._traffic.get(p, 0)
               for p in registry._assigned_partitions
               if registry._partition_map[p] == heaviest}
    viable = {p: t for p, t in movable.items()
              if load[lightest] + t < load[heaviest]}
    assert len(viable) >= 2, "الحالة لم تُبنَ كما يجب: %s" % movable

    moves = registry.rebalance(max_moves=1)
    assert moves, "اختلالٌ فوق العتبة ولم يُنقل شيء"
    chosen = moves[0][0]
    assert viable[chosen] == max(viable.values()), (
        "لم يُختَر أثقلُ الصالحين: نُقل %d (وزن %d) والصالحون %s"
        % (chosen, viable.get(chosen, -1), viable))


def test_rebalance_never_flips_the_heavy_and_the_light() -> None:
    """الحارس الذي علّمني إيّاه السقوط: نقلةٌ تقلب الميزان لا تقع.

    قسمٌ يحمل 900 من 906 لو نُقل لصار المخفَّف مثقَلًا — فالموازنة تتركه
    وتنقل ما دونه، أو لا تنقل شيئًا. وهذا ليس عجزًا بل امتناعٌ مقصود،
    وعلاجه §١٤ (تقسيم الرمز المهيمن) لا إجبار الموازنة.
    """
    registry = _registry(2)
    _drive(registry, "BUSY", 900)
    for symbol in ("Q1", "Q2", "Q3"):
        _drive(registry, symbol, 3)
    before = registry.worker_load()
    spread_before = max(before.values()) - min(before.values())
    registry.rebalance(max_moves=3)
    after = registry.worker_load()
    assert max(after.values()) - min(after.values()) <= spread_before, (
        "الموازنة قلبت الميزان: %d ⟵ %d"
        % (spread_before, max(after.values()) - min(after.values())))


def test_rebalance_actually_narrows_the_spread() -> None:
    """والمحصّلة هي الحكم: نقلةٌ لا تقرّب الحِمل ليست موازنة."""
    registry = _registry(2)
    _drive(registry, "BUSY", 900)
    for symbol in ("Q1", "Q2", "Q3"):
        _drive(registry, symbol, 3)
    before = registry.worker_load()
    spread_before = max(before.values()) - min(before.values())
    if spread_before <= 0.15 * sum(before.values()):
        pytest.skip("الحِمل متوازنٌ أصلًا")
    if not registry.rebalance(max_moves=1):
        return
    after = registry.worker_load()
    assert max(after.values()) - min(after.values()) <= spread_before, (
        "الموازنة وسّعت الفارق: %d ⟵ %d"
        % (spread_before, max(after.values()) - min(after.values())))


def test_reassign_keeps_routing_and_balancing_on_the_same_map() -> None:
    """⛔ عقلان منفصلان: التوجيه ينتقل والموازنة لا تراه.

    كشفه اختبارٌ كُتب بصدق لا قراءةٌ: جُمعت ثلاثة أقسام على عاملٍ واحد
    بـ`reassign` فلم يرها `worker_load()` مجتمعة — لأنّها كانت تكتب
    `_owners` وتترك `_partition_map`. فيُبلَّغ حِملٌ على عاملٍ لم يعد
    يملكه، وتُبنى النقلة التالية على صورةٍ كاذبة.
    """
    registry = _registry(3)
    for symbol, hits in (("A", 100), ("B", 50), ("C", 10)):
        _drive(registry, symbol, hits)
    for symbol in ("A", "B", "C"):
        registry.reassign(OwnershipKey(ACCOUNT, symbol), 0)

    load = registry.worker_load()
    assert load[0] == 160, "الموازنة لا ترى ما نقله التوجيه: %s" % load
    assert load[1] == 0 and load[2] == 0
    for symbol in ("A", "B", "C"):
        assert registry._owners[OwnershipKey(ACCOUNT, symbol)] == 0
    assert registry.layout()["load_per_worker"]["0"] == 160


def test_unpin_releases_only_a_pinned_partition() -> None:
    """⛔ طفرةٌ نجت: `state_of(p) == PINNED` في `unpin` (سطر 346).

    انقلابه يجعل `unpin` **لا يفكّ المثبَّت** — فيبقى قسمٌ لصفقةٍ أُغلقت
    مثبَّتًا إلى الأبد فلا يُوازَن أبدًا — **ويمسح حالة غير المثبَّت**،
    فيُلغي انتقالًا جاريًا بصمت. وجهان للضرر ولا حارس.
    """
    registry = _registry(3)
    key = OwnershipKey(ACCOUNT, "XAUUSD")
    registry.owner_for(key)
    partition = registry.partition_for(key)

    registry.pin(key)
    assert registry.state_of(partition) == "PINNED"
    registry.unpin(key)
    assert registry.state_of(partition) == "ACTIVE", "لم يُفكّ المثبَّت"
    registry.reassign(key, 2)                      # صار قابلًا للنقل فعلًا
    assert registry._owners[key] == 2

    # وفكُّ ما ليس مثبَّتًا لا يمسّ حالته
    other = OwnershipKey(ACCOUNT, "USTEC")
    registry.owner_for(other)
    other_partition = registry.partition_for(other)
    registry.begin_migration(other, 1)
    assert registry.state_of(other_partition) == "DRAINING"
    registry.unpin(other)
    assert registry.state_of(other_partition) == "DRAINING", (
        "فكُّ غير المثبَّت مسح انتقالًا جاريًا")
