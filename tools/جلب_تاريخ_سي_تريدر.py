"""جلب تاريخ الشموع من سي‑تريدر — قراءة فقط، عبر ويب سوكت (الواجهة المفتوحة، صيغة JSON).

أمر المالك ٢٠٢٦-١٠-٠٥ (ختم «nq»): الذهب والبتكوين والناسداك، كلّ الأطر من الدقيقة صعودًا،
«بيانات فقط» — لا تداول ولا أيّ عملٍ على الحساب.

لماذا أداة منفصلة لا ذرّة: وصلة 622 (FIX) لا تقبل طلب تاريخ — صفحة حدودها في توثيقهم
(`help.ctrader.com/fix/limitations/`): صُمّمت لأسرع اتّصال فلا تخدم البيانات التاريخيّة،
والتاريخ من «الواجهة المفتوحة» وحدها. والأداة تعمل في عمليّةٍ مستقلّة فلا تمسّ التغذية
الحيّة ولا تحتاج إقلاعًا، وتكتب في قاعدةٍ خاصّة لا يقرؤها النظام بعد.

المثبت من توثيقهم (قُرئ ٢٠٢٦-١٠-٠٥ من `help.ctrader.com/open-api/` و`spotware/openapi-proto-messages`):
- الخادم الحيّ `live.ctraderapi.com`، منفذ 5036 لـ JSON، ويب سوكت على `wss://host:port`،
  وهو منفصل عن التجريبيّ.
- نبضة `ProtoHeartbeatEvent` (51) كلّ ١٠ ثوانٍ وإلّا قُطع الاتّصال.
- حدّ الطلبات التاريخيّة ٥ في الثانية لكلّ اتّصال.
- `ProtoOAGetTrendbarsReq`: رقم الحساب والرمز والإطار إلزاميّة — فلا شموع بلا تعريف حساب؛
  المدى بالملّي‑ثانية؛ والمدى الأطول من المسموح يُرفض بـ `INCORRECT_BOUNDARIES`. حدود المدى
  لكلّ إطار **غير منشورة**، فالأداة تبدأ بنافذةٍ وتنصّفها عند الرفض وتحفظ ما تعلّمته.
- السعر = `low / 100000`، والفتح والقمّة والإغلاق = `low + delta`؛ و`utcTimestampInMinutes`
  وقت فتح الشمعة.
- الصلاحيّة `accounts` تعطي `SCOPE_VIEW` (=0): «أوامر العرض فقط، والتداول ممنوع».

ضمانات القراءة فقط (الحارس `governance/checks/check_ctrader_history_readonly.py`):
١· لا يخرج من الأداة إلّا ستّة أنواع (`SEND_ALLOWED`)؛ أيّ نوعٍ آخر يُرفض قبل الإرسال.
٢· رمزٌ بصلاحيّة التداول (`SCOPE_TRADE`) يوقف الأداة قبل تعريف الحساب.
٣· الأسرار تُقرأ من الخزنة ولا تُطبع ولا تدخل رسالة خطأ.

التشغيل (من جذر المشروع):
    vendor\\python\\runtime\\python.exe tools\\جلب_تاريخ_سي_تريدر.py --check
        يتحقّق من المعرّف والسرّ وحدهما (تفويض التطبيق) — بلا رمز دخول وبلا حساب.
    vendor\\python\\runtime\\python.exe tools\\جلب_تاريخ_سي_تريدر.py
        الجلب كاملًا؛ يحتاج `ctrader_openapi_access_token` في الخزنة. يُكمل من حيث توقّف.
"""
from __future__ import annotations

import argparse
import calendar
import itertools
import json
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOST = "live.ctraderapi.com"
PORT_JSON = 5036
URI = "wss://%s:%d" % (HOST, PORT_JSON)

SECRET_CLIENT_ID = "ctrader_openapi_client_id"
SECRET_CLIENT_SECRET = "ctrader_openapi_client_secret"
SECRET_ACCESS_TOKEN = "ctrader_openapi_access_token"

# أرقام الرسائل — `ProtoPayloadType` و`ProtoOAPayloadType` في ملفّات البروتو الرسميّة.
ERROR_COMMON = 50
HEARTBEAT = 51
APP_AUTH_REQ, APP_AUTH_RES = 2100, 2101
ACCOUNT_AUTH_REQ, ACCOUNT_AUTH_RES = 2102, 2103
SYMBOLS_LIST_REQ, SYMBOLS_LIST_RES = 2114, 2115
TRENDBARS_REQ, TRENDBARS_RES = 2137, 2138
OA_ERROR_RES = 2142
TICKDATA_REQ, TICKDATA_RES = 2145, 2146
TOKEN_INVALIDATED = 2147
CLIENT_DISCONNECT = 2148
ACCOUNTS_BY_TOKEN_REQ, ACCOUNTS_BY_TOKEN_RES = 2149, 2150
ACCOUNT_DISCONNECT = 2164
CLOSING_EVENTS = {TOKEN_INVALIDATED: "أُبطل رمز الدخول", CLIENT_DISCONNECT: "قطع الخادم الاتّصال",
                  ACCOUNT_DISCONNECT: "فُصل الحساب"}

# ⛔ القائمة البيضاء — لا يخرج من هذه الأداة غير هذه السبعة. كلّ أوامر التداول وتعديل
# الحساب خارجها فتُرفض قبل أن تُرسل، مهما كان مصدر النداء. السابع (طلب التِكّات التاريخيّة،
# قراءةٌ فقط) أُضيف بقرار المالك ٢٠٢٦-١٠-٠٥ «الاثنان» للاختبار التاريخيّ: ختمه ٠٩-٠٢ يمنع
# اختراع تِكّاتٍ من الشموع، والنظام يقرّر على التِّكّة.
SEND_ALLOWED = frozenset({HEARTBEAT, APP_AUTH_REQ, ACCOUNTS_BY_TOKEN_REQ, ACCOUNT_AUTH_REQ,
                          SYMBOLS_LIST_REQ, TRENDBARS_REQ, TICKDATA_REQ})
# جانبا السعر (`ProtoOAQuoteType`)، وأقصى مدى طلب التِّكّات بنصّ توثيقهم: أسبوعٌ = 604800000 م.ث.
QUOTE_SIDES = {"bid": 1, "ask": 2}
TICK_WINDOW_MS = 604800000
SCOPE_VIEW_VALUES = (None, 0, "SCOPE_VIEW")    # غيابه = القيمة الافتراضيّة في البروتو = عرض

