"""٥٧٧ — حارسا ما بعد التنفيذ (٢٠٢٦-١٠-٢٦، ختم المالك «NQ» على إصلاح فحص المشروع، البندان ٧ و٩).

١· **تضييقٌ ردّه الوسيط يُعاد.** كانت الذرّة تعلّم التذكرة «قُصّت» (`_capped`) لحظة الإرسال ولا تسمع ردّه، وأمرُها يذهب إلى
   ٥٧٥ مباشرةً فلا تشمله إعادات ٥٧٠، والعلامة تُحفظ في اللقطة — فتضييقٌ واحدٌ مردود يترك المركز فوق سقف المالك ما عاش.
   الآن يخرج كلّ تضييقٍ بمعرّفه (`riskcap-…`)، وتُسمع نتيجته من ٦٠١ (الجسر) ومن ٥٧٥ (ما لم يُكتب). فإن فشل رُفعت العلامة بعد
   مهلةٍ تتضاعف (٢ ثمّ ٤ ثمّ ٨ … حتّى ٣٠٠ ث، كإعادة الإغلاق في ٥٧٠) فيُعاد **الحساب** على السعر الحاضر — لا الأمرُ القديم —
   ويمرّ بحارس الجهة كما مرّ أوّل مرّة. وحدُّه عشرون محاولة لكلّ تذكرة (كأوامر الإغلاق)، ثمّ يُعلَن الإسقاط ولا يُبتلع.
٢· **مركزٌ للمنظومة بلا وقف يُعلَن.** كانت `_cap_risk` تخرج صامتةً حين لا وقف. الآن يُكتب في سجلّ الأخطاء مرّةً لكلّ تذكرة،
   ويُعلَن في الشارة ما دام قائمًا. لا يُغلق ولا يُوضع له وقفٌ هنا: الإعلانُ هو المطلوب، والفعلُ قرار المالك. ومركز المالك
   اليدويّ (سحرٌ غير سحر المنظومة) لا يُعلَن.
٣· **ردُّ «ليس للمنظومة» نهائيّ** (٢٠٢٦-١٠-٢٦، قانون صفقات المالك بختم «NQ»: «صفقات انا بفتحها مالها علاقة بل منظومة ابدا»).
   كان ردُّ ٥٧٥ `MISSING_OR_FOREIGN_MAGIC` يُعامل كأيّ ردٍّ عابر فيُعاد التضييق حتّى عشرين مرّة — ستّ عشرة محاولة على صفقتَي
   المالك اليدويّتين في ثماني عشرة دقيقة اليوم. الآن ردُّ السحر الغريب أو الملكيّة غير المطابقة (من ٥٧٥ أو من الخبير) على أمرٍ
   حمل سحرًا معروفًا ليس للمنظومة نهائيّ: لا موعد إعادة ولا حساب جديد على التذكرة ما دامت قائمة، ويُعدّ ويُكتب مرّةً واحدة.
   والتمييز نفسه في `shared/owner_trades.py`، وصفقات المالك تُسقط قبل أن تبلغ هذا الملفّ أصلًا (`atom._on_positions`) — فهذا
   حارسٌ أخير. والردّ نفسه على مركزٍ للمنظومة (سحرها، أو بلا سحر) يُعاد كما كان، فلا يُطفأ سقف خسارته (نقض ٢٦/١٠).
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from stop_maintenance_checks import _norm_side, _to_float, _to_int
from shared import owner_trades

EVENT_FAILED = "execution.command.failed"
EVENT_ACK = "execution.command.ack"
REQUEST_PREFIX = "riskcap"
#: حدُّ المحاولات ومهلتها القصوى — مرآةُ إعادة الإغلاق في ٥٧٠ (`MAX_RETRY_CLOSE` و`min(2**n, 300)`).
MAX_ATTEMPTS = 20
MAX_WAIT_S = 300.0
BACKOFF_BASE = 2.0
#: سحر المنظومة — من التمييز الواحد (`magic` في الإعداد يعلوه إن وُجد).
DEFAULT_MAGIC = owner_trades.SYSTEM_MAGIC
#: ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك): ردودٌ تقول إنّ المركز ليس للمنظومة — نهائيّة لا تُعاد. من ٥٧٥ (`575/atom.py:380` و`:310`)
#: ومن الخبير (`mt5/QUANT_NQ.mq5:1240`).
FINAL_REFUSALS = ("MISSING_OR_FOREIGN_MAGIC", "POSITION_OWNERSHIP_MISMATCH", "COMMAND_OWNERSHIP_MISMATCH")


def ensure(atom: Any) -> None:
    if hasattr(atom, "_cap_pending"):
        return
    atom._cap_pending = {}          # معرّف التضييق ⟵ التذكرة
    atom._cap_attempts = {}         # التذكرة ⟵ محاولاتها المرسلة منذ آخر نجاح
    atom._cap_retry_at = {}         # التذكرة ⟵ موعد رفع العلامة (ساعة الجدار، فتُحفظ عبر الإقلاع)
    atom._cap_refused = atom._cap_retried = atom._cap_abandoned = atom._cap_foreign = 0
    atom._last_cap_refusal = "-"
    atom._unprotected = {}          # التذكرة ⟵ وصفها، ما دامت بلا وقف
    atom._unprotected_seen = 0
    atom._last_unprotected = "-"
    atom._magic = DEFAULT_MAGIC
    atom._cap_final = {}            # التذكرة ⟵ ردُّ «ليس للمنظومة» الذي أنهى أمرها (لا يُعاد)
    atom._cap_final_seen = 0


def subscribe(atom: Any, context: Any) -> None:
    ensure(atom)
    atom._magic = int(context.config.get("magic", DEFAULT_MAGIC))

    async def _failed(payload: Any) -> None:
        await on_failed(atom, payload)

    async def _ack(payload: Any) -> None:
        await on_ack(atom, payload)

    context.subscribe(EVENT_FAILED, _failed)
    context.subscribe(EVENT_ACK, _ack)


def sent(atom: Any, ticket: int) -> str:
    """معرّف التضييق الذي يخرج الآن — ويُعدّ محاولةً للتذكرة."""
    ensure(atom)
    request_id = "%s-%d-%s" % (REQUEST_PREFIX, ticket, uuid.uuid4().hex[:12])
    atom._cap_pending[request_id] = ticket
    atom._cap_attempts[ticket] = atom._cap_attempts.get(ticket, 0) + 1
    atom._cap_retry_at.pop(ticket, None)
    return request_id


async def on_failed(atom: Any, payload: Any) -> None:
    ensure(atom)
    if not isinstance(payload, dict):
        return
    ticket = atom._cap_pending.pop(str(payload.get("request_id") or ""), None)
    if ticket is None:
        atom._cap_foreign += 1      # نتيجةُ أمرٍ ليس من تضييقات هذه الذرّة
        return
    atom._cap_refused += 1
    tries = atom._cap_attempts.get(ticket, 0)
    reason = str(payload.get("reason") or payload.get("result") or "-")
    atom._last_cap_refusal = "tk=%s %s (محاولة %d من %d)" % (ticket, reason, tries, MAX_ATTEMPTS)
    if any(code in reason.upper() for code in FINAL_REFUSALS) and owner_trades.is_owner(payload, atom._magic):
        # ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك): الأمر المردود حمل سحرًا معروفًا ليس للمنظومة ⟸ ردٌّ نهائيّ، لا موعد إعادة،
        # وعلامة القصّ تبقى. أمّا مركز المنظومة (سحرها، أو بلا سحر) فيُعاد كأيّ ردّ — لا يُطفأ سقف خسارته بردٍّ واحد.
        atom._cap_retry_at.pop(ticket, None)
        if ticket not in atom._cap_final:
            atom._cap_final[ticket] = reason
            atom._cap_final_seen += 1
            if atom._context is not None:
                atom._context.logger.warning(
                    "577 التذكرة %s ليست للمنظومة (%s) — ردٌّ نهائيّ، لا يُعاد تضييقها", ticket, reason)
        return
    if tries >= MAX_ATTEMPTS:
        atom._cap_abandoned += 1
        atom._cap_retry_at.pop(ticket, None)
        if atom._context is not None:
            atom._context.logger.error(
                "577 🔴 تضييق الوقف رُدّ %d مرّة — التذكرة %s باقيةٌ فوق سقف الخسارة (%s)", tries, ticket, reason)
        return
    atom._cap_retry_at[ticket] = time.time() + min(BACKOFF_BASE ** tries, MAX_WAIT_S)


async def on_ack(atom: Any, payload: Any) -> None:
    ensure(atom)
    if not isinstance(payload, dict):
        return
    ticket = atom._cap_pending.pop(str(payload.get("request_id") or payload.get("command_id") or ""), None)
    if ticket is None:
        atom._cap_foreign += 1
        return
    atom._cap_attempts.pop(ticket, None)
    atom._cap_retry_at.pop(ticket, None)


def refused_for_good(atom: Any, ticket: Any) -> bool:
    """٢٠٢٦-١٠-٢٦ (قانون صفقات المالك): تذكرةٌ ردّها الوسيط بأنّها ليست للمنظومة ⟸ لا حساب ولا أمر عليها ما دامت قائمة."""
    ensure(atom)
    return ticket is not None and ticket in atom._cap_final


def retry_due(atom: Any, ticket: int) -> bool:
    """تضييقٌ رُدّ وحلّ موعد إعادته ⟸ تُرفع علامة القصّ، فيُعاد الحساب على السعر الحاضر."""
    ensure(atom)
    if ticket in atom._cap_final:
        return False
    at = atom._cap_retry_at.get(ticket)
    if at is None or time.time() < at:
        return False
    atom._cap_retry_at.pop(ticket, None)
    atom._capped.discard(ticket)
    atom._cap_retried += 1
    return True


def note_unprotected(atom: Any, pos: dict[str, Any]) -> None:
    """مركزٌ للمنظومة بلا وقف ⟸ يُعلَن مرّةً لكلّ تذكرة، ويبقى في الشارة حتّى يعود وقفه أو يُغلق."""
    ensure(atom)
    ticket = _to_int(pos.get("ticket"))
    if ticket is None or "stop_loss" not in pos:
        return                      # صفٌّ لا يحمل حقل الوقف أصلًا ليس صورة مركز (٦٠٩ يحمله دائمًا)
    stop = _to_float(pos.get("stop_loss"))
    if stop is not None and stop > 0.0:
        atom._unprotected.pop(ticket, None)
        return
    if owner_trades.is_owner(pos, atom._magic) or ticket in atom._unprotected:
        return
    desc = "%s %s %s tk=%s" % (pos.get("symbol"), _norm_side(pos.get("side")) or "?", pos.get("volume"), ticket)
    atom._unprotected[ticket] = desc
    atom._unprotected_seen += 1
    atom._last_unprotected = desc
    if atom._context is not None:
        atom._context.logger.error(
            "577 ⛔ مركزٌ للمنظومة بلا وقف: %s — لا وقف يحميه عند الوسيط، ولا يُغلق هنا (الفعل قرار المالك)", desc)


def prune(atom: Any, live: set[int]) -> None:
    """تذاكر أُغلقت تخرج من كلّ دفتر — كما يُقلَّم `_capped` في الدورة نفسها."""
    ensure(atom)
    for book in (atom._cap_attempts, atom._cap_retry_at, atom._unprotected, atom._cap_final):
        for ticket in [t for t in book if t not in live]:
            del book[ticket]
    atom._cap_pending = {rid: t for rid, t in atom._cap_pending.items() if t in live}


def health_text(atom: Any) -> str:
    ensure(atom)
    return " | قصّ_مردود=%d أُعيد=%d أُسقط=%d ليس_للمنظومة=%d آخره=%s | ⛔ بلا_وقف=%d (منذ الإقلاع %d) %s" % (
        atom._cap_refused, atom._cap_retried, atom._cap_abandoned, atom._cap_final_seen, atom._last_cap_refusal,
        len(atom._unprotected), atom._unprotected_seen, atom._last_unprotected)


def snapshot(atom: Any) -> dict[str, Any]:
    ensure(atom)
    return {"cap_pending": dict(atom._cap_pending),
            "cap_attempts": {str(t): n for t, n in atom._cap_attempts.items()},
            "cap_retry_at": {str(t): at for t, at in atom._cap_retry_at.items()},
            "cap_refused": atom._cap_refused, "cap_retried": atom._cap_retried,
            "cap_abandoned": atom._cap_abandoned,
            "cap_final": {str(t): r for t, r in atom._cap_final.items()}, "cap_final_seen": atom._cap_final_seen}


def restore(atom: Any, state: dict[str, Any]) -> None:
    """المحاولات والمواعيد والمعرّفات المنتظرة تعبر الإقلاع — ونتيجةُ ما كان في الطريق تصل من مؤشّر ٦٠١ الدائم."""
    ensure(atom)
    pending = state.get("cap_pending")
    if isinstance(pending, dict):
        atom._cap_pending = {str(rid): int(t) for rid, t in pending.items() if _to_int(t) is not None}
    for name, book, cast in (("cap_attempts", atom._cap_attempts, int), ("cap_retry_at", atom._cap_retry_at, float)):
        raw = state.get(name)
        if isinstance(raw, dict):
            for ticket, value in raw.items():
                number = _to_float(value)
                if number is not None and str(ticket).lstrip("-").isdigit():
                    book[int(ticket)] = cast(number)
    final = state.get("cap_final")
    if isinstance(final, dict):
        atom._cap_final.update({int(t): str(r) for t, r in final.items() if str(t).lstrip("-").isdigit()})
    for name in ("cap_refused", "cap_retried", "cap_abandoned", "cap_final_seen"):
        value = state.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            setattr(atom, "_" + name, value)
