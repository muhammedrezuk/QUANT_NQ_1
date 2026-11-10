"""٥٥١ — حساب الحجم: اللوت من مسافة الوقف، وتحجيم المسار المباشر، وحارس السقف، والهدف الصافي.

٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): نُقلت **حرفيًّا** من `atom.py` (حدّ الأربع مئة سطرٍ
فعليّ، المادة ٩ ملف ٤) — صفر تغيير في السلوك. كلّ دالّةٍ تأخذ الذرّة أوّلًا (`atom`)
مكان `self`، وبقي في `atom.py` تفويضٌ بكلّ اسمٍ قديم (`_value_per_point` ·
`_lot_for_stop` · `_net_target` · `_resize_direct` · `_verify_costs_within_cap`)،
فالنداء من دالّةٍ هنا إلى أختها يمرّ من الذرّة كما كان. وثوابتُ المدى والبدلين
والانزلاق والعمولة هنا بشروحها، و`atom.py` يستوردها بأسمائها.
"""

from __future__ import annotations

import math
from typing import Any

from shared.financial_scope import text
from shared import execution_costs
from order_builder_common import REASON_LOSS_ABOVE_CAP, SIDE_BUY, SIDE_SELL, _PRICE_DP
from order_builder_common import _RISK_TOLERANCE, _VOLUME_DP, _VOLUME_EPSILON, _to_float

# ٢٠٢٦-٠٩-٠٦ (حكم المالك حرفيًّا): «لازم يشتغل تحت 100 — يحسب ينزلق،
# سبريد — يعني 80، 90، 95، ما يتجاوز 100 أبدًا». المدى الذي تعمل فيه
# الصفقة من سقف المالك: أضعف إعداد عند الأرضية، وأقواه عند السقف الأدنى
# من المئة. الجودة تحرّك الموضع داخل المدى، ولم تعد تضرب السقف ضربًا
# فتهبط به إلى الربع (مقيس: exposure 0.50 × step 0.44 = 0.22 ⇒ 27$).
UTILISATION_FLOOR = 0.80
UTILISATION_CEILING = 0.95
# بدل تنفيذ مقيس على ٣٠ صفقة أُغلقت على الوقف: انزلاق الدخول وسيطه 3.08،
# وانزلاق الوقف مئينه الثمانون 2.60 — مجموعهما ~5.7 عند سبريد 5.00.
# يدخل حساب اللوت كي تكون الخسارة المقيَّدة هي **الواقعة** لا الاسمية.
# ٢٠٢٦-٠٩-٠٦ (حكم المالك: «ادخله») — انزلاق الدخول يدخل الحساب.
#
# كان البدل مضاعفًا للسبريد، وهو خطأ في الوصف: ما يتجاوز به الواقعُ
# المخطَّطَ ليس دالّة السبريد. وتشريح الخسارتين فوق المئة كشف السبب
# الذي لم يكن مقيسًا: **الوقف سعر ثابت لا مسافة**. فإن جاء التنفيذ
# أفضل من المطلوب (لصالحنا) اتّسعت المسافة الحقيقية من الدخول إلى
# الوقف بمقدار ذلك الانزلاق نفسه:
#   1911353370: طُلب 79,908.71 · نُفِّذ 79,905.60 (‎−3.11‎ لصالحنا)
#               فصارت المسافة 27.36 بدل 24.25، ثم انزلق الوقف 17.79
#               ⇒ حركة 45.15 على مخطَّط 24.25 ⇒ 125.07$ فوق السقف.
#
# القياس المباشر لِما يهمّ فعلًا — الزيادة الكلّية على المسافة
# المخطَّطة (|خروج − دخول| − المسافة)، على ٤٥ صفقة أُغلقت على الوقف:
#     الوسيط  −0.65   (الواقع أفضل من المخطَّط في نصف الحالات)
#     المئين ٨٠  +7.54
#     الأقصى    +27.88
# وانزلاق الدخول لصالحنا وحده: وسيط 2.82 · مئين ٨٠ 8.60 · أقصى 16.90.
#
# البدلان يُشتقّان من السعر لا من السبريد، ولكلٍّ دوره:
#   المعتاد (المئين ٨٠ ⇒ 8.00 على 80,000) يضبط **الحجم** فتقع الخسارة
#   الاعتيادية داخل المدى 80→95.
#   الذيل (الأقصى ⇒ 28.00 على 80,000) يضبط **الحدّ** وحده: الحارس
#   أدناه يقصّ اللوت إن كانت الخسارة عنده ستتجاوز المئة — «ما يتجاوز
#   100 أبدًا».
EXCESS_ALLOWANCE_FRAC = 0.0001
TAIL_SLIPPAGE_FRAC = 0.00035

