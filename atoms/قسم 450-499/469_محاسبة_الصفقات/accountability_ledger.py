"""469 — قراءة دفتر البطاقات (465) للقراءة فقط، واشتقاق أرقام كلّ صفقةٍ مغلقة.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): المالك يسأل «إذا خسر، عنده جواب حقيقيّ مفصّل ليش
خسرنا؟ وإذا ربح ليش ربح؟». والجواب مكتوبٌ أصلًا على البطاقة — يكتبه 465 و552 و563 — وهذه الوحدة
تقرؤه كما هو، لا تكتب حرفًا في الدفتر (`mode=ro`)، وتشتقّ منه أرقامًا حسابيّةً خالصة.

ما يُقرأ (أعمدة `cards` كما يكتبها `shared/trade_card.py`):
  صفقة = بطاقةٌ عليها ربحٌ محقَّق (`profit` يكتبه 563 عند النتيجة) — مغلقةً كانت أو منتهيةً بعده.
  `risk_amount` (552) مبلغ الخطر عند الوقف المرسَل للعقد كلّه ⟸ وحدة المخاطرة R = الربح ÷ هذا المبلغ.
  `peak_r`/`worst_r` (465) أقصى حركةٍ معنا وضدّنا بوحدة مخاطرة التحليل (من دخول البطاقة ووقفها).
  `body_json` (465 من الإعداد) الاستراتيجيّة التي بنتها وسببا الوقف والهدف كما كُتبا.
  `card_writes` بالحقل «حقيقة» — حقيقة كلّ قسمٍ باسمه لحظة الولادة (465 منذ ٢٠٢٦-١٠-٠٨).

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): حدٌّ مقيس على الدفتر الحيّ ويُعلَن لا يُخفى — 465 يُغلق
البطاقة عند **أوّل** نتيجة (`CLOSED` أو `PARTIAL`)، فالصفقة التي بلغت الهدف الأوّل تحمل بطاقتُها ربحَ
ثلث العقد وحده، وما جرى للثلثين بعده لا يصل البطاقة. لذلك تُحسب «حصّة العقد المسجّلة» حسابًا:
(الربح ÷ الخطر) ÷ (حركة الخروج ÷ مسافة الوقف) — واحدٌ تقريبًا = العقد كلّه، والثلث = الجزء الأوّل وحده.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any

from shared.owner_windows import owner_window
#: ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): الحالات الحيّة (بطاقةٌ لم تُغلق صفقتها بعد) من عقد البطاقة.
from shared.trade_card import LIVE_STATES

#: اسم حقل الحقيقة كما يكتبه 465 (`card_ledger_writers.stamp_opinions`) — بيانٌ في الدفتر لا معرّف.
FACT_FIELD = "حقيقة"
#: الجهة كما تُكتب على البطاقة ⟵ اسمها في الحمولة (كلمتا الدفتر ممنوعتان في الحمولة بعقد الحقائق).
SIDE_NAMES = {"buy": "long", "sell": "short"}
WINDOW_OUTSIDE = "outside"
STRATEGY_NONE = "none"
#: أثلاث المالك: الهدف الأوّل ثلث المسافة، والثاني ثلثاها، والثالث الهدف الكامل.
THIRDS = 3
#: هامشٌ عدديّ لا عيار — كي لا تسقط ١/٣ × ٣ إلى ما دون الواحد بخطأ الفاصلة العائمة.
_EPS = 1e-9
#: سماحُ تسمية موضع الخروج: ثلث مسافة الهدف ± هذا = الهدف الأوّل …، والتعادل ± هذا من وحدة الوقف —
#: وصفٌ للموضع لا حكم.
EXIT_TOLERANCE = 0.05
#: حصّة العقد لا تُحسب لخروجٍ أقرب من هذا إلى الدخول (بوحدة مسافة الوقف) — القسمة على شبه الصفر ضجيج.
SHARE_MIN_MOVE_R = 0.2
#: حصّةٌ دون هذا = البطاقة تحمل جزءًا من العقد وحده.
SHARE_FULL_FLOOR = 0.9
#: كلماتٌ ممنوعة في الحمولة (دليل «المعرفة أوّلًا» وعقد الحقائق ١٠-٠٧) — حقيقةٌ تحملها تُحجب وتُعدّ.
FORBIDDEN_WORDS = frozenset((
    "direction", "signal", "strength", "confidence", "weight", "score", "probability",
    "threshold", "depth", "readiness", "buy", "sell", "bullish", "bearish", "strong", "weak"))
#: مفاتيح لحظةٍ لا حقيقة — بداية شمعةٍ أو ختمُ وقت؛ تقسيمها أثلاثًا يقسم الزمن لا السوق.
_MOMENT_KEYS = frozenset(("period_start", "timestamp", "ts", "time", "at"))
_MOMENT_SUFFIXES = ("_at", "_ts", "_start", "_time")

# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): تُقرأ أيضًا البطاقات التي تحمل تذكرةً أو سمعت تأكيد
# تنفيذها (`563.filled`) ولو بلا ربح — فالبطاقة المالكة لتذكرةٍ قد تكون بلا ربحٍ عليها (كتب 563 أجزاءها على
# بطاقةٍ بعدها). والتأكيد يُقرأ بفهرس المفتاح من البطاقات المرسَلة وحدها (مقيس: 0.19 ث على 25,464 بطاقة).
_FILLED_SQL = ("SELECT card_no, value_json FROM card_writes WHERE card_no IN "
               "(SELECT card_no FROM cards WHERE dispatched_at IS NOT NULL) AND author = ? AND field = ?")
_TRADES_SQL = ("SELECT * FROM cards WHERE profit IS NOT NULL OR ticket IS NOT NULL OR card_no IN "
               "(SELECT card_no FROM card_writes WHERE card_no IN (SELECT card_no FROM cards "
               "WHERE dispatched_at IS NOT NULL) AND author = ? AND field = ?)")
FILLED_AUTHOR, FILLED_FIELD = "563", "filled"
# ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): مقيس على الدفتر الحيّ (7,926,824 صفّ كتابة) — الربط
# `JOIN` يمسح `card_writes` كلّه (23.6 ث باردًا، 1.3 ث دافئًا)، و`IN (…)` يبحث بفهرس المفتاح (0.1 ث).
_FACTS_SQL = ("SELECT card_no, author, value_json FROM card_writes "
              "WHERE card_no IN (SELECT card_no FROM cards WHERE profit IS NOT NULL OR ticket IS NOT NULL "
              "OR card_no IN (SELECT card_no FROM card_writes WHERE card_no IN (SELECT card_no FROM cards "
              "WHERE dispatched_at IS NOT NULL) AND author = ? AND field = ?)) AND field = ?")
_WORD = re.compile(r"[a-z]+")


class LedgerUnavailable(Exception):
    """الدفتر غائبٌ أو لا يُقرأ — يُعلَن سببه حقيقةً «غير متاح»، ولا تنهار الذرّة."""


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def real(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def is_clean(value: Any) -> bool:
    """لا كلمة ممنوعة (ولا جمعُها) في النصّ — بالكلمة الكاملة، فـ`buyside` اسمٌ لا جهة."""
    for word in _WORD.findall(text(value).lower()):
        if word in FORBIDDEN_WORDS or (word.endswith("s") and word[:-1] in FORBIDDEN_WORDS):
            return False
    return True


def read_ledger(path: str, timeout_s: float) -> dict[str, Any]:
    """يقرأ الصفقات المغلقة وحقائق ولادتها — للقراءة فقط، ويُنادى في خيط لا على الحلقة."""
    file = Path(path) if path else None
    if file is None or not file.is_file():
        raise LedgerUnavailable("الدفتر غير موجود: %s" % (path or "—"))
    try:
        connection = sqlite3.connect(file.resolve().as_uri() + "?mode=ro", uri=True,
                                     timeout=timeout_s)
    except sqlite3.Error as exc:
        raise LedgerUnavailable("تعذّر فتح الدفتر: %s" % exc) from exc
    filled_key = (FILLED_AUTHOR, FILLED_FIELD)
    try:
        cursor = connection.execute(_TRADES_SQL, filled_key)
        names = [column[0] for column in cursor.description]
        cards = [dict(zip(names, row)) for row in cursor.fetchall()]
        filled = connection.execute(_FILLED_SQL, filled_key).fetchall()
        facts: dict[int, dict[str, str]] = {}
        for card_no, author, raw in connection.execute(_FACTS_SQL, (*filled_key, FACT_FIELD)):
            try:
                value = json.loads(raw) if raw is not None else ""
            except (TypeError, ValueError):
                value = raw
            facts.setdefault(int(card_no), {})[text(author)] = text(value)
    except sqlite3.Error as exc:
        raise LedgerUnavailable("تعذّرت قراءة الدفتر: %s" % exc) from exc
    finally:
        connection.close()
    return {"cards": cards, "facts": facts, "filled_rows": filled}


def closed_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """البطاقات التي عليها ربحٌ وانتهت — صفقاتُ المحاسبة حين يغيب سجلّ الوسيط (كما كانت قبل ١٠-٠٩).

    ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصفقة صافيةً بأجزائها): البطاقة الحيّة صار عليها ربحٌ جارٍ (مفتوحة جزئيًّا)،
    فلا تُعدّ صفقةً مغلقة حتّى تنتهي."""
    return [card for card in cards if real(card.get("profit")) is not None
            and text(card.get("state")) not in LIVE_STATES]


def strategy_of(body: dict[str, Any]) -> str:
    """«المالك:النوع» من إعداد البطاقة (`410:LIQUIDITY_RAID`) — وبلا إعداد ⟸ `none`."""
    setup_id = text(body.get("setup_id"))
    owner = setup_id.split(":", 1)[0] if setup_id else ""
    owner = owner if owner.isdigit() else ""
    kind = text(body.get("setup_type"))
    if not kind or not is_clean(kind):
        kind = ""
    if not owner and not kind:
        return STRATEGY_NONE
    return "%s:%s" % (owner or "?", kind or "?")


def _body(card: dict[str, Any]) -> dict[str, Any]:
    try:
        body = json.loads(card.get("body_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return body if isinstance(body, dict) else {}


def thirds_reached(favorable_points: float | None, target_points: float | None) -> int | None:
    """أعلى ثلثٍ بلغته أقصى حركةٍ معنا من مسافة الهدف (0 = لم تبلغ الأوّل … 3 = الهدف الكامل)."""
    if favorable_points is None or not target_points or target_points <= 0:
        return None
    reach = favorable_points / target_points
    return max(0, min(THIRDS, int(math.floor(reach * THIRDS + _EPS))))


def excursion(card: dict[str, Any], sign: float | None) -> dict[str, Any]:
    """أقصى حركةٍ معنا وضدّنا ومسافة الهدف — على أساس ما أُرسل للوسيط إن وُجد، وإلّا على التحليل.

    ٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): 465 يقيس الذروة والحضيض من **دخول التحليل** وبمسافة
    **وقف التحليل**، والأثلاث (574) والخطر بالدولار (552) على **المرسَل**: سعر التنفيذ والوقف والهدف
    المرسَلين. ومقيس على الدفتر الحيّ (البطاقة 86468): وقف التحليل 182 نقطة والمرسَل 543، وهدف التحليل 612
    والمرسَل 3,136 — فـ«1.83R والهدف الأوّل» بالتحليل هي 0.53R ولا ثلث بالمرسَل. فالأساس المرسَل أوّلًا،
    والذروة تُنقل إليه بالحساب (سعرها = دخول التحليل ± نقاطها)، ويُعلَن الأساس مع الرقم.
    """
    entry = real(card.get("entry"))
    peak, worst = real(card.get("peak_points")), real(card.get("worst_points"))
    fill, sent_stop = real(card.get("fill_price")), real(card.get("sent_stop"))
    sent_target = real(card.get("sent_target"))
    if sign is not None and entry is not None and peak is not None and worst is not None \
            and fill is not None and sent_stop is not None and fill != sent_stop:
        risk = abs(fill - sent_stop)
        best = sign * (entry + sign * peak - fill)
        bad = sign * (entry + sign * worst - fill)
        span = abs(sent_target - fill) if sent_target is not None else None
        return {"basis": "sent", "favorable_r": max(0.0, best) / risk,
                "adverse_r": max(0.0, -bad) / risk,
                "thirds": thirds_reached(max(0.0, best), span)}
    peak_r, worst_r = real(card.get("peak_r")), real(card.get("worst_r"))
    target = real(card.get("target"))
    span = abs(target - entry) if target is not None and entry is not None else None
    return {"basis": "analysis" if peak_r is not None else "none",
            "favorable_r": None if peak_r is None else max(0.0, peak_r),
            "adverse_r": None if worst_r is None else max(0.0, -worst_r),
            "thirds": thirds_reached(None if peak is None else max(0.0, peak), span)}


def exit_kind(frac: float | None, move_r: float | None, stop_overshoot: Any) -> str:
    """موضع الخروج: أثلاث الهدف المرسَل بجزءٍ من مسافته، والتعادل بوحدة الوقف — و`stop` حين أبلغ الوسيط
    أنّه خرج على الوقف (563 يكتب `stop_overshoot` عند `SL` وحده)."""
    if stop_overshoot is not None:
        return "stop"
    if frac is None:
        return "unknown"
    if abs(frac - 1 / THIRDS) <= EXIT_TOLERANCE:
        return "first_third"
    if abs(frac - 2 / THIRDS) <= EXIT_TOLERANCE:
        return "second_third"
    if frac >= 1 - EXIT_TOLERANCE:
        return "target"
    if move_r is not None and abs(move_r) <= EXIT_TOLERANCE:
        return "breakeven"
    return "other"


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _r4(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def derive_trade(card: dict[str, Any]) -> dict[str, Any]:
    """أرقام صفقةٍ واحدة كما تقولها بطاقتها — حسابٌ لا تقدير، وما لا يُحسب يبقى `None`."""
    body = _body(card)
    side = text(card.get("side")).lower()
    sign = 1.0 if side == "buy" else -1.0 if side == "sell" else None
    profit, risk = real(card.get("profit")), real(card.get("risk_amount"))
    fill, exit_price = real(card.get("fill_price")), real(card.get("exit_price"))
    sent_stop, sent_target = real(card.get("sent_stop")), real(card.get("sent_target"))
    result_r = _ratio(profit, risk) if risk is not None and risk > 0 else None
    move = None if sign is None or fill is None or exit_price is None else sign * (exit_price - fill)
    exit_move_r = _ratio(move, abs(fill - sent_stop)) if (
        move is not None and sent_stop is not None) else None
    share = None
    if result_r is not None and exit_move_r is not None and abs(exit_move_r) >= SHARE_MIN_MOVE_R:
        share = result_r / exit_move_r
    frac = _ratio(move, abs(sent_target - fill)) if (
        move is not None and sent_target is not None) else None
    reach = excursion(card, sign)
    opened_at = real(card.get("opened_at"))
    closed_at = real(card.get("closed_at")) or real(card.get("updated_at"))
    window = owner_window(opened_at) if opened_at is not None else None
    return {
        "card_no": int(card.get("card_no") or 0), "symbol": text(card.get("symbol")).upper(),
        "state": text(card.get("state")), "side": SIDE_NAMES.get(side, ""),
        "opened_at": opened_at, "closed_at": closed_at,
        "strategy": strategy_of(body), "window": window or WINDOW_OUTSIDE,
        "profit_usd": profit, "risk_usd": risk, "result_r": _r4(result_r),
        "exit_move_r": _r4(exit_move_r), "recorded_share": _r4(share),
        "max_favorable_r": _r4(reach["favorable_r"]), "max_adverse_r": _r4(reach["adverse_r"]),
        "excursion_basis": reach["basis"], "thirds_reached": reach["thirds"],
        "exit_kind": exit_kind(frac, exit_move_r, card.get("stop_overshoot")),
        "exit_target_frac": _r4(frac),
        "entry": real(card.get("entry")), "stop": real(card.get("stop")),
        "target": real(card.get("target")), "fill_price": fill, "exit_price": exit_price,
        "sent_stop": sent_stop, "sent_target": sent_target, "rr": real(card.get("rr")),
        "stop_reason": text(body.get("invalidation_reason")),
        "target_reason": text(body.get("target_reason")),
    }


def _is_moment(key: str) -> bool:
    lowered = key.lower()
    return lowered in _MOMENT_KEYS or lowered.endswith(_MOMENT_SUFFIXES)


def parse_fact(raw: str) -> tuple[str, list[tuple[str, Any]], int]:
    """«الاسم · مفتاح=قيمة · …» ⟵ (الاسم، [(مفتاح، رقم أو نصّ)]، عدد ما حُجب لكلمةٍ ممنوعة)."""
    parts = [part.strip() for part in text(raw).split(" · ")]
    label = parts[0] if parts else ""
    pairs: list[tuple[str, Any]] = []
    withheld = 0
    for part in parts[1:]:
        key, sep, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key or _is_moment(key):
            continue
        if not is_clean(key) or not is_clean(value):
            withheld += 1
            continue
        number = real(value)
        pairs.append((key, number if number is not None else value))
    return label, pairs, withheld


def clean_fact_text(raw: str) -> tuple[str, int]:
    """نصّ الحقيقة كما خُتم، بلا ما يحمل كلمةً ممنوعة — للعرض على صفقةٍ بعينها."""
    label, pairs, withheld = parse_fact(raw)
    body = " · ".join("%s=%s" % (key, value) for key, value in pairs)
    return ("%s · %s" % (label, body) if body else label), withheld
