"""تسعير قرار الفائدة (121) — ما يسعّره سوق عقود الفائدة الفيدراليّة لاجتماعات الفيدراليّ القادمة، حقائق خام بلا حكم.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا، و«تسعير الفائدة حيًّا يحتاج ياهو NQ»): ياهو مصدرٌ حيّ لهذا الرقم وحده.
الذرّة تعرف ولا تقرّر: لا تدخل قرار الدخول، ولا في حمولتها جهةٌ ولا وزنٌ ولا ثقة (عقد الحقائق ١٠-٠٧) — والنسب
سعرُ سوقٍ مقروء من العقود، لا حكمُ ذرّة ولا توقّع النظام.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — «الأخبار من مكانٍ واحد — ما نشتّت، نجمعهم تحت سقفٍ واحد»): **الذرّة لا تتّصل
بالإنترنت أبدًا.** جلب عقود الفائدة الفيدراليّة لثلاثين يومًا (CBOT · ZQ) من ياهو صار في **بوت الأخبار**
(مشروع `QUANT_NQ_NEWS` المستقلّ) يكتبها كلّ 15 دقيقة في قاعدة الجسر `nq_brain.db` جدول `fed_futures`؛ والذرّة
تقرؤه **للقراءة فقط** (`mode=ro`، مهلة قفلٍ قصيرة) في خيطٍ جانبيّ (`asyncio.to_thread`) مع كلّ `SYS_5MIN` وبعد
~30 ث من الإقلاع. (نسختها الأولى كانت تجلب من ياهو بنفسها — أُزيل ذلك كلّه بالأمر نفسه.)
وجدول الاجتماعات من موقع الفيدراليّ (في `config`)، والحدّ الأعلى للنطاق من 118 (`knowledge.monetary.state`).
الحساب في `fed_pricing_chain.py`، والحقائق وسطرها العربيّ في `fed_pricing_facts.py` (دوالّ صافية كلتاهما).

حدودٌ تُعلن: أسعار ياهو قد تتأخّر ~10–20 د (عمر السعر وعمر الجلب يُنشران) · اجتماعات 2027 مبدئيّة · تسعير السوق
لا توقّع النظام · غياب القاعدة أو الجدول ⟸ «غير متاح» بسببه، لا انهيار.
"""
from __future__ import annotations

import asyncio
import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import clock
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
import fed_pricing_chain as chain
import fed_pricing_facts as facts_text

ATOM_VERSION = "1.0.0"
ATOM_ID = "121"
SYMBOL = "USTEC"
PAYLOAD_ID = "fed_decision_pricing"
EV_PULSE = "SYS_5MIN"
EV_MONETARY = "knowledge.monetary.state"
EV_OUT = "knowledge.fed_pricing.state"
SOURCE_NAME = ("bridge nq_brain.db · fed_futures (news bot ⟵ yahoo_finance chart v8 · CBOT 30-Day Fed Funds futures ZQ) "
               "· FOMC calendar federalreserve.gov · target range knowledge.monetary.state (118)")
SCHEDULE_SOURCE = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

DEFAULT_BRIDGE_DB = r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_brain.db"
BRIDGE_ENV = "NQ_BRIDGE_DB"                    # مرسى الجسر (يضبطه الإقلاع، وللاختبار) يسبق `config` — كما 118
BRIDGE_TABLE = "fed_futures"
BRIDGE_TIMEOUT_S = 1.0                         # البوت يكتب في الجسر: مهلة قفلٍ قصيرة ثمّ «تعذّرت القراءة» — كما 118
BRIDGE_COLUMNS = ("symbol", "contract_month", "price", "implied_rate", "market_time_utc", "fetched_at_utc", "source")
SELECT_ROWS = "SELECT %s FROM %s" % (", ".join(BRIDGE_COLUMNS), BRIDGE_TABLE)
TABLE_EXISTS = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
SYMBOL_RE = re.compile(r"^ZQ([FGHJKMNQUVXZ])(\d{2})\.CBT$")
CENTURY = 2000

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
BOOT_DELAY_S = 30.0
DETAIL_CHARS = facts_text.DETAIL_CHARS
# مرميّات معلنة
BAD_PULSE = "bad_pulse"
BAD_MONETARY = "bad_monetary"
NO_TARGET = "monetary_without_rate"
BUSY = "busy_skip"
BAD_DAY = "bad_schedule_day"
BAD_SNAPSHOT_QUOTE = "bad_snapshot_quote"

