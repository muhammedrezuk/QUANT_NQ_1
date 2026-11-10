from __future__ import annotations

import math
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.financial_scope import account_broker, financial_key, text
from shared import execution_costs
# ٢٠٢٦-١٠-٠١ (ختم المالك «Nq») — وحدتان شقيقتان نُقلت إليهما أجسادٌ من هذا الملفّ
# حرفيًّا لحدّ ٤٠٠ سطرٍ فعليّ (م٩/ملف٤)، صفر تغيير في السلوك:
#   order_builder_sizing — مدى ٨٠→٩٥ وبدلا التنفيذ والذيل والانزلاق والعمولة بشروحها،
#     واللوت من مسافة الوقف، وتحجيم المسار المباشر، وحارس السقف، والهدف الصافي.
#   order_builder_common — الجهتان، وسبب «فوق السقف»، وسماح السقف، ودقّة التقريب،
#     و`_to_float` — يقرؤها الطرفان فلها نسخةٌ واحدة.
# الأسماء تُستورد هنا كما كانت فسطحُ هذه الوحدة لم يتغيّر، والطرق المنقولة بقيت
# في `Atom` تفويضًا بأسمائها وتواقيعها فلم يتغيّر نداءٌ في `_on_validated`.
from order_builder_common import REASON_LOSS_ABOVE_CAP, SIDE_BUY, SIDE_SELL, _PRICE_DP
from order_builder_common import _RISK_TOLERANCE, _VOLUME_DP, _VOLUME_EPSILON, _to_float
from order_builder_sizing import EXCESS_ALLOWANCE_FRAC, TAIL_SLIPPAGE_FRAC
from order_builder_sizing import UTILISATION_CEILING, UTILISATION_FLOOR
from order_builder_sizing import _MIN_SAMPLES_FOR_DERIVATION, _commission_for
from order_builder_sizing import _has_measured_slippage, _slippage_fracs
import order_builder_sizing

ATOM_VERSION = "5.9.1"

# ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): المسار المحجَّم مغلق — يبني بوقف 513 احتياطًا حين يغيب وقف الطلب (خلاف أمر ٠٩-١٩ «ما في وقف احتياطي»)، ويبني أمر فتحٍ حتّى لطلب إغلاقٍ بلا تذكرة؛ والبنية اليوم مسارٌ واحد: البطاقة 414 تقرّر و555 يرسل الحجم والسعر المرجعيّ دائمًا فيلتقطه المسار المباشر.
# ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): فما يصل هنا يُرفض برفضٍ معلَنٍ معدود بدل أن يُبنى أو ينهار؛ وسطورُ المسار باقيةٌ تحت هذا العلم لا محذوفة، واختباراتها تفتحه صراحةً لتحرس منطقها.
_SIZED_PATH_CLOSED = True
# ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): سقف تحذيرات المسار المغلق في السجلّ — أوّل خمسٍ في كلّ نوبة كسقف الرفض الوارد، والعدّاد في الشارة يحمل الباقي.
_SIZED_CLOSED_WARN_CAP = 5


# 🔴 ٢٠٢٦-٠٩-١٨ — أُعيدت هذه الكتلة من `aa1fdc3~1` بعد أن حذفتُها
# سهوًا: نقلتُ جدولَي الانزلاق والعمولة إلى المشترك بقصّةٍ نصّيّة
# مداها `src.find(...)` إلى أوّل سطرين فارغين، فابتلع القصُّ أربعةً
# وعشرين اسمًا مستعمَلًا معها — كلّ الأحداث والجهات والأسباب.
# والأثر مقيس: `NameError: EVENT_VALIDATED` عند `initialize`، أي أنّ
# ٥٥١ لم يُقلع أصلًا منذ ٠٠:٥٣ — مئة واثنان وثلاثون طلبًا خرجت وصفرُ
# أمرٍ بُني. والقصّ النصّيّ بمدًى محسوب لا يُستعمل ثانيةً في ملفٍّ حيّ.
EVENT_VALIDATED = "risk.validation.completed"
EVENT_SIZE = "risk.position_size.state"
EVENT_SIZE_REJECTED = "risk.position_size.rejected"
EVENT_ACCOUNT = "platform.account.state"
EVENT_OUT = "execution.order.built"
EVENT_DESIRED = "execution.desired.state"
EVENT_SKIPPED = "execution.order.skipped"

