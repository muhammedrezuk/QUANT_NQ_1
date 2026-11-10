from __future__ import annotations

import time
from collections import deque
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared.section_contract import section_atom
# ٢٠٢٦-١٠-٠١ (ختم المالك «Nq») — وحدتان شقيقتان نُقلت إليهما كتلٌ من هذا الملفّ **حرفيًّا**
# لحدّ الأربع مئة سطر فعليّ (م٩/ملف٤)، صفر تغيير سلوك: مطابقةُ النتيجة بقرارها وتسميتُها
# ونشرُ السجلّ (`learning_outcome_matching`) · والثوابتُ والمساعداتُ الصِّرفة التي تقرؤها
# الوحدتان معًا (`learning_outcome_common`). وتُستورد أسماؤها هنا كي يبقى سطحُ هذه الوحدة
# كما كان (`module.EVENT_OUT` · `module.FIELD_RECEIVED` …)، و`_on_outcome`/`_find_decision`
# بقيا بوّابتين رفيعتين فلم يتغيّر اشتراكٌ ولا نداء.
from learning_outcome_common import FIELD_RECEIVED, SEP, _OUTCOME_IDENTITY, _text, key, num
from learning_outcome_matching import EVENT_OUT, LABEL_POLICY_VERSION
import learning_outcome_matching

ATOM_VERSION = "1.8.1"
SNAPSHOT_VERSION = 1

# 2026-09-09: the model evidence 367 publishes reaches the decision chain ONLY
# on decision.evaluated.state (452 attaches it there).  453 does not forward it
# when it republishes as decision.scored.state, so every record this atom stored
# carried an empty dict -- measured: 0 of 299,464 pending decisions held one --
# and 362 rejected 100% of the samples, freezing 363-368 at zero.  Subscribing
# to the evaluated stage too is the fix that stays inside section 350-399.
EVENT_EVALUATED = "decision.evaluated.state"
EVENT_SCORED = "decision.scored.state"
EVENT_DECISION = "decision.resolved.state"
EVENT_FINAL = "trading.final_decision"
EVENT_OUTCOME = "market.outcome.realized"
EVENT_TICK = "market.tick.validated"
# v1.5.0 — الجسر: نتيجة الوسيط تصل بـ`ticket` وحده وحقولُ هويّتها فارغة.
# مقيس ٢٠٢٦-٠٩-١٨ من صندوق ٥٦٣: **١٣ من ١٣** نتيجة بـ`decision_id=None`
# و`request_id=""` ومعها `identity_missing` — أي أنّ ناشرها يعلن عجزه.
# و`execution.command.ack` يحمل **`ticket` و`decision_id` معًا في ٢١٠ من
# ٢١٠**، فالربط موجود على السلك ولم يكن أحد يلتقطه. تغطيته المقيسة على
# التاريخ المخزَّن: **١٦١ من ٢٤٢** نتيجة (٦٦٫٥٪) — و٣٦٣ يحتاج ٢٥ عيّنة.
EVENT_ACK = "execution.command.ack"
EVENT_MANAGE = "execution.manage.intent"
MAX_TICKETS = 5000

# Evaluated is the earliest and weakest stage: later stages may overwrite its
# scalars, but never its evidence (see _merge).
_SOURCE_RANK = {
    EVENT_EVALUATED: 1,
    EVENT_SCORED: 2,
    EVENT_DECISION: 3,
    EVENT_FINAL: 4,
}

# Evidence captured at decision time.  A later stage that arrives without it
# must not erase what an earlier stage already proved.
_EVIDENCE_FIELDS = ("model_evidence", "feature_snapshot", "features",
                    "strategy_evidence", "model_version", "model_direction")

#: مفتاحُ «هذا القرار صار أمرًا عند الوسيط» — يمنع طردَه بسقف العدد.
FIELD_PINNED = "_pinned"

DEFAULT_MAX_PENDING = 2000
DEFAULT_MAX_AGE_S = 21600