_iso = facts_text.iso


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _valid(quote: dict[str, Any]) -> bool:
    """سعر عقد الفائدة بين 0 و100 (الضمنيّ = 100 − السعر) ووقتُ سوقٍ معروف."""
    price, at = _num(quote.get("price")), _num(quote.get("market_time"))
    return price is not None and at is not None and 0 < price < 100


def resolve_bridge_path(configured: str | None) -> str:
    return os.environ.get(BRIDGE_ENV) or os.path.expandvars(configured or DEFAULT_BRIDGE_DB)


def month_of(symbol: str, contract_month: Any) -> str | None:
    """«YYYY-MM» من `contract_month`، وإلّا من رمز العقد (ZQX26.CBT ⟸ 2026-11) — ويُشترط أن يطابق الرمزُ الشهر."""
    ym = facts_text.parse_label(str(contract_month or ""))
    code = SYMBOL_RE.match(symbol)
    if ym is None and code is not None:
        ym = (CENTURY + int(code.group(2)), chain.MONTH_CODES.index(code.group(1)) + 1)
    if ym is None or chain.contract_symbol(*ym) != symbol:
        return None
    return chain.month_label(ym)


# ── القراءة (خيطٌ جانبيّ، قراءةً فقط — لا شبكة) ───────────────────────────────
def _row_quote(row: tuple) -> dict[str, Any] | None:
    item = dict(zip(BRIDGE_COLUMNS, row))
    symbol = str(item["symbol"] or "")
    price, implied = _num(item["price"]), _num(item["implied_rate"])
    quote = {"symbol": symbol, "month": month_of(symbol, item["contract_month"]),
             "price": price if price is not None or implied is None else 100 - implied,
             "market_time": _num(item["market_time_utc"]), "fetched_at": _num(item["fetched_at_utc"]),
             "source": str(item["source"] or "")}
    return quote if quote["month"] is not None and _valid(quote) else None


def read_bridge(path: str) -> dict[str, Any]:
    """يُستدعى في `asyncio.to_thread`. غياب القاعدة أو الجدول أو تعذّر القراءة ⟸ سببٌ مسمًّى لا استثناء."""
    if not os.path.isfile(path):
        return {"error": facts_text.BRIDGE_MISSING, "detail": path}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % Path(path).as_posix(), uri=True, timeout=BRIDGE_TIMEOUT_S)
        try:
            if con.execute(TABLE_EXISTS, (BRIDGE_TABLE,)).fetchone() is None:
                return {"error": facts_text.TABLE_MISSING, "detail": BRIDGE_TABLE}
            rows = con.execute(SELECT_ROWS).fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"error": facts_text.READ_FAILED, "detail": str(exc)[:DETAIL_CHARS]}
    quotes: dict[str, dict[str, Any]] = {}
    bad = []
    for row in rows:
        quote = _row_quote(row)
        if quote is None:
            bad.append(str(row[0])[:DETAIL_CHARS])
            continue
        label = quote.pop("month")
        old = quotes.get(label)
        if old is None or (quote["fetched_at"] or 0) >= (old["fetched_at"] or 0):
            quotes[label] = quote
    return {"quotes": quotes, "rows": len(rows), "bad_rows": bad}


def safe_read(reader: Any, path: str) -> dict[str, Any]:
    """آخر حارس حول القارئ (القارئ قابلٌ للاستبدال في الاختبار): أيّ فشلٍ سببٌ معلن لا انهيار الذرّة."""
    try:
        result = reader(path)
    except Exception as exc:  # noqa: BLE001
        return {"error": facts_text.READ_FAILED, "detail": ("%s: %s" % (type(exc).__name__, exc))[:DETAIL_CHARS]}
    return result if isinstance(result, dict) else {"error": facts_text.READ_FAILED, "detail": repr(result)[:DETAIL_CHARS]}


# ── الحمولة ────────────────────────────────────────────────────────────────────
def build_payload(state: dict[str, Any], now: float) -> dict[str, Any]:
    try:
        facts = facts_text.build_facts(state, now)
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as exc:   # لا انهيار: سببٌ معلن
        facts = facts_text.failed_facts("%s: %s" % (type(exc).__name__, exc))
    return {"id": PAYLOAD_ID, "symbol": SYMBOL, "status": STATUS_OK if facts["pricing_available"] else STATUS_UNAVAILABLE,
            "facts": facts, "computed_at": now, "summary_ar": facts_text.summary_ar(facts), "source": SOURCE_NAME}


