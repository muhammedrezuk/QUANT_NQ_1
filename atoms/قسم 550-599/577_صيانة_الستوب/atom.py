from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.trade_setup import EVENT_SETUP
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): 1.12.0 رفع هذا الملفّ إلى ٤٣٧ سطرًا فعليًّا فوق حدّ الأربع
# مئة (المادة ٩ ملف ٤)، فنُقل منه **حرفيًّا** — صفر تغيير في السلوك، الموضعُ وحده — إلى شقيقين:
# stop_maintenance_checks.py (`_to_float` · `_to_int` · `_norm_side` · `_on_specs` · `_stop_valid` ·
# `_refuse_stop`) وstop_maintenance_anchors.py (`_on_setup` · `_on_structure`). الطرق بقي لها هنا
# تفويضٌ بأسمائها، والدوالّ الثلاث تُستورد باسمها كما كانت. والنشرُ كلّه باقٍ في هذا الملفّ.
from stop_maintenance_checks import _norm_side, _to_float, _to_int
import stop_maintenance_anchors
import stop_maintenance_checks
# ٢٠٢٦-١٠-٢٦ (ختم المالك «NQ» على إصلاح فحص المشروع، البندان ٧ و٩): إعادةُ تضييقٍ ردّه الوسيط، وإعلانُ مركزٍ للمنظومة بلا
# وقف — الجسدان في stop_maintenance_guard.py، وهنا التفويض وحده (حدّ الأربع مئة سطر).
import stop_maintenance_guard
# ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»): «صفقات انا بفتحها مالها علاقة بل منظومة ابدا». كانت الذرّة تضيّق وقف مركز
# المالك اليدويّ كلّ بضع ثوانٍ (17:27–17:45، التذكرتان 2036172903 و2036216648) ويردّها ٥٧٥ `MISSING_OR_FOREIGN_MAGIC` فتعيد.
# الآن تُسقط صفقات المالك من صورة المراكز عند دخولها، بالتمييز الواحد في `shared/owner_trades.py` — فلا تضييق ولا زحف ولا
# إعلان ولا لقطة لها. وردُّ «ليس للمنظومة» نهائيّ لا يُعاد (stop_maintenance_guard.py).
from shared import owner_trades

ATOM_VERSION = "1.14.0"
# v1.12.0 (٢٠٢٦-١٠-٠٢، ختم المالك «صلح كامل nq»): التِكّة من ميتاتريدر بسعر جهة
# المركز (العرض للشراء، الطلب للبيع) لا منتصف سي‑تريدر — والوقف لا يُرسل إلّا وهو
# في جهته الصحيحة من ذلك السعر بحدّ الوسيط (`stops_level`/`freeze_level` من
# `market.symbol_specs`). كان ما في غير جهته يُرسل فيردّه الوسيط `10016`.
# v1.11.0 (٢٠٢٦-٠٩-٢٣، ختم `nq`): رُفع المسار الثالث — خطّة ٥٧١
# (`perpetual.plan.state`) — مع أرشفة ٥٧١. كان لا يعمل إلّا على
# `MAINTAIN_STOP`، وهي لا تُبنى بلا `risk.hard_stop.price` الذي أُرشف ناشره
# (٥٢٥ سعر الستوب الصلب، ٢٠٢٦-٠٩-١٩) — فالمسار ميّتٌ منذها. والصحّة كانت
# معلّقةً بوصول خطّةٍ لا تحمل شيئًا؛ صارت بوصول صورة المراكز التي يعمل عليها
# المساران الباقيان (سقف الخسارة والزحف البنيويّ).
# v1.1.0 (2026-08-25): the manage command carries the leg's magic. Measured
# on the live orphan leg: 577's MODIFY_SL reached 575 without a magic field
# and died there as MISSING_OR_FOREIGN_MAGIC -- the only path that places a
# hard stop on a position was broken at its last meter. The magic rides
# from the broker's own position row (609 passes it through), so a foreign
# position still gets refused by 575's ownership checks, never adopted.

EVENT_POSITIONS = "platform.positions.state"
EVENT_MANAGE = "execution.manage.command"
EVENT_SIZE = "risk.position_size.state"
#: 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك) — «قسمك كلّه على تِكّة، ما في دورة — إنت مال».
#: ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): من **ميتاتريدر** بسعر جهة المركز —
#: الوقف يحكم عليه الوسيط بسعره هو، لا بمنتصف سي‑تريدر (حالة US30 1976793832).
#: وتحليل السوق باقٍ على سي‑تريدر بحكم ٢٠٢٦-٠٩-١٦؛ هذا تنفيذٌ لا تحليل.
EVENT_TICK = "feed.mt5.tick"
#: مواصفات الوسيط: النقطة وحدّا موضع الوقف (`stops_level` · `freeze_level`).
EVENT_SPECS = "market.symbol_specs"

