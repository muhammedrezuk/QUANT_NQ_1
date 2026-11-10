# -*- coding: utf-8 -*-
"""§5 / Gate D — حدُّ الإقلاع: `gc.freeze()` (ختم `NQ — APPLY GC FREEZE AFTER BOOT`).

## ما يفعله `freeze` بالضبط — لا ما يُرجى منه

في بايثون ٣٫١٢ ينقل `gc.freeze()` الكائنات **المتتبَّعة وقتَ ندائه** إلى
جيلٍ دائم يُتجاوَز في عمليّات الجمع اللاحقة. وما يُنشَأ بعده يبقى مُدارًا
بالكانس كالعادة.

    ⛔ و`freeze()` ليست `disable()`: الكانس يبقى مُشتغلًا، ويبقى يفحص
       الأجيال الثلاثة — لكنّه لا يعيد مسحَ ما جُمِّد.

    ⛔ ولا كلفةَ «صفر» مضمونة (تصحيحُ المالك، وهو في محلّه): المكسبُ
       يتناسب مع نسبة ما جُمِّد إلى ما يُنشَأ بعده، وهذه تُقاس ولا تُفترَض.

## أين يقع

بعد اكتمال: الاستيراد · تحميلُ الذرّات · تهيئةُ الحالة · تجميعُ الخطّة ·
تهيئةُ المالكين — وقبل دخول الحلقة الساخنة.

    ⛔ وليس في `core/`، ولا في `EventBus`، ولا داخل تِكّة.

## الحراسة

يُسجَّل قبلُ وبعدُ: `isenabled` و`get_freeze_count` وعددُ الكائنات
المتتبَّعة وعتباتُ الأجيال. فما يُعلَن رقمٌ مقيسٌ لا أثرٌ مرجوّ.
"""
from __future__ import annotations

import gc
from typing import Any


def state() -> dict[str, Any]:
    """لقطةُ حالة الكانس — تُؤخذ قبل وبعد، فيُقرأ الفرق لا الادّعاء."""
    return {
        "enabled": gc.isenabled(),
        "frozen": gc.get_freeze_count(),
        "tracked": len(gc.get_objects()),
        "thresholds": gc.get_threshold(),
        "counts": gc.get_count(),
        "collected_per_gen": [dict(row) for row in gc.get_stats()],
    }


def freeze_after_boot(*, collect_first: bool = True) -> dict[str, Any]:
    """يُجمِّد ما بناه الإقلاع، ويُعيد ما قِيس قبلُ وبعدُ.

    و`collect_first` مقصود: كنسةٌ واحدةٌ قبل التجميد تُخرج القمامة التي
    خلّفها الإقلاع، فلا تُجمَّد معه فتبقى في الذاكرة إلى الأبد.
    """
    before = state()
    if collect_first:
        collected = gc.collect()
    else:
        collected = 0
    gc.freeze()
    after = state()
    return {
        "before": before,
        "after": after,
        "collected_at_boot": collected,
        "newly_frozen": after["frozen"] - before["frozen"],
        # ⛔ يبقى مُشتغلًا — وهذا مقصود: `freeze` ليست `disable`.
        "still_enabled": after["enabled"],
    }


def unfreeze() -> None:
    """يُعيد المجمَّد إلى الإدارة — للاختبارات وحدها، لا لمسارٍ ساخن."""
    gc.unfreeze()


def summary(record: dict[str, Any]) -> str:
    before, after = record["before"], record["after"]
    return ("الكانس: مُشتغلٌ %s ⟵ %s · مجمَّد %d ⟵ %d (+%d) · "
            "متتبَّع %d ⟵ %d · كُنس عند الحدّ %d"
            % (before["enabled"], after["enabled"],
               before["frozen"], after["frozen"], record["newly_frozen"],
               before["tracked"], after["tracked"],
               record["collected_at_boot"]))
