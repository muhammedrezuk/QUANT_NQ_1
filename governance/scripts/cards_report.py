# -*- coding: utf-8 -*-
"""بطاقات الصفقات — صفحةٌ تُقرأ بأيّ متصفّح، من السجلّ لا من اللوحة.

بأمر المالك ٢٠٢٦-٠٩-١٨: **عرض البطاقة وقراءتها عند المخازن** — والكتابة فيها
عند من يكتب (٤٦٥ و٥٥٢ و٥٦٣). وحكمه في البطاقة نفسها:

    «صار يسلمك بطاقة وانت تكتب عليه: نفّذت بطاقة بحكم لوت ستوب هدف،
     ربحت خسرت انزلقت، كلّها بهل بطاقة. **بالأخير أنا لما بدي أراجع
     صفقة بسحب بطاقتها**.»

و`trade_cards.db` قاعدة SQLite: لا متصفّح يفتحها، والمفكّرة تُظهر رموزًا. وهذه
الأداة تقرأها وتكتب صفحة HTML قائمةً بذاتها (بلا إنترنت ولا مكتبات) ثمّ تفتحها.

**والقسمة من العقد لا من اجتهادي**: `shared/trade_card.py` يعلن
`ANALYSIS_FIELDS` (١٨) و`MONEY_FIELDS` (١٥) والحالات الستّ، فتُقرأ منه — وأيّ
حقلٍ يُضاف هناك غدًا يظهر هنا بلا تعديل. وإن تعذّر استيراده تعمل الأداة
بنسخةٍ احتياطيّة **وتقول ذلك في الصفحة** بدل أن تصمت.

⚠️ **والمسار مطلقٌ من جذر المشروع عن قصد.** في المشروع مجلّدان باسم
`var/store`: الحيّ تحت `forex_runtime`، وآخرُ ميّتٌ تحت الجذر فيه هياكل فارغة.
وحلُّ المسار نسبةً لمجلّد العمل هو بعينه الداء الذي جعل النسخ الاحتياطيّة
تصوّر الشجرة الميّتة (مقيس ٢٠٢٦-٠٩-١٨: ٢٤٬٥٧٦ بايت مقابل ٢ جيجا).
"""
from __future__ import annotations

import html
import json
import os
import sqlite3
import sys
import time
import webbrowser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "forex_runtime", "var", "store", "trade_cards.db")
OUT = os.path.join(ROOT, "forex_runtime", "var", "بطاقات.html")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CONTRACT = "من العقد `shared/trade_card.py`"
try:  # المصدر الواحد للحقيقة — لا تُنسخ القوائم بيد
    from shared.trade_card import (ANALYSIS_FIELDS, MONEY_FIELDS,
                                   LIVE_STATES, FINAL_STATES)
except Exception as _exc:  # noqa: BLE001 — تعذُّر الاستيراد لا يُسقط التقرير
    CONTRACT = "⚠️ تعذّر استيراد العقد (%s) — نسخة احتياطيّة قد تتخلّف عنه" % _exc
    ANALYSIS_FIELDS = frozenset((
        "side", "decision_id", "gate_request_id", "entry", "stop", "target",
        "stop_points", "target_points", "stop_pct", "target_pct",
        "spread_points", "rr", "rr_rule", "reason",
        "peak_points", "worst_points", "peak_r", "worst_r"))
    MONEY_FIELDS = frozenset((
        "verdict_552", "volume", "sent_stop", "sent_target", "rr_at_send",
        "risk_amount", "symbol_budget", "budget_left", "ticket", "fill_price",
        "exit_price", "entry_slip", "stop_overshoot", "outcome", "profit"))
    LIVE_STATES = ("OPEN", "DISPATCHED", "FILLED")
    FINAL_STATES = ("CLOSED", "REJECTED", "EXPIRED")

# ترتيب العرض داخل كل مجموعة — الأهمّ أوّلًا، لا ترتيب الجدول.
ORDER_ANALYSIS = ("side", "entry", "stop", "target", "stop_points", "target_points",
                  "rr", "rr_rule", "stop_pct", "target_pct", "spread_points",
                  "peak_points", "worst_points", "peak_r", "worst_r", "reason",
                  "decision_id", "gate_request_id")