# عقد الدليل: ما يُحفَظ من `model_evidence` -- لا الظرف الذي يصل معه.
# مقيس ٢٠٢٦-٠٩-١٠: بعد أن صار الدليل يصل إلى ١٠٠٪ من السجلات، قفز حجم
# السجل من ٦٩٠ إلى ٢٬٣٣٧ بايت واللقطة من ١٣.٦ إلى ٣٣.٥٨ م.ب -- و`model_
# evidence` وحده ٨٥.٧٪ منها. وتفصيله يقول إنّ الثقل ليس الدليل: `unified`
# ٥٨٠ بايت (نسخة كاملة من التِكّة) + `trace_id`/`parent_event`/`event_id`
# وهي ظرف نقل تضيفه النواة، بينما المتّجه وعقده ٤١٤ بايت فقط.
# ومن يقرأ الحمولة؟ ٣٦١ ثمّ ٣٦٢ (يطلبان الأربعة الأولى) و٣٦٨ (يقرأ من
# مستوى السجل لا من الدليل) -- وهما وحدهما المشتركان، و`tests/
# test_learning_pipeline_end_to_end.py` يبني `model_evidence` بالأربعة
# الأولى حصرًا. فهذا هو العقد، والباقي بايتات تُسلسَل كل دورة بلا قارئ.
_EVIDENCE_KEEP = ("feature_vector", "feature_names", "feature_schema_version",
                  "feature_schema_hash", "model_version", "direction")

# طول نافذة الحكم الحيّ على المطابقة (نتائج، لا تِكّات).
MATCH_WINDOW = 20

# عدّادات الحالة: تُحفظ وتُستعاد بجدول واحد، فإضافة عدّاد سطرٌ هنا لا ثلاثة.
_COUNTERS = ("records", "decisions_seen", "evaluated_seen", "scored_seen",
             "resolved_seen", "final_seen", "unmatched", "unmatched_no_identity",
             "unmatched_not_found", "pruned_age", "pruned_cap", "bridged",
             "ack_seen", "manage_seen")

# ⚠️ ولماذا لا يُقاس البايت لكل إدخال رغم ما سبق: `json.dumps` على المسار
# الساخن يعيد الخنق الذي أزاله الفهرس. الحدّ العددي يكفي هنا لأنّ السجل
# **مغلق البنية** (لا قائمة تنمو داخله)، فالسقف الأعلى محسوب لا محتمَل.
# أمّا ذرّة يحمل سجلّها قائمة مفتوحة فالحدّ العددي عندها يكذب
# (٧١٢: `MAX_BUFFER_ROWS = 100000` ⇒ ١٫٢ ج.ب)، وهناك يلزم الحدّ بالبايت.
# (نقد جلسة «قسم ٢٠٠–٢٤٩» -- وقد صحّ عليّ جزئيًّا: تقديري للحجم بُني على
# متوسطٍ قِيس قبل أن يصل الدليل إلى كل السجلات، فبات في يوم واحد.)


def _identities(record: dict[str, Any]) -> set[str]:
    found = {_text(record.get("decision_id")), _text(record.get("request_id")),
             _text(record.get("cycle_id")), _text(record.get("gate_request_id"))}
    found.discard("")
    return found


