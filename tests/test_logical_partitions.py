"""الأقسام المنطقية — استقلال المشروع عن عدد أنوية الجهاز.

ورقة المالك «مصنع معالجة قابل للتوسع حسب الموارد» (٢٠٢٦-٠٩-١٠):

    §٤  الوحدة المنطقية ≠ العامل الفيزيائيّ
    §٥  عدد الأقسام المنطقية > عدد العمّال المتوقّع، والوحدة لا تنقسم
    §٨  «لا يوجد رقم ثابت للمعالج داخل الكود»
    §٢١ ٦ ← ١٢ ← ٢٤ نواة: نفس الملكية · نفس الأقسام
    §٣٠ «والأهمّ: مَن يملك ماذا؟»
    §٣١ فشلٌ إن ظهر «عامل مختنق بينما الآخرون خاملون»
"""

from __future__ import annotations

import os
from unittest import mock

from transport.ownership import (
    LOGICAL_PARTITIONS,
    OwnershipKey,
    OwnershipRegistry,
    default_worker_count,
)

ACCOUNT = "52992818"
SYMBOLS = ("AUDUSD", "BTCUSD", "EURUSD", "GBPUSD", "US30", "US500", "USTEC", "XAUUSD")
KEYS = [OwnershipKey(ACCOUNT, s) for s in SYMBOLS]


def test_partition_never_moves_when_the_machine_changes() -> None:
    """§٢١ — القسم ثابت على ٦ أنوية أو ١٢ أو ٢٤.

    قبل الأقسام كان التوزيع `digest % worker_count`، فتنتقل كلّ الملكيات
    بمجرّد تغيّر عدد العمّال — أي يفقد كلّ مفتاح حالته الساخنة عند نقل
    المشروع إلى جهاز آخر. هذا الاختبار يمنع عودة ذلك.
    """
    baseline = {k.text: OwnershipRegistry.partition_for(k) for k in KEYS}
    for worker_count in (1, 2, 3, 6, 12, 24, 48):
        registry = OwnershipRegistry(worker_count)
        for key in KEYS:
            assert OwnershipRegistry.partition_for(key) == baseline[key.text], (
                "تبدّل القسم بتبدّل عدد العمّال — الملكية صارت تابعة للجهاز"
            )
            assert 0 <= registry.owner_for(key) < registry.worker_count


def test_partitions_outnumber_workers_generously() -> None:
    """§٥ — عدد الأقسام يفوق عدد العمّال المتوقّع بكثير."""
    assert LOGICAL_PARTITIONS >= 8 * default_worker_count()
    assert OwnershipRegistry(3).logical_partitions == LOGICAL_PARTITIONS


def test_worker_count_is_discovered_not_hardcoded() -> None:
    """§٨ و§٣٣ — لا رقم أنوية مثبّت؛ يُشتقّ من الجهاز عند تمرير صفر."""
    with mock.patch.object(os, "cpu_count", return_value=24):
        assert default_worker_count() == 12
        assert OwnershipRegistry(0).worker_count == 12
    with mock.patch.object(os, "cpu_count", return_value=4):
        assert OwnershipRegistry(0).worker_count == 2
    with mock.patch.object(os, "cpu_count", return_value=None):
        assert default_worker_count() >= 1, "جهاز لا يُفصح عن أنويته يجب ألّا يُسقط الإقلاع"


def test_explicit_worker_count_still_wins() -> None:
    assert OwnershipRegistry(5).worker_count == 5


def test_ownership_is_sticky_once_assigned() -> None:
    """§٦ — الحالة تتبع القسم؛ فلا يتنقّل مفتاح حيّ من تلقاء نفسه."""
    registry = OwnershipRegistry(4)
    first = [registry.owner_for(k) for k in KEYS]
    again = [registry.owner_for(k) for k in KEYS]
    assert first == again


def test_reassign_is_the_only_way_to_move_an_owner() -> None:
    """§٧ — النقل صريح لا صامت."""
    registry = OwnershipRegistry(4)
    key = KEYS[0]
    original = registry.owner_for(key)
    target = (original + 1) % registry.worker_count
    registry.reassign(key, target)
    assert registry.owner_for(key) == target


def test_no_worker_is_starved_while_others_carry_the_load() -> None:
    """§٣١ — «عامل مختنق بينما الآخرون خاملون» معيار فشل صريح.

    يُفحص على الرموز الثمانية الحيّة وعلى حمل واسع: لا عامل يبقى فارغًا
    بينما غيره يحمل، ولا عامل يحمل أضعاف أقرانه.
    """
    for worker_count in (2, 3, 4):
        registry = OwnershipRegistry(worker_count)
        wide = [OwnershipKey(ACCOUNT, "SYM%03d" % i) for i in range(400)]
        counts = [0] * worker_count
        for key in wide:
            counts[registry.owner_for(key)] += 1
        assert min(counts) > 0, f"عامل بلا عمل إطلاقًا: {counts}"
        assert max(counts) <= 2 * min(counts), f"توزيع مختلّ: {counts}"


