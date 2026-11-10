from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.durable_execution_journal import Journal
from shared.financial_scope import row_key, text
# v3.4.2 (٢٠٢٦-١٠-٠١، ختم `Nq`) — حدّ المادة 9 (٤٠٠ سطر فعليّ): نُقل قياسُ
# الانزلاق (ومعه `number`) وهويّةُ القرار **حرفيًّا** إلى ملفّين شقيقين في مجلّد
# الذرّة، والتابعان بأسمائهما باقيان هنا يُحيلان إليهما. لا سلوك جديد.
from execution_confirm_identity import IDENTITY_ALIASES, IDENTITY_FIELDS, WARNING_IDENTITY
from execution_confirm_slippage import SIDE_BUY, _PRICE_DP, number
import execution_confirm_identity
import execution_confirm_slippage

ATOM_VERSION = "3.4.2"
# v3.1.1 (2026-08-27, item 24/27 of the 27-atom review -- blocking I/O at
# boot + restore() without guarding): initialize() called
# self._journal.ensure() (mkdir + open a raw sqlite connection + run
# schema statements + commit -- all synchronous) directly on the event
# loop, unlike every OTHER Journal call in this same atom
# (remember_request/commit_event/pending_outputs/mark_emitted/counts),
# which already run via asyncio.to_thread. Now consistent. restore()'s
# top-level guard was already fine, but the four counters were
# int(state.get(...) or 0) with no try/except -- a corrupted non-numeric
# value (e.g. a string) raised a raw, uncontrolled ValueError instead of
# the same clean INVALID_EXECUTION_CONFIRM_STATE the top-level check
# already uses, and a failure partway through left self torn (earlier
# counters already committed). Both fixed.
EVENT_IN = "platform.trade_event"
EVENT_OUT = "market.outcome.realized"
EVENT_ACK = "execution.command.ack"
EVENT_REJECTED = "execution.confirmation.rejected"
EVENT_FINAL = "trading.final_decision"
EVENT_SPECS = "market.symbol_specs"
EVENT_ACCOUNT = "platform.account.state"
EVT_OPENED = "OPENED"
EVT_CLOSED = "CLOSED"
EVT_PARTIAL = "PARTIAL"
# هويّةُ القرار (`IDENTITY_FIELDS` · `IDENTITY_ALIASES` · `WARNING_IDENTITY`) وقياسُ
# ٢٠٢٦-٠٩-١٨ الذي أوجب الجسرَ بالتذكرة والاسمَ الثاني ⟵ `execution_confirm_identity.py`.
# الخريطة تُبنى من `processed_trade_events` الدائم — لا جدول جديد ولا هجرة
# مخطّط ولا مخزنٌ ثالث يُصان. والسقف يحدّ الذاكرة: ٤٥٢ حدثًا في ستّ عشرة
# ساعة ⇒ عشرون ألفًا تكفي أسابيع، و`dict` يحفظ ترتيب الإدراج فيسقط الأقدم.
TICKET_MAP_MAX = 20000


