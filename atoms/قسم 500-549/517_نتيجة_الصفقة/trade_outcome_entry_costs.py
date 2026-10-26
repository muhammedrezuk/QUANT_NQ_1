"""٥١٧ — عمولة صفقة الدخول: من حدث الفتح أو من صورة المركز، مرّةً واحدة فوق مجموع الأرجل.

٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): نُقلت **حرفيًّا** من `atom.py` (السبب في `trade_outcome_common.py`)
— صفر تغيير في السلوك. `_mirror` و`_on_trade_event` و`_on_positions` و`_try_entry_from_view` كانت طرقًا
في `Atom`: `self` صار الذرّةَ معاملًا أوّل (`atom`)، وبقي في `atom.py` تفويضٌ بالأسماء القديمة (والاشتراكان
في `initialize` عليها). وثوابتها ودوالّها الخاصّة يستوردها `atom.py` باسمها.

لا تنشر هذه الوحدة حدثًا: تكتب حالة المركز في مخزن الذرّة (`reduce_consumer_event`) كما كانت.
"""
from __future__ import annotations

from typing import Any

from shared.financial_scope import text
from trade_outcome_common import COSTS, CONSUMER, LEG_PARTIAL, STATUS_OPEN, _digest, number

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): عمولة صفقة الدخول لم تكن تدخل أيّ نتيجة.
#
# الإكسبرت يكتب حدث الفتح بلا تكاليف (`OPENED` بعمولةٍ فارغة)، وحدثا الإغلاق
# الجزئيّ والكامل يحملان عمولة صفقة الخروج وحدها. فالنتيجة هنا = الربح + عمولات
# الخروج، ونصف الدورة غائب. مقيسٌ على الجسر (قراءة فقط) اليوم: 880 حدث فتح كلّها
# بعمولةٍ فارغة، وعمولات الإغلاق على الذهب −818.00$ على 233.4 لوت (3.50$/لوت)،
# وأحجام الفتح 232.02 لوت ذهب + 0.14 يورو ⟸ نحو 812$ غائبة عن الدفاتر.
#
# ومن أين تُقرأ: عمولة المركز المفتوح في صورة ٦٠٩ (`positions_v2.commission`)
# مجموعُ عمولات صفقاته — وقبل أيّ جزءٍ هي عمولة صفقة الدخول نفسها. مقيس على
# الخطّ الزمنيّ: 254 مركز ذهب من 254 أوّل ظهورها = −3.5 × الحجم بالضبط، و620
# مركزًا لرموزٍ بلا عمولة = صفر. والإكسبرت 3.18 (يصرّفه المالك) يكتبها في حدث
# الفتح نفسه من صفقة الدخول.
#
# فتُضاف عمولة الدخول **مرّةً واحدة** فوق مجموع الأرجل، من أحد مصدرين:
#   ١) حدث الفتح (٦١١) حين يحملها برقمٍ غير صفريّ — الإكسبرت الجديد.
#   ٢) صورة المركز (٦٠٩) حين تثبت أنّ ما فيها دخولٌ وأجزاءٌ مسجَّلة لا غير:
#      حجم الصورة + أحجام الأجزاء المسجَّلة = حجم الفتح ⟸ عمولة الدخول =
#      عمولة الصورة − عمولات الأجزاء المسجَّلة. وإلّا تُنتظر صورةٌ تالية.
# وهي حالةٌ دائمة في المخزن بمعرّفٍ ثابت للمركز، فلا تُضاف مرّتين ولا بعد إقلاع.
# وصفرٌ من صفقة الدخول لا يُعدّ دليلًا (حكم المالك ٢٠٢٦-٠٨-١٦: «الصفر ليس دليلًا
# على غياب التكلفة») — تحسمه صورة المركز. ولا علاقة لها بتقدير ٥٧٧ (ضِعف العمولة
# للدورة): ذاك حارسُ وقفٍ قبل الخروج، وهذه نتيجةٌ من أرقام الوسيط بعده.
# وغيابها لا يجعل النتيجة «مجهولة»: كانت تُحسب بدونها دائمًا، فتُعلن الحقيقة
# في الحمولة (`entry_costs_included`) وفي الشارة بدل أن تُصفَّر الصفقة عند ٥١٦.
ENTRY_FROM_DEAL = "OPENED_DEAL"
ENTRY_FROM_POSITION = "POSITION_SNAPSHOT"
_VOL_EPS = 1e-6


