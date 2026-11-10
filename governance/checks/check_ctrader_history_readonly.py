"""حارس أداة تاريخ سي‑تريدر — قراءة فقط، بأمر المالك ٢٠٢٦-١٠-٠٥ («بيانات فقط»).

الأداة `tools/جلب_تاريخ_سي_تريدر.py` تتّصل بالحساب الحيّ، فهذا الحارس يثبت شقّين بلا شبكة:
  ١· لا مخرج إلى الخادم إلّا `Link.send`، ولا يمرّ منه إلّا ستّة أنواع؛ ورمزٌ بصلاحيّة التداول
     يوقفها قبل تعريف الحساب.
  ٢· الجلب صحيح على خادمٍ مزيّف بقواعد التوثيق: نافذةٌ أطول من المسموح تُرفض بـ
     `INCORRECT_BOUNDARIES`، وردٌّ أكبر من الدفعة يحمل `hasMore` — فلا فجوة ولا تكرار، والشمعة
     التي لم تُغلق لا تُحفظ، والإكمال بعد انقطاعٍ لا يترك فجوة، والرمز لا يظهر في أيّ سطر.
"""
from __future__ import annotations

import ast
import calendar
import importlib.util
import json
import pathlib
import sys
import time
from collections import defaultdict, deque

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "جلب_تاريخ_سي_تريدر.py"
spec = importlib.util.spec_from_file_location("ctrader_history_tool", TOOL)
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)
T.HISTORY_GAP_S = 0.0          # حدّ الخمسة في الثانية للخادم الحقيقيّ؛ المزيّف لا يحتاجه

bad = 0


def show(label: str, ok: bool, detail: str = "") -> None:
    global bad
    if not ok:
        bad += 1
    print("   %-62s %-26s %s" % (label, detail, "✓" if ok else "✘"))


TOKEN = "tok-SECRET-never-printed"
LOGIN = "6175701"
H = 3600
START_S = 1767225600            # 2026-01-01 00:00 UTC — أوّل التاريخ في الخادم المزيّف


