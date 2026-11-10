"""٥٧٤ — تطبيق المرحلة: إغلاق جزئها ثمّ نقل وقفها. مسارٌ واحد للأثلاث وللمستويات.

٢٠٢٦-١٠-٠٥ (ختم المالك «nq اعتمدناها»): نُقلت **حرفيًّا** من حلقة `atom.py` لحدّ الأربع مئة
سطر فعليّ (م٩/ملف٤) حين أُضيفت الإدارة على مستويات التحليل — صفر تغيير في سطورها إلّا أنّ
موضع الوقف صار يُمرَّر جاهزًا (`lock`): `"BE"` للتعادل، أو سعرٌ (الهدف الأوّل في الأثلاث،
والمستوى الأوّل في الخطّة)، أو `None` للخروج الكامل. وثوابت الأمر معها هنا، و`atom.py`
يستوردها فيبقى سطحُه كما كان (`_mod.EVENT_OUT` · `_mod.REASON_BREAKEVEN` …).
كلّ دالّةٍ تأخذ الذرّة أوّلًا (`atom`) مكان `self` — نسقُ الوحدات الشقيقة في ٥٧٩ و٧٠٧.
"""
from __future__ import annotations

import math
from typing import Any

from shared import execution_costs

EVENT_OUT = "execution.manage.intent"
ACTION_PARTIAL = "CLOSE_PARTIAL"
ACTION_CLOSE = "CLOSE"
ACTION_MODIFY = "MODIFY_SL"
REASON_BREAKEVEN = "BREAKEVEN_AT_FIRST_TARGET"
REASON_PARTIAL = "partial_take"
REASON_LAST_LOT = "partial_take_last_lot"
SIDE_BUY = "BUY"
SIDE_SELL = "SELL"
_VOL_DP = 2
#: ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): سماحُ الفاصلة العائمة قبل قصّ الحجم إلى خطوته.
#: ‎0.7 / 0.1 = 6.9999… فكان القصّ يُسقط خطوةً كاملة (عقد 0.9 يُغلق 0.2 لا 0.3).
_STEP_EPS = 1e-6
_R_DP = 4
#: تقريب سعر الوقف المنقول. ثمانية أرقام تكفي أدقّ رمز عندنا (`tick_size`
#: الفوركس ١e-5) ولا تقصّ شيئًا من الذهب والمؤشّرات.
_PRICE_DP = 8


def spread_now(atom: Any, symbol: Any) -> float:
    """٢٠٢٦-١٠-٢٦ (ختم المالك «NQ»: «يضاف سبريد»): أوسع سبريدٍ حاضرٍ للرمز من تِكّات ميتاتريدر
    (`atom._quotes`: (الحساب، الرمز) ⟵ (العرض، الطلب)). لا تِكّة ⟸ صفر، فيبقى التعادل كما كان."""
    name = str(symbol or "").strip().upper()
    spreads = [ask - bid for (_account, sym), (bid, ask) in (getattr(atom, "_quotes", None) or {}).items()
               if sym == name and ask > bid]
    return max(spreads) if spreads else 0.0


def breakeven_price(atom: Any, symbol: Any, side: str, entry: float) -> float:
    """⚖️ ٢٠٢٦-٠٩-١٨ — أمر المالك: «أخسر 0 لمّا يضرب ستوب الدخول». وسعر الدخول الخام ليس
    تعادلًا: يخرج المركز بخسارة عمولة دورته. فيُزاح بمقدار `العمولة ÷ قيمة الوحدة` — وهي
    مستقلّةٌ عن الحجم لأنّ العمولة بالحجم والربح بالحجم. ورمزٌ بلا عمولة يبقى تعادله دخوله.
    (٢٠٢٦-١٠-٠٦: نُقلت حرفيًّا من `apply_stage` لتستعملها خطّة «أمّن ثمّ احجز» أيضًا.)

    ٢٠٢٦-١٠-٢٦ (ختم المالك «NQ»: «يضاف سبريد»): ويُزاح فوقها بالسبريد الحاضر. فحص المشروع وجد أنّ
    التعادل كان يخرج بخسارةٍ صغيرة: البتكوين −2.69$ والذهب −0.66$ مع العمولة يوم ٢٦/١٠، لأنّ الوقف
    يُضرب بسعر الجهة الأخرى وينفَّذ بعده. فصار وقف التعادل أبعد من الدخول بالعمولة والسبريد معًا."""
    vpp = atom._symbol_vpp.get(str(symbol or "").strip().upper())
    commission = execution_costs.commission_roundtrip(symbol, 0.0)
    offset = (commission / vpp) if (vpp and vpp > 0.0 and commission > 0.0) else 0.0
    offset += spread_now(atom, symbol)
    return (entry + offset) if side == SIDE_BUY else (entry - offset)