#: ⚖️ ٢٠٢٦-٠٩-١٨ — قاعدة المالك: «لا أعطي قيمة من رأسي، يجب اشتقاقها من
#: سجلّ الصفقات». وهذه مشتقّةٌ منه لا مأخوذةٌ من عندي: لكلّ رمزٍ زوجٌ من
#: النسب — انزلاق **الدخول** (مرجع البناء ⟵ سعر التنفيذ) وتجاوز **الوقف**
#: عند الخروج (الوقف المرسَل ⟵ سعر الإغلاق) — كلاهما **المئين الثمانون**
#: من سجلّ `decisions.db`، لا المتوسّط (يخفي الذيل) ولا الأقصى (يخنق اللوت).
#:
#: والعيار الأعمى الذي كان يحكم الرموز كلّها (0.0450٪ من السعر) يضخّم
#: التكلفة المقيسة **ستّة أضعاف على الذهب وثلاثة عشر على الناسداك**، فيأكل
#: اللوت: على وقفٍ ٦٠ نقطة صارت المخاطرة 22.78$ بدل المئة.
#:
#: ورمزٌ بلا سجلٍّ كافٍ يبقى على العيار القديم — احتياطٌ محافظ لا قصاصة.
_MIN_SAMPLES_FOR_DERIVATION = 20

#: ⚖️ ٢٠٢٦-٠٩-١٨ — الانزلاق والعمولة انتقلا إلى `shared/execution_costs.py`.
#:
#: كانا جدولين هنا وحدهما، و٥٨٤ يحمل رقمه الأعمى الخاصّ. ورقمٌ واحد في
#: مكانين يفترق بأوّل تصحيح — فصار للمنصّة مصدرٌ واحد لتكلفة العبور، مشتقٌّ
#: من سجلّ التنفيذ ومن جسر الوسيط، لا من رأيٍ ولا من «نقطة» لا مرجع لها.
#:
#: ويبقى هنا المدخلان فقط، بأسمائهما القديمة، فلا يتغيّر ما يناديهما.
_slippage_fracs = execution_costs.slippage_fracs
_has_measured_slippage = execution_costs.has_measured


def _commission_for(symbol, fallback: float) -> float:
    """عمولة الدورة الكاملة لكلّ لوت — من سجلّ الوسيط إن وُجد."""
    return execution_costs.commission_roundtrip(symbol, fallback)


def value_per_point(size: dict[str, Any]) -> float:
    """قيمة النقطة الواحدة للّوت الواحد — للسجلّ وحده، لا لحسابٍ يحكم."""
    tick_value = _to_float(size.get("tick_value")) or 0.0
    tick_size = _to_float(size.get("tick_size")) or 0.0
    return (tick_value / tick_size) if tick_size > 0.0 else 0.0