class FakeServer:
    """يردّ كما يصف التوثيق. حدّ المدى والدفعة هنا اختياران للاختبار، لا أرقام الوسيط."""

    def __init__(self, scope=0, period_form="code", max_range_days=None, chunk=500,
                 tick_convention="delta_minus", tick_chunk=5000):
        self.scope, self.period_form, self.chunk = scope, period_form, chunk
        self.tick_convention, self.tick_chunk = tick_convention, tick_chunk
        now_ms = int(time.time() * 1000)
        # تِكّة عرضٍ كلّ عشر ثوانٍ لتسعة أيّام، سعرٌ متعرّج بوحدات 1/100000.
        self.ticks = [(t, 400_000_000 + int(30_000 * ((t // 10_000) % 37 - 18)))
                      for t in range(now_ms - 9 * 86_400_000, now_ms, 10_000)]
        self.max_range = {k: v * T.DAY_MS for k, v in (max_range_days or {"H1": 60, "MN1": 5000}).items()}
        self.sent: list[int] = []
        self.out: deque = deque()
        now_s = int(time.time())
        self.h1 = list(range(START_S, now_s - now_s % H + H, H))   # الأخيرة تتشكّل الآن
        self.mn1 = []
        y, m = 2026, 1
        while True:
            t = calendar.timegm((y, m, 1, 0, 0, 0))
            if t > now_s:
                break
            self.mn1.append(t)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    def send(self, text):
        msg = json.loads(text)
        kind, body, mid = msg["payloadType"], msg["payload"], msg["clientMsgId"]
        self.sent.append(kind)
        reply = lambda k, p: self.out.append(json.dumps({"clientMsgId": mid, "payloadType": k, "payload": p}))  # noqa: E731
        if kind == T.APP_AUTH_REQ:
            reply(T.APP_AUTH_RES, {})
        elif kind == T.ACCOUNTS_BY_TOKEN_REQ:
            p = {"accessToken": body["accessToken"],
                 "ctidTraderAccount": [{"ctidTraderAccountId": 777, "isLive": True, "traderLogin": int(LOGIN)}]}
            if self.scope is not None:
                p["permissionScope"] = self.scope
            reply(T.ACCOUNTS_BY_TOKEN_RES, p)
        elif kind == T.ACCOUNT_AUTH_REQ:
            reply(T.ACCOUNT_AUTH_RES, {"ctidTraderAccountId": body["ctidTraderAccountId"]})
        elif kind == T.SYMBOLS_LIST_REQ:
            reply(T.SYMBOLS_LIST_RES, {"symbol": [{"symbolId": 41, "symbolName": "XAUUSD"},
                                                  {"symbolId": 10026, "symbolName": "BTCUSD"}]})
        elif kind == T.TRENDBARS_REQ:
            period = body["period"]
            if (self.period_form == "name") != isinstance(period, str):
                reply(T.OA_ERROR_RES, {"errorCode": "INVALID_REQUEST", "description": "period"})
                return
            name = period if isinstance(period, str) else {v[0]: k for k, v in T.PERIODS.items()}[period]
            frm, to = body["fromTimestamp"], body["toTimestamp"]
            if to - frm > self.max_range[name]:
                reply(T.OA_ERROR_RES, {"errorCode": "INCORRECT_BOUNDARIES", "description": "range"})
                return
            starts = [s for s in (self.h1 if name == "H1" else self.mn1) if frm <= s * 1000 <= to]
            more = len(starts) > self.chunk
            bars = [{"volume": 7, "low": str(200000000 + s // H), "deltaOpen": 100, "deltaHigh": 250,
                     "deltaClose": 50, "utcTimestampInMinutes": s // 60} for s in starts[:self.chunk]]
            reply(T.TRENDBARS_RES, {"ctidTraderAccountId": 777, "period": period, "trendbar": bars,
                                    "hasMore": more})
        elif kind == T.TICKDATA_REQ:
            frm, to = body["fromTimestamp"], body["toTimestamp"]
            if to - frm > T.TICK_WINDOW_MS:
                reply(T.OA_ERROR_RES, {"errorCode": "INCORRECT_BOUNDARIES", "description": "week"})
                return
            inside = [x for x in self.ticks if frm <= x[0] <= to][::-1]      # الأحدث أوّلًا
            chunk = inside[:self.tick_chunk]
            reply(T.TICKDATA_RES, {"ctidTraderAccountId": 777, "tickData": encode(chunk, self.tick_convention),
                                   "hasMore": len(inside) > self.tick_chunk})

    def recv(self, timeout=None):
        if not self.out:
            raise TimeoutError
        return self.out.popleft()

    def close(self):
        pass


def encode(newest_first, convention):
    """ترميز ردّ التِّكّات كما يصفه البروتو: الأولى مطلقة، والأزمنة بعدها فروق؛ والسعر بالصيغة المختارة."""
    out, prev = [], None
    for ts, price in newest_first:
        if prev is None:
            out.append({"timestamp": ts, "tick": price})
        else:
            tick = (price if convention == "absolute" else price - prev[1] if convention == "delta_plus"
                    else prev[1] - price)
            out.append({"timestamp": prev[0] - ts, "tick": tick})
        prev = (ts, price)
    return out


def fresh(server):
    link = T.Link(server)          # بلا خيط النبضة: الاختبار أقصر من تسع ثوانٍ
    return link, T.Store(":memory:")


print("=" * 100)
print("حارس أداة تاريخ سي‑تريدر — قراءة فقط، وجلبٌ بلا فجوة")
print("=" * 100)

print("\n١· القراءة فقط:")
show("القائمة البيضاء سبعة أنواع بالضبط (السابع طلب التِّكّات، قراءة)",
     T.SEND_ALLOWED == {51, 2100, 2149, 2102, 2114, 2137, 2145}, str(sorted(T.SEND_ALLOWED)))
tree = ast.parse(TOOL.read_text(encoding="utf-8"))
ws_sends = [(n.lineno, fn.name) for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)
            for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "send" and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == "_ws"]
show("مخرجٌ واحد إلى الخادم، داخل `Link.send`", [f for _l, f in ws_sends] == ["send"], "مخارج=%d" % len(ws_sends))
srv = FakeServer()
link, _ = fresh(srv)
for trading in (2106, 2107, 2108, 2109, 2110, 2111):     # فتح/إلغاء/تعديل/إغلاق مراكز وأوامر
    try:
        link.send(trading, {})
        refused = False
    except T.Refused:
        refused = True
    if not refused:
        break
show("أنواع التداول تُرفض قبل الإرسال", refused and not srv.sent, "أُرسل=%d" % len(srv.sent))

srv = FakeServer(scope=1)
link, store = fresh(srv)
logs: list[str] = []
try:
    T.run(link, store, TOKEN, LOGIN, ["XAUUSD"], ["H1"], logs.append)
    stopped = False
except T.Refused:
    stopped = True
show("رمزٌ بصلاحيّة التداول يوقفها قبل تعريف الحساب", stopped and T.ACCOUNT_AUTH_REQ not in srv.sent,
     "أنواع=%s" % srv.sent)

print("\n٢· الجلب على خادمٍ مزيّف بقواعد التوثيق:")
srv = FakeServer()
link, store = fresh(srv)
logs = []
T.run(link, store, TOKEN, LOGIN, ["XAUUSD"], ["H1", "MN1"], logs.append)
closed_h1 = [s for s in srv.h1 if s + H <= time.time()]
n, first, last = store.count("XAUUSD", "H1")
show("كلّ ساعات التاريخ المغلقة محفوظة، بلا زيادة", n == len(closed_h1) and first == closed_h1[0]
     and last == closed_h1[-1], "%d من %d" % (n, len(closed_h1)))
show("الساعة التي لم تُغلق لا تُحفظ", store.db.execute(
    "SELECT COUNT(*) FROM candles_history WHERE period='H1' AND period_start=?", (srv.h1[-1],)).fetchone()[0] == 0)
row = store.db.execute("SELECT open, high, low, close, tick_volume FROM candles_history "
                       "WHERE period='H1' AND period_start=?", (START_S,)).fetchone()
low = (200000000 + START_S // H) / 1e5
show("الأسعار = القاع/100000 + الفروق", row is not None and abs(row[2] - low) < 1e-9
     and abs(row[0] - (low + 0.001)) < 1e-9 and abs(row[1] - (low + 0.0025)) < 1e-9
     and abs(row[3] - (low + 0.0005)) < 1e-9 and row[4] == 7, str(row))
prog_h1, prog_mn = store.progress("XAUUSD", "H1"), store.progress("XAUUSD", "MN1")
show("الإطاران مكتملان", prog_h1["complete"] == 1 and prog_mn["complete"] == 1)
show("النافذة تعلّمت حدّ المدى والدفعة (≤60 يومًا و≤500 شمعة)",
     prog_h1["window_ms"] <= 60 * T.DAY_MS and prog_h1["window_ms"] / 1000 / H <= 500,
     "%.2f يوم" % (prog_h1["window_ms"] / T.DAY_MS))
show("الشهريّ محفوظ (أرض الأطر الأصغر)", store.count("XAUUSD", "MN1")[0] == len(srv.mn1) - 1,
     "%d" % store.count("XAUUSD", "MN1")[0])
show("الرمز لا يظهر في أيّ سطر", not any(TOKEN in line for line in logs), "أسطر=%d" % len(logs))

# مقيس من خادمهم ٢٠٢٦-١٠-٠٥: الشموع على منتصف ليل الوسيط (21:00/22:00 غرينتش) — شهر أكتوبر يبدأ
# 30-09 21:00. حسابه بأوّل الشهر التالي بتوقيت غرينتش كان يعدّ الشهر الجاري مغلقًا.
OCT = calendar.timegm((2026, 9, 30, 21, 0, 0))
SEP = calendar.timegm((2026, 8, 31, 21, 0, 0))
now_ms = calendar.timegm((2026, 10, 5, 19, 0, 0)) * 1000
mn = T.decode_bars("MN1", [{"low": 1, "utcTimestampInMinutes": s // 60} for s in (SEP, OCT)], now_ms)
show("الشهر الجاري بإزاحة الوسيط لا يُعدّ مغلقًا، والسابق يُعدّ", [b[0] for b in mn] == [SEP],
     "محفوظ=%d" % len(mn))
show("نهاية أكتوبر بعد 31-10 22:00 غرينتش (يوم تغيّر التوقيت)",
     T.bar_end_ms("MN1", OCT) >= calendar.timegm((2026, 10, 31, 22, 0, 0)) * 1000)
MON = calendar.timegm((2026, 10, 4, 21, 0, 0))
early = T.decode_bars("D1", [{"low": 1, "utcTimestampInMinutes": MON // 60}], (MON + 86400 + 1800) * 1000)
late = T.decode_bars("D1", [{"low": 1, "utcTimestampInMinutes": MON // 60}], (MON + 86400 + 3600) * 1000)
show("اليوميّ ينتظر ساعة الهامش ثمّ يُحفظ", not early and len(late) == 1)

# انقطاعٌ في الإلحاق: آخر ما حُفظ قبل ٢٠ يومًا، وما بعده مفقود — التشغيل التالي يسدّه كاملًا.
cut = closed_h1[-20 * 24]
store.db.execute("DELETE FROM candles_history WHERE period='H1' AND period_start>?", (cut,))
store.db.execute("UPDATE fetch_progress SET newest_ms=? WHERE period='H1'", (cut * 1000,))
store.db.commit()
T.run(link, store, TOKEN, LOGIN, ["XAUUSD"], ["H1"], logs.append)
n2 = store.count("XAUUSD", "H1")[0]
closed_h1 = [s for s in srv.h1 if s + H <= time.time()]
show("الإكمال بعد انقطاع يسدّ الفجوة ولا يكرّر", n2 == len(closed_h1), "%d من %d" % (n2, len(closed_h1)))

srv = FakeServer(period_form="name")
link, store = fresh(srv)
T.run(link, store, TOKEN, LOGIN, ["XAUUSD"], ["H1"], [].append)
show("إن رفض الخادم الإطار رقمًا يُجرَّب اسمًا ويُحفظ",
     store.meta("period_as_name") == "1" and store.count("XAUUSD", "H1")[0] > 0)

srv = FakeServer(scope=None)
link, store = fresh(srv)
T.run(link, store, TOKEN, LOGIN, ["XAUUSD"], ["MN1"], [].append)
show("صلاحيّةٌ غير مذكورة = عرض (القيمة الافتراضيّة في البروتو)", T.ACCOUNT_AUTH_REQ in srv.sent)

print("\n٣· التِّكّات التاريخيّة (قرار المالك «الاثنان»):")
sample = [(1_790_000_000_000 + i * 700, 400_000_000 + (i * 37) % 900 - 450) for i in range(50)]
round_trip = all(T.decode_ticks(encode(sample[::-1], c), c) ==
                 [(ts, round(p / T.PRICE_SCALE, 5)) for ts, p in sample] for c in T.TICK_CONVENTIONS)
show("فكّ الترميز يعيد السلسلة لكلّ صيغة (الأحدث أوّلًا، فروق الزمن)", round_trip)
for convention in T.TICK_CONVENTIONS:
    srv = FakeServer(tick_convention=convention)
    link, store = fresh(srv)
    account = T.open_account(link, store, TOKEN, LOGIN, [].append)
    minutes = defaultdict(list)                       # شموع دقيقة من التِّكّات نفسها — كما تُبنى عندهم
    for ts, price in srv.ticks:
        minutes[ts // 60000 * 60].append(price / T.PRICE_SCALE)
    store.save("XAUUSD", "M1", [(m, v[0], max(v), min(v), v[-1], len(v)) for m, v in minutes.items()], None)
    picked = T.probe_ticks(link, store, account, "XAUUSD", 41, [].append)
    show("القياس يختار صيغة الخادم (%s)" % convention, picked == convention, str(picked))
srv = FakeServer()
link, store = fresh(srv)
account = T.open_account(link, store, TOKEN, LOGIN, [].append)
try:
    T.run_ticks(link, store, account, ["XAUUSD"], 2.0, [].append)
    refused = False
except T.Refused:
    refused = True
show("لا جلب تِكّاتٍ قبل قياس الصيغة", refused and T.TICKDATA_REQ not in srv.sent)
store.meta("tick_convention", "delta_minus")
T.run_ticks(link, store, account, ["XAUUSD"], 8.5, [].append)
since = int((time.time() - 8.5 * 86400) * 1000)
expected = [x for x in srv.ticks if x[0] >= since]
n, first, last = store.tick_count("XAUUSD", 1)
show("ثمانية أيّام ونصف عبر نافذتين و`hasMore`: كاملة بلا تكرار",
     n == len(expected) and last == expected[-1][0], "%d من %d" % (n, len(expected)))
show("العرض والطلب كلاهما مجلوبان", store.tick_count("XAUUSD", 2)[0] == n)

print("\n" + "=" * 100)
print("الاختلافات = %d" % bad)
print("سليم: الأداة تقرأ فقط وتجلب بلا فجوة." if bad == 0 else "ساقط: راجع الأسطر المعلَّمة.")
sys.exit(1 if bad else 0)