def held_stop_not_looser(st: dict[str, Any], body: dict[str, Any],
                         side: str) -> tuple[float, float] | None:
    """٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): «الوقف لا يُوسَّع» (٠٩-١٨) على الوقف القائم أيضًا.

    مقيسٌ بالتشغيل: وقفٌ شُدَّ يدويًّا إلى 20010، ثمّ بلغ السعر الهدف الأوّل فخرج
    وقف التعادل 20000 فأرخاه — لأنّ النقل لم يكن يُقارَن بما عند الوسيط.
    يُرجع (القائم، المطلوب) حين يكون القائم مثلَ المطلوب أو أشدّ، وإلّا `None`.
    والقائم من صورة المركز التي تحفظها دورة ٦٠٩ (`st["pos"]`)؛ ولا وقف قائم ⟸ `None`.
    """
    try:
        held = float((st.get("pos") or {}).get("stop_loss"))
        wanted = float(body.get("stop_loss"))
    except (TypeError, ValueError):
        return None
    if held <= 0.0:
        return None
    tighter_held = wanted <= held if side == SIDE_BUY else wanted >= held
    return (held, wanted) if tighter_held else None


def restore_pending_stop(raw: Any) -> dict[str, Any] | None:
    """٢٠٢٦-١٠-٢٦ (ختم المالك «NQ» على إصلاح فحص المشروع، البند ٨): الوقف المؤجَّل يعبر الإقلاع.

    كانت اللقطة تكتبه مع حالة التذكرة (`dict(state)`) والاستعادة تبني الحالة من حقولٍ مسمّاةٍ ليس هو منها،
    والمرحلةُ تُستعاد متقدّمة — فإقلاعٌ بين إغلاق الجزء ونقل الوقف كان يُضيّع النقل حتّى الهدف التالي.
    يُعاد كما حُفظ متى سلم شكله (أمرُ نقل وقفٍ بسعرٍ موجب · حجمٌ قبل الإغلاق · رقمُ مرحلة)، وإلّا `None` كما كان.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("body"), dict):
        return None
    body = dict(raw["body"])
    try:
        stop = float(body.get("stop_loss"))
        before = float(raw.get("volume_before"))
    except (TypeError, ValueError):
        return None
    stage, cycles = raw.get("stage"), raw.get("cycles", 0)
    if (body.get("action") != ACTION_MODIFY or not stop > 0.0 or not before > 0.0
            or not isinstance(stage, int) or isinstance(stage, bool)
            or not isinstance(cycles, int) or isinstance(cycles, bool)):
        return None
    return {"body": body, "cycles": max(0, cycles), "volume_before": before, "stage": stage,
            "ready": raw.get("ready") is True, "after_close": raw.get("after_close") is True}


async def apply_stage(atom: Any, st: dict[str, Any], pos: dict[str, Any], ticket: Any,
                      symbol: Any, side: str, entry: float, current: float,
                      volume: float, close_frac: float, last_stage: bool,
                      lock: float | str | None, lock_reason: str,
                      progress: float, profit_distance: float) -> None:
    if atom._context is None:
        return
    stage = st["stage"]
    st["stage"] = stage + 1
    min_lot, lot_step = atom._lot_limits(symbol)
    # ٢٠٢٦-٠٩-١٧ — من **المتبقّي** (`volume`) لا من `original`:
    # أمر المالك «ثلث عقد ثمّ نص باقي». و`original` يبقى محفوظًا
    # للاستعادة وللتشخيص، ولا يدخل هذا الحساب.
    close_volume = (volume if last_stage
                    else round(volume * close_frac, _VOL_DP))
    if not last_stage and lot_step > 0.0:
        # الحجم يُقصّ إلى مضاعف خطوة الرمز: حجمٌ ليس من مضاعفاتها
        # يردّه الوسيط ولو تجاوز الأدنى. والقصّ لأسفل لا لأعلى حتّى
        # لا يُغلق أكثر ممّا أمر المالك. والسماح (`_STEP_EPS`) يمنع القسمة
        # العائمة من إسقاط خطوة: مقيسٌ ٢٧ حجمًا من ١٠٠ على خطوة 0.1 (٢٠٢٦-١٠-٠٨).
        close_volume = round(math.floor(close_volume / lot_step + _STEP_EPS) * lot_step,
                             _VOL_DP)
    remainder = round(volume - close_volume, _VOL_DP)
    action, reason = ACTION_PARTIAL, REASON_PARTIAL
    if last_stage:
        # الهدف الثالث: خروجٌ كامل مهما كان الحجم.
        close_volume, action, reason = volume, ACTION_CLOSE, REASON_LAST_LOT
    elif (close_volume < min_lot or remainder < min_lot
          or close_volume > volume):
        # ⚖️ أمر المالك ٢٠٢٦-٠٩-١٦ (ختم `NQ`) حرفيًّا: «واذا عقد صغير
        # ما يتسكر منه شي اجزاء مثل 0.01 يكمل لا هدف 3».
        #
        # وكان الكود يفعل **عكسه بالضبط**: عقدٌ لا يقبل التجزئة
        # يُغلق **كاملًا** عند الهدف الأوّل — أي يُخرَج بثلث ربحه
        # ويُحرَم الهدفين الباقيين. فصفقةٌ بعقد 0.01 كانت تُقفل عند
        # ١٠٠$ بدل أن تمضي إلى ٣٠٠$.
        #
        # الآن: لا يُغلق منه شيء، ويمضي إلى الهدف الثالث حيث يخرج
        # كاملًا. والمرحلة تُعدّ مقطوعة (`stage` تقدّم أعلاه) فلا
        # يُعاد الفحص، **والتعادل يقع كما هو** — نقلُ الوقف إلى سعر
        # الدخول لا يحتاج تجزئةً، والصفقة تصير مجّانيّة كما أمر.
        close_volume = 0.0
        atom._indivisible += 1
    if action == ACTION_CLOSE:
        st["done"] = True
    base = {"account_id": str(pos.get("account_id") or ""),
            "ticket": ticket, "symbol": str(symbol) if symbol else "", "side": side}
    r_multiple = (profit_distance / st["risk"]) if st["risk"] else 0.0
    if close_volume >= min_lot:
        await atom._context.publish(EVENT_OUT, {
            **base, "action": action, "volume": close_volume,
            "last_lot_guard": action == ACTION_CLOSE,
            "stage": stage + 1, "target_progress": round(progress, _R_DP),
            "reason": reason, "r_multiple": round(r_multiple, _R_DP)})
        atom._emitted += 1
    else:
        # ⚠️ ٢٠٢٦-٠٩-١٧ — الامتناع عن الإغلاق كان يمرّ **صامتًا**:
        # المرحلة تتقدّم والوقف يتحرّك ولا شيء يقول إنّ الجزء لم
        # يُغلق. سأل المالك «هدف ثاني ليش ما أغلق نصف عقد باقي»
        # عن التذكرة 1938437873 — نُقل وقفها إلى +1R في 02:17:32
        # (فالمرحلة الثانية دخلت يقينًا) ولم يُرسَل إغلاق، ولم
        # أجد في السجلّ ما يفسّر الامتناع لأنّ هذا الفرع أخرس.
        # الآن يُعلَن بأرقامه: الحجم المحسوب وحدّ الرمز وما بقي.
        atom._skipped_close += 1
        atom._last_skip = (
            "%s م%d: حجم=%.4f < أدنى=%.4f (متبقّي=%.4f خطوة=%.4f)" % (
                symbol, stage + 1, close_volume, min_lot, volume, lot_step))
        atom._context.logger.warning(
            "574 %s ticket=%s المرحلة %d لم تُغلق: حجم=%.4f أدنى=%.4f "
            "متبقّي=%.4f خطوة=%.4f — الوقف يتحرّك والجزء يبقى",
            symbol, ticket, stage + 1, close_volume, min_lot, volume, lot_step)
    # نقل الوقف بعد كل هدف: الأولى تجعل الصفقة مجّانيّة، والثانية تقفل
    # الهدف الأوّل. والنقل يقع **ولو تعذّر الإغلاق الجزئيّ** (عقدٌ لا
    # يقبل التجزئة) — تحريك سعرٍ لا يحتاج حجمًا.
    if lock is None or action == ACTION_CLOSE:
        return
    if lock == "BE":
        new_stop = breakeven_price(atom, symbol, side, entry)
        reason_stop = REASON_BREAKEVEN
    else:
        # سعرٌ محسوب: الهدف الأوّل (الأثلاث) أو المستوى الأوّل (الخطّة).
        new_stop = lock
        reason_stop = lock_reason
    body = {**base, "action": ACTION_MODIFY,
            "stop_loss": round(new_stop, _PRICE_DP),
            "stage": stage + 1, "reason": reason_stop,
            "r_multiple": round(r_multiple, _R_DP)}
    # 🔴 ٢٠٢٦-٠٩-١٩ — **يُغلق الجزء أوّلًا ثمّ يُؤمَّن.**
    #
    # كان الوقف يخرج مع الإغلاق في اللحظة نفسها بلا شرط،
    # فإن رُدَّ الإغلاق عند الوسيط تحرّك الوقفُ وحده: تُؤمَّن
    # صفقةٌ لم تُقبض حصّتُها، فتخرج على تعادلٍ وتترك ربحها.
    #
    # ومقيسٌ على التذكرة 1945019317: الوقف تحرّك ‎18:02‎ و‎18:04‎
    # ونجح، والإغلاق رُدَّ ستّ مرّات بمعرّفٍ مكرّر — فخرجت
    # الصفقة كاملةً على وقفها ولم يُقبض ثلثها ولا نصفُ باقيها.
    #
    # فإن أُرسل إغلاقٌ، يُحتجَز الوقفُ حتّى **يُرى** الحجم
    # ناقصًا على المنصّة. وإن لم يُرسل (عقدٌ لا يقبل التجزئة)
    # يخرج الوقف فورًا كما هو — حكم المالك ٢٠٢٦-٠٩-١٦:
    # «إذا عقد صغير ما يتسكّر منه شي… يكمل لهدف 3»
    # والصفقة تصير مجّانيّة كما أمر.
    if close_volume >= min_lot:
        st["pending_stop"] = {"body": body, "cycles": 0,
                              "volume_before": volume,
                              "stage": stage + 1,
                              "ready": False, "after_close": True}
        atom._stop_deferred += 1
    else:
        # ٢٠٢٦-١٠-٠٢: لا إغلاق يُنتظر، فالوقف جاهزٌ الآن — ويمرّ
        # بحارس الجهة نفسه؛ إن رُدّ يبقى جاهزًا لسعرٍ تالٍ.
        st["pending_stop"] = {"body": body, "cycles": 0,
                              "volume_before": volume,
                              "stage": stage + 1,
                              "ready": True, "after_close": False}
        await atom._release_stop(st, st["pending_stop"], symbol, side,
                                 current, ticket)
