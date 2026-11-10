"""٥٧٤ — الإدارة على مستويات التحليل لا على أثلاثٍ حسابيّة.

٢٠٢٦-١٠-٠٥ (ختم المالك «nq اعتمدناها»)، بنصّ ما اعتمده:
  · أوّل مستوىً في الطريق يحقّق 1:3: يُغلق ثلث العقد، والوقف ينتقل إلى الدخول.
  · المستوى التالي: يُغلق نصف الباقي، والوقف ينتقل إلى المستوى الأوّل.
  · الثلث الأخير يمشي إلى أبعد مستوى (هدف الأمر). ووقفه يتبع كلّ قمّةٍ (للبيع) أو قاعٍ
    (للشراء) جديدٍ مؤكَّد على الربع ساعة — تتبّعٌ بنيويّ لا أرقامٌ ثابتة، ولا يتّسع أبدًا.

المستويات من سلّم البنية نفسه (٢٠١ `structure.levels.state`) وبالقاعدة نفسها التي اختارت
الهدف (`StructureBook.exit_levels`): كلٌّ بنسبة 1:3 فأكثر بعد الكلفة، ولا يُعدّ جديدًا ما لم
يبعد عن سابقه مسافة الوقف. وتُحسب **مرّةً** لكلّ تذكرة بالمستويات المؤكَّدة لحظة أوّل رؤيةٍ
لها، وتُحفظ معها في اللقطة — فلا تتبدّل الخطّة تحت صفقةٍ مفتوحة. لا مسارَ جديدًا للأمر: مسار
الأمر يحمل وقفًا وهدفًا واحدًا (٥٥١ ⟵ ٥٥٢ ⟵ ٦٠١)، والمستويات تُستخرج هنا من البنية نفسها.

ما لا مستوىً وسيطًا له (الهدف نفسه أوّل ما يحقّق 1:3) يبقى على الأثلاث كما كان — لا
يتغيّر شيءٌ لم يُقرَّر.

كلُّ دالّةٍ تأخذ الذرّة أوّلًا (`atom`) — نسقُ الوحدات الشقيقة في ٥٧٩ و٧٠٧.
"""
from __future__ import annotations

import time
from typing import Any

from shared.structure_exits import SYMBOLS
import stage_apply
from stage_apply import EVENT_OUT, ACTION_MODIFY, SIDE_BUY, _PRICE_DP, _R_DP

#: الحدث الذي تُعلن فيه التذاكر المُدارة على المستويات — يقرؤه ٥٧٢ فيتنحّى عنها: التعادل
#: فيها عند أوّل مستوى كما اعتمد المالك، لا عند 1R.
EVENT_PLAN = "management.level_plan.state"
#: سببا نقل الوقف — يُنطقان بموضعه كما يراه المالك.
REASON_LOCK_LEVEL = "STOP_LOCKED_AT_LEVEL_1"
REASON_TRAIL = "STOP_TRAIL_STRUCTURE_15M"
#: أقصى مستويين وسيطين: ثلثٌ على الأوّل ونصف الباقي على الثاني، والباقي للهدف.
MAX_MIDDLE = 2
#: كم دورة مراكز تنتظر الخطّةُ سلّمَ البنية وسعرَ ميتاتريدر قبل أن تُحسم «بلا مستويات»
#: (الأثلاث كما كانت) — الرقم نفسه `_PENDING_STOP_CYCLES` في الذرّة (~ثلاثون ثانية):
#: صفقةٌ لا تبقى بلا إدارةٍ لأنّ ٢٠١ لم ينشر.
PLAN_WAIT_CYCLES = 15