class _EntryNotProven(Exception):
    """الصورة لا تثبت عمولة الدخول الآن — يُلغى القيد ولا يُستهلك معرّفه."""


def _key_volume(key: str) -> float | None:
    """حجم الرِّجل من مفتاحها (`النوع|الحجم|الخروج|الربح`) — لأرجلٍ سُجّلت بلا حقل حجم."""
    parts = str(key).split("|")
    return number(parts[1]) if len(parts) > 1 and parts[1] != "?" else None


def _entry_basis(state: dict[str, Any]) -> tuple[float, float, float] | None:
    """(حجم الفتح · أحجام الأجزاء المسجَّلة · عمولاتها) لمركزٍ ينتظر عمولة دخوله.

    `None` حين لا يُشتقّ شيء: عمولةٌ معروفة سلفًا، أو فتحٌ لم يُرَ، أو مركزٌ
    أُغلق، أو جزءٌ مجهول الحجم أو العمولة (لا يُطرح المجهول من صورةٍ معلومة).
    """
    opened = number(state.get("open_volume"))
    if (opened is None or opened <= 0.0 or isinstance(state.get("entry"), dict)
            or state.get("closed") or state.get("status") in {"COMPLETE", "INCOMPLETE"}):
        return None
    volume = commission = 0.0
    legs = state.get("legs") if isinstance(state.get("legs"), dict) else {}
    for key, leg in legs.items():
        if not isinstance(leg, dict) or leg.get("event_type") != LEG_PARTIAL:
            return None
        size = number(leg.get("volume"))
        size = size if size is not None else _key_volume(key)
        cost = number(leg.get("commission"))
        if size is None or cost is None:
            return None
        volume += size
        commission += cost
    return opened, volume, commission


def mirror(atom, scope: str, state: dict[str, Any]) -> None:
    """يُبقي في الذاكرة ما يلزم لاشتقاق عمولة الدخول من صورة المركز."""
    basis = _entry_basis(state) if isinstance(state, dict) else None
    if basis is None:
        atom._awaiting_entry.pop(scope, None)
    else:
        atom._awaiting_entry[scope] = basis


async def on_trade_event(atom, payload: dict[str, Any]) -> None:
    """حدث الفتح من ٦١١: حجمُ الفتح دائمًا، وعمولةُ صفقة الدخول إن حملها.

    الإكسبرت حتى 3.17 يكتبها فارغة، فيبقى الحجم وحده — به تُقرأ صورة
    المركز. والإكسبرت 3.18 يكتبها من صفقة الدخول نفسها. والصفر لا يُثبت
    شيئًا (حكم المالك ٢٠٢٦-٠٨-١٦)، فيُترك لصورة المركز تحسمه.
    """
    if not atom._running or not isinstance(payload, dict):
        return
    if text(payload.get("event_type")).upper() != "OPENED":
        return
    account = text(payload.get("account_id"))
    broker = text(payload.get("broker")) or atom._brokers.get(account, "")
    trade = text(payload.get("ticket"))
    row = text(payload.get("source_row_id") or payload.get("event_id"))
    volume = number(payload.get("volume"))
    if not account or not broker or not trade or not row or volume is None or volume <= 0.0:
        return
    if atom._journal is None or atom._storage_error:
        return
    scope = account + "|" + broker + "|" + trade
    costs = {name: number(payload.get(name)) for name in COSTS}
    deal_commission = costs["commission"]
    late: list[bool] = []

    def reduce(current: dict[str, Any]):
        if current.get("status") in {"COMPLETE", "INCOMPLETE"}:
            # النتيجة نُشرت قبل أن يصل الفتح: لا تُنشر صفقةٌ ثانية بعمولةٍ
            # وحدها (تُعدّ عند ٥١٦ خسارةً وصفقة)، بل تُحفظ وتُعدّ ظاهرةً.
            if (deal_commission is not None and deal_commission != 0.0
                    and not isinstance(current.get("entry"), dict)
                    and "entry_after_result" not in current):
                current["entry_after_result"] = {**costs, "source": ENTRY_FROM_DEAL}
                late.append(True)
            return current, []
        if not isinstance(current.get("legs"), dict):
            atom._adopt_legacy(current)
        if number(current.get("open_volume")) is None:
            current["open_volume"] = volume
        if (not isinstance(current.get("entry"), dict)
                and deal_commission is not None and deal_commission != 0.0):
            current["entry"] = {"commission": deal_commission, "swap": costs["swap"],
                                "fee": costs["fee"], "source": ENTRY_FROM_DEAL}
        if not current.get("status"):
            current["status"] = STATUS_OPEN
        if current.get("legs"):
            atom._sum_legs(current)
        return current, []

    initial = {"status": STATUS_OPEN, "legs": {}, "account_id": account,
               "broker": broker, "trade_identity": trade}
    try:
        fresh, state = atom._journal.reduce_consumer_event(
            "opened:" + _digest(account + "|" + row), account, "POSITION_OPENED",
            trade, payload, CONSUMER, scope, initial, reduce)
    except Exception as exc:
        atom._storage_error = type(exc).__name__
        return
    if not fresh:
        return
    if late:
        atom._entry_late += 1
    if state.get("status") == STATUS_OPEN:
        atom._open.add(scope)
    atom._mirror(scope, state)
    await atom._try_entry_from_view(scope)


