"""Live descriptive strategy contract for section 400.

This module never emits a trading decision.  Direction is a measured strategic
lean on -100..100; weights become effective only after evidence gates pass.
"""

from __future__ import annotations

import math
import os
import sqlite3
from collections import deque
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from shared.tick_contract import as_validated_tick

STATE_NOT_READY = "NOT_READY"
STATE_READY = "READY"
DIRECTIONAL_IDS = (
    "trend_continuation",
    "reversal_potential",
    "breakout_acceptance",
    "pullback_quality",
    "momentum_expansion",
    "range_rotation",
    "liquidity_raid",
)
CONTEXT_IDS = (
    "entry_structure_quality",
    "invalidation_quality",
    "news_regime",
    "session_regime",
)
ALL_IDS = DIRECTIONAL_IDS + CONTEXT_IDS
EQUAL_WEIGHT = 100.0 / len(DIRECTIONAL_IDS)

# ٢٠٢٦-٠٩-١١ (ختم NQ): الوزن المتساوي كان كذبًا مقيسًا.
#
# `EQUAL_WEIGHT` يعطي كل محلّل اتجاهيّ 14.2857 مهما كانت نتيجته. وقياس
# `scripts/edge_derivation.py` على **270,000 تِكّة حقيقية** من مخزن المنصّة
# (ثلاثة رموز، أفق 50/200/1000 تِكّة، بخطأ معياريّ):
#
#   404 · BTCUSD :  -126.91 ±9.97  نقطة للإشارة   ← يتكلّم في 99.8% من القرارات
#   408 · BTCUSD :  -167.30 ±9.96                  ← يتكلّم في 100%
#   406 · BTCUSD :  -422.39 ±129.90
#   404 · GBPUSD :    -0.01 ±0.00                  ← والسبريد 0.20
#   409 · XAUUSD :    -1.94 ±0.91                  ← والسبريد 8.00
#   404 · XAUUSD :   +13.27 ±2.18 مقابل سبريد 8.00 ← الحافّة المؤكّدة الوحيدة
#
# أي أنّ أكثر المحلّلَين كلامًا يخسران على رمزين من ثلاثة، ويأخذان الوزن
# نفسه الذي يأخذه من يربح. حكم المالك: «صفقات زبالة… بدّي يدير صفقة
# وستوبها وهدفها مو عدد صفقات… يشتقّ أرقام من نفسه».
#
# فالوزن صار مضروبًا بمعامل حافّة مقيس لكل (محلّل × رمز):
#   0.0  ⇐ حافّة سالبة مؤكّدة: يعلن رأيه ولا يُحسب في التصويت
#   >0   ⇐ يغطّي السبريد بحدّ ثقته الأدنى (mean − 2·se > spread)
#   None ⇐ لا حكم (عيّنة دون 200 إشارة) ⟵ **يبقى على وزنه القائم**
#
# ⛔ ثلاث قواعد في هذا الكود دُفع ثمنها:
#   ١) **الفشل آمن**: ملفٌّ غائب أو تالف أو مفتاح ناقص ⇒ لا تغيير إطلاقًا.
#      عيارٌ يُسكِت محلّلًا بسبب ملفّ مفقود أسوأ من الوزن المتساوي.
#   ٢) **لا حكم ≠ صفر**: من لم تكفِ عيّنته يبقى كما هو، ولا يُخترع له رقم.
#   ٣) **الصمت معلَن لا مخفيّ**: البطاقة تحمل `edge_factor` و`edge_verdict`،
#      فمن يقرأ وزنًا صفرًا يعرف أنّه قياسٌ لا عطل.
from shared.fs_stamp import file_stamp  # noqa: E402
# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): المسارات الثلاثة في هذا الملفّ كانت محفورة على
# `<المشروع>/forex_runtime/var/…` فتتجاهل `QUANT_RUNTIME_ROOT`، فكانت الفحوص والإعادة
# تقرأ `edge_weights.json` و`analysis_scale.json` و`market_data.db` الحيّة. صارت من مالك
# الجذور (`trade_setup.runtime_var_file` ⟵ `runtime_paths.runtime_var`)، والحيّ نفسه حرفًا.
from shared.trade_setup import runtime_var_file  # noqa: E402