def lot_for_stop(size: dict[str, Any], distance: float) -> float | None:
    """حجم اللوت من مسافة الوقف الفعلية، بعد ابتلاع تكاليف العبور.

    حكم المالك ٢٠٢٦-٠٩-٠٥: «لما يحسب لوت لازم يضمن دخول وانزلاق
    وسبريد وعمولة داخل الستوب» و«ما في صفقة تضرب ستوب أكثر من ١٠
    دولار». الخسارة الكلية = اللوت × (المسافة + السبريد + احتياطي
    الانزلاق) × قيمة النقطة + العمولة، وهي التي تُقيَّد بالميزانية —
    لا مسافة الوقف وحدها. التقريب لأسفل دائمًا كي لا تُتجاوز.
    """
    risk_amount = size.get("risk_amount")
    tick_value = size.get("tick_value")
    tick_size = size.get("tick_size")
    if not risk_amount or not tick_value or not tick_size or distance <= 0.0:
        return None
    cap = size.get("max_trade_loss")
    if cap:
        risk_amount = min(risk_amount, cap)
    # ٢٠٢٦-٠٩-٠٦ (حكم المالك: «يحسب ينزلق، سبريد» ثم «ادخله»):
    # الخسارة التي تُقيَّد بالميزانية هي **الواقعة** لا الاسمية.
    # `execution_allowance` هو المئين الثمانون للزيادة الكلّية على
    # المسافة المخطَّطة — يجمع انزلاق الدخول وانزلاق الوقف معًا لأنّ
    # كليهما يقع على المسافة نفسها، والوقفُ سعرٌ ثابت لا مسافة.
    effective = distance + (size.get("spread") or 0.0) \
        + (size.get("slippage_reserve") or 0.0) \
        + (size.get("execution_allowance") or 0.0) \
        + (size.get("tail_slippage") or 0.0)
    denom = effective * tick_value / tick_size + (size.get("commission_per_lot") or 0.0)
    if denom <= 0.0:
        return None
    step = size.get("volume_step") or 0.01
    # ⚖️ ٢٠٢٦-٠٩-١٧ — أمر المالك: «من 0.125 وتحت 0.12 · من 0.125 وفوق
    # 0.13». تقريبٌ عاديّ إلى أقرب خطوة، لا هبوطٌ دائم.
    #
    # المقيس الذي أوجب الأمر — ذهب بوقف ٧٧٧ نقطة:
    #     اللوت الدقيق لمئة دولار = 0.1287
    #     بالهبوط الدائم  ⇒ 0.12 ⇒  93.24$   (ينقص 6.76$ = ٦٫٨٪)
    #     بالتقريب العاديّ ⇒ 0.13 ⇒ 101.01$   (يزيد 1.01$ = ١٪)
    # وكلّما صغر اللوت كبرت النسبة الضائعة: الخطوة الواحدة على 0.12
    # تساوي ٨٪ من الصفقة، وعلى 2.5 تساوي ٠٫٤٪.
    #
    # و٥١٣ كان يقرّب عاديًّا أصلًا (`513:246`) وهذه وحدها تهبط — فذرّتان
    # على الرقم نفسه بقاعدتين، والأصغر منهما يفوز في `min`. الآن
    # توحّدتا، والحارس نفسه يحكمهما: هبوطٌ فقط إن تجاوز التقريبُ
    # `risk_amount × 1.02`، وحكم «ما يتجاوز 100 أبدًا» يبقى محروسًا
    # بالسقف الصلب أدناه لا بالتقريب.
    raw = risk_amount / denom
    # اللوت يُقرّب إلى الأسفل دائمًا؛ خطوة أعلى من الحساب ليست مقبولة
    # حتى لو كانت الزيادة صغيرة.
    stepped = math.floor(raw / step) * step
    # ٢٠٢٦-٠٩-٠٦ (حكم المالك: «مو تحطّ سقف يخنق غلطه — لازم من أساس
    # ما يغلط»): كان اللوت يُحسب على المسافة المعتادة ثم يُقصّ إن
    # تجاوز السقف عند الذيل — أي نصنع رقمًا خاطئًا ثم نصلحه. صار
    # `effective` أعلاه يحمل الذيل المقيس نفسه، فالخسارة القصوى
    # مقيَّدة **بالبناء** ولا يبقى ما يُقصّ. هذا السطر تأكيد لا مِقصّ:
    # إن أطلق فالخلل في تركيب `effective` لا في السوق.
    # ٢٠٢٦-٠٩-١٧ — الهامش هنا هو **خطوة التقريب وحدها**: أمر المالك
    # «من 0.125 وفوق 0.13» يقبل ضمنًا زيادةً من التقريب لأعلى، وبلا
    # هذا الهامش يطلق الحارسُ فيهبط باللوت ثانيةً ويُلغي الأمر.
    # وحكمه «ما يتجاوز 100 أبدًا» يبقى محروسًا في جوهره: السقف
    # 100 × 1.02 = 102، والتجاوز المسموح ثمن خطوةٍ لا اتّساع مخاطرة.
    hard_cap = (size.get("hard_trade_loss_cap") or 0.0) * _RISK_TOLERANCE
    if hard_cap > 0.0 and stepped * denom > hard_cap:
        self_log = size.get("logger")
        if self_log is not None:
            self_log.error("551 تناقض داخليّ: لوت %.2f × %.2f فوق السقف %.2f",
                           stepped, denom, hard_cap)
        stepped = math.floor((hard_cap / denom) / step) * step
    if stepped + _VOLUME_EPSILON < (size.get("volume_min") or 0.0):
        return None
    v_max = size.get("volume_max")
    return round(min(stepped, v_max) if v_max else stepped, _VOLUME_DP)


