from __future__ import annotations

import math
import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared import execution_costs
from shared.structure_exits import LADDER_EVENT, StructureBook
# ٢٠٢٦-١٠-٠٥ (ختم المالك «nq اعتمدناها»): الإدارة على مستويات التحليل — الخطّة والتتبّع
# البنيويّ في وحدةٍ شقيقة، وتطبيقُ المرحلة (إغلاقها ثمّ نقل وقفها) في أخرى يمرّ بها الطريقان؛
# نُقل حرفيًّا لحدّ الأربع مئة سطر، وثوابت الأمر معه تُستورد هنا فيبقى سطح الوحدة كما كان.
import partial_levels
import stage_apply
from stage_apply import EVENT_OUT, ACTION_PARTIAL, ACTION_CLOSE, ACTION_MODIFY, REASON_BREAKEVEN
from stage_apply import REASON_PARTIAL, REASON_LAST_LOT, SIDE_BUY, SIDE_SELL, _VOL_DP, _R_DP, _PRICE_DP
# ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا»): كانت الذرّة تتتبّع كلّ مركزٍ
# وتبني له خطّة أثلاثٍ ومستويات — ومعه مركز المالك اليدويّ — فتطلب إغلاق أجزائه ونقل وقفه، ويردّها ٥٧٥ لأنّه ليس للمنظومة.
# الآن تُسقط صفقات المالك من صورة المراكز عند دخولها، بالتمييز الواحد في `shared/owner_trades.py`، فلا تتبّع ولا خطّة ولا
# اسمَ لها في قائمة ٥٧٢.
from shared import owner_trades

ATOM_VERSION = "2.18.0"

EVENT_IN = "platform.positions.state"
EVENT_SPECS = "market.symbol_specs"
#: 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك) — «بس لمس رقم يتنفّذ ماركت · خلّيه يرصد
#: التِكّة».
#:
#: كان الرصدُ من دورة المراكز وحدها: `current_price` يصل مع كلّ دورةٍ من
#: ٦٠٩، فسعرٌ يلمس هدفه بين دورتين ثمّ يرتدّ **لا يُرى**. والمرحلة تنتظر
#: دورةً أخرى قد لا يعود فيها السعر.
#:
#: ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): التِكّة من **ميتاتريدر** لا من
#: سي‑تريدر، وبسعر جهة المركز: العرض (bid) للشراء والطلب (ask) للبيع.
#:
#: كانت من سي‑تريدر بالمنتصف (`623:120-125` يضع `price = mid`) بحكم ٢٠٢٦-٠٩-١٦
#: «ميتاتريدر تنفيذ فقط، كلّ أصول من سي‑تريدر». لكنّ الإغلاق الجزئيّ ونقل
#: الوقف **تنفيذ**: يُغلق بسعر ميتاتريدر ويُحكم على الوقف بسعر ميتاتريدر. فكان
#: التقدّم يُقاس بسعرٍ والتنفيذ يقع بآخر. مقيس على US30 التذكرة 1976793832
#: (2026-09-30): الدخول 51356.0 والهدف 51359.25 (3.25 نقطة) والوقف 85.9 نقطة؛
#: بلغ منتصفُ سي‑تريدر ثلثَ الهدف فأُغلق 0.3 لوت عند **51354.3 بخسارة −0.51$**،
#: ونُقل الوقف إلى 51356.0 فردّه الوسيط `10016` (العرض تحت الدخول)، ثمّ
#: المرحلة الثانية الشيء نفسه. ودورة ٦٠٩ نفسها كانت تحمل سعر جهة المركز
#: (مقيس على 905 مركزًا عند أوّل ظهور: الشراء ≈ الدخول − السبريد، والبيع ≈
#: الدخول + السبريد) — فصار المساران بمسطرةٍ واحدة. وتحليلُ السوق باقٍ على
#: سي‑تريدر كما حكم المالك؛ هذا حكمٌ على التنفيذ لا على السوق.
EVENT_TICK = "feed.mt5.tick"

#: يُنطق بموضع الوقف كما يراه المالك — «الهدف الأوّل» لا مضاعفَ مخاطرةٍ
#: يحتاج حسابًا. (`%g` يأخذ نسبة الطريق مضروبةً في عدد المراحل.)
REASON_LOCK = "STOP_LOCKED_AT_TARGET_%g"