ORDER_MONEY = ("verdict_552", "volume", "sent_stop", "sent_target", "rr_at_send",
               "risk_amount", "symbol_budget", "budget_left", "ticket",
               "fill_price", "exit_price", "entry_slip", "stop_overshoot",
               "outcome", "profit")

AR_FIELD = {
    "side": "الجهة", "entry": "الدخول", "stop": "الوقف", "target": "الهدف",
    "stop_points": "نقاط الوقف", "target_points": "نقاط الهدف",
    "stop_pct": "الوقف ٪", "target_pct": "الهدف ٪", "spread_points": "السبريد (نقاط)",
    "rr": "عائد ∕ مخاطرة", "rr_rule": "قاعدة العائد", "reason": "السبب",
    "peak_points": "أقصى تقدّم (نقاط)", "worst_points": "أقصى تراجع (نقاط)",
    "peak_r": "أقصى تقدّم (R)", "worst_r": "أقصى تراجع (R)",
    "decision_id": "هويّة القرار", "gate_request_id": "هويّة الطلب",
    "verdict_552": "حكم ٥٥٢", "volume": "اللوت", "sent_stop": "الوقف المُرسَل",
    "sent_target": "الهدف المُرسَل", "rr_at_send": "العائد عند الإرسال",
    "risk_amount": "المال المعرَّض", "symbol_budget": "ميزانيّة الرمز",
    "budget_left": "الباقي من الميزانيّة", "ticket": "التذكرة",
    "fill_price": "سعر التنفيذ", "exit_price": "سعر الخروج",
    "entry_slip": "انزلاق الدخول", "stop_overshoot": "تجاوز الوقف",
    "outcome": "النتيجة", "profit": "الربح",
}
AR_SIDE = {"buy": "شراء", "sell": "بيع", "wait": "انتظار"}
AR_STATE = {"OPEN": "مفتوحة", "DISPATCHED": "أُرسلت", "FILLED": "نُفّذت",
            "CLOSED": "أُغلقت", "REJECTED": "مرفوضة", "EXPIRED": "انتهت"}


def _t(value, fmt="%Y-%m-%d %H:%M:%S"):
    if not value:
        return "—"
    try:
        return time.strftime(fmt, time.localtime(float(value)))
    except (TypeError, ValueError, OSError):
        return "—"


def _n(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "نعم" if value else "لا"
    if isinstance(value, float):
        return ("%.5f" % value).rstrip("0").rstrip(".") or "0"
    return str(value)


def side_vs_levels(card):
    """أمستويات البطاقة متّسقة مع جهتها؟ — يُحسب ولا يُكتب بيد.

    شراء: الوقف **تحت** الدخول والهدف **فوقه**. بيع: العكس. والخلاف يُعرَض
    كما هو ولا يُفسَّر — قراءةٌ من القرص، والتفسير عند صاحب البطاقة.
    """
    side, entry = (card.get("side") or "").lower(), card.get("entry")
    stop, target = card.get("stop"), card.get("target")
    if entry is None or stop is None or target is None or side not in ("buy", "sell"):
        return None
    stop_above, target_above = stop > entry, target > entry
    want_above = (side == "sell")
    ok = (stop_above == want_above) and (target_above != want_above)
    return {"ok": ok,
            "stop": "فوق الدخول" if stop_above else "تحت الدخول",
            "target": "فوق الدخول" if target_above else "تحت الدخول"}


def read_cards():
    if not os.path.isfile(DB):
        return None, "لا ملفّ على المسار"
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"),
                               uri=True, timeout=20)
    except sqlite3.Error as exc:
        return None, "تعذّر الفتح: %s" % exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=20000")
        integrity = conn.execute("PRAGMA quick_check(1)").fetchone()[0]
        cards = []
        for row in conn.execute("SELECT * FROM cards ORDER BY card_no DESC"):
            card = {k: row[k] for k in row.keys()}
            try:
                card["body"] = json.loads(card.pop("body_json", None) or "{}")
            except (ValueError, TypeError):
                card["body"] = {}
            card["writes"] = [dict(w) for w in conn.execute(
                "SELECT author, field, value_json, hits, last_at FROM card_writes"
                " WHERE card_no=? ORDER BY hits DESC", (card["card_no"],))]
            cards.append(card)
        return {"cards": cards, "integrity": integrity,
                "size": os.path.getsize(DB), "mtime": os.path.getmtime(DB)}, ""
    except sqlite3.Error as exc:
        return None, "خطأ قراءة: %s" % exc
    finally:
        conn.close()


