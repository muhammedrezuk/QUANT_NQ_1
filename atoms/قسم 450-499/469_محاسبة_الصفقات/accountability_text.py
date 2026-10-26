"""469 — حمولة «محاسبة الصفقات» وجملها العربيّة: شرح آخر صفقة، والسطر الذي يقرؤه المالك.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): الجملة مركّبةٌ من أرقام البطاقة وحدها — لا كلمة حكم،
ولا «أصاب» ولا «أخطأ»: من بناها، وأين الوقف والهدف ولماذا كما كُتبا، وكم ذهب السعر معنا وضدّنا، وأيّ
ثلثٍ بلغ، وأين خرج، وما سُجّل بالدولار وبوحدة المخاطرة، وحقائق الأقسام لحظة الدخول.

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): الصافي من سجلّ الوسيط (`accountability_broker`) لا من
البطاقة — أجزاء كلّ صفقةٍ ومراحلها وصافيها بالدولار وبـR، و«كم R ربحنا · كم R خسرنا · الصافي» لكلّ مجموعة، ومقارنةٌ
صريحة بما قالته البطاقات القديمة. وإن غاب سجلّ الوسيط عادت المحاسبة إلى البطاقات **معلنةً ذلك** (`net_source`).
"""

from __future__ import annotations

from typing import Any

from accountability_broker import (RISK_MISSING, RISK_OTHER_ORDER, BrokerUnavailable, broker_trades,
                                   comparison, read_broker)
from accountability_groups import fact_table, group_by, stats, strategy_periods
from accountability_ledger import (SHARE_FULL_FLOOR, STRATEGY_NONE, clean_fact_text, closed_cards,
                                   derive_trade, read_ledger)

PAYLOAD_ID = "trade_accountability"
SOURCE = "465 var/store/trade_cards.db + سجلّ الوسيط trade_events_v2 في قاعدة الجسر (قراءة فقط)"
SOURCE_CARDS = "465 var/store/trade_cards.db (قراءة فقط) — سجلّ الوسيط غير متاح"
NET_BROKER, NET_CARDS = "broker", "cards"
#: كم حقيقةً تُذكر في جملة آخر صفقة — والقائمة كاملةً في `entry_facts`.
FACTS_IN_SENTENCE = 5

SIDE_AR = {"long": "شراء", "short": "بيع"}
#: أسماء البُناة كما في 465 (`card_ledger_writers._WHO`) — والمؤرشفة تبقى لأنّ صفقاتها في الدفتر.
BUILDER_AR = {"414": "بطاقة استمرار الاتّجاه", "415": "التوليفة الشاملة", "404": "الاتّجاه", "405": "الانعكاس",
              "406": "الاختراق", "407": "الارتداد", "408": "الزخم", "409": "المدى",
              "410": "السيولة"}
THIRDS_AR = {0: "لم تبلغ أقصى حركةٍ معنا الهدفَ الأوّل", 1: "بلغت الهدف الأوّل (ثلث المسافة)",
             2: "بلغت الهدف الثاني (ثلثا المسافة)", 3: "بلغت الهدف الكامل"}
EXIT_AR = {"stop": "خرج على الوقف (أبلغ الوسيط SL)", "breakeven": "خرج عند الدخول",
           "first_third": "خرج عند ثلث المسافة (الهدف الأوّل)",
           "second_third": "خرج عند ثلثي المسافة (الهدف الثاني)",
           "target": "خرج عند الهدف الكامل",
           "unknown": "موضع الخروج غير معروف (لا سعر دخولٍ أو خروجٍ أو هدفٍ مرسَل على البطاقة)"}
WINDOW_AR = {"london_peak": "ذروة لندن", "ny_open": "افتتاح أمريكا", "outside": "خارج النافذتين"}
RISK_NOTE_AR = {RISK_MISSING: "لا مبلغ مخاطرةٍ على البطاقة",
                RISK_OTHER_ORDER: "مبلغ المخاطرة على البطاقة لأمرٍ آخر (حجمها غير حجم التذكرة)"}