# آلية المالك اليدوية NQ_Manual v5.5 (أرسلها ٢٠٢٦-٠٩-٠٥) تحمل الفكرة
# الناقصة هنا: بعد التعبئة يُعاد ضبط الوقف على **سعر الدخول الفعلي**
# بحيث تبقى الخسارة مساوية للميزانية مهما كان الانزلاق:
#     exactSL = floor(SavedRisk / (lot × valuePerPoint))
#     إن كان الانزلاق ضدّنا: SL يُضيَّق بمقدار خسارة الانزلاق
# لا تقدير مسبق للانزلاق — قياس بعدي على ما نُفِّذ فعلًا. مقيس على ٢٤
# صفقة: الانزلاق ضدّنا دائمًا (وسيط 2.7 · أقصى 16.90 دولار).
#
# الفرق عن آلية المالك: وقفه من الميزانية وحدها، ووقفي من التحليل —
# فالميزانية هنا **سقف** لا مصدر. الوقف البنيوي يبقى ما دامت خسارته
# ضمن السقف، ويُضيَّق فقط إذا تجاوزته بعد الانزلاق (اللوت حينها منفَّذ
# ولا يمكن تصغيره).
# ٢٠٢٦-٠٩-٠٦ (مقيس على التذكرة 1911165380): هذا الثابت بقي ١٠ دولارات
# بعد أن صار السقف ١٪ من الرصيد (105.13$)، فخنق الحارسُ صفقةً سليمة:
# فُتحت 01:37:23 بوقف ٣٥ نقطة، وبعد **ثانيتين** أُرسل MODIFY_SL يقرّبه
# إلى 12.82 نقطة (79,800.24) كي تصير الخسارة عشرة — فماتت على أوّل
# تذبذب بـ−17.21. السقف يُقرأ الآن من 513 مع كل تحجيم (metadata
# max_trade_loss)، فيتبع الرصيد والنسبة بدل رقم متحجّر.
# ٢٠٢٦-٠٩-١٧ — أمر المالك «١٠٠ دولار على كل الصفقات». كان ١٠ فيخنق كل
# صفقة إن لم يصل سقف ٥١٣ إلى هنا لأيّ سبب.
DEFAULT_MAX_TRADE_LOSS = 100.0
# هامش ٥٪ نقصًا أو زيادة بأمر المالك ٢٠٢٦-٠٩-١٧ (كان ٢٪): المدى
# المقبول [٩٥٪, ١٠٥٪] من السقف، وما خرج عنه يُردّ إليه.
LOSS_TOLERANCE = 1.05
# مسافة التنفّس التي يجب أن تفصل الوقف الزاحف عن السعر الحالي، كنسبة من
# المسافة الأصلية للوقف. وقفٌ يلتصق بالسعر يُغلق الصفقة بدل أن يحميها.
#
# ٢٠٢٦-٠٩-٠٦ (حكم المالك: «آخر صفقة لازم تربح ٢٠٠ لا ٣٠٠ دولار، ربحانة
# ٣٥»). القياس يشهد له: أهداف الصفقات الثماني الأخيرة كانت على بعد
# 78→142 نقطة (تساوي 223$ إلى 303$ بلوتاتها)، و**لا واحدة بلغت هدفها**
# — الثمانية كلّها خرجت بـSL. ومقارنة الأربعين المزحوفة بالإحدى
# والثلاثين غير المزحوفة:
#     زُحف وقفها : ن=40 · رابحة 60% · صافي +89.05$ · أفضل صفقة +21.84$
#     بلا زحف    : ن=31 · رابحة  6% · صافي −866.68$ · أسوأ −125.07$
# فالزحف هو ما يُبقي الحساب حيًّا، لكنه سقفٌ على كل رابح عند +21.84$.
#
# الرقمان اللذان يخنقانه:
#   ١) التنفّس 0.25 من وقف 30.84 = 7.71 — وهو **مساوٍ** للضجيج المقيس
#      (الزيادة على المسافة المخطَّطة: مئين ٨٠ = 7.54، أقصى = 27.88).
#      أي أن الضجيج وحده يكفي لضرب الوقف الزاحف في خُمس الحالات.
#      يصير 0.9 ⇒ ~27.8 على وقف ثلاثين، أي بقدر أقصى ضجيج مرصود.
#   ٢) لا شرط ربح أدنى: مقيس على 1911362798 — شُدّ الوقف إلى 1.47 نقطة
#      من الدخول والسعر بعيد 9 نقاط فقط، فخرجت الصفقة بـ−0.53$ وهدفها
#      يساوي +303.08$. الزحف يبدأ الآن بعد ربح يعادل المخاطرة الأصلية
#      (1R)، فلا يُقفل رابحٌ على لا شيء، ويبقى للاتجاه مجال يكمل فيه.
TRAIL_BREATHING_FRAC = 0.9
TRAIL_MIN_PROFIT_R = 1.0

ACTION_MODIFY = "MODIFY_SL"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_DATA = "NO_POSITIONS_YET"

