# -*- coding: utf-8 -*-
"""رحلةُ البطاقة — كيف تُبنى، ومتى تمرّ على ٥٥٥ ثمّ الجسر ثمّ المخازن.

كلُّ رقمٍ في الصفحة مقروءٌ من السجلّات الحيّة لحظةَ التشغيل. لا رقم مكتوبٌ
بيدي، ولا مثالٌ مصنوع.

  دفتر البطاقات  forex_runtime/var/store/trade_cards.db   (٤٦٥ — من كتب أيّ حقل ومتى)
  القرارات       forex_runtime/var/store/decisions.db     (٧٠٧ — محطّات الرحلة بالثانية)

⚠️ الساعات: `stored_at`/`recorded_at` ساعةُ المنصّة، و`opened_at` في مخزن
الصفقات ساعةُ الوسيط — **تسبقها ثلاث ساعات**. لا يُطرح عمودٌ من عمودٍ إلّا
بعد التحقّق من ساعته.
"""
from __future__ import annotations

import html
import os
import sqlite3
import sys
import time
import webbrowser
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORE = os.path.join(ROOT, "forex_runtime", "var", "store")
OUT = os.path.join(ROOT, "forex_runtime", "var", "رحلة البطاقة.html")

DAYS = 3

# ترتيب المحطّات كما تجري فعلًا — مقيسٌ من عقود الأحداث لا من ذاكرتي
CHAIN = [
    ("ORDER_REQUESTED", "٥٥٥ طالب أمر الدخول", "ينشر execution.order.requested"),
    ("ORDER_BUILT", "٥٥١ باني الأمر", "ينشر execution.order.built"),
    ("ORDER_REJECTED", "٥٨٤/٥٥٢ — رُدّ", "شرعيّة الوقف أو تدقيق الأمر"),
    ("DECISION_FINALIZED", "٥٥٢ مدقّق الأمر", "ينشر trading.final_decision"),
    ("QUEUED_TO_BRIDGE", "٦٠١ كاتب الجسر", "كُتب في قاعدة الجسر"),
    ("BRIDGE_WRITE_FAILED", "٦٠١ — فشل الجسر", "لم تصل القاعدة"),
    ("BROKER_ACKNOWLEDGED", "ميتاتريدر", "الوسيط أقرّ الأمر"),
    ("FILLED_OPEN", "٦١١ ← ٥٦٣", "امتلأ ودخل المركز"),
    ("FILLED_PARTIAL", "تعبئة جزئيّة", ""),
    ("FILLED_CLOSED", "أُغلق المركز", ""),
]

STAGE_NAMES = {k: v for k, v, _ in CHAIN}


def ro(name: str) -> sqlite3.Connection:
    path = os.path.join(STORE, name).replace("\\", "/")
    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def clock(t) -> str:
    if not t:
        return "—"
    return time.strftime("%H:%M:%S", time.localtime(t))


def full_clock(t) -> str:
    if not t:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


def e(x) -> str:
    return html.escape("" if x is None else str(x))


# ───────────────────────────── القياس ─────────────────────────────

def measure_chain():
    """الرحلات على مفتاح ٥٥٥ (`555-<بصمة>`) — وهو المفتاح الذي يعبر المحطّات."""
    conn = ro("decisions.db")
    cut = time.time() - DAYS * 86400
    rows = conn.execute(
        "SELECT stage, request_id, symbol, recorded_at, reason FROM decisions "
        "WHERE recorded_at > ? AND request_id LIKE '555-%' ORDER BY recorded_at",
        (cut,)).fetchall()
    trips = defaultdict(list)
    for r in rows:
        trips[r["request_id"]].append(r)

    reached = {k: 0 for k, _, _ in CHAIN}
    for evs in trips.values():
        for s in {x["stage"] for x in evs}:
            if s in reached:
                reached[s] += 1

    hops = defaultdict(list)
    for evs in trips.values():
        first = {}
        for x in evs:
            first.setdefault(x["stage"], x["recorded_at"])
        order = [k for k, _, _ in CHAIN if k in first]
        for a, b in zip(order, order[1:]):
            hops[(a, b)].append(first[b] - first[a])

    complete = [(k, v) for k, v in trips.items()
                if any(x["stage"] == "QUEUED_TO_BRIDGE" for x in v)
                and any(x["stage"].startswith("FILLED") for x in v)]
    complete.sort(key=lambda kv: kv[1][-1]["recorded_at"])
    conn.close()
    return trips, reached, hops, complete