_EDGE_PATH = runtime_var_file("telemetry", "edge_weights.json")
_EDGE_CACHE: dict[str, Any] = {"mtime": None, "table": {}}
_ATOM_OF = {
    "trend_continuation": "404", "reversal_potential": "405",
    "breakout_acceptance": "406", "pullback_quality": "407",
    "momentum_expansion": "408", "range_rotation": "409",
    "liquidity_raid": "410",
}


# ٢٠٢٦-٠٩-١١ (حكم المالك): «كل رموز مخلوطة» · «بدّي [بتكوين] سكالبنك مو
# عصبي، عادي بين 20 دولار حركة لـ40 دولار».
#
# كل محلّل كان يحوّل الحركة إلى قوّة بمعامل **واحد لكل الرموز** (50,000).
# والحركة الوسيطة المقيسة داخل نافذة التحليل (100 تِكّة، 120 ألف تِكّة لكل
# رمز) تقول إنّ هذا المعامل يعني أشياء متناقضة:
#
#   BTCUSD  حركة $35.50  ⇒ المعامل الصحيح   216,948   (الثابت أصغر 4.3×)
#   XAUUSD  حركة  $1.465 ⇒                  296,410   (5.9×)
#   USTEC   حركة  6.90   ⇒                  422,715   (8.5×)
#   US30    حركة 14.50   ⇒                  361,291   (7.2×)
#   US500   حركة  2.60   ⇒                  293,805   (5.9×)
#   EURUSD  حركة 0.00015 ⇒                  749,518   (15.0×)
#   GBPUSD  حركة 0.00013 ⇒                1,081,759   (21.6×)
#
# أي أنّ «قوّة 50» على الباوند كانت تعني خُمس ما تعنيه على بتكوين — ولهذا
# كانت القوّة الوسيطة 0.74 من 100 ولا تفرّق بين حركةٍ تافهة وحركةٍ حقيقية.
# ونافذة 100 تِكّة على بتكوين تعطي $35.50، وهي مدى المالك ($20-$40) نفسه:
# حدسه طابق القياس، فصار معيارًا يُشتقّ عليه الباقي.
#
# ⛔ والفشل آمن كسابقه: ملفٌّ غائب أو رمزٌ غير مقيس ⇒ المعامل القائم بلا مساس.
_SCALE_PATH = runtime_var_file("telemetry", "analysis_scale.json")
_SCALE_CACHE: dict[str, Any] = {"mtime": None, "table": {}}


def movement_scale(symbol: Any, default: float) -> float:
    """معامل تحويل الحركة إلى قوّة لهذا الرمز — قوّة 100 = حركته الوسيطة."""
    key = str(symbol or "").strip().upper()
    if not key:
        return default
    # ٢٠٢٦-٠٩-١٨ (ختم NQ): كان `stat` يقع مع كلّ نداء — ١٣ ذرّة × رمز ×
    # تِكّة — فقِيس ٣١٪ من زمن الحلقة المشغول. الطابع الآن مخزَّن بفترةٍ
    # هي نفسها فترة `_GATE_RECHECK_S`، والمنطق بعدها بلا تغيير.
    ok, stamp = file_stamp(_SCALE_PATH)
    if not ok:
        return default
    if _SCALE_CACHE["mtime"] != stamp:
        try:
            import json
            data = json.loads(_SCALE_PATH.read_text(encoding="utf-8"))
            rows = data.get("symbols")
            _SCALE_CACHE["table"] = rows if isinstance(rows, dict) else {}
        except Exception:
            _SCALE_CACHE["table"] = {}
        _SCALE_CACHE["mtime"] = stamp
    row = _SCALE_CACHE["table"].get(key)
    if not isinstance(row, dict):
        return default
    try:
        frac = float(row.get("frac"))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(frac) or frac <= 0.0:
        return default
    return 100.0 / frac


