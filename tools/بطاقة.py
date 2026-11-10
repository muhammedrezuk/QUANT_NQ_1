# -*- coding: utf-8 -*-
"""بطاقة الصفقة — تُقرأ كاملةً بالعربيّة، من التحليل إلى التنفيذ.

بختم المالك ٢٠٢٦-٠٩-١٨:

    «صار يسلمك بطاقة وانت تكتب عليه: نفّذت بطاقة بحكم لوت ستوب هدف،
     ربحت خسرت انزلقت، كلّها بهل بطاقة. بالأخير أنا لما بدي أراجع
     صفقة بسحب بطاقتها.»

وبأمره اللاحق: **بالعربيّة كاملة** — لا اسم حقلٍ إنجليزيّ في وجه المالك.
الأرقام لاتينيّة كما في كلّ لوحات المشروع.

    python tools/بطاقة.py            آخر بطاقة
    python tools/بطاقة.py 17         بطاقة بعينها
    python tools/بطاقة.py XAUUSD     آخر بطاقة لرمز
    python tools/بطاقة.py حيّة        كلّ البطاقات الحيّة
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.trade_card import CardStore  # noqa: E402

DB = ROOT / "forex_runtime" / "var" / "store" / "trade_cards.db"

#: اسمٌ عربيٌّ لكلّ حقل، مجموعًا بمن يكتبه — والترتيب هو ترتيب الحياة.
GROUPS = (
    ("التحليل — ما رآه قبل الأمر", (
        ("side", "الجهة"),
        ("entry", "سعر الدخول"),
        ("stop", "الوقف"),
        ("target", "الهدف"),
        ("stop_points", "مسافة الوقف"),
        ("target_points", "مسافة الهدف"),
        ("stop_pct", "الوقف ٪ من السعر"),
        ("target_pct", "الهدف ٪ من السعر"),
        ("spread_points", "السبريد وقتها"),
        ("rr", "النسبة عند البناء"),
        ("rr_rule", "قاعدة حساب النسبة"),
        ("reason", "سبب الحكم"),
        ("peak_r", "أقصى ما بلغته (بالمخاطرة)"),
        ("worst_r", "أسوأ ما بلغته (بالمخاطرة)"),
        ("peak_points", "أقصى ما بلغته (بالسعر)"),
        ("worst_points", "أسوأ ما بلغته (بالسعر)"),
    )),
    ("الأمر — كما خرج إلى الوسيط", (
        ("verdict_552", "حكم البوّابة الأخيرة"),
        ("volume", "اللوت"),
        ("sent_stop", "الوقف المرسل"),
        ("sent_target", "الهدف المرسل"),
        ("rr_at_send", "النسبة عند الإرسال"),
        ("risk_amount", "المال المعرَّض"),
        ("symbol_budget", "ميزانيّة الرمز"),
        ("budget_left", "المتبقّي من الميزانيّة"),
    )),
    ("النتيجة — ما وقع فعلًا", (
        ("ticket", "رقم التذكرة"),
        ("fill_price", "سعر التنفيذ"),
        ("exit_price", "سعر الخروج"),
        ("profit", "الربح أو الخسارة"),
        ("entry_slip", "انزلاق الدخول"),
        ("stop_overshoot", "تجاوز الوقف عند الخروج"),
        ("outcome", "الخاتمة"),
    )),
    ("الهويّة والوقت", (
        ("decision_id", "هويّة القرار"),
        ("gate_request_id", "هويّة طلب البوّابة"),
        ("opened_at", "فُتحت"),
        ("updated_at", "آخر كتابة"),
        ("closed_at", "أُغلقت"),
    )),
)

STATES = {"OPEN": "مفتوحة", "DISPATCHED": "أُرسلت", "FILLED": "نُفِّذت",
          "CLOSED": "مغلقة", "REJECTED": "مرفوضة", "EXPIRED": "منتهية"}
SIDES = {"buy": "شراء", "sell": "بيع", "wait": "انتظار"}
OUTCOMES = {"WIN": "رابحة", "LOSS": "خاسرة", "BREAKEVEN": "تعادل"}
TIME_FIELDS = {"opened_at", "updated_at", "closed_at"}


def _clock(value):
    import datetime
    try:
        return datetime.datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return value


def _show(field, value):
    """القيمة كما يقرؤها المالك — لا رمزًا إنجليزيًّا ولا طابعًا خامًا."""
    if field in TIME_FIELDS:
        return _clock(value)
    if field in ("side",):
        return SIDES.get(str(value).lower(), value)
    if field == "outcome":
        return OUTCOMES.get(str(value).upper(), value)
    if field == "verdict_552":
        return value
    if isinstance(value, float):
        return ("%.8f" % value).rstrip("0").rstrip(".")
    return value


def render(store: CardStore, card: dict) -> None:
    head = "بطاقة رقم %s   ·   %s   ·   %s" % (
        card.get("card_no"), card.get("symbol"),
        STATES.get(str(card.get("state")), card.get("state")))
    print()
    print("=" * 66)
    print("  " + head)
    print("=" * 66)
    for title, fields in GROUPS:
        rows = [(label, _show(name, card.get(name)))
                for name, label in fields if card.get(name) is not None]
        print()
        print("  ── %s ──" % title)
        if not rows:
            print("     (لم يُكتب فيها شيء بعد)")
            continue
        for label, value in rows:
            print("     %-26s %s" % (label, value))
    # حقولٌ ينتظرها المالك ولم تُكتب — الفراغ خبرٌ لا صمت.
    missing = [label for _, fields in GROUPS for name, label in fields
               if card.get(name) is None and name in
               ("risk_amount", "volume", "verdict_552", "profit", "outcome",
                "ticket", "entry_slip", "rr_at_send")]
    if missing:
        print()
        print("  ⚠️  لم يُكتب بعد: " + " · ".join(missing))
    writes = store.writes(card["card_no"])
    if writes:
        print()
        print("  ── من كتب ماذا (%d كتابة) ──" % len(writes))
        for row in writes:
            value = row.get("value", row.get("value_json"))
            print("     %-6s %-22s %s" % (row.get("author"), row.get("field"),
                                          str(value)[:44]))


def main() -> int:
    if not DB.is_file():
        print("لا مخزن بطاقات على %s" % DB)
        return 1
    store = CardStore(str(DB))
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    connection = store.connect()
    try:
        if arg in ("حيّة", "حية", "live"):
            numbers = [r[0] for r in connection.execute(
                "SELECT card_no FROM cards WHERE state IN "
                "('OPEN','DISPATCHED','FILLED') ORDER BY card_no").fetchall()]
        elif arg.isdigit():
            numbers = [int(arg)]
        elif arg:
            numbers = [r[0] for r in connection.execute(
                "SELECT card_no FROM cards WHERE symbol=? ORDER BY card_no DESC LIMIT 1",
                (arg.upper(),)).fetchall()]
        else:
            numbers = [r[0] for r in connection.execute(
                "SELECT card_no FROM cards ORDER BY card_no DESC LIMIT 1").fetchall()]
    finally:
        connection.close()
    if not numbers:
        print("لا بطاقة تطابق: %s" % (arg or "(الأحدث)"))
        return 1
    for number in numbers:
        card = store.card(number)
        if card:
            render(store, card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