async def on_positions(atom, payload: dict[str, Any]) -> None:
    """صورة ٦٠٩: عمولة المركز المفتوح = عمولة صفقة الدخول + عمولات أجزائه."""
    if not atom._running or not isinstance(payload, dict):
        return
    rows = payload.get("positions")
    if not isinstance(rows, list):
        return
    owner = text(payload.get("account_id"))
    owner_broker = text(payload.get("broker")) or atom._brokers.get(owner, "")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        account = text(row.get("account_id")) or owner
        broker = text(row.get("broker")) or owner_broker or atom._brokers.get(account, "")
        trade = text(row.get("ticket"))
        volume = number(row.get("volume"))
        commission = number(row.get("commission"))
        status = row.get("commission_status")
        if (not account or not broker or not trade or volume is None or commission is None
                or status not in (None, "AVAILABLE")):
            continue
        scope = account + "|" + broker + "|" + trade
        seen.add(scope)
        atom._position_view[scope] = (volume, commission)
        if scope in atom._awaiting_entry:
            await atom._try_entry_from_view(scope)
    if owner and owner_broker:
        prefix = owner + "|" + owner_broker + "|"
        for scope in [s for s in atom._position_view if s.startswith(prefix) and s not in seen]:
            atom._position_view.pop(scope, None)


async def try_entry_from_view(atom, scope: str) -> None:
    basis = atom._awaiting_entry.get(scope)
    view = atom._position_view.get(scope)
    if basis is None or view is None or atom._journal is None or atom._storage_error:
        return
    volume, commission = view
    if abs(volume + basis[1] - basis[0]) > _VOL_EPS:
        return          # صورةٌ قبل جزءٍ لم يُسجَّل بعد، أو بعده — تُنتظر التالية

    def reduce(current: dict[str, Any]):
        # يُعاد الفحص على الحالة الدائمة نفسها داخل المعاملة: ما في الذاكرة دليلٌ لا حكم.
        proof = _entry_basis(current)
        if proof is None or abs(volume + proof[1] - proof[0]) > _VOL_EPS:
            raise _EntryNotProven()
        current["entry"] = {"commission": round(commission - proof[2], 8), "swap": None,
                            "fee": None, "source": ENTRY_FROM_POSITION,
                            "position_volume": volume, "position_commission": commission}
        if current.get("legs"):
            atom._sum_legs(current)
        return current, []

    account = scope.split("|", 1)[0]
    try:
        fresh, state = atom._journal.reduce_consumer_event(
            "entry-position:" + _digest(scope), account, "ENTRY_COMMISSION", scope,
            {"volume": volume, "commission": commission}, CONSUMER, scope, {}, reduce)
    except _EntryNotProven:
        return
    except Exception as exc:
        atom._storage_error = type(exc).__name__
        return
    atom._mirror(scope, state)
