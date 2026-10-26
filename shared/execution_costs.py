"""تكلفة عبور السوق — مقيسةٌ من الوسيط لكلّ رمز، لا نسبةً عمياء من السعر.

⚖️ ٢٠٢٦-٠٩-١٨ — حكم المالك: «مو الإكسبرت عم يزوّدك؟ بدك تخرج عن الأصول».

وكان في المنصّة ثلاثة أرقامٍ عمياء تحكم الرموز كلّها بنسبةٍ واحدة من السعر:

    551  EXCESS_ALLOWANCE_FRAC = 0.0001    ·  TAIL_SLIPPAGE_FRAC = 0.00035
    584  EXECUTION_NOISE_FRAC  = 0.000225

ونسبةٌ واحدة من السعر لا تعني شيئًا واحدًا: العيار الأخير يعطي حدًّا أدنى
للوقف يساوي **3.4 أضعاف** سبريد البتكوين و**8.1 أضعاف** سبريد الذهب. فالرقم
الواحد ليس عدلًا بين الرموز، هو عمًى عنها.

وكلّ ما يلزم يصل من الإكسبرت أصلًا:

    السبريد          من التِكّة الحيّة (ask − bid)
    انزلاق الدخول    مرجع البناء ⟵ سعر التنفيذ، من `decisions.db`
    انزلاق الخروج    الوقف المرسَل ⟵ سعر الإغلاق على SL
    stops_level      حدّ الوسيط نفسه، من `symbol_specs_v2`

فلا «نقطة» في هذا الملفّ ولا رقمَ مقدَّر. ما هنا مشتقٌّ من سجلّ التنفيذ،
وما ليس له سجلٌّ يقع على أسوأ ما قِيس — لا على تخمين.
"""
from __future__ import annotations

from typing import Any

#: عتبة الاشتقاق: دون عشرين عيّنة لا يُبنى عيار.
MIN_SAMPLES = 20

#: انزلاق العبور لكلّ رمز — (دخول، خروج) كنسبةٍ من السعر.
#:
#: مئينان لكلّ رمز، ولكلٍّ استعماله:
#:   `MEDIAN` — ما يقع في نصف الحالات. يُستعمل في **تحجيم اللوت**، لأنّ
#:              الحجز لما لا يقع يأكل الميزانيّة (مقيس: 22.78$ من مئة).
#:   `P80`    — ما لا يتجاوَز في أربعٍ من خمس. يُستعمل في **الحدّ الأدنى
#:              لمسافة الوقف**، لأنّ وقفًا لا ينجو من الانزلاق ليس وقفًا.
#:
#: والوسيط سالبٌ في ثلاثة رموزٍ من أربعة — أي أنّ الانزلاق لصالحنا في نصف
#: الحالات — وما كان لصالحنا يُصفَّر ولا يُحجز له.
SLIPPAGE_MEDIAN = {
    # الرمز: (دخول، خروج)              العيّنات    المقيس الخام
    "BTCUSD": (0.0000327, 0.0000000),   # 51 + 44   ‎+2.50‎ · ‎-5.51‎
    "USTEC":  (0.0000103, 0.0000000),   # 17 + 11   ‎+0.30‎ · ‎-47.40‎
    "XAUUSD": (0.0000000, 0.0000000),   # 26 + 22   ‎-0.02‎ · ‎-4.37‎
}

SLIPPAGE_P80 = {
    "BTCUSD": (0.000151, 0.000088),     # 51 + 44   ‎+11.54‎ · ‎+6.74‎
    "USTEC":  (0.000031, 0.000004),     # 17 + 11   ‎+0.90‎ · ‎+0.11‎
    "XAUUSD": (0.000053, 0.000024),     # 26 + 22   ‎+0.23‎ · ‎+0.10‎
}

