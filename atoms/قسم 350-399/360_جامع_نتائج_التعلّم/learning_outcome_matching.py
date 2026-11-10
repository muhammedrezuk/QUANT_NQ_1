"""٣٦٠ — مطابقةُ نتيجة الوسيط بقرارها، وتسميتُها، ونشرُ السجلّ.

v1.8.1 (٢٠٢٦-١٠-٠١، ختم المالك «Nq»): نُقلت **حرفيًّا** من `atom.py` ليبقى تحت حدّ
الأربع مئة سطر فعليّ (المادة ٩ ملف ٤). لا حقلَ ولا سببَ ولا تسميةَ ولا حدثَ تبدّل. كلّ
دالّةٍ هنا تأخذ الذرّة أوّلًا (`atom`) مكان `self`، و`atom.py` يُبقي اسمها القديم بوّابةً
رفيعة — فالمعالج `_on_outcome` ما زال تابعًا مربوطًا يلفّه `@section_atom` كما كان.
وحدثُ النشر وسياسةُ التسمية هنا لأنّ ناشرهما الوحيد صار هنا.
"""

from __future__ import annotations

from typing import Any

from learning_outcome_common import FIELD_RECEIVED, _OUTCOME_IDENTITY, _text, key, num

LABEL_POLICY_VERSION = "executed_direction_net_pnl_v2"
EVENT_OUT = "learning.outcome.recorded"


def find_decision(atom, payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    # Identity only.  The old fallback returned bucket[0] -- the OLDEST
    # pending decision, up to 4.6 days stale (measured) -- which silently
    # labelled trades against a decision that never produced them and kept
    # `unmatched` at a false zero.  563 rejoins decision_id onto the broker
    # outcome from its own ledger, so a real match has an identity.
    scope = key(payload.get("account_id"), payload.get("symbol"))
    index = atom._identity.get(scope)
    if not index:
        return scope, None
    for name in _OUTCOME_IDENTITY:
        ident = _text(payload.get(name))
        if ident and ident in index:
            return scope, index[ident]
    # الجسر: هويّةٌ التقطها `ack` باسم هذا الـticket. لا تخمين هنا --
    # الربط أعلنه منفّذ الأمر نفسه، وهو أوثق من النتيجة التي فقدته.
    bridge = atom._ticket_identity.get(_text(payload.get("ticket")))
    if bridge is None:
        atom._bridge_no_ack += 1
        return scope, None
    for name in _OUTCOME_IDENTITY:
        ident = _text(bridge.get(name))
        if ident and ident in index:
            atom._bridged += 1
            return scope, index[ident]
    # `ack` موجودٌ وقرارُه ليس في الفهرس — أي أنّه طُرد. يُسمّى ولا يُبتلع.
    atom._bridge_lost_decision += 1
    return scope, None


async def on_outcome(atom, payload: dict[str, Any]) -> None:
    if not atom._running or atom._context is None or not isinstance(payload, dict) or not payload.get("symbol"):
        return
    scope, decision = atom._find_decision(payload)
    atom._recent_match.append(decision is not None)
    if decision is not None:
        bucket = atom._decisions.get(scope) or []
        if decision in bucket:
            bucket.remove(decision)
        if not bucket:
            atom._decisions.pop(scope, None)
        atom._forget(scope, decision)
        decision = {name: value for name, value in decision.items()
                    if name != FIELD_RECEIVED}
    else:
        # v1.4.0: «غير مطابَق» وحدها لا تُعالَج -- تُقاس ١٧ من ١٧ نتيجة
        # (٢٠٢٦-٠٩-١٠) ولا يُعرف أيّ البابين، والعلاجان متضادّان:
        #   · NO_IDENTITY_ON_OUTCOME ⇒ النتيجة وصلت بلا هويّة أصلًا،
        #     والعلّة عند ناشرها (٥٦٣ يعيد ربط `decision_id` من دفتره
        #     وقد يعجز) -- تُبلَّغ جلسته ولا تُعالَج هنا.
        #   · IDENTITY_NOT_FOUND ⇒ الهويّة جاءت ولم أجدها: قراري أنا
        #     قُلّم قبل أن تصل النتيجة، والعلاج رفع `max_pending_per_scope`
        #     أو المهلة -- عيار داخل هذه الذرّة.
        # فيُصنَّف السبب ويظهر على اللوحة بدل تخمين في الجلسة التالية.
        had_identity = (any(_text(payload.get(name)) for name in _OUTCOME_IDENTITY)
                        or _text(payload.get("ticket")) in atom._ticket_identity)
        missing_reason = ("IDENTITY_NOT_FOUND" if had_identity
                          else "NO_IDENTITY_ON_OUTCOME")
        atom._unmatched += 1
        if had_identity:
            atom._unmatched_not_found += 1
        else:
            atom._unmatched_no_identity += 1
        outcome_id = _text(payload.get("event_id") or payload.get("ticket") or f"{atom._records + 1}")
        side = _text(payload.get("side")).lower()
        fallback_direction = side if side in ("buy", "sell") else "neutral"
        decision = {
            "decision_id": f"unmatched:{outcome_id}", "confidence": 0.0,
            "account_id": _text(payload.get("account_id")), "score": 0.0,
            "symbol": _text(payload.get("symbol")), "features": {},
            "direction": fallback_direction, "feature_snapshot": {},
            "model_evidence": {}, "strategy_evidence": {},
            "model_version": None, "model_direction": None,
            "price_at_decision": None, "target_net": None,
            "decision_missing": True, "training_eligible": False,
            "missing_reason": missing_reason,
            "source_event": "market.outcome.realized"}

    profit = num(payload.get("profit")) or 0.0
    direction = str(decision.get("direction") or "neutral").lower()
    if decision.get("decision_missing"):
        label = "neutral"
    else:
        label = direction if profit > 0 else (
            "sell" if direction == "buy" else "buy" if direction == "sell" else "neutral"
        ) if profit < 0 else "neutral"
    record = {
        **decision,
        "outcome": label,
        "label_policy_version": LABEL_POLICY_VERSION,
        "feature_cutoff_time": decision.get("timestamp"),
        "label_time": payload.get("timestamp"),
        "realized_pnl": profit,
        "actual_net": payload.get("actual_net"),
        "mfe": payload.get("mfe"),
        "mae": payload.get("mae"),
        "duration": payload.get("duration"),
        "exit_reason": payload.get("reason"),
        "ticket": payload.get("ticket"),
        "outcome_event_id": payload.get("event_id"),
        # بيانٌ لا حكم: أقصى ربحٍ بلغته الصفقة بوحدة R، مستقلًّا عن خروجها.
        "max_r_multiple": atom._ticket_excursion.pop(
            _text(payload.get("ticket")), None),
    }
    atom._records += 1
    await atom._context.publish(EVENT_OUT, record)