HEARTBEAT_EVERY_S = 9.0          # التوثيق: كلّ ١٠ ثوانٍ على الأكثر
HISTORY_GAP_S = 0.25             # التوثيق: ٥ طلبات تاريخيّة في الثانية؛ نبقى على ٤
REPLY_TIMEOUT_S = 60.0
PRICE_SCALE = 100000.0
MS = 1000
DAY_MS = 86400 * MS
EMPTY_STOP_MS = 365 * DAY_MS     # بلا أرضٍ معروفة: سنةٌ فارغة متّصلة = بداية التاريخ
DST_MARGIN_S = 3600              # يوم تغيّر التوقيت عند الوسيط أطول بساعة

# الإطار: (رقمه في `ProtoOATrendbarPeriod`، ثوانيه). الشهر بثوانٍ اسميّة كالإكسبرت (30 يومًا).
PERIODS: dict[str, tuple[int, int]] = {
    "M1": (1, 60), "M2": (2, 120), "M3": (3, 180), "M4": (4, 240), "M5": (5, 300),
    "M10": (6, 600), "M15": (7, 900), "M30": (8, 1800), "H1": (9, 3600), "H4": (10, 14400),
    "H12": (11, 43200), "D1": (12, 86400), "W1": (13, 604800), "MN1": (14, 2592000),
}
# نافذة البداية بالأيّام — نقطة انطلاقٍ تُنصَّف عند الرفض، لا حدٌّ مُدّعى للخادم.
START_WINDOW_DAYS = {"M1": 7, "M2": 7, "M3": 7, "M4": 7, "M5": 35, "M10": 35, "M15": 70,
                     "M30": 70, "H1": 180, "H4": 730, "H12": 730, "D1": 7300, "W1": 7300,
                     "MN1": 7300}
DEFAULT_SYMBOLS = ("XAUUSD", "BTCUSD", "USTEC")   # بأسمائها في إعداد 622
DB_PATH = ROOT / "forex_runtime" / "var" / "history" / "ctrader_history.db"


class ApiError(RuntimeError):
    def __init__(self, code: str, description: str = "", retry_after: float | None = None):
        super().__init__("%s %s" % (code, description))
        self.code, self.description, self.retry_after = code, description, retry_after


class LinkClosed(RuntimeError):
    pass


class Refused(RuntimeError):
    """رفضٌ من الأداة نفسها لحماية القراءة فقط — لا يُتجاوز."""


# ─────────────────────────────────────────────────────────── الاتّصال ──