def net_target(atom, order: dict[str, Any], size: dict[str, Any]) -> None:
    """يزيح الهدف ليصير الربح عنده **صافيًا** بعد العمولة.

    ⚖️ ٢٠٢٦-٠٩-١٨ — أمر المالك: «بدي منك أخسر 100 إذا ضربت ستوب لوز،
    وأخسر 0 لمّا يضرب ستوب دخول، وأربح 300 لمّا أضرب هدف 3 — صافي».

    والمقيس قبله: الثلاثة تنقص بمقدار العمولة. الوقف ‎-97.12‎ لا ‎-100‎،
    والتعادل ‎-1.12‎ لا صفرًا، والهدف ‎+286.88‎ لا ‎+300‎.

    والإزاحة تخرج من الجبر لا من تقريب:

        الربح الصافي = D_target × لوت × قيمة_الوحدة − عمولة × لوت
        والخسارة     = D_stop   × لوت × قيمة_الوحدة + عمولة × لوت

        فلجعل الربح = n × الميزانيّة، حيث n = D_target ÷ D_stop:
            الإزاحة = (n + 1) × العمولة ÷ قيمة_الوحدة

    وهي مستقلّةٌ عن الحجم — طرفا الكسر بالحجم. والذهب عند n=3:
    (3+1) × 7 ÷ 100 = 0.28$ — أي 0.047R، لا عُشر R كما قُدِّر.

    ⚠️ وليست «زرعًا على قالب»: مسافة الفكرة تبقى كما وردت من صاحبها،
    ولا يُضاف إليها إلّا ثمن الخروج منها. ورمزٌ بلا عمولة (البتكوين
    والناسداك، مقيسًا صفرًا في 142 صفقة) لا يتحرّك هدفه شعرة.
    """
    price = _to_float(order.get("reference_price"))
    stop = _to_float(order.get("stop_loss"))
    target = _to_float(order.get("take_profit"))
    side = str(order.get("side") or "").upper()
    symbol = order.get("symbol")
    if not price or not stop or not target or side not in (SIDE_BUY, SIDE_SELL):
        return
    commission = execution_costs.commission_roundtrip(
        symbol, size.get("commission_per_lot") or 0.0)
    vpp = atom._value_per_point(size)
    if not vpp or vpp <= 0.0:
        return
    risk_distance = abs(price - stop)
    reward_distance = abs(target - price)
    if risk_distance <= 0.0 or reward_distance <= 0.0:
        return
    multiple = reward_distance / risk_distance
    # 🔴 والعمولة وحدها لا تكفي — السبريد يدخل من الباب الآخر.
    #
    # الهدف يُقاس من `reference_price`، والربح يقع من **سعر التنفيذ**.
    # وبينهما فرقٌ مقيس: الشراء يُنفَّذ على `ask` والمرجع ليس هو، فالربح
    # ينقص بمقدار ما دُفع عند الدخول. وهو ليس تقديرًا: مقيسٌ من
    # `مرجع البناء ⟵ سعر التنفيذ` على 95 صفقة بتكوين و48 ذهبًا.
    #
    # والوقف لا يحتاج هذه الإضافة: `_lot_for_stop` يضع الانزلاق نفسه في
    # مقام حساب اللوت، فالخسارة مقيَّدة بالحجم أصلًا. وهنا وحده يُزاح
    # السعر — لأنّ الربح لا حجمَ يقيّده.
    entry_slip_frac, _ = execution_costs.slippage_fracs(symbol)
    entry_slip = abs(price) * entry_slip_frac
    offset = (multiple + 1.0) * commission / vpp + entry_slip
    if offset <= 0.0:
        return
    order["take_profit"] = round(
        (target + offset) if side == SIDE_BUY else (target - offset), _PRICE_DP)
    order["target_net_offset"] = round(offset, _PRICE_DP)
    atom._net_targets = getattr(atom, "_net_targets", 0) + 1
    atom._last_net = "%s %.2fR +%.5f" % (symbol, multiple, offset)


