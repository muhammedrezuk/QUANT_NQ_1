from __future__ import annotations

import math
from typing import Any

from core.contracts.atom import AtomBase, AtomContext, HealthState, HealthStatus

ATOM_VERSION = "4.3.0"

EVENT_IN = "market.tick"
EVENT_ACCOUNT = "platform.account.state"
EVENT_ALERT = "market_data.quality_alert"
EVENT_STATE = "market_data.quality.state"
EVENT_OUT = EVENT_ALERT

REASON_NOT_STARTED = "NOT_STARTED"
REASON_NO_DATA = "NO_TICKS_YET"

KIND_DUPLICATE = "duplicate"
KIND_GAP = "time_gap"
KIND_SPIKE = "price_spike"
KIND_SPREAD = "abnormal_spread"

STATUS_INVALID = "INVALID"
STATUS_DEGRADED = "DEGRADED"
STATUS_HEALTHY = "HEALTHY"

PCT_SCALE = 100.0
_MID_DIVISOR = 2.0

# ٢٠٢٦-٠٩-١٨ — الشارة كانت عالقة على `DEGRADED` ولا تستطيع العودة.
#
# كان الحكم: `DEGRADED if self._invalid else HEALTHY` — و`_invalid`
# عدّادٌ **تراكميّ**. تكّةٌ فاسدة واحدة منذ الإقلاع تُصفّر الشارة إلى
# الأصفر إلى الأبد، فلا تفرّق بين سوقٍ طبيعيّ وانهيارٍ في التغذية.
#
# ومقيس من `timeline.db` (٢٠٠٬٠٠٠ صفّ رفضٍ، ثلاثون ساعة متّصلة):
#   crossed_spread            198,777  (99.4%) — في **كلّ** ساعةٍ بلا استثناء
#   invalid_or_missing_price    1,223
#   invalid_or_missing_ask        958
#   invalid_or_missing_bid        836
# والمدى بين ساعةٍ وأخرى 141 ← 9,948 رفضًا، أي أنّ العدد المطلق لا يصف
# شيئًا: يرتفع لأنّ السوق نشط لا لأنّ البيانات ساءت.
#
# فالشارة تُحكَم الآن بـ**نسبةٍ في نافذةٍ قريبة** لا بعدّادٍ منذ الإقلاع،
# والعلّتان تُفصلان لأنّ ردّهما مختلف:
#   «دفتر»: `crossed_spread` وأخواته — حالة سوقٍ يحرسها 112 أصلًا.
#   «شكل» : تكّةٌ بلا رمزٍ أو حسابٍ أو وقت — تغذيةٌ مشوّهة، علّةٌ عندنا.
# خلطُهما تحت رقمٍ واحد هو سبب عمى الشارة: الأولى خلفيّةٌ دائمة تغرق
# الثانية النادرة والأخطر.
#
# والزمن من التِكّة لا من ساعة الجهاز — كسائر ذرّات هذا القسم.
_DEFAULT_WINDOW_S = 300.0
# مقيسة حيًّا لحظة التغيير: `crossed_book` عند 106 = 1.3%، و`crossed_spread`
# عند 112 = 1.3% من 78,271 تكّة. فخمسةٌ بالمئة أربعةُ أضعاف الخلفيّة
# المقيسة — خطُّ بدءٍ لا حكمٌ نهائيّ، ويُشدّ بكلمةٍ في المانيفست.
_DEFAULT_BOOK_MAX_PCT = 5.0
# علل الشكل ~20 في الساعة من عشرات الآلاف، أي أقلّ من 0.05%. فنصفُ
# الواحد بالمئة يحتمل الخلفيّة ويشتعل قبل أن تصير التغذية غير صالحة.
_DEFAULT_SHAPE_MAX_PCT = 0.5
# أصغر عيّنةٍ تُقرأ منها نسبة. نافذةٌ فُتحت للتوّ فيها تكّةٌ واحدة فاسدة
# تعطي 100% — فترتجف الشارة عند كلّ دوران. ونافذةٌ **مكتملة** وحدها
# تتجمّد على ماضٍ حين تهدأ التغذية. فالقراءة من النافذة الجارية، وما
# دامت رقيقة تُضمّ إليها السابقة. ومقيس: ~78 ألف تكّة في التشغيلة،
# أي نحو أربع عشرة في الثانية — فمئتان ≈ خمس عشرة ثانية من الاكتمال.
_DEFAULT_MIN_SAMPLE = 200.0