#: تعريف كلّ رقمٍ في الحمولة — كي يُقرأ كما حُسب.
DEFINITIONS_AR = {
    "trade": "تذكرةٌ عند الوسيط لها إغلاقٌ أخير وبطاقةٌ تملكها (سمعت تأكيد تنفيذها، وإلّا أصغر بطاقةٍ تحملها)"
             " — وحين يغيب سجلّ الوسيط: بطاقةٌ عليها ربحٌ انتهت",
    "profit_usd": "صافي الصفقة = مجموع (الربح + العمولة + المبادلة + الرسوم) على أجزائها كلّها عند الوسيط",
    "result_r": "صافي الصفقة ÷ مبلغ المخاطرة على بطاقتها (552 risk_amount) — وبلا مبلغٍ أو لأمرٍ آخر: بلا R",
    "won_r": "مجموع R الصفقات الرابحة", "lost_r": "مجموع R الصفقات الخاسرة (سالب)",
    "total_r": "الصافي = الرابحة + الخاسرة",
    "legs": "أجزاء الصفقة بترتيبها: الجزئيّ الأوّل الهدف الأوّل والثاني الهدف الثاني، والأخير بسبب الوسيط وموضعه",
    "move_r": "حركة خروج الجزء من الدخول ÷ مسافة الوقف الأصليّ المرسَل؛ الوقف ضمن ربعها حول الدخول = تعادل",
    "card_r": "ما سجّلته بطاقة الصفقة القديمة (ربحها ÷ مبلغ مخاطرتها) — و r_diff = R الوسيط − R البطاقة",
    "card_vs_broker": "مجموع ما تقوله كلّ البطاقات التي عليها ربح (حساب المحاسبة قبل ٢٠٢٦-١٠-٠٩) مقابل الوسيط",
    "recorded_share": "(الربح ÷ الخطر) ÷ (حركة الخروج ÷ مسافة الوقف): ١ ≈ العقد كلّه، ⅓ ≈ الجزء الأوّل وحده"
                      " — حين تُحسب من البطاقة وحدها",
    "max_favorable_r": "أقصى حركةٍ معنا (ذروة 465) ÷ مسافة الوقف — من سعر التنفيذ والوقف المرسَل إن وُجدا"
                       " (excursion_basis=sent)، وإلّا من دخول التحليل ووقفه (analysis)",
    "max_adverse_r": "أقصى حركةٍ ضدّنا (حضيض 465) ÷ مسافة الوقف — بالأساس نفسه",
    "thirds_reached": "أعلى ثلثٍ من مسافة الهدف (المرسَل إن وُجد) بلغته أقصى حركةٍ معنا (0..3)",
    "exit_kind": "اسم الخروج الأخير (من سبب الوسيط وموضعه)، أو موضعه من مسافة الهدف حين تُحسب من البطاقة",
    "window": "نافذة المالك لحظة ولادة البطاقة (shared/owner_windows)",
    "by_fact": "حقائق الأقسام المختومة عند الولادة: الرقميّة أثلاثًا من قيمها، والنصّيّة بقيمتها",
    "small_sample": "فئةٌ دون الحدّ الأدنى من الصفقات — لا تدخل الترتيب",
}

BASIS_AR = {"sent": "على الوقف المرسَل", "analysis": "على وقف التحليل"}


def _signed_r(value: float | None) -> str:
    return "—" if value is None else "%+.2fR" % value


def _px(value: float | None) -> str:
    return "—" if value is None else ("%.5f" % value).rstrip("0").rstrip(".")


def _strategy_ar(key: str) -> str:
    if key == STRATEGY_NONE:
        return "بلا إعدادٍ على البطاقة"
    owner, _, kind = key.partition(":")
    return "%s (%s)" % (BUILDER_AR.get(owner, owner), kind) if kind and kind != "?" else \
        BUILDER_AR.get(owner, owner)