CSS = """
:root{--ground:#f1f4f3;--surface:#fff;--sheet:#fbfcfc;--ink:#16201d;--muted:#5e6f6a;
--faint:#8a9a95;--line:#dbe3e0;--accent:#0d574f;--buy:#0f6b60;--sell:#a33c19;
--wait:#8a6414;--warn-bg:#fdf3e7;--warn-line:#e3c08a;--warn-ink:#7a4f10}
@media(prefers-color-scheme:dark){:root{--ground:#0e1513;--surface:#161f1c;--sheet:#131b19;
--ink:#e4ebe8;--muted:#9aaba6;--faint:#6d7f7a;--line:#26332f;--accent:#5fb3a6;
--buy:#4fae9f;--sell:#e0764c;--wait:#d2a444;--warn-bg:#261d0f;--warn-line:#5a441f;
--warn-ink:#e8c68a}}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);direction:rtl;
font-family:"Segoe UI",system-ui,sans-serif;font-size:15px;line-height:1.7}
.wrap{max-width:62rem;margin:0 auto;padding-inline:16px;padding-block:26px 48px}
h1{font-size:1.9rem;margin:0;letter-spacing:-.01em}
h2{font-size:1.05rem;margin-block:2rem .7rem;color:var(--muted);font-weight:600}
.lede{color:var(--muted);margin-top:.4rem;max-width:46rem}
.where{margin-top:1.2rem;background:var(--surface);border:1px solid var(--line);
border-radius:4px;padding:.8rem 1rem;display:flex;flex-wrap:wrap;gap:.4rem 1.4rem;align-items:baseline}
.where code{direction:ltr;font-family:ui-monospace,Consolas,monospace;font-size:.78rem;
color:var(--accent);word-break:break-all}
.where span{font-size:.8rem;color:var(--muted)}
.where b{color:var(--ink);font-variant-numeric:tabular-nums}
.card{background:var(--sheet);border:1px solid var(--line);
border-inline-start:3px solid var(--edge,var(--faint));border-radius:4px;margin-top:.9rem}
.chead{display:flex;flex-wrap:wrap;gap:.4rem .8rem;align-items:baseline;
padding:.7rem 1rem;border-bottom:1px solid var(--line);background:var(--surface)}
.no{color:var(--faint);font-weight:700}
.sym{font-size:1.12rem;font-weight:700}
.pill{font-size:.72rem;font-weight:600;padding:.1rem .5rem;border-radius:999px;border:1px solid currentColor}
.when{margin-inline-start:auto;font-size:.76rem;color:var(--faint);font-variant-numeric:tabular-nums}
.grp{padding:.5rem 1rem 0}
.grp h3{font-size:.74rem;letter-spacing:.1em;color:var(--faint);margin:.5rem 0 .2rem;font-weight:600}
.nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
gap:0 1.2rem;font-variant-numeric:tabular-nums}
.n{display:flex;justify-content:space-between;gap:.5rem;padding:.24rem 0;
border-bottom:1px dotted var(--line);font-size:.85rem}
.n s{text-decoration:none;color:var(--muted)}
.n b{direction:ltr;font-weight:600;max-width:58%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.n.gap b{color:var(--faint);font-weight:400}
.why{padding:.5rem 1rem .2rem;font-size:.85rem;color:var(--muted)}
.why b{color:var(--ink)}
.note{margin:.7rem 1rem 1rem;padding:.55rem .85rem;border:1px dashed var(--line);
border-radius:3px;font-size:.8rem;color:var(--muted)}
.note b{color:var(--ink)}.note code{direction:ltr;font-size:.74rem;color:var(--faint)}
.flag{margin:.7rem 1rem;padding:.55rem .85rem;background:var(--warn-bg);
border:1px solid var(--warn-line);border-radius:3px;font-size:.83rem;color:var(--warn-ink)}
details{margin:0 1rem 1rem}summary{cursor:pointer;font-size:.82rem;color:var(--accent)}
.scroll{overflow-x:auto;margin-top:.5rem}
table{border-collapse:collapse;width:100%;font-size:.8rem;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:.32rem .65rem;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:.7rem;letter-spacing:.05em;color:var(--faint)}
td.v{direction:ltr;color:var(--muted)}td.a{font-weight:600;color:var(--accent)}
footer{margin-top:2.4rem;padding-top:1rem;border-top:1px solid var(--line);
font-size:.83rem;color:var(--muted)}
footer b{color:var(--ink)}
"""


