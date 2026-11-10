"""٥٥٥ — قراءة الأرقام، وحمولة ٥١٣ كما تُنشر فعلًا، وحجم اللوت على الوقف المرسَل.

v1.24.1 (٢٠٢٦-١٠-٠١، ختم `Nq`): نُقلت هذه الدوالّ الأربع من `atom.py` **حرفيًّا**
كي ينزل تحت حدّ المادة 9 (٤٠٠ سطر فعليّ) — بلا سطرٍ جديد في منطقها ولا اسمٍ
متغيّر. و`atom.py` يستوردها بأسمائها نفسها، فلا سلوك جديد.
"""
from __future__ import annotations

import math
from typing import Any

from shared import execution_costs
from shared.pips import to_pips
from shared.trade_setup import MIN_STOP_PIPS_DEFAULT, min_stop_pips, net_ratio

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حكمُ النسبة والوقف يُعاد **عند الإرسال**.
#
# كان الحكمان يُجريان لحظةَ ولادة الإعداد في 405/406/410 على `entry_reference`، ثمّ
# يعيش الإعداد حتّى 1800 ث ويخرج الأمر على سعرٍ آخر — و555 «يقيس ولا يحكم». مقيسٌ
# في التدقيق (orders.db × الجسر): 298 صفقة منفّذة دون 1:3 عند الإرسال، منها 146 دون
# 1:1؛ وأربعة أوامر خرجت بوقف 6.0–9.7 نقطة أساس لأنّ الحدّ قِيس على سعر البناء.
#
# الرقمان **مرآةٌ** لا عيارٌ جديد — مصدرهما الاستراتيجيّات نفسها ولا يُستورد ملفّ
# ذرّةٍ من ذرّةٍ أخرى:
#: `MIN_SETUP_RATIO = 3.0` في 405 (`atom.py:55`) و406 (`:55`) و410 (`:71`) —
#: حكم المالك ٢٠٢٦-٠٩-٢٨: «هدف صفقة لا يقل عن 1/3… اذا تحت 1/3 مرفوضة».
MIN_SETUP_RATIO = 3.0
#: (تاريخ — حتّى ١٠-١٧ كان الحدّ بنقاط الأساس:) `MIN_STOP_BPS` في 405 و406 و410 (`QUANT_NQ_MIN_STOP_BPS`) — ختم المالك «Nq»
#: ٢٠٢٦-١٠-٠١ كان 10؛ ثمّ ٢٠٢٦-١٠-٠٦ 14:50 **3** بختمه «نقاط أساس خليها 3 مو 10 NQ».
#: المفتاح نفسه والافتراض نفسه هنا وهناك، وإلّا رُدّ عند الإرسال ما قبلته الاستراتيجيّة.
#: (اسم السبب `STOP_BELOW_10BPS_AT_SEND` بقي كما هو — عقدٌ تقرؤه الشارة واللوحة.)
#: ٢٠٢٦-١٠-٠٦ 15:4x — **3 للناسداك وحده، و10 للباقي** بختم المالك «NQ»: الحكم الواحد
#: `shared.trade_setup.min_stop_bps(رمز)` هنا وفي الاستراتيجيّات الثلاث. و`MIN_STOP_BPS` العامّ للشارة.
#: ٢٠٢٦-١٠-١٧ (ختم المالك «nq»: «بِب على كلّ السستم، ما في شي اسمه نقاط أساس»): الحدّ بالبِب لكلّ رمز (`shared.trade_setup.min_stop_pips`)،
#: والمسافة بالبِب (`shared.pips`). اسم السبب بقي عقدًا تقرؤه اللوحة (نصّها العربيّ صار «أدنى بِب»).
MIN_STOP_PIPS = MIN_STOP_PIPS_DEFAULT
#: هامشُ فاصلةٍ عائمة — نفسه في 405:489 وفي `_REWARD_EPSILON` بـ`atom.py`.
_SEND_EPSILON = 1e-9


