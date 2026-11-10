# -*- coding: utf-8 -*-
"""حدود الحساب — القوانين 7–10 من ورقة «خطوط حمراء» المختومة (ختم المالك «NQ» ٢٣/١٠).

**المعادلة الواحدة للحيّ ولأداة القياس** (القانون 7: «القياس يعمل على حسابٍ افتراضيّ بالمعادلة نفسها والحدود نفسها»):
- مخاطرة الصفقة **ثابتة لا تراكميّة** = نسبة الزوج × الرصيد الابتدائيّ الذي يكتبه المالك بيده («الثابت، ما بدها تراكميّ»).
- حدّ الزوج اليوميّ، والحدّ اليوميّ الشامل، والتراجع الكلّيّ: نسبٌ من **الرصيد الابتدائيّ** نفسه، لا من الرصيد الحاليّ ولا من أعلاه.
- الخسارة اليوميّة تُقاس من **الأعلى** بين رصيد إغلاق الأمس وحقوق بداية اليوم، كما تحسبها الجهة المموِّلة، واليوم يبدأ
  00:00 بساعة المالك (تركيا +3 ثابتة).
- التراجع الكلّيّ: يقف التداول كلّه حين تبلغ الحقوق مع المفتوح الرصيدَ الابتدائيّ ناقصًا نسبته (10,000 و8٪ ⟸ 9,200).

القيم الأولى (قرار المالك ٢٣/١٠: «أرقام أمثلتي قيمًا أولى»): الرصيد الابتدائيّ 10,000 · مخاطرة الصفقة لكلّ زوج 0.50٪ ·
حدّ كلّ زوج اليوميّ 1.5٪ · الحدّ اليوميّ الشامل 4٪ · التراجع الكلّيّ 8٪. ويغيّرها المالك بيده من صفحة «التحكّم».
"""
from __future__ import annotations

import math
from typing import Any, Iterable

PERCENT = 100.0
DAY_S = 86400
TURKEY_OFFSET_S = 3 * 3600          # ساعة المالك = تركيا +3 ثابتة («ساعة المالك = تركيا +3 ثابتة»)

INITIAL_BALANCE = "initial_balance"
PAIR_RISK_PCT = "pair_risk_pct"     # لكلّ زوجٍ لم يُكتب له رقمه
PAIR_DAILY_PCT = "pair_daily_pct"
DAILY_PCT = "daily_pct"
TOTAL_PCT = "total_pct"
PAIRS = "pairs"
RISK_PCT = "risk_pct"               # داخل سطر الزوج
DAY_PCT = "daily_pct"               # داخل سطر الزوج

DEFAULTS: dict[str, float] = {INITIAL_BALANCE: 10000.0, PAIR_RISK_PCT: 0.50, PAIR_DAILY_PCT: 1.5,
                              DAILY_PCT: 4.0, TOTAL_PCT: 8.0}