def edge_factor(strategy_id: str, symbol: Any) -> float | None:
    """معامل الحافّة المقيس لهذا المحلّل على هذا الرمز، أو None إن لا حكم."""
    atom = _ATOM_OF.get(str(strategy_id))
    key = str(symbol or "").strip().upper()
    if not atom or not key:
        return None
    ok, stamp = file_stamp(_EDGE_PATH)
    if not ok:
        return None                      # لا ملفّ ⇒ الوزن القائم كما هو
    if _EDGE_CACHE["mtime"] != stamp:
        try:
            import json
            data = json.loads(_EDGE_PATH.read_text(encoding="utf-8"))
            table = data.get("derived_weights")
            _EDGE_CACHE["table"] = table if isinstance(table, dict) else {}
        except Exception:
            _EDGE_CACHE["table"] = {}    # ملفّ تالف ⇒ لا تغيير
        _EDGE_CACHE["mtime"] = stamp
    row = _EDGE_CACHE["table"].get(atom)
    if not isinstance(row, dict):
        return None
    value = row.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0.0 else None


def finite(value: Any, fallback: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def clip(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    number = finite(value, 0.0) or 0.0
    return max(low, min(high, number))


# ٢٠٢٦-٠٩-٠٦ (أمر المالك: «وسّع»): كان المخزن 256 تِكّة، ونوافذ أصحاب
# الإعداد وُسِّعت إلى 240 و320 — فنافذة أوسع من المخزن لا تمتلئ أبدًا،
# وصاحبها لا يصنع فكرة قطّ (`len(prior) < window` دائمًا). المخزن يتّسع
# بهامش كي تبقى النافذة قرارَ مالكها لا أسيرةَ حدٍّ خفيّ.
#
# ٢٠٢٦-٠٩-٠٦ (حكم المالك على السبريد المقيس 38.54): «كيف نظام يغطّي
# صفقة هدفها 39؟ لازم صفقات لا تقلّ عن هدف 300 أو 500، ستوب لا يقلّ عن
# 100». وفكرةٌ بهذا المقياس تحتاج بنيةً تمتدّ آلاف التِكّات لا مئاتها،
# فالمخزن يتّسع لها. (٨١٩٢ عددًا × أربعة طوابير × نطاقات قليلة — كلفة
# ذاكرة لا تُذكر أمام فكرةٍ تستحقّ التنفيذ.)
_HISTORY = 8192


@dataclass
class StrategicTickState:
    prices: deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY))
    bids: deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY))
    asks: deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY))
    timestamps: deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY))
    returns: deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY - 1))
    sequence: int = 0


# ٢٠٢٦-٠٩-٠٦ (قياس المالك: «ساعتين ولا صفقة»). السبب مقيس لا مُخمَّن:
# النواة تُقلع ونوافذ الاستراتيجيات فارغة، فتُملأ من التِكّ الحيّ وحده
# بمعدّل 0.58 تِكّة/ثانية — أي 86 دقيقة لنافذة 3000 و115 دقيقة لنافذة
# 4000. طوال تلك المدّة كل بطاقة `insufficient_data` وكل اتجاه صفر،
# فلا يولد إعدادٌ أصلًا ولا يُرفض — صمتٌ تامّ لا يُعلن عن نفسه.
#
# وتاريخ السوق كان موجودًا طوال الوقت (٢٩٨ ألف تِكّة في market_data.db)
# ولا أحد يقرؤه. الذرّة لا يجوز أن تولد عمياء: تُملأ نافذتها من
# التاريخ المخزَّن مرّة واحدة عند أوّل تِكّة لكل نطاق، فتعمل من الثانية
# الأولى بدل أن تنتظر ساعتين بعد كل إقلاع.
_MARKET_DB = runtime_var_file("store", "market_data.db")


