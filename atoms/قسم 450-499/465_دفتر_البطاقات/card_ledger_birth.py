"""٤٦٥ — الولادة: القرار الموافَق، والإعداد ومستوياته، وفتح البطاقة وإعلانها.

v1.30.1 (٢٠٢٦-٠٩-٢٣، ختم `nq`): نُقلت **حرفيًّا** من `atom.py` (حدّ الأربع مئة
سطر). وحارسُ العَود (`if symbol in atom._live:`) بعد `_open` في المسارين بقي
كما أصلحه v1.30.0 — النداء الذاتيّ يمرّ من `atom._on_setup` كما كان.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from typing import Any

from shared.trade_card import (levels, movement_floor, STATE_DISPATCHED, STATE_FILLED,
                               STATE_OPEN)
from card_ledger_common import EVENT_CHANGED, EVENT_OPENED
from card_ledger_common import _DRAFT_SYMBOLS, _SIDES, SIDE_BUY
from card_ledger_common import _real, _side_of, _text


async def announce(atom, symbol: str, card: dict[str, Any],
                   decision_id: str = "") -> None:
    if atom._context is None:
        return
    await atom._context.publish(EVENT_CHANGED, {
        "id": "trade_card", "card_no": card["card_no"], "symbol": symbol,
        "side": card.get("side"), "state": card.get("state"),
        "decision_id": decision_id, "entry": card.get("entry"),
        "stop_points": card.get("stop_points"), "peak": card.get("peak"),
        "worst": card.get("worst"), "at": time.time()})


async def on_approved(atom, payload: dict[str, Any]) -> None:
    if not atom._running or not isinstance(payload, dict):
        return
    symbol = _text(payload.get("symbol")).upper()
    if not symbol:
        return
    side = _side_of(payload)
    approved = payload.get("approved") is True
    atom._write(symbol, "466", "approved", approved)
    if not approved or side not in _SIDES:
        return
    card = atom._live.get(symbol)
    if card is not None:
        # بطاقةٌ شغّالة على الزوج — لا بطاقة جديدة؛ القرار يُكتب فيها.
        atom._reused += 1
        atom._write(symbol, "466", "decision_id", _text(payload.get("decision_id")))
        if card["side"] and side != card["side"]:
            # القسم وافق على عكس اتّجاه بطاقةٍ حيّة. اتّجاه البطاقة لا
            # ينقلب — ولكنّ التناقض يُسمّى ويُعدّ، لا يُبتلع في سجلّ.
            atom._flipped += 1
            atom._write(symbol, "466", "side_conflict",
                        "%s←%s" % (card["side"], side))
            await atom._call_reversal(symbol, card, side, payload)
        else:
            atom._write(symbol, "466", "side", side)
        return
    # لا رقم قبل المستويات (حكم «الرقم للتحليل»). ينتظر القرارُ إعدادَه،
    # فإن كان الإعداد قد سبق ومطابقًا وُلدت البطاقة الآن.
    pending = atom._waiting.get(symbol)
    setup = (pending or {}).get("setup")
    atom._waiting[symbol] = {"side": side, "payload": payload,
                             "setup": setup, "at": time.time()}
    if len(atom._waiting) > _DRAFT_SYMBOLS:
        atom._waiting.pop(next(iter(atom._waiting)))
    if setup is not None and _text(setup.get("side")).lower() == side:
        if atom._same_spent_idea(symbol, side, setup):
            return
        await atom._open(symbol, payload, side)
        # v1.30.0: الإعداد يُكتب على البطاقة إن وُلدت — وإلّا بقي منتظرًا
        # (بلا هذا يعود `_on_setup` ففتحٌ ثانٍ على القاعدة المقفولة نفسها).
        if symbol in atom._live:
            await atom._on_setup(setup)


async def call_reversal(atom, symbol: str, card: dict[str, Any],
                        side: str, payload: dict[str, Any]) -> None:
    """يسجّل انعكاس التحليل على صفقةٍ **قائمة** — عدًّا وسطرًا على البطاقة، بلا نشر.

    (٢٠٢٦-١٠-٠٢: لا مستمع للنداء بقرار المالك ٢٠٢٦-٠٩-١٨ — انظر آخر الدالّة.)
    وثلاثة شروطٍ تمنع النداء من أن يصير ضجيجًا — فالاتّجاه يُقلب كلّ
    ٠٫٤٩ ثانية مقيسًا، ونداءٌ بهذا الإيقاع لا يُقرأ بل يُطفأ:
      ١) البطاقة **أُرسلت أو نُفِّذت** — لا نداء على فكرةٍ لم تصر صفقة.
      ٢) المحصّلة (٤١٣) تؤيّد الجهة الجديدة — لا موافقةٌ منفردة تقلبها.
      ٣) مهلةٌ بين نداءين لنفس البطاقة.
    وما دون ذلك يبقى مسجَّلًا في `466.side_conflict` بلا نداء.
    """
    if atom._context is None:
        return
    if card.get("state") not in (STATE_DISPATCHED, STATE_FILLED):
        return
    direction = (card.get("seen") or {}).get("413.direction")
    agrees = (isinstance(direction, (int, float))
              and ((direction > 0) == (side == SIDE_BUY)) and direction != 0)
    if not agrees:
        return
    now = time.time()
    if now - atom._reversal_at.get(card["card_no"], 0.0) < atom._reversal_cooldown:
        return
    atom._reversal_at[card["card_no"]] = now
    atom._reversals += 1
    atom._write(symbol, "465", "reversal_called",
                "%s←%s @%s" % (card.get("side"), side, direction))
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): النداء يُعدّ ويُكتب على البطاقة ولا يُنشر.
    # `decision.card.reversed` لم يسمعه أحدٌ قطّ (بحثٌ في المشروع كلّه: الاسم في 465
    # وحده) — 27,963 نداءً في الفراغ حتى صباح اليوم. والمستمع مؤجَّلٌ بأمر المالك
    # ٢٠٢٦-٠٩-١٨: «خدها واحتفظ فيها تحت دراسة»، وأسئلته (ماذا يفعل المال؟ وهل
    # يتعارض مع خطّة الخروج 574؟) في `ورق/١٣_المفتوح_والمعلّق/فوركس/2026-09-18 —
    # انعكاس الاتّجاه على صفقة مفتوحة — تحت الدراسة.md`. فالقياس الذي تطلبه الدراسة
    # («كم مرّةً ينادي فعلًا في يومٍ كامل؟») يبقى: العدّاد `reversals` في الصحّة
    # واللقطة، وسطر `465.reversal_called` على البطاقة نفسها. ويعود النشر بختمٍ يُسمّي
    # مستلمه. وحمولة النداء التي كانت تُنشر محفوظةٌ في الورقة نفسها.


def same_spent_idea(atom, symbol: str, side: str,
                    setup: Any) -> bool:
    """أهي الفكرةُ نفسها التي انتهت للتوّ بلا تنفيذ؟

    ⚖️ حكم المالك: «مو كلّ شويّ بتخلقوا بطاقة — نحن عم نبني بطاقة
    وبنضلّ عم نبني فيها وبنزبّطها لحتّى تزبط». والرقم يتصاعد إلى ما لا
    نهاية، فكلُّ رقمٍ يُحرَق على فكرةٍ مكرّرة يكذب على الدفتر.

    مقيس ٢٠٢٦-٠٩-٢٢: **5,559 بطاقة منتهية من 5,594**، و‎5,558‎ منها بلا
    تذكرة — و‎99٪‎ منها كانت مكتملة المستويات. وخمسٌ متتالية على ناسداك
    بالمستويات نفسها حرفيًّا (دخول ‎30513.9‎ · وقف ‎30522.33‎ · هدف
    ‎30478.08‎). فكرةٌ واحدة، خمسةُ أرقام.

    والمقارنة على المستويات لا على الزمن: فكرةٌ تغيّر وقفها أو هدفها
    فكرةٌ جديدة وتستحقّ رقمها. وما لم يتغيّر فيه شيءٌ يبقى منتظرًا.
    """
    spent = atom._spent_idea.get(symbol)
    if spent is None or not isinstance(setup, dict):
        return False
    entry = _real(setup.get("entry_reference"))
    stop = _real(setup.get("invalidation_price"))
    target = _real(setup.get("target_price"))
    if entry is None or stop is None:
        return False
    fresh = (side, entry, stop, target)
    if fresh != spent:
        return False
    atom._idea_repeat += 1
    return True


async def open_card(atom, symbol: str, payload: dict[str, Any], side: str) -> None:
    if atom._store is None or not atom._store_ready:
        return
    moment = time.time()
    try:
        card_no, fresh = await asyncio.to_thread(
            atom._store.open_card, symbol, _text(payload.get("account_id")),
            _text(payload.get("broker")), side, moment, {})
    except (OSError, sqlite3.Error) as exc:
        # لا بطاقة وُلدت: القرار التالي على الرمز يحاول الولادة ثانيةً.
        atom._store_error(exc)
        return
    atom._live[symbol] = {"card_no": card_no, "state": STATE_OPEN,
                          "side": side, "seen": {}, "entry": None,
                          "stop_points": None, "peak": None,
                          "worst": None, "saved_r": 0.0}
    if fresh:
        atom._opened += 1
    else:
        atom._reused += 1
    await atom._update(card_no, {
        "side": side, "decision_id": _text(payload.get("decision_id")) or None,
        "state": STATE_OPEN})
    # المسوّدة تُختم في البطاقة: الأحكام التي صنعت هذا القرار لا تُفقد.
    draft = atom._drafts.pop(symbol, {})
    for key, value in draft.items():
        author, _, field = key.partition(".")
        atom._write(symbol, author, field, value)
    atom._write(symbol, "466", "side", side)
    # لقطة الآراء تُجمَّد هنا — بعد المسوّدة وقبل أيّ تحديثٍ لاحق.
    atom._opinion_rows = atom._stamp_opinions(symbol)
    atom._changed = True
    if atom._context is not None:
        await atom._context.publish(EVENT_OPENED, {
            "id": "trade_card", "card_no": card_no, "symbol": symbol,
            "side": side, "state": STATE_OPEN, "opened_at": moment,
            "carried_writes": len(draft),
            "decision_id": _text(payload.get("decision_id")),
            "account_id": _text(payload.get("account_id"))})
    await atom._announce(symbol, atom._live[symbol],
                         _text(payload.get("decision_id")))


def target_died(atom, symbol: str, target: Any, spread: Any,
                owner: str) -> bool:
    """أهذا هدفُ فكرةٍ خسرت لتوّها؟ — يُردّ، ويُعلَن في البطاقة.

    الرابحة لا تُسجَّل: بلوغُ الهدف إتمامٌ لا إبطال. والمدّة مقيسة:
    وسيط عمر الفكرة من ولادة الإعداد حتّى الهدف أو الوقف.
    """
    dead = atom._dead_target.get(symbol)
    if dead is None or target is None:
        return False
    dead_target, died_at = dead
    age = time.time() - died_at
    if age >= atom._dead_target_ttl:
        return False
    if abs(float(target) - dead_target) > max(abs(dead_target) * 0.0015,
                                              spread or 0.0):
        return False
    atom._dead_blocked += 1
    atom._write(symbol, "465", "setup_rejected",
                "%s:هدفٌ ميّت %.2f منذ %.0f ث" % (owner, dead_target, age))
    return True


def write_decision_facts(atom, symbol: str, owner: str, payload: dict[str, Any]) -> None:
    """سطرٌ واحد على البطاقة: «مفتاح=قيمة» لكلّ رقمٍ قرّرت عليه الاستراتيجيّة — يُقرأ في اللوحة ويُقاس بعدها."""
    evidence = payload.get("evidence")
    facts = evidence.get("facts") if isinstance(evidence, dict) else None
    if isinstance(facts, dict) and facts:
        atom._write(symbol, owner, "حقيقة القرار", " · ".join(
            "%s=%s" % (k, "—" if v is None else v) for k, v in facts.items()))


async def on_setup(atom, payload: dict[str, Any]) -> None:
    """المستويات من ٤٠٦ أو ٤١٠ — وهنا تُحسب النسبة وتُحكَم.

    وهذا ما لم يكن له موضع: الإعداد كان يمرّ من الاستراتيجيّة إلى ٥٥٥
    دون أن يراه حارس، فتخرج صفقاتٌ بنسبةٍ دون الثلاثة. البطاقة تراه.
    """
    if not atom._running or not isinstance(payload, dict):
        return
    symbol = _text(payload.get("symbol")).upper()
    if not symbol:
        return
    card = atom._live.get(symbol)
    if card is None:
        # لا بطاقة بعد: يُحفظ الإعداد ولا يُسقَط. فإن كان القرار قد سبقه
        # ومطابقًا وُلدت البطاقة الآن — وإلّا انتظر قرارَه.
        pending = atom._waiting.setdefault(
            symbol, {"side": "", "payload": None, "setup": None, "at": time.time()})
        pending["setup"] = payload
        side = _text(pending.get("side")).lower()
        if side and pending.get("payload") is not None                     and _text(payload.get("side")).lower() == side:
            # ⚰️ قبل الولادة لا بعدها: كان الفحص أسفلَ الدالّة، فتُفتح
            #    البطاقة ثمّ يُردّ إعدادها — بطاقةٌ بلا مستويات.
            if atom._target_died(symbol, _real(payload.get("target_price")),
                                 _real(payload.get("spread")),
                                 _text(payload.get("setup_owner")) or "406/410"):
                return
            if atom._same_spent_idea(symbol, side, payload):
                return
            await atom._open(symbol, pending["payload"], side)
            # v1.30.0: يُعاد الدخول **فقط** إن وُلدت البطاقة. كان يُعاد بلا
            # شرط، فإن فشل الفتح (قفلٌ على القاعدة) عاد إلى الفرع نفسه ففتح
            # ثانيةً… حتى `RecursionError` — ‏٩٥٠ مرّة في سجلّ ١٩:٤١، وكلّ
            # محاولةِ فتحٍ تنتظر مهلة الانشغال فتحجز الدورة («المعلِّق 465»).
            # وإن لم تُولد بقي الإعداد منتظرًا، والقرار التالي يحاول ثانيةً.
            if symbol in atom._live:
                await atom._on_setup(payload)
        return
    entry = _real(payload.get("entry_reference"))
    stop = _real(payload.get("invalidation_price"))
    target = _real(payload.get("target_price"))
    if entry is None or stop is None:
        return
    owner = _text(payload.get("setup_owner")) or "406/410"
    # جهةُ الإعداد قبل مستوياته. ٥٥٥ يفحصها منذ البدء وأنا لم أفحصها،
    # فكتب إعدادُ بيعٍ من ٤١٠ مستوياتِه على بطاقة شراء وفازت لأنّها
    # وصلت أخيرًا (مقيس على بطاقتَي الذهب وناسداك ٢٠٢٦-٠٩-١٨). آخرُ
    # واصلٍ ليس أصدقَ واصل. والمرفوض يُعلَن في البطاقة لا يُبتلع.
    setup_side = _text(payload.get("side")).lower()
    card_side = _text(card.get("side")).lower()
    # 🔴 ٢٠٢٦-٠٩-٢٢ — الثغرة التي كلّفت ‎−99.52$‎ في البطاقة ٦١ (الذهب):
    #    الشرط كان `if setup_side and card_side and ...`، فجهةُ بطاقةٍ
    #    **فارغةٌ لحظتَها** تتخطّى الحارس كلَّه — ومعه فحصُ الهندسة
    #    أسفلَه، لأنّه مشروطٌ بـ`card_side` أيضًا. فدخلت مستوياتُ
    #    **شراء** على بطاقةٍ صارت `sell`، و`verdict=pass`.
    #
    #    والسجلّ يشهد: `454 · 458 · 466 side="sell"` بينما
    #    `405 رأي: الانعكاس · شراء · +100` ومستوياته `stop 4356.47`
    #    (تحت الدخول) و`target 4379.74` (فوقه) — هندسةُ شراءٍ صريحة.
    #
    #    ⚠️ وخطرُها تضاعف بعد أن تبيّن أنّ الحساب نوعه **`Hedge`**:
    #    بيعٌ وشراءٌ على الرمز نفسه لا يُقفل أحدُهما الآخر بل يفتحان
    #    مركزين متعاكسين حقيقيّين.
    #
    #    ✅ الجهةُ المجهولة تُملأ من الإعداد ولا تُتخطّى، وإعدادٌ بلا
    #    جهةٍ يُردّ — لا تُبنى صفقةٌ على جهةٍ لا أحد يعرفها.
    if not setup_side:
        atom._mismatched += 1
        atom._write(symbol, "465", "setup_rejected", "%s:بلا جهة" % owner)
        return
    if card_side and setup_side != card_side:
        atom._mismatched += 1
        atom._write(symbol, "465", "setup_rejected",
                    "%s:%s←%s" % (owner, card_side, setup_side))
        return
    if not card_side:
        card_side = setup_side
        card["side"] = setup_side
        await atom._update(card["card_no"], {"side": setup_side})
        atom._write(symbol, "465", "side_adopted", setup_side)
    # ⚰️ هدفٌ لفكرةٍ ماتت لتوّها — يُردّ. (انظر `_dead_target` أعلاه.)
    if atom._target_died(symbol, target, _real(payload.get("spread")), owner):
        return
    measured = levels(entry, stop, target, _real(payload.get("spread")),
                      side=card_side or setup_side)
    shape = measured.get("geometry")
    # `card_side` مضمونةٌ الآن (تُملأ من الإعداد أعلاه)، فالفحص لا
    # يتخطّى نفسه بغيابها. والهندسة هي الحكم الأخير: مستوياتٌ تقول
    # شراءً على بطاقة بيعٍ تُردّ مهما قالت الحقول.
    if shape in ("broken",) or (shape in ("buy", "sell")
                                and shape != card_side):
        atom._mismatched += 1
        atom._write(symbol, "465", "setup_rejected",
                    "%s:هندسة_%s←%s" % (owner, card_side or "-", shape))
        return
    rr = measured.get("rr")
    measured.pop("geometry", None)
    fields = {"entry": entry, "stop": stop, "target": target, **measured}
    await atom._update(card["card_no"], fields, body={
        "setup_id": _text(payload.get("setup_id")),
        "setup_type": _text(payload.get("setup_type")),
        "invalidation_reason": _text(payload.get("invalidation_reason")),
        "target_reason": _text(payload.get("target_reason"))})
    card["entry"] = entry
    # ⚰️ كان `target` يذهب إلى القرص وحده عبر `_update` ولا يُكتب في
    #    البطاقة الحيّة — فـ`card.get("target")` عند الإغلاق `None`
    #    دائمًا، وحارسُ الهدف الميّت لا يتسلّح أبدًا. كتابةٌ في وعاءٍ
    #    وقراءةٌ من آخر. الثمن مقيس: البطاقات ٤٠ و٤١ و٤٢ فكرةً واحدة
    #    في سبع دقائق (−68.25 · −88.18 · −0.13) و`target_died` صفرٌ
    #    في الدفتر كلّه. **كلّ حقلٍ يُقرأ لاحقًا يُكتب في الوعاءين.**
    card["stop"] = stop
    card["target"] = target
    card["stop_points"] = measured.get("stop_points")
    card["why"] = {"invalidation_reason": _text(payload.get("invalidation_reason")),
                   "target_reason": _text(payload.get("target_reason"))}
    atom._write(symbol, owner, "stop", stop)
    atom._write(symbol, owner, "target", target)
    atom._write(symbol, "465", "rr", rr)
    # ٢٠٢٦-١٠-١٢ (ختم المالك «NQ»: «كلّ صفقة تحمل الحقائق التي فُتحت عليها وأرقامها»): أرقام القرار كما أرسلتها
    # الاستراتيجيّة على إطارها (`evidence.facts`). كان الدليل لا يُكتب، وختم المحلّلين مفتاحه بلا إطار — فلم تُعرف Z صفقة 405.
    write_decision_facts(atom, symbol, owner, payload)
    # أرضيّة الحركة — إعلانٌ مقيس لا حجب. الثمن يُقرأ قبل أن يُبدَّل العيار.
    floor = movement_floor(symbol)
    risk = measured.get("stop_points")
    if floor and risk:
        below = risk < floor
        if below:
            atom._below_floor += 1
        atom._write(symbol, "465", "scale",
                    "%s %.4f/%.4f" % ("below" if below else "ok", risk, floor))
    if rr is not None and rr < atom._min_rr:
        atom._rejected_rr += 1
        atom._write(symbol, "465", "verdict",
                    "block:RR_BELOW_%.2f" % atom._min_rr)
    else:
        atom._write(symbol, "465", "verdict", "pass")
    atom._changed = True