def _rows(card, order, group):
    """صفوف مجموعةٍ واحدة — والغائب يُسمّى ولا يُحذف."""
    filled, missing = [], []
    for field in order:
        if field not in group:
            continue
        value = _n(card.get(field))
        label = AR_FIELD.get(field, field)
        if field == "side" and value:
            value = AR_SIDE.get(str(value).lower(), value)
        (filled if value is not None else missing).append((field, label, value))
    return filled, missing


def _card_html(card, e):
    side = (card.get("side") or "").lower()
    edge = {"buy": "var(--buy)", "sell": "var(--sell)"}.get(side, "var(--faint)")
    state = card.get("state")
    out = ['<article class="card" style="--edge:%s">' % edge,
           '<div class="chead"><span class="no">#%s</span><span class="sym">%s</span>'
           % (card.get("card_no"), e(str(card.get("symbol") or "—"))),
           '<span class="pill" style="color:%s">%s</span>' % (edge, e(AR_SIDE.get(side, side or "—"))),
           '<span class="pill" style="color:var(--wait)">%s</span>'
           % e(AR_STATE.get(state, str(state or "—"))),
           '<span class="when">فُتحت %s · آخر تحديث %s%s</span></div>'
           % (_t(card.get("opened_at"), "%m-%d %H:%M"), _t(card.get("updated_at"), "%m-%d %H:%M"),
              (" · أُغلقت %s" % _t(card.get("closed_at"), "%m-%d %H:%M")) if card.get("closed_at") else "")]

    for title, order, group in (("التحليل", ORDER_ANALYSIS, ANALYSIS_FIELDS),
                                ("المال والتنفيذ", ORDER_MONEY, MONEY_FIELDS)):
        filled, missing = _rows(card, order, group)
        out.append('<div class="grp"><h3>%s</h3><div class="nums">' % e(title))
        for _f, label, value in filled:
            out.append('<div class="n"><s>%s</s><b>%s</b></div>' % (e(label), e(str(value))))
        if not filled:
            out.append('<div class="n gap"><s>—</s><b>لم يُكتب منها شيء بعد</b></div>')
        out.append("</div></div>")
        if missing:
            out.append('<p class="note">⚠️ <b>لم يُكتب بعد</b> في %s (%d): %s</p>'
                       % (e(title), len(missing),
                          e(" · ".join(label for _f, label, _v in missing))))

    body = card.get("body") or {}
    if body:
        out.append('<p class="why"><b>الإعداد:</b> %s. <b>سبب الهدف:</b> %s. '
                   "<b>ما يُبطلها:</b> %s</p>"
                   % (e(str(body.get("setup_type", "—"))),
                      e(str(body.get("target_reason", "—"))),
                      e(str(body.get("invalidation_reason", "—")))))

    check = side_vs_levels(card)
    if check and not check["ok"]:
        out.append('<p class="flag"><b>لاحظ:</b> الجهة <b>%s</b>، والوقف <b>%s</b> '
                   "والهدف <b>%s</b> — وهذا شكل الجهة المقابلة. ملاحظةٌ من القرص "
                   "لا حكم؛ تفسيرها عند صاحب البطاقة.</p>"
                   % (e(AR_SIDE.get(side, side)), e(check["stop"]), e(check["target"])))

    writes = card.get("writes") or []
    if writes:
        authors = len({w["author"] for w in writes})
        out.append("<details><summary>مَن كتب فيها — %d سطرًا من %d قسمًا</summary>"
                   '<div class="scroll"><table><thead><tr><th>القسم</th><th>الحقل</th>'
                   "<th>آخر قيمة</th><th>مرّات</th><th>آخر كتابة</th></tr></thead><tbody>"
                   % (len(writes), authors))
        for w in writes:
            out.append('<tr><td class="a">%s</td><td>%s</td><td class="v">%s</td>'
                       "<td>%s</td><td>%s</td></tr>"
                       % (e(str(w["author"])),
                          e(AR_FIELD.get(str(w["field"]), str(w["field"]))),
                          e(str(w["value_json"])[:44]), w["hits"],
                          _t(w["last_at"], "%H:%M:%S")))
        out.append("</tbody></table></div></details>")
    out.append("</article>")
    return "".join(out)