def send_economics(side: str, price: Any, stop: Any, target: Any,
                   spread: Any, symbol: Any = None) -> tuple[str, dict[str, Any]]:
    """حكمُ الأمر على أسعار الإرسال نفسها: (السبب أو "", الأرقام المقيسة).

    ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»). المعادلة هي معادلة الاستراتيجيّات
    حرفًا — `shared.trade_setup.net_ratio(setup, cost)` بكلفة عبورٍ = السبريد
    الكامل (`round_trip_cost(bid, ask)` في 405:470 · 406:483 · 410:430):

        صافي = (العائد − السبريد) ÷ (المخاطرة + السبريد)

    والفرق الوحيد أنّ المرجع هنا **سعر الإرسال** (`reference_price` الذي يخرج مع
    الأمر) لا سعر البناء، والسبريد سبريدُ ٥١٣ الذي حُجّم عليه هذا الأمر نفسه.
    و`net_ratio` تقيس بالقيمة المطلقة، فالجهة تُفحص قبلها: هدفٌ بلغه السعر أو
    تجاوزه عائدُه صفرٌ ونسبتُه صفر — لا يُقرأ مسافةً موجبة على الجهة الخطأ.
    """
    ref = _number(price)
    sl = _number(stop)
    tp = _number(target)
    cost = max(0.0, _number(spread) or 0.0)
    floor_pips = min_stop_pips(symbol)
    view: dict[str, Any] = {"price": ref, "stop": sl, "take_profit": tp,
                            "spread": cost, "min_ratio": MIN_SETUP_RATIO,
                            "min_stop_pips": floor_pips}
    if ref is None or ref <= 0.0 or sl is None or tp is None:
        view.update(net_ratio=None, stop_pips=None)
        return "RR_BELOW_MIN_AT_SEND", view
    buy = str(side or "").strip().lower() == "buy"
    risk = (ref - sl) if buy else (sl - ref)
    reward = (tp - ref) if buy else (ref - tp)
    stop_pips = to_pips(ref - sl, symbol)
    ratio = (net_ratio({"entry_reference": ref, "invalidation_price": sl,
                        "target_price": tp}, cost)
             if risk > 0.0 and reward > 0.0 else 0.0)
    view.update(net_ratio=round(ratio, 4), stop_pips=round(stop_pips, 4))
    # الترتيب ترتيب 405:487-494 نفسه: الوقف أوّلًا ثمّ النسبة.
    if stop_pips + _SEND_EPSILON < floor_pips:
        return "STOP_BELOW_10BPS_AT_SEND", view
    if ratio + _SEND_EPSILON < MIN_SETUP_RATIO:
        return "RR_BELOW_MIN_AT_SEND", view
    return "", view


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _size_view(payload: dict[str, Any]) -> dict[str, Any]:
    """حمولة الحجم كما ينشرها 513 فعلًا — أرقامه كلّها تحت `metadata`.

    ٢٠٢٦-٠٩-٠٩ (مقيس على الحيّ بعد أوّل إقلاع نظيف): وصل القرار المُوافَق
    إلى هنا أخيرًا (`467 passed=5`) فسقط على `NO_EXECUTABLE_VOLUME`. والسبب
    ليس صفر حجم — بل أنّ 513 ينشر (`513/atom.py:296-307`):

        {"symbol":…, "status":"OK", "approved":true,
         "metadata": {"lot": 0.3, "price": 52774.1, "stop_distance": 263.87,
                      "buy_lot": null, "buy_stop": null, "max_trade_loss": 100.0, …}}

    بينما كانت هذه الذرّة تقرأ `buy_lot` و`lot` و`close` و`default_distance`
    **من المستوى الأعلى** — فثلاث فجوات أسماء لا واحدة: الغلاف (`metadata`)،
    والسعر (`price` لا `close`)، والمسافة (`stop_distance` لا
    `default_distance`).

    والدواء من عادة المشروع نفسه: 513 يفكّ غلاف ناشره بالسطر ذاته
    (`513/atom.py:160`). فتُفرَد `metadata` فوق المستوى الأعلى — أرقام الناشر
    تعلو لأنّها الموضع الذي يكتب فيه — ويبقى الشكل المسطَّح مقبولًا فلا ينكسر
    ناشرٌ آخر يرسل مسطَّحًا.

    يمدّ درس [[side-field-broke-the-order-link]]: **اقرأ حمولة الناشر، لا
    الوثيقة ولا الحدس.**
    """
    view = dict(payload)
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        for key, value in meta.items():
            if value is not None or key not in view:
                view[key] = value
    return view