#: ٢٠٢٦-١٠-٠٦ 18:3x — **أمّن ثمّ احجز ثمّ تتبّع** بختم المالك «NQ» بعد قوله: «وصل لا ربح دبل ستوب 100 ربح، لا أمن
#: ولا حجز من أرباح» (صفقة 17:25: +89 نقطة ≈ 1.27R والوقف لم يتحرّك، لأنّ أوّل فعلٍ كان عند المحطّة 3R).
#: للرموز هنا بدل خطّة المستويات:
#:   · عند +1R: الوقف إلى التعادل (الدخول مزاحًا بالعمولة) — بلا إغلاق.
#:   · عند +2R: يُغلق ثلث المتبقّي، والوقف إلى +1R بعد أن يُرى الحجم ناقصًا (المسار نفسه `apply_stage`).
#:   · بعدها: الوقف يتبع قيعان/قمم فريم الوقف (الخمس دقائق للناسداك) ولا يتّسع؛ والهدف عند الوسيط سقف الأمر.
#: ويسري على الصفقة المفتوحة: المرحلة تُحسب من مخاطرتها المحفوظة (`risk`) ومن ربحها الآن.
#: ٢٠٢٦-١٠-٠٦ 20:1x — بختم المالك «nq» بعد «صفقة بتكوين جابت 100 دولار ربح بس ما سكّر شي ولا أمّن» (بيع 0.18 على
#: 86,211.69 بلغ 85,550 = +661 نقطة ≈ 1.28R وأوّل فعلٍ عند 84,537 = 3.2R) وبعد شارة الناسداك (قاعٌ أعلى 31,231 والوقف
#: باقٍ 31,207): (١) **والبتكوين والذهب** هنا؛ (٢) **التتبّع من لحظة الدخول** لا بعد +2R — كلّ قاعٍ (للشراء) أو قمّةٍ
#: (للبيع) مؤكَّدةٍ جديدة على فريم وقف الرمز تشدّ الوقف خلفها، ولا يتّسع أبدًا؛ والتعادل والحجز يقعان فوقه إن كانا أضيق.
#: ⛔ ٢٠٢٦-١٠-٠٧ 16:0x — **مطفأ بأمر المالك وختمه «nq»: الأثلاث وحدها على كلّ الرموز** («صفقة 1/3: هدف أوّل نقل
#: وقف على دخول وإغلاق ثلث عقد، هدف ثاني إغلاق نصف باقي من عقد، هدف ثالث خروج — 50 مرّة شرحتها… ثبّتها بكلّ مكان،
#: ما في غيرها… على كل رموز»). مقيس ١٠-٠٦ 20:12 ⟶ ١٠-٠٧ 15:30: التتبّع من الدخول شدّ الوقف فور الفتح فدار الناسداك
#: 79 صفقة (−1,724.83$). يبقى الكود للقياس وحده (`QUANT_NQ_PROTECT_SYMBOLS`)، والافتراض فارغ.
PROTECT_SYMBOLS = frozenset(s.strip().upper() for s in __import__("os").environ.get(
    "QUANT_NQ_PROTECT_SYMBOLS", "").split(",") if s.strip())
#: ⛔ ٢٠٢٦-١٠-٠٧ — وخطّة المستويات (٥-١٠) **مطفأة** بالأمر نفسه: الأثلاث من مسافة الهدف لا من مستوياتٍ في الطريق.
#: `QUANT_NQ_LEVEL_PLAN=on` يعيدها للقياس وحده.
LEVEL_PLAN_ON = __import__("os").environ.get("QUANT_NQ_LEVEL_PLAN", "off").strip().lower() == "on"


def protected(symbol: Any) -> bool:
    return str(symbol or "").strip().upper() in PROTECT_SYMBOLS
