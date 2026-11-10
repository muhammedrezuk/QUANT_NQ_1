"""معرفة الشركات والأسواق (122) — ما تفعله الشركات التي تحمل الناسداك الآن، ومتى تعلن أرباحها، بلا حكم.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): «قبل كلّ شي لازم يعرف النظام هاد الشي ثمّ الباقي» · «بس بميتاتريدر في
كلّ الأسهم موجودة». حقائق خامٌ تُختم على كلّ صفقة ولا تدخل قرار الدخول (عقد الحقائق ١٠-٠٧: لا جهة ولا وزن ولا ثقة).
تنشر `knowledge.companies.state` كلّ دقيقة (عدّادٌ على SYS_SECOND)، وبعد كلّ قراءةٍ لجدولَي الأرباح (SYS_5MIN).

المصادر — قراءةً فقط، والعمل الثقيل في خيطٍ جانبيّ (`asyncio.to_thread`)، و**لا اتّصال بالإنترنت**:
  · `nq_stocks.db` — يكتبه إكسبرت القراءة NQ_StocksSync كلّ دقيقة (`companies_quotes.py`).
  · شموع 103 `market_data.candle_closed` للناسداك (1m و1d) + قاعدة تاريخ سي‑تريدر عند الإقلاع وكلّ يوم وسيطٍ جديد
    (`companies_nasdaq.py`).
  · قاعدة الجسر `nq_brain.db` جدولا `earnings_calendar` و`earnings_history` — يكتبهما بوت الأخبار (QUANT_NQ_NEWS) من
    موقع بورصة ناسداك الرسميّ مرّةً في اليوم، بأمر المالك «الأخبار من مكانٍ واحد» (`companies_earnings.py`).
الحدّ المعلن: مواعيد الأرباح قد تكون تقديريّة حتّى تؤكّدها الشركة؛ وأسعار الأسهم بائتة خارج الجلسة الأمريكيّة.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import clock
import companies_earnings as earnings
import companies_nasdaq as nasdaq
import companies_quotes as quotes
import companies_report as report
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "1.0.0"
ATOM_ID = "122"
PAYLOAD_ID = "companies_markets_knowledge"
SOURCE = ("mt5 nq_stocks.db (NQ_StocksSync) · market_data.candle_closed USTEC 1m/1d · ctrader_history.db D1/M1 · "
          "nq_brain.db earnings_calendar/earnings_history (news bot ⟵ api.nasdaq.com)")
EV_SECOND = "SYS_SECOND"
EV_5MIN = "SYS_5MIN"
EV_CANDLE = "market_data.candle_closed"
EV_OUT = "knowledge.companies.state"
FRAME_MINUTE = "1m"
FRAME_DAY = "1d"

DEFAULT_SYMBOL = "USTEC"
DEFAULT_TICKERS = ("NVDA", "MSFT", "AAPL", "AMZN", "AVGO", "META", "GOOGL", "GOOG", "TSLA", "COST", "NFLX", "AMD",
                   "PLTR", "CSCO", "TMUS")
DEFAULT_STOCKS_DB = r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_stocks.db"
DEFAULT_BRIDGE_DB = r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_brain.db"
DEFAULT_HISTORY_DB = r"forex_runtime\var\history\ctrader_history.db"
STOCKS_ENV = "NQ_STOCKS_DB"                       # تسبق `config` (للاختبار أو مسارٍ آخر)
BRIDGE_ENV = "NQ_BRIDGE_DB"
HISTORY_ENV = "QUANT_HISTORY_DB"                  # المتغيّر نفسه الذي يقرؤه 153
#: جذر المشروع — المسار النسبيّ في البيان يُقرأ منه (atoms/قسم/الذرّة/atom.py).
PROJECT_ROOT = Path(__file__).resolve().parents[3]
QUOTES_EVERY_S = 60.0
BOOT_DELAY_S = 30.0                               # بعد اكتمال الإقلاع كلّه (مقيس ~7 ث) — كما 118 و153
WRITER_STALE_MIN = 5.0                            # الإكسبرت يكتب كلّ دقيقة: خمس دقائق بلا كتابة ⟸ متوقّف

BAD_PULSE = "bad_pulse"
BAD_CANDLE = "bad_candle"
BUSY = "busy_skip"
COMPUTE_FAILED = "compute_failed"
READ_CRASHED = "read_crashed"
TASK_BOOT = "boot"


def _resolve(raw: Any, env: str) -> str:
    text = os.environ.get(env) or os.path.expandvars(str(raw or "").strip())
    if not text:
        return ""
    path = Path(text)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def _official(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    value = quotes.num(payload.get("official_time"))
    return value if value is not None and value > 0 else None


async def _guarded(fn: Any, *args: Any) -> dict[str, Any]:
    """قراءةٌ في خيطٍ جانبيّ لا تكسر الذرّة: أيّ استثناءٍ غير متوقَّع ⟸ سببٌ مسمًّى."""
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as exc:  # noqa: BLE001 — الذرّة لا تنهار في أيّ حالة؛ التعذّر حقيقة «غير متاح»
        return {"error": READ_CRASHED, "detail": "%s: %s" % (type(exc).__name__, exc)}


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._symbol = DEFAULT_SYMBOL
        self._tickers = list(DEFAULT_TICKERS)
        self._paths = {"stocks": DEFAULT_STOCKS_DB, "bridge": DEFAULT_BRIDGE_DB, "history": DEFAULT_HISTORY_DB}
        self._quotes_every_s = QUOTES_EVERY_S
        self._boot_delay_s = BOOT_DELAY_S
        self._clock = clock.now                   # الساعة الرسميّة؛ والنبضة تحمل وقتها
        self._tasks: dict[str, asyncio.Task] = {}
        self._tape = nasdaq.NasdaqTape()
        self._stocks: dict[str, Any] | None = None
        self._earnings: dict[str, Any] | None = None
        self._history: dict[str, Any] | None = None
        self._moves: dict = {}
        self._observed: dict[str, dict[str, Any]] = {}
        self._first_pulse: float | None = None
        self._last_quotes: float | None = None
        self._busy = False
        self._last_payload: dict[str, Any] | None = None
        self._published = 0
        self._read_errors = 0
        self._candles = 0
        self._rejected: dict[str, int] = {}
        self._last_error = ""

    # ── دورة الحياة ─────────────────────────────────────────────────────
    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._symbol = str(cfg.get("symbol") or DEFAULT_SYMBOL).upper()
        tickers = cfg.get("tickers")
        if isinstance(tickers, list) and tickers:
            self._tickers = [str(t).strip().upper() for t in tickers if str(t).strip()]
        for name, key in (("stocks", "stocks_db"), ("bridge", "bridge_db"), ("history", "history_db")):
            self._paths[name] = str(cfg.get(key) or self._paths[name])
        self._quotes_every_s = max(1.0, float(cfg.get("quotes_every_s", QUOTES_EVERY_S)))
        self._boot_delay_s = max(0.0, float(cfg.get("boot_delay_s", BOOT_DELAY_S)))
        context.subscribe(EV_SECOND, self._on_second)
        context.subscribe(EV_5MIN, self._on_5min)
        context.subscribe(EV_CANDLE, self._on_candle)

    async def start(self) -> None:
        self._running = True
        task = asyncio.create_task(self._boot())
        self._tasks[TASK_BOOT] = task
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        for name, held in list(self._tasks.items()):
            if held is task:
                self._tasks.pop(name, None)
        if not task.cancelled() and task.exception() is not None:
            self._last_error = "%s: %s" % (type(task.exception()).__name__, task.exception())

    async def stop(self) -> None:
        self._running = False
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    async def shutdown(self) -> None:
        await self.stop()

    def path(self, name: str) -> str:
        env = {"stocks": STOCKS_ENV, "bridge": BRIDGE_ENV, "history": HISTORY_ENV}[name]
        return _resolve(self._paths[name], env)

    def _reject(self, reason: str) -> None:
        self._rejected[reason] = self._rejected.get(reason, 0) + 1

    # ── القراءة والنشر ─────────────────────────────────────────────────
    async def _boot(self) -> None:
        # الإقلاع يبدأ الذرّات بترتيب أرقامها — فالقراءة الأولى بعد المهلة، والثقيل في خيطٍ جانبيّ.
        await asyncio.sleep(self._boot_delay_s)
        if self._running:
            now = self._clock()
            await self.read_history(now)
            await self.read_earnings(now)
            await self.refresh_quotes(now)

    async def read_history(self, now: float) -> None:
        ref = await _guarded(nasdaq.read_history, self.path("history"), self._symbol, now)
        if ref.get("error"):
            self._read_errors += 1
            self._history = {"error": ref["error"], "detail": ref.get("detail"), "read_at": now}
            return
        self._tape.apply_history(ref)
        self._moves = nasdaq.daily_moves(ref["d1"])
        self._history = {"error": None, "read_at": now, "day": nasdaq.broker_day_start(now)}

    async def read_earnings(self, now: float) -> None:
        raw = await _guarded(earnings.read_earnings, self.path("bridge"), list(self._tickers))
        if not raw.get("error"):
            earnings.record_times(self._observed, raw, now)
            self._earnings = raw
            return
        self._read_errors += 1
        held = self._earnings or {}
        if held.get("companies") and not held.get("error"):
            # ٢٠٢٦-١٠-٠٨: تعذّرٌ بعد قراءةٍ ناجحة (الجسر مقفلٌ لحظةً، أو بعد الإقلاع) لا يمحو آخر مواعيد معروفة —
            # تبقى بعمرها (`earnings_fetch_age_h`) ويُعلن التعذّر بسببه (`earnings_last_read_error`).
            self._earnings = {**held, "last_read_error": raw["error"]}
        else:
            self._earnings = raw

    async def refresh_quotes(self, now: float) -> dict[str, Any] | None:
        """قراءةٌ في خيطٍ جانبيّ ثمّ نشر. قراءةٌ لم تنتهِ بعد ⟸ النبضة تُعدّ وتُترك (لا تتراكم القراءات)."""
        if self._busy:
            self._reject(BUSY)
            return None
        self._busy = True
        try:
            raw = await _guarded(quotes.read_stocks, self.path("stocks"))
        finally:
            self._busy = False
        if raw.get("error"):
            self._read_errors += 1
        self._stocks, self._last_quotes = raw, now
        return await self.publish(now)

    async def publish(self, now: float) -> dict[str, Any] | None:
        try:
            facts, status = report.build_facts(self._stocks, self._tape.facts(now), self._earnings, self._observed,
                                               self._moves, self._history, self._tickers, now)
            summary = report.summary_ar(facts)
        except Exception as exc:  # noqa: BLE001 — الذرّة حيّة: التعثّر يُعدّ ويُعلن في الصحّة ولا يكسر النبضة
            self._reject(COMPUTE_FAILED)
            self._last_error = "%s: %s" % (type(exc).__name__, exc)
            return None
        payload = {"id": PAYLOAD_ID, "symbol": self._symbol, "status": status, "facts": facts,
                   "computed_at": now, "summary_ar": summary, "source": SOURCE}
        self._last_payload = payload
        if self._running and self._context is not None:
            await self._context.publish(EV_OUT, payload)
            self._published += 1
        return payload

    # ── المعالجات ───────────────────────────────────────────────────────
    async def _on_second(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        now = _official(payload)
        if now is None:
            self._reject(BAD_PULSE)
            return
        if self._first_pulse is None:
            self._first_pulse = now
        if now - self._first_pulse < self._boot_delay_s:
            return
        if self._last_quotes is not None and 0 <= now - self._last_quotes < self._quotes_every_s:
            return
        await self.refresh_quotes(now)

    async def _on_5min(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        now = _official(payload)
        if now is None:
            self._reject(BAD_PULSE)
            return
        # يومُ وسيطٍ جديد (أو تاريخٌ لم يُقرأ بعد) ⟸ تُعاد قراءة التاريخ مرّةً: إغلاق أمس وافتتاح اليوم وحركة الأيّام.
        if (self._history or {}).get("day") != nasdaq.broker_day_start(now):
            await self.read_history(now)
        await self.read_earnings(now)
        await self.publish(now)

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        if not isinstance(payload, dict):
            self._reject(BAD_CANDLE)
            return
        if str(payload.get("symbol") or "").upper() != self._symbol:
            return
        frame = str(payload.get("timeframe") or "").strip().lower()
        if frame not in (FRAME_MINUTE, FRAME_DAY):
            return
        start, close = quotes.num(payload.get("period_start")), quotes.num(payload.get("close"))
        if start is None or close is None or close <= 0:
            self._reject(BAD_CANDLE)
            return
        self._candles += 1
        if frame == FRAME_MINUTE:
            self._tape.on_minute(start, quotes.num(payload.get("open")) or close, close)
        else:
            self._tape.on_day(start, close)

    # ── الحالة ──────────────────────────────────────────────────────────
    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "earnings": self._earnings, "observed_times": dict(self._observed),
                "nasdaq": self._tape.snapshot(), "last_payload": self._last_payload,
                "published": self._published, "read_errors": self._read_errors, "candles": self._candles,
                "rejected": dict(self._rejected)}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        saved = state.get("earnings")
        if isinstance(saved, dict) and isinstance(saved.get("companies"), dict) and not saved.get("error"):
            self._earnings = saved                # آخر مواعيد قُرئت — تبقى حتّى أوّل قراءةٍ ناجحة بعد الإقلاع
        observed = state.get("observed_times")
        if isinstance(observed, dict):
            self._observed = {str(k): dict(v) for k, v in observed.items()
                              if isinstance(v, dict) and v.get("time") in (earnings.PRE_MARKET, earnings.AFTER_HOURS)}
        self._tape.restore(state.get("nasdaq"))
        last = state.get("last_payload")
        if isinstance(last, dict) and last.get("id") == PAYLOAD_ID and isinstance(last.get("facts"), dict):
            self._last_payload = last
        for name in ("published", "read_errors", "candles"):
            value = quotes.num(state.get(name))
            setattr(self, "_" + name, int(value) if value is not None and value >= 0 else 0)
        rejected = state.get("rejected")
        if isinstance(rejected, dict):
            self._rejected = {str(k): int(quotes.num(v) or 0) for k, v in rejected.items()}

    def _problems(self, facts: dict[str, Any]) -> list[str]:
        out = []
        if not facts.get("stocks_available"):
            reason = facts.get("stocks_unavailable_reason")
            out.append("أسعار الشركات غير متاحة: %s" % report.REASON_AR.get(reason, reason))
        age = facts.get("stocks_written_age_min")
        if age is not None and age > WRITER_STALE_MIN:
            out.append("إكسبرت أسعار الشركات لم يكتب منذ %.0f د" % age)
        if not facts.get("earnings_available"):
            reason = facts.get("earnings_unavailable_reason")
            out.append("مواعيد الأرباح غير متاحة: %s" % report.REASON_AR.get(reason, reason))
        return out

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        counters = "نشرات=%d · أخطاء قراءة=%d · شموع الناسداك=%d · مرميّات=%s" % (
            self._published, self._read_errors, self._candles,
            " ".join("%s=%d" % kv for kv in sorted(self._rejected.items())) or "0")
        if self._last_error:
            counters += " (آخر تعثّر: %s)" % self._last_error
        details = {"published": self._published, "read_errors": self._read_errors, "candles": self._candles,
                   "rejected": dict(self._rejected), "paths": {n: self.path(n) for n in self._paths}}
        last = self._last_payload
        if last is None:
            return HealthStatus(state=HealthState.DEGRADED, details=details, message=(
                "لم تُقرأ المصادر بعد (القراءة الأولى بعد ~%d ث من الإقلاع) · %s" % (int(self._boot_delay_s), counters)))
        facts = last.get("facts") or {}
        known = "أسعار %s/%s رمزًا · %s رمزًا غائبًا عند الوسيط %s · أرباح %s/%d شركة بموعد · تاريخ الناسداك %d يومًا" % (
            facts.get("stocks_tickers_written"), facts.get("stocks_tickers_found"),
            len(facts.get("stocks_missing_at_broker") or []), facts.get("stocks_missing_at_broker") or "",
            facts.get("earnings_with_date_n"), len(self._tickers), facts.get("nasdaq_history_days_n") or 0)
        message = "%s · %s · %s" % (last.get("summary_ar"), known, counters)
        problems = self._problems(facts)
        if problems:
            return HealthStatus(state=HealthState.DEGRADED, details=details,
                                message=" · ".join(problems) + " — " + message)
        return HealthStatus(state=HealthState.HEALTHY, message=message, details=details)