def _exit_ar(trade: dict[str, Any]) -> str:
    if trade.get("exit_ar"):
        return "الخروج الأخير %s" % trade["exit_ar"]
    kind = trade["exit_kind"]
    if kind == "other":
        return "خرج عند %s من سعر التنفيذ (%.2f من مسافة الهدف)" % (
            _signed_r(trade["exit_move_r"]), trade["exit_target_frac"])
    return EXIT_AR.get(kind, kind)


def _legs_ar(trade: dict[str, Any]) -> str:
    return "الأجزاء: " + " · ".join("%s %s @%s ⟸ %+.2f$" % (
        leg["stage_ar"], leg["volume"], _px(leg["exit_price"]), leg["net_usd"]) for leg in trade["legs"])


def last_trade_view(trade: dict[str, Any], raw_facts: dict[str, str]) -> dict[str, Any]:
    """شرح الصفقة الأخيرة: أرقامها، وحقائق الأقسام عند ولادتها، وجملةٌ مركّبةٌ منها."""
    entry_facts: dict[str, str] = {}
    withheld = 0
    for author in sorted(raw_facts):
        cleaned, hidden = clean_fact_text(raw_facts[author])
        withheld += hidden
        entry_facts[author] = cleaned
    parts = ["%s %s بناها %s" % (SIDE_AR.get(trade["side"], "؟"), trade["symbol"],
                                 _strategy_ar(trade["strategy"]))]
    if trade["stop_reason"]:
        parts.append("الوقف: %s" % trade["stop_reason"])
    if trade["target_reason"]:
        parts.append("الهدف: %s" % trade["target_reason"])
    if trade["fill_price"] is not None:
        parts.append("المرسَل: دخول %s · وقف %s · هدف %s" % (
            _px(trade["fill_price"]), _px(trade["sent_stop"]), _px(trade["sent_target"])))
    if trade["max_favorable_r"] is not None:
        parts.append("ذهب السعر معنا %.2fR وضدّنا %.2fR (%s)" % (
            trade["max_favorable_r"], trade["max_adverse_r"] or 0.0,
            BASIS_AR.get(trade["excursion_basis"], "")))
    if trade["thirds_reached"] is not None:
        parts.append(THIRDS_AR[trade["thirds_reached"]])
    if trade.get("legs"):
        parts.append(_legs_ar(trade))
    parts.append(_exit_ar(trade))
    if trade["result_r"] is not None:
        parts.append("⟸ %s (%+.2f$)" % (_signed_r(trade["result_r"]), trade["profit_usd"]))
    else:
        parts.append("⟸ %+.2f$ (%s فلا وحدة مخاطرة)" % (
            trade["profit_usd"], RISK_NOTE_AR.get(trade.get("risk_note"), RISK_NOTE_AR[RISK_MISSING])))
    if trade.get("r_diff") is not None and trade["r_diff"] != 0:
        parts.append("وسجّلت بطاقتها %s" % _signed_r(trade["card_r"]))
    share = trade["recorded_share"]
    if share is not None and share < SHARE_FULL_FLOOR:
        parts.append("المسجّل حصّة %.2f من العقد — ما بعدها لا تحمله البطاقة" % share)
    if entry_facts:
        shown = " · ".join("%s %s" % (author, entry_facts[author])
                           for author in list(entry_facts)[:FACTS_IN_SENTENCE])
        parts.append("عند الدخول %d حقيقة: %s%s" % (
            len(entry_facts), shown, " …" if len(entry_facts) > FACTS_IN_SENTENCE else ""))
    else:
        parts.append("عند الدخول: لا حقائق أقسامٍ مختومة على هذه البطاقة (الختم بدأ ٢٠٢٦-١٠-٠٨)")
    view = {key: trade.get(key) for key in (
        "card_no", "ticket", "symbol", "state", "side", "strategy", "window", "opened_at", "closed_at",
        "entry", "stop", "target", "rr", "stop_reason", "target_reason", "fill_price",
        "exit_price", "sent_stop", "sent_target", "profit_usd", "gross_usd", "costs_usd", "risk_usd",
        "result_r", "risk_note", "card_profit_usd", "card_r", "r_diff", "legs", "legs_n", "partials",
        "exit_move_r", "recorded_share", "max_favorable_r", "max_adverse_r", "excursion_basis",
        "thirds_reached", "exit_kind", "exit_ar", "exit_target_frac", "net_source")}
    view.update(side_ar=SIDE_AR.get(trade["side"], ""), strategy_ar=_strategy_ar(trade["strategy"]),
                window_ar=WINDOW_AR.get(trade["window"], trade["window"]),
                entry_facts=entry_facts, entry_facts_n=len(entry_facts),
                entry_facts_withheld=withheld, explain_ar=" · ".join(parts))
    return view


