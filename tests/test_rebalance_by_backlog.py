# -*- coding: utf-8 -*-
"""الموازِن يزن بما تراكم لا بما ورد — العطب المقيس ٢٠٢٦-٠٩-١٦.

    عامل 1  طابور      0  ·  NORMAL
    عامل 2  طابور 24,593  ·  OVERLOAD  ·  أُسقط 81,032
    عامل 3  طابور 15,128  ·  OVERLOAD  ·  أُسقط 86,748
    rebalanced = 1   ⟵ منذ الإقلاع كلّه

وأثرُه على المال مقيس: فجوة استلام التِكّة ٣٤٠ ث للذهب و٠٫٦ ث لليورو —
نفس الناشر ونفس التسلسل، والفارق موضعُ الرمز في التوزيع.
"""
from __future__ import annotations

from transport.ownership import OwnershipKey, OwnershipRegistry


def _loaded(keys_per_worker: int, backlog: dict[int, int] | None = None,
            *, hits: int = 1000):
    """سجلٌّ يُبنى **بمساره الحقيقيّ**: المفاتيح تُسجَّل بـ`owner_for`.

    ⚠️ ولا تُكتب `_owners` بيدٍ: القسم يُشتقّ من تجزئة المفتاح، فكتابةُ
       خريطةٍ مخالفة تجعل `partition_of_owner` يعيد قسمًا آخر — وهو ما
       أسقط أوّل صيغةٍ لهذا الاختبار (خطأٌ في التجهيزة لا في الكود).
    """
    reg = OwnershipRegistry(4)
    wanted = 4 * keys_per_worker
    keys = []
    index = 0
    while len(keys) < wanted:
        key = OwnershipKey("acc", "SYM%d" % index)
        index += 1
        reg.owner_for(key)
        keys.append(key)
    # ثمّ تُوزَّع الأقسام بالتساوي على العمّال الأربعة، وورودٌ متساوٍ لكلٍّ
    for position, key in enumerate(keys):
        partition = reg.partition_of_owner(key)
        reg._partition_map[partition] = position % 4
        reg._assigned_partitions.add(partition)
        reg._traffic[partition] = hits
    if backlog is not None:
        reg.set_backlog_source(lambda: dict(backlog))
    return reg


def test_equal_arrivals_but_unequal_backlog_is_seen_as_imbalance() -> None:
    """المشهد الحقيقيّ: الورود متساوٍ والتراكم ليس كذلك.

    ⛔ بالورود يبدو النظام متوازنًا تمامًا فلا يتحرّك الموازِن — وهو
       ما وقع (`rebalanced = 1` وعاملٌ يحمل ٢٤٬٥٩٣ وجارُه صفر).
    """
    reg = _loaded(1, {0: 0, 1: 0, 2: 24_593, 3: 15_128})

    by_arrivals = reg.worker_traffic()
    assert max(by_arrivals.values()) == min(by_arrivals.values()), "الورود متساوٍ"

    by_backlog = reg.worker_load()
    assert by_backlog[2] == 24_593 and by_backlog[1] == 0
    assert max(by_backlog.values()) - min(by_backlog.values()) > 0.15 * sum(
        by_backlog.values()), "الفارق يتجاوز min_gain فيتحرّك الموازِن"


def test_the_drowning_worker_loses_a_partition() -> None:
    """التوزيع الحيّ: ٦–٨ مفاتيح لكلّ عامل، فنقلُ واحدٍ يخفّف ولا يقلب.

    (مقيس ٢٠٢٦-٠٩-١٦: `keys_per_worker = {0:8, 1:7, 2:7, 3:6, 4:7, 5:0}`)
    """
    # سبعة أقسامٍ لكلّ عامل، بورودٍ متساوٍ وتراكمٍ متفاوت
    reg = _loaded(7, {0: 0, 1: 0, 2: 24_593, 3: 15_128})
    moves = reg.rebalance()
    assert moves, "لم يتحرّك الموازِن أمام فارقٍ من أربعةٍ وعشرين ألفًا"
    _partition, source, target = moves[0]
    assert source == 2, "نُقل من غير الأثقل"
    assert target in (0, 1), "لم يُنقل إلى الأخفّ"


