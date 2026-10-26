"""٥١٧ — المركز يُغلق على أرجل والنتيجة مجموعُها: هويّةُ الرِّجل، وجمعُ الأرجل، ودمجُ الحدث، وبناءُ النتيجة.

٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): نُقلت **حرفيًّا** من `atom.py` (السبب في `trade_outcome_common.py`)
— صفر تغيير في السلوك. `_output` و`_adopt_legacy` و`_sum_legs` و`_merge` كانت طرقًا في `Atom` (الثانية
والثالثة ساكنتين): `self` صار الذرّةَ معاملًا أوّل (`atom`)، وبقي في `atom.py` تفويضٌ بالأسماء القديمة،
وكلُّ نداءٍ بينها يمرّ بالذرّة كما كان (`atom._sum_legs` …). و`_leg_key` و`_leg_known` و`IDENTITY_FIELDS`
و`WARNING_IDENTITY` يستوردها `atom.py` باسمها.

لا تنشر هذه الوحدة حدثًا ولا تلمس قرصًا: `merge` تُعيد (الحالة، المخرَجات) لمعاملة المخزن في `atom.py`.
"""
from __future__ import annotations

from typing import Any

from shared.financial_scope import text
from trade_outcome_common import (COSTS, EVENT_OUT, LEG_CLOSED, LEG_LEGACY, LEG_PARTIAL,
                                  STATUS_OPEN, _digest, number)

# NQ seal, item 22, package T (T1): the decision identity pair rides the
# outcome into the loss report -- merged durably with the rest of the trade
# state, absent values pass as None and are declared, never invented.
IDENTITY_FIELDS = ("decision_id", "gate_request_id")
WARNING_IDENTITY = "identity_incomplete"


def _leg_key(payload: dict[str, Any]) -> str:
    """هويّة الرِّجل بمحتواها: النوع · الحجم · سعر الخروج · الربح.

    لا برقم صفّ الجسر: الإكسبرت يكتب الرِّجل نفسها في صفّين أحيانًا — مقيس
    ٢٠٢٦-٠٩-٢٤ في `trade_events_v2`: ثلاث أرجلٍ جزئيّة للذهب مكرّرة بقيمها كلّها
    وفي الثانية نفسها، فتصل حدثين بهويّتين. وعلى ٦٠٦ أرجل لم تتطابق رِجلان
    مختلفتان في هذه الأربعة قطّ. ومراجعةُ الرِّجل نفسها (تكاليف تصل لاحقًا)
    تقع على المفتاح نفسه لأنّ التكاليف خارجه.
    """
    parts = [text(payload.get("event_type")).upper() or LEG_CLOSED]
    for name in ("volume", "exit_price", "profit"):
        value = number(payload.get(name))
        parts.append("?" if value is None else repr(round(value, 8)))
    return "|".join(parts)


def _leg_known(leg: dict[str, Any]) -> bool:
    return all(number(leg.get(name)) is not None for name in ("profit", *COSTS))


def output(atom, state: dict[str, Any], completeness: str) -> dict[str, Any]:
    gross = number(state.get("profit")); account = str(state["account_id"])
    broker = str(state["broker"]); capital = atom._truth.get(account, "equity")
    values = {name: number(state.get(name)) for name in COSTS}
    unknown = [name for name, value in values.items() if value is None]
    complete = completeness == "COMPLETE" and gross is not None and capital is not None
    net = gross + sum(value for value in values.values() if value is not None) if complete else None
    loss_pct = -(net/capital)*100.0 if net is not None and capital else None
    identity = {field: state.get(field) for field in IDENTITY_FIELDS}
    identity_missing = [field for field in IDENTITY_FIELDS if not identity[field]]
    if identity_missing:
        atom._identity_incomplete += 1
        identity["identity_missing"] = identity_missing
        identity["identity_warnings"] = [WARNING_IDENTITY]
    legs = state.get("legs") if isinstance(state.get("legs"), dict) else {}
    # الأرجل تُعلن مع النتيجة ليُقرأ من أين جاء المجموع، لا ليُعاد جمعه.
    identity["legs"] = len(legs) or 1
    identity["partial_legs"] = sum(1 for leg in legs.values()
                                   if isinstance(leg, dict) and leg.get("event_type") == LEG_PARTIAL)
    identity["late_leg"] = bool(state.get("_late_leg"))
    if state.get("_leg_event_type"):
        identity["leg_event_type"] = state.get("_leg_event_type")
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): عمولة الدخول المضافة تُعلن بمصدرها،
    # وغيابها يُعلن ولا يُصفَّر. والرِّجل المتأخّرة لا تحملها (حُسبت مع المركز).
    entry = None if state.get("_late_leg") else state.get("entry")
    entry = entry if isinstance(entry, dict) else None
    identity["entry_costs_included"] = entry is not None
    identity["entry_commission"] = number(entry.get("commission")) if entry else None
    identity["entry_costs_source"] = entry.get("source") if entry else None
    return {"id": "trade_outcome", "account_id": account, "broker": broker,
            "symbol": state.get("symbol"), "ticket": state.get("ticket"),
            "trade_id": state.get("trade_id"), "trade_identity": state.get("trade_identity"),
            "request_id": state.get("request_id"), **identity, "completeness": completeness,
            "costs_complete": complete, "costs_known": [name for name in COSTS if name not in unknown],
            "costs_unknown": unknown, "gross_pnl": gross,
            "pnl": round(net, 2) if net is not None else None,
            "loss_pct": round(loss_pct, 4) if loss_pct is not None else None,
            "is_loss": net < 0 if net is not None else None,
            "commission": values["commission"], "swap": values["swap"],
            "fee": values["fee"],
            "cost_total": round(net-gross, 2) if net is not None and gross is not None else None,
            "metadata": {"reference_capital": capital}, "timestamp": state.get("timestamp")}


