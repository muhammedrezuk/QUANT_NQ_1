"""معرفة الوقت والعطل (117) — ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا).

المالك: «قبل كلّ شي لازم يعرف النظام هاد الشي ثمّ الباقي» — الوقت والمواسم والعطل والجلسات.
حقائق خام تعرفها المنظومة وتُختم على كلّ صفقة، ولا تدخل قرار الدخول (عقد الحقائق ١٠-٠٧: لا جهة ولا وزن).

تنشر `knowledge.time.state` بعد ~30 ث من الإقلاع (كنسق 153) ومع كلّ `SYS_5MIN`:
  الجلسات بأسمائها وبالتوقيت الصيفيّ الصحيح · النقديّ ودقائقه · نافذة المالك · العطل والإغلاق المبكّر ·
  انتهاء الخيارات · آخر/أوّل يوم تداول في الشهر والربع والسنة · يوم الوسيط.
الساعة: ساعة الجهاز الحقيقيّة (`time.time`)، والاختبارات تقودها. والتقويم يُقرأ للقراءة فقط في خيطٍ منفصل.

٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الوقت من مصدرٍ واحد): «نعتمد ذرّة الوقت» — فساعتها (الجلسات · الصيفيّ · أيّام التداول ·
يوم الوسيط) صارت `shared/market_clock`، تقرؤها هذه الذرّة و158 و159 فلا يُحسب الوقت في مكانين. الحقائق هنا لم تتغيّر
(مقيسة حرفًا بحرف على 15031 لحظة قبل النقل وبعده)؛ وبقي في الشقيق تقويم ميتاتريدر وعطله وانتهاء الخيارات.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import date
from typing import Any

import time_holidays_clock as clock
from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared import market_clock as mc
from shared.owner_windows import owner_window

ATOM_VERSION = "1.0.0"
PAYLOAD_ID = "time_and_holidays_knowledge"
SOURCE_NAME = "system_clock+owner_windows+mt5_calendar+nyse_rules"

EV_PULSE = "SYS_5MIN"
EV_STATE = "knowledge.time.state"

DEFAULT_DB = r"%APPDATA%\MetaQuotes\Terminal\Common\Files\nq_calendar_history.db"
DB_ENV = "NQ_CALENDAR_HISTORY_DB"          # يسبق `config` (للاختبار أو مسارٍ آخر) — كما 118
DEFAULT_SYMBOL = "USTEC"
BOOT_DELAY_S = 30.0                        # بعد اكتمال الإقلاع كلّه (مقيس ~7 ث) — كما 153
# ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): وقت التقويم = غرينتش + 3 ساعات ثابتة — مقيس على قرار الفائدة
# (14:00 نيويورك = 21:00 صيفًا و22:00 شتاءً) والوظائف (08:30 = 15:30)، وتشهد به `export_meta` (10800).
DEFAULT_SERVER_OFFSET_S = 10800
CALENDAR_RELOAD_S = 3600.0                 # التقويم يُكتب مرّةً عند تشغيل سكربته؛ يُعاد فحصه كلّ ساعة
UPCOMING_N = 5
FEW_DAYS_MIN = 3
BAD_PULSE = "bad_pulse"
TASK_ERROR = "task_error"

SESSION_AR = {mc.SESSION_OVERLAP: "لندن ونيويورك مفتوحتان (تداخل)",
              mc.SESSION_NY_CASH: "نيويورك النقديّة مفتوحة", mc.SESSION_LONDON: "لندن مفتوحة",
              mc.SESSION_ASIA: "آسيا (طوكيو) مفتوحة",
              mc.SESSION_GLOBEX: "عقد الناسداك الإلكترونيّ وحده مفتوح",
              mc.SESSION_CLOSED: "الأسواق مغلقة"}
REASON_AR = {clock.REASON_MISSING: "ملفّ التقويم مفقود", clock.REASON_READ: "تعذّرت قراءة التقويم"}


def resolve_db_path(configured: str | None) -> str:
    return os.environ.get(DB_ENV) or os.path.expandvars(configured or DEFAULT_DB)


def _duration_ar(minutes: int | None) -> str:
    if minutes is None:
        return "؟"
    hours, mins = divmod(int(minutes), 60)
    if hours >= 24:
        return "%dي %dس" % divmod(hours, 24)
    return "%dس%02dد" % (hours, mins)


def _days_ar(days: int) -> str:
    if days <= 0:
        return "اليوم"
    if days == 1:
        return "غدًا"
    if days == 2:
        return "بعد يومين"
    return ("بعد %d أيّام" if FEW_DAYS_MIN <= days <= 10 else "بعد %d يومًا") % days


def build_facts(now: float, cal: dict[str, Any]) -> dict[str, Any]:
    """الحقائق الخام عند لحظة `now` — أوّلًا عشرٌ مفردة (يختمها دفتر البطاقات 465 بأسمائها) ثمّ الباقي."""
    ny = mc.local_time(now, mc.CITY_NEW_YORK)
    today = ny.date()
    years = (today.year, today.year + 1)
    market, bank, london_off, tokyo_off = clock.holiday_tables(cal, years)
    known = bool((cal.get("rows") or {}).get("US"))
    # ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): بلا تقويمٍ تُعلَن العطل «غير متاحة»، لكنّ ساعة التداول لا تكذب:
    # أيّام التداول (النقديّ · الخيارات · نهاية الشهر) تُحسب حينها بقواعد البورصة وحدها، ويُعلَن مصدرها.
    trading = market if known else mc.rule_holidays(years)
    clock_now = mc.market_sessions(now, trading, london_off, tokyo_off)
    early = mc.is_early_close(today)
    day = mc.market_day(today, trading)
    monthly_opex = today == clock.opex_date(today.year, today.month, trading)
    next_opex = clock.next_opex(today, trading)
    upcoming = sorted(d for d in market if d > today) if known else []
    nxt = upcoming[0] if upcoming else None
    today_holiday = market.get(today) if known else None
    month_end = day.is_month_end
    broker = mc.broker_day(now)
    london_now, tokyo_now = mc.local_time(now, mc.CITY_LONDON), mc.local_time(now, mc.CITY_TOKYO)
    return {
        "session_now": clock_now.session_now,
        "owner_window": owner_window(now),
        "cash_open": clock_now.cash_open,
        "minutes_to_cash_close": clock_now.minutes_to_cash_close,
        "minutes_to_cash_open": clock_now.minutes_to_cash_open,
        "is_holiday_today": (today_holiday is not None) if known else None,
        "is_pre_holiday": (day.is_trading_day and mc.next_weekday(today) in market) if known else None,
        "is_early_close_today": early,
        "is_monthly_opex": monthly_opex,
        "is_month_end": month_end,
        # ── وما بعد العشر ──
        "day_of_week": mc.WEEKDAY_NAMES[today.weekday()],
        "days_to_next_holiday": (nxt - today).days if nxt else None,
        "next_holiday_name": market[nxt][0] if nxt else None,
        "next_holiday_date": nxt.isoformat() if nxt else None,
        "next_holiday_source": market[nxt][1] if nxt else None,
        "holiday_name": today_holiday[0] if today_holiday else None,
        "holiday_source": today_holiday[1] if today_holiday else None,
        "is_bank_holiday_today": (today in bank) if known else None,
        "bank_holiday_name": bank.get(today),
        "early_close_time_utc": mc.hhmm(mc.local_to_utc(today, mc.EARLY_CLOSE_MIN, mc.CITY_NEW_YORK))
        if early else None,
        "is_quarterly_opex": monthly_opex and today.month in mc.QUARTER_MONTHS,
        "days_to_next_opex": (next_opex - today).days if next_opex else None,
        "next_opex_date": next_opex.isoformat() if next_opex else None,
        "is_quarter_end": month_end and today.month in mc.QUARTER_MONTHS,
        "is_year_end": month_end and today.month == mc.DECEMBER,
        "is_month_start": day.is_month_start,
        "is_trading_day": day.is_trading_day,
        "week_of_month": (today.day - 1) // mc.WEEK_DAYS + 1,
        "trading_day_of_month": day.trading_day_of_month,
        "trading_days_in_month": day.trading_days_in_month,
        **mc.clock_offsets(now),
        "new_york_time": ny.strftime("%H:%M"),
        "new_york_date": today.isoformat(),
        "london_time": london_now.strftime("%H:%M"),
        "tokyo_time": tokyo_now.strftime("%H:%M"),
        "london_holiday_name": london_off.get(london_now.date()),
        "tokyo_holiday_name": tokyo_off.get(tokyo_now.date()),
        "broker_day_date": broker.day.isoformat(),
        "broker_day_start_utc": broker.start_utc,
        "broker_day_offset_h": broker.offset_h,
        "holidays_status": cal.get("status") or clock.STATUS_UNAVAILABLE,
        "trading_calendar_source": clock.SOURCE_BOTH if known else mc.SOURCE_RULES,
        # ── القوائم والقواميس ──
        "sessions_open": clock_now.sessions_open,
        "upcoming_market_holidays": [{"date": d.isoformat(), "name": market[d][0], "source": market[d][1]}
                                     for d in upcoming[:UPCOMING_N]],
        "calendar": _calendar_facts(cal, today),
    }


def _calendar_facts(cal: dict[str, Any], today: date) -> dict[str, Any]:
    rows = cal.get("rows") or {}
    return {"status": cal.get("status") or clock.STATUS_UNAVAILABLE, "reason": cal.get("reason"),
            "horizon_date": cal.get("horizon"),
            "us_holiday_rows_n": len(rows.get("US") or []), "gb_holiday_rows_n": len(rows.get("GB") or []),
            "jp_holiday_rows_n": len(rows.get("JP") or []), "rows_total_n": cal.get("rows_total_n"),
            "loaded_at": cal.get("loaded_at"), "server_offset_s": cal.get("server_offset_s"),
            "export_offset_s": cal.get("export_offset_s"), "exported_at": cal.get("exported_at"),
            "path": cal.get("path")}


def summary_ar(facts: dict[str, Any]) -> str:
    parts = ["الآن: " + SESSION_AR.get(facts["session_now"], facts["session_now"])]
    if facts["cash_open"]:
        parts.append("النقديّ يغلق بعد " + _duration_ar(facts["minutes_to_cash_close"]))
    else:
        parts.append("النقديّ يفتح بعد " + _duration_ar(facts["minutes_to_cash_open"]))
    if facts["is_early_close_today"]:
        parts.append("إغلاق مبكّر اليوم 13:00 نيويورك (%s غرينتش)" % facts["early_close_time_utc"])
    if facts["is_holiday_today"] is None:
        reason = str((facts["calendar"] or {}).get("reason") or "").split(":")[0]
        parts.append("العطل غير متاحة (%s)" % REASON_AR.get(reason, "التقويم لم يُقرأ بعد"))
    elif facts["is_holiday_today"]:
        parts.append("اليوم عطلة: " + str(facts["holiday_name"]))
    if facts["is_pre_holiday"]:
        parts.append("آخر يوم تداول قبل العطلة")
    if facts["days_to_next_holiday"] is not None:
        parts.append("العطلة القادمة %s %s" % (facts["next_holiday_name"], _days_ar(facts["days_to_next_holiday"])))
    if facts["is_bank_holiday_today"]:
        parts.append("عطلة مصارف (%s) والبورصة تعمل" % facts["bank_holiday_name"])
    kind = "الفصليّ" if facts["is_quarterly_opex"] else "الشهريّ"
    if facts["is_monthly_opex"]:
        parts.append("اليوم انتهاء الخيارات " + kind)
    elif facts["days_to_next_opex"] is not None:
        parts.append("انتهاء الخيارات الشهريّ " + _days_ar(facts["days_to_next_opex"]))
    for key, text in (("is_year_end", "آخر يوم تداول في السنة"), ("is_quarter_end", "آخر يوم تداول في الربع"),
                      ("is_month_end", "آخر يوم تداول في الشهر"), ("is_month_start", "أوّل يوم تداول في الشهر")):
        if facts[key]:
            parts.append(text)
            break
    return " · ".join(parts)


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._clock = time.time                  # ساعة الجهاز الحقيقيّة (والاختبارات تقودها)
        self._db_config = DEFAULT_DB
        self._server_offset_s = DEFAULT_SERVER_OFFSET_S
        self._boot_delay_s = BOOT_DELAY_S
        self._symbol = DEFAULT_SYMBOL
        self._cal: dict[str, Any] = {}
        self._tasks: dict[str, asyncio.Future] = {}
        self._loading = False
        self._published = 0
        self._read_errors = 0
        self._rejected: dict[str, int] = {}
        self._last: dict[str, Any] | None = None

    # ── الإقلاع ──────────────────────────────────────────────────────────
    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._db_config = str(cfg.get("db_path") or DEFAULT_DB)
        self._server_offset_s = int(cfg.get("server_offset_s", DEFAULT_SERVER_OFFSET_S))
        self._boot_delay_s = float(cfg.get("boot_delay_s", BOOT_DELAY_S))
        self._symbol = str(cfg.get("symbol") or DEFAULT_SYMBOL).upper()
        context.subscribe(EV_PULSE, self._on_pulse)

    async def start(self) -> None:
        self._running = True
        task = asyncio.ensure_future(self._boot())
        self._tasks["boot"] = task
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Future) -> None:
        if not task.cancelled() and task.exception() is not None:
            self._rejected[TASK_ERROR] = self._rejected.get(TASK_ERROR, 0) + 1

    async def stop(self) -> None:
        self._running = False
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    async def shutdown(self) -> None:
        await self.stop()

    async def _boot(self) -> None:
        # الإقلاع يبدأ الذرّات واحدةً بعد واحدة بترتيب أرقامها — فالنشر فورًا يسبق اشتراك من يسمع (كنسق 153).
        await self._reload()
        await asyncio.sleep(self._boot_delay_s)
        if self._running:
            await self._publish()

    # ── التقويم ──────────────────────────────────────────────────────────
    async def _reload(self) -> None:
        if self._loading:
            return
        self._loading = True
        try:
            result = await asyncio.to_thread(clock.load_calendar, resolve_db_path(self._db_config),
                                             self._server_offset_s, self._clock())
        finally:
            self._loading = False
        if result.get("status") == clock.STATUS_OK:
            self._cal = result
            return
        self._read_errors += 1
        if (self._cal.get("rows") or {}).get("US"):
            # آخر ما عُرف يبقى، ويُعلَن قديمًا بسببه — لا يُمحى عن الشاشة ولا يُدّعى حيًّا.
            self._cal = {**self._cal, "status": "stale", "reason": result.get("reason")}
        else:
            self._cal = result

    def _reload_due(self, now: float) -> bool:
        if self._cal.get("status") != clock.STATUS_OK:
            return True
        return now - float(self._cal.get("loaded_at") or 0.0) >= CALENDAR_RELOAD_S

    # ── النبض والنشر ─────────────────────────────────────────────────────
    async def _on_pulse(self, payload: Any) -> None:
        if not self._running or self._context is None:
            return
        if not isinstance(payload, dict):
            self._rejected[BAD_PULSE] = self._rejected.get(BAD_PULSE, 0) + 1
            return
        if self._reload_due(self._clock()):
            await self._reload()
        await self._publish()

    async def _publish(self) -> None:
        if self._context is None:
            return
        now = self._clock()
        facts = build_facts(now, self._cal)
        body = {"id": PAYLOAD_ID, "symbol": self._symbol, "status": "ok", "facts": facts,
                "computed_at": now, "summary_ar": summary_ar(facts), "source": SOURCE_NAME}
        self._last = body
        self._published += 1
        await self._context.publish(EV_STATE, body)

    # ── الحالة ───────────────────────────────────────────────────────────
    async def snapshot(self) -> dict[str, Any]:
        cal = dict(self._cal) if (self._cal.get("rows") or {}).get("US") else {}
        return {"version": ATOM_VERSION, "calendar": cal, "published": self._published,
                "read_errors": self._read_errors, "rejected": dict(self._rejected)}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        cal = state.get("calendar")
        if isinstance(cal, dict) and isinstance(cal.get("rows"), dict) and not self._cal:
            # جدول العطل المحفوظ يُستعمل حتّى تُقرأ القاعدة؛ وإن تعذّرت بقي «قديمًا» بسببه.
            self._cal = {**cal, "status": "restored"}
        self._published = int(state.get("published") or 0)
        self._read_errors = int(state.get("read_errors") or 0)
        rejected = state.get("rejected")
        if isinstance(rejected, dict):
            self._rejected = {str(k): int(v) for k, v in rejected.items()}

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        cal = self._cal
        rows = cal.get("rows") or {}
        if rows.get("US"):
            known = "عطل التقويم: %d صفًّا أمريكيًّا (%d بريطانيًّا، %d يابانيًّا) وأفقه %s · الحال %s" % (
                len(rows.get("US") or []), len(rows.get("GB") or []), len(rows.get("JP") or []),
                cal.get("horizon") or "؟", {"ok": "حيّ", "stale": "قديم", "restored": "مستعاد"}.get(
                    str(cal.get("status")), "؟"))
        else:
            reason = str(cal.get("reason") or "").split(":")[0]
            known = "العطل غير متاحة: %s" % REASON_AR.get(reason, "التقويم لم يُقرأ بعد")
        rejected = sum(self._rejected.values())
        counters = "نُشر %d مرّة · أخطاء قراءة التقويم %d · مدخلات مرفوضة %d" % (
            self._published, self._read_errors, rejected)
        now_text = self._last["summary_ar"] if self._last else "لم يُنشر بعد (النشر الأوّل بعد ~%d ث من الإقلاع)" % (
            int(self._boot_delay_s))
        state = HealthState.HEALTHY if self._last and cal.get("status") == clock.STATUS_OK else HealthState.DEGRADED
        return HealthStatus(state=state, message="%s · %s · %s" % (now_text, known, counters),
                            details={"published": self._published, "read_errors": self._read_errors,
                                     "rejected": dict(self._rejected), "calendar_status": cal.get("status"),
                                     "horizon": cal.get("horizon")})
