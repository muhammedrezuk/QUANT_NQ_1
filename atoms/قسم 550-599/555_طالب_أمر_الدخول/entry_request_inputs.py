"""٥٥٥ — مدخلات الحال: النطاق والحساب والطلب الطائر والمراكز والرفض والحجم.

v1.24.1 (٢٠٢٦-١٠-٠١، ختم `Nq`): نُقلت من `atom.py` **حرفيًّا** كي ينزل تحت حدّ
المادة 9 (٤٠٠ سطر فعليّ). كلّ دالّةٍ هنا كانت تابعًا في صنف الذرّة، والفرقُ
الوحيد أنّ `self` صار `atom` — والتوابعُ بأسمائها باقيةٌ في `atom.py` تُحيل إلى
هنا، والاشتراكاتُ في `initialize` لم تتغيّر. و`_REJECT_RETRY_AFTER_S` نُقل كما
هو لأنّ `on_rejected` وحدها تقرؤه، و`atom.py` يستورده باسمه. لا سلوك جديد.
(و`_side_of` باقيةٌ في `atom.py` عمدًا: اختبار الذرّة يقرؤها هناك نصًّا.)
"""
from __future__ import annotations

import time
from typing import Any

from entry_request_sizing import _size_view, _text
from shared import owner_trades

#: مهلةُ إعادة المحاولة بعد رفضٍ — مشتقّة من عمر صلاحيّة المرجع عند ٥٢١
#: (`max_data_age_s = 5`) لا مخترَعة: أقصرُ منها يطلب على سعرٍ لم يتجدّد،
#: وأطولُ منها يفوّت نافذة التدفّق المقيسة (عشر ثوانٍ).
_REJECT_RETRY_AFTER_S = 5.0


def scope(atom, payload: dict[str, Any]) -> str:
    account = _text(payload.get("account_id"))
    broker = _text(payload.get("broker")) or atom._brokers.get(account, "")
    symbol = _text(payload.get("symbol"))
    return "\x1f".join((account, broker, symbol))


