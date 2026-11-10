from __future__ import annotations

import time
from typing import Any
import clock

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.financial_scope import financial_key, row_key, text
from spread_gate import spread_points, too_wide
from order_validation import _validate
from shared.order_validator_state import (health as gate_health, restore as restore_gate,
                                          snapshot as snapshot_gate)
import order_gates
import state_inputs
# ٢٠٢٦-٠٩-٢٣ (ختم `nq`) — وحداتٌ شقيقة نُقلت إليها أجسادٌ من هذا الملفّ حرفيًّا
# لحدّ ٤٠٠ سطرٍ فعليّ (م٩/ملف٤)، صفر تغيير سلوك: بطاقة الصفقة · قياسات المال ·
# هويّة القرار. أسماء الدوالّ هنا بقيت تفويضًا، فلم يتغيّر نداءٌ في `_on_built`.
import order_card_writer
import order_identity
import order_risk_measures
from order_risk_measures import _num
from shared.trade_card import RR_RULE

ATOM_VERSION = "5.17.0"
EVENT_BUILT = "execution.order.legal"
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): حالة الأصل من 519 — التجميد، وحكمُ ميزانيّة 518
# منقولًا في الصفّ نفسه (لماذا لا يُسمع 518 مباشرةً: `state_inputs.on_portfolio`).
EVENT_PORTFOLIO = "asset.portfolio.state"
EVENT_HALT = "emergency.halt"
EVENT_RESET = "risk.kill_switch.reset_requested"
EVENT_WHITELIST = "allowed.symbols.state"
EVENT_FINAL = "trading.final_decision"
EVENT_REJECTED = "execution.order.rejected"
EVENT_GATE = "execution.gate.state"
EVENT_TICK = "feed.mt5.tick"
EVENT_SPECS = "market.symbol_specs"
EVENT_ACCOUNT = "platform.account.state"
EVENT_GATE_COMMAND = "execution.gate.command"
EVENT_RECONCILE = "execution.reconcile.state"
EVENT_REFERENCE = "reference.health.state"
EVENT_EXPOSURE = "risk.exposure.state"
EVENT_MARGIN_VERDICT = "risk.margin.validation.completed"
EVENT_SNAPSHOT = "execution.snapshot.state"
GATE_ID = "552"
ACTION_OPEN = "OPEN"
PROTECTION_PERPETUAL = "PERPETUAL_BUDGET"
ORIGIN_PERPETUAL = "perpetual-delta"
FAIL_CLOSED = "RESTORE_FAILED_FAIL_CLOSED"
MIN_SPREAD_AGE_S = 0.1

# NQ seal, item 22, package T (T3): every refusal names the refusing stage and
# carries the barrier quadruple {value, threshold, reason, measured_at} --
# value/threshold stay None where this gate genuinely has no measurement
# (never invented), same rule as the decision-chain barriers (454).
STAGE_FINAL = "FINAL_VALIDATION"
STAGE_ACTIVATION = "ASSET_ACTIVATION"
# هامشُ فاصلةٍ عائمة عند مقارنة نسبتين — لا عيار.
_RATIO_EPS = 1e-9
# `_num` صار في order_risk_measures.py ويُستورد أعلاه، وثنائيّة الهويّة
# (`IDENTITY_FIELDS` · `WARNING_IDENTITY`) في order_identity.py — ٢٠٢٦-٠٩-٢٣.