@section_atom("350", "360")
class Atom(AtomBase):

    def __init__(self) -> None:
        self._context: AtomContext | None = None
        # 🕐 عمرُ هذه النسخة الحيّة — بطلب جلسة اللوحات ٢٠٢٦-٠٩-٢٢.
        #    العدّاد الصفريّ ذو معنيين: «لم يصلها شيء» أو «أُعيد
        #    بناؤها للتوّ بتحميلٍ حارّ». والشارةُ بلا عمرٍ تجعل
        #    القارئ يخمّن — وقد كتبت اللوحةُ إنذارًا كاذبًا بسببه.
        #    فالصفرُ مع عمرٍ ساعتين انقطاعٌ، ومع ثلاثين ثانية بناءٌ جديد.
        self._started_at = time.monotonic()
        self._running = False
        self._decisions: dict[str, list[dict[str, Any]]] = {}
        # scope -> identity -> the very record object held in _decisions[scope].
        # Rebuilt on restore; never snapshotted.  Without it every incoming
        # decision scanned the whole bucket -- 246,903 comparisons per tick on
        # BTCUSD alone (measured 2026-09-09).
        self._identity: dict[str, dict[str, dict[str, Any]]] = {}
        self._prices: dict[str, float] = {}
        self._max_pending = DEFAULT_MAX_PENDING
        self._max_age_s = DEFAULT_MAX_AGE_S
        self._records = 0
        self._decisions_seen = 0
        self._evaluated_seen = 0
        self._scored_seen = 0
        self._resolved_seen = 0
        self._final_seen = 0
        self._unmatched = 0
        self._unmatched_no_identity = 0
        self._unmatched_not_found = 0
        self._recent_match: deque[bool] = deque(maxlen=MATCH_WINDOW)
        # ticket الوسيط -> هويّة القرار، من `execution.command.ack`.
        self._ticket_identity: dict[str, dict[str, Any]] = {}
        self._bridged = 0
        # 🔴 ٢٠٢٦-٠٩-٢٢ — `bridged=0/70` كان مجهولَ السبب: أتذكرةٌ بلا
        #    `ack`، أم `ack` وُجد وقرارُه طُرد؟ صفرٌ بلا اسمٍ لا يُصلَح.
        self._bridge_no_ack = 0
        self._bridge_lost_decision = 0
        self._pinned = 0
        self._ack_seen = 0
        # ticket -> أقصى r_multiple بلغته الصفقة (من أحداث الإدارة).
        self._ticket_excursion: dict[str, float] = {}
        self._manage_seen = 0
        self._pruned_age = 0
        self._pruned_cap = 0

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config if isinstance(context.config, dict) else {}
        self._max_pending = max(1, int(cfg.get("max_pending_per_scope",
                                               DEFAULT_MAX_PENDING)))
        self._max_age_s = max(60, int(cfg.get("max_pending_age_s",
                                              DEFAULT_MAX_AGE_S)))
        # ٢٠٢٦-١٠-٠٧ (ختم «NQ»): لا اشتراك في المراحل الثلاث (evaluated/scored/resolved) — ناشروها أُرشفوا؛ معالجاتها باقية لأنّ الاختبارات تستدعيها، وتعود السلسلة حين تُبنى على بطاقات الصفقات.
        context.subscribe(EVENT_FINAL, self._on_final)
        context.subscribe(EVENT_OUTCOME, self._on_outcome)
        context.subscribe(EVENT_ACK, self._on_ack)
        context.subscribe(EVENT_MANAGE, self._on_manage)
        context.subscribe(EVENT_TICK, self._on_tick)

    async def start(self) -> None:
        self._running = True
        self._started_at = time.monotonic()

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    @staticmethod
    def _keep(store: dict[str, Any], ticket: str, value: Any) -> None:
        """خزنُ مفتاحٍ بسقفٍ ثابت -- الأقدم يخرج، فلا ينمو بلا حدّ."""
        if ticket not in store and len(store) >= MAX_TICKETS:
            store.pop(next(iter(store)), None)
        store[ticket] = value

    async def _on_ack(self, payload: dict[str, Any]) -> None:
        """يلتقط `ticket ⇄ هويّة القرار` لحظة تأكيد التنفيذ."""
        if not self._running or not isinstance(payload, dict):
            return
        ticket = _text(payload.get("ticket"))
        identity = {name: payload[name] for name in _OUTCOME_IDENTITY
                    if _text(payload.get(name))}
        if ticket and identity:
            self._ack_seen += 1
            self._keep(self._ticket_identity, ticket, identity)
            # 📌 قرارٌ صار أمرًا عند الوسيط لا يُطرد بسقف العدد. مقيس
            #    ٢٠٢٦-٠٩-٢٢: `pending=14000` = سبعةُ نطاقات × سقف ٢٠٠٠،
            #    كلُّها مشبَعة، و`pruned=2,092,140`. فالقرار يعيش حتّى
            #    يصله ألفا قرارٍ أحدث — **دقائق** — والصفقة تعيش دقائق
            #    إلى ساعات، فتصل نتيجتُها وقرارُها قد أُلقي
            #    (`unmatched=56 من 117` و`bridged=0/70`).
            #    **عتبةٌ بالعدد لا تقيس زمنًا** — درسٌ مدفوع من قبل.
            #    والتثبيت لا يشمل إلّا ما صار أمرًا: عشراتٌ لا ملايين.
            for index in self._identity.values():
                hit = None
                for name in _OUTCOME_IDENTITY:
                    ident = _text(identity.get(name))
                    if ident and ident in index:
                        hit = index[ident]
                        break
                if hit is not None and not hit.get(FIELD_PINNED):
                    hit[FIELD_PINNED] = True
                    self._pinned += 1

    async def _on_manage(self, payload: dict[str, Any]) -> None:
        """أقصى `r_multiple` بلغته الصفقة -- مقياسٌ **مستقلّ عن الخروج**.

        سياسة التسمية عندي تشتقّ الحكم من الربح المحقَّق، فقرارٌ اتجاهه صائب
        أفسده خروجٌ يصل بخسارة ⟹ يُسمّى بالاتجاه المعاكس. وقِيس أنّ ٤ من ٤٣
        صفقة معكوسةُ التسمية يقينًا و١٢ من ٢٨ خاسرة حُرّك وقفُها (أي بلغت
        ربحًا ثمّ ارتدّت). و`mfe`/`mae` لا مُنتِج لهما في المنصّة، لكنّ
        ٥٧٢/٥٧٣/٥٧٤ تنشر `r_multiple = profit_distance / risk` **مقيسةً
        لحظتها**. فيُجمَع أقصاها هنا ويُعلَن مع السجلّ -- بيانٌ لا حكم:
        التسمية لم تتغيّر، ومن يريد الفلترة يملك الرقم الآن.
        """
        if not self._running or not isinstance(payload, dict):
            return
        ticket = _text(payload.get("ticket"))
        value = num(payload.get("r_multiple"))
        if ticket and value is not None:
            self._manage_seen += 1
            self._keep(self._ticket_excursion, ticket,
                       max(value, self._ticket_excursion.get(ticket, value)))

    async def _on_tick(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict) or not payload.get("symbol"):
            return
        bid, ask = num(payload.get("bid")), num(payload.get("ask"))
        price = num(payload.get("price"))
        if price is None and bid is not None and ask is not None:
            price = (bid + ask) / 2.0
        if price is not None:
            self._prices[str(payload["symbol"])] = price

    def _decision_record(self, payload: dict[str, Any], source: str) -> dict[str, Any]:
        symbol = _text(payload.get("symbol"))
        account_id = _text(payload.get("account_id"))
        decision_id = _text(payload.get("decision_id") or payload.get("request_id")
                            or payload.get("cycle_id") or payload.get("event_id"))
        model_evidence = payload.get("model_evidence") if isinstance(payload.get("model_evidence"), dict) else {}
        return {
            "decision_id": decision_id, "account_id": account_id,
            "symbol": symbol, "timestamp": payload.get("timestamp"),
            "model_version": payload.get("model_version") or model_evidence.get("model_version"),
            "model_direction": model_evidence.get("direction"),
            # Preserve the exact evidence that existed at decision time.  The
            # learner must never rebuild old features from newer market data.
            # v1.4.0: يُحفَظ عقد الدليل (`_EVIDENCE_KEEP`) لا الظرف الذي حمله
            # -- المتّجه وأسماؤه ونسخة العقد وبصمته تُحفظ كاملةً كما وصلت،
            # وما يُترك (`unified` · `trace_id` · `parent_event` …) ظرف نقل
            # تضيفه النواة ولا يقرأه مستهلك واحد. الدليل لم يُنقَص.
            "features": dict(payload.get("features")) if isinstance(payload.get("features"), dict) else {},
            "feature_snapshot": dict(payload.get("feature_snapshot")) if isinstance(payload.get("feature_snapshot"), dict) else {},
            "model_evidence": {name: model_evidence[name]
                               for name in _EVIDENCE_KEEP if name in model_evidence},
            "strategy_evidence": dict(payload.get("evidence")) if isinstance(payload.get("evidence"), dict) else (
                dict(payload.get("metadata")) if isinstance(payload.get("metadata"), dict) else {}),
            "direction": _text(payload.get("direction") or payload.get("signal") or "neutral").lower(),
            "confidence": num(payload.get("confidence")) or num(payload.get("strength")) or 0.0,
            "score": num(payload.get("score")) or 0.0,
            "price_at_decision": num(payload.get("price_at_decision")) or self._prices.get(symbol),
            "target_net": payload.get("target_net"),
            "request_id": payload.get("request_id"),
            "cycle_id": payload.get("cycle_id"), "source_event": source,
            "gate_request_id": payload.get("gate_request_id"),
            "source_rank": _SOURCE_RANK.get(source, 0),
            "decision_missing": False, "training_eligible": True}

    def _remember(self, scope: str, record: dict[str, Any]) -> None:
        index = self._identity.setdefault(scope, {})
        for ident in _identities(record):
            index[ident] = record

    def _forget(self, scope: str, record: dict[str, Any]) -> None:
        index = self._identity.get(scope)
        if not index:
            return
        for ident in _identities(record):
            if index.get(ident) is record:
                index.pop(ident, None)

    @staticmethod
    def _merge(existing: dict[str, Any], record: dict[str, Any]) -> None:
        """Later stage wins on scalars, but never blanks proven evidence."""
        for name, value in record.items():
            if value is None or value == "":
                continue
            if name in _EVIDENCE_FIELDS and not value and existing.get(name):
                continue
            existing[name] = value

    def _prune(self, scope: str) -> None:
        bucket = self._decisions.get(scope)
        if not bucket:
            return
        cutoff = time.time() - self._max_age_s
        aged = 0
        while aged < len(bucket) and num(bucket[aged].get(FIELD_RECEIVED)) is not None \
                and float(bucket[aged][FIELD_RECEIVED]) < cutoff:
            aged += 1
        over_cap = max(0, (len(bucket) - aged) - self._max_pending)
        cut = aged + over_cap
        if not cut:
            return
        # 📌 المثبَّت (صار أمرًا) ينجو من سقف العدد وحده — ويُطرد بالعمر
        #    كغيره، فلا يخلد شيء. والمطرود بالعمر يُنسى كما كان.
        rescued = [row for row in bucket[aged:cut] if row.get(FIELD_PINNED)]
        for row in bucket[:cut]:
            if row.get(FIELD_PINNED) and row in rescued:
                continue
            self._forget(scope, row)
        del bucket[:cut]
        if rescued:
            bucket[:0] = rescued
            over_cap = max(0, over_cap - len(rescued))
        self._pruned_age += aged
        self._pruned_cap += over_cap
        if not bucket:
            self._decisions.pop(scope, None)
            self._identity.pop(scope, None)

    async def _capture_decision(self, payload: dict[str, Any], source: str) -> None:
        if not self._running or not isinstance(payload, dict) or not payload.get("symbol"):
            return
        record = self._decision_record(payload, source)
        scope = key(record["account_id"], record["symbol"])
        index = self._identity.setdefault(scope, {})
        existing = next((index[ident] for ident in _identities(record) if ident in index), None)
        if existing is not None:
            if record["source_rank"] >= int(existing.get("source_rank") or 0):
                self._merge(existing, record)
                self._remember(scope, existing)
            return
        record[FIELD_RECEIVED] = time.time()
        self._decisions.setdefault(scope, []).append(record)
        self._remember(scope, record)
        self._decisions_seen += 1
        self._prune(scope)

    async def _on_evaluated(self, payload: dict[str, Any]) -> None:
        self._evaluated_seen += 1
        await self._capture_decision(payload, EVENT_EVALUATED)

    async def _on_scored(self, payload: dict[str, Any]) -> None:
        self._scored_seen += 1
        await self._capture_decision(payload, EVENT_SCORED)

    async def _on_decision(self, payload: dict[str, Any]) -> None:
        self._resolved_seen += 1
        await self._capture_decision(payload, EVENT_DECISION)

    async def _on_final(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict) or not payload.get("symbol"):
            return
        self._final_seen += 1
        scope = key(payload.get("account_id"), payload.get("symbol"))
        index = self._identity.get(scope) or {}
        match = next((index[ident] for ident in
                      (_text(payload.get("request_id")), _text(payload.get("cycle_id")))
                      if ident and ident in index), None)
        if match is None:
            await self._capture_decision(payload, EVENT_FINAL)
            return
        match.update({
            "request_id": payload.get("request_id") or match.get("request_id"),
            "cycle_id": payload.get("cycle_id") or match.get("cycle_id"),
            "target_net": payload.get("target_net", match.get("target_net")),
            "price_at_decision": num(payload.get("reference_price")) or match.get("price_at_decision"),
            "source_event": EVENT_FINAL,
            "source_rank": _SOURCE_RANK[EVENT_FINAL],
        })
        self._remember(scope, match)

    def _find_decision(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        return learning_outcome_matching.find_decision(self, payload)

    async def _on_outcome(self, payload: dict[str, Any]) -> None:
        await learning_outcome_matching.on_outcome(self, payload)

    def _pending(self) -> int:
        return sum(len(items) for items in self._decisions.values())

    async def snapshot(self) -> dict[str, Any]:
        state: dict[str, Any] = {name: getattr(self, "_" + name) for name in _COUNTERS}
        state.update({"snapshot_version": SNAPSHOT_VERSION,
                      "decisions": self._decisions, "prices": self._prices,
                      "recent_match": list(self._recent_match),
                      "ticket_identity": self._ticket_identity,
                      "ticket_excursion": self._ticket_excursion})
        return state

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict) or state.get("snapshot_version") != SNAPSHOT_VERSION:
            raise ValueError("INVALID_LEARNING_OUTCOME_SNAPSHOT")
        decisions = state.get("decisions", {})
        prices = state.get("prices", {})
        if not isinstance(decisions, dict) or not isinstance(prices, dict):
            raise ValueError("INVALID_LEARNING_OUTCOME_SNAPSHOT")
        self._decisions = {str(k): [dict(v) for v in values if isinstance(v, dict)]
                           for k, values in decisions.items() if isinstance(values, list)}
        self._prices = {str(k): float(v) for k, v in prices.items()}
        # عدّادات فقط -- لا أوعية. `setattr` على وعاء يبدّل الكائن نفسه فيكتب
        # المشترِك في قاموس يتيم بعد الاستعادة؛ الأعداد لا مرجع لها فتأمن.
        for name in _COUNTERS:
            setattr(self, "_" + name, max(0, int(state.get(name, 0))))
        # الجسر يُستعاد وإلّا ضاع ربطُ كل صفقةٍ فُتحت قبل الإقلاع.
        tickets = state.get("ticket_identity", {})
        self._ticket_identity = {str(k): dict(v) for k, v in tickets.items()
                                 if isinstance(v, dict)} if isinstance(tickets, dict) else {}
        excursion = state.get("ticket_excursion", {})
        self._ticket_excursion = {str(k): float(v) for k, v in excursion.items()
                                  if num(v) is not None} if isinstance(excursion, dict) else {}  # noqa: E501
        recent = state.get("recent_match", [])
        self._recent_match = deque(
            (bool(hit) for hit in recent if isinstance(hit, bool)),
            maxlen=MATCH_WINDOW) if isinstance(recent, list) else deque(maxlen=MATCH_WINDOW)
        # A snapshot written before v1.3.0 has no arrival stamps and no bound on
        # its buckets (measured: 299,464 rows / 179 MB).  Stamp the strays now so
        # ageing has a clock, rebuild the index, and prune before the first tick.
        now = time.time()
        self._identity = {}
        for scope, bucket in list(self._decisions.items()):
            self._identity[scope] = {}
            for row in bucket:
                if num(row.get(FIELD_RECEIVED)) is None:
                    row[FIELD_RECEIVED] = now
                self._remember(scope, row)
            self._prune(scope)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        pruned = self._pruned_age + self._pruned_cap
        window = list(self._recent_match)
        matched = sum(1 for hit in window if hit)
        # نافذة حيّة لا عدّاد تراكمي: ١٧ نتيجة متتالية أخفقت مطابقتها ولم
        # يظهر ذلك (٢٠٢٦-٠٩-١٠) لأنّ التراكميّ كان ٨٠ مطابَقة قديمة مقابل
        # ١٧ حديثة، فبقيت الشارة خضراء وهي عمياء. الحكم على الأحدث وحده.
        blind = bool(window) and not matched
        # يُبنى من جدول العدّادات نفسه، فعدّادٌ جديد يظهر هنا بلا سطر إضافيّ.
        details = {name: getattr(self, "_" + name) for name in _COUNTERS}
        details.update({
            "unmatched_outcomes": self._unmatched, "pending": self._pending(),
            "pruned_by_age": self._pruned_age, "pruned_by_cap": self._pruned_cap,
            "recent_window": len(window), "recent_matched": matched,
            "bridged_by_ticket": self._bridged,
            "tickets_known": len(self._ticket_identity),
            "excursions_known": len(self._ticket_excursion),
            "max_pending_per_scope": self._max_pending,
            "max_pending_age_s": self._max_age_s})
        if self._records:
            # `details` تُحذف بالنواة، فما يجب أن يراه المالك يسكن `message`.
            message = ("outcomes=%d unmatched=%d (no_id=%d not_found=%d) "
                       "bridged=%d/%d (بلا_ack=%d قرارٌ_طُرد=%d مثبَّت=%d) "
                       "rmax=%d last%d=%d pending=%d pruned=%d منذ_الإقلاع=%d") % (
                self._records, self._unmatched, self._unmatched_no_identity,
                self._unmatched_not_found, self._bridged, len(self._ticket_identity),
                self._bridge_no_ack, self._bridge_lost_decision, self._pinned,
                len(self._ticket_excursion), len(window), matched, self._pending(), pruned,
                int(time.monotonic() - self._started_at),
            )
            return HealthStatus(
                state=HealthState.DEGRADED if blind else HealthState.HEALTHY,
                message=message, details=details)
        return HealthStatus(
            state=HealthState.HEALTHY,
            message=("READY_AWAITING_FIRST_CLOSED_TRADE_OUTCOME | outcomes=0"
                     " pending=%d منذ_الإقلاع=%d") % (
                self._pending(), int(time.monotonic() - self._started_at)),
            details=details,
        )