_KEY_SEP = "|"


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._min_change = 1e-9
        self._legs: dict[str, list[dict[str, Any]]] = {}
        self._last_sl: dict[int, float] = {}
        self._snapshots: dict[int, dict[str, Any]] = {}
        self._tick_checks = 0
        self._duplicate_suppressed = 0
        self._vpp: dict[str, float] = {}
        self._capped: set[int] = set()
        self._risk_capped = 0
        self._risk_widened = 0
        self._structure: dict[str, dict[str, float]] = {}
        self._loss_cap: dict[str, float] = {}
        self._trailed = 0
        self._trailing_enabled = False
        self._reward_risk = 3.0
        self._trail_suppressed = 0
        # إبطال الإعداد لكل رمز: (setup_id, side, price) — مرجع الملكية.
        self._setup_stop: dict[str, tuple[str, str, float]] = {}
        self._sent = 0
        self._updates = 0
        self._seen_positions = False
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حدّ الوسيط لموضع الوقف لكلّ رمز،
        # وما لم يُرسَل لأنّه في غير جهته (يُعدّ مرّةً لكلّ تذكرة ويُعاد فحصه).
        self._point: dict[str, float] = {}
        self._stops_level: dict[str, float] = {}
        self._stop_invalid = 0
        self._invalid_tickets: set[int] = set()
        self._last_invalid = "-"
        stop_maintenance_guard.ensure(self)

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._min_change = float(context.config.get("min_sl_change", 1e-9))
        # ٢٠٢٦-٠٩-١٦ — أمر المالك «ترييلنج وقفه» بختم `NQ`. الافتراضيّ
        # `false`: غياب المفتاح لا يُعيد الزحف من تلقائه.
        self._trailing_enabled = bool(context.config.get("trailing_enabled", False))
        # مضاعف الهدف — يطابق المضاعف نفسه في ٥٥١، كي يُعاد بناء
        # الهدف بالنسبة ذاتها حين تتبدّل مسافة الوقف.
        self._reward_risk = float(context.config.get("reward_risk", 3.0))
        context.subscribe(EVENT_POSITIONS, self._on_positions)
        context.subscribe(EVENT_SIZE, self._on_size)
        context.subscribe(EVENT_TICK, self._on_tick)
        context.subscribe(EVENT_SPECS, self._on_specs)
        # مصادر التتبّع البنيوي: القمم والقيعان من 201 والهيكل الداخلي
        # من 203 — خلفها يزحف الوقف بينما الصفقة تكمل.
        # ٢٠٢٦-٠٩-٠٦ (مقيس): المصدران وحدهما نشرا سوينغين اثنين فقط
        # (201 swings=2 · 203 events=3)، فلم يجد الوقف الزاحف قاعًا يزحف
        # خلفه ولا مرّة. تُضاف كل الذرّات التي تقيس مستوى بنيويًّا —
        # هي نفسها التي تغذّي خريطة 581 — فيصير للتتبّع ما يمسك به.
        for event in ("structure.swing.state", "structure.internal.state",
                      "structure.external.state", "structure.bos.state",
                      "structure.choch.state", "structure.mss.state",
                      "liquidity.sweep.state", "liquidity.fvg.state",
                      "liquidity.buyside.state", "liquidity.sellside.state"):
            context.subscribe(event, self._on_structure)
        # ٢٠٢٦-٠٩-٠٦ — ورقة ملكية الصفقة (المرحلة ز · §١٥): الزحف كان
        # يبدأ من «أقرب قاع» في خريطة عامّة، فيستطيع أن يستبدل إبطال
        # الإعداد بمنطق لا ينتمي إليه — أي تعود المشكلة نفسها بعد الدخول.
        # 577 يسمع الإعداد الآن، ويحرس حدًّا لا يتجاوزه: لا يشدّ الوقف
        # إلى ما هو **أضيق من إبطال الفكرة** إلا إن كان الربح قد تجاوزه،
        # ولا يوسّعه أبدًا.
        context.subscribe(EVENT_SETUP, self._on_setup)
        # ٢٠٢٦-١٠-٢٦: نتيجة كلّ تضييق (نجاحه من ٦٠١، وفشله من ٦٠١ أو ٥٧٥) — كي يُعاد ما ردّه الوسيط.
        stop_maintenance_guard.subscribe(self, context)

    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): أجساد الثلاث في stop_maintenance_checks.py حرفيًّا —
    # تفويضٌ بالاسم: مواصفات الوسيط، وهل يقبل الوقفَ الآن، ورفضُ ما في غير جهته مرّةً لكلّ تذكرة.
    async def _on_specs(self, payload: dict[str, Any]) -> None:
        await stop_maintenance_checks.on_specs(self, payload)

    def _stop_valid(self, symbol: Any, side: str, stop: Any, price: Any) -> bool:
        return stop_maintenance_checks.stop_valid(self, symbol, side, stop, price)

    def _refuse_stop(self, symbol: str, ticket: int, stop: float, price: Any,
                     origin: str) -> None:
        stop_maintenance_checks.refuse_stop(self, symbol, ticket, stop, price, origin)

    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): جسدا مرساتي الزحف في stop_maintenance_anchors.py
    # حرفيًّا — تفويضٌ بالاسم: إبطالُ الإعداد لكلّ رمز، وآخرُ قاعٍ وقمّةٍ بنيويّين.
    async def _on_setup(self, payload: dict[str, Any]) -> None:
        await stop_maintenance_anchors.on_setup(self, payload)

    async def _on_structure(self, payload: dict[str, Any]) -> None:
        await stop_maintenance_anchors.on_structure(self, payload)

    async def _trail_structure(self, pos: dict[str, Any]) -> None:
        """يزحف بالوقف خلف آخر مستوى بنيوي في اتجاه الربح.

        ⛔ **موقوفٌ بأمر المالك ٢٠٢٦-٠٩-١٦ (ختم `NQ`): «ترييلنج وقفه».**

        والمقيس الذي سبق الأمر: ستّ صفقات مغلقة في اليوم، **خمسٌ منها
        أُغلقت بالوقف** وأربعٌ بأرباح تافهة (`+23.98` · `+25.56` · `+1.54`
        · `+1.21`)، وواحدة وحدها بلغت هدفها. وهذه الذرّة أرسلت خمسة أوامر
        `MODIFY_SL` على تذكرة ناسداك واحدة في تسع دقائق — فالوقف يلاحق
        السعر فيُقفل الصفقة عند أوّل ارتداد قبل أن تبلغ هدفها.

        وخطّة المالك تنقل الوقف مرّةً واحدة: إلى **سعر الدخول** عند الهدف
        الأوّل (٥٧٢ التعادل)، ثمّ لا يُمَسّ. فالزحف البنيويّ ينقض ذلك.

        **ولم يُحذف الكود بل عُطِّل بعيار** (`trailing_enabled` في
        المانيفست): الأمر قابل للرجوع بكلمة، والمسارات الأخرى في هذه الذرّة
        تبقى عاملةً — سقف الخسارة (`_on_size`) حمايةٌ لا ملاحقة. (والوقف
        المحفظيّ `_on_plan` رُفع ٢٠٢٦-٠٩-٢٣ مع أرشفة ٥٧١ — v1.11.0.)
        """
        if not self._trailing_enabled:
            self._trail_suppressed += 1
            return
        return await self._trail_structure_impl(pos)

    async def _trail_structure_impl(self, pos: dict[str, Any]) -> None:
        """جسم الزحف البنيويّ — لا يُنادى إلّا حين `trailing_enabled`.

        حكم المالك ٢٠٢٦-٠٩-٠٦: «يدير صفقة على تحليل بين ستوب وهدف ليس
        محدود — إذا اتجاه مدعوم يكمل مو يوقف». فالخروج لا يقرّره رقم
        مُسبق بل انكسارُ الهيكل: ما دام السعر يصنع قيعانًا أعلى (لشراء)
        يزحف الوقف خلف آخرها، وتبقى الصفقة مفتوحة تجمع ما يعطيه الاتجاه.
        الوقف يُشدّ ولا يُوسَّع أبدًا، ولا يتحرّك إلا والصفقة رابحة —
        فلا يُقرَّب وقفٌ على مركز خاسر فيُخنَق قبل أوانه.
        """
        ticket = _to_int(pos.get("ticket"))
        if stop_maintenance_guard.refused_for_good(self, ticket):
            return
        symbol = str(pos.get("symbol") or "")
        side = _norm_side(pos.get("side"))
        entry = _to_float(pos.get("entry_price"))
        current = _to_float(pos.get("current_price"))
        stop = _to_float(pos.get("stop_loss"))
        book = self._structure.get(symbol.upper()) or {}
        if ticket is None or not side or not entry or not current:
            return
        anchor = book.get("low") if side == "BUY" else book.get("high")
        if not anchor:
            return
        in_profit = (current > entry) if side == "BUY" else (current < entry)
        if not in_profit:
            return
        # ٢٠٢٦-٠٩-٠٦ (مقيس على التذكرة 1911168352): المرساة كانت تُقبل
        # لمجرّد وقوعها بين الدخول والسعر، فزحف الوقف إلى 79,783.69
        # بينما السعر 79,782.55 — **1.14 نقطة** فقط. وقفٌ بهذا اللصوق
        # ليس حمايةً بل إغلاقٌ فوريّ: ضُرب بعد ثوانٍ بـ−1.46 على صفقة
        # وقفها الأصلي ٣٥ نقطة. المرساة تحتاج مسافة تنفّس من السعر — لا
        # تقلّ عن رُبع المسافة الأصلية للوقف — وإلا تُركت الصفقة تتنفّس
        # بوقفها الحالي حتى يصنع الهيكل مرساةً أبعد.
        original = abs(entry - stop) if (stop and stop > 0) else 0.0
        # ربحٌ أدنى قبل أوّل زحف: بلا هذا الشرط يُشدّ الوقف إلى جوار
        # الدخول عند أوّل حركة، فيتحوّل رابحٌ محتمل بمئات الدولارات إلى
        # صفر. المقياس هو المخاطرة نفسها: لا يُمسّ الوقف قبل أن يبلغ
        # الربح مثلها (1R).
        if original > 0 and abs(current - entry) < original * TRAIL_MIN_PROFIT_R:
            return
        breathing = original * TRAIL_BREATHING_FRAC
        if breathing > 0 and abs(current - anchor) < breathing:
            return
        # ملكية الإبطال (§١٥ و§١٦): المرساة لا تُستبدل بإبطال الإعداد إلا
        # حين يكون الربح قد تجاوزه فعلًا — عندها الزحف يقفل ربحًا، لا
        # يستبدل فكرة. وقبل ذلك يبقى إبطال الإعداد هو الحدّ.
        owned = self._setup_stop.get(symbol.upper())
        if owned is not None:
            _, owned_side, owned_stop = owned
            if owned_side == side:
                beyond = (current > owned_stop) if side == "BUY" else (current < owned_stop)
                inside = (anchor < owned_stop) if side == "BUY" else (anchor > owned_stop)
                if inside and not beyond:
                    return
        # المرساة يجب أن تقع بين الدخول والسعر: خلف الربح المحقَّق، لا
        # أمامه (فتُضرب فورًا) ولا خلف الدخول (فلا تضيف حماية).
        if side == "BUY":
            if not (entry <= anchor < current):
                return
            better = stop is None or stop <= 0.0 or anchor > stop + self._min_change
        else:
            if not (current < anchor <= entry):
                return
            better = stop is None or stop <= 0.0 or anchor < stop - self._min_change
        if not better:
            return
        # ٢٠٢٦-٠٩-١٦ — مقيس من سجلّ الصفقات: اثنتا عشرة محاولة `MODIFY_SL`
        # لنفس التذكرة **في الثانية الواحدة** (كلّها بطابع `14:05:41`)، ردّها
        # الوسيط `STALE_8s` ثم `STALE_7s` … حتّى `BROKER_DISCONNECTED`، قبل
        # أن تنجح التاسعة عشرة. السبب أنّ `better` يقارن بالوقف **الحيّ** عند
        # الوسيط، وهو لا يتغيّر ما دام الأمر السابق لم يُنفَّذ بعد — فكلّ
        # تِكّة مركزٍ تُعيد إرسال الوقف نفسه. المسار الثالث (`_on_plan`) كان
        # يقرأ `_last_sl` قبل الإرسال؛ هذا المسار كان يكتبه ولا يقرأه.
        # المسار الثاني محميّ بـ`_capped`. (`_last_sl` يُنظَّف عند اختفاء
        # التذكرة، فوقفٌ تغيّر فعلًا يمرّ كما كان.)
        previous = self._last_sl.get(ticket)
        if previous is not None and abs(previous - anchor) < self._min_change:
            self._duplicate_suppressed += 1
            return
        if not self._stop_valid(symbol, side, anchor, current):
            self._refuse_stop(symbol, ticket, anchor, current, "structure_trail")
            return
        self._invalid_tickets.discard(ticket)
        self._last_sl[ticket] = anchor
        self._sent += 1
        self._trailed += 1
        self._context.logger.warning(
            "577 trail %s ticket=%s: %s -> %s (entry=%s price=%s side=%s)",
            symbol, ticket, stop, round(anchor, 6), entry, current, side)
        await self._context.publish(EVENT_MANAGE, {
            "account_id": str(pos.get("account_id") or ""),
            "action": ACTION_MODIFY, "ticket": ticket, "symbol": symbol,
            "side": side, "stop_loss": round(anchor, 6),
            "magic": _to_int(pos.get("magic")), "origin": "structure_trail"})

    async def _on_size(self, payload: dict[str, Any]) -> None:
        """قيمة النقطة لكل لوت — من مواصفة الوسيط التي ينشرها 513."""
        if not self._running or not isinstance(payload, dict):
            return
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        tick_value = _to_float(meta.get("tick_value"))
        tick_size = _to_float(meta.get("tick_size"))
        symbol = str(payload.get("symbol") or "")
        if symbol and tick_value and tick_size:
            self._vpp[symbol] = tick_value / tick_size
        # سقف الخسارة الساري كما يحسبه 513 من الرصيد والنسبة — لا رقم
        # ثابت هنا يتحجّر ويخنق الصفقات حين تتغيّر المعايرة.
        cap = _to_float(meta.get("max_trade_loss"))
        if symbol and cap and cap > 0:
            self._loss_cap[symbol] = cap

    async def _cap_risk(self, pos: dict[str, Any]) -> None:
        """يضبط وقف مركز منفَّذ كي لا تتجاوز خسارته سقف المالك.

        يُحسب على سعر الدخول **الفعلي**، فيدخل الانزلاق في الحساب بلا
        تقدير: خسارة الوقف الحالي = اللوت × (الدخول − الوقف) × قيمة
        النقطة. إن تجاوزت السقف، يُقرَّب الوقف إلى المسافة القصوى التي
        تُبقيها عنده بالضبط. الوقف يُضيَّق فقط — لا يُوسَّع أبدًا.
        """
        ticket = _to_int(pos.get("ticket"))
        symbol = str(pos.get("symbol") or "")
        side = _norm_side(pos.get("side"))
        volume = _to_float(pos.get("volume"))
        entry = _to_float(pos.get("entry_price"))
        stop = _to_float(pos.get("stop_loss"))
        vpp = self._vpp.get(symbol)
        # ٢٠٢٦-١٠-٢٦ (البند ٩): مركزٌ بلا وقف كان يخرج من هنا صامتًا — يُعلَن الآن قبل الخروج.
        stop_maintenance_guard.note_unprotected(self, pos)
        # ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك): تذكرةٌ ردّ الوسيط تضييقها لأنّها ليست للمنظومة لا يُعاد عليها حسابٌ ولا أمر.
        if stop_maintenance_guard.refused_for_good(self, ticket):
            return
        if (ticket is None or not side or not volume or not entry
                or not stop or stop <= 0.0 or not vpp or vpp <= 0.0):
            return
        distance = (entry - stop) if side == "BUY" else (stop - entry)
        if distance <= 0.0:
            return
        cap = self._loss_cap.get(symbol) or DEFAULT_MAX_TRADE_LOSS
        # ⚖️ ٢٠٢٦-٠٩-١٨ — المقايضة والعمولة داخل السقف، بأمر المالك.
        #
        # كان الحارس يقيس **فرق السعر وحده** مقابل المئة، وهما تكلفتان
        # واقعتان على المركز نفسه ويصلان في حمولته (`swap` و`commission` من
        # ٦٠٩). فمركزٌ باتَ ليلةً كان يبدو عند تسعين دولارًا وهو عند مئة
        # وثلاثين، ولا يضيّق أحدٌ وقفه.
        #
        # والمقياس الذي أوجبه، مقروءًا من مواصفات الوسيط بعد وصولها اليوم:
        # BTCUSD `swap_mode=5` (نسبة سنويّة من السعر) و`swap_long=-20` و
        # `swap_rollover3days=7` — أي 76,363 × 0.20 ÷ 365 = 41.84$ للّوت في
        # الليلة، سبع ليالٍ في الأسبوع. ولوت 6.45 يكلّف 269.89$ في ليلةٍ
        # واحدة: ضعفا ميزانيّة الصفقة ونصف، بلا حركة سعر.
        #
        # ولا تُحتسب مقايضةٌ **موجبة** خصمًا من الخسارة (الذهب بيعًا +41.97):
        # ربحٌ من المقايضة لا يشتري وقفًا أوسع — الحارس محافظ في جهةٍ واحدة.
        # والعمولة تُضاعَف: الحقل في المركز المفتوح يحمل عمولة **الفتح**
        # وحدها، ومثلها تُقتطع عند الإغلاق. مقيسٌ من مواصفات الوسيط
        # («3.5 USD للعقد — الصفقات الداخلة/الخارجة») ومن سجلّ الإغلاق
        # (‎-3.53‎$/لوت على الذهب في ٢٥ صفقة). فالحارس يرى الدورة كاملة لا
        # نصفها، وإلّا أذن بخسارةٍ يعرف أنّها آتية.
        carry = 0.0
        swap_now = _to_float(pos.get("swap"))
        if swap_now is not None and swap_now < 0.0:
            carry += -swap_now
        commission_now = _to_float(pos.get("commission"))
        if commission_now is not None and commission_now < 0.0:
            carry += -commission_now * 2.0
        loss = volume * distance * vpp + carry
        if carry > 0.0:
            self._carry_seen = getattr(self, "_carry_seen", 0) + 1
            self._last_carry = "%s tk=%s حمل=%.2f$" % (symbol, ticket, carry)
        # ⚖️ ٢٠٢٦-٠٩-١٧ — أمر المالك: «بدي سجل بالكامل ١٠٠ دولار خسارة على
        # كل الصفقات مع هامش ٥٪ نقصًا أو زيادة».
        #
        # كان الحارس **ذا اتّجاه واحد**: يضيّق إن تجاوزت الخسارة السقف،
        # ولا يوسّع إن قصُرت عنه («الوقف يُضيَّق فقط — لا يُوسَّع أبدًا»).
        # فالانزلاق لصالحنا كان يقصّ المخاطرة بلا قصد — مقيس على تذكرة
        # الذهب 1938456351: المرجع 4268.94 والتنفيذ 4268.22 (انزلاق ٠٫٧٢
        # لصالحنا)، فصارت المسافة 2.18 بدل 2.90 والمخاطرة **37$ بدل 49$**،
        # ولم يُعدَّل شيء.
        #
        # الآن المدى مغلق من الطرفين: كل خسارةٍ خارج [٩٥٪, ١٠٥٪] من السقف
        # تُردّ إلى السقف بالضبط. والهامش ٥٪ بأمره (كان ٢٪).
        #
        # ⚠️ وحارس التوسيع قائمٌ بالبناء لا بشرطٍ جديد: `distance > 0`
        # أعلاه يعني أنّ الوقف ما زال في جهة الخسارة. فمتى نُقل إلى
        # التعادل (٥٧٢) صارت `distance = 0`، ومتى نُقل إلى الربح (٢R بعد
        # الهدف الثاني) صارت سالبة — وفي الحالين تخرج الدالّة قبل هنا.
        # فلا يُعاد وقفٌ مؤمَّنٌ إلى الخسارة أبدًا.
        # ⚠️ ٢٠٢٦-٠٩-١٧ — عطّلتُ التوسيع هنا ساعةً على تشخيصٍ خاطئ، ثمّ
        # أُعيد. والسبب يستحقّ التسجيل كي لا يتكرّر:
        #
        # رأيتُ في السجلّ الحيّ ثلاثة أسطر `STOP_WIDENING_REFUSED` تقترح
        # أوقافًا تساوي ٢٠٠٠$ لبتكوين و١٠٠٠$ لذهب — وهما ميزانيّتا الأصل
        # في ٥١٨ — فنسبتُها إلى هذا الحارس وأوقفتُه. **وهي ليست منه**:
        # ذلك السطر في `_maintain` (السطر ~٥٢٣)، يقرأ `stop_price` من خطّة
        # `perpetual.plan.state`، وتلك تُبنى على ميزانيّة الأصل لا على سقف
        # الصفقة. فالحارس هناك يرفض اقتراح مسارٍ آخر — وهو عمله الصحيح.
        #
        # والدليل الذي كان أمامي ولم أقرأه: الشارة تقول `تضييق=5 توسيع=0`
        # — أي أنّ هذا الفرع لم يوسّع مرّةً واحدة أصلًا.
        #
        # **القاعدة**: اسم السبب في السجلّ لا يكفي — اقرأ الدالّة التي
        # تطبعه قبل أن تنسب الرقم إلى حارسٍ بعينه.
        low, high = cap * (2.0 - LOSS_TOLERANCE), cap * LOSS_TOLERANCE
        if low <= loss <= high:
            self._capped.discard(ticket)
            return
        # ٢٠٢٦-١٠-٢٦ (البند ٧): التذكرة المقصوصة تبقى حتّى يردّ الوسيط قصّها ويحلّ موعد إعادته — فيُعاد الحساب.
        if ticket in self._capped and not stop_maintenance_guard.retry_due(self, ticket):
            return
        widening = loss < low
        # 🔴 ٢٠٢٦-٠٩-١٨ — أمر المالك: «وقف لا يوسّع بهل همجيّة · هي مصاري
        # مو لعب». **يُلغى التوسيع**، وينقض ما فوقه من أمر ٢٠٢٦-٠٩-١٧.
        #
        # المقيس على التذكرة 1943171698 (ذهب، ١٣:٢٣:٣٩): دخول 4380.43
        # وهدف 4382.46 — أي 2.03$ بُني على وقفٍ قدره 0.677$. ثمّ وسّع هذا
        # الفرعُ الوقفَ إلى 49.93$ ليبلغ المئةَ بلوت 0.02، فصارت النسبة
        # **١:٠٫٠٤**: خمسون دولارًا معرَّضةً مقابل دولارين مرجوّين.
        #
        # والخطأ ليس في المئة بل في وسيلتها: المخاطرة تُضبط **بالحجم** لا
        # بالوقف. الوقف مُلكُ التحليل، ومدُّه يقتل الهدف المبنيّ عليه
        # ويزيد المال المعرَّض فعلًا. ومخاطرةٌ دون السقف نعمةٌ لا عيب:
        # السقف حدٌّ أعلى لا هدفٌ يُبلَغ. فالحارس ذو اتّجاهٍ واحد: يضيّق
        # ولا يوسّع. وما دون السقف يُعالَج عند التحجيم قبل الإرسال.
        if widening:
            self._widen_refused = getattr(self, "_widen_refused", 0) + 1
            self._last_widen_refused = "%s tk=%s %.2f$<%.2f$" % (
                symbol, ticket, loss, cap)
            if self._widen_refused <= 5:
                self._context.logger.warning(
                    "577 لا توسيع %s tk=%s: الخسارة %.2f$ دون السقف %.2f$ "
                    "والوقف لا يُمَدّ — المخاطرة تُضبط بالحجم لا بالوقف",
                    symbol, ticket, loss, cap)
            return
        # المسافة تُحسب على ما **بقي** من السقف بعد الحمل الواقع: حملٌ
        # قدره ٤٠$ يترك للسعر ٦٠$ لا مئة.
        room = cap - carry
        # 🔴 وحين يبتلع الحملُ السقفَ كلّه، لا وقفَ يُرضي الحدّ: أيّ مسافة
        # موجبة تتجاوزه، والمسافة الصفريّة أو السالبة تضع الوقف في جهة
        # الربح — أي تغلق المركز بسعرٍ أفضل من دخوله وتسمّيه حماية.
        #
        # مقيسٌ على أرقام هذا الحساب: بتكوين بلوت 6.45 يبيت ليلةً بـ269.89$
        # (مقايضة ‎-20%‎ سنويّة من السعر)، فـ`cap - carry = -169.89`.
        #
        # فلا يُرسَل شيء، ويُعلَن الحدث باسمه: القرار هنا إغلاقُ مركزٍ أو
        # قبولُ تجاوز، وكلاهما قرار مالكٍ لا حارسِ وقف.
        if room <= 0.0:
            self._carry_over_cap = getattr(self, "_carry_over_cap", 0) + 1
            self._last_carry = "%s tk=%s حمل=%.2f$ ⩾ سقف=%.2f$ — لا وقف يُرضيه" % (
                symbol, ticket, carry, cap)
            if self._carry_over_cap <= 8:
                self._context.logger.error(
                    "577 %s tk=%s: الحمل %.2f$ بلغ سقف الصفقة %.2f$ — لا وقفَ "
                    "يبقيها عنده. الخسارة قائمة بلا حركة سعر (مقايضة/عمولة).",
                    symbol, ticket, carry, cap)
            return
        max_distance = room / (volume * vpp)
        capped = (entry - max_distance) if side == "BUY" else (entry + max_distance)
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): السعر تجاوز الوقف المضيَّق فلا
        # يقبله الوسيط (`10016`) — لا يُرسل ولا يُعلَّم «قُصّ»، فيُعاد فحصه مع السعر.
        current = _to_float(pos.get("current_price"))
        if not self._stop_valid(symbol, side, capped, current):
            self._refuse_stop(symbol, ticket, capped, current, "risk_cap")
            return
        self._invalid_tickets.discard(ticket)
        self._capped.add(ticket)
        self._risk_capped += 1
        if widening:
            self._risk_widened = getattr(self, "_risk_widened", 0) + 1
        self._last_sl[ticket] = capped
        self._sent += 1
        self._context.logger.warning(
            "577 %s %s ticket=%s: loss=%.2f %s [%.2f..%.2f] | entry=%s "
            "stop=%s -> %s (lot=%s vpp=%.4f cap=%.2f مصدر=%s)",
            "توسيع" if widening else "تضييق", symbol, ticket, loss,
            "<" if widening else ">", low, high, entry, stop,
            round(capped, 6), volume, vpp, cap,
            "٥١٣" if symbol in self._loss_cap else "افتراضيّ")
        # ٢٠٢٦-٠٩-١٧ — الهدف يتحرّك مع الوقف أو لا يتحرّك.
        #
        # مقيس على شاشة المالك (xauusd 1938572346، فُتح ٠٢:٣٧): وُسّع الوقف
        # هنا من 92$ إلى **97.50$** ليبلغ مدى المالك، والهدف بقي على مسافته
        # الأولى — فصارت النسبة **2.84 لا 3.00**، والهدف الصحيح 4261.25 لا
        # 4261.66. أي أنّ إصلاح المئة نفسه كان يكسر عقد ٣:١ عند كل تعديل.
        #
        # فيُعاد بناء الهدف على المسافة الجديدة بالمضاعف نفسه. والمسافة
        # مقيسة من **سعر الدخول الفعليّ** كالوقف تمامًا، فالانزلاق داخلٌ
        # في الطرفين لا في طرفٍ واحد.
        #
        # ⚖️ ٢٠٢٦-٠٩-١٨ — حكم المالك: «لازم أهداف تكون من 1/3 وأكبر من هيك،
        # يعني 1/5 1/7 1/9 وأكبر». وكان المضاعف هنا ثابتًا عند `reward_risk`،
        # فصفقةٌ دخلت بـ١/٩ تُسحق إلى ١/٣ عند أوّل تعديلِ وقف — أي أنّ حارس
        # المئة دولار كان يقصّ ثلثي هدف الصفقة صامتًا.
        #
        # فالمضاعف يُشتقّ من **الصفقة نفسها** (هدفها الحيّ على وقفها الحيّ)،
        # و`reward_risk` تبقى أرضيّةً لا سقفًا: ما دخل أبعد يبقى أبعد.
        live_target = _to_float(pos.get("take_profit"))
        live_stop = _to_float(pos.get("stop_loss"))
        multiple = self._reward_risk
        if live_target and live_stop and entry:
            live_reward = (live_target - entry) if side == "BUY" else (entry - live_target)
            live_risk = abs(entry - live_stop)
            if live_risk > 0.0 and live_reward > 0.0:
                multiple = max(self._reward_risk, live_reward / live_risk)
        self._last_multiple = multiple
        target = ((entry + max_distance * multiple) if side == "BUY"
                  else (entry - max_distance * multiple))
        await self._context.publish(EVENT_MANAGE, {
            "account_id": str(pos.get("account_id") or ""),
            "action": ACTION_MODIFY, "ticket": ticket, "symbol": symbol,
            "side": side, "stop_loss": round(capped, 6),
            "take_profit": round(target, 6),
            "request_id": stop_maintenance_guard.sent(self, ticket),
            "magic": _to_int(pos.get("magic")), "origin": "risk_cap"})

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_positions(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        positions = payload.get("positions")
        if not isinstance(positions, list):
            return
        # ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك): صفقة المالك لا تدخل الذرّة — لا تُدار ولا تُحفظ صورتها ولا تُعدّ ساق.
        positions = owner_trades.system_rows(positions, self._magic)
        self._seen_positions = True
        self._updates += 1
        legs: dict[str, list[dict[str, Any]]] = {}
        live_tickets: set[int] = set()
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            symbol = str(pos.get("symbol") or "")
            ticket = _to_int(pos.get("ticket"))
            side = _norm_side(pos.get("side"))
            if not symbol or ticket is None or not side:
                continue
            key = str(pos.get("account_id") or "") + _KEY_SEP + symbol
            legs.setdefault(key, []).append({
                "ticket": ticket, "side": side,
                "magic": _to_int(pos.get("magic")),
                # الوقف القائم على المركز نفسه — مرجع «لا توسيع».
                "sl": _to_float(pos.get("stop_loss")),
                "entry": _to_float(pos.get("entry_price")),
            })
            live_tickets.add(ticket)
        self._legs = legs
        for ticket in [t for t in self._last_sl if t not in live_tickets]:
            del self._last_sl[ticket]
        self._capped &= live_tickets
        self._invalid_tickets &= live_tickets
        stop_maintenance_guard.prune(self, live_tickets)
        # 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك «قسمك كلّه على تِكّة») — صور المراكز
        # تُحفظ كما وردت من دورة ٦٠٩، لتفحصها التِكّة بسعرها اللحظيّ.
        # وتُحفظ **كاملةً** لا منتقاةً: الدالّتان تقرآن أحد عشر حقلًا
        # (`volume` · `commission` · `swap` · `magic` …)، وصورةٌ ناقصة
        # تجعل مسار التِكّة يحكم بأرقامٍ غير التي يحكم بها مسار الدورة.
        self._snapshots = {}
        for pos in positions:
            if isinstance(pos, dict):
                tk = _to_int(pos.get("ticket"))
                if tk is not None:
                    self._snapshots[tk] = dict(pos)
        if self._context is not None:
            for pos in positions:
                if not isinstance(pos, dict):
                    continue
                # الأمان أوّلًا (سقف الخسارة)، ثم التتبّع البنيوي الذي
                # يترك الصفقة تكمل ما دام الهيكل يحملها.
                await self._cap_risk(pos)
                await self._trail_structure(pos)

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        """التِكّة تعيد فحص الوقف بالسعر اللحظيّ — أمر المالك ٢٠٢٦-٠٩-١٩.

        «قسمك كلّه على تِكّة، ما في دورة — إنت مال.»

        الحكمان نفسهما (`_cap_risk` ثمّ `_trail_structure`) على الصورة
        المحفوظة بسعر التِكّة. فلا منطقَ ثانٍ ولا عتبةٌ تُقرأ مرّتين.
        """
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العرض للشراء والطلب للبيع.
        bid = _to_float(payload.get("bid"))
        ask = _to_float(payload.get("ask"))
        symbol = str(payload.get("symbol") or "").strip()
        account = str(payload.get("account_id") or "").strip()
        if bid is None or ask is None or bid <= 0.0 or ask < bid or not symbol:
            return
        rows = [dict(snap, current_price=(bid if _norm_side(snap.get("side")) == "BUY" else ask))
                for snap in self._snapshots.values()
                if str(snap.get("symbol") or "").strip() == symbol
                and (not account or not str(snap.get("account_id") or "").strip()
                     or str(snap.get("account_id")).strip() == account)]
        if not rows:
            return
        self._tick_checks += 1
        for pos in rows:
            await self._cap_risk(pos)
            await self._trail_structure(pos)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"updates": self._updates, "sent": self._sent,
                   "duplicate_suppressed": self._duplicate_suppressed,
                   "tracked_legs": sum(len(v) for v in self._legs.values())}
        if not self._seen_positions:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_DATA, details=details)
        # ٢٠٢٦-١٠-٢٦ (البند ٩): مركزٌ للمنظومة بلا وقف قائمٌ الآن ⟸ الصحّة متراجعة، والإعلان في آخر الشارة.
        return HealthStatus(state=HealthState.DEGRADED if self._unprotected else HealthState.HEALTHY,
                            # ٢٠٢٦-٠٩-١٨ (ختم NQ): مضاعفُ الهدف وأصغرُ تغييرٍ
                            # مقبول في الوقف معلَنان — عيارٌ لا يُعلَن لا
                            # يُحسَم تعارضُه.
                            message="modify_sent=%d dup_suppressed=%d ترييلنج=%s كبح=%d تضييق=%d توسيع_ملغى=%d %s حمل=%d فوق_السقف=%d %s | سعر=ميتاتريدر بجهة المركز وقف_لم_يُرسَل=%d (%s) | عيار: مضاعف=%g أصغر_تغيير=%g" % (
                                self._sent, self._duplicate_suppressed,
                                "شغّال" if self._trailing_enabled else "موقوف",
                                self._trail_suppressed, self._risk_capped,
                                getattr(self, "_widen_refused", 0), getattr(self, "_last_widen_refused", "-"), getattr(self, "_carry_seen", 0), getattr(self, "_carry_over_cap", 0), getattr(self, "_last_carry", "-"),
                                self._stop_invalid, self._last_invalid,
                                self._reward_risk, self._min_change)
                            + stop_maintenance_guard.health_text(self),
                            details=details)

    # ٢٠٢٦-٠٩-١٦ (فحصٌ شامل لـ٤٥٠–٥٩٩): هذه الذرّة لم يكن لها حفظٌ ولا
    # استعادة، وتحمل حالتين يُغيّر فقدُهما السلوك:
    #
    #   `_capped`   تذاكرُ قُصَّ وقفُها لتجاوزها سقف خسارة المالك. والحارس
    #               `if ticket in self._capped: return` هو ما يمنع تكرار
    #               القصّ — فمسحُه عند الإقلاع يعني **إعادة قصّ الوقف لكل
    #               مركزٍ قائم**، أمرًا لا يحتاجه الوسيط ويردّه أو ينفّذه
    #               مرّتين. وهو نظير علّة ٥٧٤ المقيسة اليوم
    #               (`DUPLICATE_REQUEST_ID`).
    #   `_last_sl`  آخر وقفٍ أُرسل لكل تذكرة — حارس التكرار الذي أُضيف في
    #               v1.2.0 بعد اثنتي عشرة محاولة في الثانية الواحدة.
    #
    # والاستعادة لا تُعيد ما لم يعد قائمًا: `_on_positions` ينظّف التذاكر
    # الغائبة في أوّل دورة، فتذكرةٌ أُغلقت تُسقَط من نفسها.
    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION,
                "sent": self._sent,
                "trailed": self._trailed,
                "risk_capped": self._risk_capped,
                "widen_refused": getattr(self, "_widen_refused", 0),
                "last_widen_refused": getattr(self, "_last_widen_refused", ""),
                "duplicate_suppressed": self._duplicate_suppressed,
                "trail_suppressed": self._trail_suppressed,
                "capped": sorted(self._capped),
                "last_sl": {str(k): v for k, v in self._last_sl.items()},
                **stop_maintenance_guard.snapshot(self)}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        capped = state.get("capped")
        if isinstance(capped, list):
            self._capped = {int(t) for t in capped
                            if isinstance(t, (int, str)) and str(t).lstrip("-").isdigit()}
        last = state.get("last_sl")
        if isinstance(last, dict):
            restored: dict[int, float] = {}
            for ticket, price in last.items():
                value = _to_float(price)
                if value is None or not str(ticket).lstrip("-").isdigit():
                    continue
                restored[int(ticket)] = value
            self._last_sl = restored
        for name in ("sent", "trailed", "risk_capped",
                     "duplicate_suppressed", "trail_suppressed"):
            value = state.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                setattr(self, "_" + name, value)
        stop_maintenance_guard.restore(self, state)