# ⚖️ خطّة المالك ٢٠٢٦-٠٩-١٦ (ختم `NQ`) حرفيًّا: «حط هدف ٣ أضعاف حجم ستوب.
# هدف أوّل إغلاق 0.33 من حجم عقد. هدف ثاني 50% إغلاق من حجم عقد. هدف ٣
# إغلاق كامل. بعد هدف أوّل ستوب على سعر التعادل. بعد الهدف ثاني ستوب على
# ضعف حجم مخاطرة 1/1».
#
# الهدف الكلّي ٣ أضعاف الوقف، ويُقسم ثلاثًا بالتساوي — فكل مرحلة تبعد
# مخاطرةً واحدة عن سابقتها:
#
#     المرحلة ١ عند 1R من الدخول →  يُغلق 33٪  ·  الوقف إلى سعر الدخول (0R)
#     المرحلة ٢ عند 2R           →  يُغلق 50٪  ·  الوقف إلى +2R
#     المرحلة ٣ عند 3R           →  يُغلق الباقي كاملًا
#
# ⚖️ ٢٠٢٦-٠٩-١٨ — تصحيح المالك، وهي المرّة السابعة التي يملي فيها هذه
# المواصفة: «بعد الهدف ثاني ستوب على ضعف حجم مخاطرة».
#
# وكان هنا تأويلٌ كتبتُه أنا: «معنى ضعف حجم المخاطرة أنّ الوقف ينتقل من
# `دخول − 1R` إلى `دخول + 1R` — مسافةُ نقلٍ ضعفُ المخاطرة». فجعلتُ الضِّعف
# **مسافةَ نقل** بدل أن يكون **موضعَ الوقف**، وأنزلتُ القفل من 2R إلى 1R.
#
# وظاهر لفظه يقرأ الموضع لا المسافة، بدليل البند الذي قبله مباشرةً:
# «بعد هدف أوّل ستوب **على سعر التعادل**» — «على» موضعٌ لا مسافة. فما
# بعدها «على ضعف حجم مخاطرة» = الوقف عند `دخول ± 2R`.
#
# ⚠️ وأثره المعلوم: الهدف الثاني نفسه عند 2R، فالوقف يلتصق بالسعر ساعةَ
# بلوغه — والثلث الأخير يخرج بأوّل ارتداد، بربحٍ مضمون قدره ضعف المخاطرة،
# ونادرًا ما يبلغ 3R. هذا مقيسٌ لا اعتراض، والعيار عياره.
#
# ⚖️ ٢٠٢٦-٠٩-١٧ — تصحيح المالك بنصّه: «عم يسكر **ثلث عقد** على هدف أوّل
# و**نص باقي من عقد** على هدف ثاني».
#
# وكان هنا تفسيرٌ معاكس كتبتُه أنا: «النسب كلّها من الحجم الأصليّ لا من
# المتبقّي، وإلّا صارت الخمسون الثانية نصفَ ما بقي لا نصف العقد». وهو
# **عكس ما أراده**، وكلفتُه أنّ الهدف الثالث — وهو الأكبر (٣R) — يُحرَم
# من حصّته:
#
#     بالتفسير القديم (من الأصليّ):  0.33 ثمّ 0.50  ⇒ يبقى للثالث **17٪**
#     بأمر المالك (نصف الباقي)   :  1/3  ثمّ 1/3   ⇒ يبقى للثالث **33٪**
#
# فالنسب تُقاس الآن من **المتبقّي** لا من الأصليّ، وحاصلها الثلث الثلث
# الثلث تمامًا كما نطق بها:
#     الأوّل  : ثلث المتبقّي (1.0)    = 0.333 من العقد · يبقى 0.667
#     الثاني  : نصف المتبقّي (0.667)  = 0.333 من العقد · يبقى 0.333
#     الثالث  : الباقي كلّه          = 0.333 من العقد
#
# (نسبةُ الهدف · ما يُغلق من **المتبقّي** · مضاعفُ R الذي يُنقل إليه الوقف)
#
# 🔴 ٢٠٢٦-٠٩-١٨ — أمر المالك بنصّه، وهو تصحيحٌ لما كان منفَّذًا:
#
#   «صفقة ضربت هدف أوّل: انتقل ستوب على تأمين ثمّ أُغلق جزء. ثمّ مشت
#    الصفقة إلى هدف ثانٍ: انتقل ستوب من التأمين إلى **هدف أوّل** وأُغلق
#    جزء من لوت. صفقة ماشية إلى هدف ثالث. هي خطّتي ما في غير هيك،
#    نفّذها، ما بصير تتأثّر ولا تكذب.»
#
# وكان `lock` الثاني **بمضاعف المخاطرة** (`2.0`) بينما `reached` بنسبة
# الطريق إلى الهدف — وحدتان مختلفتان في صفٍّ واحد. وبنسبة 1:3 يقع الهدف
# الثاني عند 2R، فيوضع الوقف عند 2R أيضًا: **الوقف على السعر الحاليّ
# بالضبط**، فيُغلق المركز بأوّل ارتدادٍ بنقطة. ذاك ما خسّر المالك.
#
# فصار `lock` بوحدة `reached` نفسها — نسبةً من الطريق إلى الهدف:
#   0.0  = سعر الدخول (التأمين)
#   1/3  = **الهدف الأوّل** حرفيًّا، كما أمر
# ويصحّ بأيّ نسبة ر:م لا بـ1:3 وحدها، لأنّ الطرفين يُقاسان بمسطرةٍ واحدة.
#
# (نسبةُ الهدف · ما يُغلق من المتبقّي · الموضعُ الذي يُنقل إليه الوقف)
STAGES = ((1.0 / 3.0, 1.0 / 3.0, 0.0),
          (2.0 / 3.0, 0.50, 1.0 / 3.0),
          (1.0, 1.0, None))


REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_POSITIONS = "NO_POSITIONS_YET"