def adopt_legacy(state: dict[str, Any]) -> dict[str, Any]:
    """حالةٌ من إصدارٍ سابق بلا أرجل ⟸ رِجلٌ واحدة تحمل ما عُدّ فيها."""
    legs: dict[str, Any] = {}
    if number(state.get("profit")) is not None:
        legs[LEG_LEGACY] = {"event_type": LEG_LEGACY, "profit": number(state.get("profit")),
                            **{name: number(state.get(name)) for name in COSTS}}
    state["legs"] = legs
    if state.get("status") in {"COMPLETE", "INCOMPLETE"}:
        # نُشرت نتيجتها على رِجلها الأولى، وما بعدها يُنشر رِجلًا رِجلًا.
        state["emitted_legs"] = sorted(legs)
    else:
        # الإصدار السابق عدّ كلَّ حدثٍ نهائيًّا — تبقى على عقده.
        state["closed"] = bool(legs)
    return legs


def sum_legs(state: dict[str, Any]) -> None:
    """الربح والتكاليف مجموعُ الأرجل؛ ورِجلٌ مجهولةُ رقمٍ تجعل المجموع مجهولًا."""
    legs = state.get("legs") or {}
    for name in ("profit", *COSTS):
        values = [number(leg.get(name)) for leg in legs.values() if isinstance(leg, dict)]
        state[name] = (round(sum(values), 8)
                       if values and all(value is not None for value in values) else None)
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): عمولة الدخول فوق مجموع الأرجل —
    # تُعاد من الأرجل في كلّ مرّة ثمّ تُضاف، فلا تتراكم مهما أُعيد الجمع. وما
    # لا يُعرف منها (رسمٌ لم تقرأه صورة المركز) لا يجعل المجموع مجهولًا: لم
    # يكن فيه أصلًا.
    entry = state.get("entry")
    if isinstance(entry, dict):
        for name in COSTS:
            value = number(entry.get(name))
            if value is not None and state.get(name) is not None:
                state[name] = round(state[name] + value, 8)


def merge(atom, state: dict[str, Any], payload: dict[str, Any],
          account: str, broker: str, trade: str, remaining: float):
    kind = text(payload.get("event_type")).upper() or LEG_CLOSED
    key = _leg_key(payload)
    # ٢٠٢٦-١٠-٠٢: حجم الرِّجل يُحفظ معها — به تُطرح الأجزاء من صورة المركز
    # حين تُشتقّ عمولة الدخول. (لا يدخل الجمع ولا هويّة الرِّجل.)
    incoming = {"event_type": kind, "volume": number(payload.get("volume")),
                **{name: number(payload.get(name)) for name in ("profit", *COSTS)}}
    legs = state.get("legs")
    if not isinstance(legs, dict):
        legs = atom._adopt_legacy(state)
        legacy = legs.get(LEG_LEGACY)
        # صفٌّ مكرَّر من الإكسبرت لرِجلٍ عُدّت قبل هذا الإصدار: مالُها مالُها.
        if legacy is not None and all(
                legacy.get(name) is not None and incoming.get(name) is not None
                and abs(float(legacy[name]) - float(incoming[name])) < 0.005
                for name in ("profit", *COSTS)):
            return state, []
    leg = legs.get(key)
    if leg is None:
        legs[key] = incoming
    else:
        filled = False
        for name in ("profit", *COSTS):
            if leg.get(name) is None and incoming.get(name) is not None:
                leg[name] = incoming[name]
                filled = True
        if not filled:
            return state, []          # الرِّجل نفسها ثانيةً — لا مال جديد
    state.update({"account_id": account, "broker": broker, "trade_identity": trade})
    for name in ("symbol", "ticket", "trade_id", "request_id", "timestamp", *IDENTITY_FIELDS):
        if payload.get(name) is not None:
            state[name] = payload.get(name)
    if kind != LEG_PARTIAL:
        state["closed"] = True
    capital = atom._truth.get(account, "equity")
    emitted = state.setdefault("emitted_legs", [])
    if state.get("status") in {"COMPLETE", "INCOMPLETE"}:
        # نتيجة المركز نُشرت: الرِّجل المتأخّرة تُنشر وحدها بهويّتها هي.
        if key in emitted or not _leg_known(legs[key]) or capital is None or capital <= 0:
            return state, []
        emitted.append(key)
        atom._late_legs += 1
        view = dict(state)
        view.update({name: legs[key].get(name) for name in ("profit", *COSTS)})
        view.update({"legs": {key: legs[key]}, "_late_leg": True, "_leg_event_type": kind})
        output_id = "trade-result-leg:" + _digest("|".join((account, broker, trade, key)))
        return state, [(output_id, EVENT_OUT, atom._output(view, "COMPLETE"))]
    atom._sum_legs(state)
    if not state.get("closed"):
        # مركزٌ ما زال مفتوحًا: لا نتيجة ولا مهلة حتى تصل رِجلُ إغلاقه.
        state["status"] = STATUS_OPEN
        return state, []
    state["remaining_s"] = max(0.0, remaining)
    known = all(number(state.get(name)) is not None for name in ("profit", *COSTS))
    if known and capital is not None and capital > 0:
        state["status"] = "COMPLETE"; state["remaining_s"] = 0.0
        state["terminal_input_id"] = payload.get("event_id")
        state["emitted_legs"] = sorted(legs)
        output_id = "trade-result:" + _digest(account + "|" + broker + "|" + trade)
        return state, [(output_id, EVENT_OUT, atom._output(state, "COMPLETE"))]
    state["status"] = "PARTIAL"
    return state, []