async def on_account(atom, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        return
    account = _text(payload.get("account_id"))
    broker = _text(payload.get("broker"))
    if account and broker:
        atom._brokers[account] = broker


def inflight_for(atom, symbol: str) -> int:
    """طلبٌ أُرسل ولم يظهر أثره بعد — يُعدّ مركزًا حتى يُعرف مصيره."""
    at = atom._inflight.get(symbol)
    if at is None:
        return 0
    if time.monotonic() - at > atom._inflight_ttl_s:
        del atom._inflight[symbol]
        return 0
    return 1


async def on_positions(atom, payload: dict[str, Any]) -> None:
    """عدّ المراكز المفتوحة لكل رمز — لا حكم، عدّ فقط.

    ٢٠٢٦-١٠-٢٣ (ورقة «خطوط حمراء» المختومة، القانون 13 «التحوّط ممنوعٌ بكلّ أشكاله»): العدّ **لكلّ حساب** ومعه جهة كلّ مركز.
    كان `_open_counts` يُستبدل كاملًا بصفوف كلّ حمولة، و٦٠٩ ينشر حمولةً لكلّ حساب (`609/atom.py:262-274`) — فمع حسابين
    يمحو الثاني عدّ الأوّل، ويمرّ دخولٌ على رمزٍ مفتوحٍ في الأوّل، ولو بجهةٍ معاكسة. اليوم حسابٌ واحد، والباب يُغلق قبل الثاني.
    والصفّ بلا حسابٍ معروف يُعدّ على كلّ الحسابات (الاتّجاه الآمن). و`_open_counts` يبقى مجموع الحسابات للرمز.

    ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك وجوابه، ختم «NQ»): العدّ والجهات للمنظومة وحدها. وصفقات المالك تُحفظ وحدها،
    رموزًا لكلّ حساب (`_owner_by_account`)، لغرضٍ واحد تقرؤه `entry_request_lines.owner_on`: لا دخول على رمزٍ عليه صفقةٌ للمالك.
    """
    if not isinstance(payload, dict):
        return
    rows = payload.get("positions")
    if not isinstance(rows, list):
        return
    account = _text(payload.get("account_id"))
    counts: dict[str, dict[str, int]] = {}
    sides: dict[str, dict[str, set[str]]] = {}
    owners: dict[str, dict[str, int]] = {}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = _text(row.get("symbol"))
        if symbol and owner_trades.is_owner(row):
            mine = owners.setdefault(_text(row.get("account_id")) or account, {})
            mine[symbol] = mine.get(symbol, 0) + 1
            continue
        if symbol:
            owner = _text(row.get("account_id")) or account
            mine = counts.setdefault(owner, {})
            mine[symbol] = mine.get(symbol, 0) + 1
            sides.setdefault(owner, {}).setdefault(symbol, set()).add(_text(row.get("side")).upper())
            seen.add(symbol)
    by_owner = getattr(atom, "_owner_by_account", None)
    if by_owner is None:
        by_owner = atom._owner_by_account = {}
    if account:
        atom._open_by_account[account] = counts.get(account, {})
        atom._sides_by_account[account] = sides.get(account, {})
        by_owner[account] = owners.get(account, {})
    else:
        atom._open_by_account = counts
        atom._sides_by_account = sides
        atom._owner_by_account = owners
    totals: dict[str, int] = {}
    for per_symbol in atom._open_by_account.values():
        for symbol, count in per_symbol.items():
            totals[symbol] = totals.get(symbol, 0) + count
    atom._open_counts = totals
    atom._positions_seen = True
    for seen_symbol in seen:
        atom._inflight.pop(seen_symbol, None)


def cooldown(previous: float | None, now: float, cooldown_s: float) -> dict[str, Any] | None:
    """مهلة الدخول على (حساب × رمز) — نُقلت من `atom.py` حرفيًّا في 1.28.0 (حدّ الأربع مئة سطر): تفاصيل الردّ إن لم تنقضِ
    المهلة منذ الطلب السابق، وإلّا لا شيء. الحكم والأرقام كما كانت."""
    if previous is None:
        return None
    elapsed = now - float(previous)
    if elapsed >= cooldown_s:
        return None
    return {"cooldown_s": cooldown_s,
            "elapsed_s": max(0.0, round(elapsed, 6)),
            "remaining_s": max(0.0, round(cooldown_s - elapsed, 6))}


#: جهة القرار ⟵ الجهة المعاكسة كما يكتبها ٦٠٩ في صفّ المركز.
_OPPOSITE = {"buy": "SELL", "sell": "BUY"}


def held_for(atom, account: str, symbol: str) -> int:
    """مراكز هذا الحساب على الرمز، ومعها كلّ صفٍّ بلا حسابٍ معروف."""
    by_account = atom._open_by_account
    return by_account.get(account, {}).get(symbol, 0) + (by_account.get("", {}).get(symbol, 0) if account else 0)


def hedge_elsewhere(atom, account: str, symbol: str, side: str) -> str:
    """الحساب الآخر الذي يحمل على الرمز نفسه مركزًا معاكسًا لهذه الجهة، أو "" — القانون 13."""
    opposite = _OPPOSITE.get(_text(side).lower())
    for other, per_symbol in atom._sides_by_account.items():
        if other != account and opposite in per_symbol.get(symbol, set()):
            return other or "?"
    return ""


async def on_rejected(atom, payload: dict[str, Any]) -> None:
    """أمرٌ رُفض ⇒ لا مركزَ في الطريق ⇒ يُحرَّر الرمز فورًا.

    ٢٠٢٦-٠٩-١٦ — المقيس: `_inflight` كان يُمسح بشيئين فقط، ظهورِ
    مركزٍ مفتوح أو انقضاءِ `inflight_ttl_s = 90`. والأمرُ المرفوض لا
    يصير مركزًا أبدًا، فيقعد الرمز **تسعين ثانية** على فشلٍ معروف
    مصيرُه من الثانية الأولى.

    وكلفةُ ذلك في السوق الحيّ أنّ المحاولة تفوت نافذتها: السعر
    المرجعيّ يعيش خمس ثوانٍ، والتغذية تصمت دقائق ثمّ تتدفّق **عشر
    ثوانٍ** (مقيس ٢٣:٠٤:٥١–٢٣:٠٥:٠١، والأعمار قبلها ١٨٠–٤٦٥ث). فمحاولةٌ
    كل تسعين ثانية أمام نافذةٍ من عشر لا تكاد تصيبها — والنتيجة
    المقيسة يومها **٢٨٥ أمرًا وصفر تنفيذ**.

    و٥٥٥ كان الوحيد الذي يحتاج هذا الحدث ولا يسمعه: ثلاث عشرة ذرّة
    تشترك في `execution.order.rejected` — ٥١٦ و٥١٨ و٥٠٨ و٥٥٠ و٥٦٠
    و٥٧٩ و٥٨٥ وغيرها — وهو خارجها وحده، وهو صاحب الحارس.

    ولا يغيّر هذا حكمًا ولا عتبة: الرفض يبقى رفضًا، والسعر البائت
    يبقى مرفوضًا عند ٥٥٢، والمحاولة التالية تمرّ بالبوّابات كلّها من
    أوّلها. المحرَّر هو **حقّ إعادة المحاولة** لا شرطُ القبول.
    """
    if not atom._running or not isinstance(payload, dict):
        return
    # الرمز قد يتبدّل بين الطلب والأمر (٥٨٦ بوّابة الرموز تحلّه إلى
    # رمز الوسيط)، فيُحرَّر بكل أسمائه — ومسحُ مفتاحٍ غائب لا أثر له.
    # ولا يُحرَّر إلى الصفر بل إلى **عمر صلاحيّة المرجع** (خمس ثوانٍ،
    # عتبة ٥٢١ نفسها): لا معنى لإعادة المحاولة قبل أن يتسنّى للسعر أن
    # يتجدّد، والنواة مشبعة فكلّ طلبٍ زائد حملٌ على طابورٍ يفيض.
    # والتنفيذ بتقديم طابع الإرسال حتى يبقى من مهلته هذا القدر — فلا
    # بنية جديدة ولا مسار ثانٍ للانتهاء.
    floor = time.monotonic() - atom._inflight_ttl_s + _REJECT_RETRY_AFTER_S
    cleared = False
    for field in ("symbol", "logical_symbol", "asset_canonical",
                  "broker_symbol"):
        name = _text(payload.get(field))
        at = atom._inflight.get(name) if name else None
        if at is not None and at > floor:
            atom._inflight[name] = floor
            cleared = True
    if cleared:
        atom._inflight_cleared += 1
        atom._last_reason = "INFLIGHT_CLEARED_ON_REJECT:%s" % _text(
            payload.get("reason"))


async def on_size(atom, payload: dict[str, Any]) -> None:
    if not atom._running or not isinstance(payload, dict):
        return
    atom._sizes[atom._scope(payload)] = {"payload": _size_view(payload),
                                         "at": time.monotonic()}


# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): الإيقاف لكلّ حساب، لا مفتاحٌ عامّ واحد.
#
# كان `_on_halt` يضع `_halted = True` لأيّ حمولة، و`_on_reset` يرفعه لأيّ حمولة —
# فإفراجُ حسابٍ واحد (ومنه محاذاة الإقلاع `BOOT_ALIGN` التي ينشرها 516 لكلّ دفترٍ
# غير موقوف) يفكّ إيقاف حسابٍ آخر (تدقيق 2026-10-02 م2). الدلالة الآن دلالة 552
# (`552/atom.py:155-175`) مع العقد المشترك لهذا اليوم:
#   • إيقافٌ بلا `account_id` أو بـ`scope == "SYSTEM"` ⟸ كلّ الحسابات، ومعها كلّ
#     حسابٍ يظهر بعده، حتّى تحريرٍ صريح بلا حساب.
#   • إيقافٌ بحساب ⟸ ذلك الحساب وحده.
#   • تحريرٌ بحساب ⟸ يرفع إيقاف ذلك الحساب وحده، **ولا يرفع الإيقاف العامّ**
#     (وإلّا عاد العطب نفسه من بابٍ آخر: محاذاة إقلاعٍ لحسابٍ تفكّ إيقافًا عامًّا).
#   • تحريرٌ بلا حساب (أو `SYSTEM`) ⟸ يرفع كلّ شيء.
#   • حمولةُ إيقافٍ مشوّهة ⟸ كلّ الحسابات (الاتّجاه الآمن)، وتحريرٌ مشوّه ⟸ لا شيء.
def _is_system_scope(payload: dict[str, Any]) -> bool:
    return (not _text(payload.get("account_id"))
            or _text(payload.get("scope")).upper() == "SYSTEM")


async def on_halt(atom, payload: Any) -> None:
    if not isinstance(payload, dict) or _is_system_scope(payload):
        atom._halt_all = True
        return
    atom._halted_accounts.add(_text(payload.get("account_id")))


async def on_reset(atom, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    # ٢٠٢٦-١٠-٠٢ v1.25.1: الإيقاف الموروث من لقطةٍ قديمة يفكّه أيّ تحرير، كما كان قبل 1.25.0.
    atom._halt_legacy = False
    if _is_system_scope(payload):
        atom._halt_all = False
        atom._halted_accounts.clear()
        return
    atom._halted_accounts.discard(_text(payload.get("account_id")))


def halted_for(atom, account: str) -> bool:
    """هل هذا الحساب موقوف؟ حسابٌ مجهول يُعدّ موقوفًا متى وُجد أيّ إيقاف."""
    if atom._halt_all or getattr(atom, "_halt_legacy", False):
        return True
    if not account:
        return bool(atom._halted_accounts)
    return account in atom._halted_accounts