def resize_direct(atom, order: dict[str, Any],
                   payload: dict[str, Any]) -> dict[str, Any] | None:
    """يُخضع أمر المسار المباشر لسقف خسارة المالك.

    حكمه ٢٠٢٦-٠٩-٠٥: «ما في صفقة تضرب ستوب أكثر من ١٠ دولار» و«لازم
    لوت ينحسب على ستوب ويطلع لوت مناسب، مو ثابت». الحجم يُحسب من
    مسافة وقف **هذا الأمر** بعد ابتلاع السبريد والانزلاق والعمولة،
    ولا يزيد أبدًا عمّا طلبه صاحب الأمر (سقف الخطوة يبقى حدًّا أعلى).
    أمرٌ لا يمكن تصغيره تحت السقف لا يُرسَل.
    """
    price = _to_float(order.get("reference_price"))
    stop = _to_float(order.get("stop_loss"))
    volume = _to_float(order.get("volume"))
    side = str(order.get("side") or "").upper()
    if not price or not stop or not volume or side not in (SIDE_BUY, SIDE_SELL):
        return order            # لا وقف = لا معادلة؛ 525 يحرس شرعيّته
    distance = (price - stop) if side == SIDE_BUY else (stop - price)
    if distance <= 0.0:
        return order            # مقلوب — حارس 525 يرفضه بسببه الصريح
    account = text(order.get("account_id"))
    broker = text(order.get("broker")) or atom._broker_by_account.get(account, "")
    symbol = str(order.get("symbol") or "")
    size = atom._sizes.get((account, broker, symbol)) if (account and broker) else None
    if not size:
        return order            # لا مواصفة بعد؛ الحارس التالي يقرّر
    size = dict(size)
    # حصّة هذه الخطوة من سقف المالك — عاملان لا واحد:
    #   exposure = جودة الإشارة (حِزَم 581: 0.10 · 0.25 · 0.50)
    #   step     = نسبة هذه الخطوة من الهدف الإجمالي
    # فالسقف حدٌّ أقصى لا هدف: إعداد ضعيف يأخذ عُشره، وقويّ نصفه،
    # ولا يُلامَس إلا نظريًّا. بلا عامل الجودة كانت كل صفقة تستهلك
    # السقف كاملًا مهما كانت الإشارة — وهو ما رصده المالك ٢٠٢٦-٠٩-٠٦.
    # ٢٠٢٦-٠٩-٠٦ (حكم المالك على لقطة الشارت: «ستوب لسّه ٢٥ دولار»،
    # ونصّه: «لازم يشتغل تحت 100 — يحسب ينزلق، سبريد — يعني 80، 90،
    # 95، ما يتجاوز 100 أبدًا»):
    #
    # كان العاملان (جودة الإشارة × نسبة الخطوة) يضربان السقف ضربًا،
    # فينزل ١٠٠ إلى ٢٧ مقيسًا (exposure 0.50 × step 0.44 = 0.22).
    # الضرب يصلح لترتيب الأولويات، لا لتحديد الرقم — فحاصله يهبط
    # بلا قاع كلّما تعدّدت الخطوات.
    #
    # الحصّة تُخاطَب الآن كما نطق بها المالك: مدىً بين ٨٠٪ و٩٥٪ من
    # السقف، وجودة الإشارة تحرّك الموضع داخله لا خارجه. فأضعف إعداد
    # يخاطر بثمانين، وأقواه بخمسة وتسعين، والمئة لا تُبلَغ أبدًا.
    cap = size.get("max_trade_loss") or size.get("risk_amount")
    if cap:
        # السقف الصلب يُحفظ قبل أي حصّة — الحارس يقيس عليه لا عليها.
        size["hard_trade_loss_cap"] = float(cap)
        share = 1.0
        for key in ("exposure_fraction", "step_fraction"):
            value = _to_float(payload.get(key))
            if value is not None and 0.0 < value <= 1.0:
                share *= value
        util = UTILISATION_FLOOR + max(0.0, min(1.0, share)) * (
            UTILISATION_CEILING - UTILISATION_FLOOR)
        size["risk_amount"] = size["max_trade_loss"] = cap * util
    if payload.get("costs_in_stop") is True:
        # التكاليف مُضمَّنة في مسافة الوقف المرسل (581 أزاحه للخارج
        # كي يبقى للتحليل مداه). إضافتها هنا ثانيةً تحسبها مرّتين.
        size["spread"] = size["slippage_reserve"] = 0.0
    # بدل التنفيذ يبقى خارج هذا الاستثناء: `costs_in_stop` يعني أن
    # التكاليف داخل **مكان** الوقف، لا أن التنفيذ لن ينزلق عنه.
    req_spread = _to_float(payload.get("spread")) or 0.0
    ref_price = _to_float(payload.get("reference_price")) or 0.0
    if ref_price > 0.0:
        size["commission_per_lot"] = _commission_for(
            symbol, size.get("commission_per_lot") or 0.0)
        entry_frac, exit_frac = _slippage_fracs(symbol)
        size["execution_allowance"] = ref_price * entry_frac
        size["tail_slippage"] = ref_price * exit_frac
        # لا سبريد فوق الانزلاق المقيس — هو داخلٌ فيه (مقيسٌ من الأسعار
        # الفعليّة)، وإضافته تحسبه مرّتين وتأكل اللوت.
        size["spread"] = size["slippage_reserve"] = 0.0
        atom._slip_source = "%s %s" % (
            symbol, "سجلّه" if _has_measured_slippage(symbol) else "أسوأ_مقيس")
    if payload.get("costs_in_stop") is not True and req_spread > 0.0:
        size["spread"] = req_spread
        req_slip = _to_float(payload.get("slippage_reserve"))
        if req_slip is not None:
            size["slippage_reserve"] = req_slip
    sized = atom._lot_for_stop(size, distance)
    if sized is None:
        atom._context.logger.warning(
            "551 direct %s %s: sizing unavailable — volume=%s dist=%.2f "
            "risk_amount=%r tv=%r ts=%r", symbol, side, volume, distance,
            size.get("risk_amount"), size.get("tick_value"), size.get("tick_size"))
        return order
    final = min(volume, sized)
    v_min = size.get("volume_min") or 0.0
    if final + 1e-12 < v_min:
        atom._skipped += 1
        atom._skip_reasons[REASON_LOSS_ABOVE_CAP] = \
            atom._skip_reasons.get(REASON_LOSS_ABOVE_CAP, 0) + 1
        atom._context.logger.warning(
            "551 skip %s %s: LOSS_ABOVE_CAP — أصغر لوت مسموح %s يتجاوز "
            "السقف على مسافة %.2f", symbol, side, v_min, distance)
        return None
    atom._context.logger.warning(
        "551 direct %s %s: volume %s -> %s (dist=%.2f spread=%s slip=%s cap=%s)",
        symbol, side, volume, final, distance, size.get("spread"),
        size.get("slippage_reserve"), size.get("max_trade_loss"))
    order["volume"] = final
    verified = atom._verify_costs_within_cap(order, size, distance, final)
    if verified is not None:
        atom._net_target(verified, size)
    return verified