def trade_row(trade: dict[str, Any]) -> dict[str, Any]:
    """سطرُ كلّ صفقة في الحمولة: صافيها بالدولار وبـR، وما قالته بطاقتها، وأجزاؤها بمراحلها."""
    return {"card_no": trade["card_no"], "ticket": trade.get("ticket"), "symbol": trade["symbol"],
            "closed_at": trade["closed_at"], "side": trade["side"], "strategy": trade["strategy"],
            "window": trade["window"], "net_usd": trade["profit_usd"], "net_r": trade["result_r"],
            "card_r": trade.get("card_r"), "r_diff": trade.get("r_diff"), "risk_note": trade.get("risk_note"),
            "exit_kind": trade["exit_kind"],
            "legs": [{"stage": leg["stage"], "volume": leg["volume"], "net_usd": leg["net_usd"],
                      "r": leg["r"]} for leg in trade.get("legs") or []]}


def _gap_text(table: dict[str, Any], fact_trades: int, min_sample: int) -> str:
    gaps = table["fact_gaps"]
    if gaps:
        top = gaps[0]
        return "أكثر عاملٍ يفرّق: %s %s — فرق متوسّط %.2fR بين «%s» (%s، ن=%d) و«%s» (%s، ن=%d)" % (
            top["label_ar"], top["fact"], top["avg_r_gap"], top["highest_avg_r_group"],
            _signed_r(top["highest_avg_r"]), top["highest_n"], top["lowest_avg_r_group"],
            _signed_r(top["lowest_avg_r"]), top["lowest_n"])
    if not fact_trades:
        return "أكثر عاملٍ يفرّق: لا صفقة مغلقة تحمل حقائق الأقسام بعد (الختم بدأ ٢٠٢٦-١٠-٠٨)"
    return "أكثر عاملٍ يفرّق (عيّنة صغيرة بعد): %d صفقة تحمل الحقائق، والفئة تُرتَّب من %d" % (
        fact_trades, min_sample)


def unavailable_payload(reason: str, now: float) -> dict[str, Any]:
    return {"id": PAYLOAD_ID, "status": "unavailable", "computed_at": now, "source": SOURCE,
            "facts": {"available": False, "unavailable_reason": reason},
            "summary_ar": "محاسبة الصفقات غير متاحة: %s" % reason}


def _totals_text(totals: dict[str, Any], compare: dict[str, Any] | None, partial: int) -> str:
    if compare is None:
        return "منذ البداية %d صفقة (من البطاقات — سجلّ الوسيط غير متاح): %d رابحة، %s (%+.2f$)%s" % (
            totals["n"], totals["wins"], _signed_r(totals["total_r"]), totals["total_usd"],
            ("، منها %d سُجّل على بطاقتها جزءٌ من العقد وحده" % partial) if partial else "")
    bare = (" · بلا R %d صفقة (%+.2f$)" % (totals["n_without_r"], totals["usd_without_r"])
            if totals["n_without_r"] else "")
    return ("منذ البداية %d صفقة صافيةً من سجلّ الوسيط: %d رابحة · ربحنا %s · خسرنا %s · الصافي %s (%+.2f$)%s"
            " · البطاقات القديمة قالت %s والوسيط %s (الفرق %s)" % (
                totals["n"], totals["wins"], _signed_r(totals["won_r"]), _signed_r(totals["lost_r"]),
                _signed_r(totals["total_r"]), totals["total_usd"], bare,
                _signed_r(compare["cards_total_r"]), _signed_r(compare["broker_total_r"]),
                _signed_r(compare["diff_r"])))