PROTECT_BE_R = 1.0
PROTECT_LOCK_R = 2.0
REASON_PROTECT_BE = "BREAKEVEN_AT_1R"
REASON_PROTECT_LOCK = "STOP_LOCKED_AT_1R"


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def ensure_plan(atom: Any, st: dict[str, Any], symbol: Any, side: str,
                entry: float, stop: float | None, target: float | None,
                account: Any) -> bool:
    """يحسب المستويات الوسيطة مرّةً للتذكرة. `True` حين حُسمت (بخطّةٍ أو بلا خطّة)."""
    if st.get("levels") is not None:
        return True
    if not LEVEL_PLAN_ON:
        st["levels"] = []       # ١٠-٠٧: الأثلاث وحدها — لا خطّة مستويات ولا انتظار سلّم
        return True
    name = str(symbol or "").strip().upper()
    if name not in SYMBOLS or not stop or not target or st.get("stage", 0) > 0:
        # رمزٌ بلا بنية، أو صفقةٌ بدأت مراحلها على الأثلاث قبل الخطّة — لا خلط بين خطّتين.
        st["levels"] = []
        return True
    quote = atom._quotes.get((str(account or "").strip(), name))
    if quote is None or not atom._book.ladders_seen:
        # يُعاد مع الدورة التالية: لا خطّة على سلّمٍ لم يصل — وبسقف، ثمّ الأثلاث كما كانت.
        st["plan_waits"] = int(st.get("plan_waits") or 0) + 1
        if st["plan_waits"] > PLAN_WAIT_CYCLES:
            st["levels"] = []
            atom._plan_timeouts += 1
            return True
        return False
    spread = max(0.0, quote[1] - quote[0])
    until = st.get("seen_at") or time.time()
    levels = atom._book.exit_levels(symbol=name, side=side.lower(), entry=entry, stop=stop,
                                    spread=spread, until=until)
    risk = abs(entry - stop)
    buy = side.upper() == "BUY"
    middle = [price for price, _frame, _at, _ratio in levels
              if (entry < price < target if buy else target < price < entry)
              and abs(target - price) >= risk]
    st["levels"] = middle[:MAX_MIDDLE]
    if st["levels"]:
        atom._level_plans += 1
    return True


def reached(side: str, current: float, level: float, eps: float) -> bool:
    return current >= level - eps if side.upper() == "BUY" else current <= level + eps


def plan_stage(st: dict[str, Any], side: str, current: float, progress: float,
               stages: tuple, eps: float) -> tuple[float, float | str | None, bool] | None:
    """مرحلة الخطّة التي بلغها السعر الآن، أو `None`.

    يعيد `(ما يُغلق من المتبقّي · موضع الوقف بعدها · أهي الأخيرة)`؛ وموضع الوقف `"BE"`
    للتعادل، أو سعر المستوى الأوّل، أو `None` (الخروج الكامل عند الهدف). وكسورُ الإغلاق
    من جدول مراحل الذرّة نفسه (`STAGES`: ثلث المتبقّي ثمّ نصفه ثمّ كلّه) — رقمٌ واحد لا اثنان.
    """
    levels = st["levels"]
    stage = st["stage"]
    if stage < len(levels):
        if not reached(side, current, levels[stage], eps):
            return None
        if stage == 0:
            return stages[0][1], "BE", False
        return stages[1][1], levels[0], False
    if progress < stages[-1][0] - eps:
        return None
    return stages[-1][1], None, True