def warm_start(state: "StrategicTickState", symbol: str) -> int:
    """يملأ النافذة من تاريخ السوق المخزَّن. يُرجع عدد التِكّات المحمَّلة.

    ⚠️ وضع الإعادة التاريخية (`QUANT_REPLAY_NO_WARM=1`): يُعزَل التسخين.
    السبب مقيس ٢٠٢٦-٠٩-٠٧: التسخين يملأ `state.timestamps` بطوابع **اليوم**
    من `market_data.db` (آخرها 1788790421)، فيرفض حارسُ الترتيب في `ingest`
    (`stamp <= timestamps[-1]`) كل تِكّة تاريخية — النتيجة المقيسة كانت
    404 `ticks=0 emitted=0` بينما 112 يقول `valid=640 invalid=0`، فيغيب
    القسم 400 عن كل دورة و453 يقيس `p=0.00`.
    حارس الترتيب نفسه **لا يُمسّ** — هو حماية حقيقية من التكرار وخارج الترتيب.
    الافتراضي بلا المتغيّر: السلوك السابق حرفًا بحرف.
    """
    if os.environ.get("QUANT_REPLAY_NO_WARM", "").strip() == "1":
        return 0
    if not _MARKET_DB.exists():
        return 0
    try:
        conn = sqlite3.connect(
            "file:%s?mode=ro" % _MARKET_DB.as_posix(), uri=True, timeout=2.0
        )
        try:
            rows = conn.execute(
                "SELECT bid, ask, occurred_at FROM market_data "
                "WHERE symbol = ? ORDER BY id DESC LIMIT ?",
                (symbol, _HISTORY),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return 0
    loaded = 0
    for bid, ask, stamp in reversed(rows):
        b, a, ts = finite(bid), finite(ask), finite(stamp)
        if b is None or a is None or ts is None or b <= 0 or a < b or ts <= 0:
            continue
        if state.timestamps and ts <= state.timestamps[-1]:
            continue
        price = (b + a) / 2.0
        if state.prices:
            state.returns.append(price / state.prices[-1] - 1.0)
        state.prices.append(price)
        state.bids.append(b)
        state.asks.append(a)
        state.timestamps.append(ts)
        loaded += 1
    return loaded


class StrategyRuntime:
    def __init__(self, strategy_id: str, *, directional: bool = True) -> None:
        if strategy_id not in ALL_IDS:
            raise ValueError("UNKNOWN_STRATEGY_COMPONENT")
        self.strategy_id = strategy_id
        self.directional = directional
        self.states: dict[tuple[str, str, str], StrategicTickState] = {}
        self.weight = EQUAL_WEIGHT if directional else 0.0
        self.required_depth = 60.0
        self.confidence_threshold = 60.0
        self.strength_threshold = 0.0
        self.required_ticks = 24
        self.invalid = 0
        self.warmed: dict[tuple[str, str, str], int] = {}

    def configure(self, config: dict[str, Any]) -> None:
        self.weight = (
            clip(config.get("weight", self.weight)) if self.directional else 0.0
        )
        self.required_depth = clip(config.get("required_depth", 60.0))
        self.confidence_threshold = clip(config.get("confidence_threshold", 60.0))
        self.strength_threshold = clip(config.get("strength_threshold", 0.0))
        self.required_ticks = max(2, int(config.get("required_ticks", 24)))

    def ingest(
        self, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], StrategicTickState] | None:
        tick = as_validated_tick(payload)
        account = str(tick.get("account_id") or "").strip()
        broker = str(tick.get("broker") or "").strip()
        symbol = str(tick.get("symbol") or "").strip().upper()
        price = finite(tick.get("price"))
        bid = finite(tick.get("bid"), price)
        ask = finite(tick.get("ask"), price)
        stamp = finite(tick.get("source_timestamp", tick.get("timestamp")))
        if (
            not account
            or not broker
            or not symbol
            or price is None
            or bid is None
            or ask is None
            or stamp is None
            or price <= 0
            or bid <= 0
            # ٢٠٢٦-٠٩-٠٧ — تُوحَّد القاعدة مع 112 و106 و103 و115
            # و`live_analysis`: السبريد الصفريّ (`bid == ask`) دفتر
            # معطوب لا سوق، وقياسه يعطي صفرًا فتدخل تكلفة عبورٍ
            # كاذبة إلى حساب اللوت (موثّق في 551:471).
            or ask <= bid
            or stamp <= 0
        ):
            self.invalid += 1
            return None
        scope = (account, broker, symbol)
        state = self.states.get(scope)
        if state is None:
            state = StrategicTickState()
            self.warmed[scope] = warm_start(state, symbol)
            self.states[scope] = state
        if state.timestamps and stamp <= state.timestamps[-1]:
            self.invalid += 1
            return None
        if state.prices:
            state.returns.append(price / state.prices[-1] - 1.0)
        state.prices.append(price)
        state.bids.append(bid)
        state.asks.append(ask)
        state.timestamps.append(stamp)
        state.sequence += 1
        return tick, state

    def depth(self, state: StrategicTickState) -> tuple[float, dict[str, float]]:
        returns = list(state.returns)[-self.required_ticks :]
        sample = clip(len(returns) / self.required_ticks * 100.0)
        movement = clip(sum(abs(x) for x in returns) * 160_000.0)
        spreads = [
            (a - b) / p
            for b, a, p in zip(
                list(state.bids)[-self.required_ticks :],
                list(state.asks)[-self.required_ticks :],
                list(state.prices)[-self.required_ticks :],
            )
            if p > 0
        ]
        spread_quality = clip(
            100.0 - (sum(spreads) / len(spreads) if spreads else 0.0) * 200_000.0
        )
        if returns:
            mean = sum(returns) / len(returns)
            variance = sum((x - mean) ** 2 for x in returns) / len(returns)
            mean_abs = sum(abs(x) for x in returns) / len(returns)
            consistency = clip(100.0 - math.sqrt(variance) / max(mean_abs, 1e-9) * 50.0)
        else:
            consistency = 0.0
        current = clip(
            0.4 * sample + 0.25 * movement + 0.2 * spread_quality + 0.15 * consistency
        )
        return current, {
            "sample": sample,
            "movement": movement,
            "spread_quality": spread_quality,
            "consistency": consistency,
        }

    def card(
        self,
        tick: dict[str, Any],
        state: StrategicTickState,
        *,
        direction: float,
        strength: float,
        confidence: float,
        signal: str,
        evidence: dict[str, Any] | None = None,
        status: str = "ok",
        context_factor: float = 1.0,
    ) -> dict[str, Any]:
        depth, depth_parts = self.depth(state)
        direction = max(-100.0, min(100.0, float(direction)))
        strength = clip(strength)
        confidence = clip(confidence)
        context_factor = max(0.0, min(1.0, float(context_factor)))
        # ⛔ **ختم `NQ` ٢٠٢٦-٠٩-٢٣ — «لا توقف تحليل ابدا، مو شغلكم توقفوه».**
        #
        # كان هنا إسكاتٌ بُني ٢٠٢٦-٠٩-١١: `if edge == 0.0: direction = 0.0`.
        # ومعامل الحافّة يُقرأ من `edge_weights.json`، وعشرُ خلايا فيه كانت
        # صفرًا (404 على BTCUSD·USTEC·US30 · 406 على BTCUSD·US30 · 407 على
        # XAUUSD·USTEC · 408 على BTCUSD·USTEC·US30). وما يُصوَّت به هو
        # `direction`، فكان تصفيرُه **يخرس المحلّل عند ٤١٣ و٤٥٣ معًا** —
        # اثنا عشر (محلّل × رمز) صامتون بقياسٍ سالب.
        #
        # والقياسُ السالب حقيقةٌ تُقال **لا تفويضًا بالإسكات**. وهذا هو العطب
        # نفسُه الذي نُزع من ٤٠٥/٤٠٦/٤١٠ صباحَ اليوم (`cb197f7`) — بوّابةُ
        # رمزٍ تمنع النشر — **وبقي هذا التوأم قائمًا فلم يُرَ**. البوّابات
        # التوأم: يُصلَح جانبٌ ويُنسى نظيره.
        #
        # فالحافّةُ اليوم **تُعاير ولا تحكم**: تضرب الوزنَ إن كانت موجبة،
        # ولا تلمس `direction` أبدًا، ولا تُنزل وزنًا إلى الصفر. و
        # `edge_verdict` و`declared_weight` يبقيان في البطاقة فيُقرأ القياس.
        edge = edge_factor(self.strategy_id, tick.get("symbol"))
        declared_direction = direction
        ready = (
            status == "ok"
            and depth >= self.required_depth
            and confidence >= self.confidence_threshold
            and strength >= self.strength_threshold
            and (not self.directional or direction != 0.0)
        )
        # ⛔ ولا صفرَ من الحافّة: معاملٌ صفريٌّ (من ملفٍّ قديم أو تشغيلٍ
        #    لاحقٍ للأداة) يُقرأ «لا حكم» فيبقى الوزن المعلَن كما هو.
        weight = self.weight if not edge else self.weight * edge
        effective = weight * context_factor if ready else 0.0
        contract_state = STATE_READY if ready else STATE_NOT_READY
        return {
            "account_id": tick.get("account_id"),
            "broker": tick.get("broker"),
            "symbol": tick.get("symbol"),
            "timeframe": "tick",
            "period_start": tick.get("period_start"),
            "cycle_id": tick.get("cycle_id"),
            "source_timestamp": tick.get("source_timestamp", tick.get("timestamp")),
            "timestamp": tick.get("timestamp"),
            "sequence": state.sequence,
            "id": self.strategy_id,
            "strategy_id": self.strategy_id,
            "analysis_mode": "live_tick",
            "contract_version": 2,
            "status": status,
            "signal": signal,
            "direction": round(direction, 6),
            "score": round(direction, 6),
            "strength": round(strength, 6),
            "confidence": round(confidence, 6),
            "current_depth": round(depth, 6),
            "required_depth": round(self.required_depth, 6),
            "confidence_threshold": round(self.confidence_threshold, 6),
            "strength_threshold": round(self.strength_threshold, 6),
            "threshold": round(self.confidence_threshold, 6),
            "weight": round(weight, 6),
            "weight_applied": round(effective, 6),
            "ratio": round(weight, 6),
            # الصمت معلَن لا مخفيّ: وزنٌ صفرٌ هنا قياسٌ لا عطل.
            "declared_weight": round(self.weight, 6),
            "declared_direction": round(declared_direction, 6),
            "edge_factor": (None if edge is None else round(edge, 6)),
            "edge_verdict": ("unmeasured" if edge is None
                             else "no_edge" if edge == 0.0 else "edge"),
            "ready": ready,
            "analysis_state": contract_state,
            "state": contract_state,
            "context_factor": round(context_factor, 6),
            "quality": "good" if ready else "low",
            "warnings": [] if ready else ["STRATEGY_COMPONENT_NOT_READY"],
            "metadata": {
                "method": "descriptive_validated_tick",
                "depth_evidence": depth_parts,
                **(evidence or {}),
            },
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "invalid": self.invalid,
            "states": [
                {
                    "scope": list(scope),
                    "prices": list(s.prices),
                    "bids": list(s.bids),
                    "asks": list(s.asks),
                    "timestamps": list(s.timestamps),
                    "returns": list(s.returns),
                    "sequence": s.sequence,
                }
                for scope, s in self.states.items()
            ],
        }

    def restore(self, payload: Any) -> None:
        self.states = {}
        if (
            not isinstance(payload, dict)
            or payload.get("strategy_id") != self.strategy_id
        ):
            return
        self.invalid = max(0, int(payload.get("invalid", 0)))
        for row in payload.get("states") or []:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("scope"), list)
                or len(row["scope"]) != 3
            ):
                continue
            try:
                state = StrategicTickState()
                state.prices.extend(float(x) for x in row.get("prices", []))
                state.bids.extend(float(x) for x in row.get("bids", []))
                state.asks.extend(float(x) for x in row.get("asks", []))
                state.timestamps.extend(float(x) for x in row.get("timestamps", []))
                state.returns.extend(float(x) for x in row.get("returns", []))
                state.sequence = max(0, int(row.get("sequence", 0)))
                self.states[tuple(str(x) for x in row["scope"])] = state
            except (TypeError, ValueError):
                continue