# `crossed_spread` وحدها حالةُ دفتر: الباقي شكلٌ مشوّه لا سوقٌ ضيّق.
# و`nonpositive_price` ليست سوقًا: سعرٌ صفريّ أو سالب لا يوجد في أيّ
# دفترٍ حيّ، فهي شكل.
_BOOK_REASONS = frozenset({"crossed_spread"})

# 🔴 ٢٠٢٦-٠٩-٢٤ (ختم المالك «Nq كل إصلاحات») — السبريد الصفريّ يُعدّ وحده، لا فسادًا.
#
# كانت `crossed_spread` تجمع حالتين: شراءٌ فوق البيع (تقاطعٌ حقيقيّ) وشراءٌ يساوي
# البيع (سبريد صفر). ومقيسٌ على 13,468 رفضًا لـ112 في ثلاث ساعات من مخزن الخطّ
# الزمنيّ: اليورو 5,939 مساواةً تامّة مقابل 45 تقاطعًا فقط — والسبريد الصفر على
# اليورو حالةُ سوقٍ معروفة في حساب السبريد الخام. فبلغت نسبة «الدفتر» 5–7٪ منذ
# فُعّل اليورو، والشارة صفراء على ما ليس فسادًا.
#
# وقاعدة ٢٠٢٦-٠٩-٠٧ باقية كما هي: التِكّة ذات السبريد الصفر تبقى INVALID للقرار
# (454 يقرأ الحالة لا السبب)، و112 و106 و103 يردّونها بقاعدتهم. الذي تغيّر هنا
# العدّ وحده: تُعدّ باسمها `locked_spread` وتُعلن نسبتُها، ولا تدخل إنذار الدفتر.
_LOCKED_REASONS = frozenset({"locked_spread"})