async def step(atom: Any, stages: tuple, eps: float, st: dict[str, Any], pos: dict[str, Any],
               ticket: Any, symbol: Any, side: str, entry: float, current: float,
               volume: float, stop: float | None) -> None:
    """مرحلة الخطّة إن بلغها السعر — وإلّا وقفُ الجزء الأخير يتبع البنية."""
    profit_distance = (current - entry) if side == SIDE_BUY else (entry - current)
    progress = profit_distance / st["span"]
    if protected(symbol) and st.get("risk"):
        await protect_step(atom, stages, eps, st, pos, ticket, symbol, side, entry, current,
                           volume, stop, profit_distance, progress)
        return
    spec = plan_stage(st, side, current, progress, stages, eps)
    if spec is not None:
        close_frac, lock, last = spec
        await stage_apply.apply_stage(atom, st, pos, ticket, symbol, side, entry, current,
                                      volume, close_frac, last, lock, REASON_LOCK_LEVEL,
                                      progress, profit_distance)
        return
    body = trail(atom, st, symbol, side, current, stop, pos.get("account_id"), eps)
    if body is None or atom._context is None:
        return
    r_multiple = (profit_distance / st["risk"]) if st["risk"] else 0.0
    await atom._context.publish(EVENT_OUT, {
        "account_id": str(pos.get("account_id") or ""), "ticket": ticket,
        "symbol": str(symbol) if symbol else "", "side": side, "action": ACTION_MODIFY,
        "stop_loss": round(body["stop_loss"], _PRICE_DP), "stage": st["stage"],
        "reason": body["reason"], "r_multiple": round(r_multiple, _R_DP)})
    atom._emitted += 1
    atom._trails += 1


def trail(atom: Any, st: dict[str, Any], symbol: Any, side: str, current: float,
          stop_now: float | None, account: Any, eps: float,
          force: bool = False) -> dict[str, Any] | None:
    """وقف الجزء الأخير خلف أحدث بنيةٍ مؤكَّدة على الربع ساعة — يضيق ولا يتّسع.
    (٢٠٢٦-١٠-٠٦ بختم المالك «NQ»: على **الخمس دقائق** للناسداك — `StructureBook.stop_frame`؛ واسم
    السبب `STOP_TRAIL_STRUCTURE_15M` بقي كما هو، عقدٌ يقرؤه سجلّ الصفقات.)

    يعيد جسم أمر `MODIFY_SL` أو `None`. يعمل بعد آخر إغلاقٍ جزئيّ وحده، وبلا وقفٍ مؤجَّل
    (و`force` لخطّة «أمّن ثمّ احجز» بعد +2R، حيث لا مستويات تُعدّ).
    """
    if st.get("pending_stop"):
        return None
    if not force and (st["stage"] != len(st.get("levels") or []) or not st["levels"]):
        return None
    level = atom._book.trail_level(symbol=symbol, side=side.lower(), price=current,
                                   until=time.time())
    if level is None:
        return None
    pad = atom._roundtrip_cost(account, symbol) or 0.0
    new_stop = level - pad if side.upper() == "BUY" else level + pad
    best = [v for v in (stop_now, st.get("trail_sent")) if v]
    if best:
        tightest = max(best) if side.upper() == "BUY" else min(best)
        if (new_stop <= tightest + eps) if side.upper() == "BUY" else (new_stop >= tightest - eps):
            return None
    if not atom._stop_valid(symbol, side.upper(), new_stop, current):
        return None
    st["trail_sent"] = new_stop
    return {"stop_loss": new_stop, "reason": REASON_TRAIL}