ACTION_OPEN = "OPEN"
# SIDE_BUY · SIDE_SELL في order_builder_common.py ويُستوردان أعلاه.

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_INPUT = "NO_INPUT_YET"

REASON_UPSTREAM_REJECTED = "UPSTREAM_REJECTED"
REASON_BAD_SYMBOL_OR_SIDE = "BAD_SYMBOL_OR_SIDE"
REASON_NO_SIZE_YET = "NO_SIZE_YET"
REASON_INCOMPLETE_SIZE_DATA = "INCOMPLETE_SIZE_DATA"
REASON_INVALID_RISK_DISTANCE = "INVALID_RISK_DISTANCE"
# REASON_LOSS_ABOVE_CAP في order_builder_common.py ويُستورد أعلاه.
#: لا هدفَ من التحليل ⟹ لا أمر. رفضٌ لغيابِ مستوًى لا لقصرِ نسبة.
REASON_NO_ANALYSIS_TARGET = "NO_ANALYSIS_TARGET"
# _RISK_TOLERANCE (سقف المخاطرة الصلب) في order_builder_common.py ويُستورد أعلاه.

# NQ seal item 22, package T (T2): 513's real sizing-rejection reason no
# longer disappears silently -- it rides here as an extra, honest field
# alongside our own categorical skip reason. Never invented: only what 513
# itself published on risk.position_size.rejected.

# _PRICE_DP · _VOLUME_DP · _VOLUME_EPSILON في order_builder_common.py وتُستورد أعلاه.

_DIRECT_FIELDS = (
    "request_id", "account_id", "action", "symbol", "side", "volume",
    "reference_price", "stop_loss", "take_profit", "cycle_id", "origin",
    "pair_id", "leg_role", "attempt", "pair_required", "protection_mode",
    "pair_volume", "purpose", "target_net", "current_net", "delta_net",
    "ticket", "params_json", "logical_symbol", "broker_symbol", "asset_canonical",
    "symbol_resolution_status", "symbol_spec", "snapshot_id",
    "risk_budget", "asset_stop_distance", "broker", "magic",
    # v4.3.0 (2026-08-25): the parent-identity chain crosses this hop AS-IS
    # (layer-3 contract). Measured: the three built orders of 08-19..21
    # carried NONE of these although 576 sent them -- 551 dropped the chain,
    # and 552's snapshot-based recovery was impossible (snapshot_id null).
    # Absent stays absent (never invented); present crosses untouched.
    "decision_id", "gate_request_id", "parent_decision_id",
    "owner_command_id", "session_epoch",
    # ٢٠٢٦-٠٩-٠٦ — ورقة ملكية الصفقة (المرحلة هـ · §٦): هوية الفكرة
    # وهندستها تعبران هذه القفزة **كما هما**. 551 يملك حساب الحجم
    # وتقريبه وقيود الوسيط، ولا يملك تغيير إبطال الإعداد ولا هدفه.
    # الحقول تُنقل بلا مساس كي لا تضيع الملكية بين الطبقات (§٢٢).
    "setup_id", "setup_owner", "setup_type",
    "analysis_invalidation", "analysis_target",
    "invalidation_source", "invalidation_reason",
    "target_source", "target_reason",
)

# الحقول التي لا يجوز لـ551 أن يمسّها البتّة — يُحرسها اختبار القبول.
_SETUP_OWNED_FIELDS = (
    "setup_id", "setup_owner", "setup_type",
    "analysis_invalidation", "analysis_target",
    "invalidation_source", "invalidation_reason",
    "target_source", "target_reason",
)