def num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class Atom(AtomBase):
    def __init__(self) -> None:
        self._context: AtomContext | None = None
        self._running = False
        self._gap_threshold_s = 0.0
        self._spike_pct = 0.0
        self._spread_pct = 0.0
        self._window_s = _DEFAULT_WINDOW_S
        self._book_max_pct = _DEFAULT_BOOK_MAX_PCT
        self._shape_max_pct = _DEFAULT_SHAPE_MAX_PCT
        self._min_sample = _DEFAULT_MIN_SAMPLE
        self._using_defaults: list[str] = []
        self._brokers: dict[str, str] = {}
        self._last_price: dict[tuple, float] = {}
        self._last_ts: dict[tuple, float] = {}
        self._last_key: dict[tuple, tuple] = {}
        self._checked = 0
        self._alerts = 0
        self._invalid = 0
        self._shape_total = 0
        self._book_total = 0
        self._locked_total = 0
        self._reason_totals: dict[str, int] = {}
        # النافذة الجارية وآخر نافذةٍ اكتملت
        self._win_start: float | None = None
        self._win_end: float | None = None
        self._win_checked = 0
        self._win_shape = 0
        self._win_book = 0
        self._win_locked = 0
        self._win_reasons: dict[str, int] = {}
        self._last_window: dict[str, Any] | None = None

    async def initialize(self, context: AtomContext) -> None:
        self._context = context
        config = context.config
        self._gap_threshold_s = float(config["gap_threshold_s"])
        self._spike_pct = float(config["spike_pct"])
        self._spread_pct = float(config["spread_pct"])
        # ٢٠٢٦-٠٩-١٨ — العيارات الثلاثة الجديدة لها نسخةٌ في الكود.
        #
        # مقيس ٢٠٢٦-٠٩-١٦ على 109: `atom.py` يصير حيًّا فور حفظه بينما
        # `config` من المانيفست لا يبلغ الذرّة بلا إقلاع. فلو اتّكلت
        # هذه العيارات على `config` وحده لبقيت الشارة عالقة بعد الإصلاح،
        # والإصلاح مكتوبٌ على القرص. والمانيفست يبقى المرجع حين يصل.
        #
        # و`in config` لا `.get() or`: صفرٌ صريح قرارُ مالكٍ (تعطيل
        # النافذة) لا فراغٌ يُدهس بافتراضيّ.
        self._using_defaults = []
        for key, attr, fallback in (
                ("quality_window_s", "_window_s", _DEFAULT_WINDOW_S),
                ("book_max_pct", "_book_max_pct", _DEFAULT_BOOK_MAX_PCT),
                ("shape_max_pct", "_shape_max_pct", _DEFAULT_SHAPE_MAX_PCT),
                ("min_sample", "_min_sample", _DEFAULT_MIN_SAMPLE)):
            if key in config:
                setattr(self, attr, float(config[key]))
            else:
                setattr(self, attr, fallback)
                self._using_defaults.append(key)
        context.subscribe(EVENT_IN, self._on_tick)
        context.subscribe(EVENT_ACCOUNT, self._on_account)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        await self.stop()

    async def _on_account(self, payload: Any) -> None:
        if not self._running or not isinstance(payload, dict):
            return
        account = str(payload.get("account_id") or "").strip()
        broker = str(payload.get("broker") or "").strip()
        if account and broker:
            self._brokers[account] = broker

    async def _state(self, payload: dict, status: str, reasons: list) -> None:
        if self._context is None:
            return
        body = {
            "account_id": payload.get("account_id"),
            "broker": payload.get("broker") or self._brokers.get(
                str(payload.get("account_id") or "")),
            "symbol": payload.get("symbol"),
            "status": status,
            "usable_for_decision": status != STATUS_INVALID,
            "reasons": reasons,
        }
        timestamp = num(payload.get("timestamp"))
        if timestamp is not None:
            body["timestamp"] = timestamp
        await self._context.publish(EVENT_STATE, body)

    def _invalid_reasons(self, symbol: str, account: str, broker: str,
                         bid: float | None, ask: float | None,
                         timestamp: float | None) -> list:
        reasons = []
        if not symbol:
            reasons.append("missing_symbol")
        if not account:
            reasons.append("missing_account_id")
        if not broker:
            reasons.append("missing_broker")
        if bid is None or ask is None:
            reasons.append("non_finite_price")
        elif bid <= 0 or ask <= 0:
            reasons.append("nonpositive_price")
        elif ask < bid:
            # ٢٠٢٦-٠٩-٠٧ — تُوحَّد القاعدة مع 112 و106 و103: السبريد الصفريّ
            # (`bid == ask`) دفتر معطوب لا سوق، وكان يمرّ هنا ويُرفض هناك.
            reasons.append("crossed_spread")
        elif ask == bid:
            # ٢٠٢٦-٠٩-٢٤ — ويبقى مرفوضًا للقرار كما قضت قاعدة ٠٩-٠٧، لكن باسمه
            # هو: مساواةٌ لا تقاطع (`_LOCKED_REASONS` أعلاه).
            reasons.append("locked_spread")
        if timestamp is None or timestamp <= 0:
            reasons.append("invalid_timestamp")
        return reasons

    def _roll_window(self, timestamp: float | None) -> None:
        """يفتح نافذةً جديدة متى انقضت مدّتها — بساعة التِكّة.

        وتراجُع الزمن يفتح نافذةً أيضًا: مصدرٌ أُعيد ضبطه أو ساعةٌ
        صُحّحت لا يُخلط قياسُه بما قبله. (سابقتها في 101.)
        """
        if timestamp is None or self._window_s <= 0:
            return
        if self._win_start is None:
            self._win_start = timestamp
            self._win_end = timestamp
            return
        if timestamp < self._win_start or timestamp - self._win_start >= self._window_s:
            if self._win_checked:
                self._last_window = self._window_snapshot()
            self._win_start = timestamp
            self._win_checked = 0
            self._win_shape = 0
            self._win_book = 0
            self._win_locked = 0
            self._win_reasons = {}
        self._win_end = timestamp

    def _window_snapshot(self) -> dict[str, Any]:
        span = 0.0
        if self._win_start is not None and self._win_end is not None:
            span = max(0.0, self._win_end - self._win_start)
        return {"checked": self._win_checked, "shape": self._win_shape,
                "book": self._win_book, "locked": self._win_locked,
                "reasons": dict(self._win_reasons), "span_s": span}

    async def _on_tick(self, payload: Any) -> None:
        if not self._running or self._context is None or not isinstance(payload, dict):
            return
        symbol = str(payload.get("symbol") or "")
        account = str(payload.get("account_id") or "")
        broker = str(payload.get("broker") or "") or self._brokers.get(account, "")
        scope = (account, broker, symbol)
        bid = num(payload.get("bid"))
        ask = num(payload.get("ask"))
        timestamp = num(payload.get("timestamp"))
        self._checked += 1
        self._roll_window(timestamp if timestamp and timestamp > 0 else None)
        self._win_checked += 1
        # ٢٠٢٦-٠٩-١٨ — شرط الفساد كان مكتوبًا مرّتين: نسخةٌ مضمّنة هنا
        # ونسخةٌ في `_invalid_reasons`. توأمان يُصلَح أحدهما ويُنسى الآخر
        # فتصير الذرّة تُعلن سببًا وتحكم بغيره. المصدر واحدٌ الآن.
        problems = self._invalid_reasons(symbol, account, broker, bid, ask, timestamp)
        if problems:
            if all(reason in _LOCKED_REASONS for reason in problems):
                # سبريد صفر وحده: مرفوضٌ للقرار، ويُعدّ وحده لا فسادًا.
                self._locked_total += 1
                self._win_locked += 1
                for reason in problems:
                    self._reason_totals[reason] = self._reason_totals.get(reason, 0) + 1
                await self._state(payload, STATUS_INVALID, problems)
                return
            self._invalid += 1
            book = any(reason in _BOOK_REASONS for reason in problems)
            if book:
                self._book_total += 1
                self._win_book += 1
            else:
                self._shape_total += 1
                self._win_shape += 1
            for reason in problems:
                self._reason_totals[reason] = self._reason_totals.get(reason, 0) + 1
                if not book:
                    self._win_reasons[reason] = self._win_reasons.get(reason, 0) + 1
            await self._state(payload, STATUS_INVALID, problems)
            return

        reasons = []
        price = (bid + ask) / _MID_DIVISOR
        key = (bid, ask, timestamp)
        if key == self._last_key.get(scope):
            reasons.append(KIND_DUPLICATE)
            await self._alert(KIND_DUPLICATE, payload, {}, timestamp)
        self._last_key[scope] = key

        previous_ts = self._last_ts.get(scope)
        if previous_ts is not None and timestamp - previous_ts > self._gap_threshold_s:
            reasons.append(KIND_GAP)
            await self._alert(KIND_GAP, payload,
                              {"gap_s": round(timestamp - previous_ts, 2)}, timestamp)
        self._last_ts[scope] = timestamp

        previous_price = self._last_price.get(scope)
        if previous_price and abs(price - previous_price) / previous_price * PCT_SCALE > self._spike_pct:
            change = abs(price - previous_price) / previous_price * PCT_SCALE
            reasons.append(KIND_SPIKE)
            await self._alert(KIND_SPIKE, payload,
                              {"change_pct": round(change, 3)}, timestamp)
        self._last_price[scope] = price

        spread = (ask - bid) / price * PCT_SCALE
        if spread > self._spread_pct:
            reasons.append(KIND_SPREAD)
            await self._alert(KIND_SPREAD, payload,
                              {"spread_pct": round(spread, 4)}, timestamp)

        await self._state(payload, STATUS_DEGRADED if reasons else STATUS_HEALTHY,
                          reasons)

    async def _alert(self, kind: str, payload: dict, details: dict,
                     timestamp: float | None) -> None:
        self._alerts += 1
        account = str(payload.get("account_id") or "")
        body = {
            "kind": kind,
            "account_id": account,
            "broker": payload.get("broker") or self._brokers.get(account),
            "symbol": payload.get("symbol"),
            **details,
        }
        if timestamp is not None:
            body["timestamp"] = timestamp
        await self._context.publish(EVENT_ALERT, body)

    async def health_check(self) -> HealthStatus:
        if not self._running:
            return HealthStatus(state=HealthState.UNHEALTHY,
                                message=REASON_NOT_STARTED)
        if self._checked == 0:
            return HealthStatus(state=HealthState.DEGRADED, message=REASON_NO_DATA)
        # القراءة من النافذة الجارية — فهي الحاضر. وما دامت أرقّ من
        # `min_sample` تُضمّ إليها السابقة: بلا الضمّ ترتجف الشارة عند
        # كلّ دوران (تكّةٌ فاسدة واحدة = 100%)، وبالسابقة وحدها تتجمّد
        # على ماضٍ متى هدأت التغذية.
        window = self._window_snapshot()
        if window["checked"] < self._min_sample and self._last_window:
            previous = self._last_window
            reasons = dict(previous["reasons"])
            for name, count in window["reasons"].items():
                reasons[name] = reasons.get(name, 0) + count
            window = {"checked": window["checked"] + previous["checked"],
                      "shape": window["shape"] + previous["shape"],
                      "book": window["book"] + previous["book"],
                      "locked": window.get("locked", 0) + previous.get("locked", 0),
                      "reasons": reasons,
                      "span_s": window["span_s"] + previous["span_s"]}
        checked = window["checked"] or 1
        shape_pct = PCT_SCALE * window["shape"] / checked
        book_pct = PCT_SCALE * window["book"] / checked
        locked_pct = PCT_SCALE * window.get("locked", 0) / checked
        # العتبة ليست شذوذًا؛ ما يتجاوزها هو الشاذّ — كقاعدة السبريد أعلاه.
        breached = []
        if shape_pct > self._shape_max_pct:
            breached.append("شكل")
        if book_pct > self._book_max_pct:
            breached.append("دفتر")
        detail = ""
        if window["reasons"]:
            detail = " (%s)" % ", ".join(
                "%s=%d" % kv for kv in sorted(window["reasons"].items()))
        message = ("نافذة=%gث/%gث · فُحص=%d · شكل=%.2f%%%s · دفتر=%.2f%% · "
                   "سبريد_صفر=%.2f%% · "
                   "الإجمالي: %d فحصًا · %d فاسدة (شكل=%d دفتر=%d) · سبريد_صفر=%d · %d تنبيهًا"
                   % (window["span_s"], self._window_s, window["checked"],
                      shape_pct, detail, book_pct, locked_pct, self._checked,
                      self._invalid, self._shape_total, self._book_total,
                      self._locked_total, self._alerts))
        if breached:
            message = "تجاوُز " + "+".join(breached) + " · " + message
        if self._using_defaults:
            # لا يُقرأ العيار منفَّذًا من مصدرٍ لم يُقصد — سابقتها في 109.
            message += " [افتراضيّ: %s]" % ",".join(self._using_defaults)
        return HealthStatus(
            state=HealthState.DEGRADED if breached else HealthState.HEALTHY,
            message=message,
            details={"checked": self._checked, "alerts": self._alerts,
                     "invalid": self._invalid, "shape_total": self._shape_total,
                     "book_total": self._book_total,
                     "locked_total": self._locked_total,
                     "window_locked_pct": round(locked_pct, 4),
                     "reason_totals": dict(self._reason_totals),
                     "window_checked": window["checked"],
                     "window_span_s": window["span_s"],
                     "window_shape_pct": round(shape_pct, 4),
                     "window_book_pct": round(book_pct, 4)})