async def protect_step(atom: Any, stages: tuple, eps: float, st: dict[str, Any], pos: dict[str, Any],
                       ticket: Any, symbol: Any, side: str, entry: float, current: float,
                       volume: float, stop: float | None, profit_distance: float,
                       progress: float) -> None:
    """«أمّن ثمّ احجز ثمّ تتبّع» (`PROTECT_SYMBOLS`): تعادلٌ عند +1R، ثلثٌ ووقف +1R عند +2R، ثمّ تتبّع."""
    if st.get("pending_stop") or atom._context is None:
        return
    buy = side == SIDE_BUY
    risk = float(st["risk"])
    r_now = profit_distance / risk
    phase = int(st.get("protect") or 0)
    tighter = (lambda a, b: a > b + eps) if buy else (lambda a, b: a < b - eps)
    # أضيقُ ما عند الوسيط أو ما أُرسل للتوّ (تتبّعٌ لم تصل صورته بعد) — فلا يُرخى وقفٌ بالتعادل أو الحجز.
    held = [v for v in (stop, st.get("trail_sent")) if v]
    stop = (max(held) if buy else min(held)) if held else stop
    if progress >= stages[-1][0] - eps:
        # الهدف (سقف الأمر) بلغه السعر: خروجٌ كامل كما في الخطّة.
        await stage_apply.apply_stage(atom, st, pos, ticket, symbol, side, entry, current, volume,
                                      stages[-1][1], True, None, REASON_PROTECT_LOCK,
                                      progress, profit_distance)
        return
    if phase < 2 and r_now >= PROTECT_LOCK_R - eps:
        st["protect"] = 2
        lock = entry + risk if buy else entry - risk
        await stage_apply.apply_stage(atom, st, pos, ticket, symbol, side, entry, current, volume,
                                      stages[0][1], False,
                                      lock if (stop is None or tighter(lock, stop)) else None,
                                      REASON_PROTECT_LOCK, progress, profit_distance)
        return
    if phase < 1 and r_now >= PROTECT_BE_R - eps:
        st["protect"] = 1
        be = stage_apply.breakeven_price(atom, symbol, side, entry)
        if stop is not None and not tighter(be, stop):
            return      # الوقف عند التعادل أو أضيق منه أصلًا — لا يُرخى
        body = {"account_id": str(pos.get("account_id") or ""), "ticket": ticket,
                "symbol": str(symbol) if symbol else "", "side": side, "action": ACTION_MODIFY,
                "stop_loss": round(be, _PRICE_DP), "stage": st["stage"], "reason": REASON_PROTECT_BE,
                "r_multiple": round(r_now, _R_DP)}
        st["pending_stop"] = {"body": body, "cycles": 0, "volume_before": volume,
                              "stage": st["stage"], "ready": True, "after_close": False}
        await atom._release_stop(st, st["pending_stop"], symbol, side, current, ticket)
        return
    # التتبّع من لحظة الدخول (٢٠:١x): كلّ بنيةٍ مؤكَّدة جديدة في صالح الصفقة تشدّ الوقف — ولا يتّسع.
    body = trail(atom, st, symbol, side, current, stop, pos.get("account_id"), eps, force=True)
    if body is None:
        return
    await atom._context.publish(EVENT_OUT, {
        "account_id": str(pos.get("account_id") or ""), "ticket": ticket,
        "symbol": str(symbol) if symbol else "", "side": side, "action": ACTION_MODIFY,
        "stop_loss": round(body["stop_loss"], _PRICE_DP), "stage": st["stage"],
        "reason": body["reason"], "r_multiple": round(r_now, _R_DP)})
    atom._emitted += 1
    atom._trails += 1


def plan_tickets(atom: Any) -> list[str]:
    """التذاكر التي يديرها ٥٧٤ الآن — ٥٧٢ يتنحّى عنها فلا يُنقل وقفُها من مكانين.

    ٢٠٢٦-١٠-٠٧ (ختم المالك «nq»): **كلّ تذكرةٍ حُسمت خطّتها ولم تنتهِ** — في الأثلاث التعادلُ عند الهدف الأوّل
    (ثلث المسافة) لا عند 1R من ٥٧٢؛ هدفٌ بنسبة 1:5 كان ٥٧٢ يؤمّنه قبل هدفه الأوّل.
    ٢٠٢٦-١٠-٢٣ (ورقة «خطوط حمراء» المختومة، القانون 6 «يُغلق الجزء فورًا ثمّ يُنقل الوقف»): **وصفقة الهدف الواحد** أيضًا — ثلثُ
    هدفها داخل كلفة الدورة فلا أجزاء ولا نقل وقفٍ عندنا («الهدف والوقف للوسيط»)، وكانت تخرج من القائمة بـ`done` فيؤمّنها ٥٧٢ عند
    1R بلا إغلاق جزء."""
    return sorted(key for key, st in atom._tracked.items()
                  if (not st.get("done") or st.get("single")) and st.get("levels") is not None)
