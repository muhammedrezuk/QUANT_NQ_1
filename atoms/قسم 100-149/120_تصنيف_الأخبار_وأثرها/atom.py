"""تصنيف الأخبار وأثرها (120) — تنشر `knowledge.news.state`.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): «قبل كلّ شي لازم يعرف النظام هاد الشي ثمّ الباقي» — الأخبار والحروب
والتصريحات. الذرّة تعرف **حقائق خامًا** عن الأخبار وتُختم على كلّ صفقة، **ولا تدخل قرار الدخول** (عقد الحقائق ١٠-٠٧).

من أين تصل الأخبار (مقروء من الكود ٢٠٢٦-١٠-٠٨):
  بوت الأخبار المستقلّ ⟶ قاعدة الجسر `nq_brain.db` (جدول news) ⟶ 616 يقرؤها كلّ 30 ث وينشر `market.news`
  ⟶ 108 يفضّ التكرار ويوحّد الشكل وينشر `market_data.news_received` (العنوان · المصدر · `published_at`) ⟶ هنا
  (و411 بجانبها). قاعدة الجسر لا تُقرأ هنا: الحدث يحمل العنوان والوقت والمصدر.
  والسعر من 103 `market_data.candle_closed`: شموع الدقيقة للناسداك (`USTEC`).

ما تعرفه:
  ١) أصناف كلّ عنوان بقوائم كلماتٍ مسمّاة ثابتة (`news_category_rules`): نقديّ · جيوسياسيّ · تجارة · شركات · بيانات ·
     أخرى — وقد يقع العنوان في أكثر من صنف.
  ٢) سعر الإغلاق عند الخبر (آخر شمعة دقيقةٍ أُغلقت عند `published_at` أو قبله) ثمّ الحركة ٪ بعد 5 و15 و60 دقيقة،
     تُملأ حين تُغلق الشمعة المعنيّة لا قبلها. والخبر يصل الجسر متأخّرًا أحيانًا (مقيس ١٠-٠٨ على آخر 40 خبرًا:
     `written_at − published_at` من 154 ث إلى 22630 ث) فيُقاس من مخزون شموع الدقيقة الماضية — كلّها أُغلقت قبل
     وصوله، فلا نظر إلى المستقبل. وفجوة أكثر من دقيقتين (سوقٌ مغلق · انقطاع · عطلة) ⟸ «لا سعر» لا رقمٌ مخترع.
  ٣) آخر 3 أخبار لكلّ صنف (الوقت · العنوان · المصدر · الحركة بعده حتّى الآن) · عدد كلّ صنف في آخر 24 ساعة ·
     الدقائق منذ آخر خبرٍ جيوسياسيّ · متوسّط |الحركة بعد 15 د| لكلّ صنف على ما تراكم ومعه n.

⛔ حدٌّ معلَن: **تصنيفٌ بالكلمات وقياسُ أثر، لا فهمٌ للمضمون.** الصنف يقول «في العنوان كلمةٌ من القائمة»، لا ما حدث
   ولا في أيّ اتّجاه؛ والحركة بعد الخبر حركةُ السوق في تلك الدقائق بكلّ أسبابها لا أثرُ الخبر وحده.
"""
from __future__ import annotations

import math
import time
from collections import deque
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

import news_category_rules as rules

ATOM_VERSION = "1.0.0"
KNOWLEDGE_ID = "news_category_knowledge"
SOURCE = "108 market_data.news_received + 103 market_data.candle_closed"

EV_NEWS = "market_data.news_received"
EV_CANDLE = "market_data.candle_closed"
EV_PULSE = "SYS_5MIN"
EV_OUT = "knowledge.news.state"

#: آفاق الحركة بعد الخبر بالدقائق — من نصّ المالك.
HORIZONS_MIN = (5, 15, 60)
#: الأفق الذي يُجمع متوسّط قيمته المطلقة لكلّ صنف.
MEAN_HORIZON_MIN = 15
#: أبعد ما يُقبل بين اللحظة المطلوبة وآخر إغلاقٍ قبلها: شمعتا دقيقة. أبعد ⟸ فجوة فلا سعر.
PRICE_GAP_TOLERANCE_S = 120.0
#: طول العنوان في سطر الملخّص.
SUMMARY_HEADLINE_CHARS = 60
#: من هذا العدد من الدقائق تُكتب المدّة في الملخّص ساعاتٍ.
SUMMARY_HOURS_FROM_MIN = 120
#: مفاتيح فضّ التكرار المحفوظة — أكثر من الأخبار المحفوظة: بداية 616 الدافئة تعيد آخر خمسة بعد كلّ إقلاع، و108
#: لا يذكر ما قبل إقلاعه، فبلا هذا يُعدّ الخبر نفسه مرّتين.
SEEN_KEYS_KEEP = 1000
FRAME_SECONDS = {"1m": 60.0, "5m": 300.0}
METHOD = "keyword_match"
LIMIT_AR = "تصنيفٌ بالكلمات لا فهمٌ للمضمون"

