from __future__ import annotations

from typing import Any

import clock
from core.contracts.atom import HealthState, HealthStatus
from shared.financial_scope import text


# ٢٠٢٦-٠٩-١٦: لقطة هذه الذرّة بلغت ٢٫١ ميغابايت مقيسةً على القرص
# (`snapshots` ١٫٢٨م + `margin_verdicts` ٧٠٤ك). السقف العدديّ ٤٠٩٦ في
# `state_inputs._remember` يحدّ الذاكرة لكنّه لا يعرف الزمن: سجلّ لقطة ٥٨٣
# وحُكم هامش ٥٨٥ يخصّان أمرًا بعينه وعمرهما الفعليّ ثوانٍ، فيُحمل أربعة
# آلاف منها في كل حفظ. التقليم بالزمن أوّلًا (درس ٢٠٢٦-٠٩-٠٩: عتبة بالعدد
# لا تبلغ ليلًا). ٦٠٠ ثانية = ستّة أضعاف مهلة الطلب الطائر في ٥٥٥ (٩٠ث).
#
# 🔴 ٢٠٢٦-٠٩-١٨ — قِيست المهلة على الحيّ فبان أنّها لا تقلّم شيئًا:
#
#     4096 سجلًّا · كلُّها بختمٍ زمنيّ · أقدمها 196 ثانية
#     أقدم من 600 ثانية: **صفر**
#
# فالسجلّات تُنتَج بمعدّل ٢١ في الثانية وتملأ السقف العدديّ في ثلاث دقائق
# قبل أن تقترب من عشر الدقائق — فالسقف هو الحاكم، والمهلة زينة. والثمن
# ١٫٣٧ م.ب تُجمَّد وتُكتب كل ستّين ثانية (~٢ ج.ب يوميًّا) مقابل صفر حكمِ
# هامشٍ في اللقطة نفسها.
#
# ومئةٌ وعشرون ثانية تبقى **أكبر** من مهلة الطلب الطائر في ٥٥٥ (٩٠ث)
# بهامش الثلث — فلا تسقط لقطةٌ يحتاجها أمرٌ لم يُحسم بعد. والعدّاد الذي
# يحرس هذا القرار موجودٌ ومعلَن: `snapshot_validity_blocked` في الشارة.
# إن ارتفع فالمهلة قصيرة، وإن بقي حيث هو فالتقليم يأخذ ميّتًا لا حيًّا.
_RECORD_TTL_S = 120.0


def _fresh_rows(registry: dict, now: float) -> list:
    """السجلّات التي لم يتجاوز عمرها المهلة. سجلّ بلا `measured_at` يُبقى:
    fail-open هنا أأمن من رمي حُكم هامش سليم فيُرفض أمر صحيح."""
    fresh = []
    for key, value in registry.items():
        measured_at = value.get("measured_at")
        if isinstance(measured_at, (int, float)) and now - measured_at > _RECORD_TTL_S:
            continue
        fresh.append((key, value))
    return fresh


