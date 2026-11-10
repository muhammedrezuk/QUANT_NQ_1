"""بطاقة الصفقة من جهة البوّابة — فتحُ المخزن والكتابةُ عليه.

٢٠٢٦-٠٩-٢٣ (ختم `nq`): نُقلت الدالّتان من `atom.py` **حرفيًّا** لأنّه تجاوز
حدّ ٤٠٠ سطرٍ فعليّ (م٩/ملف٤) — صفر تغيير في السلوك. `self` صار الذرّةَ معاملًا
أوّل، وبقي في `atom.py` تفويضٌ بالاسمين القديمين (`_open_card_store` ·
`_write_card`). ورقمُ البوّابة (`GATE_ID`) يبقى ملكَ `atom.py` ويصل هنا معاملًا،
فلا يُكتب له رقمٌ ثانٍ في مكانٍ آخر.

وهذا الملفّ في مجلّد الذرّة نفسه، فـ`__file__` هنا يصعد إلى الجذر نفسه الذي
كان يصعد إليه من `atom.py` — حلُّ المسار النسبيّ لم يتغيّر.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from core.contracts.atom import AtomContext
from shared.trade_card import CardStore


def open_card_store(atom, context: AtomContext) -> None:
    """بطاقة الصفقة — بختم المالك ٢٠٢٦-٠٩-١٨.

    «صار يسلمك بطاقة وانت تكتب عليه: نفّذت بطاقة بحكم لوت ستوب هدف،
    ربحت خسرت انزلقت، كلّها بهل بطاقة. بالأخير أنا لما بدي أراجع
    صفقة بسحب بطاقتها».

    ولا اتّصال معمَّر: `CardStore` يفتح ويغلق في كل نداء. درسُ
    ٢٠٢٦-٠٩-١٨ مدفوعُ الثمن — اتّصالٌ عمّرتُه منع `VACUUM` فأوقف
    المنصّة. وتعذُّرُ الفتح لا يعطّل بوّابة: البطاقة سجلٌّ لا حارس.
    """
    raw = str(context.config.get("card_db_path") or "").strip()
    if not raw:
        return
    path = raw.replace(os.sep, "/") if not os.path.isabs(raw) else raw
    # الذرّة لا تعرف أين شُغِّلت: مسارٌ نسبيّ يُحلّ عند مالك المسارات
    # وإلّا فُتح مخزنٌ موازٍ تحت مجلّد التشغيل لا يقرؤه أحد — وهو عطبٌ
    # مقيسٌ ومكتوبٌ في ٥١٦ (ملاحظة #1). ويُشترط للإلصاق أن ينتهي اسم
    # المفتاح بـ`_path` وأن يُمرَّر `code_root`، وإلّا مرّ النداء
    # بلا أثرٍ وابتلع `except` الخبر.
    try:
        from pathlib import Path as _Path
        from shared.runtime_paths import manifest_config_rebase
        root = next((parent for parent in _Path(__file__).resolve().parents
                     if (parent / "shared" / "runtime_paths.py").is_file()), None)
        if root is not None:
            path = str(manifest_config_rebase(
                {"card_db_path": path}, code_root=root).get("card_db_path") or path)
    except Exception as exc:  # noqa: BLE001 — أزمةُ مسارٍ لا توقف إقلاع ذرّة
        atom._card_error = "PATH:" + type(exc).__name__
    try:
        store = CardStore(path)
        store.ensure()
        atom._cards = store
    except Exception as exc:  # noqa: BLE001
        atom._card_error = type(exc).__name__


async def write_card(atom, symbol: str, fields: dict[str, Any], gate_id: str,
                     decision_id: str = "") -> None:
    """يكتب حقول المال على بطاقة الرمز الحيّة — ولا يوقف أمرًا أبدًا.

    الكتابة تقع على خيطٍ جانبيّ: قرصٌ متزامنٌ على حلقة asyncio يجمّد
    كلّ ذرّةٍ عليها، وهذه الحلقة تحمل أربعًا وخمسين ذرّة.

    وكلُّ حقلٍ يُسجَّل في `card_writes` باسم كاتبه: من راجع بطاقةً
    عرف من كتب ماذا ومتى، لا الرقمَ وحده.
    """
    store = atom._cards
    if store is None or not symbol or not fields:
        return

    def _job() -> bool | None:
        card = store.live_card(symbol)
        if card is None:
            return False
        # ٢٠٢٦-١٠-٠٧ (تدقيق الإغلاق — ورقة النقاش ٤-ب/١٩): البطاقة الحيّة للرمز قد تكون بطاقةَ صفقةٍ
        # أخرى، فكُتب «رُفض» على صفقةٍ رابحة ودخولان ووقفان على بطاقةٍ واحدة (#86470). الحكم يُكتب
        # على بطاقة القرار نفسه وحدها؛ وإن اختلف الرقمان يُعدّ ولا يُكتب.
        owner = str(card.get("decision_id") or "")
        if decision_id and owner and owner != decision_id:
            return None
        number = int(card["card_no"])
        store.update(number, fields)
        moment = time.time()
        store.notes((number, gate_id, name, value, moment)
                    for name, value in fields.items())
        return True

    try:
        written = await asyncio.to_thread(_job)
        if written is None:
            atom._card_other_decision = getattr(atom, "_card_other_decision", 0) + 1
        elif written:
            atom._card_writes += 1
        else:
            # بطاقةٌ غائبة ليست خطأً: أمرٌ لا بطاقة له (رمزٌ لم يفتح
            # التحليلُ له بطاقة) يُعدّ ولا يُسكت عنه.
            atom._card_missing += 1
    except Exception as exc:  # noqa: BLE001
        atom._card_error = type(exc).__name__
