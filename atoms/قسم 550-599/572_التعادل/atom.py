from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared import execution_costs
from shared import owner_trades

ATOM_VERSION = "1.8.0"
#: ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا»): كانت الذرّة تتتبّع كلّ مركزٍ
#: له وقف — ومعه مركز المالك اليدويّ — وتطلب نقل وقفه إلى التعادل عند 1R، فيردّه ٥٧٥ لأنّه ليس للمنظومة. الآن تُسقط صفقات
#: المالك من صورة المراكز عند دخولها، بالتمييز الواحد في `shared/owner_trades.py`.
#: 2026-10-23 (owner's sealed red lines, law 6 -- "close the part at market first, *then* move the stop"): 574 closes a part at
#: each target and only then moves the stop; it names its tickets on `management.level_plan.state` and this atom stands aside.
#: Two doors were left where this atom could secure first: before 574's list was heard at all (after a start), and on the very
#: cycle a ticket first appears (574 names it at the end of that same cycle). So nothing moves until the list has been heard
#: and the ticket has been seen on an earlier positions cycle.
PLAN_GRACE_CYCLES = 2
#: ٢٠٢٦-١٠-٠٥ (ختم المالك «nq اعتمدناها»): التذاكر التي يديرها ٥٧٤ على مستويات التحليل —
#: التعادل فيها عند **أوّل مستوىً** في الطريق كما اعتمد المالك («يُغلق ثلث العقد والوقف
#: ينتقل إلى الدخول»)، لا عند 1R. فتتنحّى هذه الذرّة عنها، وتبقى على كلّ صفقةٍ غيرها كما كانت.
EVENT_PLAN = "management.level_plan.state"

EVENT_IN = "platform.positions.state"
EVENT_SPECS = "market.symbol_specs"
EVENT_OUT = "execution.manage.intent"
#: 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك) — «قسمك كلّه على تِكّة، ما في دورة — إنت مال».
#:
#: ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): التِكّة من **ميتاتريدر** بسعر جهة
#: المركز (العرض للشراء، الطلب للبيع) لا منتصف سي‑تريدر. نقلُ الوقف تنفيذ:
#: الوسيط يحكم عليه بسعره هو، والمنتصف من دفترٍ آخر كان يرى «1R» والعرض عند
#: ميتاتريدر دونها (حالة US30 1976793832 في ٥٧٤). ودورة ٦٠٩ تحمل سعر جهة
#: المركز أصلًا، فصار المساران بمسطرةٍ واحدة. وتحليل السوق باقٍ على سي‑تريدر.
EVENT_TICK = "feed.mt5.tick"

ACTION_MODIFY = "MODIFY_SL"
REASON_BREAKEVEN = "breakeven"

SIDE_BUY = "BUY"
SIDE_SELL = "SELL"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_POSITIONS = "NO_POSITIONS_YET"