#: 🔴 ٢٠٢٦-٠٩-١٨ — هامش فاصلةٍ عائمة عند مقارنة التقدّم بالمرحلة، لا عيار.
#: كشفه فحصُ المالك («خدهم على جنب، مرّرلهم صفقات شوف كيف راح يتعاملو»):
#: مُرّرت صفقة الذهب 1944615686 بأرقامها على هذه الذرّة مرحلةً مرحلةً،
#: فلم تتحرّك عند الهدف الأوّل إطلاقًا، وفعلت عند الثاني ما كان عليها فعلُه
#: عند الأوّل — **متأخّرةً مرحلةً كاملة**. والسبب:
#:
#:     progress = 0.33333333333330223
#:     reached  = 0.3333333333333333     ⟹ الفرق  -3.1e-14
#:
#: أي ثلاثة أجزاء من مئة تريليون تمنع إغلاق ثلث العقد ونقلَ الوقف. وسعرٌ
#: يلمس هدفه بالضبط ثمّ يرتدّ كان يمرّ بلا أن يُؤمَّن منه شيء.
_PROGRESS_EPS = 1e-9
#: هامشُ فاصلةٍ عائمة عند مقارنة حجمين — أصغرُ خطوةِ لوتٍ في السوق `0.01`،
#: فهامشٌ بعشر ميكرو لا يبتلع نقصانًا حقيقيًّا ولا يصدّق ضجيج التقريب.
_VOL_EPS = 1e-6
#: كم **دورةَ مراكز** ينتظر الوقفُ المؤجَّل نقصانَ الحجم قبل أن يُحتجَز.
#:
#: بالدورات لا بالثواني: هذه الذرّة لا تشترك في `SYS_SECOND` ولا ساعةَ
#: لها، ومهلةٌ بالثواني على ساعةٍ لا تتقدّم تبقى صفرًا أبدًا — عيارٌ
#: يبدو حارسًا ولا يحرس. والدورة هي نبضُها الحقيقيّ.
#:
#: والرقم مشتقٌّ من المقيس: أطولُ فجوةٍ بين إرسال إغلاقٍ ووصول نقصانه على
#: المنصّة يوم ٢٠٢٦-٠٩-١٩ كانت ثانيةً واحدة (‎18:41:09‎ الأمر ⟵ ‎18:41:10‎
#: الإغلاق)، ودورةُ المراكز تصل كلّ ثانيتين تقريبًا. فخمس عشرة دورةً نحو
#: ثلاثين ثانية — وما لم يقع فيها لن يقع.
_PENDING_STOP_CYCLES = 15
#: ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): هامشُ فاصلةٍ عائمة عند مقارنة الهدف
#: بكلفة العبور (بوحدة السعر).
_COST_EPS = 1e-9


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._at_r = 1.0
        self._fraction = 0.5
        self._min_lot = 0.01
        self._tracked: dict[str, dict[str, Any]] = {}
        self._seen = 0
        self._emitted = 0
        self._restored = 0
        self._indivisible = 0
        self._skipped_close = 0
        self._last_skip = "-"
        # ٢٠٢٦-٠٩-١٩ — الوقفُ يتأخّر عن الإغلاق عمدًا، فتُعدّ أطواره
        # الثلاثة: أُجِّل · خرج بعد أن نقص الحجم · احتُجز لأنّ الجزء لم يُغلق.
        # والثالث هو الذي يجب أن يُرى: صفقةٌ لم تُقبض حصّتُها ولم تُؤمَّن.
        self._stop_deferred = 0
        self._stop_after_close = 0
        self._stop_withheld = 0
        self._tick_checks = 0
        self._last_withheld = "-"
        self._now = 0.0
        self._symbol_min: dict[str, float] = {}
        self._symbol_step: dict[str, float] = {}
        self._symbol_vpp: dict[str, float] = {}
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حدّ الوسيط لموضع الوقف، وآخر
        # عرضٍ وطلبٍ من ميتاتريدر لكلّ (حساب، رمز)، وعدّادات ما لم يُرسَل ولماذا.
        self._symbol_point: dict[str, float] = {}
        self._symbol_stops: dict[str, float] = {}
        self._quotes: dict[tuple[str, str], tuple[float, float]] = {}
        self._stop_invalid = 0
        self._last_invalid = "-"
        self._stop_kept = 0          # ٢٠٢٦-١٠-٠٨: وقفٌ لم يُرسَل لأنّ القائم مثلُه أو أشدّ
        self._last_kept = "-"
        self._single_target = 0
        self._last_single = "-"
        self._cost_unknown = 0
        # ٢٠٢٦-١٠-٠٥: سلّم البنية (٢٠١) — منه مستويات الطريق وقمم الربع ساعة للتتبّع.
        self._book = StructureBook()
        self._level_plans = 0
        self._plan_timeouts = 0
        self._trails = 0
        self._plan_published: list[str] | None = None

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._at_r = float(cfg["partial_at_r"])
        self._fraction = float(cfg["partial_fraction"])
        self._min_lot = float(cfg["min_partial_lot"])
        context.subscribe(EVENT_IN, self._on_positions)
        context.subscribe(EVENT_SPECS, self._on_specs)
        context.subscribe(EVENT_TICK, self._on_tick)
        context.subscribe(LADDER_EVENT, self._on_ladder)

    async def _on_ladder(self, payload: dict[str, Any]) -> None:
        self._book.on_ladder(payload)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_specs(self, payload: dict[str, Any]) -> None:
        """حدود اللوت لكل رمز كما يعلنها الوسيط.

        ⚖️ ٢٠٢٦-٠٩-١٦ — تصحيح المالك: «بروكر أصغر شي عنده 0.01، تحت هيك ما
        يقبل». والمقيس من مواصفات الوسيط أنّ الحدّ **ليس واحدًا**:

            BTCUSD · XAUUSD · EURUSD · GBPUSD    أصغر لوت = 0.01
            USTEC  · US30   · US500              أصغر لوت = 0.1   ← عشرة أضعاف

        وهذه الذرّة كانت تحمل رقمًا واحدًا (`min_partial_lot: 0.01`) لكل
        الرموز. فنصيبٌ قدره 0.09 على ناسداك كان يُعَدّ صالحًا ويُرسَل،
        والوسيط يردّه — إغلاقٌ جزئيّ يضيع بلا أثر ظاهر. والخطوة كذلك: حجمٌ
        ليس من مضاعفات `volume_step` يُرفض ولو تجاوز الأدنى.

        والإعداد يبقى أرضيّةً: يُؤخذ الأكبر منه ومن حدّ الوسيط، فلا يفتح
        غيابُ المواصفة بابًا أوسع ممّا سمح به المالك.
        """
        if not isinstance(payload, dict):
            return
        # الشكل مقروءٌ من ناشره لا مفترَض: `513._on_specs` يقرأ
        # `payload["symbols"]` قائمةَ صفوف، كل صفّ فيه `symbol` وحدوده.
        rows = payload.get("symbols")
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            minimum = _to_float(row.get("volume_min"))
            step = _to_float(row.get("volume_step"))
            if minimum is not None and minimum > 0.0:
                self._symbol_min[symbol] = minimum
            if step is not None and step > 0.0:
                self._symbol_step[symbol] = step
            # قيمة وحدة السعر — بها تُترجَم عمولة الدورة إلى مسافة، فيصير
            # «التعادل» صفرًا صافيًا لا صفرًا ورقيًّا (أمر المالك ٢٠٢٦-٠٩-١٨).
            tick_value = _to_float(row.get("tick_value"))
            tick_size = _to_float(row.get("tick_size"))
            if tick_value and tick_size and tick_size > 0.0:
                self._symbol_vpp[symbol] = tick_value / tick_size
            # ٢٠٢٦-١٠-٠٢: النقطة وحدّا الوسيط (`stops_level` · `freeze_level`) —
            # بها يُعرف قبل الإرسال أنّ الوقف في جهته الصحيحة من سعر التنفيذ.
            point = _to_float(row.get("point")) or tick_size
            if point and point > 0.0:
                self._symbol_point[symbol] = point
            levels = [_to_float(row.get(name)) for name in ("stops_level", "freeze_level")]
            self._symbol_stops[symbol] = max([v for v in levels if v is not None and v > 0.0],
                                             default=0.0)

    def _stop_valid(self, symbol: Any, side: str, stop: Any, price: Any) -> bool:
        """هل يقبل الوسيط هذا الوقف الآن؟ — قبل الإرسال لا بعد الردّ.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): وقف الشراء تحت العرض، ووقف البيع
        فوق الطلب، بحدّ الوسيط (`max(stops_level, freeze_level) × point`) ونقطةٍ
        واحدة فوقه (لا يساوي السعر). مقيسٌ في جدول الأوامر: 30 `MODIFY_SL` ردّها
        الوسيط `RETCODE_10016` — وقفٌ في الجهة الخطأ من السعر، وكلّ ردٍّ منها
        كان يجمّد الدخولات خمس عشرة دقيقة عند ٦٠١. سعرٌ مجهول = لا إرسال.
        """
        stop_value = _to_float(stop)
        current = _to_float(price)
        if stop_value is None or stop_value <= 0.0 or current is None or current <= 0.0:
            return False
        name = str(symbol or "").strip().upper()
        point = self._symbol_point.get(name, 0.0)
        gap = (self._symbol_stops.get(name, 0.0) + 1.0) * point
        room = (current - stop_value) if side == SIDE_BUY else (stop_value - current)
        if point <= 0.0:
            return room > 0.0
        return room >= gap - point * 1e-6

    def _roundtrip_cost(self, account: Any, symbol: Any) -> float | None:
        """كلفة الدورة بوحدة السعر: سبريد ميتاتريدر الحيّ + عمولة الدورة ÷ قيمة الوحدة.

        `None` حين لا تُعرف: لا سبريد مقيس بعد، أو عمولةٌ بلا قيمة وحدة. والعمولة
        من جدول `shared/execution_costs` نفسه الذي يزيح به هذا الملفّ التعادل —
        والرمز الغائب عنه صفرٌ هناك وهنا (لا جدولان لرقمٍ واحد).
        """
        name = str(symbol or "").strip().upper()
        quote = self._quotes.get((str(account or "").strip(), name))
        if quote is None:
            return None
        cost = quote[1] - quote[0]
        commission = execution_costs.commission_roundtrip(name, 0.0)
        if commission > 0.0:
            vpp = self._symbol_vpp.get(name)
            if not vpp or vpp <= 0.0:
                return None
            cost += commission / vpp
        return cost

    async def _release_stop(self, st: dict[str, Any], pending: dict[str, Any],
                            symbol: Any, side: str, price: Any, ticket: Any) -> None:
        """يُرسل الوقف المؤجَّل إن قبله الوسيط الآن، وإلّا يبقى مؤجَّلًا ويُعدّ."""
        if self._context is None:
            return
        body = pending["body"]
        # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): القائم عند الوسيط مثلُه أو أشدّ ⟸ يبقى القائم ويسقط المؤجَّل.
        kept = stage_apply.held_stop_not_looser(st, body, side)
        if kept is not None:
            self._stop_kept += 1
            self._last_kept = "%s م%d: قائم=%s مطلوب=%s" % (symbol, pending["stage"], *kept)
            self._context.logger.warning(
                "574 %s ticket=%s المرحلة %d: الوقف القائم %s مثلُ المطلوب %s أو أشدّ — "
                "لم يُرسَل (الوقف لا يُوسَّع)", symbol, ticket, pending["stage"], *kept)
            st["pending_stop"] = None
            return
        if not self._stop_valid(symbol, side, body.get("stop_loss"), price):
            if not pending.get("invalid_counted"):
                pending["invalid_counted"] = True
                self._stop_invalid += 1
                self._last_invalid = "%s م%d: وقف=%s والسعر=%s — لم يُرسَل" % (
                    symbol, pending["stage"], body.get("stop_loss"), price)
                self._context.logger.warning(
                    "574 %s ticket=%s المرحلة %d: الوقف %s في غير جهته من سعر التنفيذ %s "
                    "— لم يُرسَل (كان سيُردّ 10016)، ويُعاد فحصه مع كلّ سعر",
                    symbol, ticket, pending["stage"], body.get("stop_loss"), price)
            return
        await self._context.publish(EVENT_OUT, dict(body))
        self._emitted += 1
        if pending.get("after_close"):
            self._stop_after_close += 1
        st["pending_stop"] = None

    def _lot_limits(self, symbol: str) -> tuple[float, float]:
        """(أصغر لوت · خطوته) لهذا الرمز — حدّ الوسيط أوّلًا، والإعداد أرضيّة."""
        name = str(symbol or "").strip().upper()
        minimum = max(self._min_lot, self._symbol_min.get(name, 0.0))
        return minimum, self._symbol_step.get(name, minimum)

    def _track(self, ticket: str, entry: float, stop: float,
               target: float | None, volume: float) -> dict[str, Any]:
        st = self._tracked.get(ticket)
        if st is None:
            risk = abs(entry - stop) if stop and stop > 0.0 else None
            span = abs(target - entry) if target and target > 0.0 else None
            # الحجم الأصليّ يُحفظ مرّة — للاستعادة وللتشخيص وحدهما.
            # والنسب تُقاس من **المتبقّي** بأمر المالك ٢٠٢٦-٠٩-١٧
            # («ثلث عقد ثمّ نص باقي») — انظر `STAGES` أعلاه.
            st = {"risk": risk, "span": span, "entry": entry,
                  "original": volume, "stage": 0, "done": False,
                  "pending_stop": None, "levels": None, "seen_at": time.time()}
            self._tracked[ticket] = st
        return st

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        """التِكّة تفحص المراحل بالسعر اللحظيّ — أمر المالك ٢٠٢٦-٠٩-١٩.

        لا منطقَ جديدًا هنا: تُبنى صورةُ المركز المحفوظة بسعر التِكّة
        ويُستدعى الفحصُ نفسه. فلا يفترق مساران ولا يُنسخ حكم.

        ولا تُحذف المراكز في هذا الطريق (`from_tick`): التِكّة تخصّ رمزًا
        واحدًا، وحذفُ ما ليس فيها يمحو تتبّع كلّ رمزٍ آخر.
        """
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): تِكّة ميتاتريدر بطرفيها، وكلُّ
        # مركزٍ يُقاس بسعر خروجه: العرض للشراء والطلب للبيع — لا المنتصف.
        bid = _to_float(payload.get("bid"))
        ask = _to_float(payload.get("ask"))
        symbol = str(payload.get("symbol") or "").strip()
        account = str(payload.get("account_id") or "").strip()
        if bid is None or ask is None or bid <= 0.0 or ask < bid or not symbol:
            return
        self._quotes[(account, symbol.upper())] = (bid, ask)
        rows = [dict(st["pos"], current_price=(bid if st["pos"].get("side") == SIDE_BUY else ask))
                for st in self._tracked.values()
                if st.get("pos") and not st.get("done")
                and str(st["pos"].get("symbol") or "").strip() == symbol
                and (not account or not str(st["pos"].get("account_id") or "").strip()
                     or str(st["pos"].get("account_id")).strip() == account)]
        if not rows:
            return
        self._tick_checks += 1
        await self._on_positions({"positions": rows}, from_tick=True)

    async def _on_positions(self, payload: dict[str, Any], *,
                            from_tick: bool = False) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        positions = payload.get("positions")
        if not isinstance(positions, list):
            return
        positions = owner_trades.system_rows(positions)   # ٢٠٢٦-١٠-٢٦: صفقة المالك لا تُتتبّع ولا تُقسَّم ولا يُنقل وقفها
        if not from_tick:
            self._seen += 1
        live: set[str] = set()
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            ticket = pos.get("ticket")
            side = str(pos.get("side", ""))
            entry = _to_float(pos.get("entry_price"))
            current = _to_float(pos.get("current_price"))
            stop = _to_float(pos.get("stop_loss"))
            volume = _to_float(pos.get("volume"))
            symbol = pos.get("symbol")
            if ticket is None or entry is None or current is None or volume is None \
                    or side not in (SIDE_BUY, SIDE_SELL):
                continue
            key = str(ticket)
            live.add(key)
            target = _to_float(pos.get("take_profit"))
            st = self._track(key, entry, stop if stop is not None else 0.0,
                             target, volume)
            # صورةُ المركز تُحفظ من دورة ٦٠٩ وحدها — هي المصدر الموثوق
            # للهويّة والحجم. والتِكّة تستعيرها وتبدّل السعر وحده.
            if not from_tick:
                st["pos"] = {"account_id": pos.get("account_id"),
                             "ticket": ticket, "symbol": symbol, "side": side,
                             "entry_price": entry, "stop_loss": stop,
                             "take_profit": target, "volume": volume}
            # 🔴 ٢٠٢٦-٠٩-١٩ (سؤال المالك «كيف عم يأمّن قبل ما يسكّر جزء»)
            #
            # الوقفُ المؤجَّل يخرج هنا — بعد أن يُرى الحجمُ ناقصًا فعلًا على
            # المنصّة، أي بعد أن **وقع** الإغلاق لا بعد أن أُرسل. ونقصانُ
            # الحجم شهادةُ المنصّة نفسها، لا إقرارَ وسيطٍ نستنتجه.
            pending = st.get("pending_stop")
            if pending:
                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): بعد أن نقص الحجم يصير الوقف
                # «جاهزًا»، ولا يُرسل إلّا وهو في جهته الصحيحة من سعر التنفيذ — وإلّا
                # يبقى جاهزًا ويُعاد فحصه مع كلّ سعر بدل أن يُجمع ردُّ `10016`.
                if not pending.get("ready") and volume + _VOL_EPS < pending["volume_before"]:
                    pending["ready"] = True
                if pending.get("ready"):
                    await self._release_stop(st, pending, symbol, side, current, ticket)
                elif not from_tick:
                    # المهلة بدورات ٦٠٩ وحدها كما يقول اسمها: الحجم لا ينقص إلّا
                    # فيها (التِكّة تستعير حجم الدورة)، وتِكّات ميتاتريدر أكثر من
                    # أن تُعدّ دوراتٍ — كانت ستحتجز الوقف قبل أن تصل دورة النقصان.
                    pending["cycles"] += 1
                if (st.get("pending_stop") and not pending.get("ready")
                        and pending["cycles"] > _PENDING_STOP_CYCLES):
                    # المهلةُ انتهت والجزءُ لم يُغلق، فالوقف **لا يخرج**.
                    # صفقةٌ تُؤمَّن بلا أن تُقبض حصّتُها تخرج على تعادلٍ
                    # وتترك ربحها — وهو الذي شكا منه المالك.
                    st["pending_stop"] = None
                    self._stop_withheld += 1
                    self._last_withheld = "%s م%d: الجزء لم يُغلق في %d دورة — الوقف لم يتحرّك" % (
                        symbol, pending["stage"], _PENDING_STOP_CYCLES)
                    self._context.logger.warning(
                        "574 %s ticket=%s: الجزء لم يُغلق، فالوقف لم يُنقل — "
                        "لا تُؤمَّن صفقةٌ لم تُقبض حصّتُها", symbol, ticket)
            if not from_tick:
                partial_levels.ensure_plan(self, st, symbol, side, entry, stop, target,
                                           pos.get("account_id"))
            if st["done"] or st["span"] is None or st["span"] <= 0.0:
                continue
            if (partial_levels.LEVEL_PLAN_ON and st.get("levels")) or (
                    st.get("levels") is not None and partial_levels.protected(symbol)):
                # ٢٠٢٦-١٠-٠٥: صفقةٌ لها مستوياتٌ في الطريق — تُدار عليها لا على الأثلاث.
                # ٢٠٢٦-١٠-٠٦ (ختم المالك «nq»): ورموز «أمّن ثمّ احجز» ولو بلا مستويات.
                await self._plan_step(st, pos, ticket, symbol, side, entry, current, volume, stop)
                continue
            if st.get("levels") is None:
                continue        # الخطّة لم تُحسم بعد (سلّمٌ أو سعرٌ لم يصل) — لا أثلاث قبلها
            stage = st["stage"]
            if stage >= len(STAGES):
                continue
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): هدفٌ ثلثُه داخل كلفة الدورة
            # (سبريد ميتاتريدر + عمولة الدورة) لا يُقسَّم أثلاثًا — يُعامل هدفًا واحدًا
            # ويُترك وقفه وهدفه للوسيط. حالة US30 (1976793832): ثلثُ الهدف 1.08 نقطة،
            # فكان الجزء الأوّل يُغلق في الكلفة والوقف يُنقل إلى سعرٍ تحت العرض.
            # وخطّة المالك (٢٠٢٦-٠٩-١٦ و١٧ و١٨: ثلث ثمّ نصف الباقي ثمّ الكلّ، والوقف
            # إلى التعادل ثمّ الهدف الأوّل) باقيةٌ كما هي لكلّ هدفٍ ثلثُه فوق الكلفة.
            # يُحكم مرّةً قبل المرحلة الأولى بأوّل كلفةٍ مقيسة، ولا يتبدّل.
            if stage == 0 and st.get("single") is None:
                cost = self._roundtrip_cost(pos.get("account_id"), symbol)
                if cost is not None:
                    first = st["span"] * STAGES[0][0]
                    st["single"] = first <= cost + _COST_EPS
                    if st["single"]:
                        st["done"] = True
                        self._single_target += 1
                        self._last_single = "%s tk=%s: ثلث الهدف %.5g ≤ كلفة الدورة %.5g" % (
                            symbol, ticket, first, cost)
                        self._context.logger.warning(
                            "574 %s ticket=%s هدفٌ واحد: ثلث الهدف %.5g داخل كلفة الدورة %.5g "
                            "(سبريد ميتاتريدر + عمولة) — لا أثلاث ولا نقل وقف، الهدف والوقف للوسيط",
                            symbol, ticket, first, cost)
                        continue
            reached, close_frac, lock_r = STAGES[stage]
            profit_distance = (current - entry) if side == SIDE_BUY else (entry - current)
            progress = profit_distance / st["span"]
            if progress < reached - _PROGRESS_EPS:
                continue
            if stage == 0 and st.get("single") is None:
                # بلغ الثلث وكلفةُ الدورة لم تُقس بعد (لا تِكّة ميتاتريدر للرمز
                # منذ الإقلاع): لا يُحكم بأنّ الهدف داخل كلفةٍ لم تُقس — تمضي خطّة
                # المالك كما هي، ويُعدّ ذلك ظاهرًا في الشارة.
                self._cost_unknown += 1
            # نقل الوقف بعد كل هدف — أمر المالك ٢٠٢٦-٠٩-١٦:
            #   بعد الهدف الأوّل  → سعر الدخول      (lock_r = 0)
            #   بعد الهدف الثاني  → الهدف الأوّل    (lock_r = 1/3 من الطريق)
            # بمسطرة المراحل نفسها: `lock` نسبةٌ من الطريق إلى الهدف، فـ`1/3`
            # تضع الوقف على **الهدف الأوّل** حرفيًّا مهما كانت نسبة ر:م.
            lock: float | str | None = (
                None if lock_r is None else "BE" if lock_r == 0.0
                else (entry + lock_r * st["span"] if side == SIDE_BUY
                      else entry - lock_r * st["span"]))
            await self._apply_stage(
                st, pos, ticket, symbol, side, entry, current, volume,
                close_frac, stage == len(STAGES) - 1, lock,
                REASON_LOCK % round((lock_r or 0.0) * len(STAGES)), progress, profit_distance)
        # التقليم من دورة ٦٠٩ وحدها: التِكّة تحمل رمزًا واحدًا، فحذفُ ما
        # ليس فيها يمحو تتبّع كلّ رمزٍ آخر ويُعيد مراحله إلى الصفر.
        if not from_tick:
            for key in list(self._tracked):
                if key not in live:
                    del self._tracked[key]
            # ٢٠٢٦-١٠-٠٥: التذاكر المُدارة على المستويات تُعلَن حين تتغيّر — ٥٧٢ يتنحّى عنها.
            tickets = partial_levels.plan_tickets(self)
            if tickets != self._plan_published:
                self._plan_published = tickets
                await self._context.publish(partial_levels.EVENT_PLAN, {"tickets": tickets})

    async def _plan_step(self, *args: Any) -> None:
        # ⟵ partial_levels.step (٢٠٢٦-١٠-٠٥): مرحلة الخطّة إن بلغها السعر، وإلّا التتبّع.
        await partial_levels.step(self, STAGES, _PROGRESS_EPS, *args)

    async def _apply_stage(self, *args: Any) -> None:
        # ⟵ stage_apply.apply_stage (٢٠٢٦-١٠-٠٥): إغلاق المرحلة ثمّ نقل وقفها — مسارٌ واحد.
        await stage_apply.apply_stage(self, *args)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"tracked": len(self._tracked), "seen": self._seen, "emitted": self._emitted,
                   "restored": self._restored}
        if self._seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_POSITIONS,
                                details=details)
        # المواصفة السارية تُعلَن في الرسالة نفسها. سببها مقيس: عيار هذه
        # الذرّة دُهس ثلاث مرّات بتأويلٍ منّي (النسب من الأصليّ بدل المتبقّي،
        # ثمّ قفل 1R بدل 2R، ثمّ وحدتان مختلفتان في الصفّ الواحد) ولم يظهر
        # الفرق في أيّ شاشة. و`details` تُحذف بالنواة ورقمُ الإصدار يُبنى من
        # المانيفست — فهذا السطر هو الدليل الوحيد.
        #
        # ٢٠٢٦-٠٩-١٨: صار يُنطق بلغة المالك — «هدف١» لا «1R». هو يقرأ
        # أهدافًا ويأمر بها، والمضاعف ترجمةٌ تحتاج حسابًا وتُخفي الخطأ.
        names = {0.0: "تعادل"}
        plan = " ".join("هدف%d: أغلِق %d%% → الوقف %s" % (
            round(reached * len(STAGES)), round(frac * 100),
            "—" if lock is None
            else names.get(lock, "هدف%d" % round(lock * len(STAGES))))
            for reached, frac, lock in STAGES)
        return HealthStatus(state=HealthState.HEALTHY,
                            # 🔴 ٢٠٢٦-٠٩-١٨ (ختم NQ) — عيارٌ يكذب أخطرُ من
                            # عيارٍ مخفيّ: `partial_at_r` و`partial_fraction`
                            # يُقرآن من الإعداد إلى `self._at_r`/`self._fraction`
                            # **ولا يُستعملان في المنطق** — الحاكمُ `STAGES`
                            # الثابتة في الكود (خطّة المالك: ثلث ثمّ نصف
                            # المتبقّي ثمّ الكامل). فالمالك قد يغيّرهما ولا
                            # يحدث شيء. تُعلَن الحقيقة هنا حتى يُحسم أمرُهما.
                            # ٢٠٢٦-١٠-٠٢: ما لم يُرسَل ولماذا — وقفٌ في غير جهته، وهدفٌ داخل الكلفة.
                            message="partials=%d tracked=%d restored=%d عقد_صغير=%d تعذّر=%d | %s | خطّة=%s | مستويات: خطط=%d مُدارة_الآن=%d تتبّع=%d بلا_سلّم=%d | سعر=ميتاتريدر بجهة المركز · وقف_لم_يُرسَل=%d (%s) · القائم_أشدّ=%d (%s) · هدف_واحد=%d (%s) · كلفة_مجهولة=%d | عيار: أصغر_عقد=%g · (partial_at_r=%g و partial_fraction=%g معلَنان ولا يحكمان — الخطّة من الكود)" % (
                                self._emitted, len(self._tracked), self._restored,
                                self._indivisible, getattr(self, "_skipped_close", 0),
                                getattr(self, "_last_skip", "-"), plan,
                                self._level_plans, len(partial_levels.plan_tickets(self)),
                                self._trails, self._plan_timeouts,
                                self._stop_invalid, self._last_invalid,
                                self._stop_kept, self._last_kept,
                                self._single_target, self._last_single, self._cost_unknown,
                                self._min_lot, self._at_r, self._fraction),
                            details=details)

    # ٢٠٢٦-٠٩-١٦ — مقيس من سجلّ الصفقات: `CLOSE_PARTIAL … reason:
    # DUPLICATE_REQUEST_ID`. السبب أنّ هذه الذرّة لم يكن لها حفظ ولا استعادة
    # إطلاقًا، فكل إقلاع يمسح `_tracked` ويعيد كل مركز حيّ إلى `stage=0`:
    # مركزٌ أغلق ثلاثين بالمئة عند هدفه الأوّل يُطلب إغلاقه مرّة ثانية.
    # والأخطر أنّ `original` كان يُلتقط عندئذٍ من الحجم **المتبقّي**، فتصير
    # الخمسون بالمئة الثانية نصف السبعين لا نصف العقد — انحراف صامت في كل
    # النسب بعد أوّل إقلاع.
    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "seen": self._seen,
                "emitted": self._emitted,
                "tracked": {ticket: dict(state)
                            for ticket, state in self._tracked.items()}}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        tracked = state.get("tracked")
        if isinstance(tracked, dict):
            loaded: dict[str, dict[str, Any]] = {}
            for ticket, row in tracked.items():
                if not isinstance(row, dict):
                    continue
                stage = row.get("stage")
                original = _to_float(row.get("original"))
                entry = _to_float(row.get("entry"))
                if not isinstance(stage, int) or isinstance(stage, bool) or stage < 0:
                    continue
                if original is None or entry is None:
                    continue
                loaded[str(ticket)] = {
                    "risk": _to_float(row.get("risk")),
                    "span": _to_float(row.get("span")),
                    "entry": entry, "original": original,
                    # مرحلة محفوظة تُقرأ كما هي: تخفيضها يعيد إغلاقًا وقع،
                    # ورفعها يُسقط هدفًا لم يُؤخذ. وسقفها عدد المراحل.
                    "stage": min(stage, len(STAGES)),
                    "done": row.get("done") is True,
                    # ٢٠٢٦-١٠-٠٢: حكم «هدفٌ واحد» يُحفظ كما حُكم، ولا يُعاد على كلفةٍ أخرى.
                    "single": row.get("single") if isinstance(row.get("single"), bool) else None,
                    # ٢٠٢٦-١٠-٠٥: خطّة المستويات تُحفظ كما حُسمت — لا تتبدّل تحت صفقةٍ مفتوحة.
                    "levels": ([float(v) for v in row["levels"] if _to_float(v) is not None]
                               if isinstance(row.get("levels"), list) else None),
                    "trail_sent": _to_float(row.get("trail_sent")),
                    # ٢٠٢٦-١٠-٠٦ (ختم المالك «NQ»): مرحلة «أمّن ثمّ احجز» تُحفظ فلا يُعاد الثلث بعد إقلاع.
                    "protect": row.get("protect") if isinstance(row.get("protect"), int) else 0,
                    # ٢٠٢٦-١٠-٢٦ (ختم «NQ»، إصلاح الفحص): الوقف المؤجَّل يُستعاد — كان يضيع والمرحلةُ متقدّمة.
                    "pending_stop": stage_apply.restore_pending_stop(row.get("pending_stop")),
                    "seen_at": _to_float(row.get("seen_at"))}
            # تعديل في مكانه لا استبدال — درس ٥٠٠ ٢٠٢٦-٠٩-٠٩.
            self._tracked.clear()
            self._tracked.update(loaded)
            self._restored = len(loaded)
        for name in ("seen", "emitted"):
            value = state.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                setattr(self, "_" + name, value)