class Link:
    """طلبٌ واحد في الطيران؛ النبضة من خيطٍ جانبيّ يرسل ولا يستقبل."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._last_send = time.monotonic()
        self._last_history = 0.0
        self._stop = threading.Event()
        self._beat = threading.Thread(target=self._heartbeat, name="ctrader-heartbeat", daemon=True)

    def start(self) -> None:
        self._beat.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self._ws.close()
        except Exception:  # noqa: BLE001 — الإغلاق لا يُفشل الأداة
            pass

    def send(self, ptype: int, payload: dict[str, Any]) -> str:
        """المخرج الوحيد إلى الخادم."""
        if ptype not in SEND_ALLOWED:
            raise Refused("نوع رسالة خارج القائمة البيضاء: %r — لا يُرسل" % (ptype,))
        mid = "q%d" % next(self._ids)
        text = json.dumps({"clientMsgId": mid, "payloadType": ptype, "payload": payload})
        with self._lock:
            self._ws.send(text)
            self._last_send = time.monotonic()
        return mid

    def _heartbeat(self) -> None:
        while not self._stop.wait(1.0):
            if time.monotonic() - self._last_send >= HEARTBEAT_EVERY_S:
                try:
                    self.send(HEARTBEAT, {})
                except Exception:  # noqa: BLE001 — الاستقبال يكشف الانقطاع ويبلّغ عنه
                    return

    def request(self, ptype: int, payload: dict[str, Any], expect: int) -> dict[str, Any]:
        if ptype in (TRENDBARS_REQ, TICKDATA_REQ):          # كلاهما «طلبٌ تاريخيّ» في حدّهم
            wait = HISTORY_GAP_S - (time.monotonic() - self._last_history)
            if wait > 0:
                time.sleep(wait)
            self._last_history = time.monotonic()
        mid = self.send(ptype, payload)
        deadline = time.monotonic() + REPLY_TIMEOUT_S
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ApiError("TIMEOUT", "لا ردّ خلال %d ثانية" % REPLY_TIMEOUT_S)
            try:
                raw = self._ws.recv(timeout=remaining)
            except TimeoutError:
                continue
            msg = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            kind, body, rid = msg.get("payloadType"), msg.get("payload") or {}, msg.get("clientMsgId")
            if kind == HEARTBEAT:
                continue
            if kind in CLOSING_EVENTS:
                raise LinkClosed(CLOSING_EVENTS[kind])
            # طلبٌ واحد في الطيران: ردٌّ بلا رقم يُقبل إن كان من النوع المنتظَر أو خطأً.
            if rid not in (mid, None):
                continue
            if kind in (OA_ERROR_RES, ERROR_COMMON):
                retry = body.get("retryAfter")
                raise ApiError(str(body.get("errorCode", "ERROR")), str(body.get("description", "")),
                               float(retry) if retry is not None else None)
            if kind == expect:
                return body
            if rid is not None:
                raise ApiError("UNEXPECTED", "نوع ردّ %r بدل %r" % (kind, expect))


@contextmanager
def open_link(uri: str = URI) -> Iterator[Link]:
    from websockets.sync.client import connect
    # ping_interval=None: نبضة التطبيق (51) هي المطلوبة في توثيقهم، لا نبضة البروتوكول.
    # max_size=None: ردّ الشموع قد يتجاوز الحدّ الافتراضيّ (١ م.ب).
    with connect(uri, open_timeout=20, ping_interval=None, max_size=None) as ws:
        link = Link(ws)
        link.start()
        try:
            yield link
        finally:
            link.close()


# ─────────────────────────────────────────────────────────── الأسرار ──

def load_secrets(*names: str) -> dict[str, str]:
    """من خزنة النظام بإعداد `config/core_forex.yaml` نفسه؛ القيم لا تُطبع أبدًا."""
    import yaml
    from security import FileSecretProvider
    cfg = yaml.safe_load((ROOT / "config" / "core_forex.yaml").read_text(encoding="utf-8")) or {}
    sec = cfg.get("secrets") or {}
    base = ROOT / "forex_runtime"                    # النواة تعمل منه، والمسارات نسبيّة إليه

    def rooted(raw: str | None) -> Path | None:
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_absolute() else (base / path).resolve()

    provider = FileSecretProvider(rooted(sec.get("vault_path", "runtime/secrets.enc")),
                                  dpapi_blob=rooted(sec.get("dpapi_blob")),
                                  allow_prompt=False, auto_open=True)
    try:
        return {name: str(provider.get_secret(name) or "").strip() for name in names}
    finally:
        provider.clear()


def default_login() -> str:
    """رقم حساب سي‑تريدر من إعداد 622 — مصدرٌ واحد لا نسخة."""
    import yaml
    for manifest in (ROOT / "atoms").glob("*/622_*/manifest.yaml"):
        cfg = (yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}).get("config") or {}
        if cfg.get("username"):
            return str(cfg["username"])
    return ""


# ─────────────────────────────────────────────────────────── التخزين ──

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles_history (
    symbol TEXT NOT NULL,
    period TEXT NOT NULL,
    period_seconds INTEGER NOT NULL,
    period_start INTEGER NOT NULL,          -- ثواني يونكس UTC: وقت فتح الشمعة
    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
    tick_volume INTEGER NOT NULL,
    PRIMARY KEY (symbol, period, period_start)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS fetch_progress (
    symbol TEXT NOT NULL, period TEXT NOT NULL,
    oldest_ms INTEGER, newest_ms INTEGER,
    complete INTEGER NOT NULL DEFAULT 0,
    window_ms INTEGER, requests INTEGER NOT NULL DEFAULT 0,
    note TEXT, updated_at INTEGER,
    PRIMARY KEY (symbol, period)
);
CREATE TABLE IF NOT EXISTS fetch_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS ticks_history (
    symbol TEXT NOT NULL,
    side INTEGER NOT NULL,                  -- 1 عرض · 2 طلب (`ProtoOAQuoteType`)
    ts_ms INTEGER NOT NULL,                 -- م.ث يونكس UTC
    price REAL NOT NULL,
    PRIMARY KEY (symbol, side, ts_ms, price)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS tick_progress (
    symbol TEXT NOT NULL, side INTEGER NOT NULL,
    oldest_ms INTEGER, newest_ms INTEGER, requests INTEGER NOT NULL DEFAULT 0,
    note TEXT, updated_at INTEGER,
    PRIMARY KEY (symbol, side)
);
"""
PROGRESS_KEYS = ("oldest_ms", "newest_ms", "complete", "window_ms", "requests", "note")


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.db = sqlite3.connect(str(path))
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def progress(self, symbol: str, period: str) -> dict[str, Any]:
        row = self.db.execute("SELECT %s FROM fetch_progress WHERE symbol=? AND period=?"
                              % ", ".join(PROGRESS_KEYS), (symbol, period)).fetchone()
        return dict(zip(PROGRESS_KEYS, row)) if row else {
            "oldest_ms": None, "newest_ms": None, "complete": 0, "window_ms": None, "requests": 0, "note": None}

    def save(self, symbol: str, period: str, bars: list[tuple], prog: dict[str, Any] | None) -> None:
        seconds = PERIODS[period][1]
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO candles_history VALUES (?,?,?,?,?,?,?,?,?)",
                                [(symbol, period, seconds, *bar) for bar in bars])
            if prog is not None:
                self.db.execute("INSERT OR REPLACE INTO fetch_progress VALUES (?,?,?,?,?,?,?,?,?)",
                                (symbol, period, *(prog[k] for k in PROGRESS_KEYS[:4]),
                                 prog["requests"], prog["note"], int(time.time())))

    def meta(self, key: str, value: Any = None) -> str | None:
        if value is not None:
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO fetch_meta VALUES (?,?)", (key, str(value)))
            return str(value)
        row = self.db.execute("SELECT value FROM fetch_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def count(self, symbol: str, period: str) -> tuple[int, int | None, int | None]:
        return self.db.execute("SELECT COUNT(*), MIN(period_start), MAX(period_start) FROM candles_history "
                               "WHERE symbol=? AND period=?", (symbol, period)).fetchone()

    def tick_progress(self, symbol: str, side: int) -> dict[str, Any]:
        row = self.db.execute("SELECT oldest_ms, newest_ms, requests, note FROM tick_progress "
                              "WHERE symbol=? AND side=?", (symbol, side)).fetchone()
        keys = ("oldest_ms", "newest_ms", "requests", "note")
        return dict(zip(keys, row)) if row else dict.fromkeys(keys) | {"requests": 0}

    def save_ticks(self, symbol: str, side: int, ticks: list[tuple[int, float]],
                   prog: dict[str, Any] | None) -> None:
        with self.db:
            self.db.executemany("INSERT OR IGNORE INTO ticks_history VALUES (?,?,?,?)",
                                [(symbol, side, ts, price) for ts, price in ticks])
            if prog is not None:
                self.db.execute("INSERT OR REPLACE INTO tick_progress VALUES (?,?,?,?,?,?,?)",
                                (symbol, side, prog["oldest_ms"], prog["newest_ms"], prog["requests"],
                                 prog["note"], int(time.time())))

    def tick_count(self, symbol: str, side: int) -> tuple[int, int | None, int | None]:
        return self.db.execute("SELECT COUNT(*), MIN(ts_ms), MAX(ts_ms) FROM ticks_history "
                               "WHERE symbol=? AND side=?", (symbol, side)).fetchone()

    # ٢٠٢٦-١٠-١٧ (المالك: «جيبه سنة 2023 بالأوّل، وبعدها خلّيه شغّال يجيب كلّ تِكّات ناسداك»): مدّةٌ بعينها تُجلب
    # قبل غيرها، وتقدّمها في جدولٍ لها — `tick_progress` يفترض مدًى متّصلًا (أقدم ⟵ أحدث)، فلو كُتبت فيه 2023
    # لظنّ الجلب العاديّ أنّ ما بينها وبين اليوم موجود.
    def _ranges(self) -> None:
        self.db.execute("CREATE TABLE IF NOT EXISTS tick_ranges (symbol TEXT NOT NULL, side INTEGER NOT NULL, "
                        "lo_ms INTEGER NOT NULL, hi_ms INTEGER NOT NULL, reached_ms INTEGER, requests INTEGER NOT NULL "
                        "DEFAULT 0, done INTEGER NOT NULL DEFAULT 0, note TEXT, updated_at INTEGER, "
                        "PRIMARY KEY (symbol, side, lo_ms, hi_ms))")

    def range_progress(self, symbol: str, side: int, lo: int, hi: int) -> dict[str, Any]:
        self._ranges()
        row = self.db.execute("SELECT reached_ms, requests, done, note FROM tick_ranges WHERE symbol=? AND side=? "
                              "AND lo_ms=? AND hi_ms=?", (symbol, side, lo, hi)).fetchone()
        keys = ("reached_ms", "requests", "done", "note")
        return dict(zip(keys, row)) if row else {"reached_ms": None, "requests": 0, "done": 0, "note": None}

    def save_range(self, symbol: str, side: int, lo: int, hi: int, ticks: list[tuple[int, float]],
                   prog: dict[str, Any]) -> None:
        self._ranges()
        with self.db:
            self.db.executemany("INSERT OR IGNORE INTO ticks_history VALUES (?,?,?,?)",
                                [(symbol, side, ts, price) for ts, price in ticks])
            self.db.execute("INSERT OR REPLACE INTO tick_ranges VALUES (?,?,?,?,?,?,?,?,?)",
                            (symbol, side, lo, hi, prog["reached_ms"], prog["requests"], prog["done"], prog["note"],
                             int(time.time())))

    def done_ranges(self, symbol: str, side: int) -> list[tuple[int, int]]:
        self._ranges()
        return [(lo, hi) for lo, hi in self.db.execute(
            "SELECT lo_ms, hi_ms FROM tick_ranges WHERE symbol=? AND side=? AND done=1", (symbol, side))]


#: لا يُملأ القرص: يقف الجلب ويُكتب السبب إن قلّت المساحة الحرّة عن هذا (غيغابايت). سنة تِكّات الناسداك ≈ 117 مليون
#: (عرضًا وطلبًا، مقيس على أسبوعٍ من 9/2026) ≈ 5–6 غيغا.
MIN_FREE_GB = 25.0


def disk_low(path: Path | str) -> bool:
    import shutil
    try:
        return shutil.disk_usage(str(Path(path).parent)).free / 1e9 < MIN_FREE_GB
    except OSError:
        return False


# ─────────────────────────────────────────────────────────── التِّكّات ──
#
# مثبت من ملفّ البروتو الرسميّ: «القائمة بترتيبٍ زمنيّ، الأحدث أوّلًا. التِّكّة الأولى تحمل زمن
# يونكس بالملّي‑ثانية، وكلّ ما بعدها فرقُ الزمن عن سابقتها». أمّا السعر فالتعليق لا يذكر أهو
# مطلقٌ أم فرق — فلا يُفترض: `--probe-ticks` يقيسه بمطابقة التِّكّات مع شموع الدقيقة المحفوظة،
# ويحفظ التفسير الذي يقع داخل الشمعة في `fetch_meta`، ولا يُجلب شيءٌ قبل ذلك.

TICK_CONVENTIONS = ("absolute", "delta_plus", "delta_minus")


def decode_ticks(raw: list[dict[str, Any]], convention: str) -> list[tuple[int, float]]:
    """إلى [(م.ث، سعر)] من الأقدم إلى الأحدث."""
    out: list[tuple[int, float]] = []
    stamp = price = None
    for entry in raw:
        t, p = entry.get("timestamp"), entry.get("tick")
        if t is None or p is None:
            continue
        t, p = int(t), int(p)
        if stamp is None:
            stamp, price = t, p
        else:
            stamp -= abs(t)                    # الأحدث أوّلًا: كلّ تالية أقدم
            price = p if convention == "absolute" else price + p if convention == "delta_plus" else price - p
        out.append((stamp, round(price / PRICE_SCALE, 5)))
    out.reverse()
    return out


def containment(store: Store, symbol: str, ticks: list[tuple[int, float]]) -> tuple[int, int]:
    """كم تِكّة عرضٍ تقع داخل [قاع، قمّة] شمعة الدقيقة المحفوظة لدقيقتها (شموعهم على العرض)."""
    inside = total = 0
    for ts, price in ticks:
        row = store.db.execute("SELECT low, high FROM candles_history WHERE symbol=? AND period='M1' "
                               "AND period_start=?", (symbol, ts // 60000 * 60)).fetchone()
        if row is None:
            continue
        total += 1
        inside += 1 if row[0] - 1e-9 <= price <= row[1] + 1e-9 else 0
    return inside, total


class TickFetcher:
    def __init__(self, link: Link, store: Store, account_id: int, convention: str,
                 log: Callable[[str], None] = print):
        self.link, self.store, self.account_id = link, store, account_id
        self.convention, self.log = convention, log

    def request(self, symbol_id: int, side: int, frm: int, to: int) -> tuple[list[dict], bool]:
        payload = {"ctidTraderAccountId": self.account_id, "symbolId": symbol_id, "type": side,
                   "fromTimestamp": frm, "toTimestamp": to}
        while True:
            try:
                body = self.link.request(TICKDATA_REQ, payload, TICKDATA_RES)
                return list(body.get("tickData") or []), bool(body.get("hasMore"))
            except ApiError as exc:
                if exc.code in ("REQUEST_FREQUENCY_EXCEEDED", "BLOCKED_PAYLOAD_TYPE"):
                    time.sleep(exc.retry_after or 1.0)
                    continue
                raise

    def series(self, symbol: str, symbol_id: int, side: int, since_ms: int) -> dict[str, Any]:
        """إلى الأمام من أحدث المحفوظ حتى الآن، ثمّ إلى الخلف حتى `since_ms`."""
        prog = self.store.tick_progress(symbol, side)
        prog["note"] = None
        now_ms = int(time.time() * MS)
        if prog["newest_ms"] is not None:
            top = self._walk(symbol, symbol_id, side, prog, prog["newest_ms"] + 1, now_ms, backward=False)
            if top is not None and prog["note"] is None:
                prog["newest_ms"] = max(prog["newest_ms"], top)
                self.store.save_ticks(symbol, side, [], prog)
        hi = prog["oldest_ms"] - 1 if prog["oldest_ms"] is not None else now_ms
        if prog["note"] is None and hi > since_ms:
            self._walk(symbol, symbol_id, side, prog, since_ms, hi, backward=True)
        return prog

    def _walk(self, symbol: str, symbol_id: int, side: int, prog: dict[str, Any], lo: int, hi: int,
              backward: bool) -> int | None:
        """نوافذ أسبوعٍ من `hi` إلى الخلف؛ وداخل النافذة يُتابَع `hasMore` من أقدم ما وصل."""
        to, top = hi, None
        done = self.store.done_ranges(symbol, side)
        while to > lo:
            frm = max(lo, to - TICK_WINDOW_MS + 1)
            if any(a <= frm and to <= b for a, b in done):   # a range fetched on its own already holds this week
                to = frm - 1
                continue
            if self.store.path != ":memory:" and disk_low(self.store.path):
                prog["note"] = "مساحة القرص الحرّة أقلّ من %d غيغا — توقّف" % MIN_FREE_GB
                self.store.save_ticks(symbol, side, [], prog)
                self.log("   ✘ %s %s: %s" % (symbol, side, prog["note"]))
                return top
            inner_to = to
            while True:
                try:
                    raw, has_more = self.request(symbol_id, side, frm, inner_to)
                except ApiError as exc:
                    prog["note"] = "%s %s" % (exc.code, exc.description)
                    self.store.save_ticks(symbol, side, [], prog)
                    self.log("   ✘ %s %s: %s" % (symbol, side, prog["note"]))
                    return top
                prog["requests"] += 1
                ticks = decode_ticks(raw, self.convention)
                if ticks:
                    oldest, newest = ticks[0][0], ticks[-1][0]
                    top = newest if top is None else max(top, newest)
                    if backward:
                        prog["oldest_ms"] = oldest if prog["oldest_ms"] is None else min(prog["oldest_ms"], oldest)
                        prog["newest_ms"] = newest if prog["newest_ms"] is None else max(prog["newest_ms"], newest)
                self.store.save_ticks(symbol, side, ticks, prog)
                if not has_more or not ticks or ticks[0][0] <= frm:
                    break
                # الأقدم مشمول ثانيةً (تِكّاتٌ في الملّي‑ثانية نفسها قد تنقسم بين دفعتين)، والمفتاح يمنع التكرار.
                inner_to = ticks[0][0] if ticks[0][0] < inner_to else ticks[0][0] - 1
            to = frm - 1
            if prog["requests"] % 40 == 0:
                self.log("   … %s %s وصل %s · طلبات %d" % (symbol, "عرض" if side == 1 else "طلب",
                                                          _day(frm), prog["requests"]))
        return top

    def range(self, symbol: str, symbol_id: int, side: int, lo: int, hi: int) -> dict[str, Any]:
        """مدّةٌ بعينها [lo, hi) من آخرها إلى أوّلها، أسبوعًا أسبوعًا، ويُكمَل من حيث وقف."""
        prog = self.store.range_progress(symbol, side, lo, hi)
        if prog["done"]:
            return prog
        prog["note"] = None
        to = (prog["reached_ms"] - 1) if prog["reached_ms"] else hi - 1
        while to >= lo:
            if self.store.path != ":memory:" and disk_low(self.store.path):
                prog["note"] = "مساحة القرص الحرّة أقلّ من %d غيغا — توقّف" % MIN_FREE_GB
                self.store.save_range(symbol, side, lo, hi, [], prog)
                self.log("   ✘ %s %s: %s" % (symbol, side, prog["note"]))
                return prog
            frm = max(lo, to - TICK_WINDOW_MS + 1)
            inner_to = to
            while True:
                try:
                    raw, has_more = self.request(symbol_id, side, frm, inner_to)
                except ApiError as exc:
                    prog["note"] = "%s %s" % (exc.code, exc.description)
                    self.store.save_range(symbol, side, lo, hi, [], prog)
                    self.log("   ✘ %s %s: %s" % (symbol, side, prog["note"]))
                    return prog
                prog["requests"] += 1
                ticks = decode_ticks(raw, self.convention)
                self.store.save_range(symbol, side, lo, hi, ticks, prog)
                if not has_more or not ticks or ticks[0][0] <= frm:
                    break
                inner_to = ticks[0][0] if ticks[0][0] < inner_to else ticks[0][0] - 1
            prog["reached_ms"] = frm
            to = frm - 1
            self.store.save_range(symbol, side, lo, hi, [], prog)
            if prog["requests"] % 40 == 0:
                self.log("   … %s %s وصل %s · طلبات %d" % (symbol, "عرض" if side == 1 else "طلب",
                                                          _day(frm), prog["requests"]))
        prog["done"] = 1
        self.store.save_range(symbol, side, lo, hi, [], prog)
        return prog


# ─────────────────────────────────────────────────────────── الشموع ──

def bar_end_ms(period: str, start_s: int) -> int:
    """نهاية الشمعة. الشهر يُقاس بطوله لا بأوّل الشهر التالي بتوقيت غرينتش: مقيس ٢٠٢٦-١٠-٠٥ أنّ
    شموعهم على منتصف ليل خادم الوسيط (21:00 أو 22:00 غرينتش)، فشهر أكتوبر يبدأ 30-09 21:00،
    وحسابه بأوّل الشهر التالي كان يعدّ الشهر الجاري مغلقًا. يومٌ بعد البداية يقع داخل شهر الشمعة
    مهما كانت الإزاحة. وتغيّر التوقيت الصيفيّ يزيح منتصف ليل الخادم ساعة: في أكتوبر يطول الشهر
    ساعة فتُضاف ساعة هامشًا (وفي مارس يصير التأخير ساعتين — أي بحذر لا بتسرّع). والهامش نفسه لكلّ
    إطارٍ من أربع ساعات فصاعدًا لأنّها كلّها على منتصف ليل الخادم؛ وما دونها على حدود الساعة فلا يتأثّر.
    الشمعة المؤجَّلة لا تضيع: أحدث المحفوظ قبلها، فالتشغيل التالي يلتقطها."""
    seconds = PERIODS[period][1]
    margin = DST_MARGIN_S if seconds >= 4 * 3600 else 0
    if period != "MN1":
        return (start_s + seconds + margin) * MS
    inside = datetime.fromtimestamp(start_s + 86400, timezone.utc)
    days = calendar.monthrange(inside.year, inside.month)[1]
    return (start_s + days * 86400 + margin) * MS


def decode_bars(period: str, raw: list[dict[str, Any]], now_ms: int) -> list[tuple]:
    """إلى (بداية، فتح، قمّة، قاع، إغلاق، حجم). الشمعة التي لم تُغلق بعدُ تُترك — قيمها تتغيّر."""
    bars = []
    for tb in raw:
        if tb.get("low") is None or tb.get("utcTimestampInMinutes") is None:
            continue
        start_s = int(tb["utcTimestampInMinutes"]) * 60
        if bar_end_ms(period, start_s) > now_ms:
            continue
        low = int(tb["low"])
        o, h, c = (low + int(tb.get(k) or 0) for k in ("deltaOpen", "deltaHigh", "deltaClose"))
        bars.append((start_s, round(o / PRICE_SCALE, 5), round(h / PRICE_SCALE, 5),
                     round(low / PRICE_SCALE, 5), round(c / PRICE_SCALE, 5), int(tb.get("volume") or 0)))
    return bars


class Fetcher:
    def __init__(self, link: Link, store: Store, account_id: int, log: Callable[[str], None] = print):
        self.link, self.store, self.account_id, self.log = link, store, account_id, log
        self.period_as_name = store.meta("period_as_name") == "1"

    def trendbars(self, symbol_id: int, period: str, frm: int, to: int) -> tuple[list[dict], bool]:
        tried_name = self.period_as_name
        while True:
            payload = {"ctidTraderAccountId": self.account_id, "symbolId": symbol_id,
                       "period": period if self.period_as_name else PERIODS[period][0],
                       "fromTimestamp": frm, "toTimestamp": to}
            try:
                body = self.link.request(TRENDBARS_REQ, payload, TRENDBARS_RES)
            except ApiError as exc:
                if exc.code in ("REQUEST_FREQUENCY_EXCEEDED", "BLOCKED_PAYLOAD_TYPE"):
                    time.sleep(exc.retry_after or 1.0)
                    continue
                if exc.code == "INVALID_REQUEST" and not tried_name:
                    # صيغة الإطار في JSON غير منشورة: نجرّب الاسم بدل الرقم مرّة، ونحفظه إن نجح.
                    tried_name = self.period_as_name = True
                    continue
                if self.store.meta("period_as_name") != "1":
                    self.period_as_name = False
                raise
            if self.period_as_name and self.store.meta("period_as_name") != "1":
                self.store.meta("period_as_name", "1")
            return list(body.get("trendbar") or []), bool(body.get("hasMore"))

    def series(self, symbol: str, symbol_id: int, period: str, floor_ms: int | None) -> dict[str, Any]:
        """إلى الأمام من أحدث المحفوظ حتى الآن، ثمّ إلى الخلف حتى أوّل التاريخ إن لم يكتمل."""
        prog = self.store.progress(symbol, period)
        prog["window_ms"] = prog["window_ms"] or START_WINDOW_DAYS[period] * DAY_MS
        prog["note"] = None
        now_ms = int(time.time() * MS)
        if prog["newest_ms"] is not None:
            top = self._walk(symbol, symbol_id, period, prog, prog["newest_ms"] + 1, now_ms, now_ms, None, False)
            # أحدث المحفوظ لا يتقدّم إلّا بعد أن يتّصل المشي بما قبله — انقطاعٌ في منتصفه لا يترك فجوة.
            if top is not None and prog["note"] is None:
                prog["newest_ms"] = max(prog["newest_ms"], top)
                self.store.save(symbol, period, [], prog)
        if not prog["complete"] and prog["note"] is None:
            hi = prog["oldest_ms"] - 1 if prog["oldest_ms"] is not None else now_ms
            self._walk(symbol, symbol_id, period, prog, floor_ms or 0, hi, now_ms,
                       None if floor_ms else EMPTY_STOP_MS, True)
            if prog["note"] is None:
                prog["complete"] = 1
                self.store.save(symbol, period, [], prog)
        return prog

    def _walk(self, symbol: str, symbol_id: int, period: str, prog: dict[str, Any], lo: int, hi: int,
              now_ms: int, empty_stop: int | None, backward: bool) -> int | None:
        """من `hi` إلى الخلف حتى `lo` بنوافذ تُنصَّف عند الرفض أو حين يبقى المزيد.

        في مشي التاريخ (`backward`) يتقدّم الأقدم والأحدث مع كلّ نافذة لأنّ المغطّى متّصلٌ بـ`hi`.
        وفي مشي الإلحاق يُرجَع أحدث ما رُئي ولا يُكتب إلّا عند الاتّصال."""
        min_window = PERIODS[period][1] * MS * 2
        to, empty, top = hi, 0, None
        while to > lo:
            frm = max(lo, to - prog["window_ms"])
            try:
                raw, has_more = self.trendbars(symbol_id, period, frm, to)
            except ApiError as exc:
                if exc.code == "INCORRECT_BOUNDARIES" and prog["window_ms"] // 2 >= min_window:
                    prog["window_ms"] //= 2
                    continue
                prog["note"] = "%s %s" % (exc.code, exc.description)
                self.store.save(symbol, period, [], prog)
                self.log("   ✘ %s %s: %s" % (symbol, period, prog["note"]))
                return top
            prog["requests"] += 1
            bars = decode_bars(period, raw, now_ms)
            if has_more:
                # الردّ جزءٌ من النافذة ولا نعرف أيّ طرفيها: نحفظ الشموع ولا نحرّك التقدّم، وننصّف.
                self.store.save(symbol, period, bars, None)
                if prog["window_ms"] // 2 < min_window:
                    prog["note"] = "hasMore عند أصغر نافذة"
                    self.store.save(symbol, period, [], prog)
                    return top
                prog["window_ms"] //= 2
                continue
            if bars:
                first, last = min(b[0] for b in bars) * MS, max(b[0] for b in bars) * MS
                top = last if top is None else max(top, last)
                if backward:
                    prog["oldest_ms"] = first if prog["oldest_ms"] is None else min(prog["oldest_ms"], first)
                    prog["newest_ms"] = last if prog["newest_ms"] is None else max(prog["newest_ms"], last)
            self.store.save(symbol, period, bars, prog)
            empty = 0 if raw else empty + (to - frm)
            if empty_stop is not None and empty >= empty_stop:
                return top
            to = frm - 1
            if prog["requests"] % 40 == 0:
                self.log("   … %s %s وصل %s · طلبات %d" % (symbol, period, _day(frm), prog["requests"]))
        return top


def _day(ms: int | None) -> str:
    return "—" if ms is None else datetime.fromtimestamp(ms / MS, timezone.utc).strftime("%Y-%m-%d")


def _norm(name: str) -> str:
    return "".join(ch for ch in name.upper() if ch.isalnum())


# ─────────────────────────────────────────────────────────── المسار ──

def authorize_app(link: Link, client_id: str, client_secret: str) -> None:
    link.request(APP_AUTH_REQ, {"clientId": client_id, "clientSecret": client_secret}, APP_AUTH_RES)


def pick_account(link: Link, token: str, login: str, log: Callable[[str], None]) -> int:
    body = link.request(ACCOUNTS_BY_TOKEN_REQ, {"accessToken": token}, ACCOUNTS_BY_TOKEN_RES)
    scope = body.get("permissionScope")
    if scope not in SCOPE_VIEW_VALUES:
        raise Refused("رمز الدخول بصلاحيّة %r — الأداة لا تعمل إلّا بصلاحيّة العرض (accounts)" % (scope,))
    log("   الصلاحيّة: عرضٌ فقط%s" % ("" if scope is not None else " (غير مذكورة؛ افتراضها في البروتو عرض)"))
    accounts = body.get("ctidTraderAccount") or []
    for acc in accounts:
        if str(acc.get("traderLogin")) == login and acc.get("isLive"):
            return int(acc["ctidTraderAccountId"])
    seen = ", ".join("%s(%s)" % (a.get("traderLogin"), "حيّ" if a.get("isLive") else "تجريبيّ") for a in accounts)
    raise Refused("الحساب %s الحيّ ليس بين حسابات الرمز: %s" % (login, seen or "لا شيء"))


def resolve_symbols(link: Link, account_id: int, wanted: list[str], log: Callable[[str], None]) -> dict[str, int]:
    body = link.request(SYMBOLS_LIST_REQ, {"ctidTraderAccountId": account_id}, SYMBOLS_LIST_RES)
    by_name = {_norm(str(s.get("symbolName", ""))): int(s["symbolId"])
               for s in body.get("symbol") or [] if s.get("symbolId") is not None}
    found = {}
    for name in wanted:
        if _norm(name) in by_name:
            found[name] = by_name[_norm(name)]
        else:
            near = [n for n in by_name if _norm(name)[:3] in n][:10]
            log("   ✘ الرمز %s غير موجود؛ القريب: %s" % (name, ", ".join(near) or "لا شيء"))
    return found


def open_account(link: Link, store: Store, token: str, login: str, log: Callable[[str], None]) -> int:
    account_id = pick_account(link, token, login, log)
    link.request(ACCOUNT_AUTH_REQ, {"ctidTraderAccountId": account_id, "accessToken": token}, ACCOUNT_AUTH_RES)
    log("✓ عُرِّف الحساب %s للقراءة" % login)
    store.meta("account_login", login)
    return account_id


def probe_ticks(link: Link, store: Store, account_id: int, symbol: str, symbol_id: int,
                log: Callable[[str], None] = print) -> str | None:
    """يقيس صيغة سعر التِّكّة بمطابقتها مع شموع الدقيقة المحفوظة، ويحفظ ما يقع داخلها (≥99٪)."""
    newest = store.db.execute("SELECT MAX(period_start) FROM candles_history WHERE symbol=? AND period='M1'",
                              (symbol,)).fetchone()[0]
    if newest is None:
        log("   ✘ لا شموع دقيقة محفوظة لـ%s — اجلب الشموع أوّلًا" % symbol)
        return None
    to = newest * MS + 60 * MS - 1
    raw, _more = TickFetcher(link, store, account_id, "absolute", log).request(
        symbol_id, QUOTE_SIDES["bid"], to - 30 * 60 * MS, to)
    log("   عيّنة خام: أوّل ثلاث %s" % [(e.get("timestamp"), e.get("tick")) for e in raw[:3]])
    scores = {}
    for convention in TICK_CONVENTIONS:
        inside, total = containment(store, symbol, decode_ticks(raw, convention))
        scores[convention] = (inside, total)
        log("   %-12s داخل الشمعة %d من %d" % (convention, inside, total))
    best = max(scores, key=lambda c: scores[c][0] / scores[c][1] if scores[c][1] else 0.0)
    inside, total = scores[best]
    if total < 50 or inside / total < 0.99:
        log("   ✘ لا تفسير يقع داخل الشموع بثقة (%s %d/%d) — لا يُحفظ ولا يُجلب" % (best, inside, total))
        return None
    store.meta("tick_convention", best)
    store.meta("tick_convention_evidence", "%s %d/%d %s" % (symbol, inside, total, _day(to)))
    log("✓ صيغة السعر مقيسة: %s (%d/%d داخل شموع الدقيقة)" % (best, inside, total))
    return best


def run_range(link: Link, store: Store, account_id: int, symbols: list[str], lo_ms: int, hi_ms: int,
              log: Callable[[str], None] = print) -> None:
    """مدّةٌ بعينها أوّلًا (المالك ١٧/١٠: سنة 2023 قبل غيرها)."""
    convention = store.meta("tick_convention")
    if convention not in TICK_CONVENTIONS:
        raise Refused("صيغة سعر التِّكّة لم تُقَس بعد — شغّل --probe-ticks أوّلًا")
    fetcher = TickFetcher(link, store, account_id, convention, log)
    for symbol, symbol_id in resolve_symbols(link, account_id, symbols, log).items():
        for name, side in QUOTE_SIDES.items():
            prog = fetcher.range(symbol, symbol_id, side, lo_ms, hi_ms)
            n = store.db.execute("SELECT COUNT(*) FROM ticks_history WHERE symbol=? AND side=? AND ts_ms>=? AND ts_ms<?",
                                 (symbol, side, lo_ms, hi_ms)).fetchone()[0]
            log("   %s %-3s المدّة %s ⟵ %s: %12d تِكّة · طلبات %d · %s%s" % (
                symbol, name, _day(lo_ms), _day(hi_ms), n, prog["requests"], "اكتملت" if prog["done"] else "لم تكتمل",
                "  ✘ " + prog["note"] if prog["note"] else ""))


def run_ticks(link: Link, store: Store, account_id: int, symbols: list[str], days: float,
              log: Callable[[str], None] = print, since_ms: int | None = None) -> None:
    convention = store.meta("tick_convention")
    if convention not in TICK_CONVENTIONS:
        raise Refused("صيغة سعر التِّكّة لم تُقَس بعد — شغّل --probe-ticks أوّلًا")
    since_ms = since_ms if since_ms is not None else int((time.time() - days * 86400) * MS)
    fetcher = TickFetcher(link, store, account_id, convention, log)
    for symbol, symbol_id in resolve_symbols(link, account_id, symbols, log).items():
        for name, side in QUOTE_SIDES.items():
            prog = fetcher.series(symbol, symbol_id, side, since_ms)
            n, first, last = store.tick_count(symbol, side)
            log("   %s %-3s %12d تِكّة  %s ← %s  طلبات %d%s" % (
                symbol, name, n, _day(first), _day(last), prog["requests"],
                "  ✘ " + prog["note"] if prog["note"] else ""))


def run(link: Link, store: Store, token: str, login: str, symbols: list[str], periods: list[str],
        log: Callable[[str], None] = print, account_id: int | None = None) -> None:
    """بعد تفويض التطبيق: الحساب للقراءة، ثمّ الرموز، ثمّ الشموع — الأكبر إطارًا أوّلًا."""
    if account_id is None:
        account_id = open_account(link, store, token, login, log)
    fetcher = Fetcher(link, store, account_id, log)
    for symbol, symbol_id in resolve_symbols(link, account_id, symbols, log).items():
        store.meta("symbol_id." + symbol, symbol_id)
        first_month = store.count(symbol, "MN1")[1]
        floor_ms = first_month * MS if first_month is not None else None
        for period in sorted(periods, key=lambda p: -PERIODS[p][1]):
            prog = fetcher.series(symbol, symbol_id, period, None if period == "MN1" else floor_ms)
            n, first, last = store.count(symbol, period)
            if period == "MN1" and first is not None:
                floor_ms = first * MS                  # أوّل شهرٍ عند الوسيط = أرض كلّ الأطر الأصغر
            log("   %s %-4s %10d شمعة  %s ← %s  طلبات %d  نافذة %.2f يوم%s" % (
                symbol, period, n, _day(first * MS if first else None), _day(last * MS if last else None),
                prog["requests"], prog["window_ms"] / DAY_MS, "  ✘ " + prog["note"] if prog["note"] else ""))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="جلب تاريخ الشموع من سي‑تريدر — قراءة فقط")
    ap.add_argument("--check", action="store_true", help="تفويض التطبيق وحده (المعرّف والسرّ)")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--periods", default=",".join(PERIODS))
    ap.add_argument("--login", default=None, help="رقم حساب سي‑تريدر (افتراضيًّا من إعداد 622)")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--no-bars", action="store_true", help="بلا شموع (للتِّكّات وحدها)")
    ap.add_argument("--probe-ticks", action="store_true",
                    help="يقيس صيغة سعر التِّكّة على أوّل رمز بمطابقتها مع شموع الدقيقة المحفوظة")
    ap.add_argument("--ticks-days", type=float, default=0.0, help="تِكّات العرض والطلب لآخر N يومًا")
    ap.add_argument("--ticks-range", default="", help="مدّةٌ بعينها أوّلًا: من,إلى (تاريخان، الثاني غير مشمول)")
    ap.add_argument("--ticks-since", default="", help="بعدها: كلّ التاريخ إلى الوراء حتّى هذا التاريخ")
    args = ap.parse_args(argv)

    def _ms(day: str) -> int:
        return int(datetime.fromisoformat(day.strip()).replace(tzinfo=timezone.utc).timestamp() * MS)

    names = (SECRET_CLIENT_ID, SECRET_CLIENT_SECRET) + (() if args.check else (SECRET_ACCESS_TOKEN,))
    secrets = load_secrets(*names)
    missing = [n for n in names if not secrets[n]]
    if missing:
        print("✘ ناقص في الخزنة: %s — يُضاف من «التحكّم والمخاطر» ← «الأمان»" % ", ".join(missing))
        return 2
    periods = [p for p in args.periods.split(",") if p in PERIODS]
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    login = args.login or default_login()

    from websockets.exceptions import ConnectionClosed
    print("الاتّصال بـ %s …" % URI)
    try:
        with open_link() as link:
            authorize_app(link, secrets[SECRET_CLIENT_ID], secrets[SECRET_CLIENT_SECRET])
            print("✓ تفويض التطبيق نجح (المعرّف والسرّ صحيحان)")
            if args.check:
                return 0
            store = Store(args.db)
            try:
                account_id = open_account(link, store, secrets[SECRET_ACCESS_TOKEN], login, print)
                if not args.no_bars and not args.probe_ticks:
                    run(link, store, secrets[SECRET_ACCESS_TOKEN], login, symbols, periods,
                        account_id=account_id)
                if args.probe_ticks:
                    ids = resolve_symbols(link, account_id, symbols[:1], print)
                    for symbol, symbol_id in ids.items():
                        if probe_ticks(link, store, account_id, symbol, symbol_id) is None:
                            return 4
                if args.ticks_range:
                    lo_day, hi_day = args.ticks_range.split(",")
                    run_range(link, store, account_id, symbols, _ms(lo_day), _ms(hi_day))
                if args.ticks_since:
                    run_ticks(link, store, account_id, symbols, 0.0, since_ms=_ms(args.ticks_since))
                elif args.ticks_days > 0:
                    run_ticks(link, store, account_id, symbols, args.ticks_days)
            finally:
                store.db.close()
        print("✓ انتهى. القاعدة: %s" % args.db)
        return 0
    except Refused as exc:
        print("⛔ %s" % exc)
        return 3
    except (ApiError, LinkClosed, ConnectionClosed, OSError) as exc:
        print("✘ %s" % exc)
        return 1
    except KeyboardInterrupt:
        print("أُوقف يدويًّا — التقدّم محفوظ، والتشغيل التالي يُكمل من حيث توقّف")
        return 130
    finally:
        secrets.clear()


if __name__ == "__main__":
    raise SystemExit(main())
