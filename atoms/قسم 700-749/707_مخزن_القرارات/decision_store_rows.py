"""٧٠٧ — بناءُ الصفّ من الحمولة، وما يُنطق عنه: انحرافُ ساعة المصدر وقرارٌ لم يُخزَّن.

v4.20.1 (٢٠٢٦-١٠-٠١، ختم المالك «Nq»): نُقلت **حرفيًّا** من `atom.py` ليبقى تحت حدّ
الأربع مئة سطر فعليّ (المادة ٩ ملف ٤). لا عمودَ ولا حقلَ ولا نصَّ سجلٍّ تبدّل. كلّ
دالّةٍ هنا تأخذ الذرّة أوّلًا (`atom`) مكان `self`، و`atom.py` يُبقي اسمها القديم
بوّابةً رفيعة.
"""

from __future__ import annotations

import json
import time
from typing import Any

# فارق يُعدّ طابعًا مستقبليًّا. الطابع لا يُصحَّح — يُسجَّل كما جاء ويُنطق
# الانحراف؛ تصحيحه بطرح ثابت تخمينٌ، وقد كاد يزرع خطأً دائمًا من قبل.
_FUTURE_STAMP_TOLERANCE_S = 60.0
_STAMP_LOG_EVERY_S = 60.0
_FAILURE_LOG_EVERY_S = 60.0


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _clock_skew(payload: dict[str, Any], stamp: float | None,
                now: float) -> float | None:
    """انحراف ساعة المصدر — أيًّا كان الحقل الذي يحمله.

    عقد `platform.trade_event` تغيّر ٢٠٢٦-٠٩-١٦ (٦١١ v4.1.0): `timestamp`
    صار **بساعتنا**، وطابع الوسيط انتقل إلى `broker_time` ومعه
    `clock_skew_s` جاهزًا. فقياسُ الانحراف من `timestamp` وحده — كما كان —
    **يعمى بعد هذا التغيير**: العدّاد يتوقّف عن الزيادة لا لأنّ العلّة زالت
    بل لأنّ مكانها تبدّل. تُقرأ المصادر الثلاثة بالترتيب، وأوّلُ موجودٍ يفوز:
    الحقل الجاهز · ثمّ `broker_time - timestamp` · ثمّ (توافقًا مع الناشرين
    الذين لم يتحوّلوا بعد) `timestamp - الآن`.
    """
    if not isinstance(payload, dict):
        return None
    ready = _to_float(payload.get("clock_skew_s"))
    if ready is not None:
        return ready
    broker = _to_float(payload.get("broker_time"))
    if broker is not None:
        return broker - (stamp if stamp is not None else now)
    return None if stamp is None else stamp - now


def build_row(atom, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    approved = payload.get("approved")
    if approved is None:
        approved = meta.get("approved")
    decided_at = _to_float(payload.get("timestamp"))
    recorded_at = time.time()
    skew = _clock_skew(payload, decided_at, recorded_at)
    if skew is not None and skew > _FUTURE_STAMP_TOLERANCE_S:
        atom.future_stamp_count += 1
        atom._note_future_stamp(stage, recorded_at + skew, recorded_at)
    rejection = payload.get("rejection")
    # سبب الرفض الحقيقي: ذرّة ٤٦٦ تنشر تصنيف الطبقة في `metadata.reason`
    # (`BLOCKED_UPSTREAM`) والسببَ الفعليّ في `rejection.reason`. كان
    # الأوّل وحده يُخزَّن، فبدت ٧٢٬٦٦٦ رفضةً بسبب واحد بينما الحقيقة في
    # الحمولة: DECISION_SIDE_WAIT ٦٤٬٨٥٢ · FILTER_FAILED ٧٬٦٠٩ · وغيرها
    # (مقيس ٢٠٢٦-٠٩-٠٩، وبلاغ قسم ٤٥٠-٤٩٩). العمودان يتعايشان: كلٌّ صادق
    # في موضعه.
    rejection_reason = _text(rejection.get("reason")) if isinstance(rejection, dict) else None
    payload_json = None
    if atom._keep_payload:
        try:
            payload_json = json.dumps(payload, ensure_ascii=False,
                                      sort_keys=True, default=str)
        except (TypeError, ValueError):
            payload_json = None
    return {
        "stage": stage,
        "request_id": _text(payload.get("request_id")),
        "account_id": _text(payload.get("account_id")),
        "symbol": _text(payload.get("symbol")),
        "direction": _text(payload.get("direction") or payload.get("side")
                           or payload.get("bias") or meta.get("direction")),
        "approved": None if approved is None else int(bool(approved)),
        "reason": _text(payload.get("reason") or meta.get("reason")),
        "confidence": _to_float(payload.get("confidence")
                                if payload.get("confidence") is not None
                                else meta.get("confidence")),
        # T5: the decision-chain identity pair, wherever the stage's own
        # payload carries it; absent stays NULL (never invented).
        "decision_id": _text(payload.get("decision_id")),
        "gate_request_id": _text(payload.get("gate_request_id")),
        "strategy_id": _text(payload.get("strategy_id")),
        "model_id": _text(payload.get("model_id")),
        "volume": _to_float(payload.get("volume")),
        "stop_loss": _to_float(payload.get("stop_loss")),
        "take_profit": _to_float(payload.get("take_profit")),
        "payload_json": payload_json,
        "decided_at": decided_at,
        "rejection_reason": rejection_reason,
        "recorded_at": recorded_at,
    }


def note_future_stamp(atom, stage: str, decided_at: float, now: float) -> None:
    """ينطق انحراف الساعة بدل ابتلاعه — بخنق دقيقة."""
    if now - atom._last_stamp_log_at < _STAMP_LOG_EVERY_S:
        return
    atom._last_stamp_log_at = now
    context = atom._context
    if context is None or getattr(context, "logger", None) is None:
        return
    try:
        context.logger.warning(
            "707 انحراف ساعة المصدر: مرحلة=%s فرق=%+.0f ثانية (%.2f ساعة)"
            " — الطابع يُخزَّن كما جاء، وساعة الاستلام في recorded_at."
            " مجموع=%d",
            stage, decided_at - now, (decided_at - now) / 3600.0,
            atom.future_stamp_count)
    except Exception:  # noqa: BLE001 — لا يسقط مخزن بسبب سجلّ
        pass


def note_failure(atom, stage: str, reason: str) -> None:
    """القرار الذي لم يُخزَّن يُنطق — لا يُعدّ في صمت.

    مقيس ٢٠٢٦-٠٩-٠٩: `failures=36` في اللقطة وصفر ذكر في
    `var/logs/errors-*.log`. قرارٌ ضائع لا يعرف به أحد أسوأ من قرار فاشل
    معلوم. الخنق دقيقة لأنّ الفشل يتكرّر مع كل حدث حين تسقط القاعدة.
    """
    now = time.monotonic()
    if now - atom._last_failure_log_at < _FAILURE_LOG_EVERY_S:
        return
    atom._last_failure_log_at = now
    context = atom._context
    if context is None or getattr(context, "logger", None) is None:
        return
    try:
        context.logger.error(
            "707 مخزن القرارات: قرار لم يُخزَّن — مرحلة=%s سبب=%s"
            " مجموع الإخفاقات=%d", stage, reason, atom.failure_count)
    except Exception:  # noqa: BLE001 — لا يسقط مخزن بسبب سجلّ
        pass