# _to_float في order_builder_common.py ويُستورد أعلاه.


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._magic = 20260801
        self._sizes: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._size_rejections: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._broker_by_account: dict[str, str] = {}
        self._seen = 0
        self._built = 0
        self._skipped = 0
        self._skip_reasons: dict[str, int] = {}
        self._absorbed = 0
        self._last_costs = "-"
        # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): طلباتٌ بلغت المسار المحجَّم المغلق فرُفضت — تُعلَن في الشارة.
        self._sized_closed = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._magic = int(context.config.get("magic",20260801))
        context.subscribe(EVENT_VALIDATED, self._on_validated)
        context.subscribe(EVENT_SIZE, self._on_size)
        context.subscribe(EVENT_SIZE_REJECTED, self._on_size_rejected)
        context.subscribe(EVENT_ACCOUNT, self._on_account)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account_id = text(payload.get("account_id"))
        broker = text(payload.get("broker"))
        if account_id and broker:
            self._broker_by_account[account_id] = broker

    async def _on_size(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        key = financial_key(payload, symbol, self._broker_by_account)
        if key is None:
            return
        if payload.get("status") == "REJECTED":
            return
        # T2: a fresh usable size clears any stale sizing rejection for this
        # scope -- the next skip (if any) must not carry a stale reason.
        self._size_rejections.pop(key, None)
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        self._sizes[key] = {
            "price": _to_float(meta.get("price")),
            "buy_lot": _to_float(meta.get("buy_lot")),
            "buy_stop": _to_float(meta.get("buy_stop")),
            "sell_lot": _to_float(meta.get("sell_lot")),
            "sell_stop": _to_float(meta.get("sell_stop")),
            # معاملات معادلة الحجم — تعبر من 513 كي يُعاد الحساب هنا على
            # مسافة الوقف الفعلية بدل الاعتماد على لوت محسوب لوقف آخر.
            "risk_amount": _to_float(meta.get("risk_amount")),
            "tick_value": _to_float(meta.get("tick_value")),
            "tick_size": _to_float(meta.get("tick_size")),
            "volume_step": _to_float(meta.get("volume_step")),
            "volume_min": _to_float(meta.get("volume_min")),
            "volume_max": _to_float(meta.get("volume_max")),
            "spread": _to_float(meta.get("spread")),
            "slippage_reserve": _to_float(meta.get("slippage_reserve")),
            "commission_per_lot": _to_float(meta.get("commission_per_lot")),
            "max_trade_loss": _to_float(meta.get("max_trade_loss")),
        }

    # ٢٠٢٦-١٠-٠١ (ختم «Nq»): أجساد هاتين الطريقتين والثلاث بعد `_direct_order`
    # نُقلت حرفيًّا بشروحها إلى order_builder_sizing.py. هنا تفويضٌ بالأسماء
    # والتواقيع نفسها لا غير — فالاختبار ينادي `Atom._lot_for_stop` كما كان.
    @staticmethod
    def _value_per_point(size: dict[str, Any]) -> float:
        return order_builder_sizing.value_per_point(size)

    @staticmethod
    def _lot_for_stop(size: dict[str, Any], distance: float) -> float | None:
        return order_builder_sizing.lot_for_stop(size, distance)

    async def _on_size_rejected(self, payload: dict[str, Any]) -> None:
        """T2: remember 513's real sizing-rejection reason per scope, so a
        later skip here (REASON_NO_SIZE_YET) can carry it forward instead of
        losing it -- the reason is exactly what 513 published, never
        invented."""
        if not self._running or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        key = financial_key(payload, symbol, self._broker_by_account)
        if key is None:
            return
        self._size_rejections[key] = {"reason": text(payload.get("reason")) or None}

    def _direct_order(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        symbol = payload.get("symbol")
        side = str(payload.get("side") or "").upper()
        action = str(payload.get("action") or ACTION_OPEN).upper()
        volume = _to_float(payload.get("volume"))
        price = _to_float(payload.get("reference_price"))
        if not symbol or side not in (SIDE_BUY, SIDE_SELL):
            return None
        if volume is None or volume <= 0.0:
            return None
        if action == ACTION_OPEN and (price is None or price <= 0.0):
            return None
        if action != ACTION_OPEN and payload.get("ticket") in (None, "", 0):
            return None
        account = text(payload.get("account_id"))
        broker = text(payload.get("broker")) or self._broker_by_account.get(account, "")
        if not account or not broker:
            return None
        order = {key: payload.get(key) for key in _DIRECT_FIELDS}
        target = _to_float(payload.get("take_profit"))
        target_source = text(payload.get("target_source")) or None
        if target is not None and target > 0.0:
            target_source = target_source or "REQUEST"
            # النسبة تُقاس فقط على الوقف والهدف الواردين؛ لا نرفع الهدف ولا نشتقّ بديلًا.
            stop_ref = _to_float(payload.get("stop_loss"))
            if stop_ref and price:
                risk_d = abs(price - stop_ref)
                if risk_d > 0.0:
                    self._last_ratio = "%s %s %.2fR" % (
                        symbol, side, abs(target - price) / risk_d)
        else:
            # بلا هدف صالح: نبني الحمولة ناقصة، و٥٨٤ يرفضها صراحةً.
            target, target_source = None, None
        order.update({
            "request_id": str(payload.get("request_id", "")),
            "account_id": account, "broker": broker, "magic":self._magic,
            "action": action,
            "symbol": str(symbol), "side": side, "volume": volume,
            "reference_price": round(price, _PRICE_DP) if price is not None else None,
            "stop_loss": payload.get("stop_loss"),
            "take_profit": target,
            "target_source": target_source,
        })
        return order

    # الثلاث التالية أجسادُها في order_builder_sizing.py (انظر أعلاه).
    def _net_target(self, order: dict[str, Any], size: dict[str, Any]) -> None:
        order_builder_sizing.net_target(self, order, size)

    def _resize_direct(self, order: dict[str, Any],
                       payload: dict[str, Any]) -> dict[str, Any] | None:
        return order_builder_sizing.resize_direct(self, order, payload)

    def _verify_costs_within_cap(self, order: dict[str, Any], size: dict[str, Any],
                                distance: float, volume: float) -> dict[str, Any]:
        return order_builder_sizing.verify_costs_within_cap(self, order, size, distance, volume)

    async def _on_validated(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        self._seen += 1
        if not payload.get("approved"):
            # ⚖️ ٢٠٢٦-٠٩-١٨ — الرفض الوارد كان يُبتلع باسمٍ واحد.
            #
            # ٥١٦ ينشر نتيجته **دائمًا** ومعها `reason` صريح (KILL_SWITCH ·
            # RISK_LEDGER_UNKNOWN · RISK_BUDGET_EXCEEDED · MAX_OPEN_TRADES …)،
            # وكنّا نعدّها كلّها `UPSTREAM_REJECTED` ونمضي. فلا سطر في
            # `decisions.db` (لا يُكتب `ORDER_REJECTED` من هنا) ولا سبب في
            # شارة، ولا في سجلّ.
            #
            # وثمنُه مقيس: تسعة طلبات تخرج في سبع دقائق وصفرُ أمرٍ يُبنى،
            # وطاردتُ الوصلة ثلاث مرّات الليلة بين ٥٨٦ و٥٨٥ و٥١٦ — وكلّها
            # سليمة، والسبب كان مكتوبًا في الحمولة التي نرميها.
            #
            # فيُحفظ السبب الوارد بعينه، ويُعلَن في الشارة، ويُسجَّل أوّل
            # خمسٍ منه في كل نوبة (سقفٌ يمنع إغراق المسجّل — درس ٥٨١/٤٥٣).
            upstream = text(payload.get("reason")) or "UNKNOWN"
            self._upstream_reasons = getattr(self, "_upstream_reasons", {})
            self._upstream_reasons[upstream] = self._upstream_reasons.get(upstream, 0) + 1
            self._last_upstream = "%s %s %s" % (
                text(payload.get("symbol")) or "-",
                text(payload.get("side")) or "-", upstream)
            if self._upstream_reasons[upstream] <= 5 and self._context is not None:
                self._context.logger.warning(
                    "551 رفضٌ وارد %s %s: %s (kill_switch=%s request=%s) — "
                    "الأمر لا يُبنى", text(payload.get("symbol")),
                    text(payload.get("side")), upstream,
                    payload.get("kill_switch_state"),
                    text(payload.get("request_id")))
            await self._skip(REASON_UPSTREAM_REJECTED, payload)
            return

        direct = self._direct_order(payload)
        if direct is not None:
            # ٢٠٢٦-٠٩-٠٥ (مقيس، وهو جذر ثبات الحجم عند 0.5): الطلب
            # الاتجاهي يحمل volume وreference_price، فيلتقطه المسار
            # المباشر ويخرج من هنا فورًا — وكل حساب الحجم وحارس السقف
            # أدناه شيفرة ميتة لم تُنفَّذ ولا مرّة. لهذا لم يظهر سطر
            # «551 built» ولا LOSS_ABOVE_CAP في السجلّ رغم ثماني صفقات.
            # النتيجة: الحجم يعبر كما أرسله 581 (سقف الخطوة 0.5) مهما
            # كان بُعد الوقف — قِيست مسافات 17.76 → 56.76 كلّها بـ0.5،
            # وخسائر 10.23 · 11.34 · 15.26 فوق سقف المالك.
            # الحجم يُعاد حسابه هنا على مسافة وقف الأمر نفسه.
            direct = self._resize_direct(direct, payload)
            if direct is None:
                return
            await self._context.publish(EVENT_OUT, direct)
            await self._publish_desired(direct)
            self._built += 1
            return

        side = str(payload.get("side", "")).upper()
        symbol = payload.get("symbol")
        if not symbol or side not in (SIDE_BUY, SIDE_SELL):
            await self._skip(REASON_BAD_SYMBOL_OR_SIDE, payload)
            return
        symbol = str(symbol)
        # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): المسار المحجَّم مغلق (انظر `_SIZED_PATH_CLOSED`) — رفضٌ معلَن معدود قبل أيّ بحثٍ عن حجم 513 أو وقفه.
        if _SIZED_PATH_CLOSED:
            self._sized_closed += 1
            if self._sized_closed <= _SIZED_CLOSED_WARN_CAP and self._context is not None:
                self._context.logger.warning(
                    "551 رفض %s %s (action=%s ticket=%s request=%s): طلبٌ بلا حجم أو بلا سعر "
                    "مرجعيّ (أو إغلاقٌ بلا تذكرة) — لا يُبنى أمرٌ من حجم 513 ولا من وقفه "
                    "(أمر المالك ٠٩-١٩)", symbol, side, payload.get("action"),
                    payload.get("ticket"), text(payload.get("request_id")))
            await self._skip(REASON_INCOMPLETE_SIZE_DATA, payload)
            return
        account = text(payload.get("account_id"))
        broker = text(payload.get("broker")) or self._broker_by_account.get(account, "")
        scope = (account, broker, symbol) if account and broker else None
        size = self._sizes.get(scope) if scope else None
        if size is None:
            rejection = self._size_rejections.get(scope) if scope else None
            await self._skip(REASON_NO_SIZE_YET, payload,
                              sizing_reason=rejection.get("reason") if rejection else None)
            return
        price = size.get("price")
        volume = size.get("buy_lot") if side == SIDE_BUY else size.get("sell_lot")
        stop = size.get("buy_stop") if side == SIDE_BUY else size.get("sell_stop")
        if price is None or volume is None or stop is None or volume <= 0.0:
            await self._skip(REASON_INCOMPLETE_SIZE_DATA, payload)
            return
        # ٢٠٢٦-٠٩-٠٥ (مقيس على الحساب): الطلب يصل بوقف وهدف محسوبين من
        # مستويات بنيوية (مخاطرة 7.4 مقابل عائد 32.5 = نسبة 4.4)، وكان
        # يُستبدلان هنا بوقف 513 البعيد (74,655 على سعر 79,655 = 6.3%)
        # وهدف بنسبة ثابتة — فتنهار النسبة إلى 0.004 بعد حسابها. وقف
        # الطلب البنيوي يُحترم متى جاء صالحًا؛ وقف التحجيم يبقى الاحتياط.
        requested_stop = _to_float(payload.get("stop_loss"))
        requested_target = _to_float(payload.get("take_profit"))
        if requested_stop is not None and requested_stop > 0.0:
            valid = (requested_stop < price) if side == SIDE_BUY else (requested_stop > price)
            if valid:
                stop = requested_stop
        risk_dist = (price - stop) if side == SIDE_BUY else (stop - price)
        if risk_dist <= 0.0:
            await self._skip(REASON_INVALID_RISK_DISTANCE, payload)
            return
        # 🔴 ٢٠٢٦-٠٩-١٩ (أوامر المالك) — «ولا هدف احتياطي أو هدف صلب،
        # احذفو» و«حارس يستلم صفقة فيها هدف وستوب تمرق، ما فيها ترد».
        #
        # كان هنا ثلاثةُ مصادرَ للهدف يعلو بعضُها بعضًا: المضاعف الثابت
        # (`REWARD_MULTIPLE_FALLBACK`)، ثمّ هدف ٥٢٦ المشتقّ، ثمّ هدف الطلب.
        # ثمّ يُفرض الأوّل **أرضيّةً** بعدها جميعًا، فيُرفض كلُّ هدفٍ من
        # تحليلٍ قصَر عنه بـ`TARGET_BELOW_REWARD_MULTIPLE`.
        #
        # الهدف لا يُشتقّ هنا؛ النسبة تُقاس وتُسجّل فقط.
        # مستوًى — وهو الوجهُ الآخر لوقف ‎0.107٪‎: رقمان مصنوعان عندنا
        # يحملان اسم فكرةٍ ليست لنا.
        #
        # صار الهدف من الطلب حصرًا — وهو هدف التحليل الذي مرّره ٥٥٥ بعد
        # أن صار يأخذه من الإعداد وحده. وما لا هدف له يُرفض ولا يُخترع له.
        # و٥٢٦ يُؤرشف بأمر المالك، فمصدره يسقط معه.
        target = None
        target_source = None
        if requested_target is not None and requested_target > 0.0:
            valid_t = (requested_target > price) if side == SIDE_BUY else (requested_target < price)
            if valid_t:
                target = requested_target
                target_source = "REQUEST"
        # ولا هدفَ ⟹ لا أمر. الرفضُ هنا لغيابِ مستوًى لا لقصرِ نسبة:
        # حارسُ الأرضيّة (`TARGET_BELOW_REWARD_MULTIPLE`) سقط بأمر المالك،
        # وكان يردّ هدفَ التحليل نفسَه إن قصَر عن مضاعفٍ من الإعداد.
        if target is None:
            risk_d = abs(price - stop) if (price and stop) else 0.0
            got = (abs(requested_target - price) / risk_d) if (
                requested_target and risk_d > 0.0) else -1.0
            self._last_reject = "%s %s بلا هدفٍ صالح (وارد=%s)" % (
                symbol, side, requested_target)
            await self._skip(REASON_NO_ANALYSIS_TARGET, payload)
            if self._context is not None:
                self._context.logger.warning(
                    "551 رفض %s %s: لا هدف من التحليل — الوارد %s وسعرُ "
                    "المرجع %s، ولا يُخترع هدف", symbol, side,
                    requested_target, price)
            return
        # والنسبة تُقاس وتُعلَن ولا تحكم — أمر المالك ٢٠٢٦-٠٩-١٩.
        risk_d = abs(price - stop) if (price and stop) else 0.0
        if risk_d > 0.0:
            self._last_ratio = "%s %s %.2fR" % (
                symbol, side, abs(target - price) / risk_d)
        # حكم المالك ٢٠٢٦-٠٩-٠٥: «وقف الخسارة لازم ينحسب على معادلة حجم
        # لوت». اللوت الوارد من 513 محسوب على وقف 513؛ متى تغيّر الوقف
        # وجب أن يتغيّر معه اللوت، وإلا صارت المخاطرة الفعلية رقمًا آخر
        # غير الميزانية. يُعاد الحساب هنا على المسافة النهائية، وسقف
        # خطوة 581 (volume في الطلب) يبقى حدًّا أعلى لا يُتجاوز.
        # تكاليف العبور المقيسة في الطلب تسبق ما نشره 513: 513 يستمع إلى
        # market.tick.validated (بلا bid/ask) فيرسل السبريد صفرًا، بينما
        # 581 يقيسه من تِكّة الوسيط نفسها.
        req_spread = _to_float(payload.get("spread"))
        req_slip = _to_float(payload.get("slippage_reserve"))
        if req_spread is not None and req_spread > 0.0:
            size = dict(size)
            size["spread"] = req_spread
            if req_slip is not None:
                size["slippage_reserve"] = req_slip
        sized = self._lot_for_stop(size, risk_dist)
        if sized is not None:
            volume = sized
        elif self._context is not None:
            # مقيس ٢٠٢٦-٠٩-٠٥ على التذكرة 1911030333: بُني لوت 0.5 على وقف
            # 30 نقطة = 15$ — فوق سقف المالك — فاضطُرّ 577 إلى تضييق الوقف
            # بعد الفتح فمات التحليل وضُرب الوقف (-9.90). اللوت يجب أن
            # يُصغَّر قبل الإرسال؛ فشل حسابه يجب أن يُرى بأسمائه لا يمرّ.
            self._context.logger.warning(
                "551 sizing fallback %s: risk_amount=%r tick_value=%r "
                "tick_size=%r max_loss=%r spread=%r volume=%r dist=%.2f",
                symbol, size.get("risk_amount"), size.get("tick_value"),
                size.get("tick_size"), size.get("max_trade_loss"),
                size.get("spread"), volume, risk_dist)
        step_cap = _to_float(payload.get("volume"))
        if step_cap is not None and step_cap > 0.0:
            volume = min(volume, step_cap)
        volume = round(volume, _VOLUME_DP)
        if volume <= 0.0:
            await self._skip(REASON_INCOMPLETE_SIZE_DATA, payload)
            return
        # حارس نهائي على حكم المالك «ما في صفقة تضرب ستوب أكثر من ١٠
        # دولار»: تُحسب الخسارة الكلّية بالحجم النهائي، وما يتجاوز السقف
        # لا يُرسَل. بلا هذا الحارس مرّت التذكرة 1911030333 بلوت 0.5 على
        # وقف 30 نقطة (15$)، فصحّحها 577 بتضييق الوقف بعد الفتح — أي
        # بقتل التحليل بدل تصغير الحجم.
        tick_value = size.get("tick_value")
        tick_size = size.get("tick_size")
        cap = size.get("max_trade_loss")
        if cap and tick_value and tick_size:
            effective = risk_dist + (size.get("spread") or 0.0) \
                + (size.get("slippage_reserve") or 0.0)
            loss = volume * effective * tick_value / tick_size \
                + volume * (size.get("commission_per_lot") or 0.0)
            if loss > cap * _RISK_TOLERANCE:
                await self._skip(REASON_LOSS_ABOVE_CAP, payload)
                if self._context is not None:
                    self._context.logger.warning(
                        "551 skip %s: LOSS_ABOVE_CAP loss=%.2f cap=%.2f "
                        "volume=%s dist=%.2f", symbol, loss, cap, volume, risk_dist)
                return
        order = {
            "request_id": str(payload.get("request_id", "")),
            "account_id": account, "broker": broker, "magic":self._magic,
            "action": ACTION_OPEN, "symbol": symbol, "side": side,
            "volume": volume, "reference_price": round(price, _PRICE_DP),
            "stop_loss": round(stop, _PRICE_DP),
            "take_profit": round(target, _PRICE_DP),
            # ٢٠٢٦-٠٩-٠٧ — الحقل كان معلنًا في العقد ولا يُملأ. مصدر الهدف
            # يُعلَن كي يُعرف على أيّ أساس بُني: هدف 526 المقيس، أم هدف
            # الطلب البنيويّ، أم المضاعف الثابت الاحتياطيّ.
            "target_source": target_source,
            # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): كان `(owned or {}).get(...)` و`owned` حُذف تعريفه مع هدف 526 (٠٩-١٩) فينفجر NameError؛ لا مضاعف هدفٍ بعد اليوم، فالحقل فارغٌ صريح.
            "reward_multiple": None,
            "cycle_id": str(payload.get("cycle_id", "")),
        }
        # v4.3.0: parent-identity chain passthrough (layer-3 contract) --
        # present fields cross untouched, absent fields stay absent.
        for chain_field in ("decision_id", "gate_request_id",
                            "parent_decision_id", "owner_command_id",
                            "session_epoch"):
            if payload.get(chain_field) is not None:
                order[chain_field] = payload[chain_field]
        # ٢٠٢٦-٠٩-٠٥ (مقيس على ٨ صفقات): الحجم خرج 0.5 في كلّها بينما
        # مسافات الوقف تراوحت 17.76 → 56.76 — أي أن المعادلة لم تحكم.
        # مكوّناتها تُطبع مع كل أمر كي يُعرف أيّ حدّ هو الذي قصّ الحجم:
        # المحسوب من الوقف، أم سقف خطوة 581، أم لوت 513 الاحتياطي.
        self._context.logger.warning(
            "551 built %s %s: volume=%s sized=%s step_cap=%s dist=%.2f "
            "spread=%s slip=%s cap=%s vpp=%s",
            symbol, side, volume, sized, step_cap, risk_dist,
            size.get("spread"), size.get("slippage_reserve"),
            size.get("max_trade_loss"),
            (size.get("tick_value") / size.get("tick_size"))
            if size.get("tick_value") and size.get("tick_size") else None)
        await self._context.publish(EVENT_OUT, order)
        await self._publish_desired(order)
        self._built += 1

    async def _skip(self, reason: str, payload: dict[str, Any],
                    sizing_reason: str | None = None) -> None:
        self._skipped += 1
        self._skip_reasons[reason] = self._skip_reasons.get(reason, 0) + 1
        if self._context is None:
            return
        if self._skipped <= 25:
            self._context.logger.warning(
                "551 skip reason=%s symbol=%s account=%s side=%s approved=%r "
                "origin=%s sizes_keys=%s", reason, payload.get("symbol"),
                payload.get("account_id"), payload.get("side"),
                payload.get("approved"), payload.get("origin"),
                list(self._sizes)[:4])
        body = {
            "reason": reason,
            "symbol": payload.get("symbol"),
            "account_id": payload.get("account_id"),
            "request_id": str(payload.get("request_id", "")),
            "cycle_id": str(payload.get("cycle_id", "")),
            # T2: the skipped request keeps its decision identity when the
            # input carried one -- absent stays None, never invented.
            "decision_id": payload.get("decision_id"),
            "gate_request_id": payload.get("gate_request_id"),
        }
        if sizing_reason:
            # T2: 513's real sizing-rejection reason, passed through as-is
            # instead of disappearing behind our own NO_SIZE_YET category.
            body["sizing_reason"] = sizing_reason
        await self._context.publish(EVENT_SKIPPED, body)

    async def _publish_desired(self, order: dict[str, Any]) -> None:
        if self._context is None:
            return
        leg = dict(order)
        leg["leg_id"] = order.get("request_id") or order.get("symbol")
        leg["entry_price"] = order.get("reference_price")
        await self._context.publish(EVENT_DESIRED, {
            "account_id": order.get("account_id"), "broker": order.get("broker"),
            "symbol": order.get("symbol"),
            "asset_canonical": order.get("symbol"),
            "legs": [leg], "leg_id": leg["leg_id"],
            "entry_price": leg["entry_price"], "version": self._built + 1,
            "pair_id": order.get("pair_id"),
            "leg_role": order.get("leg_role"),
        })

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"seen": self._seen, "built": self._built, "skipped": self._skipped,
                   "sized_path_closed": self._sized_closed,
                   "skip_reasons": dict(self._skip_reasons),
                   "sized_scopes": len(self._sizes),
                   "accounts_with_broker": len(self._broker_by_account)}
        if self._seen == 0:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_AWAITING_FIRST_RISK_VALIDATION | built=0 skipped=0",
                                details=details)
        # ٢٠٢٦-١٠-٠٨ (ختم المالك «nq»): «محجَّم_مغلق» عددُ ما بلغ المسار المغلق فرُفض — لا يختفي داخل `skipped`.
        return HealthStatus(state=HealthState.HEALTHY,
                            message="built=%d skipped=%d محجَّم_مغلق=%d سليم=%d | %s | آخر_رفض=%s" % (
                                self._built, self._skipped, self._sized_closed,
                                getattr(self, "_passed_intact", 0),
                                getattr(self, "_last_costs", "-"),
                                getattr(self, "_last_reject", "-")) + " | انزلاق=%s صافي=%d %s | وارد=%s آخره=%s | سحر=%d" % (getattr(self, "_slip_source", "-"), getattr(self, "_net_targets", 0), getattr(self, "_last_net", "-"), (" ".join("%s:%d" % kv for kv in sorted(getattr(self, "_upstream_reasons", {}).items(), key=lambda kv: -kv[1])[:3]) or "-"), getattr(self, "_last_upstream", "-"), self._magic),
                            details=details)