# ── الذرّة ─────────────────────────────────────────────────────────────────────
class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._boot_delay_s = BOOT_DELAY_S
        self._bridge_config = DEFAULT_BRIDGE_DB
        self._schedule: list[dict[str, Any]] = []
        self._schedule_source = SCHEDULE_SOURCE
        self._clock = clock.now               # الساعة الرسميّة؛ والنبضة تحمل وقتها فيُقدَّم
        self._read = read_bridge              # القارئ الحقيقيّ — يُستبدل في الاختبار
        self._boot_task: asyncio.Future | None = None
        self._busy = False
        self._quotes: dict[str, dict[str, Any]] = {}
        self._last_read: dict[str, Any] | None = None
        self._target_upper: float | None = None
        self._target_at: float | None = None
        self._last: dict[str, Any] | None = None
        self._published = 0
        self._reads = 0
        self._read_errors = 0
        self._rejected: dict[str, int] = {}

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._boot_delay_s = float(cfg.get("boot_delay_s", BOOT_DELAY_S))
        self._bridge_config = str(cfg.get("bridge_db_path") or DEFAULT_BRIDGE_DB)
        self._schedule_source = str(cfg.get("fomc_schedule_source") or SCHEDULE_SOURCE)
        self._schedule, bad = chain.build_schedule(cfg.get("fomc_decision_days"), cfg.get("fomc_tentative_days"))
        if bad:
            self._rejected[BAD_DAY] = bad
        context.subscribe(EV_PULSE, self._on_pulse)
        context.subscribe(EV_MONETARY, self._on_monetary)

    async def start(self) -> None:
        self._running = True
        # الإقلاع يبدأ الذرّات بترتيب أرقامها — فالنشر فورًا يسبق اشتراك من يسمع. يُؤجَّل كما 118 و153.
        self._boot_task = asyncio.ensure_future(self._boot_refresh())
        self._boot_task.add_done_callback(self._task_done)

    async def stop(self) -> None:
        self._running = False
        if self._boot_task is not None and not self._boot_task.done():
            self._boot_task.cancel()

    async def shutdown(self) -> None:
        await self.stop()

    def _task_done(self, task: asyncio.Future) -> None:
        if not task.cancelled() and task.exception() is not None and self._context is not None:
            self._context.logger.error("121 boot refresh failed: %s", task.exception())

    async def _boot_refresh(self) -> None:
        try:
            await asyncio.sleep(self._boot_delay_s)
            if self._running:
                await self.refresh(self._clock())
        except asyncio.CancelledError:
            pass

    def _reject(self, reason: str) -> None:
        self._rejected[reason] = self._rejected.get(reason, 0) + 1

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        if not isinstance(payload, dict):
            self._reject(BAD_PULSE)
            return
        await self.refresh(_num(payload.get("official_time")) or self._clock())

    async def _on_monetary(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        facts = payload.get("facts") if isinstance(payload, dict) else None
        if not isinstance(facts, dict):
            self._reject(BAD_MONETARY)
            return
        upper = _num(facts.get("fed_rate_current"))
        if upper is None:                      # 118 بلا فائدة معروفة ⟸ يبقى آخر ما عُرف بوقته
            self._reject(NO_TARGET)
            return
        self._target_upper, self._target_at = upper, _num(payload.get("computed_at")) or self._clock()

    def _absorb(self, result: dict[str, Any], now: float) -> None:
        error = result.get("error")
        self._reads += 1
        self._last_read = {"at": now, "error": error, "detail": str(result.get("detail") or "")[:DETAIL_CHARS],
                           "rows": result.get("rows"), "bad_rows": list(result.get("bad_rows") or [])}
        if error:
            # آخر الأسعار المقروءة تبقى بأعمارها؛ وغياب القاعدة أو الجدول يُعلَن «غير متاح» ولا يُسعَّر منها (fed_pricing_facts).
            self._read_errors += 1
            return
        self._quotes = dict(result.get("quotes") or {})

    def _state(self) -> dict[str, Any]:
        return {"quotes": self._quotes, "last_read": self._last_read, "schedule": self._schedule,
                "schedule_source": self._schedule_source, "target_upper": self._target_upper,
                "target_at": self._target_at}

    async def refresh(self, now: float) -> dict[str, Any] | None:
        """قراءةٌ في خيطٍ جانبيّ ثمّ حسابٌ ونشر. قراءةٌ لم تنتهِ بعد ⟸ النبضة تُعدّ وتُترك (لا تتراكم القراءات)."""
        if self._busy:
            self._reject(BUSY)
            return None
        self._busy = True
        try:
            result = await asyncio.to_thread(safe_read, self._read, resolve_bridge_path(self._bridge_config))
        finally:
            self._busy = False
        self._absorb(result, now)
        payload = build_payload(self._state(), now)
        self._last = payload
        if self._running and self._context is not None:
            await self._context.publish(EV_OUT, payload)
            self._published += 1
        return payload

    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "quotes": {label: dict(q) for label, q in self._quotes.items()},
                "last_read": self._last_read, "target_upper": self._target_upper, "target_at": self._target_at,
                "last": self._last, "published": self._published, "reads": self._reads,
                "read_errors": self._read_errors, "rejected": dict(self._rejected)}

    def _restore_quote(self, key: Any, quote: Any) -> None:
        # المفتاح «YYYY-MM»، أو رمز العقد في لقطة النسخة الأولى (كانت تجلب من ياهو بنفسها).
        key = str(key)
        label = key if facts_text.parse_label(key) is not None else month_of(key, None)
        if label is None or not isinstance(quote, dict) or not _valid(quote):
            self._reject(BAD_SNAPSHOT_QUOTE)
            return
        self._quotes[label] = {"symbol": chain.contract_symbol(*facts_text.parse_label(label)),
                               "price": _num(quote["price"]), "market_time": _num(quote["market_time"]),
                               "fetched_at": _num(quote.get("fetched_at")), "source": str(quote.get("source") or "snapshot")}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        quotes = state.get("quotes")
        for key, quote in (quotes.items() if isinstance(quotes, dict) else ()):
            self._restore_quote(key, quote)
        if _num(state.get("target_upper")) is not None:
            self._target_upper, self._target_at = _num(state["target_upper"]), _num(state.get("target_at"))
        last = state.get("last")
        if isinstance(last, dict) and last.get("id") == PAYLOAD_ID and isinstance(last.get("facts"), dict):
            self._last = last
        self._published = int(_num(state.get("published")) or 0)
        self._reads = int(_num(state.get("reads")) or 0)
        self._read_errors = int(_num(state.get("read_errors")) or 0)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        counters = "قراءات=%d · أخطاء قراءة=%d · نشرات=%d · مرميّات=%s" % (
            self._reads, self._read_errors, self._published,
            " ".join("%s=%d" % kv for kv in sorted(self._rejected.items())) or "0")
        details = {"reads": self._reads, "read_errors": self._read_errors, "published": self._published,
                   "rejected": dict(self._rejected), "quotes": len(self._quotes), "meetings": len(self._schedule),
                   "bridge_path": resolve_bridge_path(self._bridge_config)}
        last = self._last
        if last is None:
            return HealthStatus(state=HealthState.DEGRADED, details=details,
                                message="لم يُقرأ جدول الجسر بعد (القراءة الأولى بعد ~%d ث من الإقلاع) · %s" % (
                                    int(self._boot_delay_s), counters))
        facts = last["facts"]
        if not facts.get("pricing_available"):
            return HealthStatus(state=HealthState.DEGRADED, details=details,
                                message="%s · %s" % (last.get("summary_ar"), counters))
        message = "الاجتماع القادم %s بعد %s يومًا: %+.1f ن.أ مسعَّرة · عقود=%d/%d · السعر قبل %s د والجلب قبل %s د · " \
                  "آخر قراءة للجسر %s · %s" % (
                      facts["next_fomc_date"], facts["days_to_next_fomc"], facts["expected_change_bp_next"],
                      facts["contracts_available"], facts["contracts_in_window"], facts["quotes_age_minutes"],
                      facts["fetched_age_minutes"], facts["bridge_read_utc"], counters)
        return HealthStatus(state=HealthState.HEALTHY, message=message, details=details)