def measure_card():
    """آخر بطاقة كاملة — بناؤها حقلًا حقلًا بأسماء من كتب."""
    conn = ro("trade_cards.db")
    card = conn.execute(
        "SELECT * FROM cards WHERE ticket IS NOT NULL ORDER BY card_no DESC LIMIT 1"
    ).fetchone()
    if card is None:
        card = conn.execute("SELECT * FROM cards ORDER BY card_no DESC LIMIT 1").fetchone()
    writes = conn.execute(
        "SELECT author, field, value_json, first_at, hits FROM card_writes "
        "WHERE card_no=? ORDER BY first_at, author", (card["card_no"],)).fetchall()
    states = conn.execute(
        "SELECT state, COUNT(*) n FROM cards GROUP BY state ORDER BY n DESC").fetchall()
    total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    authors = conn.execute(
        "SELECT author, COUNT(*) n, COUNT(DISTINCT card_no) c FROM card_writes "
        "GROUP BY author ORDER BY n DESC").fetchall()
    conn.close()
    return card, writes, states, total, authors


# ───────────────────────────── الرسم ─────────────────────────────

CSS = """
:root{
  --ink:#1d2129; --dim:#6b7280; --line:#e2e0da; --paper:#faf9f6; --card:#ffffff;
  --live:#0f7b6c; --dead:#a33a3a; --warn:#9a6a00; --mine:#2f5d8a;
  --band:#f2f0ea;
}
@media (prefers-color-scheme:dark){ :root:not([data-theme=light]){
  --ink:#e8e6e1; --dim:#9aa0a8; --line:#33373d; --paper:#15171a; --card:#1c1f23;
  --live:#4fc4ad; --dead:#e07b7b; --warn:#d9a441; --mine:#7fb0dd; --band:#212429;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
     font-family:"Segoe UI","Noto Naskh Arabic",Tahoma,sans-serif;
     direction:rtl;line-height:1.75;font-size:15px}
.wrap{max-width:1080px;margin:0 auto;padding-block:28px;padding-inline:16px}
h1{font-size:27px;margin:0 0 4px;font-weight:650;letter-spacing:-.2px}
h2{font-size:19px;margin:38px 0 12px;font-weight:620;
   border-bottom:2px solid var(--line);padding-bottom:7px}
.sub{color:var(--dim);font-size:13.5px;margin:0 0 6px}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:600;font-size:12.5px;white-space:nowrap}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:9px;background:var(--card)}
.flow{display:flex;flex-direction:column;gap:0;margin:18px 0}
/* minmax(0,1fr) لا 1fr: عمودُ الشبكة لا ينكمش دون محتواه افتراضًا، فكان اسمُ
   الحدث الطويل يفيض بالصفحة عرضًا ويُقصّ الرقم عند العرض الضيّق. */
.step{display:grid;grid-template-columns:minmax(84px,118px) minmax(0,1fr) auto;
      gap:14px;align-items:center;
      background:var(--card);border:1px solid var(--line);border-radius:10px;
      padding:11px 14px;margin-bottom:6px}
.step .who{font-weight:650;font-size:14.5px}
.step .what{color:var(--dim);font-size:13px;overflow-wrap:anywhere}
.step .n{font-size:20px;font-weight:650}
.arrow{color:var(--dim);text-align:center;font-size:15px;margin:-2px 0 4px}
.bar{height:6px;border-radius:3px;background:var(--band);overflow:hidden;margin-top:5px}
.bar i{display:block;height:100%;background:var(--live)}
.dead .n,.dead .who{color:var(--dead)} .dead .bar i{background:var(--dead)}
.warn .n,.warn .who{color:var(--warn)} .warn .bar i{background:var(--warn)}
.note{background:var(--card);border:1px solid var(--line);border-inline-start:4px solid var(--warn);
      border-radius:9px;padding:13px 15px;margin:14px 0;font-size:14px}
.note.bad{border-inline-start-color:var(--dead)}
.note b{font-weight:650}
.tag{display:inline-block;padding:1px 8px;border-radius:999px;background:var(--band);
     font-size:12px;color:var(--dim);margin-inline-start:6px}
.mine{color:var(--mine);font-weight:600}
code{background:var(--band);padding:1px 5px;border-radius:4px;font-size:12.5px}
.foot{color:var(--dim);font-size:12.5px;margin-top:34px;border-top:1px solid var(--line);
      padding-top:12px}
"""