def build(data):
    e = html.escape
    cards = data["cards"]
    live = [c for c in cards if c.get("state") in LIVE_STATES]
    final = [c for c in cards if c.get("state") not in LIVE_STATES]
    odd = sum(1 for c in cards
              if (side_vs_levels(c) or {"ok": True})["ok"] is False)

    out = ['<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           "<title>بطاقات الصفقات</title><style>", CSS, "</style></head><body>",
           '<div class="wrap">', "<h1>بطاقات الصفقات</h1>",
           '<p class="lede">البطاقة ورقةٌ واحدة لكلّ زوج: يفتحها التحليل، ويكتب '
           "فيها قسم المال عند الأمر وعند النتيجة. هذه قراءةٌ مباشرة من السجلّ — "
           "لا من اللوحة — تُحدَّث كلّما شغّلت الزرّ.</p>",
           '<div class="where"><code>%s</code>' % e(DB),
           "<span>الحجم <b>%s</b> بايت</span>" % f"{data['size']:,}",
           "<span>السلامة <b>%s</b></span>"
           % e("سليمة" if data["integrity"] == "ok" else str(data["integrity"])),
           "<span>آخر كتابة <b>%s</b></span>" % _t(data["mtime"], "%H:%M:%S"),
           "<span>قُرئت <b>%s</b></span>" % _t(time.time()),
           "<span>حيّة <b>%d</b> · منتهية <b>%d</b></span>" % (len(live), len(final))]
    if odd:
        out.append("<span style='color:var(--warn-ink)'>مستوياتها تخالف جهتها "
                   "<b>%d</b></span>" % odd)
    out.append("</div>")

    out.append("<h2>حيّة الآن (%d)</h2>" % len(live))
    if not live:
        out.append('<p class="lede">لا بطاقة حيّة — لا زوجَ مشغولًا الآن.</p>')
    for card in live:
        out.append(_card_html(card, e))

    if final:
        out.append("<h2>منتهية (%d)</h2>" % len(final))
        out.append("<details><summary>افتحها — مطويّةٌ كي لا تزحم الحيّ</summary>")
        for card in final:
            out.append(_card_html(card, e))
        out.append("</details>")

    out.append("<footer><p><b>القسمة من العقد لا من الأداة:</b> %s — "
               "%d حقل تحليل و%d حقل مال. وأيّ حقلٍ يُضاف هناك يظهر هنا بلا تعديل.</p>"
               % (e(CONTRACT), len(ANALYSIS_FIELDS), len(MONEY_FIELDS)))
    out.append("<p><b>والفراغ خبرٌ لا نقصُ عرض:</b> كلّ حقلٍ لم يُكتب بعد يُسمّى "
               "باسمه — بطاقةٌ بلا مالٍ معرَّض تقول إنّ حارس المال لم يقس هذه الصفقة.</p>")
    out.append("<p>البطاقات لا تُؤرشَف ولا تُنظَّف ولا يقصّها سقف، وسلامتها مفحوصة "
               "في الذرّة ٧١٧ قراءةً فقط — البطاقة المغلقة عيّنةُ تعلّم. "
               "والصفحة قائمةٌ بذاتها: لا إنترنت ولا مكتبات.</p>")
    out.append("</footer></div></body></html>")
    return "".join(out)


def main() -> int:
    data, error = read_cards()
    if data is None:
        print("⛔ %s" % error)
        print("   المسار: %s" % DB)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(build(data))
    live = sum(1 for c in data["cards"] if c.get("state") in LIVE_STATES)
    print("البطاقات: %d (حيّة %d) · السلامة: %s"
          % (len(data["cards"]), live, data["integrity"]))
    print("العقد   : %s" % CONTRACT)
    print("الصفحة  : %s" % OUT)
    try:
        webbrowser.open("file:///" + OUT.replace("\\", "/"))
        print("فُتحت في المتصفّح.")
    except Exception as exc:  # noqa: BLE001 — الفتح رفاهية لا شرط
        print("افتحها بنفسك (تعذّر الفتح التلقائيّ: %s)" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
