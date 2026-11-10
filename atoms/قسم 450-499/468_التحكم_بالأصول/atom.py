from __future__ import annotations

from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.cycle_identity import cycle_key_of

ATOM_VERSION = "1.6.0"
# سقف الأسماء في رسالة الصحّة — الرسالة تُعرض على اللوحة فلا تكبر بلا حدّ،
# والفائض يُعلن عددًا ولا يُكتم.
_MAX_NAMED_SYMBOLS = 8
_MAX_NAMED_ACCOUNTS = 3
# v1.5.0 (2026-08-27, item 12/27 of the 27-atom review -- an unknown
# command on a shared event silently splits the allow-list): _on_asset_
# command called self._allowed_by_account.setdefault(account, set(self.
# _allowed)) UNCONDITIONALLY whenever account was non-empty, before ever
# checking whether `command` was one it recognizes. risk.asset.command is
# a shared event -- any unrecognized command (a typo, a future command
# not meant for this atom, a malformed payload) or even a RECOGNIZED
# command with nothing to do (PAUSE on a symbol already absent, RESUME on
# one already present) still materialized a per-account snapshot of the
# global allow-list at that moment. Once materialized, _on_tick's lookup
# (self._allowed_by_account.get(account, self._allowed)) permanently
# prefers that frozen snapshot over the live global set -- a LATER global
# addition via _on_activate (no account_id) never reaches that account
# again. Silent, no log, no error. Fixed by computing the EFFECTIVE set
# read-only first and only materializing (setdefault) the per-account
# partition once a real mutation is about to happen.

EVENT_IN = "market.tick.validated"
EVENT_FILTER = "decision.filter.asset.state"
EVENT_WHITELIST = "allowed.symbols.state"
EVENT_ACTIVATE = "perpetual.asset.activate"
EVENT_ASSET_COMMAND = "risk.asset.command"

_REMOVE_COMMANDS = {"PAUSE", "FREEZE"}
_RESTORE_COMMANDS = {"RESUME", "UNFREEZE"}

ID_FILTER = "asset_filter"
STATUS_OK = "ok"
SIGNAL_ALLOW = "allow"
SIGNAL_BLOCK = "block"
METHOD = "whitelist"

REASON_NOT_STARTED = "NOT_STARTED"
REASON_EMPTY = "EMPTY_WHITELIST_BLOCKS_ALL"
# لقطة غير صالحة تعني أنّ قائمة المالك عادت إلى المانيفست وحده — أي أنّ
# تفعيلاته ضاعت. تُعلَن في `message` لا في `details`: الأخيرة تموت عند
# حدود النواة (`core/api/app.py::_serialize_atom`) فلا تبلغ اللوحة.
RESTORE_INVALID = "RESTORE_INVALID_CONFIG_ONLY"