#: الرموز التي تتداولها المنظومة — لعرض مخاطرة صفقة كلٍّ منها في الحالة واللوحة.
TRADED = ("USTEC", "US30", "US500", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")
#: أسباب المنع والإغلاق — تنشرها ذرّة حدود الحساب 509 وتردّ بها بوّابة الدخول 555.
REASON_TOTAL = "TOTAL_DRAWDOWN_LIMIT"
REASON_DAILY = "DAILY_LOSS_LIMIT"
REASON_PAIR = "PAIR_DAILY_LIMIT"
REASON_UNKNOWN = "ACCOUNT_LIMITS_UNKNOWN"
STATE_MAX_AGE_S = 120.0             # الحالة تُنشر كلّ 30 ث على الأقلّ؛ أقدم من دقيقتين لا يُحكم بها
GLOBAL_KEYS = tuple(DEFAULTS)
PAIR_KEYS = (RISK_PCT, DAY_PCT)


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _valid(key: str, value: float | None) -> bool:
    if value is None:
        return False
    if key == INITIAL_BALANCE:
        return value > 0.0
    return 0.0 < value <= PERCENT


def normalize(raw: Any = None) -> dict[str, Any]:
    """الإعداد كاملًا: القيم الأولى تحت ما كتبه المالك، وما خرج عن حدّه لا يُقرأ."""
    out: dict[str, Any] = dict(DEFAULTS)
    out[PAIRS] = {}
    if not isinstance(raw, dict):
        return out
    for key in GLOBAL_KEYS:
        value = _num(raw.get(key))
        if _valid(key, value):
            out[key] = value
    pairs = raw.get(PAIRS)
    if isinstance(pairs, dict):
        for symbol, row in pairs.items():
            name = str(symbol or "").strip().upper()
            if not name or not isinstance(row, dict):
                continue
            kept = {k: _num(row.get(k)) for k in PAIR_KEYS if _valid(k, _num(row.get(k)))}
            if kept:
                out[PAIRS][name] = kept
    return out


def merge(current: Any, update: Any) -> tuple[dict[str, Any] | None, str]:
    """تعديل المالك على الإعداد القائم. قيمةٌ واحدة خاطئة تُرفض بالتعديل كلّه ويبقى القديم (الدستور م14)."""
    if not isinstance(update, dict):
        return None, "NOT_A_MAPPING"
    out = normalize(current)
    out[PAIRS] = {s: dict(v) for s, v in out[PAIRS].items()}
    for key in GLOBAL_KEYS:
        if key in update:
            value = _num(update[key])
            if not _valid(key, value):
                return None, "BAD_" + key.upper()
            out[key] = value
    pairs = update.get(PAIRS)
    if pairs is not None:
        if not isinstance(pairs, dict):
            return None, "BAD_PAIRS"
        for symbol, row in pairs.items():
            name = str(symbol or "").strip().upper()
            if not name or not isinstance(row, dict):
                return None, "BAD_PAIR"
            mine = dict(out[PAIRS].get(name, {}))
            for key in PAIR_KEYS:
                if key in row:
                    value = _num(row[key])
                    if not _valid(key, value):
                        return None, "BAD_PAIR_" + key.upper()
                    mine[key] = value
            out[PAIRS][name] = mine
    return out, ""


def _full(settings: Any) -> dict[str, Any]:
    """الإعداد كما هو إن كان كاملًا (ناتج `normalize` أو `merge`)، وإلّا يُكمَّل."""
    if isinstance(settings, dict) and all(k in settings for k in GLOBAL_KEYS) and isinstance(settings.get(PAIRS), dict):
        return settings
    return normalize(settings)


def pair_pcts(settings: Any, symbol: Any) -> tuple[float, float]:
    """(مخاطرة الصفقة ٪ · حدّ الزوج اليوميّ ٪) لهذا الزوج."""
    s = _full(settings)
    row = s[PAIRS].get(str(symbol or "").strip().upper(), {})
    return float(row.get(RISK_PCT, s[PAIR_RISK_PCT])), float(row.get(DAY_PCT, s[PAIR_DAILY_PCT]))


def _initial(settings: Any) -> float:
    return float(_full(settings)[INITIAL_BALANCE])


def trade_risk(settings: Any, symbol: Any) -> float:
    """مخاطرة الصفقة بالمال: نسبة الزوج × الرصيد الابتدائيّ — ثابتة مهما صعد الرصيد أو نزل."""
    return _initial(settings) * pair_pcts(settings, symbol)[0] / PERCENT


def pair_daily_limit(settings: Any, symbol: Any) -> float:
    return _initial(settings) * pair_pcts(settings, symbol)[1] / PERCENT


def daily_limit(settings: Any) -> float:
    s = _full(settings)
    return float(s[INITIAL_BALANCE]) * float(s[DAILY_PCT]) / PERCENT


def total_floor(settings: Any) -> float:
    """الحقوق التي يقف عندها كلّ شيء: الرصيد الابتدائيّ ناقصًا نسبة التراجع الكلّيّ."""
    s = _full(settings)
    return float(s[INITIAL_BALANCE]) * (1.0 - float(s[TOTAL_PCT]) / PERCENT)


def turkey_day(epoch_s: float) -> int:
    """رقم اليوم بساعة المالك — يتبدّل عند 00:00 تركيا."""
    return int((float(epoch_s) + TURKEY_OFFSET_S) // DAY_S)


def day_base(prev_close_balance: Any, day_start_equity: Any) -> float | None:
    """أساس الخسارة اليوميّة: الأعلى بين رصيد إغلاق الأمس وحقوق بداية اليوم."""
    values = [v for v in (_num(prev_close_balance), _num(day_start_equity)) if v is not None and v > 0.0]
    return max(values) if values else None


def entry_block(state: Any, account: Any, symbol: Any, now: float) -> tuple[str, dict[str, Any]]:
    """ما يمنع الدخول من حدود الحساب، أو ("", {}). حالةٌ غائبة أو قديمة أو حسابٌ لم تُعرف أرقامه يمنع —
    الجهل بالحساب ليس إذنًا بالدخول."""
    if not isinstance(state, dict):
        return REASON_UNKNOWN, {"why": "NO_STATE"}
    stamp = _num(state.get("official_time"))
    if stamp is None or abs(float(now) - stamp) > STATE_MAX_AGE_S:
        return REASON_UNKNOWN, {"why": "STALE_STATE", "official_time": stamp}
    view = (state.get("accounts") or {}).get(str(account or "").strip())
    if not isinstance(view, dict) or view.get("known") is not True:
        return REASON_UNKNOWN, {"why": "ACCOUNT_NOT_KNOWN"}
    if view.get("total_blocked"):
        return REASON_TOTAL, {"equity": view.get("equity"), "floor": view.get("floor")}
    if view.get("daily_blocked"):
        return REASON_DAILY, {"day_loss": view.get("day_loss"), "daily_limit": view.get("daily_limit")}
    name = str(symbol or "").strip().upper()
    if name in (view.get("blocked_pairs") or []):
        return REASON_PAIR, {"pair_loss": (view.get("pair_loss") or {}).get(name),
                             "pair_limit": (view.get("pair_limit") or {}).get(name)}
    return "", {}


def simulate(trades: Iterable[tuple[float, str, float]], settings: Any = None) -> dict[str, Any]:
    """القياس على حسابٍ افتراضيّ بالمعادلة نفسها والحدود نفسها — ويُعدّ كم مرّة كان الحساب سيسقط.

    `trades`: (لحظة الإغلاق · الرمز · النتيجة بوحدات المخاطرة). المال = النتيجة × مخاطرة الصفقة الثابتة.
    تقريبٌ معلن: الصفقة تُحسب بنتيجتها لحظة إغلاقها (المفتوح بين الصفقات لا يُرى)، وما يُغلق بعد بلوغ حدٍّ في يومه
    يُسقط من الحساب كأنّ الحدّ منعه. وحين يبلغ التراجع الكلّيّ يُعدّ سقوطًا ويبدأ حسابٌ جديد بالرصيد الابتدائيّ.
    """
    s = normalize(settings)
    initial = s[INITIAL_BALANCE]
    floor = total_floor(s)
    day_cap = daily_limit(s)
    balance = initial
    day = None
    base = initial
    pair_loss: dict[str, float] = {}
    stopped_pairs: set[str] = set()
    day_stopped = False
    out = {"initial_balance": initial, "taken": 0, "skipped": 0, "daily_stops": 0, "pair_stops": 0,
           "account_falls": 0, "fall_days": [], "max_day_loss": 0.0, "lowest_equity": initial, "net": 0.0}
    for moment, symbol, r in sorted(trades, key=lambda t: t[0]):
        today = turkey_day(moment)
        if today != day:
            day, base, pair_loss, stopped_pairs, day_stopped = today, balance, {}, set(), False
        name = str(symbol or "").strip().upper()
        if day_stopped or name in stopped_pairs:
            out["skipped"] += 1
            continue
        money = float(r) * trade_risk(s, name)
        balance += money
        out["net"] += money
        out["taken"] += 1
        out["lowest_equity"] = min(out["lowest_equity"], balance)
        pair_loss[name] = pair_loss.get(name, 0.0) - money
        loss = base - balance
        out["max_day_loss"] = max(out["max_day_loss"], loss)
        if balance <= floor:
            out["account_falls"] += 1
            out["fall_days"].append(today * DAY_S - TURKEY_OFFSET_S)
            balance, base, day_stopped = initial, initial, True
            continue
        if loss >= day_cap:
            out["daily_stops"] += 1
            day_stopped = True
        elif pair_loss[name] >= pair_daily_limit(s, name):
            out["pair_stops"] += 1
            stopped_pairs.add(name)
    out["final_balance"] = round(balance, 2)
    out["net"] = round(out["net"], 2)
    out["max_day_loss"] = round(out["max_day_loss"], 2)
    out["lowest_equity"] = round(out["lowest_equity"], 2)
    return out
