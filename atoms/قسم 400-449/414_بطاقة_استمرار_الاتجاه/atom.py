"""بطاقة استمرار الاتّجاه بعد الارتداد (414) — أوّل استراتيجيّة في طبقة تحديد الصفقة.

ورقة النقاش ٢٠٢٦-١٠-٠٧ (ختم المالك «NQ»):
  «الأقسام تعطي الاستراتيجيّات تحليلًا خامًا — ما في قسم إله وزن أو عمق أو ثقة، ولا قسم موصول
  بالقرار — وهون الاستراتيجيّات بتاخد القرار» · «كلّ استراتيجيّة عندها ما يلزمها لتحدّد وقفها وهدفها
  ونقطة دخولها… والصفقة تنحسب عليها وعلى كلّ عامل اشتغل معها».

تقرأ الحقائق الخام (لا تعيد قراءة السوق):
  151 analysis.trend.state      (1h · 4h)   الإغلاق ومتوسّط 20
  153 analysis.volatility.state (5m · 1d)   متوسّط المدى الحقيقيّ
  201 structure.levels.state                القمم والقيعان المؤكَّدة (5m · 1h · 4h)
  103 market_data.candle_closed (5m)        إغلاق شمعة الزناد
  412 strategy.session.state                نافذة المالك (ذروة لندن · افتتاح أمريكا)
  411 news.trading_window.state             نافذة المنع حول الخبر العالي
  151 analysis.trend.state للإس آند بي والداو (1h · 4h)  تأكيد الأسواق المرتبطة
والقرار نفسه في `shared/card_trend.py` — الدالّة نفسها التي قيست على سنتين.

تنشر:
  strategy.card.state      — كلّ بطاقة تُقيَّم (مفتوحة أو مؤرشفة بسببها) ومعها مصادر حقائقها
  strategy.setup.proposed  — إعداد البطاقة المفتوحة (للدفتر 465 ولـ555)
  decision.approved.state  — الموافقة بالجهة والوقف والهدف ⟵ 467 ⟵ 555 ⟵ حرّاس السلامة ⟵ التنفيذ
لا تُدير الصفقة: الإدارة أثلاث المالك (574) على الهدف المرسَل.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus
from shared import card_trend, owner_trades, strategy_switch
from shared.owner_windows import broker_day_offset_s
from shared.trade_setup import SETUP_TREND_PULLBACK, build_setup

ATOM_VERSION = "1.1.0"
ATOM_ID = "414"

EV_CANDLE = "market_data.candle_closed"
EV_TREND = "analysis.trend.state"
EV_VOL = "analysis.volatility.state"
EV_LADDER = "structure.levels.state"
EV_SESSION = "strategy.session.state"
EV_NEWS = "news.trading_window.state"
EV_ACCOUNT = "platform.account.state"
EV_POSITIONS = "platform.positions.state"

EV_CARD = "strategy.card.state"
EV_SETUP = "strategy.setup.proposed"
EV_APPROVED = "decision.approved.state"

TRIGGER_FRAME = "5m"
FRAME_SECONDS = {"5m": 300, "1h": 3600, "4h": 14400, "1d": 86400}
SETUP_TTL_S = 300.0               # الموافقة صالحةٌ لشمعة الزناد وحدها
SESSION_FRESH_S = 120.0           # حقيقة الوقت أقدم من دقيقتين ⟸ طبقة الوقت مجهولة
# ٢٠٢٦-١٠-٠٧ (تدقيق الإغلاق): باني الشموع 103 يُغلق الشمعة عند أوّل تِكّةٍ من الفترة التالية —
# فبعد انقطاعٍ تصل شمعةُ ما قبل القطع عند العودة، وإغلاقها قديم. شمعةٌ أُغلقت قبل أكثر من طول
# شمعة لا تكون زنادًا (سعرها ماضٍ)؛ وشمعةٌ ليست أحدث من آخر ما رأينا لا تُقرأ أصلًا.
CANDLE_LATE_S = 300.0
CANDLE_LATE = "CANDLE_LATE"
CANDLE_OLD = "CANDLE_OLD"
# ٢٠٢٦-١٠-٠٨ (ختم المالك «صلح NQ») — «الحيّ = المقيس» عند حدود الإطارات. القياس يقرأ عند إغلاق شمعة 5 د
# كلَّ ما أُغلق حتّى اللحظة **شاملًا**: شمعة الساعة والأربع ساعات التي تُغلق معها، ومدى شمعة الزناد نفسها.
# والحيّ كان يقيّم الشمعة لحظة وصولها، قبل أن تصل حقائق الإطارات التي أُغلقت في اللحظة نفسها (الناقل صناديق
# منفصلة، والمحلّلون في عمليّات أخرى). مقيس اليوم 12:00: انقلبت الأربع ساعات هابطةً عند الإغلاق نفسه، فالقياس
# يفتح بيعًا (30973.1 · وقف 31049.5 · هدف 30725 — بلغ الهدف الأوّل 13:30) والحيّ قرأ الأربع ساعات القديمة.
# الآن: تُحجز الشمعة حتّى تصل حقائق لحظتها (كلّ حقيقة تحمل بداية شمعتها)، وما لم يصل خلال المهلة ⟸
# «حقيقة متأخّرة» بلا صفقة (لا تُبنى صفقةٌ على حقيقةٍ غير المقيسة). والقرار نفسه في `card_trend` لم يُمسّ.
FACT_WAIT_S = 30.0
FACT_LATE = "FACT_LATE"

# ٢٠٢٦-١٠-٠٨ (أمر المالك «هل تقبل تخاطر بـ100$؟» — ورقة النقاش ٤-ل/٣أ والبند ٢٠): النسبة الأساسيّة
# الصادقة لبطاقةٍ كهذه في نافذتها — من إعادة البطاقة على السنتين بقلبها نفسه (241 صفقة، 2024-10 ⟶ 2026-10،
# الأثلاث، كلفة 1.5). **للعلم لا للمنع:** قيس ١٠-٠٨ أنّ لا خاصّة وقت القرار تميّز النجاح خارج العيّنة
# (انقلب الترتيب)، وقاعدة «لندن وحدها» رفضها معيار المالك. تخصّ عيار البطاقة الحاليّ وحده — أيّ تغييرٍ
# في `shared/card_trend.py` يستوجب إعادة القياس (`card_prob_features.py` ثمّ `card_prob_checks.py`).
BASE_RATES: dict[str, dict[str, Any]] = {
    "london_peak": {"n": 136, "stop_pct": 47.1, "t1_pct": 52.9, "t1_ci": [45, 61], "t2_pct": 32.4,
                    "final_pct": 18.4, "final_ci": [13, 26], "r_per_trade": 0.182, "label": "ذروة لندن"},
    "ny_open": {"n": 105, "stop_pct": 49.5, "t1_pct": 50.5, "t1_ci": [41, 60], "t2_pct": 25.7,
                "final_pct": 7.6, "final_ci": [4, 14], "r_per_trade": 0.006, "label": "افتتاح أمريكا"},
}


def base_rate_text(window: Any) -> str | None:
    rate = BASE_RATES.get(str(window or ""))
    if not rate:
        return None
    return ("بطاقاتٌ كهذه في %s على السنتين (%d): بلغ الهدف الأوّل %.0f٪، والثاني %.0f٪، والنهائيّ %.0f٪ · "
            "متوسّطها %+.2f وحدة خطر" % (rate["label"], rate["n"], rate["t1_pct"], rate["t2_pct"],
                                        rate["final_pct"], rate["r_per_trade"]))


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _frame_of(payload: dict[str, Any]) -> str:
    return str(payload.get("timeframe") or "").strip().lower()


def _meta(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("metadata")
    return meta if isinstance(meta, dict) else {}


def frame_boundary(at: float, seconds: float) -> float:
    """آخر حدٍّ للإطار عند `at` أو قبله — بمحاذاة باني الشموع 103 نفسها (الأربع ساعات واليوم على يوم الوسيط)."""
    if seconds > FRAME_SECONDS["1h"]:
        return at - ((at + broker_day_offset_s(at)) % seconds)
    return at - (at % seconds)


def _close_at(start: Any, frame: str) -> float | None:
    """إغلاق الشمعة التي حُسبت منها الحقيقة = بدايتها + طول إطارها؛ وبلا بداية ⟸ مجهول."""
    begin = _num(start)
    return None if begin is None or frame not in FRAME_SECONDS else begin + FRAME_SECONDS[frame]


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._symbols: set[str] = {"USTEC"}
        self._trend: dict[tuple[str, str], dict[str, Any]] = {}
        self._atr: dict[tuple[str, str], dict[str, Any]] = {}
        self._ladder: dict[str, dict[str, Any]] = {}
        self._ladder_at: dict[str, float] = {}
        self._session: dict[str, dict[str, Any]] = {}
        self._news: dict[str, list[tuple[float, float]]] = {}
        self._prev_close: dict[str, float] = {}
        self._last_start: dict[str, float] = {}
        self._clock = time.time          # ساعةٌ واحدة للذرّة كلّها (والاختبارات تقودها)
        self._account: dict[str, Any] = {}
        self._open_symbols: set[str] = set()
        self._positions_seen = False
        self._last_card: dict[str, dict[str, Any]] = {}
        self._tally: dict[str, int] = {}
        self._opened = 0
        self._candles = 0
        # ٢٠٢٦-١٠-٠٨: شمعة زنادٍ محجوزة حتّى تصل حقائق لحظتها (لكلّ رمز واحدة) · ومهلتها · وإغلاق آخر
        # شمعةٍ حدّثت السلّم في كلّ إطار · وعدد ما انتظر.
        self._pending: dict[str, dict[str, Any]] = {}
        self._timers: dict[str, asyncio.Task] = {}
        self._ladder_close: dict[tuple[str, str], float] = {}
        self._waited = 0

    # ── الإقلاع ──────────────────────────────────────────────────────────
    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        symbols = cfg.get("symbols")
        if isinstance(symbols, list) and symbols:
            self._symbols = {str(s).upper() for s in symbols}
        for event, handler in ((EV_CANDLE, self._on_candle), (EV_TREND, self._on_trend),
                               (EV_VOL, self._on_vol), (EV_LADDER, self._on_ladder),
                               (EV_SESSION, self._on_session), (EV_NEWS, self._on_news),
                               (EV_ACCOUNT, self._on_account), (EV_POSITIONS, self._on_positions)):
            context.subscribe(event, handler)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()

    async def shutdown(self) -> None:
        await self.stop()

    # ── الحقائق ──────────────────────────────────────────────────────────
    def _mine(self, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        symbol = str(payload.get("symbol") or "").upper()
        return symbol if symbol in self._symbols else None

    async def _on_trend(self, payload: dict[str, Any]) -> None:
        symbol = self._mine(payload)
        if not symbol and isinstance(payload, dict):
            peer = str(payload.get("symbol") or "").upper()
            symbol = peer if peer in card_trend.PEERS else None
        frame = _frame_of(payload) if symbol else ""
        if not symbol or frame not in ("1h", "4h"):
            return
        meta = _meta(payload)
        close, ema20 = _num(meta.get("close")), _num(meta.get("ema_slow_value"))
        if close is None or ema20 is None:
            return
        self._trend[(symbol, frame)] = {"close": close, "ema_slow_value": ema20,
                                        "at": self._clock(), "source": "151",
                                        "candles": meta.get("candles"),
                                        "close_at": _close_at(meta.get("period_start"), frame)}
        await self._flush()

    async def _on_vol(self, payload: dict[str, Any]) -> None:
        symbol = self._mine(payload)
        frame = _frame_of(payload) if symbol else ""
        if not symbol or frame not in ("5m", "1d"):
            return
        # ٢٠٢٦-١٠-٠٨: متوسّط المدى بنافذته الثابتة 14 (تعريف القياس) — لا `atr` الذي يمدّه مفتاح السرعة إلى 21.
        atr = _num(_meta(payload).get("atr_14"))
        if atr is None or atr <= 0:
            return
        self._atr[(symbol, frame)] = {"atr": atr, "at": self._clock(), "source": "153",
                                      "close_at": _close_at(_meta(payload).get("period_start"), frame)}
        await self._flush()

    async def _on_ladder(self, payload: dict[str, Any]) -> None:
        symbol = self._mine(payload)
        frames = payload.get("frames") if symbol else None
        if isinstance(frames, dict):
            self._ladder[symbol] = frames
            self._ladder_at[symbol] = self._clock()
            closed = payload.get("frame_closed")
            if isinstance(closed, dict):
                frame = str(closed.get("frame") or "").lower()
                end = _close_at(closed.get("period_start"), frame)
                if end is not None:
                    self._ladder_close[(symbol, frame)] = max(end, self._ladder_close.get((symbol, frame), end))
            await self._flush()

    async def _on_session(self, payload: dict[str, Any]) -> None:
        symbol = self._mine(payload)
        if symbol:
            self._session[symbol] = {"window": payload.get("owner_window"),
                                     "window_at": _num(payload.get("window_at")),
                                     "seen": self._clock(), "source": "412"}
            if self._pending:
                await self._flush()

    async def _on_news(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        start, end = _num(payload.get("window_start")), _num(payload.get("window_end"))
        if start is None or end is None:
            return
        symbol = str(payload.get("symbol") or "").upper()
        for sym in ([symbol] if symbol in self._symbols else sorted(self._symbols)):
            rows = [w for w in self._news.get(sym, []) if w[1] > self._clock() - 86400]
            if (start, end) not in rows:
                rows.append((start, end))
            self._news[sym] = rows[-50:]

    async def _on_account(self, payload: dict[str, Any]) -> None:
        if isinstance(payload, dict) and payload.get("account_id"):
            self._account = {"account_id": payload.get("account_id"),
                             "broker": payload.get("broker") or self._account.get("broker")}

    async def _on_positions(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        rows = payload.get("positions")
        if not isinstance(rows, list):
            return
        self._positions_seen = True
        # ٢٠٢٦-١٠-٢٦ (قانون صفقات المالك، ختم «NQ»): الرموز المفتوحة للمنظومة وحدها، بالتمييز الواحد — كما ٤١٥.
        self._open_symbols = {str(r.get("symbol") or "").upper() for r in owner_trades.system_rows(rows) if isinstance(r, dict)}

    # ── الزناد ──────────────────────────────────────────────────────────
    def _news_blocked(self, symbol: str, at: float) -> bool:
        return any(start <= at <= end for start, end in self._news.get(symbol, []))

    def _window(self, symbol: str, at: float) -> str | None:
        fact = self._session.get(symbol)
        if not fact or self._clock() - fact["seen"] > SESSION_FRESH_S:
            return None
        return fact["window"]

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        symbol = self._mine(payload)
        if payload.get("history") or not symbol or _frame_of(payload) != TRIGGER_FRAME:
            return
        close = _num(payload.get("close"))
        start = _num(payload.get("period_start"))
        if close is None or start is None:
            return
        self._candles += 1
        at = start + FRAME_SECONDS[TRIGGER_FRAME]
        last = self._last_start.get(symbol)
        if last is not None and start <= last:
            self._tally[CANDLE_OLD] = self._tally.get(CANDLE_OLD, 0) + 1
            return
        self._last_start[symbol] = start
        prev = self._prev_close.get(symbol)
        self._prev_close[symbol] = close
        lateness = self._clock() - at
        if lateness > CANDLE_LATE_S:
            card = {"status": CANDLE_LATE, "late_s": round(lateness, 1), "at": at,
                    "card_id": "%s:%s:%d" % (ATOM_ID, symbol, int(at)), "symbol": symbol,
                    "timeframe": TRIGGER_FRAME, "period_start": start}
            self._tally[CANDLE_LATE] = self._tally.get(CANDLE_LATE, 0) + 1
            self._last_card[symbol] = card
            await self._context.publish(EV_CARD, card)
            return
        if symbol in self._pending:                     # شمعةٌ سابقة ما زالت تنتظر ⟸ تُحسم الآن
            await self._expire(symbol, self._pending[symbol]["at"])
        held = {"at": at, "close": close, "prev": prev, "start": start}
        if self._stale(symbol, at):
            self._pending[symbol] = held
            self._waited += 1
            self._arm(symbol, at)
            return
        await self._evaluate(symbol, held)

    def _stale(self, symbol: str, at: float) -> list[str]:
        """حقائق لحظة الزناد التي لم تصل بعد. كلّ إطارٍ تُغلق شمعته عند `at` نفسها يجب أن تكون حقيقته من
        تلك الشمعة (القياس يقرأ ما أُغلق حتّى `at` شاملًا)، ومدى الخمس دقائق من شمعة الزناد نفسها."""
        window = self._session.get(symbol) or {}
        if (_num(window.get("window_at")) or 0.0) < at:
            return ["412"]
        if not window.get("window"):
            return []                                   # خارج النافذة: لا حاجة لغيرها
        def fresh(fact: dict[str, Any] | None) -> bool:
            return (_num((fact or {}).get("close_at")) or 0.0) >= at
        late = []
        for frame in ("1h", "4h"):
            if frame_boundary(at, FRAME_SECONDS[frame]) != at:
                continue
            late += ["151:%s:%s" % (name, frame) for name in (symbol, *card_trend.PEERS)
                     if not fresh(self._trend.get((name, frame)))]
            if self._ladder_close.get((symbol, frame), 0.0) < at:
                late.append("201:%s" % frame)
        for frame in ("5m", "1d"):
            if frame_boundary(at, FRAME_SECONDS[frame]) == at and not fresh(self._atr.get((symbol, frame))):
                late.append("153:%s" % frame)
        return late

    def _arm(self, symbol: str, at: float) -> None:
        # المحجوزة السابقة حُسمت قبل هذه (`_on_candle`) فلا مهلة قديمة؛ والإلغاء عند الوصول أو الإيقاف.
        self._timers[symbol] = asyncio.ensure_future(self._expire_later(symbol, at))

    async def _expire_later(self, symbol: str, at: float) -> None:
        await asyncio.sleep(FACT_WAIT_S)
        await self._expire(symbol, at)

    async def _flush(self) -> None:
        """حقيقةٌ وصلت ⟸ كلّ شمعةٍ محجوزة اكتملت حقائقُ لحظتها تُقيَّم الآن."""
        for symbol, held in list(self._pending.items()):
            if self._pending.get(symbol) is held and not self._stale(symbol, held["at"]):
                self._release(symbol)
                await self._evaluate(symbol, held)

    def _release(self, symbol: str) -> dict[str, Any] | None:
        timer = self._timers.pop(symbol, None)
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()
        return self._pending.pop(symbol, None)

    async def _expire(self, symbol: str, at: float) -> None:
        """انقضت المهلة (أو جاءت الشمعة التالية): ما اكتمل يُقيَّم، وما لم يكتمل «حقيقة متأخّرة» بلا صفقة."""
        held = self._pending.get(symbol)
        if not held or held["at"] != at:
            return
        late = self._stale(symbol, at)
        self._release(symbol)
        if not late:
            await self._evaluate(symbol, held)
            return
        card = {"status": FACT_LATE, "late": late, "at": at, "close": held["close"],
                "card_id": "%s:%s:%d" % (ATOM_ID, symbol, int(at)), "symbol": symbol,
                "timeframe": TRIGGER_FRAME, "period_start": held["start"], "facts": self._facts(symbol)}
        self._tally[FACT_LATE] = self._tally.get(FACT_LATE, 0) + 1
        self._last_card[symbol] = card
        if self._context is not None:
            await self._context.publish(EV_CARD, card)

    async def _evaluate(self, symbol: str, held: dict[str, Any]) -> None:
        if self._context is None:
            return
        at, close, prev, start = held["at"], held["close"], held["prev"], held["start"]
        card = card_trend.evaluate(
            at=at, close=close, prev_close=prev,
            trend_1h=self._trend.get((symbol, "1h")), trend_4h=self._trend.get((symbol, "4h")),
            atr_5m=(self._atr.get((symbol, "5m")) or {}).get("atr"),
            atr_1d=(self._atr.get((symbol, "1d")) or {}).get("atr"),
            ladder=self._ladder.get(symbol), window=self._window(symbol, at),
            news_blocked=self._news_blocked(symbol, at),
            peers={peer: (self._trend.get((peer, "1h")), self._trend.get((peer, "4h")))
                   for peer in card_trend.PEERS})
        if card["status"] == card_trend.OPEN and (symbol in self._open_symbols or not self._positions_seen):
            card["status"] = "POSITION_OPEN" if symbol in self._open_symbols else "POSITIONS_UNKNOWN"
        card_id = "%s:%s:%d" % (ATOM_ID, symbol, int(at))
        card.update({"card_id": card_id, "symbol": symbol, "timeframe": TRIGGER_FRAME,
                     "period_start": start, "facts": self._facts(symbol)})
        if card.get("status") == card_trend.OPEN and card.get("window") in BASE_RATES:
            card["base_rate"] = dict(BASE_RATES[card["window"]])
            card["base_rate_text"] = base_rate_text(card["window"])
        self._tally[card["status"]] = self._tally.get(card["status"], 0) + 1
        self._last_card[symbol] = card
        await self._context.publish(EV_CARD, card)
        if card["status"] == card_trend.OPEN:
            await self._open(card)

    def _facts(self, symbol: str) -> dict[str, Any]:
        """مصادر الحقائق التي بُنيت عليها البطاقة — للمحاسبة على كلّ ذرّة شاركت."""
        now = self._clock()
        def age(at):
            return None if at is None else round(now - at, 1)
        return {
            "151_trend_1h": {**(self._trend.get((symbol, "1h")) or {}), "age_s": age((self._trend.get((symbol, "1h")) or {}).get("at"))},
            "151_trend_4h": {**(self._trend.get((symbol, "4h")) or {}), "age_s": age((self._trend.get((symbol, "4h")) or {}).get("at"))},
            "153_atr_5m": {**(self._atr.get((symbol, "5m")) or {}), "age_s": age((self._atr.get((symbol, "5m")) or {}).get("at"))},
            "153_atr_1d": {**(self._atr.get((symbol, "1d")) or {}), "age_s": age((self._atr.get((symbol, "1d")) or {}).get("at"))},
            "201_ladder_age_s": age(self._ladder_at.get(symbol)),
            "412_window": self._session.get(symbol),
            "411_news_windows": len(self._news.get(symbol, [])),
            "151_peers": {peer: {frame: self._trend.get((peer, frame)) for frame in ("1h", "4h")}
                          for peer in card_trend.PEERS},
        }

    async def _open(self, card: dict[str, Any]) -> None:
        account = self._account.get("account_id")
        broker = self._account.get("broker")
        # 2026-10-17 (owner seal "NQ"): the card sends nothing unless shared/strategy_switch.json names it.
        why = None if strategy_switch.active(ATOM_ID) else "PAUSED_BY_OWNER"
        why = why or (None if account and broker else "ACCOUNT_UNKNOWN")
        if why:
            card["status"] = why
            self._tally[why] = self._tally.get(why, 0) + 1
            await self._context.publish(EV_CARD, card)
            return
        self._opened += 1
        side = card["side"]
        levels = {"invalidation_price": card["stop"], "target_price": card["target"],
                  "setup_id": card["card_id"],
                  "invalidation_source": "414:pullback_%s+noise_%.1fatr" % (
                      "low" if side == card_trend.BUY else "high", card_trend.N_NOISE)}
        identity = {"account_id": account, "broker": broker, "symbol": card["symbol"],
                    "timeframe": TRIGGER_FRAME, "period_start": card["period_start"],
                    "decision_id": card["card_id"]}
        # ٢٠٢٦-١٠-٠٧ (تدقيق الإغلاق): الإعداد يُبنى بدالّة العقد المشترك نفسها (`shared/trade_setup`) —
        # كان يُنشر بأسماء البطاقة (`entry_price` بلا `setup_owner` ولا سببٍ للوقف والهدف)، فيرميه دفتر
        # البطاقات 465 (يبحث عن `entry_reference`) ويكتب الباني «406/410»: صفقةٌ بلا مالكٍ ولا سبب، وهو
        # نقيض أمر المالك «تنحسب على الاستراتيجيّة وعلى كلّ عامل اشتغل معها».
        buy = side == card_trend.BUY
        setup = build_setup(
            owner=ATOM_ID, setup_type=SETUP_TREND_PULLBACK, side=side,
            entry_reference=card["entry"], invalidation_price=card["stop"],
            invalidation_source=levels["invalidation_source"],
            invalidation_reason="%s الارتداد على ٥ د (%.2f) وخلف ضعفَي متوسّط مدى ٥ د (%.2f)" % (
                "تحت قاع" if buy else "فوق قمّة", card["pullback"], card["atr_5m"]),
            target_price=card["target"], target_source="414:ladder_1h_4h",
            target_reason="أقرب مستوى ساعة/٤ ساعات بنسبة 1:%.1f، في متناول ١٫٥ من مدى اليوم" % card["rr"],
            account_id=account, broker=broker, symbol=card["symbol"], cycle_id=card["card_id"],
            period_start=card["period_start"], evidence={"facts": card.get("facts")},
            created_at=self._clock(), ttl_s=SETUP_TTL_S)
        await self._context.publish(EV_SETUP, {
            **setup, **identity, "setup_id": card["card_id"], "id": "trend_continuation_card",
            "strategy": ATOM_ID, "direction": side, "entry_price": card["entry"], "rr": card["rr"],
            "card": card})
        await self._context.publish(EV_APPROVED, {
            **identity, "id": "card_approval", "status": "ok", "approved": True,
            "decision_side": side, "signal": side, "cycle_id": card["card_id"],
            "strategy": ATOM_ID, "card": card, "warnings": [],
            "metadata": {"method": card_trend.STRATEGY_NAME, "timeframe": TRIGGER_FRAME,
                         "direction": side, "decision_side": side, "approved": True,
                         "reason": None, "request_id": card["card_id"]},
            **levels})

    # ── الحالة ──────────────────────────────────────────────────────────
    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION, "prev_close": dict(self._prev_close),
                "last_start": dict(self._last_start),
                # ٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق): حقائق الإطارات الكبيرة لا تُنشر إلّا عند إغلاق شمعتها (الأربع
                # ساعات كلّ أربع، والمدى اليوميّ مرّة) — فتُحفظ عبر الإقلاع، ولا يُستعاد إلّا الصالح منها.
                "trend": {"%s|%s" % key: dict(fact) for key, fact in self._trend.items()},
                "atr": {"%s|%s" % key: dict(fact) for key, fact in self._atr.items()},
                "tally": dict(self._tally), "opened": self._opened}

    async def restore(self, state: dict[str, Any]) -> None:
        if isinstance(state, dict):
            prev = state.get("prev_close")
            if isinstance(prev, dict):
                self._prev_close = {str(k): float(v) for k, v in prev.items() if _num(v) is not None}
            starts = state.get("last_start")
            if isinstance(starts, dict):
                self._last_start = {str(k): float(v) for k, v in starts.items() if _num(v) is not None}
            # الحقيقة صالحةٌ ما دامت شمعتها آخر مغلقٍ في إطارها: عمرها أقلّ من طول الإطار. وما زاد يُترك
            # فتقول البطاقة «حقيقة ناقصة» حتّى تُغلق شمعةٌ جديدة — لا تُبنى صفقةٌ على شمعةٍ مضت بعدها أخرى.
            for name, store in (("trend", self._trend), ("atr", self._atr)):
                rows = state.get(name)
                if not isinstance(rows, dict):
                    continue
                for key, fact in rows.items():
                    symbol, _, frame = str(key).partition("|")
                    at = _num((fact or {}).get("at")) if isinstance(fact, dict) else None
                    if frame in FRAME_SECONDS and at is not None and 0 <= self._clock() - at < FRAME_SECONDS[frame]:
                        store[(symbol, frame)] = dict(fact)
            tally = state.get("tally")
            if isinstance(tally, dict):
                self._tally = {str(k): int(v) for k, v in tally.items()}
            self._opened = int(state.get("opened") or 0)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        tally = " ".join("%s=%d" % kv for kv in sorted(self._tally.items()))
        # ٢٠٢٦-١٠-٠٧ (تدقيق الإغلاق): أيّ الحقائق حاضرة — ليلًا تقول كلّ بطاقة «خارج النافذة» قبل
        # أن تقرأ غيرها، فلا يُعرف منها أنّ الاتّجاه والمدى والسلّم يصلون. هنا يُقرأ ذلك من الصحّة.
        names = sorted(self._symbols) + list(card_trend.PEERS)
        trend = sum(1 for s in names for f in ("1h", "4h") if (s, f) in self._trend)
        vol = sum(1 for s in self._symbols for f in ("5m", "1d") if (s, f) in self._atr)
        facts = "حقائق: اتّجاه=%d/%d مدى=%d/%d سلّم=%d/%d وقت=%d/%d" % (
            trend, 2 * len(names), vol, 2 * len(self._symbols),
            sum(1 for s in self._symbols if s in self._ladder), len(self._symbols),
            sum(1 for s in self._symbols if s in self._session), len(self._symbols))
        return HealthStatus(
            state=HealthState.HEALTHY if self._candles else HealthState.DEGRADED,
            message="شموع_5د=%d · بطاقات_مفتوحة=%d · %s · %s · انتظرت_حقائق_لحظتها=%d" % (
                self._candles, self._opened, tally or "—", facts, self._waited),
            details={"candles": self._candles, "opened": self._opened, "tally": dict(self._tally),
                     "symbols": sorted(self._symbols), "facts": facts, "waited": self._waited})