def snapshot(atom: Any, version: str) -> dict[str, Any]:
    import time as _time
    now = _time.time()
    # التقليم يقع على الحالة الحيّة لا على نسخة اللقطة وحدها، وإلّا عاد
    # النموّ مع أوّل استعادة.
    for registry in (atom._snapshots, atom._margin_verdicts):
        keep = dict(_fresh_rows(registry, now))
        if len(keep) != len(registry):
            registry.clear()
            registry.update(keep)
    return {
        "version": version,
        # (٢٠٢٦-٠٨-٢٥) بوّابة `enabled` تُحفظ وتُستعاد — كانت تضيع مع كل
        # إقلاع فتعود مفتوحة (`fail-open` على آخر بوّابة قبل الوسيط، مقيس).
        "enabled": bool(getattr(atom, "_enabled", True)),
        "global_halted": atom._global_halted,
        "halted_accounts": dict(atom._halted_accounts),
        "snapshots": [
            {"snapshot_id": key, **value} for key, value in atom._snapshots.items()
        ],
        "margin_verdicts": [
            {"account_id": account, "request_id": request, **value}
            for (account, request), value in atom._margin_verdicts.items()
        ],
        # ٢٠٢٦-٠٩-١٨ — عدّادات الحجب كانت في `health.details` وحدها والنواة
        # تحذفها، فلا يُقرأ من القرص لماذا حُجب أمر. ومعها يُقاس السقف نفسه:
        # `snapshots` تحمل 4096 سجلًّا (1.37 م.ب تُجمَّد كل دورة لقطة) مقابل
        # 88 حكمَ هامشٍ فقط — أي تُخزَّن بمعدّل ستٍّ وأربعين ضِعف الحاجة.
        # وخفضُ السقف يحتاج أن يُعرَف أوّلًا كم مرّةً لم تُوجد لقطةٌ مطلوبة.
        "blocked": {
            "snapshot_validity": getattr(atom, "_snapshot_validity_blocked", 0),
            "margin_verdict": getattr(atom, "_margin_verdict_blocked", 0),
            "parent_decision": getattr(atom, "_parent_decision_blocked", 0),
            "ratio": getattr(atom, "_ratio_blocked", 0),
            "budget": getattr(atom, "_budget_blocked", 0),
            # ٢٠٢٦-٠٩-٢٣ (ختم `nq`): صار سببَ رفض — فيُقرأ من القرص لا من الشارة وحدها.
            "risk_unmeasured": getattr(atom, "_risk_unmeasured", 0),
            "spread": getattr(atom, "_spread_blocked", 0),
            "clock": getattr(atom, "_clock_blocked", 0),
            "reconcile": getattr(atom, "_reconcile_blocked", 0),
            "reference": getattr(atom, "_reference_blocked", 0),
            "exposure": getattr(atom, "_exposure_blocked", 0),
            "whitelist": getattr(atom, "_whitelist_blocked", 0),
            "identity": getattr(atom, "_identity_blocked", 0),
            # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): بوّابتا الفتح الجديدتان في 552.
            "asset_state": getattr(atom, "_asset_blocked", 0),
            "exposure_cap": getattr(atom, "_exposure_cap_blocked", 0),
            "exposure_reduced": getattr(atom, "_exposure_reduced", 0),
        },
        "last_reject": getattr(atom, "_last_reject", ""),
        "seen": getattr(atom, "_seen", 0),
        "finalized": getattr(atom, "_decisions_finalized", 0),
        "rejected": getattr(atom, "_rejected", 0),
    }


async def restore(atom: Any, state: dict[str, Any], fail_closed: str) -> None:
    if not isinstance(state, dict):
        atom._global_halted = True
        atom._restore_error = fail_closed
        raise ValueError(fail_closed)
    global_halted = state.get("global_halted", state.get("halted"))
    accounts = state.get("halted_accounts", {})
    if not isinstance(global_halted, bool) or not isinstance(accounts, dict):
        atom._global_halted = True
        atom._restore_error = fail_closed
        raise ValueError(fail_closed)
    atom._global_halted = global_halted
    atom._halted_accounts = {
        str(key): str(value) for key, value in accounts.items() if str(key)
    }
    # بوّابة مقفولة قبل الإيقاف تبقى مقفولة بعده — لا fail-open صامت.
    stored_enabled = state.get("enabled")
    if isinstance(stored_enabled, bool):
        atom._enabled = stored_enabled
    atom._snapshots = {}
    for row in state.get("snapshots") or []:
        if not isinstance(row, dict):
            continue
        snapshot_id = text(row.get("snapshot_id"))
        if not snapshot_id:
            continue
        atom._snapshots[snapshot_id] = {
            "decision_id": row.get("decision_id"),
            "gate_request_id": row.get("gate_request_id"),
            "snapshot_status": row.get("snapshot_status"),
            "usable_for_new_exposure": row.get("usable_for_new_exposure") is True,
            "usable_for_protection": row.get("usable_for_protection") is True,
            "produced_at": row.get("produced_at"),
            "measured_at": row.get("measured_at"),
        }
    atom._margin_verdicts = {}
    for row in state.get("margin_verdicts") or []:
        if not isinstance(row, dict):
            continue
        account = text(row.get("account_id"))
        request_id = text(row.get("request_id"))
        if not account or not request_id:
            continue
        atom._margin_verdicts[(account, request_id)] = {
            "approved": row.get("approved") is True,
            "reason": text(row.get("reason")),
            "required_margin": row.get("required_margin"),
            "free_margin": row.get("free_margin"),
            "measured_at": row.get("measured_at"),
        }
    atom._restore_error = ""
    await atom._publish_gate()