def verify_costs_within_cap(atom, order: dict[str, Any], size: dict[str, Any],
                            distance: float, volume: float) -> dict[str, Any]:
    """حارسٌ يتحقّق أنّ الصفقة **كما وردت** تسع الميزانيّة — ولا يعدّلها.

    ⚖️ ٢٠٢٦-٠٩-١٧ — شكوى المالك بنصّها: «كيف صفقة ناسدك ستوبها 60
    دولار وربحها 200 دولار». وهي مقيسة على تذكرة `FILLED_OPEN` حقيقيّة
    (`555-106098ac8d57`, USTEC BUY vol=1.8):

        مرجع 28961.70 · وقف 28925.21 · هدف 29071.18
        مسافة الوقف 36.49 · مسافة الهدف 109.48 · النسبة 3.000
        وبالدولار: وقف ≈ 65.7$ · هدف ≈ 197$

    والنسبة ٣ صحيحة **على المسافة** وكاذبة **على المال**، والمالك يقرأ
    المال. والسبب أنّ الحدّين يُقاسان بمسطرتين:

        اللوت يُحسب على  `effective = distance + spread + slippage
                          + execution_allowance + tail_slippage`
                         (حكمه ٢٠٢٦-٠٩-٠٥: «يضمن دخول وانزلاق وسبريد
                          وعمولة داخل الستوب») ⇒ الخسارة الواقعة = السقف
        والهدف يُحسب على `distance` وحدها ⇒ الربح أقصر بنسبة
                         `distance / effective`

    فالمخاطرة الواقعة ٨٠ (السقف ١٠٠ × `util` ٠٫٨٠ بحكمه «٨٠، ٩٠، ٩٥،
    ما يتجاوز ١٠٠ أبدًا») والربح ١٩٧ — أي **٢٫٤٦ لا ٣**. وهي شكواه
    القديمة نفسها: «الهدف ١٫٦٩R لا ٣R».

    والعلاج من الكود نفسه لا من عندي: `costs_in_stop` آليّةٌ قائمة
    يستعملها ٥٨١ (يزيح الوقف للخارج «كي يبقى للتحليل مداه»، سطر ٤٢٢)
    ولا يستعملها مسار ٥٥٥. فيُزاح الوقف إلى `effective` — وهي المسافة
    التي حُسب عليها اللوت أصلًا، فلا يتغيّر اللوت ولا تزيد الخسارة
    الواقعة قيد دولار — ثمّ يُبنى الهدف على المسافة نفسها:

        الخسارة عند الوقف = lot × effective × vpp = السقف بالضبط
        الربح  عند الهدف  = lot × 3×effective × vpp = ثلاثة أضعافه

    ⚠️ وما لم يتغيّر: `util` يبقى ٠٫٨٠–٠٫٩٥ كما نطق به المالك، فالنتيجة
    ٨٠ و٢٤٠ لا ١٠٠ و٣٠٠. بلوغ المئة يلزمه رفع `util` إلى ١٫٠ وهو عيارٌ
    نطق به هو، فلا يُرفع إلا بكلمته.
    """
    price = _to_float(order.get("reference_price"))
    stop = _to_float(order.get("stop_loss"))
    side = str(order.get("side") or "").upper()
    if not price or not stop or side not in (SIDE_BUY, SIDE_SELL):
        return order
    cost = ((size.get("spread") or 0.0)
            + (size.get("slippage_reserve") or 0.0)
            + (size.get("execution_allowance") or 0.0)
            + (size.get("tail_slippage") or 0.0))
    if cost <= 0.0 or distance <= 0.0:
        return order
    effective = distance + cost
    # 🔴 ٢٠٢٦-٠٩-١٨ — حكم المالك: «هي صفقة مرفوضة، ما بصير يتعدّل عليه
    # وتنزرع على قالب وتتمشّى».
    #
    # وكان هنا إزاحةُ الوقف والهدف: وقفٌ ورد بستّين نقطة يخرج إلى المنصّة
    # بمئتين وواحدة وتسعين على الذهب وبأربعة آلاف وتسعمئة وستٍّ وتسعين على
    # البتكوين — مقيسًا بتشغيل هذا الملفّ نفسه على تِكّاتٍ حيّة. السبب أنّ
    # `execution_allowance` و`tail_slippage` نسبةٌ من **سعر الرمز** لا من
    # مسافة الوقف، فكلّما غلا الرمز ابتلعت التكاليفُ الوقفَ كلّه.
    #
    # ولا حاجة للإزاحة أصلًا: `_lot_for_stop` تضع هذه التكاليف نفسها في
    # **مقام** حساب اللوت (`effective` هناك)، فالخسارة القصوى مقيَّدة
    # بالحجم لا بمكان الوقف. فالإزاحة كانت حسابًا ثانيًا للتكلفة نفسها،
    # وثمنه أنّ مستويات الصفقة لم تعد مستويات صاحبها.
    #
    # فالوقف والهدف يمرّان **كما وردا**. وهذه الدالّة تتحقّق ولا تكتب:
    # إن لم تتّسع الميزانيّة للصفقة كما طُلبت، يُرفض الأمر بسببٍ معلن.
    vpp = atom._value_per_point(size)
    volume = _to_float(order.get("volume")) or volume
    exposure = volume * effective * vpp + \
        (size.get("commission_per_lot") or 0.0) * volume
    hard_cap = (size.get("hard_trade_loss_cap") or 0.0) * _RISK_TOLERANCE
    atom._last_costs = (
        "%s وقف=%.4f تكاليف=%.4f سبريد=%.4f احتياطي=%.4f انزلاق=%.4f "
        "ذيل=%.4f عمولة=%.2f مخاطرة=%.2f$" % (
            order.get("symbol"), distance, cost, size.get("spread") or 0.0,
            size.get("slippage_reserve") or 0.0,
            size.get("execution_allowance") or 0.0,
            size.get("tail_slippage") or 0.0,
            (size.get("commission_per_lot") or 0.0) * volume, exposure))
    if hard_cap > 0.0 and exposure > hard_cap:
        atom._skipped += 1
        atom._skip_reasons[REASON_LOSS_ABOVE_CAP] = \
            atom._skip_reasons.get(REASON_LOSS_ABOVE_CAP, 0) + 1
        atom._last_reject = "%s %s مخاطرة=%.2f$ سقف=%.2f$" % (
            order.get("symbol"), side, exposure, hard_cap)
        atom._context.logger.warning(
            "551 رفض %s %s: %s — الصفقة كما وردت تخاطر بـ%.2f$ والسقف "
            "%.2f$، ولا يُزاح وقفها (حكم المالك ٢٠٢٦-٠٩-١٨)",
            order.get("symbol"), side, REASON_LOSS_ABOVE_CAP, exposure, hard_cap)
        return None
    # `costs_in_stop = False` تصريحٌ لمن بعدنا: التكاليف في الحجم لا في
    # مكان الوقف — فلا يطرحها أحدٌ مرّةً ثانية.
    order["costs_in_stop"] = False
    atom._passed_intact = getattr(atom, "_passed_intact", 0) + 1
    return order