_ORDER_FIELDS = (
    "account_id", "broker", "request_id", "action", "symbol", "side", "volume",
    "reference_price", "stop_loss", "take_profit", "cycle_id", "origin",
    "pair_id", "leg_role", "attempt", "pair_required", "protection_mode",
    "pair_volume", "purpose", "target_net", "current_net", "delta_net",
    "ticket", "params_json", "logical_symbol", "broker_symbol", "asset_canonical",
    "symbol_resolution_status", "symbol_spec", "snapshot_id",
    "risk_budget", "asset_stop_distance", "magic",
    "decision_id", "gate_request_id", "parent_decision_id", "owner_command_id",
    # ٢٠٢٦-٠٩-١٨ — جهةُ القرار تعبر مع **الرفض** أيضًا: أمرٌ يُرفض وجهةُ
    # قراره مجهولة لا يُعرف أكان رفضًا لقرارٍ صحيح أم لقرارٍ منقلب. وهذه
    # القائمة هي حمولة الرفض وحدها؛ القرار النهائيّ يمرّر الحمولة كاملةً.
    "decision_side",
)


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._enabled = False
        self._global_halted = False
        self._halted_accounts: dict[str, str] = {}
        self._restore_error = ""
        self._rehydrated = False
        self._allowed: set[str] = set()
        self._allowed_by_account: dict[str, set[str]] = {}
        self._whitelist_seen = False
        self._broker_by_account: dict[str, str] = {}
        self._pending_specs: list[dict[str, Any]] = []
        self._max_spread_points = 0.0
        self._spread_ttl_s = 5.0
        self._spread: dict[tuple[str, str, str], tuple[float, float]] = {}
        self._specs: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._reconcile: dict[tuple[str, str, str], str] = {}
        self._reference: dict[str, str] = {}
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): لحظةُ استلام المطابقة (لكلّ حساب) والمرجع (لكلّ
        # رمز) — `state_inputs.on_reconcile/on_reference`؛ والتعرّض يحمل طابعه في صفّه (`_received_mono`).
        self._reconcile_at: dict[tuple[str, str], float] = {}
        self._reference_at: dict[str, float] = {}
        self._state_max_age_s = order_gates.STATE_MAX_AGE_S  # يُعلَن في الشارة (shared/order_validator_state)
        self._exposure: dict[tuple[str, str], dict[str, Any]] = {}
        self._margin_verdicts: dict[tuple[str, str], dict[str, Any]] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): بوّابتا الفتح الجديدتان — الشرح في
        # `order_gates.asset_state_gate` و`order_gates.pre_trade_exposure`.
        self._portfolios: dict[tuple[str, str], dict[str, Any]] = {}
        self._asset_gate = self._exposure_cap = False
        self._asset_blocked = self._exposure_cap_blocked = self._exposure_reduced = 0
        self._last_exposure_cut = ""
        self._seen = self._decisions_finalized = self._rejected = 0
        self._whitelist_blocked = self._clock_blocked = self._spread_blocked = 0
        self._reconcile_blocked = self._reference_blocked = self._identity_blocked = 0
        self._exposure_blocked = self._ratio_blocked = self._budget_blocked = 0
        self._risk_unmeasured = 0
        self._last_unmeasured = ""
        self._cards: CardStore | None = None
        self._card_writes = 0
        # ‎_card_other_decision: حكمٌ لم يُكتب لأنّ البطاقة الحيّة لقرارٍ آخر (٢٠٢٦-١٠-٠٧)
        self._card_missing = self._card_other_decision = 0
        self._card_error = ""
        self._min_reward_risk = self._risk_floor_frac = 0.0
        self._risk_cap_frac = 1.0
        self._parent_decision_blocked = self._margin_verdict_blocked = 0
        self._snapshot_validity_blocked = 0
        self._identity_recovered = self._identity_incomplete = 0
        # ٢٠٢٦-٠٩-١٦: عشرة عدّادات حجب كانت كلّها في `details` والنواة تحذفها،
        # فالرسالة الوحيدة الباقية `finalized/rejected` لا تقول لماذا. ومقيس
        # في اليوم نفسه: تحذيرات هذه الذرّة لا تبلغ سجلّ الأخطاء إطلاقًا
        # (صفر ذكر لـ ATOM 552 مقابل ستّة رفوض SPREAD_TOO_WIDE في سجلّ
        # الصفقات). فآخر سبب رفض يسكن هنا ويخرج في `health.message`.
        self._last_reject = ""

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._enabled = bool(context.config["enabled"])
        self._max_spread_points = float(context.config.get("max_spread_points", 0.0))
        self._min_reward_risk = float(context.config.get("min_reward_risk", 0.0))
        self._risk_floor_frac = float(context.config.get("risk_floor_frac", 0.0))
        self._risk_cap_frac = float(context.config.get("risk_cap_frac", 1.0))
        self._spread_ttl_s = max(MIN_SPREAD_AGE_S, float(context.config.get("spread_ttl_s", 5.0)))
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): المفتاحان **مطلوبان** في مخطّط المانيفست
        # (غيابهما يُسقط البطاقة عند التحميل فلا تعمل البوّابة أصلًا)، وقيمتهما الحيّة
        # `true`. والافتراض `False` هنا لسياقٍ يُبنى بلا مانيفست (اختبارٌ قديم) وحده،
        # وإطفاءُ أيٍّ منهما يُعلَن في الشارة ويجعل الصحّة `DEGRADED`.
        self._asset_gate = context.config.get("asset_freeze_gate", False) is True
        self._exposure_cap = context.config.get("pre_trade_exposure_cap", False) is True
        self._open_card_store(context)
        for event, handler in (
            (EVENT_TICK, self._on_tick), (EVENT_SPECS, self._on_specs),
            (EVENT_ACCOUNT, self._on_account), (EVENT_BUILT, self._on_built),
            (EVENT_GATE_COMMAND, self._on_gate_command), (EVENT_GATE, self._rehydrate),
            (EVENT_HALT, self._on_halt), (EVENT_RESET, self._on_reset),
            (EVENT_WHITELIST, self._on_whitelist),
            (EVENT_RECONCILE, self._on_reconcile), (EVENT_REFERENCE, self._on_reference),
            (EVENT_EXPOSURE, self._on_exposure),
            (EVENT_MARGIN_VERDICT, self._on_margin_verdict),
            (EVENT_SNAPSHOT, self._on_snapshot),
            (EVENT_PORTFOLIO, self._on_portfolio)):
            context.subscribe(event, handler)

    async def start(self) -> None:
        self._running = True
        await self._publish_gate()
    async def stop(self) -> None: self._running = False
    async def shutdown(self) -> None: await self.stop()

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
        account = text(payload.get("account_id")); broker = text(payload.get("broker"))
        if account and broker:
            self._broker_by_account[account] = broker
            pending, self._pending_specs = self._pending_specs, []
            for item in pending: await self._on_specs(item)

    async def _on_halt(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
        self._rehydrated = True
        account = text(payload.get("account_id"))
        if account:
            self._halted_accounts[account] = text(payload.get("reason")) or "RISK_HALT"
        elif str(payload.get("scope") or "").upper() == "SYSTEM":
            self._global_halted = True
        else:
            self._identity_blocked += 1
            return
        await self._publish_gate()

    async def _on_reset(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
        self._rehydrated = True
        account = text(payload.get("account_id"))
        if account: self._halted_accounts.pop(account, None)
        elif str(payload.get("scope") or "").upper() == "SYSTEM": self._global_halted = False
        else: return
        await self._publish_gate()

    async def _publish_gate(self) -> None:
        if self._context is None: return
        status = "HALTED" if self._global_halted else "PARTIAL_HALT" if self._halted_accounts else "LIVE" if self._enabled else "STOPPED"
        await self._context.publish(EVENT_GATE, {
            "enabled": self._enabled, "halted": self._global_halted,
            # v5.4.2 (nq seal 2026-08-25): "open" -- the field the dashboard
            # banner reads (gate?.open) never existed on the wire, so the
            # banner said "closed" forever (documented display lie). The wire
            # now states it: open = enabled and not halted.
            "open": bool(self._enabled and not self._global_halted),
            "halted_accounts": dict(self._halted_accounts), "status": status,
            "seen": self._seen})

    async def _rehydrate(self, payload: dict[str, Any]) -> None:
        if self._rehydrated: return
        self._rehydrated = True
        if not isinstance(payload, dict):
            self._global_halted = True
            self._restore_error = FAIL_CLOSED
            return
        halted = payload.get("halted")
        accounts = payload.get("halted_accounts", {})
        if not isinstance(halted, bool) or not isinstance(accounts, dict):
            self._global_halted = True
            self._restore_error = FAIL_CLOSED
            return
        self._global_halted = halted
        self._halted_accounts = {str(k): str(v) for k,v in accounts.items() if str(k)}

    async def _on_gate_command(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict): return
        if str(payload.get("gate") or "") not in (GATE_ID, "both"): return
        wanted = payload.get("enabled")
        if isinstance(wanted, bool) and wanted != self._enabled:
            self._enabled = wanted; await self._publish_gate()

    async def _on_whitelist(self, payload: dict[str, Any]) -> None:
        # v5.4.0 (nq seal 2026-08-25, measured live): NO _running gate on a
        # STATE handler. 468 publishes the whitelist at ITS start -- before
        # this atom's start in boot order -- so the guard swallowed the only
        # whitelist this boot and every order died SYMBOL_NOT_ALLOWED while
        # the list plainly said BTCUSD allowed. Storing state is always safe;
        # the running gate belongs to command/decision handlers only.
        if not isinstance(payload, dict): return
        allowed = payload.get("allowed")
        if isinstance(allowed, list):
            self._allowed = {text(x) for x in allowed if text(x)}; self._whitelist_seen = True
        scoped = payload.get("allowed_by_account")
        if isinstance(scoped, dict):
            self._allowed_by_account = {str(a): {text(x) for x in values if text(x)}
                                        for a,values in scoped.items() if isinstance(values,list)}
            self._whitelist_seen = True

    async def _on_specs(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
        rows = payload.get("symbols")
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict): continue
            key = row_key(payload, row, self._broker_by_account)
            if key is not None: self._specs[key] = dict(row)
            elif text(row.get("account_id") or payload.get("account_id")) and payload not in self._pending_specs: self._pending_specs.append(dict(payload))

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict): return  # state handler: no running gate (v5.4.1)
        key = financial_key(payload, payload.get("symbol"), self._broker_by_account)
        if key is None: return
        points = spread_points(payload, self._specs.get(key))
        if points is not None: self._spread[key] = (points, time.monotonic(), time.time())

    async def _on_margin_verdict(self, payload: dict[str, Any]) -> None:
        """T3 (c): remember 526's margin verdict per (account, request)."""
        await state_inputs.on_margin_verdict(self, payload)

    async def _on_snapshot(self, payload: dict[str, Any]) -> None:
        """T3 (d) + T1: remember 583's snapshot verdict and the decision
        identity it carried, keyed by the immutable snapshot_id."""
        await state_inputs.on_snapshot(self, payload)

    async def _on_reconcile(self, payload: dict[str, Any]) -> None:
        await state_inputs.on_reconcile(self, payload)

    async def _on_exposure(self, payload: dict[str, Any]) -> None:
        await state_inputs.on_exposure(self, payload)

    async def _on_reference(self, payload: dict[str, Any]) -> None:
        await state_inputs.on_reference(self, payload)

    async def _on_portfolio(self, payload: dict[str, Any]) -> None:
        await state_inputs.on_portfolio(self, payload)

    @staticmethod
    def _opens_new_exposure(order: dict[str, Any]) -> bool:
        # ٢٠٢٦-٠٩-٢٣ (ختم `nq`): كلّ فتحٍ تعرّضٌ جديد — نُزع إعفاءُ الرِّجل الدائمة.
        return str(order.get("action") or ACTION_OPEN).upper() == ACTION_OPEN

    def _symbol_allowed(self, order: dict[str, Any]) -> bool:
        if str(order.get("action") or ACTION_OPEN).upper() != ACTION_OPEN: return True
        if not self._whitelist_seen: return False
        account = text(order.get("account_id")); allowed = self._allowed_by_account.get(account, self._allowed)
        names = {text(order.get(field)) for field in ("symbol","logical_symbol","asset_canonical","broker_symbol")}
        return bool(allowed and names & allowed)

    # ٢٠٢٦-٠٩-٢٣ (ختم `nq`): أجساد الدوالّ الخمس التالية نُقلت حرفيًّا إلى
    # order_card_writer.py (بطاقة الصفقة) وorder_risk_measures.py (نصف السبريد ·
    # النسبة · المال المعرَّض) — بشروحها. هنا تفويضٌ بالأسماء نفسها لا غير.
    def _open_card_store(self, context: AtomContext) -> None:
        order_card_writer.open_card_store(self, context)

    async def _write_card(self, symbol: str, fields: dict[str, Any], decision_id: Any = "") -> None:
        await order_card_writer.write_card(self, symbol, fields, GATE_ID, text(decision_id))

    def _half_spread(self, scoped: tuple[str, str, str] | None) -> float:
        return order_risk_measures.half_spread(self, scoped)

    def _reward_ratio(self, body: dict[str, Any], half: float = 0.0) -> float | None:
        return order_risk_measures.reward_ratio(body, half)

    def _risk_dollars(self, body: dict[str, Any],
                      scoped: tuple[str, str, str] | None) -> float | None:
        return order_risk_measures.risk_dollars(self, body, scoped)

    def _reconcile_status(self, key: tuple[str,str,str]) -> str:
        return self._reconcile.get(key) or self._reconcile.get((key[0], key[1], "*"), "UNKNOWN")

    async def _refuse(self, payload: dict[str, Any], reason: str,
                      stage: str = STAGE_FINAL, value: Any = None,
                      threshold: Any = None, measured_at: Any = None) -> None:
        self._rejected += 1
        self._last_reject = reason
        if value is not None or threshold is not None:
            self._last_reject = "%s %s/%s" % (reason, value, threshold)
        # الحكم يُكتب على البطاقة في المرحلة النهائيّة وحدها: من يراجع
        # صفقةً يريد أن يعرف أنّها رُدّت ولماذا، لا أن يبحث في سجلّ. وحجبُ
        # التفعيل (`ASSET_ACTIVATION`) يقع قبل أن تُبنى بطاقةٌ لأمرٍ بعينه
        # فلا محلّ له، ورفضُه يتكرّر آلافًا (١٬١٢٨ رفضًا اليوم).
        if stage == STAGE_FINAL:
            await self._write_card(text(payload.get("symbol")),
                                   {"verdict_552": "رُفض: %s" % reason}, payload.get("decision_id"))
        if self._context is not None:
            await self._context.publish(EVENT_REJECTED, {
                **{key: payload.get(key) for key in _ORDER_FIELDS},
                "request_id": text(payload.get("request_id")),
                "symbol": text(payload.get("symbol")), "side": text(payload.get("side")),
                "reason": reason, "stage": stage,
                "barrier": {"name": stage, "value": value, "threshold": threshold,
                            "reason": reason, "measured_at": measured_at},
                # ٢٠٢٦-٠٩-١٦ — مقيس على مخزن القرارات: **٤٬٤٠٥ صفّ
                # `ORDER_REJECTED` وكلّها `rejection_reason = NULL`**، منها
                # ٣٬٠٨٤ لبتكوين. و٧٠٧ يقرأ السبب من `payload["rejection"]
                # ["reason"]` (سطر ٦٦٦)، وهذه الذرّة تنشره في `barrier`
                # وحده — اسمان لشيءٍ واحد، فالعمود المخصّص له يبقى فارغًا
                # بينما السبب بجانبه. نفس عائلة `decision_side`/`side`.
                #
                # والشكل منسوخ من ناشره الأصليّ ٤٦٦ (سطر ١٤٤) لا مخترَعًا،
                # و`barrier` يبقى كما هو لقارئيه (٥٥٢ نفسها و٥٨٠) — إضافة
                # خالصة: صفر حذف وصفر تغيير شكل.
                "rejection": {"reason": reason, "stage": stage, "value": value,
                              "threshold": threshold, "time": time.time(),
                              "decision_id": text(payload.get("decision_id"))}})

    def _resolve_identity(self, body: dict[str, Any]) -> None:
        """T1 — الجسد في order_identity.py (نُقل حرفيًّا ٢٠٢٦-٠٩-٢٣)."""
        order_identity.resolve_identity(self, body)

    async def _on_built(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict): return
        self._seen += 1
        reason = _validate(payload)
        account = text(payload.get("account_id")); broker = text(payload.get("broker")) or self._broker_by_account.get(account, "")
        symbol = text(payload.get("symbol")); scoped = financial_key({"account_id":account,"broker":broker}, symbol, self._broker_by_account)
        if not reason and scoped is None:
            reason = "MISSING_ACCOUNT_BROKER_OR_SYMBOL"; self._identity_blocked += 1
        try:magic=int(payload.get("magic"))
        except (TypeError,ValueError):magic=0
        if not reason and magic<=0:reason="MISSING_MAGIC"
        if reason: await self._refuse(payload, reason); return
        if not self._symbol_allowed(payload):
            self._whitelist_blocked += 1
            allowed = sorted(self._allowed_by_account.get(account, self._allowed))
            await self._refuse(payload, "SYMBOL_NOT_ALLOWED", STAGE_ACTIVATION,
                               value=symbol, threshold=allowed or None,
                               measured_at=time.time()); return
        if self._max_spread_points > 0 and str(payload.get("action") or ACTION_OPEN).upper() == ACTION_OPEN:
            record = self._spread.get(scoped) if scoped is not None else None
            fresh = record if record and time.monotonic()-record[1] <= self._spread_ttl_s else None
            spread = fresh[0] if fresh else None
            if too_wide(spread, self._max_spread_points):
                self._spread_blocked += 1
                self._context.logger.warning(
                    "552 SPREAD_TOO_WIDE scope=%s spread=%r limit=%s record=%r "
                    "ttl=%s spread_keys=%s spec_keys=%s",
                    scoped, spread, self._max_spread_points, record,
                    self._spread_ttl_s, list(self._spread)[:5], list(self._specs)[:5])
                await self._refuse(payload, "SPREAD_TOO_WIDE", STAGE_FINAL,
                                   value=spread, threshold=self._max_spread_points,
                                   measured_at=fresh[2] if fresh else None); return
        assert scoped is not None
        body = {key: payload.get(key) for key in _ORDER_FIELDS}
        body.update({"account_id": account, "broker": broker, "symbol": symbol,
                     "action": str(payload.get("action") or ACTION_OPEN).upper()})
        self._resolve_identity(body)
        if not self._enabled: await self._refuse(body, "disabled"); return
        if self._global_halted or account in self._halted_accounts:
            await self._refuse(body, "halted"); return
        if body["action"] == ACTION_OPEN:
            # T3 (a/c/d): parent authority, margin verdict, snapshot validity
            # -- delegated to order_gates.py (item 25, 2026-08-27: the
            # extracted copy is now wired in instead of duplicated inline).
            if await order_gates.run_open_gates(self, body):
                return
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الأصل المجمّد أو المنفدة ميزانيّته
            # لا يُفتح من أيّ باب — مرآةُ حجب 581 (تدقيق ح-3).
            if await order_gates.asset_state_gate(self, body):
                return
        if self._opens_new_exposure(body) and clock.quality() != clock.SYNCED:
            self._clock_blocked += 1
            if self._clock_blocked <= 5:
                self._context.logger.warning(
                    "552 CLOCK_NOT_SYNCED quality=%r module=%r id=%s",
                    clock.quality(), getattr(clock, "__file__", "?"), id(clock))
            await self._refuse(body, "CLOCK_NOT_SYNCED")
            return
        if self._opens_new_exposure(body):
            reconcile = self._reconcile_status(scoped)
            # ٢٠٢٦-٠٩-٠٥: حساب فارغ لا يُنتج لقطة فعلية، فتبقى الحالة
            # WAITING_FOR_ACTUAL ويُرفض كل أمر — قفل ذاتي بعد إغلاق كل
            # المراكز. لا شيء عند الوسيط يخالف المرغوب حين لا مركز أصلًا.
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ذاك القفل أُغلق في 520 نفسه — الحساب الفارغ
            # يُنشر `MATCH_EMPTY_ACCOUNT` كلّ لقطة، وتُعلَّم معه نطاقاتُه المرغوبة «رُئيت»
            # (`520/atom.py:260-268`). فبقي `WAITING_FOR_ACTUAL` يعني حرفيًّا «لا لقطة وسيطٍ لهذا
            # النطاق بعد» — غيابُ معرفةٍ كان يُقبل مطابقةً. لا يُفتح عليه الآن (يفشل مغلقًا)؛
            # والمقيس في لقطة 520 الحيّة: النطاقات الستّة المتداولة كلّها «رُئيت»، فلا يبلغه إلّا
            # GBPUSD (لم يُتداول قطّ) أو مطابقةٌ مُسحت حالتها. والخروج لا يمرّ من هنا أصلًا.
            if reconcile in {"MATCH", "MATCH_EMPTY_ACCOUNT"} and \
                    order_gates.state_stale(self._reconcile_at.get((account, broker))):
                # ٢٠٢٦-١٠-٠٢: 520 صمت عن الحساب أكثر من عمر صورة المراكز ⟸ مجهول (تدقيق م-5).
                self._reconcile_blocked += 1
                await self._refuse(body, "RECONCILIATION_STALE", value=order_gates.state_age(
                    self._reconcile_at.get((account, broker))),
                    threshold=order_gates.STATE_MAX_AGE_S)
                return
            if reconcile not in {"MATCH", "MATCH_EMPTY_ACCOUNT"}:
                self._reconcile_blocked += 1
                if self._reconcile_blocked <= 8:
                    self._context.logger.warning(
                        "552 RECONCILIATION_NOT_MATCHED status=%r scope=%r "
                        "known=%r", reconcile, scoped,
                        {str(k): v for k, v in list(self._reconcile.items())[:6]})
                await self._refuse(body, "RECONCILIATION_NOT_MATCHED", value=reconcile)
                return
            reference = self._reference.get(symbol, "UNKNOWN")
            if reference in {"HEALTHY", "FALLBACK"} and \
                    order_gates.state_stale(self._reference_at.get(symbol)):
                self._reference_blocked += 1
                await self._refuse(body, "REFERENCE_STALE", value=order_gates.state_age(
                    self._reference_at.get(symbol)), threshold=order_gates.STATE_MAX_AGE_S)
                return
            if reference not in {"HEALTHY", "FALLBACK"}:
                self._reference_blocked += 1
                await self._refuse(body, "REFERENCE_NOT_USABLE")
                return
            exposure = self._exposure.get((account, broker))
            if exposure is None or exposure.get("usable_for_new_exposure") is not True:
                self._exposure_blocked += 1
                await self._refuse(body, "EXPOSURE_STATE_NOT_USABLE")
                return
            if order_gates.state_stale(exposure.get("_received_mono")):
                # ٢٠٢٦-١٠-٠٢: سقف التعرّض يفحص العمر حين يحكم؛ وهنا يُفحص دائمًا، بالاسم نفسه.
                self._exposure_blocked += 1
                await self._refuse(body, "EXPOSURE_STATE_STALE", value=order_gates.state_age(
                    exposure.get("_received_mono")), threshold=order_gates.STATE_MAX_AGE_S,
                    measured_at=exposure.get("timestamp"))
                return
            # 🔴 ٢٠٢٦-٠٩-١٨ (ختم NQ) — حكم المالك: «صفقة وصلت للإكسبرت
            # وتنفّذت مثل طلقة، اخترقت كل حرّاسكم».
            #
            # حرّاس النسبة كلّهم فوق: ٥٥٥ يرفض دون ٣ و٥٥١ يرفض هدفًا أقصر
            # من مضاعفه. ثمّ يوسّع ٥٨٤ الوقفَ وحده إلى أرضيّة الشرعيّة،
            # فتنقلب النسبة **بعد** كل فحص. ولا أحد يعيد قياسها: بحثًا في
            # هذه الذرّة و`order_gates` و٦٠١ عن `reward` أو `risk_distance`
            # كان الجواب صفرًا. فمرّت ١١٦ صفقة من ١٩٥ (٥٩٫٥٪) دون 1:3،
            # وثلاثٌ منها هدفُها أقصر من وقفها.
            #
            # وهذه آخرُ بوّابةٍ قبل الجسر: تُقاس النسبة هنا على الأرقام
            # **النهائيّة** — ما يصل الوسيط حرفيًّا، لا ما نُوي قبله.
            # 🔴 ٢٠٢٦-٠٩-١٩ (أمر المالك) — «حارس يستلم صفقة فيها هدف وستوب
            # تمرق، ما فيها تُردّ · ينحسب لوته صحيح وتفتح».
            #
            # فردُّ النسبة يسقط من آخر بوّابة أيضًا. والنسبةُ تبقى محسوبةً
            # على الأرقام النهائيّة ومنشورةً ومعلَنةً في الشارة — **تُقاس
            # ولا تحكم**. ومقياسٌ يُعلَن غيرُ حارسٍ يردّ.
            #
            # وما يبقى هنا حراسةً: اكتمالُ الهدف والوقف وجهتُهما، وسلامةُ
            # الهويّة والسلطة والميزانيّة والهامش — أي أنّ الأمر **مكتمل**
            # لا أنّه **مُجدٍ**. والجدوى حكمُ صاحب الفكرة لا حكمُ البوّاب.
            ratio = self._reward_ratio(body, self._half_spread(scoped))
            if self._min_reward_risk > 0.0 \
                    and ratio is not None and ratio + _RATIO_EPS < self._min_reward_risk:
                self._ratio_blocked += 1
                if self._ratio_blocked <= 8:
                    self._context.logger.warning(
                        "552 نسبة=%.3f دون عيار %g لـ%s %s — تُقاس ولا تحكم، "
                        "والأمر يمرّ", ratio, self._min_reward_risk, symbol,
                        body.get("side"))
            # 🔴 ٢٠٢٦-٠٩-١٨ (ختم NQ) — حكم المالك: «شوف باقي أزواج كلّها
            # تنحسب صح؟». الجواب المقيس على ١٩٧ أمرًا وصلت الوسيط: **لا**.
            #
            #   BTCUSD  138 أمرًا — ضمن ±٢٠٪ من المئة: 40 (29٪)
            #   XAUUSD   33        10 (30٪)      USTEC 25 — 5 (20٪)
            #   والمدى من 0.20$ إلى 218.96$ وميزانيّةُ كلٍّ منها 100$.
            #
            # والسبب: ٥١٣ يحجّم على وقفٍ من عياره (5.81$ للذهب) بينما
            # يُرسَل وقف التحليل (0.36$)، ثمّ يوسّع ٥٨٤ الوقفَ إلى أرضيّته
            # **ويقصّ الحجم بنسبة التوسيع** — فتصير الخسارة فُتاتًا.
            #
            # ولا يجوز إصلاحُه برفع الحجم هنا: ٥٨٥ حارس الهامش يقع قبل
            # ٥٥١، فحجمٌ يُرفع بعده لا يُفحص هامشه. فيُرفض الأمر الذي لا
            # يطابق حجمُه ميزانيّته — «المرفوضة تُرفض ولا تُعدَّل».
            budget = _num(body.get("risk_budget"))
            if budget and budget > 0.0 and self._risk_floor_frac > 0.0:
                exposed = self._risk_dollars(body, scoped)
                # 🔴 ٢٠٢٦-٠٩-٢٣ (ختم `nq`) — كان `None` يمرّ صامتًا: «لا أعرف كم
                # المعرَّض» صار «مطابق». الآن مالٌ لا يُقاس لا يصل الوسيط،
                # ويُرفض بسببه المسمّى لا بصمت.
                if exposed is None:
                    self._budget_blocked += 1
                    self._context.logger.warning(
                        "552 RISK_UNMEASURED %s %s: %s — لا يصل الوسيط",
                        symbol, body.get("side"), self._last_unmeasured or "مدخل ناقص")
                    await self._refuse(body, "RISK_UNMEASURED", STAGE_FINAL,
                                       threshold=round(budget, 2))
                    return
                if exposed is not None:
                    low = budget * self._risk_floor_frac
                    high = budget * self._risk_cap_frac
                    if exposed < low or exposed > high:
                        self._budget_blocked += 1
                        if self._budget_blocked <= 8:
                            self._context.logger.warning(
                                "552 RISK_OFF_BUDGET %s %s: معرَّض=%.2f$ "
                                "ميزانيّة=%.2f$ مدى=[%.2f, %.2f] — لا يصل الوسيط",
                                symbol, body.get("side"), exposed, budget, low, high)
                        await self._refuse(body, "RISK_OFF_BUDGET", STAGE_FINAL,
                                           value=round(exposed, 2),
                                           threshold=round(budget, 2))
                        return
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): 🔴 حدّ التعرّض قبل الأمر لا بعده.
            # آخرُ فحصٍ قبل النشر عمدًا: الميزانيّة أعلاه تُقاس على الحجم كما بُني (تكشف
            # خطأ التحجيم)، ثمّ يُقصّ الحجم هنا إلى ما يبقى تحت حدّ 508 — فالمال المعرَّض
            # المنشور أدناه يُحسب على الحجم الذي يخرج فعلًا.
            if await order_gates.pre_trade_exposure(self, body, scoped):
                return
        # ٢٠٢٦-٠٩-١٨ — طلبُ جلسة اللوحة: «سمِّ لي الحقل الذي يحمل النسبة
        # والمال المعرَّض؛ لا أعرض رقمًا لا أعرف ناشره». وهي محقّة: حارسُها
        # `check_dashboard_fields.py` يسقط على حقلٍ لا ينشره ناشره. فالرقمان
        # يُحسبان هنا — حيث تُقاس البوّابة — ويُنشران مع الأمر النهائيّ، لا
        # تُترك اللوحة تشتقّهما من ثلاثة حقولٍ ومواصفات رمز.
        ratio = self._reward_ratio(body, self._half_spread(scoped))
        if ratio is not None:
            body["reward_risk_ratio"] = round(ratio, 4)
        exposed = self._risk_dollars(body, scoped)
        if exposed is not None:
            body["risk_dollars"] = round(exposed, 2)
        # العياران يعبران مع كلّ أمرٍ — لا ليُعرَف الرقم وحده بل ليُعرَف
        # **هل هناك حارسٌ أصلًا**: صفرٌ يعني بوّابةً مفتوحة، وغيابُ النسبة
        # مع عيارٍ موجب يعني أسعارًا ناقصة. غيابٌ واحدٌ بمعنيين لا يُقرأ.
        body["reward_risk_min"] = self._min_reward_risk
        body["risk_budget_bounds"] = [self._risk_floor_frac, self._risk_cap_frac]
        self._decisions_finalized += 1; await self._context.publish(EVENT_FINAL, body)
        # البطاقة تُكتب **بعد** النشر: سجلٌّ لا بوّابة، فلا يتأخّر أمرٌ
        # بسبب قرص. و`sent_stop`/`rr_at_send` مقصودان — بطاقةُ التحليل
        # تحمل النسبة عند البناء، وهذه تحمل ما وصل الوسيط حرفيًّا. وبينهما
        # ٥٨٤ الذي حوّل 1:7.1 إلى 1:0.945 ذات مرّة (التذكرة 1943171698)،
        # فالفرقُ بين الرقمين يُقرأ الآن بدل أن يُكتشف بعد الخسارة.
        budget = _num(body.get("risk_budget"))
        await self._write_card(text(body.get("symbol")), {
            "verdict_552": "مرّر", "volume": _num(body.get("volume")),
            "sent_stop": _num(body.get("stop_loss")),
            "sent_target": _num(body.get("take_profit")),
            "rr_at_send": None if ratio is None else round(ratio, 4),
            "rr_rule": RR_RULE,
            "risk_amount": None if exposed is None else round(exposed, 2),
            "symbol_budget": budget,
            "budget_left": None if (budget is None or exposed is None)
                           else round(budget - exposed, 2)}, body.get("decision_id"))

    async def snapshot(self) -> dict[str, Any]:
        return snapshot_gate(self, ATOM_VERSION)

    async def restore(self, state: dict[str, Any]) -> None:
        await restore_gate(self, state, FAIL_CLOSED)

    async def health_check(self) -> HealthStatus:
        return gate_health(self)
