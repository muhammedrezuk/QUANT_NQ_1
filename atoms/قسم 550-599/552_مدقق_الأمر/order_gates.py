from __future__ import annotations

import math
import time
from typing import Any

from shared.financial_scope import text
from order_risk_measures import _num

# Campaign 450-901 batch B: the OPEN-path gates (parent authority, margin
# verdict, snapshot validity) extracted verbatim -- same behavior, smaller atom.
#
# Item 25 (27-atom review, 2026-08-27): found completely unwired -- atom.py
# had kept its own inline copy of every check below instead of calling out to
# this module. Fixed here first, with the same rigor as live code, since a
# "wire this in" pass would otherwise trust code that already looks correct
# without re-diffing it against atom.py. Wired into atom.py (v5.5.0) only
# after the fix was proven behavior-preserving: the atom's own 11-scenario
# suite plus a 90-case old-vs-new differential simulation (9 contexts x 10
# order shapes) matched exactly, run outside the project's own test tooling.
# atom.py's OPEN-path block in `_on_built` now delegates to
# `run_open_gates()` below instead of duplicating these three checks inline.
#
# One real bug was closed before wiring: the margin-verdict lookup used the RAW
# `body.get("account_id")` as half of its registry key, while every write to
# that same registry (atom.py's `_on_margin_verdict`, and this file's own
# `on_margin_verdict` in state_inputs.py) stores the key through
# `text(...)` (str(), stripped, "" for None). In atom.py's real call order
# this coincidentally matched, because `_on_built` already normalizes
# `body["account_id"]` before reaching these gates -- but nothing in this
# file enforced that precondition, so a caller that invoked this gate before
# that normalization (or passed a differently-shaped body) would silently
# miss an approved verdict and reject a legitimate order with
# MARGIN_VERDICT_MISSING. Wrapped in text() to match the registry's actual
# key shape unconditionally, the same as every other lookup in this atom.

AUTHORITY_FIELDS = ("decision_id", "parent_decision_id", "owner_command_id")


STAGE_PARENT = "PARENT_DECISION"
STAGE_MARGIN = "MARGIN_VERDICT"
STAGE_SNAPSHOT = "SNAPSHOT_VALIDITY"
SNAPSHOT_USABLE_STATUS = "READY"


async def run_open_gates(atom, body: dict[str, Any],
                         authority_fields: tuple = AUTHORITY_FIELDS) -> str:
    """Empty string = all OPEN gates passed; else the refusal reason."""
    # ٢٠٢٦-٠٩-٢٣ (ختم `nq`): لا إعفاء من القرار الأب لساق هيدج — نُزع الاستثناء.
    if not any(text(body.get(field)) for field in authority_fields):
        atom._parent_decision_blocked += 1
        await atom._refuse(body, "PARENT_DECISION_MISSING", STAGE_PARENT,
                           measured_at=time.time())
        return "PARENT_DECISION_MISSING"
    verdict = atom._margin_verdicts.get(
        (text(body.get("account_id")), text(body.get("request_id"))))
    if verdict is None:
        atom._margin_verdict_blocked += 1
        await atom._refuse(body, "MARGIN_VERDICT_MISSING", STAGE_MARGIN,
                           measured_at=time.time())
        return "MARGIN_VERDICT_MISSING"
    if not verdict.get("approved"):
        atom._margin_verdict_blocked += 1
        await atom._refuse(body, "MARGIN_VERDICT_REJECTED", STAGE_MARGIN,
                           value=verdict.get("required_margin"),
                           threshold=verdict.get("free_margin"),
                           measured_at=verdict.get("measured_at"))
        return "MARGIN_VERDICT_REJECTED"
    snapshot_id = text(body.get("snapshot_id"))
    if snapshot_id:
        record = atom._snapshots.get(snapshot_id)
        if record is None:
            atom._snapshot_validity_blocked += 1
            await atom._refuse(body, "SNAPSHOT_UNKNOWN", STAGE_SNAPSHOT,
                           measured_at=time.time())
            return "SNAPSHOT_UNKNOWN"
        if not record.get("usable_for_new_exposure"):
            atom._snapshot_validity_blocked += 1
            await atom._refuse(body, "SNAPSHOT_NOT_USABLE", STAGE_SNAPSHOT,
                               value=record.get("snapshot_status"),
                               threshold=SNAPSHOT_USABLE_STATUS,
                               measured_at=record.get("measured_at"))
            return "SNAPSHOT_NOT_USABLE"
    return ""


# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): بوّابتان جديدتان لأوامر الفتح وحدها.
#
# (١) تجميدُ الأصل وميزانيّته. 519 يجمّد الأصل حين تنفد ميزانيّته عند 518 (u ≥ 1) أو
# يوقفه المالك، و581 يحجب ذلك (`shared/position_delta_recompute.py:308-311`
# `PORTFOLIO_FROZEN`). أمّا طلب 555 فلا يحمل `snapshot_id` فلا يمرّ بلقطة 583، وحارس
# 516 يرى الطافي وحده — فكان الأصل المجمّد مفتوحًا للدخول (تدقيق ح-3؛ حيًّا 10-02:
# BTCUSD · USTEC · XAUUSD مجمّدة في لقطة 519 والأوامر تخرج عليها). الفحص مرآةُ 581:
# الحالة `FROZEN`/`PAUSED` تردّ، ومعها حكمُ دفتر 518 كما ينقله صفّ 519 (`breached` أو
# `u ≥ 1`) — لأنّ 519 يُبقي أصلًا في `HEDGING` على حاله وإن نفدت ميزانيّته
# (`519/atom.py:232-242`). والمجهول يُرفض كما يُرفض كلّ مدخلٍ غائب في هذه البوّابة.
_FROZEN_STATES = ("FROZEN", "PAUSED")  # `position_delta_recompute.py:310` حرفًا
#: نفادُ الميزانيّة: `u ≥ 1` — العتبة نفسها في 518 (`ledger_support.py:220`) و519 (`BREACH_RATIO`).
_BUDGET_SPENT_U = 1.0


def _asset_names(body: dict[str, Any]) -> list[str]:
    """أسماء الأصل التي قد يُفهرس بها 518/519 — بلا تكرار وبالترتيب."""
    names: list[str] = []
    for field in ("asset_canonical", "symbol", "logical_symbol", "broker_symbol"):
        name = text(body.get(field))
        if name and name not in names:
            names.append(name)
    return names


async def asset_state_gate(atom, body: dict[str, Any]) -> str:
    """"" = الأصل مفتوحٌ للتعرّض الجديد؛ وإلّا سبب الرفض بعد نشره."""
    if not atom._asset_gate:
        return ""
    account = text(body.get("account_id"))
    names = _asset_names(body)
    portfolios = [atom._portfolios[(account, n)] for n in names if (account, n) in atom._portfolios]
    reason, value, threshold, measured = "", None, None, time.time()
    if not portfolios:
        reason, value = "ASSET_STATE_UNKNOWN", names
    else:
        frozen = next((p for p in portfolios
                       if p.get("state") in _FROZEN_STATES or p.get("paused")), None)
        spent = next((p for p in portfolios if p.get("breached")
                      or (_num(p.get("u")) or 0.0) >= _BUDGET_SPENT_U), None)
        if frozen is not None:
            reason, value, threshold = "ASSET_FROZEN", frozen.get("state"), "NORMAL"
            measured = frozen.get("measured_at")
        elif spent is not None:
            reason, value, threshold = "ASSET_BUDGET_EXHAUSTED", spent.get("u"), 1.0
            measured = spent.get("measured_at")
    if not reason:
        return ""
    atom._asset_blocked += 1
    await atom._refuse(body, reason, value=value, threshold=threshold, measured_at=measured)
    return reason


# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): (٢) سقفُ التعرّض **قبل** الإرسال. 508 يحسب التعرّض من المراكز القائمة بعد التنفيذ،
# فيمرّ أمرٌ يضاعف الحدّ ثمّ يُقفَل القاطع ويُفكّ حتّى 83 مرّة يوميًّا؛ وبلغت الوسيطَ
# أوامر مثل USTEC 31.2 لوت (≈945,000$ على حقوق ~800$) — تدقيق ح-2. الحدّ نفسه حدّ
# المالك في 508 (`max_exposure_pct` يُقرأ من حالته المنشورة لا يُنسخ رقمه)، وتُطبَّق
# معادلته نفسها: الاسميّ = |الحجم| × السعر × حجم العقد (`508/atom.py:132,177`) والخرق
# `pct >= limit` (`:207`) — فالمسموح ما يبقى **دون** الحدّ بعد الأمر. وما تجاوزه يُقصّ
# حجمُه إلى الأدنى على خطوة الرمز (أمر المالك ٢٠٢٦-١٠-٠١)، وما دون أصغر لوت يُرفض.
#: عمر حالة 508 المقبول — مرآةُ `stale_after_s = 10` في 609 الذي تُبنى منه صورة المراكز
#: (609 يقرأ كلّ ثانية، و508 ينشر مع كلّ قراءة) — فحالةٌ أقدم منه صورةٌ بائتة.
_EXPOSURE_MAX_AGE_S = 10.0
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العمر نفسه لحالات المطابقة (520) والمرجع (521) والتعرّض
# (508) قبل أن يُبنى عليها فتح — كلّها تُشتقّ من صورة المراكز أو تُنشر كلّ ثانية، وصورةٌ أقدم من
# `stale_after_s` في 609 بائتةٌ بحكم 609 نفسه. لا رقم جديد: هو `_EXPOSURE_MAX_AGE_S` باسمٍ عامّ.
STATE_MAX_AGE_S = _EXPOSURE_MAX_AGE_S


