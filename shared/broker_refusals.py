"""رفضُ الوسيط الذي يجوز أن يُعاد — مؤكَّدٌ أنّه لم يُنفَّذ، وعابرٌ بطبعه.

🔴 ٢٠٢٦-٠٩-٢٦ (ختم المالك «Nq») — استخراج الذهب m0 (370$) عالقٌ منذ ٢٥ أيلول.

طُلب 15:30:08 على التذكرة 1965649602 فردّه الوسيط `RETCODE_10029` — «Order or
position frozen» بنصّ ميتاتريدر. وفي الثانية نفسها رُدّ تعديل الوقف على التذكرة
نفسها بالرمز ذاته، وأُغلقت 15:30:09 بوقفها. كان الوسيط يُغلقها فجمّدها. ومن يومها
الطلب `FAILED` لا يُعاد، لأنّ الإعادة لا تقع إلّا بطلبٍ صريح لا ناشر له.

والإعادة على مالٍ حيّ لا تجوز إلّا على ما **ثبت أنّه لم يُنفَّذ**. فالمهلة
(`RETCODE_10012`) ليست رفضًا: في ٢٠٢٦-٠٩-٠٦ رُدّت أربعة أوامر بها و**نُفّذت
كلّها** (مذكّرة `count_unsettled_opens` في ٦٠١). فهي لا تُعاد هنا أبدًا، ولا ما لم
يثبت عندي أنّه لم يُنفَّذ (10011 · 10028 · 10031)، ويبقى كلُّه فشلًا يراه المالك.

ويُعاد من المؤكَّد ما كان عابرًا بطبعه — حالُ مركزٍ أو سوقٍ تتغيّر بعد قليل:

    RETCODE_10004  Requote
    RETCODE_10018  Market is closed
    RETCODE_10020  Prices changed
    RETCODE_10021  No quotes to process the request
    RETCODE_10024  Too frequent requests
    RETCODE_10029  Order or position frozen                        ⟵ المقيس
    RETCODE_10036  Position already closed
    RETCODE_10038  Close volume exceeds current position volume
    RETCODE_10039  Close order already exists for specified position

(النصوص من وثائق ميتاتريدر الرسميّة لرموز خادم التداول، مقروءةً ٢٠٢٦-٠٩-٢٦.)

ومن رفض الإكسبرت نفسه قبل أن يلمس الوسيط (مقروءٌ من `RunCommand` و`CanTrade`):

    NO_POSITION           التذكرة لم تعد موجودة — `SelectPos` فشل قبل أيّ طلب
    BROKER_DISCONNECTED   الوسيط مقطوع — لم يُرسل شيء
    STALE_*               حارس العمر ختمه `EXPIRED` «ولا يلمس السوق»

ولا يُعاد ما هو دائمٌ بطبعه (حجمٌ أو سعرٌ أو وقفٌ غير صالح · تداولٌ معطَّل ·
مالٌ لا يكفي) — إعادته تكرارُ رفضٍ لا علاج — ولا ما أطفأه المالك بيده (إيقافُه ·
منعُ الإكسبرت · التوقّف الطارئ): النظام يعيد ما ردّه السوق، ولا يلتفّ على ما
أطفأه صاحبه.
"""
from __future__ import annotations

from typing import Any

_RETRYABLE_RETCODES = frozenset({10004, 10018, 10020, 10021, 10024,
                                 10029, 10036, 10038, 10039})
_RETRYABLE_NAMES = frozenset({"NO_POSITION", "BROKER_DISCONNECTED"})
_RETCODE_PREFIX = "RETCODE_"
_STALE_PREFIX = "STALE_"


def retryable(reason: Any) -> bool:
    """هل هذا الرفض مؤكَّدٌ أنّه لم يُنفَّذ، وعابرٌ يجوز أن يُعاد؟"""
    text = str(reason or "").strip().upper()
    if not text:
        return False
    if text in _RETRYABLE_NAMES or text.startswith(_STALE_PREFIX):
        return True
    if text.startswith(_RETCODE_PREFIX):
        try:
            return int(text[len(_RETCODE_PREFIX):]) in _RETRYABLE_RETCODES
        except ValueError:
            return False
    return False
