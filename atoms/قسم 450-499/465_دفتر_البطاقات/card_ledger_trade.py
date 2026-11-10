"""٤٦٥ — الصفقة: التِكّة وأقصى الحركة، والإرسال والحجب، والنتيجة والإغلاق.

v1.30.1 (٢٠٢٦-٠٩-٢٣، ختم `nq`): نُقلت **حرفيًّا** من `atom.py` (حدّ الأربع مئة
سطر). كلّ دالّةٍ تأخذ الذرّة أوّلًا (`atom`) مكان `self`.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from typing import Any

from shared.trade_card import (excursion, STATE_CLOSED, STATE_DISPATCHED, STATE_EXPIRED,
                               STATE_FILLED)
from card_ledger_common import EVENT_CLOSED, _PEAK_STEP_R, _SIDES
from card_ledger_common import _real, _side_of, _text
import card_ledger_legs


async def retire_if_dead(atom, symbol: str, card: dict[str, Any],
                         price: float | None) -> bool:
    """بطاقةٌ أُرسلت ولم تصر أمرًا، وتجاوز السعرُ إبطالَ تحليلها.

    ⚖️ قِيس ٢٠٢٦-٠٩-١٩: البطاقة ٤٤ أُرسلت ‎19:06:33‎ بلا تذكرة، واخترق
    السعرُ وقفَها بـ‎223‎ نقطة، وبقيت تحجز خانة بتكوين **حتّى سقف الوقت
    وحده** (‎900‎ ث) — فلا صفقة على الرمز طوال ذلك. والسقف الزمنيّ لا
    يعرف موتَ الفكرة؛ يعرف مرور الوقت فقط.

    وثلاثة شروط معًا، فلا تُخلى خانةٌ على ظنّ:
      ١) `DISPATCHED` بلا تذكرة — لم يصر أمرًا على المنصّة قطّ.
      ٢) مضت مهلةُ الطيران (‎90‎ ث = `inflight_ttl_s` عند ٥٥٥)، فلا
         نسابق تنفيذًا في الطريق فتبقى صفقةٌ بلا بطاقة.
      ٣) السعر تجاوز **وقف التحليل** — وهو `is_broken` بعينه، الفحص
         الذي لا يجريه أحد على الطريق كلّه.
    """
    if (card.get("state") != STATE_DISPATCHED or card.get("ticket")
            or price is None or atom._store is None):
        return False
    stop = _real(card.get("stop"))
    if stop is None:
        return False
    sent = _real(card.get("dispatched_at")) or _real(card.get("opened_at")) or 0.0
    moment = time.time()
    if moment - sent < atom._dead_idea_grace:
        return False
    side = _text(card.get("side")).lower()
    if not ((price <= stop) if side == "buy" else (price >= stop)):
        return False
    try:
        await asyncio.to_thread(atom._store.set_state, card["card_no"],
                                STATE_EXPIRED, moment)
    except (OSError, sqlite3.Error) as exc:
        atom._last_error = str(exc)
        return False
    atom._write(symbol, "465", "idea_dead",
                "السعر %.6f تجاوز إبطال التحليل %.6f بلا تذكرة — أُخليت الخانة"
                % (price, stop))
    card["state"] = STATE_EXPIRED
    # v1.32.0: الإخلاء صار في مهمّةٍ جانبيّة (`atom._retire_if_dead`)، فقد تُولد
    # للرمز بطاقةٌ أخرى قبل أن يعود — فلا يُنزع من الذاكرة إلّا صاحبُه.
    if atom._live.get(symbol) is card:
        atom._live.pop(symbol, None)
    atom._dead_idea += 1
    atom._changed = True
    return True


async def on_tick(atom, payload: dict[str, Any]) -> None:
    """أقصى ما بلغته الصفقة — لا خاتمتها وحدها.

    تحذير قسم ٣٥٠-٣٩٩ (٢٠٢٦-٠٩-١٨): الحكم المشتقّ من الربح المحقَّق
    ملوَّث — ٤ من ٤٣ معكوسة التسمية و١٢ من ٢٨ خاسرة حُرِّك وقفها بعد أن
    بلغت ربحًا. فبطاقةٌ تحمل النهاية وحدها تورّث الكذب إلى من يتعلّم
    منها. والذروة والحضيض يُقاسان هنا بالنقاط وبمضاعف المخاطرة — لا
    بالمال، فهذا قسمٌ لا يرى مالًا.
    """
    if not atom._running or not isinstance(payload, dict):
        return
    symbol = _text(payload.get("symbol")).upper()
    card = atom._live.get(symbol)
    if card is None or card["state"] not in (STATE_DISPATCHED, STATE_FILLED):
        return
    if await atom._retire_if_dead(symbol, card, _real(payload.get("price"))):
        return
    measured = excursion(card.get("entry"), card.get("stop_points"),
                         card.get("side") or "", _real(payload.get("price")),
                         card.get("peak"), card.get("worst"))
    if measured is None:
        return
    card["peak"] = measured["peak_points"]
    card["worst"] = measured["worst_points"]
    reach = max(abs(measured["peak_r"]), abs(measured["worst_r"]))
    if reach - float(card.get("saved_r") or 0.0) < _PEAK_STEP_R:
        return
    card["saved_r"] = reach
    await atom._update(card["card_no"], measured)


async def on_blocked(atom, payload: dict[str, Any]) -> None:
    if not atom._running or not isinstance(payload, dict):
        return
    symbol = _text(payload.get("symbol"))
    atom._write(symbol, "467", "verdict", "block")
    reason = _text(payload.get("reject_reason"))
    if reason:
        atom._write(symbol, "467", "reason", reason)


async def dispatch(atom, payload: dict[str, Any], state: str) -> None:
    if not atom._running or not isinstance(payload, dict):
        return
    symbol = _text(payload.get("symbol")).upper()
    card = atom._live.get(symbol)
    if card is None:
        return
    atom._write(symbol, "467", "verdict", "pass")
    # جانبُ البطاقة يتبع الأمر الذي **خرج**، لا القرار الذي وُلدت عليه.
    # مقيس على البطاقة ١٩ (٢٠٢٦-٠٩-١٨): وُلدت `buy` ثمّ وافق ٤٦٦ على
    # `sell` فخرج الأمر بيعًا، فكتب ٥٥٢ وقفًا فوق الدخول وهدفًا تحته على
    # بطاقةٍ تقول شراء — بطاقةٌ تكذب على قارئها وعلى من يتعلّم منها.
    #
    # 🔴 v1.32.0 (٢٠٢٦-٠٩-٢٥، ختم المالك «NQ» على «صلح»): الحكمُ باقٍ، وموضعُه
    #    تغيّر. عبورُ البوّابة **ليس خروجَ أمر**: ٥٥٥ قد يحجبه (القاطع حجب كلّ
    #    عبورٍ اليوم) أو يبنيه من إعداد جهته هو. وكان الجانب ينقلب مع كلّ عبورٍ
    #    معاكس — والتحليل ينقلب كلّ ثوانٍ — فتبقى مستوياتُ الجهة الأولى على
    #    بطاقةٍ صارت الأخرى، ويبقى الانقلاب طوال الصفقة لأنّ البطاقة لا تعلم
    #    أنّها نُفِّذت. مقيس في ٢٤ ساعة: 11,202 انقلابًا على 6,214 بطاقة، و**41
    #    صفقةً حقيقيّة من 195 جهةُ بطاقتها عكسُ جهة الأمر** (وقفُ الإرسال مقابل
    #    سعر التنفيذ)؛ والبطاقة 80242 صارت `sell` ووقفُها تحت دخولها.
    #    ✅ فالجانب لا ينقلب هنا: التعارض يُسمّى في `467.side_conflict`، والبطاقة
    #    تأخذ جهتها الحقيقيّة لحظةَ التنفيذ نفسها (`on_ack` أدناه). والجانبُ
    #    الفارغ وحده يُملأ من العبور، كما يُملأ من الإعداد.
    passed_side = _side_of(payload)
    if passed_side in _SIDES and not card.get("side"):
        card["side"] = passed_side
        await atom._update(card["card_no"], {"side": passed_side})
    elif passed_side in _SIDES and card.get("side") != passed_side:
        atom._write(symbol, "467", "side_conflict",
                    "%s←%s" % (card.get("side") or "-", passed_side))
    # والمنفَّذة (صارت تُعرف الآن من التأكيد) لا تعود «مرسَلة» بعبورٍ جديد —
    # وإلّا شاخت بمهلة الإرسال ورآها حارسُ الفكرة الميّتة وصفقتُها مفتوحة.
    if card["state"] in (state, STATE_FILLED):
        return
    card["state"] = state
    atom._dispatched += 1
    atom._changed = True
    await atom._update(card["card_no"],
                       {"reason": atom._compose_reason(symbol, card)[:2000]})
    await atom._announce(symbol, card, _text(payload.get("decision_id")))
    await atom._update(card["card_no"], {
        "state": state,
        "gate_request_id": _text(payload.get("gate_request_id")) or None,
        "decision_id": _text(payload.get("decision_id")) or None})


async def on_ack(atom, payload: dict[str, Any]) -> None:
    """الصفقة نُفِّذت: البطاقة تصير `FILLED`، وتأخذ جهتها الحقيقيّة.

    v1.32.0 (٢٠٢٦-٠٩-٢٥، ختم المالك «NQ» على «صلح»): `on_outcome` يضع `FILLED`
    لكلّ حدثٍ غير الإغلاق — و٥٦٣ لا ينشر على `market.outcome.realized` إلّا
    الإغلاق والجزئيّ، وحدثُ الفتح يخرج منه على `execution.command.ack`. فلم تصر
    بطاقةٌ `FILLED` قطّ: بقيت «مرسَلة» طوال صفقتها، يقلب العبورُ جهتها ويراها
    حارسُ الفكرة الميّتة. والتأكيدُ المعتبر تأكيدُ ٥٦٣ وحده (`status=ACK` ومعه
    سعرُ الدخول): ٦٠١ ينشر على الاسم نفسه نتائجَ أوامرَ أخرى (إغلاق · تعديل).

    والتذكرةُ وسعرُ التنفيذ عمودان يملكهما ٥٦٣ ويكتبهما عند النتيجة — فلا
    يُكتبان هنا في العمود؛ يُحفظان في الذاكرة لحرّاسها، ويُسجَّلان ملاحظةً باسم
    ٥٦٣ كما يُسجَّل كلُّ حكمٍ باسم صاحبه.
    """
    if not atom._running or not isinstance(payload, dict):
        return
    entry = _real(payload.get("entry_price"))
    if _text(payload.get("status")).upper() != "ACK" or entry is None:
        return
    symbol = _text(payload.get("symbol")).upper()
    ticket = _text(payload.get("ticket"))
    card = atom._live.get(symbol)
    if card is None or not ticket:
        return
    side = _text(payload.get("side")).lower()
    if card["state"] == STATE_FILLED:
        # مركزٌ آخر على الرمز نفسه: يُسمّى على البطاقة ولا يبدّلها.
        atom._write(symbol, "563", "extra_fill", "%s %s @%s" % (ticket, side or "-", entry))
        # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): وأجزاؤه لا تُضاف إلى صافي هذه البطاقة
        # ولا تُغلقها، ولا تتبنّاها بطاقةٌ تولد بعدها على الرمز — تذكرته تُحفظ تذكرةً غريبة.
        card_ledger_legs.remember(atom._foreign_tickets, ticket, card["card_no"])
        return
    atom._write(symbol, "563", "filled", "%s %s @%s" % (ticket, side or "-", entry))
    fields: dict[str, Any] = {"state": STATE_FILLED}
    if side in _SIDES and side != _text(card.get("side")).lower():
        # الجهة الحقيقيّة تغلب، ومستوياتُ الجهة الأخرى لا تبقى عليها تكذب —
        # تاريخُها باقٍ في `card_writes` باسم كاتبه.
        atom._write(symbol, "465", "side_from_fill",
                    "%s←%s" % (card.get("side") or "-", side))
        atom._side_from_fill += 1
        card.update(side=side, entry=None, stop=None, target=None, stop_points=None,
                    peak=None, worst=None, saved_r=0.0)
        fields.update(side=side, entry=None, stop=None, target=None, stop_points=None,
                      target_points=None, stop_pct=None, target_pct=None, rr=None,
                      peak_points=None, worst_points=None, peak_r=None, worst_r=None)
    card["state"] = STATE_FILLED
    card["ticket"] = ticket
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): سعرُ التنفيذ في الذاكرة — تُعاد به قيمُ البطاقة
    # إن كتب 563 فوقها جزءَ تذكرةٍ أخرى (`card_ledger_legs.reassert`).
    card["fill"] = entry
    atom._filled += 1
    atom._changed = True
    await atom._update(card["card_no"], fields)
    await atom._announce(symbol, card)


async def on_outcome(atom, payload: dict[str, Any]) -> None:
    """النتيجة: الجزئيّ جزءٌ على البطاقة، والإغلاقُ الأخير وحده يُغلقها ويحرّر الزوج.

    ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): كانت «النتيجة تُغلق البطاقة» عند **أوّل** حدث —
    `PARTIAL` الهدف الأوّل كـ`CLOSED` الأخير — فتُسجَّل الصفقة بربح ثلثها الأوّل (البطاقة 86470: +0.33R والوسيط
    +2.20R). الآن يُضاف كلّ جزءٍ إلى البطاقة (`card_ledger_legs`) ولا يُغلقها إلّا الإغلاقُ الأخير، بصافي أجزائه
    كلّها؛ وجزءُ تذكرةٍ أُغلقت بطاقتها يعود إليها، وجزءُ تذكرةٍ أخرى لا يُغلق بطاقةً ليست له.
    """
    if not atom._running or not isinstance(payload, dict):
        return
    symbol = _text(payload.get("symbol")).upper()
    event_type = _text(payload.get("event_type")).upper()
    if event_type and event_type not in ("CLOSED", "PARTIAL"):
        card = atom._live.get(symbol)
        if card is not None and card["state"] != STATE_FILLED:
            card["state"] = STATE_FILLED
            await atom._update(card["card_no"], {"state": STATE_FILLED})
            await atom._announce(symbol, card)
            atom._changed = True
        return
    ticket = card_ledger_legs.ticket_of(payload)
    if ticket and ticket in atom._final_tickets:
        await card_ledger_legs.late_leg(atom, symbol, ticket, payload)
        return
    card = atom._live.get(symbol)
    if card is None:
        return
    if ticket and (ticket in atom._foreign_tickets
                   or (card.get("ticket") and _text(card["ticket"]) != ticket)):
        await card_ledger_legs.foreign_leg(atom, symbol, card, ticket, payload)
        return
    final, summary = await card_ledger_legs.record_leg(atom, symbol, card, payload)
    if not final:
        return
    await atom._flush_safely()
    moment = time.time()
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): الربح صافي الأجزاء كلّها (الربح + العمولة +
    # المبادلة + الرسوم)، والنتيجة نتيجته لا نتيجة الجزء الأخير.
    profit = summary["net_usd"]
    result = summary["result"]
    # الذروة تُثبَّت قبل الإغلاق — آخر حركةٍ دون العتبة لا تُفقد.
    if card.get("peak") is not None and card.get("stop_points"):
        risk = float(card["stop_points"])
        await atom._update(card["card_no"], {
            "peak_points": card["peak"], "worst_points": card["worst"],
            "peak_r": round(float(card["peak"]) / risk, 4),
            "worst_r": round(float(card["worst"]) / risk, 4)})
    if atom._store is not None:
        try:
            await asyncio.to_thread(
                atom._store.set_state, card["card_no"], STATE_CLOSED, moment,
                outcome=result, profit=profit)
        except (OSError, sqlite3.Error) as exc:
            atom._store_error(exc)
            if not atom._store_ready:
                return
            # قفلٌ عابر: الإغلاق لا يضيع — يُقيَّد ويُكتب مع النبض كما
            # يكتب `set_state` نفسه (الحالة وختم الإغلاق والنتيجة).
            await atom._update(card["card_no"], {
                "state": STATE_CLOSED, "closed_at": moment,
                "outcome": result, "profit": profit})
    # وعند الإغلاق تُعاد الكتابة: ما بين الإرسال والنتيجة يُضاف إليها.
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): ومعها أجزاء الصفقة وصافيها في جسم البطاقة.
    await atom._update(card["card_no"],
                       {"reason": atom._compose_reason(symbol, card)[:2000]},
                       card_ledger_legs.body(card, summary, card_ledger_legs.STATUS_CLOSED))
    closed_net = card_ledger_legs.closing(atom, symbol, card, summary)
    atom._live.pop(symbol, None)
    atom._closed += 1
    atom._changed = True
    if atom._context is not None:
        await atom._context.publish(EVENT_CLOSED, {
            "id": "trade_card", "card_no": card["card_no"], "symbol": symbol,
            "state": STATE_CLOSED, "closed_at": moment,
            "outcome": result, "profit": profit, **closed_net})
        card["state"] = STATE_CLOSED
        # ⚰️ صفقةٌ خسرت ⟹ هدفُها ميّت. يُحفظ ليُردّ ما يعيده.
        # والرابحة لا تُحفظ: بلوغُ الهدف إتمامٌ لا إبطال.
        if profit is not None and profit < 0:
            # `target` تُكتب في الوعاءين عند الإعداد، **و`_reload_live`
            # صارت تحملها** بعد الإقلاع. وكان تعليقي هنا يقول إنّ
            # `live_cards` تكفي — وهذا نصفُ الحقيقة: الصفُّ يحملها
            # والاستعادةُ كانت ترميها.
            dead = card.get("target")
            if dead:
                atom._dead_target[symbol] = (float(dead), moment)
                atom._write(symbol, "465", "target_died",
                            "%.2f (خسارة %.2f)" % (float(dead), profit))
        await atom._announce(symbol, card)