def state_age(stamp: Any) -> float | None:
    """عمر حالةٍ من لحظة استلامها (`time.monotonic`)، أو None إن لم يُختم شيء."""
    value = _num(stamp)
    return None if value is None else time.monotonic() - value


def state_stale(stamp: Any) -> bool:
    """بلا طابع، أو أقدم من العمر الأقصى، أو من المستقبل ⟸ مجهول."""
    age = state_age(stamp)
    return age is None or age < 0.0 or age > STATE_MAX_AGE_S


_PERCENT = 100.0
_LOT_EPSILON = 1e-9


def _contract_spec(atom, body: dict[str, Any], scoped: tuple) -> dict[str, Any] | None:
    """مواصفة الرمز كما يقرؤها `order_risk_measures.risk_dollars` تمامًا."""
    spec = atom._specs.get(scoped)
    if not isinstance(spec, dict):
        spec = body.get("symbol_spec")
        if isinstance(spec, dict) and text(spec.get("symbol")) != text(body.get("symbol")):
            spec = None
    return spec if isinstance(spec, dict) else None


async def pre_trade_exposure(atom, body: dict[str, Any], scoped: tuple) -> str:
    """"" = الأمر (ربّما مقصوصًا) يبقى تحت الحدّ؛ وإلّا سبب الرفض بعد نشره."""
    if not atom._exposure_cap:
        return ""
    record = atom._exposure.get((scoped[0], scoped[1])) or {}
    stamp = _num(record.get("_received_mono"))
    age = None if stamp is None else time.monotonic() - stamp
    limit = _num(record.get("max_exposure_pct"))
    gross = _num(record.get("gross_exposure"))
    equity = _num(record.get("equity"))
    spec = _contract_spec(atom, body, scoped) or {}
    size = _num(spec.get("contract_size"))
    price = _num(body.get("reference_price"))
    volume = _num(body.get("volume"))
    if age is None or age < 0.0 or age > _EXPOSURE_MAX_AGE_S:
        reason, value, threshold = "EXPOSURE_STATE_STALE", age, _EXPOSURE_MAX_AGE_S
    elif limit is not None and limit <= 0.0:
        return ""  # حدٌّ صفر = لا حدّ، بدلالة 508 نفسها (`over` يشترط `limit > 0`)
    elif None in (limit, gross, equity, size, price, volume) or equity <= 0.0 \
            or size <= 0.0 or price <= 0.0 or volume <= 0.0:
        reason, value, threshold = "EXPOSURE_PROJECTION_UNKNOWN", None, limit
    else:
        cap = limit / _PERCENT * equity
        unit = price * size
        projected = (gross + volume * unit) / equity * _PERCENT
        body["exposure_projected_pct"] = round(projected, 4)
        body["exposure_limit_pct"] = limit
        if gross + volume * unit < cap:
            return ""
        step = _num(spec.get("volume_step"))
        minimum = _num(spec.get("volume_min")) or step
        if not step or step <= 0.0:
            reason, value, threshold = "EXPOSURE_PROJECTION_UNKNOWN", round(projected, 4), limit
        else:
            lots = math.floor(max(0.0, cap - gross) / unit / step + _LOT_EPSILON)
            while lots > 0 and gross + lots * step * unit >= cap:
                lots -= 1  # الحدّ خرقٌ عند المساواة (`pct >= limit`) — خطوةٌ أدنى
            reduced = round(lots * step, 8)
            if lots <= 0 or reduced < minimum - _LOT_EPSILON:
                reason, value, threshold = "EXPOSURE_CAP_BELOW_MIN_LOT", round(projected, 4), limit
            else:
                atom._exposure_reduced += 1
                atom._last_exposure_cut = "%s %s⟶%s (%.0f%%⟶%.0f%% حدّ %g%%)" % (
                    text(body.get("symbol")), volume, reduced, projected,
                    (gross + reduced * unit) / equity * _PERCENT, limit)
                body["volume_before_exposure_cap"] = volume
                body["volume"] = reduced
                body["exposure_projected_pct"] = round((gross + reduced * unit) / equity * _PERCENT, 4)
                return ""
    atom._exposure_cap_blocked += 1
    await atom._refuse(body, reason, value=value, threshold=threshold,
                       measured_at=record.get("timestamp"))
    return reason