def build_payload(path: str, now: float, min_sample: int, top: int, timeout_s: float,
                  bridge_path: str | None = None) -> dict[str, Any]:
    """يقرأ الدفتر وسجلّ الوسيط (للقراءة فقط) ويبني الحمولة — يُنادى في خيط. وغياب الدفتر يرفع `LedgerUnavailable`."""
    ledger = read_ledger(path, timeout_s)
    broker, reason = None, "لا مسار لقاعدة الجسر"
    if bridge_path:
        try:
            broker, reason = read_broker(bridge_path, timeout_s), ""
        except BrokerUnavailable as exc:
            reason = str(exc)
    counts: dict[str, int] = {}
    compare = None
    if broker is not None:
        trades, counts = broker_trades(ledger, broker)
        compare = comparison(ledger["cards"], trades)
    else:
        trades = [derive_trade(card) for card in closed_cards(ledger["cards"])]
    trades.sort(key=lambda t: (t["closed_at"] or 0.0, t["card_no"]))
    facts = ledger["facts"]
    fact_trades = sum(1 for t in trades if facts.get(t["card_no"]))
    table = fact_table(trades, facts, min_sample, top)
    totals = stats(trades, min_sample)
    by_state: dict[str, int] = {}
    for trade in trades:
        by_state[trade["state"]] = by_state.get(trade["state"], 0) + 1
    partial = sum(1 for t in trades
                  if t["recorded_share"] is not None and t["recorded_share"] < SHARE_FULL_FLOOR)
    last = last_trade_view(trades[-1], facts.get(trades[-1]["card_no"]) or {}) if trades else None
    body = {
        "available": True, "net_source": NET_BROKER if broker is not None else NET_CARDS,
        "broker_unavailable_reason": reason or None, "broker_counts": counts, "card_vs_broker": compare,
        "trades_closed": len(trades), "trades_by_state": by_state,
        "trades_with_entry_facts": fact_trades, "trades_partial_recorded": partial,
        "first_closed_at": trades[0]["closed_at"] if trades else None,
        "last_closed_at": trades[-1]["closed_at"] if trades else None,
        "totals": totals, "last_trade": last,
        "by_strategy": group_by(trades, lambda t: t["strategy"], min_sample),
        "by_window": group_by(trades, lambda t: t["window"], min_sample),
        "by_side": group_by(trades, lambda t: t["side"], min_sample),
        "by_symbol": group_by(trades, lambda t: t["symbol"], min_sample),
        # ٢٠٢٦-١٠-١٧ (ختم المالك «NQ»، الخطوة 20: «لازم تعرف أداءها السابق بالأشهر الماضية إذا خسرانة أو ربحانة،
        # والأسبوع واليوم»): كلّ استراتيجيّة بشهرها وأسبوعها ويومها — بتاريخ تركيا لوقت الإغلاق.
        "by_strategy_period": strategy_periods(trades, min_sample, now),
        "trades": [trade_row(t) for t in trades],
        "min_sample": min_sample, "definitions_ar": DEFINITIONS_AR, **table}
    if last is None:
        head = "لا صفقة مغلقة في الدفتر بعد"
    else:
        head = "آخر صفقة: %s %s (%s) ⟸ %s (%+.2f$)" % (
            last["side_ar"], last["symbol"], last["strategy_ar"], _signed_r(last["result_r"]),
            last["profit_usd"])
    summary = "%s · %s · %s" % (head, _totals_text(totals, compare, partial),
                                _gap_text(table, fact_trades, min_sample))
    return {"id": PAYLOAD_ID, "status": "ok", "facts": body, "computed_at": now,
            "summary_ar": summary, "source": SOURCE if broker is not None else SOURCE_CARDS}