CONFIDENCE_PASS = 1.0
CONFIDENCE_FAIL = 0.0


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._allowed: set[str] = set()
        self._config_allowed: set[str] = set()
        self._allowed_by_account: dict[str, set[str]] = {}
        self._restore_note = ""
        self._seen = 0
        self._blocked = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        self._config_allowed = {str(s) for s in context.config.get("allowed_symbols", [])}
        self._allowed = set(self._config_allowed)
        context.subscribe(EVENT_IN, self._on_tick)
        context.subscribe(EVENT_ACTIVATE, self._on_activate)
        context.subscribe(EVENT_ASSET_COMMAND, self._on_asset_command)

    # v1.6.0: القائمة حالةٌ يضعها المالك بيده — فلا تُنسى عند إعادة تحميل.
    # مقيس ٢٠٢٦-٠٩-١٠: فعّل المالك أربعة أصول من اللوحة ودخل EURUSD صفقة
    # حقيقية، ثم مسحَتها إعادةُ تحميل ساخنة لأنّ الذرّة بلا حفظ — فعاد
    # `allowed=1 [BTCUSD]` وحُجب ٩٧–١٠٠٪ من الرموز الأربعة خلال دقيقة.
    # الخطر ليس في إعادة التحميل وحدها: أيّ إقلاع للمنصّة كان سيفعلها.
    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION,
                "allowed": sorted(self._allowed),
                "allowed_by_account": {a: sorted(v) for a, v
                                       in self._allowed_by_account.items()},
                # الأساس الذي أُخذت عليه اللقطة — يسمح بالتقاط ما يضيفه
                # المالك للمانيفست لاحقًا بلا أن تطغى اللقطة على تعديله.
                "config_baseline": sorted(self._config_allowed)}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict) or not isinstance(state.get("allowed"), list):
            self._restore_note = RESTORE_INVALID
            return
        # ما أُضيف إلى المانيفست بعد أخذ اللقطة يدخل؛ وما أُزيل حيًّا
        # (`PAUSE`) يبقى مُزالًا — فقدُ إيقافٍ أخطر من فقد تفعيل.
        baseline = {str(s) for s in (state.get("config_baseline") or [])
                    if isinstance(s, str)}
        added_in_config = self._config_allowed - baseline
        self._allowed = {str(s) for s in state["allowed"] if isinstance(s, str)}
        self._allowed |= added_in_config
        rows = state.get("allowed_by_account")
        restored: dict[str, set[str]] = {}
        if isinstance(rows, dict):
            for account, symbols in rows.items():
                if isinstance(account, str) and account and isinstance(symbols, list):
                    restored[account] = {str(s) for s in symbols if isinstance(s, str)}
        self._allowed_by_account = restored
        self._restore_note = ""

    async def start(self) -> None:
        self._running = True
        await self._publish_whitelist()

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _publish_whitelist(self) -> None:
        if self._context is None:
            return
        await self._context.publish(EVENT_WHITELIST, {
            "id": ID_FILTER, "status": STATUS_OK, "allowed": sorted(self._allowed),
            "allowed_by_account": {a: sorted(v) for a, v in self._allowed_by_account.items()}})

    async def _on_activate(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "").strip()
        account = str(payload.get("account_id") or "").strip()
        if not symbol:
            return
        if account:
            allowed = self._allowed_by_account.setdefault(account, set(self._allowed))
            allowed.add(symbol)
        else:
            self._allowed.add(symbol)
        # v1.x (nq seal 2026-08-25): an activation ALWAYS republishes the
        # whitelist -- even when the symbol was already listed. The old
        # "publish only on change" left a consumer that missed the boot-time
        # state with no second chance (measured live: 552 swallowed the boot
        # whitelist and the owner's activation republished nothing, so six
        # built orders died SYMBOL_NOT_ALLOWED). A cheap reaffirmation kills
        # that trap family.
        await self._publish_whitelist()

    async def _on_asset_command(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "").strip()
        account = str(payload.get("account_id") or "").strip()
        command = str(payload.get("command") or "").strip().upper()
        if not symbol:
            return
        current = self._allowed_by_account.get(account, self._allowed) if account else self._allowed
        if command in _REMOVE_COMMANDS and symbol in current:
            allowed = self._allowed_by_account.setdefault(account, set(self._allowed)) if account else self._allowed
            allowed.discard(symbol)
            await self._publish_whitelist()
        elif command in _RESTORE_COMMANDS and symbol not in current:
            allowed = self._allowed_by_account.setdefault(account, set(self._allowed)) if account else self._allowed
            allowed.add(symbol)
            await self._publish_whitelist()

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = payload.get("symbol")
        if not symbol:
            return
        symbol = str(symbol)
        timeframe = "tick"
        account = str(payload.get("account_id") or "")
        effective = self._allowed_by_account.get(account, self._allowed)
        passed = symbol in effective
        sequence = str(payload.get("sequence") or "")
        cycle_id = str(payload.get("cycle_id") or cycle_key_of(
            payload, symbol=symbol, timeframe=timeframe, period_start=sequence))
        self._seen += 1
        if not passed:
            self._blocked += 1
        await self._context.publish(EVENT_FILTER, {
            "symbol": symbol, "account_id": payload.get("account_id"),
            "id": ID_FILTER, "status": STATUS_OK,
            "cycle_id": cycle_id, "timeframe": timeframe,
            "signal": SIGNAL_ALLOW if passed else SIGNAL_BLOCK,
            "confidence": CONFIDENCE_PASS if passed else CONFIDENCE_FAIL,
            "warnings": [],
            "metadata": {"method": METHOD, "timeframe": timeframe, "passed": passed}})

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message=REASON_NOT_STARTED)
        details = {"allowed_symbols": sorted(self._allowed), "seen": self._seen,
                   "blocked": self._blocked}
        if not self._allowed:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_EMPTY,
                                details=details)
        # v1.5.1: `details` لا يخرج من النواة أبدًا — `core/api/app.py`
        # (`_serialize_atom`) يُخرج `state` و`message` فقط. و`allowed=1` كان
        # يخفي **أيّ** أصل هو المسموح، وهو سطح قرار المالك نفسه (رمز واحد
        # الآن، ثم يفعّل غيره بيده عبر `risk.asset.command`). فالأسماء تُكتب
        # في الرسالة، والفائض يُعلن عددًا لا يُكتم.
        # v1.5.2: القائمة العامّة وحدها تكذب حين يفعّل المالك أصلًا من اللوحة.
        # `activate_asset` يحمل `account_id`، فـ`_on_activate` يضعه في
        # `_allowed_by_account[<الحساب>]` لا في `_allowed` — و`_on_tick`
        # يرجّح تلك القائمة على العامّة. مقيس ٢٠٢٦-٠٩-١٠: فعّل المالك
        # XAUUSD · EURUSD · US30 · USTEC من اللوحة (الأوامر 481-484)، ودخل
        # EURUSD صفقة حقيقية، بينما الرسالة تقول `allowed=1 [BTCUSD]`
        # و`accounts=1` — عددٌ بلا أسماء. فالقائمة **الفعّالة** لكل حساب
        # تُكتب هنا: هي التي تحكم من يمرّ، وهي سطح قرار المالك.
        def _named(symbols: set[str]) -> str:
            names = sorted(symbols)
            listed = ",".join(names[:_MAX_NAMED_SYMBOLS])
            if len(names) > _MAX_NAMED_SYMBOLS:
                listed += ",+%d" % (len(names) - _MAX_NAMED_SYMBOLS)
            return listed

        parts = ["allowed=%d [%s]" % (len(self._allowed), _named(self._allowed))]
        for account in sorted(self._allowed_by_account)[:_MAX_NAMED_ACCOUNTS]:
            effective = self._allowed_by_account[account]
            parts.append("%s=%d [%s]" % (account, len(effective), _named(effective)))
        extra = len(self._allowed_by_account) - _MAX_NAMED_ACCOUNTS
        if extra > 0:
            parts.append("+%d حسابًا" % extra)
        if self._restore_note:
            parts.append(self._restore_note)
        return HealthStatus(state=HealthState.HEALTHY,
                            message="%s seen=%d blocked=%d" % (
                                " · ".join(parts), self._seen, self._blocked),
                            details=details)
