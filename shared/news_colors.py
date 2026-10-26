# -*- coding: utf-8 -*-
"""مرجعنا لألوان أخبار الدولار — ختم المالك «NQ» في ١٠-١٧.

قوله: «هنّ عدد أخبار محدود ومعروف وكلّ سنة بتكرّر — ليش ما تحفظوا بقاعدة عنّا يعرف أيّه أحمر أو أيّه برتقاليّ أو أصفر»، ثمّ:
«أخبار السنة الحمراء معروفة … الاختلاف على ميتاتريدر بس».

الألوان ألوان فوركس فاكتوري (أحمر = HIGH · برتقاليّ = MEDIUM · أصفر = LOW · بلا لون = عطلة). ميتاتريدر يسمّي الأحداث نفسها
بالعربيّة ويصنّفها بغير ذلك (مخزون النفط عنده HIGH، وبيان اللجنة MEDIUM) — فكلّ رمز حدث عنده رُبط باليد باسمه في فوركس فاكتوري،
وأخذ كلّ اسم عربيّ يحمله ذلك الرمز لونه. الجدول `news_colors.json` بجانب هذا الملفّ، تكتبه أداة البناء من قاعدتَي الجسر.
فأيًّا كان المصدر الذي يصل منه الخبر صار لونه واحدًا. واسمٌ ليس في المرجع ⟸ `None`، فيبقى تصنيف المصدر ويُعدّ.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

COLORS_PATH = Path(__file__).with_name("news_colors.json")
IMPACT_OF_COLOR = {"red": "HIGH", "orange": "MEDIUM", "yellow": "LOW", "none": "LOW"}
_CACHE: dict[str, Any] = {}


def reference() -> dict[str, Any]:
    if "ref" not in _CACHE:
        try:
            _CACHE["ref"] = json.loads(COLORS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _CACHE["ref"] = {}
    return _CACHE["ref"]


def normalize(title: Any) -> str:
    return " ".join(str(title or "").split())


def currency() -> str:
    return str(reference().get("currency") or "")


def color_of(title: Any, event_currency: Any) -> str | None:
    """لون الخبر من مرجعنا، أو `None` إن لم يكن فيه أو كانت عملته غير عملة المرجع (الاسم العربيّ نفسه يُطلق على عملات أخرى)."""
    if str(event_currency or "").strip().upper() != currency():
        return None
    return reference().get("by_name", {}).get(normalize(title))


def impact_of(title: Any, event_currency: Any) -> str | None:
    color = color_of(title, event_currency)
    return IMPACT_OF_COLOR.get(color) if color else None