STATUS_OK = "ok"
STATUS_NO_NEWS = "no_news_yet"

NO_HEADLINE = "no_headline"
NO_TIME = "no_published_at"
BAD_CANDLE = "bad_candle"
BAD_RESTORED_ROW = "bad_restored_row"


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _key(headline: str) -> str:
    """مفتاح فضّ التكرار: العنوان بحروفٍ صغيرة ومسافاتٍ موحّدة — كما يفعل 411."""
    return " ".join(headline.lower().split())


def _signed(value: float) -> str:
    return ("%+.2f" % value).replace("-", "−")


def _move_name(minutes: int) -> str:
    return "%dm" % minutes


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._symbol = "USTEC"
        self._frame = "1m"
        self._frame_s = 60.0
        self._keep = 200
        self._recent = 3
        self._buffer = 1500
        self._clock = time.time          # ساعةٌ واحدة للذرّة كلّها (والاختبارات تقودها)
        self._rows: deque = deque(maxlen=self._keep)
        self._seen: deque = deque(maxlen=SEEN_KEYS_KEEP)
        # شموع الدقيقة المغلقة: (وقت الإغلاق، الإغلاق) مرتّبة — مخزون يومٍ وزيادة للخبر المتأخّر.
        self._closes: list[tuple[float, float]] = []
        # لكلّ صنف: [مجموع |الحركة بعد 15 د|، عددها] — تراكميّ ويبقى بعد الإقلاع.
        self._abs_mean: dict[str, list[float]] = {}
        self._received = 0
        self._accepted = 0
        self._duplicates = 0
        self._candles = 0
        self._old_candles = 0
        self._pulses = 0
        self._published = 0
        self._restored = 0
        self._rejected: dict[str, int] = {}

    # ── دورة الحياة ─────────────────────────────────────────────────────
    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        cfg = context.config or {}
        self._symbol = str(cfg.get("symbol") or self._symbol).upper()
        frame = str(cfg.get("price_timeframe") or self._frame).lower()
        if frame in FRAME_SECONDS:
            self._frame, self._frame_s = frame, FRAME_SECONDS[frame]
        self._keep = max(1, int(cfg.get("keep_news", self._keep)))
        self._recent = max(1, int(cfg.get("recent_per_category", self._recent)))
        self._buffer = max(1, int(cfg.get("price_buffer_candles", self._buffer)))
        self._rows = deque(self._rows, maxlen=self._keep)
        context.subscribe(EV_NEWS, self._on_news)
        context.subscribe(EV_CANDLE, self._on_candle)
        context.subscribe(EV_PULSE, self._on_pulse)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    def _reject(self, reason: str) -> None:
        self._rejected[reason] = self._rejected.get(reason, 0) + 1

    # ── المدخلات ────────────────────────────────────────────────────────
    async def _on_news(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        self._received += 1
        headline = str(payload.get("headline") or "").strip()
        if not headline:
            self._reject(NO_HEADLINE)
            return
        # وقت الخبر = `published_at` (ثوانٍ UTC من الجسر)؛ وبلاه لا وقت — لا يُختلق من ساعة الوصول (درس 411 و616:
        # خبرٌ عمره أسابيع دخل الدفتر مختومًا «الآن»).
        published = _num(payload.get("published_at"))
        if published is None:
            published = _num(payload.get("timestamp"))
        if published is None or published <= 0:
            self._reject(NO_TIME)
            return
        key = _key(headline)
        if key in self._seen:
            self._duplicates += 1
            return
        self._seen.append(key)
        row = {"key": key, "time": published, "headline": headline, "source": payload.get("source"),
               "categories": rules.classify(headline), "price_at_news": None, "base_done": False,
               "moves": {}, "no_price": []}
        self._rows.append(row)
        self._accepted += 1
        self._resolve(row)
        await self._publish()

    async def _on_candle(self, payload: dict[str, Any]) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        if (str(payload.get("symbol") or "").upper() != self._symbol
                or str(payload.get("timeframe") or "").lower() != self._frame):
            return
        start, close = _num(payload.get("period_start")), _num(payload.get("close"))
        if start is None or close is None or close <= 0:
            self._reject(BAD_CANDLE)
            return
        close_at = start + self._frame_s
        # 103 ينشر الشمعة لكلّ حسابٍ ووسيط: الرمز نفسه يصل أكثر من مرّة. الأوّل يُؤخذ، والمكرّر والمتأخّر يُعدّان.
        if self._closes and close_at <= self._closes[-1][0]:
            self._old_candles += 1
            return
        self._closes.append((close_at, close))
        if len(self._closes) > self._buffer:
            del self._closes[:len(self._closes) - self._buffer]
        self._candles += 1
        for row in self._rows:
            if self._pending(row):
                self._resolve(row)

    async def _on_pulse(self, payload: dict[str, Any]) -> None:
        if not self._running or self._context is None:
            return
        self._pulses += 1
        await self._publish()

    # ── السعر بعد الخبر ─────────────────────────────────────────────────
    def _pending(self, row: dict[str, Any]) -> bool:
        return not row["base_done"] or len(row["moves"]) + len(row["no_price"]) < len(HORIZONS_MIN)

    def _resolve(self, row: dict[str, Any]) -> None:
        """يملأ ما أُغلقت شمعته من سعر الخبر وآفاقه — بالترتيب، ويقف عند أوّل أفقٍ لم تُغلق شمعته بعد."""
        if not row["base_done"]:
            done, price = rules.price_at(self._closes, row["time"], PRICE_GAP_TOLERANCE_S)
            if not done:
                return
            row["base_done"], row["price_at_news"] = True, price
        for minutes in HORIZONS_MIN:
            name = _move_name(minutes)
            if name in row["moves"] or name in row["no_price"]:
                continue
            if row["price_at_news"] is None:
                row["no_price"].append(name)
                continue
            done, price = rules.price_at(self._closes, row["time"] + minutes * 60, PRICE_GAP_TOLERANCE_S)
            if not done:
                return
            if price is None:
                row["no_price"].append(name)
                continue
            move = rules.move_pct(row["price_at_news"], price)
            row["moves"][name] = move
            if minutes == MEAN_HORIZON_MIN:
                for category in row["categories"]:
                    total = self._abs_mean.setdefault(category, [0.0, 0])
                    total[0], total[1] = total[0] + abs(move), total[1] + 1

    def _since(self, row: dict[str, Any] | None) -> tuple[float | None, float | None]:
        """الحركة من سعر الخبر إلى آخر إغلاقٍ معروف، ودقائقها — «حتّى الآن»."""
        if not row or row["price_at_news"] is None or not self._closes:
            return None, None
        last_at, last_price = self._closes[-1]
        if last_at < row["time"]:
            return None, None
        return rules.move_pct(row["price_at_news"], last_price), round((last_at - row["time"]) / 60, 1)

    # ── الحمولة ─────────────────────────────────────────────────────────
    @staticmethod
    def _minutes(now: float, at: float) -> int:
        return int(round((now - at) / 60))

    def _view(self, row: dict[str, Any], now: float) -> dict[str, Any]:
        since, since_minutes = self._since(row)
        view = {"time": row["time"], "minutes_ago": self._minutes(now, row["time"]),
                "headline": row["headline"], "source": row["source"],
                "categories": list(row["categories"]), "price_at_news": row["price_at_news"]}
        for minutes in HORIZONS_MIN:
            view["move_%s_pct" % _move_name(minutes)] = row["moves"].get(_move_name(minutes))
        view.update({"no_price": list(row["no_price"]), "move_since_pct": since,
                     "since_minutes": since_minutes})
        return view

    def _payload(self) -> dict[str, Any]:
        now = self._clock()
        rows = sorted(self._rows, key=lambda r: r["time"], reverse=True)
        day = [r for r in rows if now - r["time"] <= 86400]
        counts = {name: sum(1 for r in day if name in r["categories"]) for name in rules.CATEGORIES}
        geo = next((r for r in rows if rules.GEOPOLITICS in r["categories"]), None)
        # ٢٠٢٦-١٠-٠٨ (الوكيل الرئيس — دفتر البطاقات 465 يختم أوّل 10 حقائق مفردة بأسمائها): المفردات أوّلًا.
        facts: dict[str, Any] = {"news_24h": len(day)}
        facts.update({"%s_24h" % name: counts[name] for name in rules.CATEGORIES})
        facts.update({
            "last_geopolitics_minutes_ago": self._minutes(now, geo["time"]) if geo else None,
            "last_news_minutes_ago": self._minutes(now, rows[0]["time"]) if rows else None,
            "last_geopolitics_move_since_pct": self._since(geo)[0],
            "latest_by_category": {name: [self._view(r, now) for r in rows if name in r["categories"]][:self._recent]
                                   for name in rules.CATEGORIES},
            "abs_move_%s_mean_pct" % _move_name(MEAN_HORIZON_MIN): {
                name: {"mean": round(total[0] / total[1], 4) if total[1] else None, "n": int(total[1])}
                for name, total in ((n, self._abs_mean.get(n, [0.0, 0])) for n in rules.CATEGORIES)},
            # العدّ من المحفوظ (آخر `keep_news`): إن امتلأ المخزون وأقدمه داخل اليوم فالعدّ حدٌّ أدنى — يُعلَن.
            "counts_24h_complete": len(rows) < self._keep or (bool(rows) and now - rows[-1]["time"] > 86400),
            "stored_news": len(rows),
            "pending_moves": sum(1 for r in rows if self._pending(r)),
            "price_symbol": self._symbol,
            "price_timeframe": self._frame,
            "price_candles": len(self._closes),
            "last_price_close_at": self._closes[-1][0] if self._closes else None,
            "method": METHOD,
            "limit_ar": LIMIT_AR,
        })
        return {"id": KNOWLEDGE_ID, "status": STATUS_OK if rows else STATUS_NO_NEWS, "symbol": self._symbol,
                "facts": facts, "computed_at": now, "summary_ar": self._summary(now, counts, geo),
                "source": SOURCE}

    def _summary(self, now: float, counts: dict[str, int], geo: dict[str, Any] | None) -> str:
        if not self._rows:
            return "لم يصل خبرٌ بعد — %s" % LIMIT_AR
        parts = []
        for name in rules.CATEGORIES:
            if counts[name] == 0 and not (name == rules.GEOPOLITICS and geo):
                continue
            text = "%s %d" % (rules.LABELS_AR[name], counts[name])
            if name == rules.GEOPOLITICS and geo:
                text += " (%s)" % self._geo_text(now, geo)
            parts.append(text)
        return "آخر 24س: %s — %s" % (" · ".join(parts) or "لا خبر", LIMIT_AR)

    def _geo_text(self, now: float, row: dict[str, Any]) -> str:
        minutes = self._minutes(now, row["time"])
        ago = "%dد" % minutes if minutes < SUMMARY_HOURS_FROM_MIN else "%.1fس" % (minutes / 60)
        headline = (row["headline"] if len(row["headline"]) <= SUMMARY_HEADLINE_CHARS
                    else row["headline"][:SUMMARY_HEADLINE_CHARS].rstrip() + "…")
        moved = None
        for horizon in reversed(HORIZONS_MIN):
            value = row["moves"].get(_move_name(horizon))
            if value is not None:
                moved = "الناسداك %s٪ بعد %dد" % (_signed(value), horizon)
                break
        if moved is None:
            since, since_minutes = self._since(row)
            moved = ("الناسداك %s٪ حتّى الآن (بعد %sد)" % (_signed(since), since_minutes)
                     if since is not None else "لا سعر للناسداك بعده")
        return 'قبل %s: "%s" — %s' % (ago, headline, moved)

    async def _publish(self) -> None:
        if self._context is None:
            return
        await self._context.publish(EV_OUT, self._payload())
        self._published += 1

    # ── الحفظ والاستعادة ─────────────────────────────────────────────────
    async def snapshot(self) -> dict[str, Any]:
        return {"version": ATOM_VERSION,
                "rows": [{**row, "categories": list(row["categories"]), "moves": dict(row["moves"]),
                          "no_price": list(row["no_price"])} for row in self._rows],
                "seen": list(self._seen),
                "closes": [[at, price] for at, price in self._closes],
                "abs_mean": {name: [total[0], int(total[1])] for name, total in self._abs_mean.items()},
                "counters": {"received": self._received, "accepted": self._accepted,
                             "duplicates": self._duplicates, "candles": self._candles,
                             "rejected": dict(self._rejected)}}

    @staticmethod
    def _restored_row(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        headline = str(raw.get("headline") or "").strip()
        at = _num(raw.get("time"))
        if not headline or at is None:
            return None
        moves = raw.get("moves") if isinstance(raw.get("moves"), dict) else {}
        no_price = raw.get("no_price") if isinstance(raw.get("no_price"), list) else []
        # الأصناف تُعاد من العنوان بالقوائم الحاليّة: إن صُحّحت قائمةٌ بنسخةٍ لاحقة لا يبقى خبرٌ بصنفٍ قديم.
        return {"key": _key(headline), "time": at, "headline": headline, "source": raw.get("source"),
                "categories": rules.classify(headline), "price_at_news": _num(raw.get("price_at_news")),
                "base_done": bool(raw.get("base_done")),
                "moves": {str(k): float(v) for k, v in moves.items() if _num(v) is not None},
                "no_price": [str(x) for x in no_price]}

    async def restore(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        rows = []
        for raw in state.get("rows") or []:
            row = self._restored_row(raw)
            if row is None:
                self._reject(BAD_RESTORED_ROW)
                continue
            rows.append(row)
        self._rows = deque(rows[-self._keep:], maxlen=self._keep)
        self._seen = deque((str(k) for k in state.get("seen") or [] if isinstance(k, str)), maxlen=SEEN_KEYS_KEEP)
        for row in self._rows:
            if row["key"] not in self._seen:
                self._seen.append(row["key"])
        pairs = [(_num(p[0]), _num(p[1])) for p in state.get("closes") or []
                 if isinstance(p, (list, tuple)) and len(p) == 2]
        self._closes = sorted((at, price) for at, price in pairs
                              if at is not None and price is not None and price > 0)[-self._buffer:]
        sums = state.get("abs_mean")
        for name, total in (sums.items() if isinstance(sums, dict) else ()):
            if name in rules.CATEGORIES and isinstance(total, list) and len(total) == 2:
                value, count = _num(total[0]), _num(total[1])
                if value is not None and count is not None and count >= 0:
                    self._abs_mean[name] = [value, int(count)]
        counters = state.get("counters") if isinstance(state.get("counters"), dict) else {}
        for name in ("received", "accepted", "duplicates", "candles"):
            setattr(self, "_" + name, int(_num(counters.get(name)) or 0))
        self._restored = len(self._rows)

    # ── الصحّة ──────────────────────────────────────────────────────────
    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY, message="NOT_STARTED")
        now = self._clock()
        day = [r for r in self._rows if now - r["time"] <= 86400]
        per = " · ".join("%s %d" % (rules.LABELS_AR[name], sum(1 for r in day if name in r["categories"]))
                         for name in rules.CATEGORIES)
        rejected = " ".join("%s=%d" % kv for kv in sorted(self._rejected.items())) or "لا شيء"
        pending = sum(1 for r in self._rows if self._pending(r))
        message = ("أخبار محفوظة=%d · آخر 24س=%d (%s) · شموع %s للناسداك=%d · بانتظار حركة=%d · مكرّر=%d · "
                   "مرفوض: %s · %s" % (len(self._rows), len(day), per, self._frame, len(self._closes), pending,
                                        self._duplicates, rejected, LIMIT_AR))
        details = {"received": self._received, "accepted": self._accepted, "duplicates": self._duplicates,
                   "stored": len(self._rows), "restored": self._restored, "candles": self._candles,
                   "old_candles": self._old_candles, "price_candles": len(self._closes), "pending": pending,
                   "pulses": self._pulses, "published": self._published, "rejected": dict(self._rejected)}
        if not self._rows:
            return HealthStatus(state=HealthState.DEGRADED, message="لم يصل خبرٌ بعد · " + message,
                                details=details)
        if not self._closes:
            return HealthStatus(state=HealthState.DEGRADED,
                                message="لا شموع دقيقة للناسداك — الحركة بعد الخبر غير متاحة · " + message,
                                details=details)
        return HealthStatus(state=HealthState.HEALTHY, message=message, details=details)