def _rebased_config(raw_cfg: dict) -> dict:
    """config المانيفست على يد مالك المسارات — نسبةً لجذر الـruntime.

    الذرّة لا تعرف أين شُغِّلت: قراءة القيمة النسبية من المانيفست نسبةً إلى
    مجلد التشغيل كانت تُنشئ شجرة ``var/store`` موازية تحت جذر المشروع لا
    يقرأها أحد. لذلك تُحلَّ القيمة عند مالك المسارات: يُتقدَّم جذرُ تشغيل
    صالح (فيه ``shared/runtime_paths.py`` — نسخة الـruntime أو الجذر العام)،
    ثم تُمرَّر config إليه. المسار المطلق (``C:\\…`` في جسر المنصّة) يمرّ
    حرفيًّا — إعادة صياغته قرار نشر لا تصحيح مسار. وتعذُّر الحلّ يرجع
    config كما هي: لا يُعطَّل إقلاع ذرّة بأزمة مسار.
    """
    here = Path(__file__).resolve()
    code_root = None
    for parent in here.parents:
        if (parent / "shared" / "runtime_paths.py").is_file():
            code_root = parent
            break
    if code_root is None:
        return raw_cfg
    # ٢٠٢٦-٠٩-٢٣ — رُفع حقنُ `sys.path` من هنا: وزنٌ ميّت لا حماية.
    # `scripts/run_forex.py:9-11` ثمّ `governance/scripts/run_core.py:19-22`
    # يضعان جذرَ المشروع في رأس المسار عند كلّ إقلاع، وهو بعينه
    # `code_root` أدناه — فالشرطُ لا يتحقّق أبدًا. ونصُّ النواة صريح
    # (`core/bootloader.py:252`): لا حاجة لأن تحقن الذرّة المسارَ بنفسها.
    try:
        from shared.runtime_paths import manifest_config_rebase
        return manifest_config_rebase(raw_cfg, code_root=code_root)
    except Exception:  # noqa: BLE001 — لا يُعطَّل الإقلاع بأزمة مسار
        return raw_cfg


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context = None; self._running = False
        self._brokers: dict[str, str] = {}
        self._specs: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._pending_specs: list[dict[str, Any]] = []
        self._journal: Journal | None = None
        self._journal_ready = False; self._last_error = ""
        self._seen = 0
        self._opened = 0
        self._realized = 0
        self._dropped = 0
        self._duplicates = 0
        self._missing_identity = 0
        self._measured = 0
        self._unmatched = 0
        self._outbox_recovered = 0
        self._identity_incomplete = 0
        self._cards: Any = None
        self._card_writes = 0
        self._card_missing = 0
        self._card_error = ""
        self._ticket_map: dict[str, tuple[str, str]] = {}
        self._ticket_loaded = 0
        self._ticket_bridged = 0
        self._identity_by_alias = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        # المانيفست يحمل var\store\… ويندوزيًا؛ على لينكس لا شيء يُستبدَل،
        # وعلى ويندوز الفصل هو os.sep فتُقرأ القيمة كما كُتبت في المانيفست.
        cfg = _rebased_config({k: (str(v).replace(os.sep, "/") if isinstance(v, str) else v)
                               for k, v in context.config.items()})
        self._journal = Journal(str(cfg.get(
            "dedupe_db_path", "var/store/execution_confirmation.db")))
        # البطاقة تُفتح بنفس `cfg` المُلصق أعلاه — لا نداءَ إلصاقٍ ثانٍ ولا
        # مسارٌ نسبيّ يُفتح تحت مجلّد التشغيل. ومسارٌ فارغ = لا كتابة.
        card_path = str(cfg.get("card_db_path") or "").strip()
        if card_path:
            try:
                from shared.trade_card import CardStore
                store = CardStore(card_path)
                store.ensure()
                self._cards = store
            except Exception as exc:  # noqa: BLE001 — سجلٌّ لا بوّابة
                self._card_error = type(exc).__name__
        try:
            await asyncio.to_thread(self._journal.ensure); self._journal_ready = True
        except (OSError, sqlite3.Error) as exc:
            self._last_error = str(exc); self._journal_ready = False
        context.subscribe(EVENT_IN, self._on_event)
        context.subscribe(EVENT_FINAL, self._on_requested)
        context.subscribe(EVENT_SPECS, self._on_specs)
        context.subscribe(EVENT_ACCOUNT, self._on_account)

    async def start(self) -> None:
        self._running = True
        if self._journal_ready:
            try:
                self._ticket_loaded = await asyncio.to_thread(self._load_ticket_map)
            except (OSError, sqlite3.Error) as exc:
                # خريطة فارغة تعني هويّةً ناقصة، لا نتيجةً ضائعة: التسليم
                # يمضي كما كان قبل هذا الجسر. فلا يُعطَّل إقلاعٌ لأجلها.
                self._last_error = str(exc)
            self._outbox_recovered = await self._drain_outbox()

    def _load_ticket_map(self) -> int:
        """`ticket ⇄ request_id` كما أعلنهما الوسيط في أحداث الفتح المخزَّنة.
        تُقرأ من القرص عند كل إقلاع فتنجو الخريطة من إعادة التشغيل."""
        if self._journal is None:
            return 0
        connection = self._journal.connect()
        try:
            rows = connection.execute(
                "SELECT account_id,payload_json FROM processed_trade_events "
                "WHERE event_type=? ORDER BY rowid DESC LIMIT ?",
                (EVT_OPENED, TICKET_MAP_MAX)).fetchall()
        finally:
            connection.close()
        loaded = 0
        for account, raw in reversed(rows):  # الأقدم أوّلًا: الأحدث يغلب
            try:
                body = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(body, dict):
                continue
            ticket = text(body.get("ticket")); request_id = text(body.get("request_id"))
            if ticket and request_id:
                self._ticket_map[ticket] = (text(account), request_id); loaded += 1
        return loaded

    def _remember_ticket(self, account: str, payload: dict[str, Any]) -> None:
        ticket = text(payload.get("ticket")); request_id = text(payload.get("request_id"))
        if not ticket or not request_id:
            return
        self._ticket_map.pop(ticket, None)  # إعادة الإدراج تُجدّد موضعه
        self._ticket_map[ticket] = (account, request_id)
        excess = len(self._ticket_map) - TICKET_MAP_MAX
        for key in list(self._ticket_map)[:excess] if excess > 0 else ():
            self._ticket_map.pop(key, None)

    async def stop(self) -> None: self._running = False
    async def shutdown(self) -> None: await self.stop()

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict): return
        account = text(payload.get("account_id")); broker = text(payload.get("broker"))
        if account and broker:
            self._brokers[account] = broker
            pending, self._pending_specs = self._pending_specs, []
            for item in pending: await self._on_specs(item)

    async def _on_specs(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict): return
        for row in payload.get("symbols", []) if isinstance(payload.get("symbols"), list) else []:
            if not isinstance(row, dict): continue
            key = row_key(payload, row, self._brokers)
            if key is not None:
                spec = dict(row)
                spec["point"] = number(row.get("point")) or number(row.get("tick_size"))
                spec["spec_digest"] = hashlib.sha256(json.dumps(
                    spec, sort_keys=True, default=str).encode()).hexdigest()
                self._specs[key] = spec
            elif text(row.get("account_id") or payload.get("account_id")) \
                    and payload not in self._pending_specs:
                self._pending_specs.append(dict(payload))

    async def _on_requested(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict) or not self._journal_ready:
            return
        account = text(payload.get("account_id")); broker = text(payload.get("broker")) \
            or self._brokers.get(account, "")
        request_id = text(payload.get("request_id")); symbol = text(payload.get("symbol"))
        requested = number(payload.get("reference_price"))
        if not account or not broker or not request_id or not symbol or requested is None:
            return
        spec = self._specs.get((account, broker, symbol), {})
        row = {"account_id": account, "request_id": request_id, "broker": broker,
               "symbol": symbol, "side": text(payload.get("side")).upper(),
               "requested_price": requested, "point": number(spec.get("point")),
               "tick_value": number(spec.get("tick_value")),
               "tick_size": number(spec.get("tick_size")),
               "spec_digest": spec.get("spec_digest"), "payload": dict(payload)}
        try:
            await asyncio.to_thread(self._journal.remember_request, row)
        except (OSError, sqlite3.Error) as exc:
            self._journal_ready = False; self._last_error = str(exc)

    async def _publish_rejection(self, payload: dict[str, Any], reason: str) -> None:
        self._dropped += 1
        if self._context is not None:
            await self._context.publish(EVENT_REJECTED, {**payload, "reason": reason})

    async def _on_event(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict): return
        if not self._journal_ready or self._journal is None:
            await self._publish_rejection(payload, "DURABLE_DEDUPE_UNAVAILABLE"); return
        event_type = text(payload.get("event_type")).upper()
        if event_type not in {EVT_OPENED, EVT_CLOSED, EVT_PARTIAL}: return
        account = text(payload.get("account_id")); broker = text(payload.get("broker")) \
            or self._brokers.get(account, "")
        source_identity = text(payload.get("source_row_id") or payload.get("event_id")
                               or payload.get("deal_id"))
        if not account or not broker or not source_identity:
            self._missing_identity += 1
            await self._publish_rejection(payload, "MISSING_DURABLE_EVENT_ID_OR_SCOPE"); return
        identity = "|".join((account, broker, event_type, source_identity))
        if event_type in {EVT_CLOSED, EVT_PARTIAL}:
            revision = {name: payload.get(name) for name in
                        ("profit", "commission", "swap", "fee", "trade_id", "request_id")}
            revision_id = hashlib.sha256(json.dumps(
                revision, sort_keys=True, default=str).encode()).hexdigest()[:24]
            identity += "|" + revision_id
        outputs = await self._outputs(identity, event_type, account, broker, payload)
        try:
            inserted = await asyncio.to_thread(
                self._journal.commit_event, identity, account, event_type,
                source_identity, payload, outputs)
        except (OSError, sqlite3.Error) as exc:
            self._journal_ready = False; self._last_error = str(exc)
            await self._publish_rejection(payload, "DURABLE_DEDUPE_UNAVAILABLE"); return
        if not inserted:
            self._duplicates += 1; self._dropped += 1; return
        self._seen += 1
        if event_type == EVT_OPENED: self._opened += 1
        else: self._realized += 1
        await self._drain_outbox()

    def _decision_identity(self, requested: dict[str, Any] | None,
                           payload: dict[str, Any]) -> dict[str, Any]:
        return execution_confirm_identity.decision_identity(self, requested, payload)

    async def _outputs(self, identity: str, event_type: str, account: str, broker: str,
                       payload: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
        if self._journal is None: return []
        request_id = text(payload.get("request_id"))
        # مفتاحُ البحث وحده يُجسَّر؛ `request_id` المنشور يبقى كما أعلنه
        # الوسيط. وإلّا لتبدّل `trade_identity` أدناه — وهو يقع على
        # `request_id` قبل `ticket` — فتغيّرت هويّة الصفقة عند كل مستهلك.
        lookup_id = request_id
        if not lookup_id:
            mapped = self._ticket_map.get(text(payload.get("ticket")))
            # الحساب يُطابَق: تذكرةٌ من حسابٍ آخر ليست هذه الصفقة.
            if mapped is not None and mapped[0] == account:
                lookup_id = mapped[1]; self._ticket_bridged += 1
        requested = await asyncio.to_thread(self._journal.request, account, lookup_id) \
            if lookup_id else None
        if event_type == EVT_OPENED:
            self._remember_ticket(account, payload)
            slippage = self._slippage(requested, number(payload.get("entry_price")),
                                      number(payload.get("volume")))
            body = {"command_id": request_id or text(payload.get("ticket")),
                    "request_id": request_id, "status": "ACK", "account_id": account,
                    "broker": broker, "symbol": text(payload.get("symbol")),
                    "ticket": payload.get("ticket"), "side": text(payload.get("side")),
                    "volume": number(payload.get("volume")),
                    "entry_price": number(payload.get("entry_price")),
                    "pair_id": payload.get("pair_id"), "leg_role": payload.get("leg_role"),
                    **self._decision_identity(requested, payload), **slippage}
            return [("execution-confirm:" + identity + ":ack", EVENT_ACK, body)]
        profit = number(payload.get("profit")); symbol = text(payload.get("symbol"))
        if profit is None or not symbol:
            return [("execution-confirm:" + identity + ":rejected", EVENT_REJECTED,
                     {**payload, "account_id": account, "broker": broker,
                      "reason": "MISSING_REALIZED_PROFIT_OR_SYMBOL"})]
        result = "WIN" if profit > 0 else "LOSS" if profit < 0 else "BREAKEVEN"
        trade_identity = text(payload.get("trade_id") or payload.get("order_id") or
                              request_id or payload.get("ticket") or payload.get("source_row_id"))
        body = {"id": "execution_confirm", "symbol": symbol, "profit": round(profit, 2),
                "account_id": account, "broker": broker, "request_id": request_id,
                "trade_identity": trade_identity,
                "result": result, "side": text(payload.get("side")),
                "volume": number(payload.get("volume")),
                "entry_price": number(payload.get("entry_price")),
                "exit_price": number(payload.get("exit_price")),
                "event_type": event_type, "reason": text(payload.get("reason")),
                "ticket": payload.get("ticket"), "trade_id": payload.get("trade_id"),
                "source_row_id": payload.get("source_row_id"),
                "commission": number(payload.get("commission")),
                "swap": number(payload.get("swap")), "fee": number(payload.get("fee")),
                **self._decision_identity(requested, payload)}
        await self._write_card(symbol, event_type, payload, requested, profit, result)
        return [("execution-confirm:" + identity + ":outcome", EVENT_OUT, body)]

    async def _write_card(self, symbol: str, event_type: str, payload: dict[str, Any],
                          requested: dict[str, Any] | None, profit: float,
                          result: str) -> None:
        """نتيجةُ الصفقة على بطاقتها — بختم المالك ٢٠٢٦-٠٩-١٨.

        «ربحت خسرت انزلقت، كلّها بهل بطاقة. بالأخير أنا لما بدي أراجع
        صفقة بسحب بطاقتها».

        ورقمان يُقاسان هنا ولا يُقاسان في مكانٍ آخر:

          `entry_slip`     الدخول الفعليّ ناقص السعر الذي حُسب عليه الحجم.
                           مقيسٌ اليوم على بتكوين: متوسّط 7.88$ وأقصى 88.74$
                           بينما سقف الانزلاق في الإكسبرت 5.00$ — أي أنّ
                           مسافة الوقف بالدولار تكبر قبل أن تبدأ الصفقة.
          `stop_overshoot` كم تجاوز السعرُ الوقفَ عند الخروج. مقيسٌ على ٧٢
                           صفقةٍ لم يُعدَّل وقفُها: ٤٦ تجاوزت، والكلفة ٣٣٨$.

        وكلاهما كان يُستخرَج بتنقيبٍ بعد يوم؛ صارا سطرين في البطاقة.
        والكتابة لا تُفشل تسليمًا أبدًا: الصندوق الدائم هو الضامن،
        والبطاقة سجلٌّ يُقرأ.
        """
        store = self._cards
        if store is None or not symbol:
            return
        source = (requested or {}).get("payload")
        source = source if isinstance(source, dict) else {}
        fill = number(payload.get("entry_price"))
        exit_price = number(payload.get("exit_price"))
        reference = number((requested or {}).get("requested_price"))
        stop = number(source.get("stop_loss"))
        side = text(payload.get("side") or source.get("side")).upper()
        fields: dict[str, Any] = {
            "ticket": text(payload.get("ticket")) or None,
            "fill_price": fill, "exit_price": exit_price,
            "profit": round(profit, 2), "outcome": result}
        if fill is not None and reference is not None:
            # بالإشارة لا بالمطلق: الموجب ضدّنا في الشراء ولنا في البيع،
            # ومن يجرّده من إشارته يخسر الخبر كلّه.
            fields["entry_slip"] = round(
                (fill - reference) if side == SIDE_BUY else (reference - fill), 8)
        if (exit_price is not None and stop is not None
                and text(payload.get("reason")).upper() == "SL"):
            # موجبٌ = تجاوزَ الوقفَ إلى غير صالحنا. ويُقاس عند الوقف وحده:
            # خروجٌ بهدفٍ أو بيدٍ لا وقفَ يُقاس عليه.
            fields["stop_overshoot"] = round(
                (stop - exit_price) if side == SIDE_BUY else (exit_price - stop), 8)

        def _job() -> bool:
            card = store.live_card(symbol)
            if card is None:
                return False
            number_ = int(card["card_no"])
            store.update(number_, fields)
            moment = time.time()
            store.notes((number_, "563", name, value, moment)
                        for name, value in fields.items())
            return True

        try:
            if await asyncio.to_thread(_job):
                self._card_writes += 1
            else:
                self._card_missing += 1
        except Exception as exc:  # noqa: BLE001
            self._card_error = type(exc).__name__

    def _slippage(self, requested: dict[str, Any] | None, filled: float | None,
                  volume: float | None) -> dict[str, Any]:
        return execution_confirm_slippage.slippage(self, requested, filled, volume)

    async def _drain_outbox(self) -> int:
        if self._journal is None or self._context is None: return 0
        emitted = 0
        while True:
            try:
                rows = await asyncio.to_thread(self._journal.pending_outputs)
            except (OSError, sqlite3.Error) as exc:
                self._journal_ready = False; self._last_error = str(exc); return emitted
            if not rows: return emitted
            for output_id, event_name, payload in rows:
                await self._context.publish(event_name, payload)
                await asyncio.to_thread(self._journal.mark_emitted, output_id)
                emitted += 1

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "journal_path": self._journal.path if self._journal else None,
                "seen": self._seen, "opened": self._opened, "realized": self._realized,
                "duplicates": self._duplicates}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict): raise ValueError("INVALID_EXECUTION_CONFIRM_STATE")
        try:
            new_seen = int(state.get("seen") or 0)
            new_opened = int(state.get("opened") or 0)
            new_realized = int(state.get("realized") or 0)
            new_duplicates = int(state.get("duplicates") or 0)
        except (TypeError, ValueError):
            raise ValueError("INVALID_EXECUTION_CONFIRM_STATE")
        self._seen = new_seen; self._opened = new_opened
        self._realized = new_realized; self._duplicates = new_duplicates

    async def health_check(self) -> HealthStatus:
        if not self._running: return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        journal_counts = {}
        if self._journal_ready and self._journal is not None:
            try: journal_counts = await asyncio.to_thread(self._journal.counts)
            except (OSError, sqlite3.Error) as exc:
                self._journal_ready = False; self._last_error = str(exc)
        details = {"seen": self._seen, "opened": self._opened, "realized": self._realized,
                   "dropped": self._dropped, "duplicates": self._duplicates,
                   "missing_identity": self._missing_identity, "slippage_measured": self._measured,
                   "slippage_unmatched": self._unmatched, "journal_ready": self._journal_ready,
                   "journal": journal_counts, "outbox_recovered": self._outbox_recovered,
                   "identity_incomplete": self._identity_incomplete,
                   "ticket_map": len(self._ticket_map), "ticket_loaded": self._ticket_loaded,
                   "ticket_bridged": self._ticket_bridged,
                   "identity_by_alias": self._identity_by_alias,
                   "last_error": self._last_error}
        # ٢٠٢٦-٠٩-١٨ — حالة الهويّة تُقال في كل رسالة لا في `details` وحدها:
        # الذرّة أعلنت نفسها صحّيّةً بينما ٢٤٢ نتيجةً خرجت بلا هويّة قرار،
        # لأنّ `identity_incomplete` لا يدخل أيّ شرطِ تدهور ولا أيّ رسالة.
        identity = ""
        if self._identity_incomplete:
            identity += " بلا هويّة قرار=%d" % self._identity_incomplete
        if self._ticket_bridged:
            identity += " جُسِر بالتذكرة=%d" % self._ticket_bridged
        if self._identity_by_alias:
            identity += " باسمٍ ثانٍ=%d" % self._identity_by_alias
        if self._card_writes or self._card_missing or self._card_error:
            identity += " | بطاقة: كُتبت=%d بلا بطاقة=%d%s" % (
                self._card_writes, self._card_missing,
                (" ⚠ %s" % self._card_error) if self._card_error else "")
        elif self._cards is None:
            identity += " | بطاقة: معطّلة"
        if not self._journal_ready:
            return HealthStatus(state=HealthState.UNHEALTHY,
                                message="DURABLE_DEDUPE_UNAVAILABLE", details=details)
        if self._missing_identity or self._unmatched or journal_counts.get("outbox_pending"):
            return HealthStatus(
                state=HealthState.DEGRADED,
                message="CONFIRMATION_INCOMPLETE | بلا حساب=%d · انزلاقٌ بلا طلب=%d"
                        " · صندوقٌ معلَّق=%d%s" % (
                            self._missing_identity, self._unmatched,
                            journal_counts.get("outbox_pending") or 0, identity),
                details=details)
        if not self._seen:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_AWAITING_FIRST_PLATFORM_TRADE_EVENT | processed=0 duplicates=0",
                                details=details)
        return HealthStatus(state=HealthState.HEALTHY,
                            # ٢٠٢٦-٠٩-١٦ (فحص شامل ٤٥٠–٥٩٩): `last_error` و`dropped`
            # و`missing_identity` في `details` وحدها والنواة تحذفها — وهذه
            # ذرّة تأكيد التنفيذ: تأكيدٌ يسقط بلا هويّة يعني صفقةً نُفِّذت
            # ولا يُعرف قرارُها، والشارة تقول `processed=N`.
            message="processed=%d duplicates=%d%s%s%s%s" % (
                self._seen, self._duplicates,
                " ⚠ %s" % self._last_error if self._last_error else "",
                " مُهمَل=%d" % self._dropped if self._dropped else "",
                " بلا حساب=%d" % self._missing_identity if self._missing_identity else "",
                identity),
                            details=details)
