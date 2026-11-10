# -*- coding: utf-8 -*-
"""الخطوط الحمراء — قوانين المالك ٢٠٢٦-١٠-١٧ (أختام «nq» ثمّ «NQ» على الخطوات 6–9).

**كلّ أصلٍ مع بورصته وحدها، وخطّه الأحمر إغلاقها** (الخطوة 6): المؤشّرات الأمريكيّة مع نيويورك 09:30–16:00 بساعة
نيويورك («لا تداول مع أيّ بورصة أخرى أبدًا») · اليورو والجنيه مع لندن 08:00–16:30 بساعة لندن (= فرانكفورت؛ «10:00–18:30
فرانكفورت ولندن كلّ الأمور المتعلّقة بهالأمور») · وللعملات الأخرى بعملتها الأولى: الفرنك زيورخ · الأسترالي والنيوزيلنديّ
سيدني · الين طوكيو · الكنديّ تورونتو. **وما لم يُقرَّر له بعدُ (الذهب · البتكوين · غيرهما) على النافذة العامّة:** من
افتتاح سيدني 10:00 بساعة سيدني (الخطوة 7: «نبدأ من جلسة سيدني») إلى 16:00 بساعة نيويورك (ساعةٌ قبل إغلاق اليوم 17:00،
ختم ٢٥/١٠؛ وكانت 15:00). **أوّل ربع ساعة من نافذة الأصل لا دخول** (الخطوة 9). **والخبر الأحمر ±15 دقيقة لكلّ عملةٍ على
أصولها، والدولار على كلّ الرموز** (٢٣/١٠؛ وكان ±6 دقائق للدولار وحده) كما يعلنه التقويم 109.

**٢٣/١٠ (ورقة «خطوط حمراء» المختومة، وأمر المالك «غيّر الحيّ نفسه لا الورقة»):**
- القانون 23: السبت والأحد لا تداول لأيّ رمز، **ومعه البتكوين** — سقط استثناء «العطلة بتكوين وحده».
- القوانين 24–25: الخبر الأحمر لأيّ عملةٍ يحجب الأصول التي فيها عملته، وخبر الدولار يحجب كلّ الرموز؛ والنافذة 15 دقيقة قبل
  الخبر وبعده كما يعلنها التقويم 109 في `blocked_currencies` (العملات التي نافذتها قائمةٌ الآن). وحالةٌ قديمة بلا هذا الحقل
  تُقرأ كما كانت: حجبٌ لكلّ الرموز.

**٢٥/١٠ (ختم المالك «nq» على القانونين 17 و21):**
- القانون 21: «قاعدة وقت يكفي خليها تشتغل اخر ساعة بس ما تفتح صفقات جديدة بس هيك» — لا صفقة جديدة في الساعة الأخيرة من نافذة
  الأصل، فقط (`in_last_hour` في `entry_block`). سقط شرط «هل تكفي الحركة المتوقّعة للهدف قبل أقرب خطٍّ أحمر» كلّه، والمفتوح يكمل
  حتّى نهاية النافذة.
- القانون 17: «نافذة لا 23:00» — النافذة العامّة (الذهب والبتكوين) تنتهي قبل إغلاق اليوم في نيويورك بساعة (16:00) لا بساعتين.

**٢٦/١٠ (ختم المالك «nq اصلح» بعد فحص المشروع، القانونان 24–25):** التقويم المجهول لا يُقرأ «لا خبر». حالةٌ غائبة، أو
أقدم من دقيقتين، أو يقول فيها 109 إنّه لا يعرف (`known` غير صادقة، كأن ينقضي أفقه) — تمنع الدخول الجديد بسببٍ مسمّى
(`news_unknown` في `entry_block`). والمفتوح لا يُغلق بالجهل وحده: ذاك قرار المالك ولم يُحسم، فـ`red_line` كما كانت.

كلّ بورصةٍ بمنطقتها الزمنيّة من قاعدة المناطق (صيفها وشتاؤها آليّان) — لا رقم ساعاتٍ ثابت. وبلا القاعدة تُرجَع النافذة
العامّة القديمة بساعة الوسيط (03:00–22:00) للجميع، ولا يُعلَن ذلك بعدُ في شارةٍ ولا عدّاد (فحص ٢٦/١٠).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from shared.market_clock import broker_day_offset_s

try:
    from zoneinfo import ZoneInfo
except ImportError:  # noqa: BLE001
    ZoneInfo = None

SECONDS_PER_DAY = 86400
SECONDS_PER_MINUTE = 60
FIRST_MINUTES = 15
FIRST_SECONDS = FIRST_MINUTES * SECONDS_PER_MINUTE
CALENDAR_MAX_AGE_S = 120.0          # التقويم ينبض كلّ 30 ث؛ حالةٌ أقدم من دقيقتين لا يُحكم بها
CALENDAR_BLOCKED = "BLOCKED"
WEEKDAYS = 5                        # الإثنين–الجمعة بساعة البورصة

REASON_WINDOW = "OUTSIDE_TRADING_WINDOW"
REASON_NEWS = "NEWS_RED_LINE"
REASON_FIRST_MINUTES = "FIRST_15_MIN_OF_SESSION"
#: ٢٥/١٠ (القانون 21): الساعة الأخيرة من نافذة الأصل — لا صفقة جديدة، والمفتوح يكمل.
REASON_LAST_HOUR = "LAST_HOUR_OF_SESSION"
#: ٢٦/١٠ (القانونان 24–25): التقويم لا يعرف الأخبار الآن — لا دخول جديد، والمفتوح يكمل.
REASON_NEWS_UNKNOWN = "NEWS_CALENDAR_UNKNOWN"
LAST_HOUR_S = 3600

NEW_YORK, LONDON, ZURICH, SYDNEY, TOKYO, TORONTO = (
    "America/New_York", "Europe/London", "Europe/Zurich", "Australia/Sydney", "Asia/Tokyo", "America/Toronto")
#: الجلسة: (المنطقة · الافتتاح · الإغلاق) بساعة البورصة.
SESSIONS: dict[str, tuple[str, tuple[int, int], tuple[int, int]]] = {
    "NEW_YORK": (NEW_YORK, (9, 30), (16, 0)),
    "LONDON": (LONDON, (8, 0), (16, 30)),
    "ZURICH": (ZURICH, (9, 0), (17, 30)),
    "SYDNEY": (SYDNEY, (10, 0), (16, 0)),
    "TOKYO": (TOKYO, (9, 0), (15, 30)),
    "TORONTO": (TORONTO, (9, 30), (16, 0)),
}
SYMBOL_SESSION = {"USTEC": "NEW_YORK", "US30": "NEW_YORK", "US500": "NEW_YORK",
                  "EURUSD": "LONDON", "GBPUSD": "LONDON"}
CURRENCY_SESSION = {"EUR": "LONDON", "GBP": "LONDON", "CHF": "ZURICH", "AUD": "SYDNEY", "NZD": "SYDNEY",
                    "JPY": "TOKYO", "CAD": "TORONTO"}
GENERAL = "GENERAL"
GENERAL_OPEN = (SYDNEY, (10, 0))     # افتتاح سيدني
#: ٢٥/١٠ (القانون 17، «نافذة لا 23:00»): ساعةٌ قبل إغلاق اليوم 17:00 نيويورك — كانت 15:00 (ساعتين قبله).
GENERAL_CLOSE = (NEW_YORK, (16, 0))
_FALLBACK_OPEN_MIN, _FALLBACK_CLOSE_MIN = 3 * 60, 22 * 60   # ساعة الوسيط — بلا قاعدة المناطق فقط

_ZONES: dict[str, Any] = {}


def _zone(name: str):
    if ZoneInfo is None:
        return None
    if name not in _ZONES:
        try:
            _ZONES[name] = ZoneInfo(name)
        except Exception:  # noqa: BLE001
            _ZONES[name] = None
    return _ZONES[name]


def zones_available() -> bool:
    return _zone(NEW_YORK) is not None and _zone(SYDNEY) is not None


def session_of(symbol: Any) -> str:
    """اسم جلسة الأصل: من جدوله، أو بعملته الأولى إن كان زوج عملات، وإلّا النافذة العامّة."""
    s = str(symbol or "").strip().upper()
    if s in SYMBOL_SESSION:
        return SYMBOL_SESSION[s]
    if len(s) == 6 and s.isalpha() and s[:3] in CURRENCY_SESSION:
        return CURRENCY_SESSION[s[:3]]
    return GENERAL


def _last_at(epoch_s: float, zone: str, hm: tuple[int, int]) -> float:
    """آخر لحظةٍ ≤ اللحظة تكون فيها الساعة hm بساعة المنطقة."""
    local = datetime.fromtimestamp(epoch_s, _zone(zone))
    at = local.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    if at > local:
        at -= timedelta(days=1)
    return at.timestamp()


def owner_minute(epoch_s: float) -> int:
    """دقيقة اليوم بساعة الوسيط (نيويورك + 7) — للبديل بلا قاعدة المناطق."""
    t = float(epoch_s)
    return int(((t + broker_day_offset_s(t)) % SECONDS_PER_DAY) // SECONDS_PER_MINUTE)


def session_state(epoch_s: float, symbol: Any = None) -> tuple[bool, float | None]:
    """(هل نافذة الأصل مفتوحة الآن؟ · لحظة افتتاحها الأخير)."""
    t = float(epoch_s)
    if not zones_available():
        m = owner_minute(t)
        return _FALLBACK_OPEN_MIN <= m < _FALLBACK_CLOSE_MIN, None
    name = session_of(symbol)
    if name == GENERAL:
        opened = _last_at(t, GENERAL_OPEN[0], GENERAL_OPEN[1])
        closed = _last_at(t, GENERAL_CLOSE[0], GENERAL_CLOSE[1])
        # ١٧/١٠ (المالك بصورة اللوحة يوم السبت: «كيف الدهب يعمل واليوم عطلة؟»): النافذة العامّة كانت تُفتح كلّ يوم، والعطلة الأسبوعيّة
        # للذهب والعملات من إغلاق الجمعة إلى افتتاح الإثنين بسيدني. نافذةٌ افتُتحت يوم سبتٍ أو أحدٍ بسيدني مغلقة.
        # ٢٣/١٠ (القانون 23): والبتكوين معها — «في حسابات ممنوع عليها تداول أيّام الويك إند، لهيك خلّيه معهم».
        if opened > closed and weekend_open(opened):
            return False, None
        return opened > closed, opened
    zone, open_hm, close_hm = SESSIONS[name]
    local = datetime.fromtimestamp(t, _zone(zone))
    if local.weekday() >= WEEKDAYS:
        return False, None
    opened = local.replace(hour=open_hm[0], minute=open_hm[1], second=0, microsecond=0)
    closes = local.replace(hour=close_hm[0], minute=close_hm[1], second=0, microsecond=0)
    return opened <= local < closes, opened.timestamp()


#: ١٧/١٠: كان ما يتداول في العطلة الأسبوعيّة («العطلة بتكوين وحده»). ٢٣/١٠ (القانون 23): لا يُستثنى من العطلة بعد اليوم؛
#: بقي تعريفًا لمن يسأل «أهو عملةٌ رقميّة؟» لا بابًا للعطلة.
CRYPTO = ("BTCUSD", "ETHUSD")


def is_crypto(symbol: Any) -> bool:
    return str(symbol or "").strip().upper() in CRYPTO


def weekend_open(opened_epoch: float) -> bool:
    """هل افتُتحت النافذة العامّة يوم سبتٍ أو أحدٍ بساعة سيدني؟ (إذن هي داخل العطلة الأسبوعيّة)."""
    return datetime.fromtimestamp(opened_epoch, _zone(GENERAL_OPEN[0])).weekday() >= WEEKDAYS


def in_trading_window(epoch_s: float, symbol: Any = None) -> bool:
    return session_state(epoch_s, symbol)[0]


def in_first_minutes(epoch_s: float, symbol: Any = None) -> bool:
    inside, opened = session_state(epoch_s, symbol)
    return inside and opened is not None and float(epoch_s) - opened < FIRST_SECONDS


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


USD = "USD"
#: ٢٣/١٠ (القانون 24): عملات الأصل التي يحجبه خبرها. المؤشّرات الأمريكيّة الثلاثة بالدولار؛ وما كان ستّة أحرف فعملتاه نصفاه
#: (اليورو والدولار · الجنيه والدولار · الذهب والدولار · البتكوين والدولار). وما سوى ذلك بالدولار.
SYMBOL_CURRENCIES: dict[str, tuple[str, ...]] = {"USTEC": (USD,), "US30": (USD,), "US500": (USD,)}


def currencies_of(symbol: Any) -> tuple[str, ...]:
    s = str(symbol or "").strip().upper()
    if s in SYMBOL_CURRENCIES:
        return SYMBOL_CURRENCIES[s]
    if len(s) == 6 and s.isalpha():
        return (s[:3], s[3:])
    return (USD,)


def news_hits(currency: Any, symbol: Any = None) -> bool:
    """هل يحجب خبرٌ أحمر لهذه العملة هذا الأصل؟ — الدولار يحجب كلّ الرموز (١٧/١٠)، وغيره أصولَ عملته وحدها (٢٣/١٠).
    وبلا رمز (حالةٌ عامّة للعرض) كلّ خبرٍ حاجبٍ يحجب."""
    cur = str(currency or "").strip().upper()
    if symbol is None or cur == USD:
        return True
    return cur in currencies_of(symbol)


def news_blocked(calendar_state: Any, epoch_s: float, max_age_s: float = CALENDAR_MAX_AGE_S, symbol: Any = None) -> bool:
    """هل هذا الأصل داخل نافذة خبرٍ أحمر لعملةٍ فيه؟ — حالة 109 الحديثة وحدها؛ القديمة أو الغائبة لا تحجب (وتُعدّ عند القارئ).
    ٢٣/١٠: من `blocked_currencies` إن حملته الحالة؛ وحالةٌ بلا هذا الحقل (109 قبل 3.12.0) تحجب كلّ الرموز كما كانت."""
    if not isinstance(calendar_state, dict):
        return False
    stamp = _num(calendar_state.get("utc"))
    if stamp is None or abs(float(epoch_s) - stamp) > max_age_s:
        return False
    blocked = calendar_state.get("blocked_currencies")
    if isinstance(blocked, list):
        return any(news_hits(currency, symbol) for currency in blocked)
    return calendar_state.get("in_event_window") is True or str(calendar_state.get("status") or "") == CALENDAR_BLOCKED


def news_unknown(calendar_state: Any, epoch_s: float, max_age_s: float = CALENDAR_MAX_AGE_S) -> bool:
    """٢٦/١٠: هل يجهل التقويم الأخبار الآن؟ — لا حالة، أو طابعها غائب أو أقدم من الحدّ، أو `known` فيها غير صادقة.
    `news_blocked` تقرأ القائمة المحجوبة وحدها، والقائمة الفارغة في هذه الأحوال كانت تُقرأ «لا خبر»."""
    if not isinstance(calendar_state, dict):
        return True
    stamp = _num(calendar_state.get("utc"))
    if stamp is None or abs(float(epoch_s) - stamp) > max_age_s:
        return True
    return calendar_state.get("known") is not True


def red_line(epoch_s: float, calendar_state: Any = None, symbol: Any = None) -> str | None:
    """خطٌّ أحمر يُغلق عنده كلّ مفتوح: خارج نافذة الأصل، أو نافذة خبرٍ أحمر لعملةٍ فيه. وإلّا لا شيء."""
    if not in_trading_window(epoch_s, symbol):
        return REASON_WINDOW
    if news_blocked(calendar_state, epoch_s, symbol=symbol):
        return REASON_NEWS
    return None


def seconds_to_window_close(epoch_s: float, symbol: Any = None) -> float | None:
    """الثواني حتّى إغلاق نافذة الأصل وحده (بلا الأخبار). لا شيء إن كان خارج النافذة أو بلا قاعدة المناطق."""
    t = float(epoch_s)
    if not zones_available():
        return None
    inside, _ = session_state(t, symbol)
    if not inside:
        return None
    name = session_of(symbol)
    if name == GENERAL:
        zone, hm = GENERAL_CLOSE
        local = datetime.fromtimestamp(t, _zone(zone))
        close = local.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if close <= local:
            close += timedelta(days=1)
        return close.timestamp() - t
    zone, _, close_hm = SESSIONS[name]
    local = datetime.fromtimestamp(t, _zone(zone))
    return local.replace(hour=close_hm[0], minute=close_hm[1], second=0, microsecond=0).timestamp() - t


def in_last_hour(epoch_s: float, symbol: Any = None) -> bool:
    """٢٥/١٠ (القانون 21): داخل الساعة الأخيرة من نافذة الأصل — لا صفقة جديدة فيها، والمفتوح يكمل حتّى الإغلاق."""
    left = seconds_to_window_close(epoch_s, symbol)
    return left is not None and left <= LAST_HOUR_S


def seconds_to_red_line(epoch_s: float, symbol: Any = None, calendar_state: Any = None) -> float | None:
    """الثواني حتّى أقرب خطٍّ أحمر للأصل: إغلاق نافذته، أو بداية نافذة الخبر الحاجب القادم (من 109). لا شيء إن كان خارج النافذة
    أو بلا قاعدة المناطق. (كان قانون الوقت الكافي يقرؤها حتّى ٢٥/١٠؛ وأداة القياس تقرؤها لإغلاق الصفقة عند الخطّ.)"""
    t = float(epoch_s)
    left = seconds_to_window_close(t, symbol)
    if left is None:
        return None
    if isinstance(calendar_state, dict):
        stamp = _num(calendar_state.get("utc"))
        if stamp is not None and abs(t - stamp) <= CALENDAR_MAX_AGE_S:
            for event in calendar_state.get("next_blocking") or []:
                # ٢٣/١٠: خبر عملةٍ ليست في الأصل لا يقرّب خطّه (والدولار يقرّب خطّ كلّ الرموز).
                if isinstance(event, dict) and "currency" in event and not news_hits(event.get("currency"), symbol):
                    continue
                start = _num(event.get("red_line_from")) if isinstance(event, dict) else None
                if start is not None and start > t:
                    left = min(left, start - t)
    return left


def entry_block(epoch_s: float, calendar_state: Any = None, symbol: Any = None) -> str | None:
    """ما يمنع الدخول: الخطّ الأحمر، ثمّ جهل التقويم بالأخبار (٢٦/١٠)، ثمّ أوّل ربع ساعة من نافذة الأصل، ثمّ ساعتها
    الأخيرة (٢٥/١٠، القانون 21)."""
    line = red_line(epoch_s, calendar_state, symbol)
    if line:
        return line
    if news_unknown(calendar_state, epoch_s):
        return REASON_NEWS_UNKNOWN
    if in_first_minutes(epoch_s, symbol):
        return REASON_FIRST_MINUTES
    if in_last_hour(epoch_s, symbol):
        return REASON_LAST_HOUR
    return None
