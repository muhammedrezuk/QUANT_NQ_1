from __future__ import annotations

from pathlib import Path

import time
from collections import deque
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.durable_execution_journal import Journal
from durable_ledger_consumer import (consume_trade, flush_outbox as flush_consumer_outbox,
                                     initialize_consumer, merge_projection,
                                     persist_budget)
from ledger_persistence import snapshot as save_ledger, restore as restore_ledger
from ledger_support import (
    POS_SEP, SEP, make_state, normalize_position, num, parts,
    position_scope, scope, text,
)
# ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا ولا بصير يقيس عليها … ولا يحسبها»):
# دفتر الأصل كان يجمع عائم مراكز المالك وتعرّضها في ميزانيّة الأصل (`floating_economic` · `loss_exposure` · `u` · `breached`)
# — فصفقةٌ يدويّة تستهلك ميزانيّة المنظومة على رمزها وقد تجمّده. الآن تُسقط مراكز المالك عند دخولها، بالتمييز الواحد في
# `shared/owner_trades.py`. والمحقَّق كان للمنظومة وحدها من مصدره (الخبير لا يكتب إغلاقًا إلّا لسحرها).
from shared import owner_trades

ATOM_VERSION = "4.6.0"

# v4.5.3 (٢٠٢٦-٠٩-٢٤، ختم المالك «Nq»): **للحجز عمر** — توأمُ 516 v5.9.3. الحجز
# هنا يدخل `u` (`effective = loss_exposure + reserved`)، ولا يُفكّ إلّا بحدث
# الردّ أو حدث الصفقة بالهويّة نفسها؛ فعلقت 7 حجوزات ذهب (700$ على 740$ ⇒
# u=0.946 على حافّة التجميد) بلا صفقةٍ وراءها. الآن حجزٌ تجاوز
# `reservation_ttl_s` (المانيفست) يُفكّ عند أوّل نشرٍ للدفتر، ويُسجَّل ويُعدّ.

# v4.5.2 (٢٠٢٦-٠٩-٢٤، ختم المالك «صلحnq»): **التصفير صار دائمًا.** كان
# `_on_ledger_reset` يمحو الدفاتر من الذاكرة وحدها، و`reduce_consumer_event`
# يقرأ الحالة المخزّنة ويتجاهل الابتدائيّة — فعادت الخسارة القديمة مع أوّل
# صفقة، ويعيدها كلّ إقلاع. مقيس: صُفّر الذهب والبتكوين ١٢:١٧ فعادا في لقطة
# ١٢:٣٢ (−2631.47$ و−5804.41$ إجماليًّا) مجمّدَين. الآن يمرّ التصفير نفسه
# بالمخزن الدائم بهويّةٍ لا تتكرّر، ويبقى صفُّه في `processed_trade_events`
# أثرًا لا يُمحى.
#: ⛔ نصًّا لا استيرادًا: الوحدة الشقيقة لا تُنشَر حيًّا، واستيرادُ اسمٍ لم
#:    يكن فيها يقتل الترقية الحارّة. مطابقٌ لـ`durable_ledger_consumer.CONSUMER`.
_LEDGER_CONSUMER = "518"