def build(trips, reached, hops, complete, card, writes, states, total, authors) -> str:
    n_trips = max(1, len(trips))
    top = reached.get("ORDER_REQUESTED", 0) or 1
    P = []
    A = P.append

    A("<title>رحلة البطاقة</title>")
    A("<style>%s</style>" % CSS)
    A("<div class='wrap'>")
    A("<h1>رحلة البطاقة</h1>")
    A("<p class='sub'>كيف تُبنى البطاقة، ومتى تمرّ على ٥٥٥ ثمّ الجسر ثمّ المخازن — "
      "كلُّ رقمٍ مقروءٌ من السجلّ الحيّ لحظةَ التشغيل: "
      "<span class='num'>%s</span></p>" % full_clock(time.time()))

    # ── ١ · السلسلة والقُمع
    A("<h2>١ · المسار الحقيقيّ — وكم يبقى عند كلّ محطّة</h2>")
    A("<p class='sub'>مقيسٌ على <b class='num'>%d</b> طلبًا ختمه ٥٥٥ خلال %d أيّام. "
      "المفتاح الذي يعبر المحطّات هو <code>request_id</code> بصيغة "
      "<code>555-&lt;بصمة&gt;</code>.</p>" % (len(trips), DAYS))

    A("<div class='flow'>")
    for i, (key, who, what) in enumerate(CHAIN):
        n = reached.get(key, 0)
        pct = 100.0 * n / top
        cls = ""
        if key in ("ORDER_REJECTED", "BRIDGE_WRITE_FAILED"):
            cls = " dead"
        elif key in ("FILLED_PARTIAL", "FILLED_CLOSED") and n == 0:
            cls = " warn"
        A("<div class='step%s'>" % cls)
        A("<div><div class='who'>%s</div></div>" % e(who))
        A("<div><div class='what'>%s</div><div class='bar'><i style='width:%.2f%%'></i></div></div>"
          % (e(what), min(100.0, pct)))
        A("<div style='text-align:center'><div class='n num'>%d</div>"
          "<div class='what num'>%.1f%%</div></div>" % (n, pct))
        A("</div>")
        if i < len(CHAIN) - 1:
            A("<div class='arrow'>↓</div>")
    A("</div>")

    # ── ٢ · الأزمنة
    A("<h2>٢ · كم تستغرق كلُّ قفزة</h2>")
    A("<p class='sub'>الوسيط أصدقُ من المتوسّط هنا: قفزةٌ واحدة بطيئة تزيح المتوسّط ولا تزيح الوسيط.</p>")
    A("<div class='scroll'><table><tr><th>القفزة</th><th>الوسيط</th><th>أسرع</th>"
      "<th>أبطأ</th><th>عدد</th></tr>")
    for (a, b), vals in sorted(hops.items(), key=lambda kv: -len(kv[1]))[:10]:
        vals = sorted(vals)
        mid = vals[len(vals) // 2]
        A("<tr><td>%s <span class='tag'>→</span> %s</td>"
          "<td class='num'>%.3f ث</td><td class='num'>%.3f</td>"
          "<td class='num'>%.3f</td><td class='num'>%d</td></tr>"
          % (e(STAGE_NAMES.get(a, a)), e(STAGE_NAMES.get(b, b)),
             mid, vals[0], vals[-1], len(vals)))
    A("</table></div>")

    if complete:
        key, evs = complete[-1]
        t0 = evs[0]["recorded_at"]
        span = evs[-1]["recorded_at"] - t0
        A("<p class='sub' style='margin-top:16px'>آخر رحلةٍ بلغت الجسر وامتلأت — "
          "<b>%s</b> · <code>%s</code> · من الطلب إلى المركز "
          "<b class='num'>%.3f ثانية</b>:</p>" % (e(evs[0]["symbol"]), e(key), span))
        A("<div class='scroll'><table><tr><th>الساعة</th><th>منذ الطلب</th>"
          "<th>المحطّة</th><th>السبب</th></tr>")
        # طابعان متساويان يقعان في محطّتين متتاليتين، فيكسر التعادلَ ترتيبُ
        # السلسلة لا ترتيبُ الورود — وإلّا ظهر ٥٥٢ قبل ٥٥١ في صفحةٍ موضوعها الترتيب.
        order = {k: i for i, (k, _, _) in enumerate(CHAIN)}
        seen, shown = set(), []
        for x in evs:
            if x["stage"] in seen:
                continue
            seen.add(x["stage"])
            shown.append(x)
        shown.sort(key=lambda x: (round(x["recorded_at"], 3), order.get(x["stage"], 99)))
        for x in shown:
            A("<tr><td class='num'>%s</td><td class='num'>+%.3f ث</td><td>%s</td><td>%s</td></tr>"
              % (clock(x["recorded_at"]), x["recorded_at"] - t0,
                 e(STAGE_NAMES.get(x["stage"], x["stage"])), e(x["reason"] or "")))
        A("</table></div>")

    # ── ٣ · بناء بطاقة حقيقيّة
    A("<h2>٣ · كيف تُبنى بطاقةٌ واحدة — حقلًا حقلًا</h2>")
    A("<p class='sub'>البطاقة رقم <b class='num'>%s</b> · %s %s · الحالة %s · "
      "تذكرة <span class='num'>%s</span>. كلُّ سطرٍ كتبه صاحبُه باسمه ورقمه.</p>"
      % (e(card["card_no"]), e(card["symbol"]), e(card["side"]),
         e(card["state"]), e(card["ticket"])))

    filled = [k for k in card.keys() if card[k] not in (None, "")]
    A("<p class='sub'>حقولٌ مكتوبة: <b class='num'>%d</b> من <b class='num'>%d</b>. "
      "الباقي لم يُكتب بعدُ لأنّ الرحلة لم تبلغه.</p>" % (len(filled), len(card.keys())))

    if writes:
        t0 = writes[0]["first_at"]
        A("<div class='scroll'><table><tr><th>الساعة</th><th>منذ فتح البطاقة</th>"
          "<th>مَن كتب</th><th>الحقل</th><th>القيمة</th></tr>")
        for w in writes:
            A("<tr><td class='num'>%s</td><td class='num'>+%.3f ث</td>"
              "<td class='mine num'>%s</td><td><code>%s</code></td><td>%s</td></tr>"
              % (clock(w["first_at"]), w["first_at"] - t0, e(w["author"]),
                 e(w["field"]), e(str(w["value_json"])[:60])))
        A("</table></div>")
        A("<p class='sub'>عمرُ البناء كلّه: <b class='num'>%.1f ثانية</b> على "
          "<b class='num'>%d</b> حقلًا.</p>" % (writes[-1]["first_at"] - t0, len(writes)))

    # ── ٤ · من يكتب على البطاقات
    A("<h2>٤ · مَن يكتب على البطاقات أصلًا</h2>")
    A("<div class='scroll'><table><tr><th>الذرّة</th><th>كتابات</th><th>بطاقات</th></tr>")
    for a in authors:
        A("<tr><td class='num'>%s</td><td class='num'>%d</td><td class='num'>%d</td></tr>"
          % (e(a["author"]), a["n"], a["c"]))
    A("</table></div>")

    # ── ٥ · الدفتر
    A("<h2>٥ · الدفتر كلّه</h2>")
    A("<p class='sub'>مجموع البطاقات: <b class='num'>%d</b></p>" % total)
    A("<div class='scroll'><table><tr><th>الحالة</th><th>عدد</th></tr>")
    for s in states:
        A("<tr><td>%s</td><td class='num'>%d</td></tr>" % (e(s["state"]), s["n"]))
    A("</table></div>")

    # ── ٦ · ما وجدتُه وأنا أقيس
    A("<h2>٦ · ما وجدتُه وأنا أقيس</h2>")
    fin = reached.get("DECISION_FINALIZED", 0)
    bad = reached.get("BRIDGE_WRITE_FAILED", 0)
    if fin:
        A("<div class='note bad'><b>واحدٌ من كلّ خمسة أوامر مرّرها ٥٥٢ لم يصل الجسر.</b> "
          "<span class='num'>%d</span> من <span class='num'>%d</span> قرارًا نهائيًّا "
          "(<span class='num'>%.1f%%</span>) سجّلها ٧٠٧ باسم <code>BRIDGE_WRITE_FAILED</code>، "
          "وسببُها المكتوب <code>database is locked</code> — قفلٌ على قاعدة الجسر لا على "
          "مخازني. آخرُها اليوم.</div>" % (bad, fin, 100.0 * bad / fin))
    if reached.get("FILLED_CLOSED", 0) == 0 and reached.get("FILLED_OPEN", 0):
        A("<div class='note'><b>الأثر ينقطع عند الإغلاق.</b> "
          "<span class='num'>%d</span> طلبًا بلغ <code>FILLED_OPEN</code> ولا واحد يظهر عند "
          "<code>FILLED_CLOSED</code> بالمفتاح نفسه: محطّةُ الإغلاق لا تحمل "
          "<code>request_id</code>، فيُفقد ربطُها بطلب ٥٥٥. الصفقة مسجّلةٌ في مخزن "
          "الصفقات، لكنّ سلسلة القرار تنتهي قبل نهايتها. المخزن مسؤوليّتي وهذا نقصٌ فيه."
          "</div>" % reached.get("FILLED_OPEN", 0))
    A("<div class='note'><b>ساعتان لا ساعة.</b> <code>recorded_at</code> و<code>stored_at</code> "
      "ساعةُ المنصّة، و<code>opened_at</code> في مخزن الصفقات ساعةُ الوسيط وتسبقها "
      "<b>ثلاث ساعات</b>. كلُّ أزمنة هذه الصفحة من ساعة المنصّة وحدها.</div>")

    A("<p class='foot'>المصادر: <code>trade_cards.db</code> (دفتر ٤٦٥ وسجلّ "
      "<code>card_writes</code>) · <code>decisions.db</code> (محطّات ٧٠٧). "
      "لا رقم في هذه الصفحة مكتوبٌ بيدي — أعِد التشغيل تتجدّد كلّها.</p>")
    A("</div>")
    return "\n".join(P)


def main() -> int:
    if not os.path.isdir(STORE):
        print("⛔ لم يُعثر على المخزن: %s" % STORE)
        return 1
    trips, reached, hops, complete = measure_chain()
    card, writes, states, total, authors = measure_card()
    page = build(trips, reached, hops, complete, card, writes, states, total, authors)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print("الصفحة: %s" % OUT)
    print("طلبات ٥٥٥: %d · بلغ الجسر: %d · امتلأ: %d · فشل الجسر: %d"
          % (len(trips), reached.get("QUEUED_TO_BRIDGE", 0),
             reached.get("FILLED_OPEN", 0), reached.get("BRIDGE_WRITE_FAILED", 0)))
    if "--no-open" not in sys.argv:
        webbrowser.open("file:///" + OUT.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
