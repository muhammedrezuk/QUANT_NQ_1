from __future__ import annotations

import math
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "4.2.0"

EVENT_TICK = "market.tick"
EVENT_ACCOUNT = "platform.account.state"
EVENT_VALID = "market.tick.validated"
EVENT_INVALID = "market_data.validation_failed"
EVENT_STATE = "market_data.validation.state"
EVENT_OUT = EVENT_INVALID

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_TICKS = "NO_TICKS_YET"

# عقد الحقول التي تعبر البوّابة كما جاءت — يختبره اختبار الذرّة واختبار
# مسار القرار (`tests/test_market_decision_path.py`)، فلا يُحذف.
CONTRACT_FIELDS = (
    "symbol", "bid", "ask", "price", "volume", "provider", "timestamp",
    "exchange_timestamp", "received_at", "account_id",
)

# ٢٠٢٦-٠٩-١٠ (ختم NQ) — الرفض كان يُعدّ ولا يُعلَّل.
#
# مقيس قبل هذا التغيير: `invalid=5,723` من `checked=27,821` (20.6%) ولا
# سبيل لمعرفة السبب من الذرّة: العدد وحده في `message`، ولا توزيع في أيّ
# مكان. السبب كان يصل `market_data.validation_failed` إلى 704 و831
# ويُخزَّن في `timeline.db` — لكن قراءته تحتاج فتح المخزن والاستعلام،
# وهو ما استغرق جلسة كاملة لمعرفة سبب واحد.
#
# التوزيع يوضع في `message` لا في `details`: النواة تحذف `details` قبل
# أن تبلغ اللوحة، فما يُكتب هناك لا يراه المالك.
#
# ولا يمسّ هذا منطق القبول أو الرفض بحرف: العدّ فقط.
_TOP_PROBLEMS = 3


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class Atom(AtomBase):

    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._broker_by_account: dict[str, str] = {}
        self.checked_count = 0
        self.valid_count = 0
        self.failed_count = 0
        self.problem_counts: dict[str, int] = {}
        self.failed_by_symbol: dict[str, int] = {}

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        context.subscribe(EVENT_TICK, self._on_tick)
        context.subscribe(EVENT_ACCOUNT, self._on_account)

    async def start(self) -> None:
        self._running = True
        await self._publish_state("ACTIVE")

    async def stop(self) -> None:
        if self._running:
            self._running = False
            await self._publish_state("STOPPED")

    async def shutdown(self) -> None:
        await self.stop()

    async def _publish_state(self, status: str) -> None:
        if self._context is not None:
            await self._context.publish(EVENT_STATE, {
                "status": status,
                "usable_for_decision": status == "ACTIVE",
                "checked": self.checked_count,
                "valid": self.valid_count,
                "invalid": self.failed_count,
            })

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = str(payload.get("account_id") or "").strip()
        broker = str(payload.get("broker") or "").strip()
        if account and broker:
            self._broker_by_account[account] = broker

    @staticmethod
    def _validate(payload: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        symbol = str(payload.get("symbol") or "").strip()
        account = str(payload.get("account_id") or "").strip()
        provider = str(payload.get("provider") or "").strip()
        if not symbol:
            problems.append("missing_symbol")
        if not account:
            problems.append("missing_account_id")
        if not provider:
            problems.append("missing_provider")

        bid = number(payload.get("bid"))
        ask = number(payload.get("ask"))
        if bid is None:
            problems.append("invalid_or_missing_bid")
        elif bid <= 0:
            problems.append("nonpositive_bid")
        if ask is None:
            problems.append("invalid_or_missing_ask")
        elif ask <= 0:
            problems.append("nonpositive_ask")
        if bid is not None and ask is not None and ask <= bid:
            # ٢٠٢٦-٠٩-٠٧ — كان الشرط `ask < bid` فيمرّ السبريد الصفريّ
            # (`bid == ask`) في مسار التِكّة ويُرفض في مسار العمق
            # (`106:BAD_CROSSED` يفحص `best_bid >= best_ask`). اختلاف مدقّقَين
            # على الحالة نفسها. وسعرٌ يُشترى ويُباع بالقيمة عينها ليس سوقًا:
            # هو دفتر معطوب أو مستوى تبخّر بين طرفيه، وقياس السبريد عليه
            # يعطي صفرًا فيدخل تكلفةَ عبورٍ كاذبة إلى حساب اللوت. يُوسم هنا
            # كما يُوسم هناك، والاسم واحد كي يقرأ المالك سببًا واحدًا.
            problems.append("crossed_spread")

        price = number(payload.get("price"))
        if price is None:
            problems.append("invalid_or_missing_price")
        elif price <= 0:
            problems.append("nonpositive_price")

        stamp = number(payload.get("timestamp"))
        if stamp is None or stamp <= 0:
            problems.append("invalid_timestamp")
        for field in ("exchange_timestamp", "received_at"):
            if payload.get(field) is not None:
                value = number(payload.get(field))
                if value is None or value <= 0:
                    problems.append("invalid_" + field)
        if payload.get("volume") is not None:
            volume = number(payload.get("volume"))
            if volume is None:
                problems.append("invalid_volume")
            elif volume < 0:
                problems.append("negative_volume")
        return list(dict.fromkeys(problems))

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        self.checked_count += 1
        problems = self._validate(payload)
        if problems:
            self.failed_count += 1
            for problem in problems:
                self.problem_counts[problem] = self.problem_counts.get(problem, 0) + 1
            symbol_key = str(payload.get("symbol") or "?")
            self.failed_by_symbol[symbol_key] = self.failed_by_symbol.get(symbol_key, 0) + 1
            await self._context.publish(EVENT_INVALID, {
                "source_event": EVENT_TICK,
                "status": "INVALID",
                "problems": problems,
                # ٢٠٢٦-٠٩-١٦ (ختم NQ) — ثلاثة حقول تُرفع إلى الجذر، ولا
                # يُحذف شيء. مستهلكا هذا الحدث يقرآن من الجذر لا من
                # `payload`، فكان كلاهما يعمل أعمى:
                #
                # • 704 (مخزن الخطّ الزمنيّ) يقرأ `symbol` و`account_id`
                #   من الجذر ليملأ عموديهما. مقيس على القرص: **294,784
                #   صفًّا من رفض هذه الذرّة، عمود `symbol` فارغ 100%
                #   و`account_id` فارغ 100%** — بينما 115 في القسم نفسه
                #   تضعهما في الجذر فعمودها ممتلئ 100%. فأيّ سؤال عن
                #   «كم رُفض من الذهب» كان يتطلّب فكّ 294 ألف JSON.
                #
                # • 831 (المنذِر) يصنّف هذا الحدث `CRITICAL` ثمّ يبحث عن
                #   تفصيله في `error`/`message`/`reason`/`detail` — ولا
                #   واحد منها كان موجودًا، فيطلق إنذارًا حرجًا **بلا سبب**.
                #   `problems` تبقى كما هي لمن يقرأ القائمة.
                "symbol": payload.get("symbol"),
                "account_id": payload.get("account_id"),
                "reason": ", ".join(problems),
                "payload": dict(payload),
            })
            return

        validated = dict(payload)
        account = str(payload.get("account_id") or "")
        broker = self._broker_by_account.get(account)
        if broker and not validated.get("broker"):
            validated["broker"] = broker
        self.valid_count += 1
        await self._context.publish(EVENT_VALID, validated)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"checked": self.checked_count, "valid": self.valid_count,
                   "invalid": self.failed_count,
                   "problems": dict(self.problem_counts),
                   "invalid_by_symbol": dict(self.failed_by_symbol),
                   "accounts_with_broker": len(self._broker_by_account)}
        if self.checked_count == 0:
            return HealthStatus(state=HealthState.DEGRADED,
                                message=REASON_NO_TICKS, details=details)
        state = HealthState.DEGRADED if self.failed_count and not self.valid_count else HealthState.HEALTHY
        message = "checked=%d valid=%d invalid=%d" % (
            self.checked_count, self.valid_count, self.failed_count)
        if self.failed_count:
            message += " (%.1f%%)" % (100.0 * self.failed_count / self.checked_count)
            top = sorted(self.problem_counts.items(), key=lambda kv: -kv[1])
            message += " · " + " ".join(
                "%s=%d" % (name, count) for name, count in top[:_TOP_PROBLEMS])
            worst = sorted(self.failed_by_symbol.items(), key=lambda kv: -kv[1])
            message += " · أسوأ=" + ",".join(
                "%s:%d" % (symbol, count) for symbol, count in worst[:_TOP_PROBLEMS])
        return HealthStatus(state=state, message=message, details=details)
