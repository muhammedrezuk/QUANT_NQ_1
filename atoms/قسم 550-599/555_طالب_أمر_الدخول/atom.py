"""طالب أمر الدخول (555) — من قرارٍ مُوافَق إلى طلب أمر.

**الحلقة التي كانت مفقودة.** ثلاثة ناشرين وحدهم يُصدرون
`execution.order.requested`: 576 و578 (محرّكا الزوج المحايد، مغلقان بأمر
المالك) و581 (يبني أهدافًا لا طلبات). فبقي مسار الستوب والهدف بلا مُصدِر:
القرار يُوافَق، والحجم يُحسب، والهدف يُبنى — ولا أمر يُطلب.

مقيس ٢٠٢٦-٠٩-٠٧: `466 approved=193` · `513 sized=583`؛
الهدف التحليلي لا يصل ⇒ الطلب يُرفض بدل اختراع هدف.

## ماذا تفعل

تجمع ثلاثة مدخلات لنطاق واحد (حساب · وسيط · رمز) وتُصدر الطلب:

    466 ──decision.gate.passed──►  الجهة والسلطة
    513 ──risk.position_size.state──►  اللوت والوقف
    strategy.setup.proposed ──►  الستوب والهدف التحليلي
                    ↓
          execution.order.requested
                    ↓
        527 → 526 → 516 → 551 → 525 → 552 → 601

## الدخول الأوّل وحده

`max_open_per_symbol = 0` — لا تُصدر طلبًا لرمزٍ له مركز مفتوح. الإضافة على
مركز قائم شأن 581 (محرك فرق المركز)، وازدواج المُصدِرين على الرمز نفسه
يفتح مركزين لا واحدًا.

## ما لا تفعله

**لا تحكم على جدوى القرار.** الموافقة جاءت من 466 بعد 454 و458، وإعادة
الحكم هنا تكرار. تتحقّق من **اكتمال المدخلات** لا من صوابها، وكل تعذّر
يُعلَن على `execution.entry.state` بسببه ويُحصى — لا إسقاط صامت.

**ولا تخترع سلطة.** `parent_decision_id` يُنقل من القرار كما ورد؛ فبلا
سلطة يرفض 552 الأمر، وهذا صواب لا عطل.
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthStatus
from shared import execution_costs
try:  # a hot reload keeps the old shared module in memory until restart -- the gate must not fall with it
    from shared.market_clock import no_trade_day
except ImportError:  # noqa: BLE001
    no_trade_day = None
try:  # new module (2026-10-17): loads fresh even on a hot reload, guarded all the same
    from shared.red_lines import entry_block
except ImportError:  # noqa: BLE001
    entry_block = None
import entry_request_lines
from shared.trade_setup import (EVENT_SETUP, is_alive, is_target_reached,
                                validate_setup,
                                OK as SETUP_OK)
# v1.24.1 (٢٠٢٦-١٠-٠١، ختم `Nq`) — حدّ المادة 9 (٤٠٠ سطر فعليّ): نُقلت أجزاءٌ
# **حرفيًّا** إلى ملفّاتٍ شقيقة في مجلّد الذرّة، والتوابعُ بأسمائها باقيةٌ هنا
# تُحيل إليها. لا سلوك جديد. (الحجم ⟵ sizing · المدخلات ⟵ inputs ·
# الإعدادات ⟵ setups · جسد الطلب ⟵ order · نصّ الشارة ⟵ badge)
from entry_request_sizing import _lot_for_stop, _number, _size_view, _text
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حكما الإرسال (النسبة ≥ 3 بعد السبريد ·
# الوقف ≥ 10 ن.أ) يُحسبان في الملفّ الشقيق بمعادلة الاستراتيجيّات نفسها.
from entry_request_sizing import send_economics
from entry_request_inputs import _REJECT_RETRY_AFTER_S
from entry_request_order import ACTION_OPEN, ORIGIN, PRICE_DP, PROTECTION_STOP_TARGET
import entry_request_badge
import entry_request_inputs
import entry_request_order
import entry_request_setups
import entry_request_state

ATOM_VERSION = "1.31.0"
#: ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك وجوابه، ختم «NQ»: «لازم يعرف صفقات مالك وما يفتح شي على اي زوج عليه صفقة مني»): هنا وحده
#: تُقرأ صفقات المالك، ولغرضٍ واحد: لا دخول بأيّ جهة على رمزٍ عليه صفقةٌ مفتوحة للمالك، في أيّ حساب. وكلّ عدّاتها الأخرى
#: — مراكز الرمز في الحساب، والجهة المعاكسة في حسابٍ آخر، والمركز الخاسر في حسابٍ آخر — للمنظومة وحدها
#: (`entry_request_inputs.on_positions` و`entry_request_lines.on_positions`، بالتمييز الواحد في `shared/owner_trades.py`).
#: والردّ في `entry_request_lines.wait_block` بسببه `OWNER_POSITION_OPEN` (حدّ الأربع مئة سطر في هذا الملفّ).
#: مهلةٌ بين دخولين على الرمز نفسه — جاءت من المستودع (فرعٌ آخر، ٠٩-٢٠)
#: ودُمجت هنا. تمنع تكرار **الدخول على الرمز** ولو بفكرةٍ جديدة، بينما
#: استهلاكُ الإعداد أدناه يمنع تكرار **الفكرة** ولو تباعد الدخولان.
#: حارسان لبابين مختلفين، لا واحدٌ مكرَّر.
ENTRY_COOLDOWN_S = 45.0

EVENT_DECISION = "decision.gate.passed"
EVENT_SIZE = "risk.position_size.state"
EVENT_ACCOUNT = "platform.account.state"
EVENT_POSITIONS = "platform.positions.state"
EVENT_HALT = "emergency.halt"
EVENT_RESET = "risk.kill_switch.reset_requested"

EVENT_REJECTED = "execution.order.rejected"
EVENT_REQUEST = "execution.order.requested"
EVENT_STATE = "execution.entry.state"

SIDE_BUY = "buy"
SIDE_SELL = "sell"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_HALTED = "EMERGENCY_HALT"
REASON_NO_SIDE = "DECISION_SIDE_UNKNOWN"
REASON_NO_SIZE = "NO_SIZE_FOR_SCOPE"
REASON_SIZE_STALE = "SIZE_STALE"
REASON_NO_VOLUME = "NO_EXECUTABLE_VOLUME"
REASON_NO_STOP = "NO_STOP_FOR_SIDE"
REASON_NO_TARGET = "NO_TARGET_FOR_SIDE"
#: هدفٌ وصل دون ١/٣. حكم المالك ٢٠٢٦-٠٩-١٨: يُرفض ولا يُرفع إلى قالب.
REASON_TARGET_BELOW_FLOOR = "TARGET_BELOW_MIN_REWARD"
#: قياسُ الهندسة على مرجع البناء يفتح بابًا لم يكن مفتوحًا: إعدادٌ بلغ
#: السعرُ هدفَه بعد بنائه تبقى هندسته سليمة على مرجعه، فيمرّ بلا عائدٍ
#: باقٍ. الحارس قائمٌ في مسار ٥٨١ (`position_delta_recompute.py:554`)
#: وكان غائبًا عن هذا المسار. يُغلق البابُ قبل أن يُفتح.
REASON_TARGET_REACHED = "TARGET_ALREADY_REACHED"
#: هامش عائم عند مقارنة المضاعف بالأرضيّة — هدفٌ بـ2.9999999R بسبب
#: تقريب السعر ليس هدفًا مخالفًا.
_REWARD_EPSILON = 1e-9
REASON_POSITION_OPEN = "POSITION_ALREADY_OPEN"
#: 2026-10-23 (sealed red lines, law 13 -- "hedging is forbidden in every form"): the opposite side of the symbol is open in
#: another account. The same account is already held by `max_open_per_symbol = 0`.
REASON_HEDGE_OTHER_ACCOUNT = "HEDGE_WITH_OTHER_ACCOUNT"
REASON_POSITIONS_UNKNOWN = "POSITIONS_UNKNOWN"
REASON_IN_FLIGHT = "REQUEST_IN_FLIGHT"
REASON_NO_IDENTITY = "NO_ACCOUNT_OR_BROKER"
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): سببا الردّ عند الإرسال — تُرجعهما
# `entry_request_sizing.send_economics` بهذين الاسمين حرفًا.
REASON_RR_AT_SEND = "RR_BELOW_MIN_AT_SEND"
REASON_STOP_AT_SEND = "STOP_BELOW_10BPS_AT_SEND"
#: 1.26.0 (2026-10-17, owner seal): the days law -- no entry on any symbol (bitcoin included) on a US exchange or bank holiday or an
#: early-close day (15 a year), by the broker day (`shared.market_clock.no_trade_day`).
REASON_NO_TRADE_DAY = "NO_TRADE_DAY"
#: 2026-10-17 (owner seal): the red lines -- no entry outside the asset's window and none inside a red news window, as 109
#: announces it. 2026-10-23 (sealed red lines): no symbol on Saturday or Sunday, bitcoin included (law 23); the news window is
#: 15 minutes either side of a red item of any currency the asset holds, USD for every symbol (laws 24-25).
#: Reasons: `shared.red_lines.REASON_WINDOW` / `REASON_NEWS`.
EVENT_PULSE = "SYS_SECOND"
EVENT_CALENDAR = "market_data.calendar.state"
#: 2026-10-17 (owner seal, steps 6-11): every asset on its own exchange's window, the first 15 minutes of it closed
#: (`shared.red_lines.entry_block`), and the waits after a trade (`entry_request_lines`) -- full closes come from 611.
#: 2026-10-25 (owner seal, laws 17 and 21): no new entry in the last hour of the asset's window (`entry_block`); the general
#: window closes at 16:00 New York. The five-day range from 124 fed only the time-enough check, which is gone.
EVENT_TRADE = "platform.trade_event"
#: 2026-10-23 (sealed red lines, laws 7-10): 509's account limits -- the total drawdown, the global daily and each pair's
#: daily limit refuse entries here (`entry_request_lines.wait_block`); a missing or stale state refuses too.
EVENT_LIMITS = "risk.account_limits.state"


def _side_of(payload: dict[str, Any]) -> str:
    """جهة القرار بأسمائها الأربعة — لا باسم واحد.

    ٢٠٢٦-٠٩-٠٩ (ختم المالك `NQ`): كانت تُقرأ `side` وحدها، و**467 ينشر على
    `decision.gate.passed` باسم `decision_side`** (`467/atom.py:129`). فوصل
    القرار المُوافَق ويده فارغة: المقيس حيًّا `467 passed=10` و
    `555 seen=10 emitted=0 blocked=10 last=DECISION_SIDE_UNKNOWN`، والحمولة
    على `execution.entry.state` تقول `"side": ""` حرفًا. **عشرة قرارات
    مُوافَقة سقطت على اسم حقل.**

    ولم يكشفه اختبار لأنّ اختبارات هذه الذرّة تبني القرار بـ`side` — أي
    بحمولة لا ينشرها ناشرها الحقيقيّ، فمرّت كلّها والذرّة لا تصدر شيئًا حيًّا.

    و**581 يقرؤها صوابًا** بثلاثة أسماء (`581/atom.py:122`) وهو الوحيد
    العامل (`targets=16,845`). أمّا 576 و578 و580 فتقرأ `side` وحدها —
    وثلاثتها مغلقة بأمر المالك، فوُلدت 555 على نمط الميت.

    الترتيب هنا كترتيب 581، و`side` يبقى آخرًا للتوافق مع أيّ ناشر يستعمله.
    """
    raw = (payload.get("decision_side") or payload.get("direction")
           or payload.get("signal") or payload.get("side"))
    return _text(raw).lower()


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._size_stale_after_s = 30.0
        self._target_stale_after_s = 30.0
        self._max_open_per_symbol = 0
        self._positions_seen = False
        self._inflight: dict[str, float] = {}
        # كبح الدخول العام المشترك لكل حساب×رمز. هذا الحارس يمنع مسار 555
        # من الالتفاف على كبح 581 عندما تُغلق صفقة ثم يُعاد طلب الدخول فورًا.
        # الزمن محفوظ بالثانية الرسمية حتى لا يضيع عند Hot Reload.
        self._last_request_at: dict[str, float] = {}
        self._inflight_ttl_s = 90.0
        self._min_reward = 3.0
        self._setups: dict[tuple[str, str], dict] = {}
        self._setup_missing = 0
        self._setup_dead = 0
        self._geometry_at_build = 0
        self._target_reached = 0
        # ⚖️ ٢٠٢٦-٠٩-١٩ — عدّادٌ لا يُستعاد، بجانب التراكميّ الذي يُستعاد.
        #
        # `seen` و`emitted` و`blocked` تعبر الإقلاعات عبر `restore`، وجيرانُ
        # هذه الذرّة يبدأون من صفر. فمقارنةُ رقمي برقمهم تقارن تاريخًا
        # بلحظة. وقعتُ فيها مرّتين في يومٍ واحد: قرأتُ `emitted=750` مقابل
        # `586 seen=1` فظننتُ السلسلة مقطوعة وهي سليمة، ثمّ قرأتُ «صفر
        # إعداد وارد» من عدّادٍ عمره دقائق فقلتُها «اليوم» وهي خطأ —
        # والقرص كذّبني: إعدادٌ وصل الساعة 14:31.
        #
        # ولا يُحفظ في اللقطة عمدًا: قيمته أنّه يموت مع كلّ إقلاع.
        self._seen_boot = 0
        self._emitted_boot = 0
        self._reason_tally: dict[str, int] = {}
        self._setup_refused = 0
        self._setup_taken = 0
        # لماذا لم يصل وقفُ التحليل؟ ثلاثةُ أسبابٍ كانت تُبتلع في سقوطٍ
        # واحدٍ صامتٍ إلى الاحتياطيّ. تُفرَّق كي يُعرف أيُّها يحجب فعلًا.
        self._setup_consumed = 0
        self._last_consumed = ""
        self._stop_no_setup = 0
        self._stop_no_level = 0
        self._stop_wrong_side = 0
        self._last_stop_reject = ""
        self._refuse_why: dict[str, int] = {}
        self._last_refused = ""
        self._last_drift = ""
        self._last_reached = ""
        self._setup_used = 0
        #: ٢٠٢٦-٠٩-٢٣ — من أين جاءت المستويات: مختومةً على القرار أم من
        #: المخزون. تعهُّدٌ لجلسة التحليل كي نقرأ التحوّلَ بالرقم لا بالظنّ،
        #: ويوم يصير `مخزون=0` يسقط الوصلُ بالمطابقة من هذه الذرّة كلَّها.
        self._levels_inline = 0
        self._levels_stored = 0
        self._resized = self._resize_failed = 0
        self._last_resize = ""
        self._sizes: dict[str, dict[str, Any]] = {}
        self._brokers: dict[str, str] = {}
        self._open_counts: dict[str, int] = {}
        # 2026-10-23 (law 13): open positions per account, and the sides held per account and symbol.
        self._open_by_account: dict[str, dict[str, int]] = {}
        self._sides_by_account: dict[str, dict[str, set[str]]] = {}
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): كان `_halted` مفتاحًا عامًّا واحدًا
        # يفكّه إفراجُ أيّ حساب. صار إيقافًا عامًّا + مجموعة حسابات — الدلالة كاملةً
        # في `entry_request_inputs.on_halt`، و`_halted` أدناه قراءةٌ لا حالة.
        self._halt_all = False
        # ٢٠٢٦-١٠-٠٢ v1.25.1: إيقافٌ عامّ قادمٌ من لقطةٍ قديمة — يفكّه أيّ تحريرٍ كما كان قبل 1.25.0
        # (انظر entry_request_inputs.on_reset)، لا تحريرُ المالك وحده.
        self._halt_legacy = False
        self._halted_accounts: set[str] = set()
        self._send_blocked: dict[str, int] = {}
        self._last_send_block = ""
        self._official_time = 0.0
        self._pulse_seen_at = 0.0   # monotonic arrival of the last pulse: its age, not a stamp
        self._gate_missing = no_trade_day is None or entry_block is None
        self._calendar: dict[str, Any] | None = None
        self._limits: dict[str, Any] | None = None
        self._seen = 0
        self._emitted = 0
        self._blocked = 0
        self._inflight_cleared = 0
        self._last_reason = ""

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config
        self._size_stale_after_s = float(cfg["size_stale_after_s"])
        self._target_stale_after_s = float(cfg["target_stale_after_s"])
        self._max_open_per_symbol = int(cfg["max_open_per_symbol"])
        self._inflight_ttl_s = float(cfg["inflight_ttl_s"])
        self._min_reward = float(cfg["min_reward_multiple"])
        context.subscribe(EVENT_DECISION, self._on_decision)
        context.subscribe(EVENT_SIZE, self._on_size)
        context.subscribe(EVENT_ACCOUNT, self._on_account)
        context.subscribe(EVENT_POSITIONS, self._on_positions)
        context.subscribe(EVENT_REJECTED, self._on_rejected)
        context.subscribe(EVENT_SETUP, self._on_setup)
        context.subscribe(EVENT_HALT, self._on_halt)
        context.subscribe(EVENT_RESET, self._on_reset)
        context.subscribe(EVENT_PULSE, self._on_pulse)
        context.subscribe(EVENT_CALENDAR, self._on_calendar)
        context.subscribe(EVENT_TRADE, self._on_trade)
        context.subscribe(EVENT_LIMITS, self._on_limits)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _scope(self, payload: dict[str, Any]) -> str:
        return entry_request_inputs.scope(self, payload)

    async def _on_account(self, payload: dict[str, Any]) -> None:
        await entry_request_inputs.on_account(self, payload)

    def _inflight_for(self, symbol: str) -> int:
        return entry_request_inputs.inflight_for(self, symbol)

    # الخانة لكلّ (رمز × جهة)، ومستويات القرار أوّلًا ثمّ الخانة — الشرح
    # والتاريخ مع الدوالّ نفسها في `entry_request_setups.py`.
    async def _on_setup(self, payload: dict) -> None:
        await entry_request_setups.on_setup(self, payload)

    def _levels_on_decision(self, payload: dict[str, Any]):
        return entry_request_setups.levels_on_decision(self, payload)

    def _setup_levels(self, symbol: str, side: str):
        return entry_request_setups.setup_levels(self, symbol, side)

    async def _on_positions(self, payload: dict[str, Any]) -> None:
        await entry_request_inputs.on_positions(self, payload)
        entry_request_lines.on_positions(self, payload)

    async def _on_trade(self, payload: dict[str, Any]) -> None:
        entry_request_lines.on_trade(self, payload, self._official_time or time.time())

    # الرفض يحرّر الرمز إلى عمر صلاحيّة المرجع — الشرح مع الدالّة في
    # `entry_request_inputs.py`.
    async def _on_rejected(self, payload: dict[str, Any]) -> None:
        await entry_request_inputs.on_rejected(self, payload)

    @property
    def _halted(self) -> bool:
        """هل في الذرّة إيقافٌ قائم — عامٌّ أو لحسابٍ واحد على الأقلّ؟"""
        return self._halt_all or self._halt_legacy or bool(self._halted_accounts)

    async def _on_halt(self, payload: dict[str, Any]) -> None:
        await entry_request_inputs.on_halt(self, payload)

    async def _on_reset(self, payload: dict[str, Any]) -> None:
        await entry_request_inputs.on_reset(self, payload)

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        official = _number(payload.get("official_time")) if isinstance(payload, dict) else None
        if official is not None and official > 0:
            self._official_time = official
            self._pulse_seen_at = time.monotonic()

    async def _on_calendar(self, payload: dict[str, Any]) -> None:
        if isinstance(payload, dict):
            self._calendar = dict(payload)

    async def _on_limits(self, payload: dict[str, Any]) -> None:
        if isinstance(payload, dict):
            self._limits = dict(payload)

    async def _on_size(self, payload: dict[str, Any]) -> None:
        await entry_request_inputs.on_size(self, payload)

    async def _decline(self, reason: str, payload: dict[str, Any],
                       extra: dict[str, Any] | None = None) -> None:
        self._blocked += 1
        self._last_reason = reason
        self._reason_tally[reason] = self._reason_tally.get(reason, 0) + 1
        if self._context is None:
            return
        body = {"account_id": payload.get("account_id"),
                "broker": payload.get("broker"),
                "symbol": payload.get("symbol"),
                "requested": False, "reason": reason}
        if extra:
            body.update(extra)
        await self._context.publish(EVENT_STATE, body)

    async def _on_decision(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        if not isinstance(payload, dict):
            self._blocked += 1
            self._last_reason = "PAYLOAD_NOT_A_MAPPING"
            return
        self._seen += 1
        self._seen_boot += 1

        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإيقاف يُقرأ لحساب القرار نفسه.
        if entry_request_inputs.halted_for(self, _text(payload.get("account_id"))):
            await self._decline(REASON_HALTED, payload)
            return

        gate = entry_request_lines.gate_block(self)   # 2026-10-26: a missing gate or a stalled pulse refuses
        if gate:
            await self._decline(gate, payload)
            return
        now = self._official_time or time.time()   # the official pulse; the wall clock only before the first one
        holiday = no_trade_day(now) if no_trade_day is not None else None
        if holiday:
            await self._decline(REASON_NO_TRADE_DAY, payload, {"day": holiday})
            return
        line = entry_block(now, self._calendar, payload.get("symbol")) if entry_block is not None else None
        if line:
            await self._decline(line, payload)
            return
        wait, detail = entry_request_lines.wait_block(self, payload.get("account_id"), payload.get("symbol"), now)
        if wait:
            await self._decline(wait, payload, detail)
            return

        side = _side_of(payload)
        if side not in (SIDE_BUY, SIDE_SELL):
            await self._decline(REASON_NO_SIDE, payload, {"side": side})
            return

        account = _text(payload.get("account_id"))
        symbol = _text(payload.get("symbol"))
        broker = _text(payload.get("broker")) or self._brokers.get(account, "")
        if not account or not broker or not symbol:
            await self._decline(REASON_NO_IDENTITY, payload)
            return

        # ٢٠٢٦-٠٩-١٠ (شكوى المالك: «ليش تفعل هيدج؟ أنا مو مشغّله» ·
        # «ناسدك ٣ صفقات مع بعض» · «بيتكوين مهدّج»): `_open_counts` حالةٌ
        # في الذاكرة لا تُحفظ في اللقطة ولا تُستعاد، والذرّات تُبدَّل ساخنة.
        # فبعد كل إعادة تحميل تبدأ الخريطة فارغة ⇒ `open_now = 0` ⇒ يمرّ
        # الدخول رغم وجود مركز قائم، حتى تصل أوّل `platform.positions.state`.
        # مقيس: `USTEC SELL 0.5 FILLED_OPEN` مرّتين، وBTCUSD شراءٌ وبيعٌ معًا.
        # الجهل بالمراكز ليس إذنًا بالدخول — يُرفَض حتى تُعرَف الحال.
        if not self._positions_seen:
            await self._decline(REASON_POSITIONS_UNKNOWN, payload)
            return
        # الطلب الطائر يُعدّ مركزًا: بين الإرسال ووصول المركز من الجسر
        # ثوانٍ كان يمرّ فيها قرارٌ ثانٍ وثالث على الرمز نفسه.
        held = entry_request_inputs.held_for(self, account, symbol)
        flying = self._inflight_for(symbol)
        open_now = held + flying
        if open_now > self._max_open_per_symbol:
            # الإضافة على مركز قائم شأن 581؛ ازدواج المُصدِرين يفتح مركزين.
            await self._decline(REASON_POSITION_OPEN if held else REASON_IN_FLIGHT,
                                payload, {"open_positions": held, "in_flight": flying})
            return
        if hedged := entry_request_inputs.hedge_elsewhere(self, account, symbol, side):
            await self._decline(REASON_HEDGE_OTHER_ACCOUNT, payload, {"other_account": hedged})
            return

        scope = "\x1f".join((account, broker, symbol))
        entry = self._sizes.get(scope)
        if entry is None:
            await self._decline(REASON_NO_SIZE, payload, {"scope_known": False})
            return
        age = time.monotonic() - float(entry["at"])
        if self._size_stale_after_s and age > self._size_stale_after_s:
            await self._decline(REASON_SIZE_STALE, payload,
                                {"size_age_s": round(age, 3)})
            return

        size = entry["payload"]
        # الحجم من ٥١٣، والوقف **لا**. كان يُقرأ هنا `buy_stop`/`sell_stop`
        # ثمّ يُستبدل بإبطال التحليل إن صلح — فالاحتياطيّ يمرّ حين لا يصلح.
        # وبأمر المالك ٢٠٢٦-٠٩-١٩ لم يعد له مصدرٌ إلا التحليل.
        if side == SIDE_BUY:
            volume = _number(size.get("buy_lot")) or _number(size.get("lot"))
        else:
            volume = _number(size.get("sell_lot")) or _number(size.get("lot"))
        if volume is None or volume <= 0.0:
            await self._decline(REASON_NO_VOLUME, payload, {"volume": volume})
            return

        price = (_number(size.get("close")) or _number(size.get("reference_price"))
                 or _number(size.get("price")))
        # وكان هنا اشتقاقُ وقفٍ من `default_distance`/`stop_distance` — نسبة
        # ٥١٣ الافتراضيّة. حُذف بأمر المالك ٢٠٢٦-٠٩-١٩، وهو المصدر الذي
        # أخرج ‎87.2‎ نقطةً في أربعة أوامرٍ متتالية بينما إبطال التحليل ‎28.9‎.
        #
        # حكم المالك ٢٠٢٦-٠٩-١١: «الستوب يجي من التحليل حصرًا».
        # مقيس على ٣٬٨٢٦ أمرًا: كلّها خرجت بوقفٍ احتياطيّ ٠٫٥٪ ثابتة
        # و`invalidation_source: None` — والمستويات التحليليّة تُنشر في
        # `strategy.setup.proposed` ويستهلكها ٥٨١ وحده، ولا تصل الدخول.
        # 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك) — «ما في وقف احتياطي أو وقف صلب، احذفو».
        #
        # كان الوقف يسقط إلى احتياطيّ ٥١٣ حين لا يصلح إبطال التحليل، وهو
        # نسبةٌ مئويّة ثابتة لا مستوًى. ومقيسٌ على آخر أربعة أوامر:
        #
        #   87.25 · 87.33 · 87.21 · 86.86   ⟸ 0.1070% من السعر في الأربعة
        #   واللوت تبعٌ له: 1.0 · 1.0 · 1.0 · 1.01
        #
        # وقفٌ ثابتٌ بالنسبة يجمّد الحجم معه، ويُغرق نسبة المخاطرة إلى
        # المكافأة: بنى التحليل ‎9.44‎ فخرجت ‎4.53‎ لأنّ الوقف اتّسع ثلاثة
        # أضعاف والهدف بقي. وينقض حكم المالك ٢٠٢٦-٠٩-١١ «الوقف من التحليل
        # حصرًا» في السطر نفسه الذي يدّعي احترامه.
        #
        # فلا مصدر للوقف إلا إبطال التحليل. وما لا إبطال له **يُرفض ولا
        # يُخترع له بديل** — وهو حكمه ٢٠٢٦-٠٩-١٨ نفسه: «المرفوضة تُرفض ولا
        # تُعدَّل». وثمنُه معلَن: صفقاتٌ أقلّ، وكلُّ صفقةٍ لها مستوًى يُدافَع
        # عنه بدل نسبةٍ من الرأس.
        #
        # والسبب يُفرَّق ويُعدّ: بلا إعدادٍ أصلًا · إعدادٌ بلا إبطال ·
        # إبطالٌ على الجهة الخطأ من السعر. ثلاثتُها كانت تُبتلع في سقوطٍ
        # واحدٍ صامتٍ اسمه `FALLBACK_513`.
        # المستوياتُ من القرار أوّلًا، ومن الخانة عند غيابها. والفرقُ
        # يُعدّ ويُعلَن، فنقرأ أنا وجلسة التحليل تقدُّمَ التحوّل بالرقم.
        setup = self._levels_on_decision(payload)
        from_decision = setup is not None
        if not from_decision:
            self._levels_stored += 1
            setup = self._setup_levels(symbol, side)
        setup_id = None
        stop = None
        stop_source = None
        if setup is None:
            self._stop_no_setup += 1
        else:
            setup_id = setup.get("setup_id")
            analysis_stop = _number(setup.get("invalidation_price"))
            if analysis_stop is None or analysis_stop <= 0.0:
                self._stop_no_level += 1
                self._last_stop_reject = "%s %s بلا إبطال" % (symbol, side)
            elif not ((analysis_stop < price) if side == SIDE_BUY
                      else (analysis_stop > price)):
                self._stop_wrong_side += 1
                self._last_stop_reject = "%s %s إبطال=%.5f والسعر=%.5f" % (
                    symbol, side, analysis_stop, price or 0.0)
            else:
                stop = analysis_stop
                stop_source = setup.get("invalidation_source") or "ANALYSIS"
                self._setup_used += 1

        if stop is None or stop <= 0.0:
            await self._decline(REASON_NO_STOP, payload,
                                {"price": price, "setup_id": setup_id,
                                 "analysis_only": True})
            return

        # 🔴 الوقف صار وقفَ التحليل — فالحجم يُعاد حسابه عليه. تفصيلُه في
        # `_lot_for_stop` أعلاه: حجمُ ٥١٣ محسوبٌ على وقفه هو، وتركُه هنا
        # يُخرج أمرًا حجمُه من وقفٍ ووقفُه من آخر.
        if price is not None and price > 0.0:
            final_distance = abs(price - stop)
            # 🔴 ٢٠٢٦-٠٩-٢٤ (ختم المالك «Nq على كلهم») — العمولة من سجلّ الوسيط
            # لكلّ رمز، لا رقمُ ٥١٣ الواحد.
            #
            # كانت ٧$/لوت لكلّ الرموز (`513/manifest.yaml`)، وسجلّ الجسر يقول
            # غير ذلك: ناسداك 131 حدثًا و308.6 لوت **وعمولتها صفر** في كلّها،
            # ومثلها البتكوين. فخرج اللوت ثلثَ حجمه على الوقف القصير — مقيس
            # 14:46:31: وقف 2.35 نقطة ⟸ 100 ÷ (2.35 + 1 + 7) = 9.6 لوت ⟸
            # معرَّض 22.56$، فردّه 552 تحت أرضيّته 50$. وردّ كلّ أوامر الناسداك
            # منذ إقلاع 14:22 (7 من 7). بعمولته الحقيقيّة: 29.8 لوت ⟸ 70.03$.
            #
            # والجدول نفسه الذي يبني عليه 551 (`shared/execution_costs.py`)،
            # فيقف الطالب والباني على مسطرةٍ واحدة. والرمز الذي لا سجلّ له
            # يبقى على رقم ٥١٣ كما كان. نسخةٌ لا تعديل: الحمولة المخزّنة من
            # ٥١٣ لا تُمَسّ.
            size = dict(size)
            size["commission_per_lot"] = execution_costs.commission_roundtrip(
                symbol, _number(size.get("commission_per_lot")) or 0.0)
            resized = _lot_for_stop(size, final_distance)
            if resized is None:
                self._resize_failed += 1
                self._last_resize = "%s %s مسافة=%.5f" % (symbol, side, final_distance)
                await self._decline(REASON_NO_VOLUME, payload,
                                    {"stop_source": stop_source,
                                     "stop_distance": round(final_distance, 8),
                                     "sizing": "RESIZE_BELOW_MIN_LOT"})
                return
            if abs(resized - volume) > 1e-12:
                self._resized += 1
                # السبريد المستعمل يدخل السطر: هو المجهول الوحيد في معادلة
                # الحجم، وبدونه يُستنتج بقسمةٍ عكسيّة تخلط ثلاثة مجاهيل.
                self._last_resize = "%s %s %s⟶%s على %.5f +سبريد %.5f +عمولة %.2f (%s)" % (
                    symbol, side, volume, resized, final_distance,
                    size.get("_spread_used") or 0.0,
                    _number(size.get("commission_per_lot")) or 0.0, stop_source)
            volume = resized

        # 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك) — «ولا هدف احتياطي أو هدف صلب، احذفو».
        #
        # الهدف لا يُشتقّ هنا: يُؤخذ فقط من إعداد الصفقة التحليلي.
        # يعلوه هدف التحليل إن وُجد. فالإعدادُ الذي يصل بهدفٍ ولا إبطال —
        # أو لا يصل أصلًا — كان يخرج بهدفٍ من معادلة لا من مستوًى، تمامًا
        # كما كان الوقف يسقط إلى نسبةٍ مئويّة.
        #
        # وهدف ٥٢٦ لمركزٍ **قائم** بابه ٥٨١، لا باب الدخول. فلا يُخلط
        # المساران: الدخولُ لا يُبنى إلا على مستويَي صاحب الفكرة — إبطالُه
        # وهدفُه — وما نقص أحدُهما يُرفض.
        take_profit = None
        target_source = None
        if setup is not None:
            analysis_tp = _number(setup.get("target_price"))
            if analysis_tp is not None and analysis_tp > 0.0:
                take_profit = analysis_tp
                target_source = setup.get("target_source") or "ANALYSIS"

        # ⚖️ ٢٠٢٦-٠٩-١٨ — حكم المالك ينقض حكمه ٢٠٢٦-٠٩-١١ هنا بنصّه:
        # «لازم أهداف تكون من 1/3 وأكبر من هيك، يعني 1/5 1/7 1/9 وأكبر»
        # و«صفقة جاي بهدف 1/2، كيف تعدّلها وتركّبها 1/3؟ ما رح تشمّ ريحة مال
        # فيها من خسرات متتالية».
        #
        # وكان هنا «هدفٌ صلب» يرفع كلّ ما قصر عن ١/٣ إلى ١/٣ — وهو القالب
        # الذي منعه. فالثلاثة صارت **أرضيّة قبول لا قالب سحب**: ما بلغها أو
        # تجاوزها يمرّ **بمضاعفه هو** (١/٥ تبقى ١/٥ و١/٩ تبقى ١/٩)، وما قصر
        # عنها يُرفض بسببه المعلن.
        #
        # وسنده مقيس على ٩٠ صفقة مغلقة تحت القالب: صفرٌ بلغت 3R، وأربعٌ فقط
        # خرجت بـTP — القالب لم يصنع مضاعفه، صنع طابور خسارات.
        # 📐 ٢٠٢٦-٠٩-١٩ — الهندسة تُقاس على مرجع بناء الإعداد لا على السعر
        # الحيّ. حكم المالك ٢٠٢٦-٠٩-٠٦ منصوصٌ في `shared/trade_setup.py`:
        # «الهندسة تُقاس على `entry_reference` لا على السعر الحاليّ. السعر
        # الحاليّ يجيب سؤالًا آخر تمامًا — هل فاتت الفكرة؟»
        #
        # وكانت النسبة هنا تُحسب ببسطٍ ومقامٍ من سعرين: `price` من حمولة
        # ٥١٣ المتجدّدة مع كلّ تِكّة، و`stop`/`take_profit` من إعدادٍ بُني
        # في لحظةٍ سابقة. فما بُني عند 3.00 بالضبط يسقط بأيّ انزياحٍ
        # معاكس، بلا أن يتغيّر مستوًى واحد في الإعداد — ردٌّ لهندسةٍ سليمة
        # لأنّ الزمن مرّ. نبّهت إليه جلسة ٤٠٠-٤٥٠ وأثبته الكود.
        #
        # ويُشترط أن يكون الطرفان من التحليل معًا: خلطُ وقف ٥١٣ الاحتياطيّ
        # (المبنيّ على السعر الحيّ) بمرجعِ بناءٍ قديم يقيس ضلعين من زمنين.
        geometry_ref = price
        # الوقف من التحليل حتمًا بعد أمر ٢٠٢٦-٠٩-١٩ (وإلّا رُفض الأمر قبل
        # الوصول إلى هنا)، فيبقى شرطُ الهدف وحده.
        if setup is not None and target_source not in (None, "REQUEST"):
            built_at = _number(setup.get("entry_reference"))
            if built_at is not None and built_at > 0.0:
                geometry_ref = built_at
                drift = abs(built_at - price) if price else 0.0
                self._geometry_at_build = getattr(self, "_geometry_at_build", 0) + 1
                self._last_drift = "%s %s بناء=%.5f حيّ=%.5f انزياح=%.5f" % (
                    symbol, side, built_at, price or 0.0, drift)
                # والسؤال الآخر يُسأل على السعر الحيّ وحده: هل فاتت الفكرة؟
                if price is not None and is_target_reached(setup, price):
                    self._target_reached = getattr(self, "_target_reached", 0) + 1
                    self._last_reached = "%s %s هدف=%s حيّ=%.5f" % (
                        symbol, side, setup.get("target_price"), price)
                    await self._decline(REASON_TARGET_REACHED, payload, {
                        "price": price, "target_price": setup.get("target_price"),
                        "entry_reference": built_at})
                    return

        risk_distance = abs(geometry_ref - stop)
        if risk_distance <= 0.0:
            await self._decline(REASON_NO_TARGET, payload, {"stop": stop, "price": price})
            return
        reward = (None if take_profit is None else
                  ((take_profit - geometry_ref) if side == SIDE_BUY
                   else (geometry_ref - take_profit)))
        if reward is None or reward <= 0.0:
            await self._decline(REASON_NO_TARGET, payload, {"stop": stop, "price": price})
            return
        # 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك) — «حارس يستلم صفقة فيها هدف وستوب
        # تمرق، ما فيها تُردّ».
        #
        # فحارسُ النسبة يسقط: كان يردّ كلّ ما قصَر عن `min_reward_multiple`
        # (‎3.0‎). والنسبةُ ما زالت تُحسب وتُنشر وتُعلَن في الشارة — **تُقاس
        # ولا تحكم**. ومقياسٌ يُعلَن غيرُ حارسٍ يردّ، والخلط بينهما هو الذي
        # جعل ثلاثةً وتسعين بالمئة من قراراته تموت بصمت.
        #
        # وينقض هذا حكمه ٢٠٢٦-٠٩-١٨ «دون ١:٣ ننتظر»، وهو حقُّه وأحدثُ
        # كلمتيه تعلو. والشرطُ الباقي شرطُه هو: هدفٌ موجب ووقفٌ موجب على
        # جهتيهما — وقد فُحصا في السطور الأربعة أعلاه.
        multiple = reward / risk_distance
        if multiple + _REWARD_EPSILON < self._min_reward:
            self._below_floor = getattr(self, "_below_floor", 0) + 1
            self._last_below = "%s %s %.2fR (عيار %gR يُقاس ولا يحكم) مصدر=%s" % (
                symbol, side, multiple, self._min_reward, target_source or "-")
        if take_profit is None or take_profit <= 0.0:
            await self._decline(REASON_NO_TARGET, payload, {"stop": stop, "price": price})
            return

        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): 🔴 النسبة والوقف **يحكمان** عند الإرسال.
        #
        # «يُقاس ولا يحكم» أعلاه حكمُ ٢٠٢٦-٠٩-١٩، ونقضه المالك ٢٠٢٦-٠٩-٢٨: «هدف صفقة لا
        # يقل عن 1/3… اذا تحت 1/3 مرفوضة» — وأحدثُ كلمتيه تعلو. والقياس أعلاه على مرجع
        # البناء، فما بُني عند 3 يبقى 3 مهما مشى السعر؛ ومقيسٌ: 298 صفقة منفّذة دون 1:3
        # عند الإرسال (146 دون 1:1)، وأربعة أوامر بوقف 6.0–9.7 ن.أ. فيُعاد الحكمان هنا
        # على `price`/`stop`/`take_profit` التي تخرج مع الأمر حرفًا، بمعادلة 405/406/410
        # (صافي بعد السبريد ≥ 3 · وقف ≥ 10 ن.أ) — ردٌّ بسببٍ مسمّى، لا تعديل مستوى.
        why, economics = send_economics(side, price, stop, take_profit, size.get("spread"), symbol)
        if why:
            self._send_blocked[why] = self._send_blocked.get(why, 0) + 1
            self._last_send_block = "%s %s %s صافي=%s وقف=%sن.أ" % (
                symbol, side, why, economics.get("net_ratio"), economics.get("stop_pips"))
            await self._decline(why, payload, {**economics, "setup_id": setup_id,
                                               "target_source": target_source})
            return
        # 2026-10-25 (owner seal, law 21): the time-enough check is gone; the last hour of the asset's window refuses new
        # entries in `entry_block` above, and an open trade runs on to the window's end.

        # كبح موحّد للدخول: 555 هو باب الدخول الأوّل، و581 باب الإضافة.
        # وجود 45 ثانية في 581 وحده كان يترك 555 كطريق التفاف بعد إغلاق المركز.
        cooldown_scope = account + "\x1f" + symbol
        now = time.time()
        previous_request_at = self._last_request_at.get(cooldown_scope)
        # v1.28.0: the check moved verbatim to `entry_request_inputs.cooldown` (the 400-line limit).
        if cooling := entry_request_inputs.cooldown(previous_request_at, now, ENTRY_COOLDOWN_S):
            await self._decline("ENTRY_COOLDOWN", payload, cooling)
            return

        request_id = f"555-{uuid.uuid4().hex[:12]}"
        # جسدُ الطلب يُبنى في `entry_request_order.py` حرفيًّا كما كان هنا —
        # الحقول والتقريب ونقلُ سلسلة الهويّة (`decision_side` وأخواتها).
        request = entry_request_order.build_request(
            request_id=request_id, account=account, broker=broker, symbol=symbol,
            side=side, volume=volume, price=price, stop=stop,
            take_profit=take_profit, target_source=target_source, size=size,
            setup_id=setup_id, stop_source=stop_source, setup=setup,
            payload=payload)

        # ٢٠٢٦-٠٩-٢٢ (دمج) — طرفا التعارض كلاهما صحيح ولا يُغني عن الآخر:
        # مهلةُ الدخول من المستودع، واستهلاكُ الإعداد من هنا. ورَدُّ الحالة
        # عند الفشل يشمل الاثنين — إن لم يخرج الأمر فلا يُحسب دخولًا ولا
        # يُستهلَك إعداده.
        self._last_request_at[cooldown_scope] = now
        try:
            await self._context.publish(EVENT_REQUEST, request)
        except Exception:
            if previous_request_at is None:
                self._last_request_at.pop(cooldown_scope, None)
            else:
                self._last_request_at[cooldown_scope] = previous_request_at
            raise
        # 🔴 ٢٠٢٦-٠٩-٢١ — **الإعداد يُستهلَك مرّةً واحدة.**
        #
        # سألتُ ناشرَه (جلسة ٤٠٠-٤٥٠) عن قصده فأجاب صريحًا: «الإعداد
        # يُقصد به الاستهلاك مرّةً واحدة، ليس أمرًا قائمًا ولا اشتراكًا
        # مدّته ١٨٠٠ ثانية. و`expires_at` حدُّ **طزاجة** لا رخصةَ تكرار».
        #
        # وكنتُ أقرؤه رخصةً: أحفظ الإعداد في خانته وأعيد استعماله مع كلّ
        # قرارٍ يصلني حتّى ينقضي أجلُه. فأنا **أخالف عقد ناشره لا أنفّذه**،
        # وهذا تصحيحُ قراءةٍ لا تغييرُ عيار.
        #
        # وثمنُه مقيسٌ عندهم: إعدادٌ واحد من ٤٠٦ أخرج **خمسة أوامر** بالوقف
        # نفسه ‎81628.85‎ والهدف نفسه ‎81312.02‎ — وثلاثةٌ منها الفكرةُ ذاتها
        # حرفيًّا وخسرت ثلاثتها (‎−68.25 · −88.18 · −0.13‎). فكرةٌ واحدة
        # قيمتُها صفقةٌ واحدة، أُخرجت خمسًا.
        #
        # ولا يخالف أمر المالك «فيها هدف وستوب تمرق»: الإعدادُ يمرّ كاملًا
        # مرّةً، والثانية تحتاج فكرةً جديدة من صاحبها لا صدًى لقديمة.
        # [[setup-cached-by-ttl-only-room-collapses]]
        # ٢٠٢٦-٠٩-٢٣ — الاستهلاكُ للمخزون وحده. فمتى جاءت المستويات مختومةً
        # على القرار لم يعد ثَمَّ مخزونٌ يُتنازَع عليه: كلُّ قرارٍ يحمل فكرتَه،
        # وتكرارُ الفكرة يمنعه `max_open_per_symbol` و`_inflight` لا المسح.
        # ومسحُ خانةٍ لم يُقرأ منها يحرم قرارًا تاليًا لا يحمل مستوياته.
        if setup_id and not from_decision:
            self._setups.pop((symbol, side), None)
            self._setup_consumed += 1
            self._last_consumed = "%s %s %s" % (symbol, side, setup_id)
        self._inflight[symbol] = time.monotonic()
        self._emitted += 1
        self._emitted_boot += 1
        self._last_reason = "REQUESTED"
        await self._context.publish(EVENT_STATE, {
            "account_id": account, "broker": broker, "symbol": symbol,
            "requested": True, "reason": "REQUESTED",
            "request_id": request_id, "side": side, "volume": volume,
            "stop_loss": request["stop_loss"],
            "take_profit": request["take_profit"],
            "target_source": target_source})

    # v1.27.0 (2026-10-23): the bodies of these three moved verbatim to `entry_request_state.py` (the 400-line limit).
    async def health_check(self) -> HealthStatus:
        return entry_request_state.health(self)

    async def snapshot(self) -> dict[str, Any]:
        return entry_request_state.snapshot(self, ATOM_VERSION)

    async def restore(self, state: dict[str, Any]) -> None:
        entry_request_state.restore(self, state, ENTRY_COOLDOWN_S)