#: عمولة الدورة الكاملة لكلّ لوت — من `trade_events_v2` في جسر ميتاتريدر.
#: المسجَّل عمولةُ اتّجاهٍ واحد ومثلها عند الفتح، فالدورة ضعفُه.
COMMISSION_ROUNDTRIP = {
    "XAUUSD": 7.0,    # ‎-3.53‎$/لوت في 25 صفقة · ومواصفات الوسيط: 3.5$ للعقد
    "EURUSD": 7.0,    # ‎-3.50‎$/لوت
    "USTEC":  0.0,    # 15 صفقة، صفرٌ في كلّها
    "BTCUSD": 0.0,    # 127 صفقة، صفرٌ في كلّها
    # ٢٠٢٦-٠٩-٢٤ (ختم المالك «Nq على كلهم») — من المصدر نفسه، وكانا يقعان على
    # ٧$/لوت من ٥١٣ فيُصغَّر لوتُهما بعمولةٍ لا يأخذها الوسيط:
    "US30":   0.0,    # 40 حدثًا و74.2 لوت، صفرٌ في كلّها
    "US500":  0.0,    # 4 أحداث و11.6 لوت، صفرٌ في كلّها
}


def _key(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def _worst(table: dict) -> tuple[float, float]:
    """أسوأ ما قِيس — سقفُ المقيس لا رقمٌ من عندنا."""
    return (max((e for e, _ in table.values()), default=0.0),
            max((x for _, x in table.values()), default=0.0))


def slippage_fracs(symbol: Any, *, p80: bool = False) -> tuple[float, float]:
    """نسبتا انزلاق الدخول والخروج — من سجلّ الرمز، وإلّا أسوأ ما قِيس."""
    table = SLIPPAGE_P80 if p80 else SLIPPAGE_MEDIAN
    return table.get(_key(symbol), _worst(table))


def has_measured(symbol: Any) -> bool:
    """هل لهذا الرمز سجلٌّ بلغ عتبة الاشتقاق؟"""
    return _key(symbol) in SLIPPAGE_MEDIAN


def commission_roundtrip(symbol: Any, fallback: float = 0.0) -> float:
    """عمولة الدورة لكلّ لوت. رمزٌ بلا سجلٍّ يقع على ما يرسله الإعداد."""
    value = COMMISSION_ROUNDTRIP.get(_key(symbol))
    return fallback if value is None else value


def crossing_cost(symbol: Any, price: float, spread: float = 0.0,
                  *, p80: bool = False) -> float:
    """تكلفة عبور السوق ذهابًا وإيابًا، بوحدة سعر الرمز.

    السبريد يُمرَّر من التِكّة الحيّة حين يتوفّر. وهو **لا يُضاف** فوق
    الانزلاق المقيس لرمزٍ له سجلّ: ذلك الانزلاق مقيسٌ من الأسعار الفعليّة
    فالسبريد داخلٌ فيه، وإضافته تحسبه مرّتين — وهو العطب الذي كان يأكل
    اللوت (مقيس: المخاطرة 22.78$ من ميزانيّة مئة).
    """
    try:
        reference = abs(float(price))
    except (TypeError, ValueError):
        return 0.0
    if reference <= 0.0:
        return 0.0
    entry_frac, exit_frac = slippage_fracs(symbol, p80=p80)
    cost = reference * (entry_frac + exit_frac)
    if not has_measured(symbol):
        try:
            cost += max(0.0, float(spread))
        except (TypeError, ValueError):
            pass
    return cost


def minimum_stop_distance(symbol: Any, price: float, spread: float = 0.0,
                          *, stops_level_distance: float = 0.0) -> float:
    """أضيق وقفٍ له معنى — بوحدة سعر الرمز.

    وقفٌ أضيق من تكلفة عبوره يُضرَب بالتكلفة وحدها قبل أن يتحرّك السوق.
    فالحدّ هو تكلفة العبور عند المئين الثمانين، ولا يقلّ عن حدّ الوسيط
    نفسه (`stops_level`/`freeze_level` مضروبَين في `point` عند المنادي).

    ولا مضاعفَ فوق ذلك: المضاعف رقمٌ من الرأس، والمئين الثمانون مقيس.
    """
    floor = crossing_cost(symbol, price, spread, p80=True)
    try:
        broker = abs(float(stops_level_distance))
    except (TypeError, ValueError):
        broker = 0.0
    return max(floor, broker)
