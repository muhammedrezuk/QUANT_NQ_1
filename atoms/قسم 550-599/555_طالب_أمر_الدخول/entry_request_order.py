"""٥٥٥ — جسد `execution.order.requested`: الحقول والتقريب ونقلُ سلسلة الهويّة.

v1.24.1 (٢٠٢٦-١٠-٠١، ختم `Nq`): نُقل هذا المقطع من `_on_decision` في `atom.py`
**حرفيًّا** كي ينزل تحت حدّ المادة 9 (٤٠٠ سطر فعليّ): القاموسُ وحلقةُ نقل الهويّة
كما كانا، والمتغيّراتُ المحلّيّة نفسها تصل بأسمائها وسيطاتٍ مسمّاة. ونداؤه في
الموضع نفسه من `_on_decision` (بعد مهلة الدخول وقبل النشر)، والنشرُ نفسه باقٍ في
`atom.py` — هذا الملفّ يبني الجسد ولا ينشر شيئًا. والثوابتُ الأربعة لا يقرؤها
غيرُ هذا الجسد، و`atom.py` يستوردها بأسمائها.
"""
from __future__ import annotations

from typing import Any

from entry_request_sizing import _number

ACTION_OPEN = "OPEN"
PROTECTION_STOP_TARGET = "STOP_TARGET"
ORIGIN = "entry-555"
PRICE_DP = 8


def build_request(*, request_id: str, account: str, broker: str, symbol: str,
                  side: str, volume: float, price: float | None, stop: float,
                  take_profit: float | None, target_source: Any,
                  size: dict[str, Any], setup_id: Any, stop_source: Any,
                  setup: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """جسد الطلب من محلّيّات `_on_decision` كما هي — لا حقل يُشتقّ هنا ولا يُحذف."""
    request = {
        "request_id": request_id, "account_id": account, "broker": broker,
        "action": ACTION_OPEN, "symbol": symbol, "side": side,
        "volume": volume,
        "reference_price": round(price, PRICE_DP) if price is not None else None,
        "stop_loss": round(stop, PRICE_DP),
        "take_profit": round(take_profit, PRICE_DP) if take_profit else None,
        "target_source": target_source,
        "origin": ORIGIN, "attempt": 1,
        "protection_mode": PROTECTION_STOP_TARGET,
        "purpose": "ENTRY",
        "risk_budget": _number(size.get("max_trade_loss")),
        # هويّة الإعداد ونسب الأرقام تعبر مع الأمر — ٥٥١ يمرّرها
        # في `_DIRECT_FIELDS`، فيُعرف من أين جاء كل مستوى.
        "setup_id": setup_id,
        "invalidation_source": stop_source,
        "analysis_invalidation": (stop if stop_source != "FALLBACK_513" else None),
        "analysis_target": (take_profit if setup is not None else None),
    }
    # 🔴 ٢٠٢٦-٠٩-١٨ — `decision_side` يُمرَّر كما ورد، لا يُشتقّ.
    #
    # هذه الذرّة تقرؤه (السطر ٢٢١) وتحوّله إلى `side` ثمّ **تستهلكه**،
    # فلا يبقى في الطلب أثرٌ لما قرّره التحليل. ومقيسٌ عند جلسة ٤٠٠–٤٥٠:
    # ٢٦٣ أمرًا في دفتر الطلبات ولا واحدٌ يحمله — فلا يمكن إثبات ولا نفي
    # أنّ الأمر خرج بعكس القرار. وبطاقة ذهبٍ عندي أرَتْ ذلك حرفًا:
    # التحليل شراء (`466 side=buy`) والأمر بيع، والتعارض مسجَّل بثلاثة
    # شهود في البطاقة ولا شاهد في الأمر.
    #
    # ولا حقل يُبتكر ولا اسم يتغيّر: ٤٦٧ ينشره على `decision.gate.passed`
    # (سطر ١٢٩) وهو المدخل نفسه الذي تقرؤه هذه الذرّة. يُنقل كما ورد
    # ويبقى `side` كما هو — ومن يقرأ الاثنين يرى التطابق أو الانقلاب.
    # (نمط `decision_side`/`side` الذي كلّف عشرة قرارات في ٢٠٢٦-٠٩-٠٩:
    #  اسمان لشيءٍ واحد، والدواء تمريرُ كليهما لا اختيارُ أحدهما.)
    for field in ("decision_id", "gate_request_id", "parent_decision_id",
                  "owner_command_id", "session_epoch", "cycle_id",
                  "decision_side"):
        if payload.get(field) is not None:
            request[field] = payload[field]
    return request