def test_a_single_partition_hoarding_the_backlog_is_not_moved() -> None:
    """وحدُّ صدقٍ على العلاج: تراكمٌ محبوسٌ في قسمٍ واحد **لا يُعالَج بالنقل**.

    نقلُه ينقل المشكلة ولا يحلّها، فيرفضه حارس «لا يقلب الميزان» — وهو
    عقدٌ قائم لم أمسّه. وعندها يكون العلاج في مكانٍ آخر لا في الموازنة.
    """
    reg = _loaded(1, {0: 0, 1: 0, 2: 1000, 3: 0}, hits=1)
    assert reg.rebalance() == []


def test_without_a_backlog_source_the_old_behaviour_is_kept_exactly() -> None:
    """ارتدادٌ معلَن: سجلٌّ بلا مصدرٍ يزن بالورود كما كان — لا بأصفار."""
    reg = _loaded(2)                                 # بلا backlog
    assert reg.worker_load() == reg.worker_traffic()
    assert sum(reg.worker_load().values()) == sum(reg.worker_traffic().values())


def test_partition_weight_shares_the_backlog_by_arrival_share() -> None:
    """وحدةُ القياس واحدة: `load` تراكمٌ ووزنُ القسم تراكمٌ كذلك."""
    reg = OwnershipRegistry(4)
    for partition, hits in ((0, 300), (4, 100)):     # كلاهما على العامل 0
        reg._partition_map[partition] = 0
        reg._assigned_partitions.add(partition)
        reg._traffic[partition] = hits
    reg.set_backlog_source(lambda: {0: 800, 1: 0, 2: 0, 3: 0})
    # 800 مقسومة بحصص 300:100  ⟶  600 و200
    assert reg.partition_weight(0) == 600.0
    assert reg.partition_weight(4) == 200.0
    assert reg.partition_weight(0) + reg.partition_weight(4) == 800.0


def test_the_reserved_cold_worker_never_receives_a_scope() -> None:
    """حكمٌ قائم لا يُنقض: المحجوز خارج الوزن وخارج الوجهة."""
    reg = OwnershipRegistry(4, reserved_workers=(3,))
    assert 3 not in reg.worker_load()
    assert 3 not in reg.worker_traffic()


# ── الوصل نفسه، لا المكوّن وحده ────────────────────────────────────────────
#
# ⛔ **درسُ الليلة مطبَّقًا:** أوّل صيغةٍ لهذه الحرّاس اختبرت
#    `OwnershipRegistry` معزولًا، فنجت طفرتان: إلغاءُ الوصل في
#    `OwnershipRuntime`، وتصفيرُ `queue_depth`. كلتاهما تُعيد العطب
#    كاملًا والاختبارات خضراء — وهو نفس ما وقع مع `age_observed`:
#    **يُفحص المكوّن ولا يُفحص الطريق.**

async def _noop(_handler_id, _item):  # noqa: ANN001, ANN202
    return None


def _runtime(worker_count: int = 4):
    from transport.ownership import OwnershipRuntime
    return OwnershipRuntime(
        worker_count=worker_count, mailbox_max_events=64,
        dispatch=_noop, is_active=lambda _h: True)


def test_the_runtime_actually_wires_the_backlog_into_the_registry() -> None:
    runtime = _runtime()
    assert runtime.registry._backlog_source is not None, "الوصل غير موجود"
    # صناديقٌ فارغة ⟶ تراكمٌ صفر لكلّ عامل مفتوح (لا ارتداد إلى الورود)
    assert set(runtime.registry.worker_load().values()) == {0}


def test_real_mailbox_depth_reaches_worker_load() -> None:
    """يُملأ صندوقٌ حقيقيّ، فيجب أن يظهر في وزن الموازِن."""
    runtime = _runtime()
    worker = runtime._workers[0]
    for index in range(17):
        worker.enqueue(handler_id=1, item=("evt", "market.tick", {"n": index}, None),
                       event_name="market.tick", subscriber="777")
    assert worker.queue_depth() == 17
    load = runtime.registry.worker_load()
    assert load[0] == 17, "عمق الصندوق لا يبلغ الموازِن — الوصل مقطوع"
    assert all(load[w] == 0 for w in load if w != 0)