def test_owner_key_text_is_ascii_and_cannot_be_mangled() -> None:
    """§٣٠ — حقلٌ يعرض «مَن يملك ماذا» ثمّ يكذب في الاسم أسوأ من غيابه.

    كان الفاصل `×` (U+00D7) فوصل إلى لوحة المالك `52992818ÃUSTEC` —
    بايتا UTF-8 قُرئا Latin-1 في مكانٍ ما على الطريق. الفاصل الآن ASCII
    فلا يبقى للترميز مدخل، بدل ملاحقته على كلّ طبقة.
    """
    text = OwnershipKey("52992818", "USTEC").text
    assert text.isascii(), f"فاصل غير ASCII يعود إلى التشوّه: {text!r}"
    assert text.encode("utf-8").decode("latin-1") == text, "يتشوّه عند خلط الترميز"
    assert text == "52992818|USTEC"


def test_few_live_keys_still_spread_across_every_worker() -> None:
    """§٣١ — الحالة التي كسرت النظام فعلًا: مفاتيح قليلة وعمّال كثيرون.

    مقيس على النواة الحيّة ٢٠٢٦-٠٩-١٠ قبل الإصلاح:

        keys_per_worker = {0: 0, 1: 1, 2: 5, 3: 1, 4: 2, 5: 1}
        العامل 0: صفر مفاتيح · إسقاط صفر
        العامل 2: خمسة مفاتيح · OVERLOAD · إسقاط 868,404

    والأثر التجاريّ مقيس أيضًا: عمر التِكّة تبع حِمل العامل رمزًا برمز
    (6.2ث على أخفّ عامل مقابل 199–208ث على الأثقل)، فحُجب 1,027 قرارًا
    من 1,027 لتقادم البيانات — وBTCUSD الرمز الوحيد المسموح كان عليه.

    السبب: `partition % worker_count` يتكتّل حين تكون المفاتيح الحيّة
    عشرة على أربعة وستّين قسمًا.
    """
    live = ["*", "AUDUSD", "BTCUSD", "DXY_U6", "EURUSD",
            "GBPUSD", "US30", "US500", "USTEC", "XAUUSD"]
    for worker_count in (2, 3, 4, 5, 6):
        registry = OwnershipRegistry(worker_count)
        counts = [0] * worker_count
        for symbol in live:
            counts[registry.owner_for(OwnershipKey(ACCOUNT, symbol))] += 1
        assert min(counts) > 0, f"عامل بلا مفتاح واحد: عمّال={worker_count} {counts}"
        assert max(counts) - min(counts) <= 1, (
            f"فارق حِمل يتجاوز مفتاحًا واحدًا: عمّال={worker_count} {counts}")


def test_assignment_is_reproducible_for_the_same_arrival_order() -> None:
    """الموازنة بالحِمل لا تُفقد الحتميّة — التشخيص يحتاج إعادة إنتاج."""
    live = [OwnershipKey(ACCOUNT, s) for s in SYMBOLS]
    first = [OwnershipRegistry(4).owner_for(k) for k in live]
    second = []
    registry = OwnershipRegistry(4)
    second = [registry.owner_for(k) for k in live]
    third = OwnershipRegistry(4)
    assert [third.owner_for(k) for k in live] == second
    assert first[0] == second[0]


def test_layout_declares_who_owns_what() -> None:
    """§٣٠ — التوزيع معلَن لا صامت.

    وهذا هو الفرق بين «أفضلية» و«قاعدة توجيه خفيّة»: أيّ أولوية تُضاف
    مستقبلًا يجب أن تظهر هنا بالاسم.
    """
    registry = OwnershipRegistry(3)
    for key in KEYS:
        registry.owner_for(key)
    layout = registry.layout()

    assert layout["worker_count"] == 3
    assert layout["logical_partitions"] == LOGICAL_PARTITIONS
    assert layout["worker_count_source"] == "explicit"
    assert sum(layout["keys_per_worker"].values()) == len(KEYS)
    flat = [text for keys in layout["keys"].values() for text in keys]
    assert sorted(flat) == sorted(k.text for k in KEYS), "مفتاح حيّ غائب عن الإعلان"


def test_discovered_count_is_labelled_as_discovered() -> None:
    with mock.patch.object(os, "cpu_count", return_value=8):
        assert OwnershipRegistry(0).layout()["worker_count_source"] == "discovered"