_R_DP = 4


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
        self._tracked: dict[str, dict[str, Any]] = {}
        self._tick_checks = 0
        #: قيمة وحدة السعر لكلّ لوت، لكلّ رمز — `tick_value/tick_size` من
        #: مواصفات الوسيط. بها وحدها يُترجَم الدولار إلى سعر.
        self._vpp: dict[str, float] = {}
        self._seen = 0
        self._emitted = 0
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حدّ الوسيط لموضع الوقف لكلّ رمز،
        # وعدّاد التعادل الذي لم يُرسَل لأنّه في غير جهته من سعر التنفيذ.
        self._point: dict[str, float] = {}
        self._stops_level: dict[str, float] = {}
        self._stop_invalid = 0
        self._last_invalid = "-"
        self._plan_tickets: set[str] = set()
        self._plan_yielded: set[str] = set()
        self._plan_heard = False
        self._awaiting_plan: set[str] = set()

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._at_r = float(context.config["breakeven_at_r"])
        context.subscribe(EVENT_IN, self._on_positions)
        context.subscribe(EVENT_SPECS, self._on_specs)
        context.subscribe(EVENT_TICK, self._on_tick)
        context.subscribe(EVENT_PLAN, self._on_plan)

    async def _on_plan(self, payload: dict[str, Any]) -> None:
        """قائمة ٥٧٤ كاملةً في كلّ نشرة — آخرُها يحلّ محلّ ما قبله."""
        if isinstance(payload, dict) and isinstance(payload.get("tickets"), list):
            self._plan_tickets = {str(t) for t in payload["tickets"] if t is not None}
            self._plan_heard = True

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_specs(self, payload: dict[str, Any]) -> None:
        """يلتقط قيمة وحدة السعر. بلا مواصفةٍ لا يُنقل وقفٌ إلى «تعادل»
        لا نعرف كلفته — والذرّة تبقى على سعر الدخول كما كانت.

        والشكل مقروءٌ من ناشره لا مفترَضًا: `513:154` و`574:148` كلاهما يقرأ
        `payload["symbols"]` قائمةَ صفوف. وكنتُ كتبتُ هنا ثلاثة أسماء محتملة
        (`specs` ثمّ `symbols` ثمّ `rows`) — وذاك تخمينٌ يبدو احتياطًا: لو
        حمل الناشر مفتاحًا باسم `specs` لشيءٍ آخر لالتُقط الخطأ أوّلًا وصمتت
        الذرّة. درسٌ مدفوعُ الثمن عندنا: اختبارات ٥٥٥ بنَت حمولةً لا ينشرها
        ناشرها، فمرّت اثنتا عشرة خضراء والذرّة ميتةٌ حيًّا.
        """
        if not isinstance(payload, dict):
            return
        rows = payload.get("symbols")
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            # المفتاح موحَّد الصيغة عند الخزن والقراءة معًا. رمزٌ يُخزَّن
            # «XAUUSD» ويُطلَب «xauusd» لا يُوجَد، فيبقى التعادل خامًا بلا
            # أن يقول أحدٌ شيئًا — و٥٧٤ يوحّده كذلك (`.strip().upper()`).
            symbol = str(row.get("symbol") or "").strip().upper()
            tick_value = _to_float(row.get("tick_value"))
            tick_size = _to_float(row.get("tick_size"))
            if symbol and tick_value and tick_size and tick_size > 0.0:
                self._vpp[symbol] = tick_value / tick_size
            # ٢٠٢٦-١٠-٠٢: النقطة وحدّا الوسيط — لفحص جهة الوقف قبل إرساله.
            point = _to_float(row.get("point")) or tick_size
            if symbol and point and point > 0.0:
                self._point[symbol] = point
            if symbol:
                levels = [_to_float(row.get(name)) for name in ("stops_level", "freeze_level")]
                self._stops_level[symbol] = max(
                    [v for v in levels if v is not None and v > 0.0], default=0.0)

    def _stop_valid(self, symbol: Any, side: str, stop: Any, price: Any) -> bool:
        """هل يقبل الوسيط هذا الوقف الآن؟ — ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»).

        وقف الشراء تحت العرض، ووقف البيع فوق الطلب، بحدّ الوسيط
        (`max(stops_level, freeze_level) × point`) ونقطةٍ فوقه. مقيس: 30 `MODIFY_SL`
        ردّها الوسيط `RETCODE_10016`، وكلّ ردٍّ يجمّد الدخولات 15 دقيقة عند ٦٠١.
        """
        stop_value = _to_float(stop)
        current = _to_float(price)
        if stop_value is None or stop_value <= 0.0 or current is None or current <= 0.0:
            return False
        name = str(symbol or "").strip().upper()
        point = self._point.get(name, 0.0)
        room = (current - stop_value) if side == SIDE_BUY else (stop_value - current)
        if point <= 0.0:
            return room > 0.0
        return room >= (self._stops_level.get(name, 0.0) + 1.0) * point - point * 1e-6

    def _breakeven_price(self, symbol: str, entry: float, side: str,
                         volume: float) -> float:
        """سعرُ تعادلٍ **صافٍ** — لا سعر الدخول الخام.

        ⚖️ ٢٠٢٦-٠٩-١٨ — أمر المالك: «أخسر 0 لمّا يضرب ستوب الدخول».
        وكان الوقف يُنقل إلى `entry` حرفيًّا، فيخرج المركز بخسارة عمولته:
        مقيسٌ على 21 صفقة خرجت عند التعادل بصافي ‎-76.85$‎.

        فيُزاح بمقدار ما يلزم لتغطية عمولة الدورة:
            المسافة = عمولة_الدورة × اللوت ÷ (اللوت × قيمة الوحدة)
                    = عمولة_الدورة ÷ قيمة الوحدة
        وهي مستقلّةٌ عن الحجم — لأنّ العمولة بالحجم والربح بالحجم.

        ورمزٌ بلا عمولة (البتكوين والناسداك، مقيسٌ صفرًا في 142 صفقة) يبقى
        تعادلُه سعرَ دخوله بالضبط. ولا يُضاف انزلاق: لا يُعرف قبل وقوعه،
        وحجزُ ما لا يقع يزيح التعادل إلى الربح ويخرجنا مبكّرين.
        """
        name = str(symbol or "").strip().upper()
        vpp = self._vpp.get(name)
        commission = execution_costs.commission_roundtrip(name, 0.0)
        if not vpp or vpp <= 0.0 or commission <= 0.0:
            return entry
        offset = commission / vpp
        return (entry + offset) if side == SIDE_BUY else (entry - offset)

    def _track(self, ticket: str, entry: float, stop: float, side: str) -> dict[str, Any]:
        st = self._tracked.get(ticket)
        if st is None:
            risk = abs(entry - stop) if stop and stop > 0.0 else None
            st = {"entry": entry, "side": side, "risk": risk, "done": False}
            self._tracked[ticket] = st
        return st

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        """التِكّة تفحص التعادل بالسعر اللحظيّ — أمر المالك ٢٠٢٦-٠٩-١٩.

        «قسمك كلّه على تِكّة، ما في دورة — إنت مال.»

        كان الفحص من دورة ٦٠٩ وحدها (كلّ ثانيتين تقريبًا)، فسعرٌ يبلغ
        عتبة التعادل بين دورتين ثمّ يرتدّ لا يُرى — والصفقة تبقى بلا
        تأمينٍ كان يستحقّه.

        ولا منطقَ جديدًا: تُبنى صورةُ المركز المحفوظة بسعر التِكّة ويُستدعى
        الفحصُ نفسه. حكمٌ واحدٌ في موضعٍ واحد.
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
        positions = owner_trades.system_rows(positions)   # ٢٠٢٦-١٠-٢٦: صفقة المالك لا تُتتبّع ولا يُنقل وقفها
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
            symbol = pos.get("symbol")
            if ticket is None or entry is None or current is None or side not in (SIDE_BUY, SIDE_SELL):
                continue
            key = str(ticket)
            live.add(key)
            st = self._track(key, entry, stop if stop is not None else 0.0, side)
            # صورةُ المركز من دورة ٦٠٩ وحدها — هي المصدر الموثوق للهويّة.
            # والتِكّة تستعيرها وتبدّل السعر وحده.
            if not from_tick:
                # كلُّ حقلٍ تقرؤه الحلقة يدخل الصورة — ولو لم يؤثّر اليوم.
                # `volume` مثالًا لا يغيّر سعر التعادل (العمولة مستقلّةٌ عن
                # الحجم)، لكنّ صورةً ناقصةً تجعل المسارين يقرآن شيئين
                # مختلفين، وذاك أصلُ كلّ عطبٍ صامتٍ مرّ بنا اليوم.
                st["pos"] = {"account_id": pos.get("account_id"),
                             "ticket": ticket, "symbol": symbol, "side": side,
                             "entry_price": entry, "stop_loss": stop,
                             "volume": pos.get("volume")}
                st["cycles"] = st.get("cycles", 0) + 1
            if st["done"] or st["risk"] is None or st["risk"] <= 0.0:
                continue
            if key in self._plan_tickets:
                self._plan_yielded.add(key)    # تعادلُها عند أوّل مستوى — بيد ٥٧٤
                self._awaiting_plan.discard(key)
                continue
            if not self._plan_heard or st.get("cycles", 0) < PLAN_GRACE_CYCLES:
                self._awaiting_plan.add(key)   # 2026-10-23 (law 6): 574 has not spoken for this ticket yet
                continue
            self._awaiting_plan.discard(key)
            profit_distance = (current - entry) if side == SIDE_BUY else (entry - current)
            r_multiple = profit_distance / st["risk"]
            if r_multiple < self._at_r:
                continue
            new_sl = self._breakeven_price(
                str(symbol) if symbol else "", entry, side,
                _to_float(pos.get("volume")) or 0.0)
            cur_sl = stop if stop is not None else 0.0
            tighter = (side == SIDE_BUY and new_sl > cur_sl) or \
                      (side == SIDE_SELL and (cur_sl <= 0.0 or new_sl < cur_sl))
            if not tighter:
                st["done"] = True
                continue
            if not self._stop_valid(symbol, side, new_sl, current):
                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): تعادلٌ في غير جهته من سعر
                # التنفيذ يردّه الوسيط `10016` — لا يُرسل، ولا يُعلَن «تمّ»، ويُعاد
                # فحصه مع السعر التالي. يُعدّ مرّةً لكلّ تذكرة.
                if not st.get("invalid_counted"):
                    st["invalid_counted"] = True
                    self._stop_invalid += 1
                    self._last_invalid = "%s tk=%s وقف=%s سعر=%s" % (symbol, ticket, new_sl, current)
                    self._context.logger.warning(
                        "572 %s ticket=%s: التعادل %s في غير جهته من سعر التنفيذ %s — "
                        "لم يُرسَل (كان سيُردّ 10016)", symbol, ticket, new_sl, current)
                continue
            await self._context.publish(EVENT_OUT, {
                "account_id": str(pos.get("account_id") or ""),
                "ticket": ticket, "symbol": str(symbol) if symbol else "", "side": side,
                "action": ACTION_MODIFY, "stop_loss": new_sl,
                "reason": REASON_BREAKEVEN, "r_multiple": round(r_multiple, _R_DP)})
            st["done"] = True
            self._emitted += 1
        # التقليم من دورة ٦٠٩ وحدها: التِكّة تحمل رمزًا واحدًا، وحذفُ ما
        # ليس فيها يمحو تتبّع كلّ رمزٍ آخر.
        if not from_tick:
            for key in list(self._tracked):
                if key not in live:
                    del self._tracked[key]
                    self._awaiting_plan.discard(key)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"tracked": len(self._tracked), "seen": self._seen, "emitted": self._emitted}
        if self._seen == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_POSITIONS,
                                details=details)
        # العيار الساري يُعلَن في الرسالة نفسها: رقم الإصدار يُبنى من
        # المانيفست فلا يثبت أنّ القيمة المقروءة هي المكتوبة، و`details`
        # تُحذف بالنواة. فـ`at_r` هنا هو الدليل الوحيد على العتبة الحيّة.
        return HealthStatus(state=HealthState.HEALTHY,
                            message="breakevens=%d tracked=%d at_r=%.2f مواصفات=%d سعر=ميتاتريدر بجهة المركز وقف_لم_يُرسَل=%d (%s) · لخطّة_المستويات=%d" % (
                                self._emitted, len(self._tracked), self._at_r, len(self._vpp),
                                self._stop_invalid, self._last_invalid, len(self._plan_yielded))
                            + " · plan_heard=%s awaiting_574=%d" % (self._plan_heard, len(self._awaiting_plan)),
                            details=details)