# سقفُ نافذة إزالة التكرار — حدُّ ذاكرةٍ لا قيمةَ تداول. مقيسٌ على أعلى
# معدّل ورودٍ في القسم (٥٥٢ يستقبل سبع عشرة لقطة في الثانية): ثمانية آلاف
# تغطّي نحو ثماني دقائق من أشدّ تدفّقٍ رُصد، وهي أضعافُ ما يلزم لكشف
# تكرارٍ يقع في نفس الدورة.
_MAX_SEEN = 8192
# v4.2.0 (2026-08-27, item 18/27 of the 27-atom review -- "silent restore
# on corruption + a fake test file"): ledger_persistence.restore() raised
# nothing on a non-dict state (self silently kept its empty __init__
# defaults for realized/extracted/budgets -- financial state that gates
# real extraction decisions). Now raises, and every field is parsed into
# a local before any commit to self, so a future failure point can't tear
# the books. tests/test_risk_scope.py was a single comment line with no
# actual test -- now verifies its own claim (dollar budget, no percent
# conversion) for real; tests/test_atom.py's inline scenario is now a
# proper pytest-discoverable function (was invisible to `pytest`/the
# official governance/scripts/test_atoms.py runner -- collectible only
# via direct script execution).
# v4.1.0 (2026-08-25): budgets are durable (see durable_ledger_consumer
# BUDGET_CONSUMER) -- an owner budget written through 901 now survives any
# restart exactly like realized profit does.
EVENT_POSITIONS = "platform.positions.state"
EVENT_ACTIVATE = "perpetual.asset.activate"
EVENT_TRADES = "risk.loss_reported"
EVENT_TRADE_EVENTS = "platform.trade_event"
EVENT_ACCOUNT = "platform.account.state"
EVENT_ORDER = "execution.order.built"
EVENT_REJECTED = "execution.order.rejected"
EVENT_SPECS = "market.symbol_specs"
EVENT_SPECS_CTRADER = "market.ctrader.symbol_specs"
EVENT_BUDGET = "risk.asset_budget.state"
EVENT_EXTRACT = "risk.asset_profit.extracted"
EVENT_LEDGER_RESET = "risk.asset_ledger.reset_requested"
EVENT_EXTRACT_PENDING = "asset.extraction.execution_requested"
EVENT_OUT = "risk.asset_ledger.state"
MAX_SEEN = 10000
WARNING_RATIO = 0.95


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
        self._context: AtomContext | None = None
        self._running = False
        self._default_budget = 0.0
        self._brokers: dict[str, str] = {}
        self._pending_specs: list[dict[str, Any]] = []
        self._count_realized = True
        self._max_seen = MAX_SEEN
        self._positions: dict[str, dict[str, Any]] = {}
        self._specs: dict[str, dict[str, Any]] = {}
        self._realized: dict[str, float] = {}
        self._realized_gross: dict[str, float] = {}
        self._realized_costs: dict[str, float] = {}
        self._extracted: dict[str, float] = {}
        self._budgets: dict[str, float] = {}
        self._known: set[str] = set()
        self._last_snapshot: dict[str, float] = {}
        self._seen_ids: set[str] = set()
        self._seen_order: deque[str] = deque()
        self._journal: Journal | None = None
        self._storage_error = ""
        self._duplicates = 0
        self._missing_event_ids = 0
        self._ledger_resets = 0
        self._ledger_reset_not_durable = 0
        self._reservation_ttl_s: float | None = None
        self._reservation_born: dict[tuple[str, str], float] = {}
        self._reservations_expired = 0
        self._extraction_tickets: dict[str, str] = {}
        self._reservations: dict[tuple[str, str], dict[str, Any]] = {}
        self._positions_seen = 0
        self._trades_seen = 0
        self._published = 0
        self._stale = 0
        self._missing_specs = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = _rebased_config(context.config)
        self._default_budget = num(cfg.get("default_risk_budget")) or 0.0
        self._count_realized = bool(cfg.get("count_realized", True))
        self._max_seen = max(1, int(cfg.get("max_seen_trades", MAX_SEEN)))
        ttl = num(cfg.get("reservation_ttl_s"))
        self._reservation_ttl_s = ttl if ttl is not None and ttl > 0 else None
        initialize_consumer(self, cfg)
        context.subscribe(EVENT_POSITIONS, self._on_positions)
        context.subscribe(EVENT_ACTIVATE, self._on_activate)
        context.subscribe(EVENT_TRADES, self._on_trade)
        context.subscribe(EVENT_TRADE_EVENTS, self._on_trade_event)
        context.subscribe(EVENT_ACCOUNT, self._on_account)
        context.subscribe(EVENT_ORDER, self._on_order)
        context.subscribe(EVENT_REJECTED, self._on_release)
        context.subscribe(EVENT_SPECS, self._on_specs)
        context.subscribe(EVENT_SPECS_CTRADER, self._on_specs)
        context.subscribe(EVENT_BUDGET, self._on_budget)
        context.subscribe(EVENT_LEDGER_RESET, self._on_ledger_reset)
        context.subscribe(EVENT_EXTRACT, self._on_extract)
        context.subscribe(EVENT_EXTRACT_PENDING, self._on_extraction_pending)

    async def start(self) -> None:
        self._running = True
        await self._flush_outbox()

    async def _flush_outbox(self) -> None:
        await flush_consumer_outbox(self)

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict): return
        account = text(payload.get("account_id")); broker = text(payload.get("broker"))
        if account and broker:
            self._brokers[account] = broker
            pending, self._pending_specs = self._pending_specs, []
            for item in pending: await self._on_specs(item)

    def _owner(self, payload: dict[str, Any], row: dict[str, Any] | None = None) -> tuple[str, str] | None:
        row = row or payload
        account = text(row.get("account_id"), text(payload.get("account_id")))
        broker = text(row.get("broker"), text(payload.get("broker"))) or self._brokers.get(account, "")
        return (account, broker) if account and broker else None

    async def _on_positions(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        rows = payload.get("positions")
        rows = rows if isinstance(rows, list) else []
        source = text(payload.get("source"), "positions")
        account_default = text(payload.get("account_id"))
        broker_default = text(payload.get("broker")) or self._brokers.get(account_default, "")
        if not account_default and not rows: return
        grouped: dict[str, list[dict[str, Any]]] = {}
        for raw in owner_trades.system_rows(rows):   # ٢٠٢٦-١٠-٢٦: مراكز المالك لا تدخل دفتر الأصل
            if isinstance(raw, dict):
                owner = self._owner(payload, raw)
                if owner is None: continue
                position = normalize_position(raw, owner[0], owner[1], source)
                if position is not None:
                    grouped.setdefault(position["source_scope"], []).append(position)
        if not grouped and account_default and broker_default:
            grouped[position_scope(source, account_default, broker_default)] = []
        stamp = num(payload.get("timestamp")) or num(payload.get("read_at"))
        affected: set[str] = set()
        existing_scopes = {str(p.get("source_scope")) for p in self._positions.values()
                           if str(p.get("source_scope") or "").startswith(source + SEP)}
        if payload.get("complete") is True or source in ("609", "broker"):
            for missing_scope in existing_scopes - set(grouped):
                grouped[missing_scope] = []
        for source_scope, fresh in grouped.items():
            old_stamp = self._last_snapshot.get(source_scope)
            if stamp is not None and old_stamp is not None and stamp <= old_stamp:
                self._stale += 1
                continue
            old_ids = [k for k, p in self._positions.items() if p.get("source_scope") == source_scope]
            for old_id in old_ids:
                old = self._positions.pop(old_id)
                affected.add(scope(old["account_id"], old["symbol"], old.get("broker")))
            for position in fresh:
                key = f"{source_scope}{POS_SEP}{position['ticket']}"
                self._positions[key] = position
                asset = scope(position["account_id"], position["symbol"], position.get("broker"))
                self._known.add(asset)
                affected.add(asset)
                self._positions_seen += 1
            if stamp is not None:
                self._last_snapshot[source_scope] = stamp
        if affected:
            await self._publish_all()
        elif payload.get("complete") is True or source in ("609", "broker"):
            # ٢٠٢٦-٠٩-٠٦ (مقيس — حلقة مفرغة أوقفت التداول كلّيًّا):
            # `affected` لا تمتلئ إلا بمركز قديم أو جديد. وعلى حساب فارغ
            # تمامًا لا يوجد أيّ منهما، فلا يُنشر الدفتر أبدًا — فتبقى
            # 519 على NO_LEDGER_YET، ويخرج محرّك الفرق بـ
            # PORTFOLIO_STATE_MISSING (581 targets=0 · 551 built=0).
            # أي أن الدفتر ينتظر أوّل مركز، والمركز ينتظر الدفتر.
            # لقطة مراكز كاملة لحساب معروف — ولو خالية — حالةٌ صالحة
            # تعني «الميزانية كاملة ولا تعرّض»، فتُنشر كما تُنشر أيّ حالة.
            await self._publish_all()

    async def _on_specs(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        rows = payload.get("symbols")
        if isinstance(rows, dict): rows = [rows]
        if not isinstance(rows, list): rows = [payload] if payload.get("symbol") else []
        affected = False
        for raw in rows:
            if not isinstance(raw, dict): continue
            symbol = text(raw.get("asset_canonical"), text(raw.get("symbol")))
            tick_size = num(raw.get("tick_size")); tick_value = num(raw.get("tick_value"))
            if not symbol or tick_size is None or tick_value is None or tick_size <= 0 or tick_value <= 0:
                continue
            owner = self._owner(payload, raw)
            if owner is None:
                if text(raw.get("account_id") or payload.get("account_id")) and payload not in self._pending_specs: self._pending_specs.append(dict(payload))
                continue
            account, broker = owner
            asset = scope(account, symbol, broker)
            self._specs[asset] = {"symbol": symbol, "tick_size": tick_size,
                                  "tick_value": tick_value}
            # ٢٠٢٦-٠٩-٠٦ (مقيس — الحلقة الثانية التي أوقفت التداول):
            # `_known` كانت تمتلئ من المراكز وحدها، فعلى حساب فارغ تبقى
            # خالية ⇒ ledgers=[] ⇒ 523 محرّك العيار dials=0 (رغم
            # emits=369) ⇒ stop_distance_frac مفقود في محرّك الفرق ⇒
            # كل قرار يخرج NO_DIRECTION (dir=wait في 231 من 231).
            # أي: الأصل لا يُعرف إلا بمركز، والمركز لا يُفتح بلا عيار،
            # والعيار لا يُحسب بلا أصل معروف. رمزٌ له مواصفة عند الوسيط
            # أصلٌ معروف — يستحق دفترًا ولو خاليًا من المراكز.
            self._known.add(asset)
            affected = True
        if affected:
            await self._publish_all()

    async def _on_activate(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        owner = self._owner(payload)
        if owner is None: return
        account, broker = owner
        symbol = text(payload.get("asset_canonical"), text(payload.get("symbol")))
        budget = num(payload.get("budget", payload.get("risk_budget", self._default_budget)))
        if not symbol or budget is None or budget <= 0:
            return
        key = scope(account, symbol, broker)
        self._budgets[key] = budget
        self._known.add(key)
        persist_budget(self, text(payload.get("event_id")), account, key, budget)
        await self._publish_all()

    async def _on_budget(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict): return
        owner = self._owner(payload)
        if owner is None: return
        account, broker = owner
        symbol = text(payload.get("asset_canonical"), text(payload.get("symbol")))
        budget = num(payload.get("risk_budget"))
        if not symbol or budget is None or budget < 0: return
        key = scope(account, symbol, broker); self._budgets[key] = budget; self._known.add(key)
        persist_budget(self, text(payload.get("event_id")), account, key, budget)
        await self._publish_all()

    def _remember(self, key: str) -> bool:
        """نافذةُ إزالة تكرارٍ محدودة — لا سجلٌّ أبديّ.

        ٢٠٢٦-٠٩-١٨: كانت المجموعة والطابور يُملآن ولا يُقلَّمان أبدًا، و
        `deque` بلا `maxlen` — أي نموٌّ بلا سقف ما دامت المنصّة تعمل. وهذه
        الذرّة تستقبل ثلاثة عشر حدثًا، ومفتاحُها `event_id` فريدٌ لكلٍّ.
        والغرضُ منع معالجة الحدث مرّتين، وذلك لا يحتاج ذاكرةً أبديّة: ما
        يعبر النافذة لن يعود.
        """
        if key in self._seen_ids: return False
        self._seen_ids.add(key); self._seen_order.append(key)
        while len(self._seen_order) > _MAX_SEEN:
            self._seen_ids.discard(self._seen_order.popleft())
        return True

    async def _on_trade(self, payload: dict[str, Any]) -> None:
        await consume_trade(self, payload)

    async def _on_extraction_pending(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        ticket = text(payload.get("ticket"))
        extraction_id = text(payload.get("extraction_id"), text(payload.get("request_id")))
        account = text(payload.get("account_id"))
        if account and ticket and extraction_id:
            self._extraction_tickets[account + SEP + ticket] = extraction_id

    async def _on_ledger_reset(self, payload: dict[str, Any]) -> None:
        """يبدأ دفترًا جديدًا لأصل بأمر صريح من المالك.

        الخسارة المحقّقة تراكمية ولا يزيلها شيء، فتبقى `u` فوق الواحد ويبقى
        الأصل مجمّدًا عبر ٥١٩ مهما رُفعت الميزانية دون مبلغها.  مقيس
        ٢٠٢٦-٠٩-١٠: BTCUSD خسارة ٦١١٫٩٣$ مقابل ميزانية ٥٠٠$ ⇒ u=1.22 ⇒ FROZEN.

        لا تصفير شامل: الحساب والرمز شرطان صريحان.  والممحوّ يُسجَّل في
        السجلّ الحيّ وفي عدّاد معلن — محو الحقيقة المحاسبيّة يترك أثرًا.
        """
        if not self._running or not isinstance(payload, dict): return
        owner = self._owner(payload)
        if owner is None: return
        account, broker = owner
        symbol = text(payload.get("asset_canonical"), text(payload.get("symbol")))
        if not symbol: return
        key = scope(account, symbol, broker)
        before = self._realized.get(key, 0.0)
        durable = self._persist_ledger_reset(payload, account, key)
        for book in (self._realized, self._realized_gross, self._realized_costs, self._extracted):
            book.pop(key, None)
        self._ledger_resets += 1
        self._known.add(key)
        if self._context is not None:
            self._context.logger.warning(
                "518 LEDGER_RESET scope=%s realized_before=%r reason=%r durable=%s",
                key, before, text(payload.get("reason")) or "OWNER_RESET", durable)
        await self._publish_all()

    def _persist_ledger_reset(self, payload: dict[str, Any], account: str, key: str) -> str:
        """يكتب التصفير في المخزن الدائم نفسه الذي تُجمع فيه الصفقات.

        بهويّة `ledger-reset:<رقم الأمر>:<النطاق>`، فالأمر المكرَّر لا يصفّر مرّتين،
        والمخزن يحفظ صفّه أثرًا. وإن تعذّرت الكتابة يبقى محوُ الذاكرة كما كان،
        ويُعدّ «غير دائم» في الشارة، فلا يُقرأ تصفيرٌ لم يثبت على أنه ثابت.
        """
        if self._journal is None or self._storage_error:
            self._ledger_reset_not_durable += 1
            return "NO_JOURNAL"
        command = text(payload.get("command_id")) or text(payload.get("event_id"))
        reset_id = "ledger-reset:%s:%s" % (command or repr(time.time()), key)

        def reduce(state: dict[str, Any]):
            return {"realized": 0.0, "gross": 0.0, "costs": 0.0}, []

        try:
            fresh, _ = self._journal.reduce_consumer_event(
                reset_id, account, "LEDGER_RESET", reset_id,
                {"scope": key, "command_id": command,
                 "reason": text(payload.get("reason")) or "OWNER_RESET",
                 "operator": text(payload.get("operator"))},
                _LEDGER_CONSUMER, key, {}, reduce)
        except Exception as exc:  # noqa: BLE001 — المخزن معطوب: يُقال ولا يُخفى
            self._storage_error = type(exc).__name__
            self._ledger_reset_not_durable += 1
            return "FAILED:" + type(exc).__name__
        return "DONE" if fresh else "DUPLICATE"

    async def _on_extract(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict): return
        owner = self._owner(payload)
        if owner is None: return
        account, broker = owner
        symbol = text(payload.get("asset_canonical"), text(payload.get("symbol")))
        amount = num(payload.get("amount"))
        if not symbol or amount is None or amount <= 0: return
        key = scope(account, symbol, broker)
        extraction_id = text(payload.get("extraction_id"), text(payload.get("request_id")))
        if extraction_id:
            self._extraction_tickets = {ticket: ident for ticket, ident in self._extraction_tickets.items()
                                        if ident != extraction_id}
        realized_net_total = self._realized.get(key, 0.0)
        available = max(0.0, realized_net_total - self._extracted.get(key, 0.0))
        self._extracted[key] = self._extracted.get(key, 0.0) + min(amount, available)
        self._known.add(key); await self._publish_all()

    async def _on_order(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict) or str(payload.get("action") or "OPEN").upper() != "OPEN": return
        owner = self._owner(payload); symbol = text(payload.get("symbol")); request = text(payload.get("request_id")); amount = num(payload.get("risk_budget"))
        if owner is None or not symbol or not request or amount is None or amount <= 0: return
        key = scope(owner[0], symbol, owner[1]); self._reservations[(owner[0], request)] = {"scope": key, "amount": amount}
        self._reservation_born[(owner[0], request)] = time.monotonic(); self._known.add(key); await self._publish_all()

    async def _on_release(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict): return
        account = text(payload.get("account_id")); request = text(payload.get("request_id"))
        self._reservation_born.pop((account, request), None)
        if account and request and self._reservations.pop((account, request), None) is not None: await self._publish_all()

    def _expire_reservations(self) -> None:
        """يفكّ الحجز الذي تجاوز عمره — والمستعادُ من اللقطة يبدأ عمرَه من أوّل فحص."""
        if not self._reservations or not self._reservation_ttl_s:
            return
        now = time.monotonic()
        stale = [k for k in list(self._reservations)
                 if now - self._reservation_born.setdefault(k, now) > self._reservation_ttl_s]
        for key in stale:
            gone = self._reservations.pop(key, None); self._reservation_born.pop(key, None)
            if gone is None:
                continue
            self._reservations_expired += 1
            if self._context is not None:
                self._context.logger.warning(
                    "518 حجزٌ عالق فُكّ آليًّا حساب=%s طلب=%s نطاق=%s مبلغ=%s بعد %.0fث",
                    key[0], key[1], str(gone.get("scope", "")).replace(SEP, "/"),
                    gone.get("amount"), self._reservation_ttl_s)

    async def _on_trade_event(self, payload: dict[str, Any]) -> None:
        await self._on_release(payload)

    def _ledger_payload(self, realized_book=None, gross_book=None, costs_book=None,
                        known=None) -> dict[str, Any]:
        realized_book = self._realized if realized_book is None else realized_book
        gross_book = self._realized_gross if gross_book is None else gross_book
        costs_book = self._realized_costs if costs_book is None else costs_book
        known = self._known if known is None else known
        ledgers = []; missing_total = 0
        for key in sorted(known):
            state, missing = make_state(key, self._positions, realized_book, self._extracted,
                                        self._budgets, self._default_budget, self._specs,
                                        self._count_realized, realized_gross_book=gross_book,
                                        realized_costs_book=costs_book)
            reserved = sum(float(x["amount"]) for x in self._reservations.values() if x["scope"] == key)
            budget = float(state.get("risk_budget") or 0.0); base_exposure = float(state.get("loss_exposure") or 0.0)
            effective = base_exposure + reserved; state["reserved_risk"] = round(reserved, 8)
            state["effective_exposure"] = round(effective, 8)
            # ٢٠٢٦-٠٩-١٠: هذه الأسطر كانت **تدهس** ما حسبه `make_state` بحكم
            # المالك ٢٠٢٦-٠٨-١٣ (م١٣): «الخسارة المحقّقة تسافر في مسارها الخاصّ
            # إلى u».  فعاد العطل الذي عولج هناك بالحرف — مقيس ٢٠٢٦-٠٩-٠٩ على
            # BTCUSD: `u_realized=5.2985` (خسارة ٥٢٩٫٨٥$ مقابل ميزانية ١٠٠$)
            # بينما `u=0.0` و`breached=False` و`remaining_risk=100.0`، أي
            # «الميزانية لم تُمَسّ» فوق خسارة تعادل خمسة أضعافها.
            # الحجز يدخل الطافي، والمحقَّق يبقى مساره، و`u` أسوأ النسبتين.
            u_effective = effective / budget if budget > 0 else None
            realized_ratio = state.get("u_realized")
            realized_ratio = float(realized_ratio) if isinstance(realized_ratio, (int, float)) and not isinstance(realized_ratio, bool) else 0.0
            state["u_float"] = u_effective
            state["u"] = None if u_effective is None else max(u_effective, realized_ratio)
            # ولا «متبقٍّ» فوق ميزانية مخترقة: كان يطرح الطافي وحده فيعلن ١٠٠
            # متاحة بعد خسارة ٥٣٠.
            state["remaining_risk"] = round(max(0.0, budget * (1.0 - state["u"])), 8) if state["u"] is not None else None
            state["warning"] = state["u"] is not None and state["u"] >= WARNING_RATIO
            state["breached"] = state["u"] is not None and state["u"] >= 1.0
            missing_total += missing; ledgers.append(state)
        self._missing_specs = missing_total
        worst = max((state["u"] for state in ledgers if state.get("u") is not None), default=None)
        return {"ledgers": ledgers, "count": len(ledgers), "worst_u": worst}

    async def _publish_all(self) -> None:
        if self._context is None: return
        self._expire_reservations()
        await self._context.publish(EVENT_OUT, self._ledger_payload())
        self._published += 1

    def state(self, key: str) -> dict[str, Any]:
        return make_state(key, self._positions, self._realized, self._extracted,
                          self._budgets, self._default_budget, self._specs,
                          self._count_realized, realized_gross_book=self._realized_gross,
                          realized_costs_book=self._realized_costs)[0]

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        details = {"positions": self._positions_seen, "trades": self._trades_seen,
                   "published": self._published, "stale": self._stale,
                   "missing_specs": self._missing_specs, "duplicates": self._duplicates,
                   "missing_event_ids": self._missing_event_ids, "ledger_resets": self._ledger_resets,
                   "storage_error": self._storage_error}
        if self._storage_error:
            return HealthStatus(state=HealthState.UNHEALTHY,
                                message="DURABLE_CONSUMER_UNAVAILABLE", details=details)
        if not self._positions_seen and not self._trades_seen:
            return HealthStatus(state=HealthState.HEALTHY,
                                message="READY_LEDGER_EMPTY_AWAITING_FIRST_POSITION_OR_TRADE | positions=0 trades=0",
                                details=details)
        # ٢٠٢٦-٠٩-١٨ (ختم NQ) — أمر المالك: «أظهر كل ما هو مهمّ ومخفيّ».
        # كانت الرسالة كلمةً واحدة: `ledger_active`. وهذه الذرّة تحمل
        # ميزانيّة كل أصلٍ والمحقَّق منها، ومنها يقرأ ٥١٦ حدَّ المخاطرة —
        # فرقمُها هو ما يسمح بالصفقة أو يمنعها. وكلمةٌ واحدة لا تقول شيئًا.
        realized = sum(self._realized.values()) if self._realized else 0.0
        budgets = len(self._budgets)
        total_budget = sum(self._budgets.values()) if self._budgets else 0.0
        message = "مراكز=%d صفقات=%d نشر=%d | ميزانيّات=%d مجموعها=%.0f$ (افتراضيّ %.0f$) | محقَّق=%.2f$ · مستخرَج=%.2f$" % (
            self._positions_seen, self._trades_seen, self._published,
            budgets, total_budget, self._default_budget,
            realized, sum(self._extracted.values()) if self._extracted else 0.0)
        if self._duplicates:
            message += " · مكرَّر=%d" % self._duplicates
        if self._stale:
            message += " · بائت=%d" % self._stale
        if self._ledger_resets:
            message += " · تصفير=%d" % self._ledger_resets
        if self._ledger_reset_not_durable:
            message += " (غير دائم=%d)" % self._ledger_reset_not_durable
        if self._reservations:
            message += " · حجوزات=%d" % len(self._reservations)
        if self._reservations_expired:
            message += " (فُكّ_آليًّا=%d)" % self._reservations_expired
        message += " · نافذة_التكرار=%d/%d" % (len(self._seen_ids), _MAX_SEEN)
        if self._missing_specs:
            return HealthStatus(state=HealthState.DEGRADED,
                                message="MISSING_SPECS · " + message, details=details)
        return HealthStatus(state=HealthState.HEALTHY, message=message, details=details)

    async def snapshot(self) -> dict[str, Any]:
        state = save_ledger(self)
        state["version"] = ATOM_VERSION
        return state

    async def restore(self, state: dict[str, Any]) -> None:
        restore_ledger(self, state)
        merge_projection(self)
