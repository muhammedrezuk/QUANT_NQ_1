"""قياسات المال على الأرقام النهائيّة — آخر بوّابةٍ قبل الجسر.

٢٠٢٦-٠٩-٢٣ (ختم `nq`): نُقلت هذه الدوالّ من `atom.py` **حرفيًّا** لأنّه تجاوز
حدّ ٤٠٠ سطرٍ فعليّ (م٩/ملف٤) — صفر تغيير في السلوك. ما كان يقرأ حالة الذرّة
(`self`) صار يأخذ الذرّة معاملًا أوّل، وبقيت في `atom.py` دوالُّ تفويضٍ بأسمائها
القديمة (`_half_spread` · `_reward_ratio` · `_risk_dollars`) فلا يتغيّر نداءٌ
واحد في `_on_built`. والقاعدة كما هي: ذرّةٌ واحدة، عملٌ واحد.
"""
from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def half_spread(atom, scoped: tuple[str, str, str] | None) -> float:
    """نصفُ السبريد بالسعر — كلفةُ عبور الجهة، صفرٌ إن لم تُقَس.

    ٢٠٢٦-٠٩-١٨ (ختم المالك «اعمل أنسب بتلاقيه») — قِيس من ٣٢٦ أمرًا
    منفَّذًا أنّ سعرنا المرجعيّ هو **منتصف السوق** لا سعر الطلب:

        BTCUSD شراء ٧٢ أمرًا وسيط +2.990  ·  بيع ٧٤ أمرًا وسيط −2.500

    تماثلٌ حول الصفر — بصمةُ `mid` قاطعة. فالشراء يُملأ عند
    `mid + s/2` **ويخرج على الجهة المقابلة**: الخسارة `d + s/2`
    والربح `t − s/2`. ومن يضيف إلى المخاطرة ولا يطرح من العائد
    يقيس نسبةً أفضل من الحقيقة — وهذه آخرُ بوّابةٍ قبل الجسر،
    فالكذب فيها يمرّ إلى الوسيط. (كشفَت النصفَ الثاني جلسة ٤٠٠–٤٥٠
    بعد أن صحّحتُ لها النصف الأوّل، وقياسُها يعيد قياسي حرفًا.)

    والصفر عند تعذّر القياس مقصود: النسبة تبقى تُقاس (بلا تصحيح)
    ولا تصمت — والصمتُ هو ما أصلحناه في هذه الدالّة نفسها اليوم.
    """
    record = atom._spread.get(scoped) if scoped is not None else None
    spec = atom._specs.get(scoped) if scoped is not None else None
    if not record or not isinstance(spec, dict):
        return 0.0
    point = _num(spec.get("point")) or _num(spec.get("tick_size"))
    points = _num(record[0])
    if not point or not points or points < 0.0:
        return 0.0
    return points * point / 2.0


def reward_ratio(body: dict[str, Any],
                 half: float = 0.0) -> float | None:
    """نسبةُ الهدف إلى الوقف على الأرقام النهائيّة، أو `None` إن تعذّرت.

    تُقاس هنا وحدها لأنّ هذه آخرُ بوّابةٍ قبل الجسر: ما تقرؤه هو ما
    يصل الوسيط حرفيًّا، لا ما نُوي قبل أن يعدّله حارسُ الشرعيّة.

    🔴 ٢٠٢٦-٠٩-١٨ — كشفته جلسة اللوحة: كانت تعود `None` أيضًا حين
    يُطفأ الحارس بعياره (`min_reward_risk <= 0`)، **قبل أن تقرأ سعرًا
    واحدًا**. فغيابُ الحقل صار ذا معنيين لا يفرّق بينهما قارئ:
    «الحارس مطفأ وكلُّ أمرٍ يمرّ» أو «الأسعار ناقصة في هذا الأمر».
    والأوّل يستحقّ لونًا أحمر لا صمتًا. فصار القياس يقع دائمًا،
    والعيارُ يُفحص عند الحجب وحده ويُنشر مع الأمر ليُقرأ الفرق.
    """
    ref_price = _num(body.get("reference_price"))
    stop = _num(body.get("stop_loss"))
    target = _num(body.get("take_profit"))
    if not ref_price or not stop or not target:
        return None
    # نصفٌ يُضاف إلى المخاطرة ونصفٌ يُطرح من العائد — الجهتان معًا،
    # لا واحدة. والعائد لا ينزل تحت الصفر: هدفٌ داخل السبريد عائدُه
    # صفرٌ ونسبتُه صفر، وذلك حكمٌ صحيح لا قسمةٌ فاشلة.
    risk_d = abs(ref_price - stop) + half
    if risk_d <= 0.0:
        return None
    return max(0.0, abs(target - ref_price) - half) / risk_d


def risk_dollars(atom, body: dict[str, Any],
                 scoped: tuple[str, str, str] | None) -> float | None:
    """المالُ المعرَّض فعلًا عند الوقف، أو `None` إن تعذّر قياسه.

    قيمةُ وحدة السعر للّوت = `tick_value / tick_size` من مواصفات
    الوسيط نفسه — لا «نقطة» ولا رقمٌ من الرأس (ميتاتريدر يعرض
    «قيمة النقطة: 0» لهذه الرموز).
    """
    if scoped is None:
        return None
    spec = atom._specs.get(scoped)
    if not isinstance(spec, dict):
        # ٢٠٢٦-٠٩-٢٣ (ختم `nq`): المواصفة التي حلّها ٥٢٧ تسافر مع الأمر
        # (`symbol_spec`) — وهي التي قاس عليها ٥٢٥ و٥٢٦ قبلي. فلا يُعدّ
        # الأمرُ «بلا مواصفات» وهي في يده.
        spec = body.get("symbol_spec")
        # ولا تُقبل مواصفةُ رمزٍ آخر — المطابقة بالاسم شرط، كما في ٥٢٥.
        if isinstance(spec, dict) and str(spec.get("symbol") or "") != str(body.get("symbol") or ""):
            spec = None
    if not isinstance(spec, dict):
        # 🔴 ٢٠٢٦-٠٩-١٨ — حارسٌ يصمت عند نقص مدخله هو `fail-open` على
        # المال: بلا مواصفات الرمز لا يُقاس المعرَّض، فيمرّ الأمر بلا
        # فحصٍ ولا أثر. يُعدّ هنا ليُقرأ من الشارة، فيُعرف الفرق بين
        # «كلُّ الأوامر مطابقة» و«لم يُقَس منها شيء».
        atom._risk_unmeasured += 1
        atom._last_unmeasured = "%s: لا مواصفات" % (scoped[2] if scoped else "?")
        return None
    tick_value = _num(spec.get("tick_value"))
    tick_size = _num(spec.get("tick_size"))
    volume = _num(body.get("volume"))
    ref_price = _num(body.get("reference_price"))
    stop = _num(body.get("stop_loss"))
    if not tick_value or not tick_size or not volume or not ref_price or not stop:
        return None
    distance = abs(ref_price - stop)
    if distance <= 0.0:
        return None
    return volume * distance * (tick_value / tick_size)