def health(atom: Any) -> HealthStatus:
    if not atom._running:
        return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
    details = {
        "enabled": atom._enabled,
        # (٢٠٢٦-٠٨-٢٥) عمى القائمة كان يقتل بصمت — صارت حالتها معلنة.
        "whitelist_seen": bool(getattr(atom, "_whitelist_seen", False)),
        "allowed_global": len(getattr(atom, "_allowed", ()) or ()),
        "allowed_accounts": {a: sorted(v) for a, v in
                             (getattr(atom, "_allowed_by_account", {}) or {}).items()},
        "global_halted": atom._global_halted,
        "halted_accounts": dict(atom._halted_accounts),
        "restore_error": atom._restore_error,
        "seen": atom._seen,
        "decision_finalized": atom._decisions_finalized,
        "rejected": atom._rejected,
        "clock_quality": clock.quality(),
        "spread_scopes": len(atom._spread),
        "reconcile_scopes": len(atom._reconcile),
        "reference_symbols": len(atom._reference),
        "reconcile_blocked": atom._reconcile_blocked,
        "reference_blocked": atom._reference_blocked,
        "identity_blocked": atom._identity_blocked,
        # ٢٠٢٦-٠٩-١٦: ثلاثة عدّادات حجب لم تكن معلنة أصلًا — لا في الرسالة
        # ولا في التفاصيل — ومنها السبق، وهو أكثر أسباب الرفض مقيسًا اليوم.
        "spread_blocked": atom._spread_blocked,
        "clock_blocked": atom._clock_blocked,
        "whitelist_blocked": atom._whitelist_blocked,
        "last_reject": getattr(atom, "_last_reject", ""),
        "exposure_scopes": len(atom._exposure),
        "exposure_blocked": atom._exposure_blocked,
        "parent_decision_blocked": atom._parent_decision_blocked,
        "margin_verdict_blocked": atom._margin_verdict_blocked,
        "snapshot_validity_blocked": atom._snapshot_validity_blocked,
        "margin_verdicts_tracked": len(atom._margin_verdicts),
        "snapshots_tracked": len(atom._snapshots),
        "identity_recovered": atom._identity_recovered,
        "identity_incomplete": atom._identity_incomplete,
        "asset_freeze_gate": bool(getattr(atom, "_asset_gate", False)),
        "pre_trade_exposure_cap": bool(getattr(atom, "_exposure_cap", False)),
        "asset_blocked": getattr(atom, "_asset_blocked", 0),
        "exposure_cap_blocked": getattr(atom, "_exposure_cap_blocked", 0),
        "exposure_reduced": getattr(atom, "_exposure_reduced", 0),
    }
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — البوّابة كانت `HEALTHY` في كلّ حال: مقفلةً
    # (`enabled=false`) وموقوفةً، بل كان فحص `enabled` بعد فرع `seen == 0` فلا يُقرأ قبل
    # أوّل أمر أصلًا (تدقيق ع1). الآن يُقدَّم الفحص على ذلك الفرع، والمقفلة أو الموقوفة
    # (عامًّا أو لحسابٍ واحد) `DEGRADED` — ومعهما إطفاءُ إحدى بوّابتي الفتح الجديدتين.
    # الصحّة وحدها تغيّرت؛ لا حكمَ أمرٍ واحد.
    prefix = ""
    if not atom._enabled:
        prefix += "🔴 البوّابة مقفلة (enabled=false) · "
    if atom._global_halted:
        prefix += "🔴 موقوفة لكلّ الحسابات · "
    elif atom._halted_accounts:
        prefix += "🔴 موقوفة للحسابات [%s] · " % ",".join(sorted(atom._halted_accounts))
    if atom._enabled and not getattr(atom, "_asset_gate", False):
        prefix += "⛔ حارس تجميد الأصل وميزانيّته مطفأ · "
    if atom._enabled and not getattr(atom, "_exposure_cap", False):
        prefix += "⛔ سقف التعرّض قبل الإرسال مطفأ · "
    state = HealthState.DEGRADED if prefix else HealthState.HEALTHY
    if atom._seen == 0:
        return HealthStatus(
            state=state,
            message=prefix + "READY_AWAITING_FIRST_LEGAL_ORDER | finalized=0 rejected=0",
            details=details,
        )
    # ٢٠٢٦-٠٩-١٦: `details` تُحذف بالنواة، فكل ما لا يسكن `message` غير
    # موجود عمليًّا. مقيس في اليوم نفسه: هذه الذرّة رفضت عشرة أوامر من اثني
    # عشر وقالت `rejected=10` فقط — والسبب (سبق واسع · مرجع غير صالح · ساعة
    # غير متزامنة) لم يظهر في أيّ مكان، لا هنا ولا في سجلّ الأخطاء.
    blocked = [(name, count) for name, count in (
        ("spread", atom._spread_blocked), ("ref", atom._reference_blocked),
        ("clock", atom._clock_blocked), ("recon", atom._reconcile_blocked),
        ("ident", atom._identity_blocked), ("expo", atom._exposure_blocked),
        ("parent", atom._parent_decision_blocked),
        ("margin", atom._margin_verdict_blocked),
        ("snap", atom._snapshot_validity_blocked),
        ("wl", atom._whitelist_blocked),
        ("نسبة", getattr(atom, "_ratio_blocked", 0)),
        ("مال", getattr(atom, "_budget_blocked", 0)),
        # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): تجميد/ميزانيّة الأصل · سقف التعرّض.
        ("أصل", getattr(atom, "_asset_blocked", 0)),
        ("سقف", getattr(atom, "_exposure_cap_blocked", 0)),
        ("قُصّ", getattr(atom, "_exposure_reduced", 0))) if count]
    message = "finalized=%d rejected=%d" % (
        atom._decisions_finalized, atom._rejected)
    if blocked:
        message += " | " + " ".join("%s=%d" % row for row in blocked)
    last_reject = getattr(atom, "_last_reject", "")
    if last_reject:
        message += " | last=%s" % last_reject
    # ٢٠٢٦-٠٩-١٨ (ختم NQ) — أمر المالك: «أظهر كل ما هو مهمّ ومخفيّ».
    # عيارُ هذه البوّابة هو ما يحجب، وكان غير معلَنٍ في شارةٍ ولا لقطة —
    # فالمالك يغيّره ولا يرى القيمة السارية. ودرسُ جلسة التحليل في اليوم
    # نفسه: **عيارٌ لا يُعلَن لا يُحسَم تعارضُه**، وذرّةٌ واحدة عندهم لم
    # تُعلن عيارها فبقي تعارضُها معلّقًا بينما حُسم في خمسٍ أخرى.
    # ٢٠٢٦-٠٩-١٨ (ختم المالك «اعمل أنسب») — النسبة تُقاس الآن بعد خصم نصف
    # السبريد من العائد وإضافته إلى المخاطرة، لأنّ السعر المرجعيّ منتصفُ
    # السوق مقيسًا (٣٢٦ أمرًا: شراء +2.99 · بيع −2.50). ويُقال في الشارة
    # كي لا يُقارَن رقمُ هذه البوّابة برقمِ بوّابةٍ لا تخصم — فيُظنّ الفرقُ
    # عطبًا. ومن لا يُعلن قاعدة قياسه يجعل رقمه غير قابلٍ للمقارنة.
    # ٢٠٢٦-٠٩-١٩ — النسبة لم تعد تردّ أمرًا بأمر المالك: «حارس يستلم صفقة
    # فيها هدف وستوب تمرق». تبقى محسوبةً معلَنةً ليُعرف ما خرج، لا لتحجب.
    message += " | عيار: نسبة %g ⛔تُقاس ولا تحكم (بعد نصف السبريد) · مال=[%g..%g]×الميزانيّة سبريد<=%g" % (
        getattr(atom, "_min_reward_risk", 0.0),
        getattr(atom, "_risk_floor_frac", 0.0),
        getattr(atom, "_risk_cap_frac", 0.0),
        getattr(atom, "_max_spread_points", 0.0))
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العياران الجديدان يُعلَنان مع آخر قصّ.
    message += " · فتح: تجميد/ميزانيّة الأصل=%s سقف تعرّض 508 قبل الإرسال=%s%s" % (
        "يحكم" if getattr(atom, "_asset_gate", False) else "مطفأ",
        "يحكم" if getattr(atom, "_exposure_cap", False) else "مطفأ",
        (" آخر قصّ: " + atom._last_exposure_cut)
        if getattr(atom, "_last_exposure_cut", "") else "")
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): العمر الأقصى لحالات المطابقة والمرجع والتعرّض قبل
    # الفتح عيارٌ يحجب — يُعلَن مع مصدره (`stale_after_s` في 609)، و`WAITING_FOR_ACTUAL` لا يُقبل.
    max_age = getattr(atom, "_state_max_age_s", None)
    if max_age is not None:
        message += " · حالات الفتح: عمر≤%gث (609) · بلا لقطة وسيط=رفض" % max_age
    # حارسٌ صامتٌ لنقص مدخله يبدو ناجحًا وهو غائب. العدد يفرّق بين «كلُّ
    # الأوامر مطابقة» و«لم يُقَس منها شيء».
    unmeasured = getattr(atom, "_risk_unmeasured", 0)
    if unmeasured:
        message += " | ⛔ مالٌ لا يُقاس يُرفض: %d أمرًا (%s)" % (
            unmeasured, getattr(atom, "_last_unmeasured", "-"))
    # ٢٠٢٦-٠٩-١٨ — البطاقة سجلُّ المالك: «لما بدي أراجع صفقة بسحب بطاقتها».
    # وسجلٌّ لا يُعرف أنّه يُكتب لا يُوثق به — فحالُه في الشارة: كم كُتب، وكم
    # أمرًا لم يجد بطاقةً، وآخر عطبِ قرص.
    # ٢٠٢٦-٠٩-١٨: حجم اللقطة قرارٌ ماليّ لا تفصيلٌ تقنيّ — ١.٣٧ م.ب كل دورة
    # تُجمَّد على حلقةٍ تحمل أربعًا وخمسين ذرّة. فعددُ المحفوظ يُعلَن مع
    # عدّاد الحجب الذي يحرسه، ليُقرأ القراران معًا.
    tracked = len(getattr(atom, "_snapshots", ()) or ())
    if tracked:
        message += " | لقطات محفوظة=%d (حجب=%d)" % (
            tracked, getattr(atom, "_snapshot_validity_blocked", 0))
    cards = getattr(atom, "_card_writes", 0)
    missing = getattr(atom, "_card_missing", 0)
    card_error = getattr(atom, "_card_error", "")
    if cards or missing or card_error:
        message += " | بطاقة: كُتبت=%d بلا بطاقة=%d%s" % (
            cards, missing, (" ⚠ %s" % card_error) if card_error else "")
    elif getattr(atom, "_cards", None) is None:
        message += " | بطاقة: معطّلة"
    return HealthStatus(
        state=state,
        message=prefix + message,
        details=details,
    )