def _lot_for_stop(size: dict[str, Any], distance: float) -> float | None:
    """حجمُ اللوت من مسافة الوقف **التي ستُرسَل فعلًا**.

    🔴 ٢٠٢٦-٠٩-١٨ (ختم NQ) — أمر المالك: «الإصلاح الجذريّ أن يحجّم ٥١٣
    على وقف التحليل».

    ٥١٣ يحجّم على وقفه هو (عيار ٥٢٣ أو نسبته الافتراضيّة)، ثمّ تستبدل هذه
    الذرّةُ الوقفَ بإبطال التحليل **ولا تعيد حساب الحجم** — فيخرج أمرٌ
    حجمُه من وقفٍ ووقفُه من آخر. المقيس على التذكرة 1943171698: حجّم ٥١٣
    على 5.81$ فأعطى 0.17 لوت، وأُرسل وقفٌ مسافته 0.36$ — أي مخاطرةٌ
    فعليّة 6.11$ مقابل ميزانيّةٍ معلَنة 100$. وعلى ١٩٧ أمرًا وصلت الوسيط:
    **٥٦ فقط (٢٨٫٤٪) ضمن ±٢٠٪ من المئة**، والمدى من 0.20$ إلى 218.96$.

    ولا يُعالَج عند ٥٥١ ولا ٥٨٤: كلاهما بعد حارس الهامش ٥٨٥، فحجمٌ يُرفع
    هناك لا يُفحص هامشه. فيُعاد الحساب هنا — قبل الحارس — بمعاملات ٥١٣
    نفسها التي يمرّرها لهذا الغرض بالذات (`513/atom.py:352-368`).

    والمعادلة هي معادلته حرفًا: الخسارة الواقعة = اللوت × (المسافة +
    السبريد + احتياطي الانزلاق) × قيمة وحدة السعر + العمولة. والتقريب
    لأسفل دائمًا كي لا تُتجاوز الميزانيّة.
    """
    risk_amount = _number(size.get("risk_amount")) or _number(size.get("max_trade_loss"))
    tick_value = _number(size.get("tick_value"))
    tick_size = _number(size.get("tick_size"))
    if not risk_amount or not tick_value or not tick_size or distance <= 0.0:
        return None
    # 🔴 ٢٠٢٦-٠٩-١٨ (أمر المالك «ليش رقم خسارة أقلّ من مطلوب وهدف مو صحيح»)
    #
    # كانت: المسافة + سبريدٌ كامل + احتياطيّ انزلاقٍ **ضعفَي** السبريد —
    # أي ثلاثة أضعاف السبريد تُحجَز من الميزانيّة. والمقيس على ثلاث صفقات
    # أُغلقت في الساعة نفسها:
    #
    #   USTEC   لوت 3.6  والمطلوب 5.5  ⟹ خسارة  64.80$ وهدف 230$
    #   BTCUSD  لوت 0.59 والمطلوب 0.68 ⟹ خسارة  85.59$
    #   US30    لوت 2.6  والمطلوب 3.5  ⟹ خسارة  72.80$ وهدف 295$
    #
    # والمحجوز على ناسداك 9.78 بينما **التجاوز الفعليّ وقع 0.90** — حجزٌ
    # بعشرة أضعاف ما دُفع. فالخسارة تقلّ عن مئة المالك والهدف عن ثلاثمئته،
    # وكلاهما ليس عن تحفّظٍ بل عن رقمٍ مضروبٍ في ثلاثة بلا سند.
    #
    # والصواب سبريدٌ **كامل** لا أكثر، ومعناه بنيويّ لا تقديريّ: نصفٌ
    # يُدفع عند الدخول (المرجع منتصف السوق، مقيسٌ على ٣٢٦ أمرًا) ونصفٌ
    # عند الخروج على الجهة المقابلة. وهي القسمة نفسها التي تقيس بها ٥٥٢
    # النسبة منذ اليوم — فالحجم والنسبة على مسطرةٍ واحدة.
    #
    # والاحتياطي المضاعف يسقط: ذيلُ الانزلاق يحرسه ٥٨٤ بأرضيّته المقيسة
    # (`execution_costs.minimum_stop_distance`) لا بتضخيم كلّ حجم.
    spread_used = _number(size.get("spread")) or 0.0
    # ٢٠٢٦-٠٩-١٨ — السبريد المستعمل يُسجَّل ليُقرأ لا ليُستنتج. مقيسٌ اليوم:
    # لوتُ بتكوينٍ (1.01) يقتضي تكلفةً 12.15 بينما سجلّ التِكّات يقول 5.00
    # ثابتًا في خمس عشرة تِكّة — ولا سبيل للحسم لأنّ السجلّ لا يرجع إلى
    # لحظة البناء (٢٥ صفًّا فقط). فاستنتاجُ السبريد بالقسمة العكسيّة يخلط
    # ثلاثة مجاهيل، وقراءتُه من مصدره تحسم بسطر.
    size["_spread_used"] = spread_used
    # ٢٠٢٦-١٠-٢٣ (ورقة «خطوط حمراء» المختومة، القانونان 2–3): «السبريد والعمولة وانزلاقٌ متوقّع تُحسب كلّها داخل الوقف» — وكان
    # الانزلاق غائبًا هنا (حاضرًا عند ٥٥١ وحده). كلفة العبور المتوقّعة من الجدول الواحد `shared/execution_costs.crossing_cost`:
    # لرمزٍ له سجلّ انزلاقه المقيس (والسبريد داخله)، ولغيره أسوأ المقيس فوق السبريد. ويُحجز الأكبر منها ومن السبريد — فلا
    # يتغيّر لوتٌ كان سبريده يغطّي انزلاقه، ويصغر قليلًا لوت ما لا سجلّ له. والوقف لا يُمسّ: اللوت وحده يُقصّ.
    price = _number(size.get("close")) or _number(size.get("reference_price")) or _number(size.get("price")) or 0.0
    cost_used = max(spread_used, execution_costs.crossing_cost(size.get("symbol"), price, spread_used))
    size["_cost_used"] = cost_used
    effective = distance + cost_used
    denom = effective * tick_value / tick_size \
        + (_number(size.get("commission_per_lot")) or 0.0)
    if denom <= 0.0:
        return None
    step = _number(size.get("volume_step")) or 0.01
    raw = risk_amount / denom
    lot = math.floor(raw / step + 1e-9) * step
    minimum = _number(size.get("volume_min")) or step
    maximum = _number(size.get("volume_max"))
    if maximum is not None and maximum > 0.0:
        lot = min(lot, maximum)
    if lot < minimum - 1e-12:
        return None
    return round(lot, 8)
