# -*- coding: utf-8 -*-
"""الوقف والهدف من بنية الفريمات — أمر المالك بختم «Nq» ٢٠٢٦-٠٩-٢٨.

كلام المالك، وقد أمر به أربع مرّات (٠٥ · ١٩ · ٢٢ · ٢٧ أيلول) قبل أن يُبنى:
«نحلل يومي و4 ساعات و ساعة ناخد منها وننزل… بدنا ناخد ادق ستوب واكبر هدف» ·
«هدف صفقة لا يقل عن 1/3 وفوق يعني هدف ممكن 1/15. 1/30 اذا تحليل جيد» ·
«اذا تحت 1/3 مرفوضة» · ثمّ «ابنيهم وثبتهم بل ورق» و«Nq».

**الصفقة تبقى من السلسلة كلّها** — والشكل المرفوض ١٩ أيلول (ذرّةٌ جانبيّة تفتح
صفقاتها بنفسها) لا يُبنى هنا:
  · الدخول      من الاستراتيجيّة نفسها (٤٠٥ · ٤٠٦ · ٤١٠) كما كان.
  · الإذن       من قسم التحليل: اتّجاه فريم الساعة في بطاقة ١٦٦ البطيئة.
  · الوقف       خلف آخر قاعٍ (للشراء) أو قمّةٍ (للبيع) مؤكَّدة على الربع ساعة،
                زائدَ كلفة العبور المقيسة (المئين الثمانون).
  · الهدف       **أبعد** قمّةٍ/قاعٍ مؤكَّد على الساعة أو 4س أو اليوم تبلغ نسبتُه 1:3
                **بعد الكلفة** (٢٠٢٦-١٠-٠٥ بختم المالك «nq اعتمدناها» على «أكبر هدف» — كان
                الأقرب). والمستويات التي في الطريق إليه (`exit_levels`) يُدار عليها الخروج
                في ٥٧٤: ثلثٌ على الأوّل ونصف الباقي على الثاني، والباقي إلى الهدف بوقفٍ
                يتبع قمم/قيعان الربع ساعة. وما لا مستوى له بهذه النسبة **يُرفض** — لا يُمطّ
                هدفٌ ولا يُخترع مستوى. و1:15 و1:30 تؤخذ حين تعطيها البنية، ولا تُصنع.
  · والقمم والقيعان من ٢٠١ (`structure.levels.state`): شمعةٌ أعلى/أدنى من
    الشمعتين قبلها والشمعتين بعدها، مؤكَّدةٌ بعد إغلاق الثانية — بلا نظرٍ في المستقبل.

**القياس الذي بُني عليه — قواعد الحيّ نفسها** (ورقة الخطوة الثالثة، § القياس
بقواعد الحيّ): صفقات النظام الحقيقيّة ٠٥⟶٢٧ أيلول على البتكوين والذهب، الدخول
نفسه، والكلفة كاملة، وشموع 4س ويوم مسلولةٌ على ساعة UTC كما يبنيها ١٠٣:

    عمق التاريخ   الصفقات   R للصفقة   النصفان بالزمن
    4 أيّام        186      +0.255     +0.15 | +0.36
    10 أيّام       212      +0.345     +0.23 | +0.46
    23 يومًا       217      +0.321     +0.23 | +0.41
    كلّه           257      +0.294     +0.32 | +0.27
    (والأصل الذي يُستبدل: −0.37R للصفقة.)

⛔ **لماذا لا «4س/يوم وحدهما حين يتّفق الفريمان»** كما كُتب في المقترح الأوّل:
قِيس بقواعد الحيّ فانقلب على البتكوين حين يقصر التاريخ (23 يومًا: −0.40R) —
المنصّة تحفظ أيّامًا من الأسعار لا سنين، فالمستوى الكبير الأقرب غائبٌ والهدف يبتعد
إلى 1:8 فلا يُبلغ. فالإذن من الساعة، والأهداف من الفريمات الثلاثة، والنسبة 1:3
حدٌّ أدنى لا سقف.

⛔ **ميتاتريدر ليس مصدرًا هنا** (حكم المالك ٢٠٢٦-٠٩-١٦): المستويات من شموع
سي‑تريدر التي يبنيها ١٠٣ حيًّا، والبذرة الأولى من مخزن تِكّاتها — لا من الوسيط.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from shared.trade_setup import net_ratio, runtime_var_file

#: الحدثان اللذان يُقرأ منهما — القمم والقيعان من البنية، والإذن من التحليل.
LADDER_EVENT = "structure.levels.state"
FRAMES_EVENT = "analysis.slow.state"

#: الرمزان اللذان ثبت فيهما القياس في نصفَي المدّة كليهما. والباقي على سلوكه حتّى
#: تكفي عيّنته (ناسداك 9 صفقات · داو وإس‌آند‌بي أقلّ) — لا يُعمَّم بلا قياس.
#: ٢٠٢٦-١٠-٠٦ (تفويض المالك «NQ صلاحية كاملة» — قياس الناسداك): `QUANT_NQ_STRUCTURE_SYMBOLS` يغيّرها
#: في عمليّة الاختبار التاريخيّ وحدها (`backtest/calibration_loop` يمرّره لتجربته) لتُقاس رموزٌ أخرى قبل
#: أن تُعتمد. الحيّ لا يضبطه.
#: ٢٠٢٦-١٠-٠٦ — **الناسداك دخل**: بسلوكه السابق صفر صفقات (الحيّ منذ ١٠-٠٢، والاختبار أسبوعًا كاملًا:
#: كلّ إعدادٍ «وقف أضيق من 10 ن.أ» أو «نسبة < 3»). وبالوقف والهدف البنيويّين على تِكّات سي‑تريدر
#: (مدموجة كلّ ثانية، 5 شرائح يوميّة): أسبوع 09-28 +171.46$ (8 صفقات، معامل 1.36) وأسبوع 09-21 خارج
#: العيّنة +340.37$ (4، معامل 2.83). عيّنةٌ صغيرة معلَنة، والبديل لا تداول، والخسارة ~1R.
SYMBOLS = frozenset(s.strip().upper() for s in os.environ.get(
    "QUANT_NQ_STRUCTURE_SYMBOLS", "BTCUSD,XAUUSD,USTEC").split(",") if s.strip())

STOP_FRAME = "15m"
#: ٢٠٢٦-١٠-٠٦ 15:4x — **وقف الناسداك وتتبّعه على الخمس دقائق** بختم المالك «NQ» على شارة صفقة 15:30:
#: «ستوب كبير وهدف مافي» — وقف 138 نقطة خلف قاع الربع ساعة، فصار هدف 9R على 1,230 نقطة. وأمره قبلها:
#: «لازم يداول على فريم دقيقة و5 مو يحط ستوب خلف اخر قاع شمعة شهر». `QUANT_NQ_STOP_FRAME` «رمز:فريم».
#: وسلّمٌ لم تصله بعدُ قمم/قيعان الخمس دقائق (أوّل 25 دقيقة بعد بذرةٍ بلا خمس دقائق) يعود إلى الربع ساعة.
STOP_FRAME_BY_SYMBOL: dict[str, str] = {}
for _pair in os.environ.get("QUANT_NQ_STOP_FRAME", "USTEC:5m").split(","):
    _name, _sep, _frame = _pair.partition(":")
    if _sep and _name.strip() and _frame.strip() in ("5m", "15m"):
        STOP_FRAME_BY_SYMBOL[_name.strip().upper()] = _frame.strip()
#: ٢٠٢٦-١٠-٠٧ 16:0x — **الهدف من الساعة والأربع ساعات، لا اليوميّ** بختم المالك «nq» بعد قوله «دخول على فريم 5
#: دقايق وهدف على فريم يومي هاد عقل؟» (بيع ناسداك هدفه 22,782.90 = −27٪، وبيع بتكوين هدفه 57,693 = −33٪): الأثلاث تُحسب
#: من مسافة الهدف، فهدفٌ يوميّ بعيد يجعل الهدف الأوّل بعيدًا لا يُبلغ. والحدّ 1:3 فأكثر بلا سقف كما أمر.
#: `QUANT_NQ_TARGET_FRAMES` يغيّرها للقياس. ومنطقة «بلا مستوى سابق» تُعرف على الساعة و4س **واليوم** (`DISCOVERY_FRAMES`).
TARGET_FRAMES = tuple(f.strip() for f in os.environ.get("QUANT_NQ_TARGET_FRAMES", "1h,4h").split(",")
                      if f.strip() in ("15m", "1h", "4h", "1d"))
DISCOVERY_FRAMES = ("1h", "4h", "1d")
#: ٢٠٢٦-١٠-٠٧ 16:1x — **الهدف أقرب مستوىً يعطي 1:3 فأكثر** بختم المالك «nq» على الخيار (ب): «أقرب مستوى يعطي ٣ أضعاف
#: فأكثر: الهدف الأوّل قريب، نحو ضعف المخاطرة». كان «أبعد مستوى» (٠٥-١٠ «أكبر هدف»): بيع بتكوين 83,397.8 فأبعد قاعٍ
#: على 4س 74,886.86 = 23R، فالهدف الأوّل من الأثلاث 7.7R لا يُبلغ. وفي قياس السنتين على الناسداك (دخول 5د، وقف أو
#: هدف): الأقرب −0.10R للصفقة والأبعد −0.23R. وفي «منطقة بلا مستوى سابق» الهدف 3R وحده. `QUANT_NQ_TARGET_PICK=far` للقياس.
TARGET_PICK = "far" if os.environ.get("QUANT_NQ_TARGET_PICK", "near").strip().lower() == "far" else "near"
GATE_FRAME = "1h"
FRAME_SECONDS = {"5m": 300.0, "15m": 900.0, "1h": 3600.0, "4h": 14400.0, "1d": 86400.0}
#: بطاقة الفريم حيّةٌ ما دام عمرها ≤ ثلاث شمعاتٍ منه — القاعدة نفسها في ١٦٦.
ALIVE_BARS = 3.0
#: حدّ الجانبيّ في اتّجاه الفريم — `SIDEWAYS_SCORE` في ١٦٦ نفسه.
SIDEWAYS = 5.0
#: حكم المالك: «اذا تحت 1/3 مرفوضة» — بعد الكلفة، كما في ٤٠٥/٤٠٦/٤١٠.
MIN_NET_RATIO = 3.0
#: أعمق ما يُقرأ من كلّ جهة — الوقف من أحدث مئة قاعٍ على الربع ساعة، والهدف من
#: أحدث مئتين على كلّ فريمٍ كبير (القياس استعمل 50 و400؛ والمنصّة لا تحفظ أكثر).
DEPTH = {"5m": 100, "15m": 100, "1h": 200, "4h": 200, "1d": 200}

#: بذرةُ السلّم الأولى — شموعٌ مغلقة من تِكّات سي‑تريدر المخزَّنة، تُقرأ مرّةً عند
#: الإقلاع إن لم تكن للذرّة لقطة. لا تُكتب من هنا أبدًا.
#: ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): من جذر التشغيل المعلَن لا من مسارٍ محفور —
#: كانت الفحوص والإعادة تبذر سلّمها من بذرة المنصّة الحيّة (`trade_setup.runtime_var_file`).
SEED_PATH = runtime_var_file("telemetry", "structure_ladder_seed.json")

# أسباب الرفض — كلٌّ باسمه، فيُقرأ في شارة الاستراتيجيّة لماذا لم يُنشر إعداد.
#: ٢٠٢٦-١٠-٠٦ (تفويض المالك «NQ صلاحية كاملة») — إذن الاتّجاه اليوميّ، **مطفأ افتراضًا**:
#: `QUANT_NQ_TREND_GATE=20` (طول المتوسّط) يشغّله في عمليّة الاختبار التاريخيّ لقياسه. الشراء حين إغلاق
#: آخر يومٍ مغلق فوق متوسّط آخر N إغلاقًا، والبيع تحته. السند: 39,427 إعدادًا حيًّا (09-23→10-06) مقيَّمةً
#: واحدًا واحدًا على شموع الدقيقة (3R أو الوقف): البتكوين الموافق +0.39R (9/12 يومًا موجبًا) والمخالف
#: 0.00R؛ الذهب الموافق +0.19R (6/9) والمخالف −0.10R. والإغلاقات من 201 (`daily_closes`).
#: ٢٠٢٦-١٠-٠٦ 13:45 — **يعمل على الذهب حيًّا** بأمر المالك وختمه «ابنيها nq» بعد أن قِيس سبب غياب صفقات
#: الذهب: 95 من ~100 قرار «محايد» لأنّ 406 تقول شراء و410 تقول بيع معًا فيتعادل المجموع. الإذن يُبقي
#: الموافق لاتّجاه اليوم ويُسقط المعاكس فيزول التعارض. سنده على الذهب: الإعدادات الحيّة الموافق +0.19R
#: والمعاكس −0.10R؛ وصفقات الاختبار المعاكس −542$ في أسبوعين والموافق ≈ تعادل.
TREND_GATE_N = int(os.environ.get("QUANT_NQ_TREND_GATE", "20") or 0)
#: الذهب وحده: البتكوين أدلّته متعارضة (الإعدادات مع الإذن، صفقات الاختبار ضدّه)، والناسداك لم يُقس.
#: ٢٠٢٦-١٠-٠٦ 17:3x — **والناسداك** بختم المالك «NQ» على «اتّجاه اليوم هو الجهة على الناسداك، والاستراتيجيّات
#: تختار نقطة الدخول فقط»: الإعداد المعاكس يُرفض هنا، والصوت المعاكس يصمت في 453 (`QUANT_NQ_HTF_DIRECTION_SYMBOLS`).
#: سنده الصغير المعلَن (12 صفقة اختبار، عهد البنية): الموافق +194$ و+526$، والمعاكس −23$ و−186$.
TREND_GATE_SYMBOLS = frozenset(s.strip().upper() for s in os.environ.get(
    "QUANT_NQ_TREND_GATE_SYMBOLS", "XAUUSD,USTEC").split(",") if s.strip())
TREND_AGAINST = "STRUCTURE_TREND_AGAINST"
#: ٢٠٢٦-١٠-٠٦ 13:28 — **أُلغي إذن فريم الساعة و«الجانبيّ» ±5 بأمر المالك وختمه**: «إذن فريم الساعة،
#: و«الجانبيّ» بين −5 و+5 الغيه هاد لانو نختم عليه بدون اثبات او علم عن طريق سرعة يمكن يكون قرار خاطى nq».
#: كان يرفض كلّ إعدادٍ بنيويّ إن لم يوافق اتّجاه ساعة بطاقة 166 الجهة (مقيس اليوم: الذهب والناسداك بلا
#: صفقة من الإقلاع، والبتكوين جانبيّ −0.23). `QUANT_NQ_HOUR_GATE=on` يعيده (لقياس قيمته في الاختبار).
HOUR_GATE_OFF = os.environ.get("QUANT_NQ_HOUR_GATE", "off").strip().lower() == "off"
TREND_UNKNOWN = "STRUCTURE_TREND_UNKNOWN"

NO_LADDER = "STRUCTURE_NO_LADDER"
GATE_UNKNOWN = "STRUCTURE_GATE_UNKNOWN"
GATE_STALE = "STRUCTURE_GATE_STALE"
GATE_DISAGREES = "STRUCTURE_GATE_DISAGREES"
NO_STOP = "STRUCTURE_NO_STOP_LEVEL"
NO_TARGET = "STRUCTURE_NO_TARGET_3R"
PAD_UNKNOWN = "STRUCTURE_COST_UNKNOWN"

#: ٢٠٢٦-١٠-٠٦ — **السعر بلا مستوى سابق** (ختم المالك «… حلّ القمّة التاريخيّة. NQ» على خطّة الثلاث، بعد
#: شارتين من الناسداك: «ليش ما اشترى من هون» و«شوف صفقة كيف ضاعت» — صعودٌ من 31,150 إلى 31,290): في القمّة
#: التاريخيّة كلّ شراءٍ «لا هدف 1:3» لأنّ لا قمّة فوقه. قاعدة ٠٩-٢٨ «لا يُخترع مستوى» تُبقى حيث للبنية مستوى؛
#: وحين لا مستوى أصلًا في جهة الهدف تُبنى محطّاتٌ بـ`DISCOVERY_R` يُدار عليها كالمستويات.
#: `QUANT_NQ_DISCOVERY=off` يعيد القديم (للقياس).
DISCOVERY_ON = os.environ.get("QUANT_NQ_DISCOVERY", "on").strip().lower() != "off"
DISCOVERY_FRAME = "discovery"
#: ٢٠٢٦-١٠-٠٦ 15:4x (ختم المالك «NQ»): محطّةٌ واحدة لا اثنتان — عند 3R يُغلق الثلث والوقف إلى الدخول،
#: والباقي يركب الموجة بوقفٍ يتبع البنية (574 يبدأ التتبّع بعد آخر محطّة). و9R سقفٌ يحمله الأمر عند الوسيط
#: لأنّ السلسلة لا ترسل أمرًا بلا هدف (551/584/555) — لا هدفٌ يُنتظر.
DISCOVERY_R = (3.0, 9.0)
#: ٢٠٢٦-١٠-٠٦ 16:1x — **ركوب الموجة للناسداك في الجهتين** بختم المالك «NQ»: بيع 410 كان هدفه أبعد قاعٍ
#: يوميّ 22,782.90 (−27٪ من 31,260) — «أبعد مستوى» (٠٥-١٠) بلا معنى لصفقة اليوم. فللرموز هنا: محطّةٌ عند 3R
#: (ثلثٌ والوقف إلى الدخول)، ثمّ تتبّعٌ على فريم الوقف، والهدف أبعد مستوىً حقيقيّ **ما لم يتجاوز سقف 9R**
#: وإلّا فالسقف. وشرط القبول كما كان: مستوىً حقيقيّ بـ1:3 فأكثر، أو منطقةٌ بلا مستوى. `QUANT_NQ_RIDE_SYMBOLS`.
#: ⛔ ٢٠٢٦-١٠-٠٧ — **مطفأ** بختم المالك «nq»: «الأهداف من ١:٣ وأكبر — ١:١٥ · ١:٣٠ إذا التحليل جيّد» فلا سقف 9R على
#: مستوىً حقيقيّ، والإدارة أثلاث المالك وحدها لا محطّة 3R. يبقى للقياس (`QUANT_NQ_RIDE_SYMBOLS`).
RIDE_SYMBOLS = frozenset(s.strip().upper() for s in os.environ.get(
    "QUANT_NQ_RIDE_SYMBOLS", "").split(",") if s.strip())
RIDE_FRAME = "ride"
RIDE_CAP_FRAME = "ride_cap"
_NAMES = {"5m": "الخمس دقائق", "15m": "الربع ساعة", "1h": "الساعة", "4h": "الأربع ساعات", "1d": "اليوم",
          DISCOVERY_FRAME: "منطقةٍ بلا مستوى سابق", RIDE_FRAME: "محطّة 3R", RIDE_CAP_FRAME: "سقف 9R"}


def _real(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def load_seed(path: Path = SEED_PATH) -> dict[str, Any] | None:
    """البذرة كما كُتبت، أو `None` إن غابت أو فسدت — غيابها ليس عطلًا."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("symbols"), dict) else None


class StructureBook:
    """ما سمعته الاستراتيجيّة من البنية والتحليل — ولا شيء غيره.

    لا يقرأ قرصًا ولا ينتظر قفلًا: حدثان يُحفظ آخرُهما لكلّ رمز، وسؤالٌ واحد يُجاب
    من الذاكرة لحظة ولادة الإعداد.
    """

    def __init__(self) -> None:
        self._ladders: dict[str, dict[str, dict[str, list[tuple[float, float]]]]] = {}
        self._closes: dict[str, list[tuple[float, float]]] = {}
        self._frames: dict[str, dict[str, dict[str, Any]]] = {}
        self.ladders_seen = 0
        self.frames_seen = 0

    # ─── المدخلات ────────────────────────────────────────────────────────
    def on_ladder(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        symbol = str(payload.get("symbol") or "").strip().upper()
        frames = payload.get("frames")
        if not symbol or not isinstance(frames, dict):
            return False
        book: dict[str, dict[str, list[tuple[float, float]]]] = {}
        for frame in FRAME_SECONDS:
            sides = frames.get(frame)
            if not isinstance(sides, dict):
                continue
            book[frame] = {}
            for side in ("highs", "lows"):
                rows = []
                for row in sides.get(side) or []:
                    if isinstance(row, (list, tuple)) and len(row) >= 2:
                        price, at = _real(row[0]), _real(row[1])
                        if price is not None and price > 0 and at is not None:
                            rows.append((price, at))
                book[frame][side] = rows[-DEPTH[frame]:]
        self._ladders[symbol] = book
        closes = []
        for row in payload.get("daily_closes") or []:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                start, close = _real(row[0]), _real(row[1])
                if start is not None and close is not None and close > 0:
                    closes.append((start, close))
        if closes:
            self._closes[symbol] = sorted(closes)
        self.ladders_seen += 1
        return True

    def trend(self, symbol: str, now: float) -> int | None:
        """اتّجاه اليوم: +1 إغلاق آخر يومٍ مغلق فوق متوسّط آخر `TREND_GATE_N`، −1 تحته، و`None` مجهول."""
        n = TREND_GATE_N
        rows = [close for start, close in self._closes.get(symbol, []) if start + 86400.0 <= now]
        if n <= 0 or len(rows) < n:
            return None
        window = rows[-n:]
        sma = sum(window) / n
        return 1 if window[-1] > sma else -1 if window[-1] < sma else None

    def on_frames(self, payload: Any) -> bool:
        """بطاقة ١٦٦ البطيئة من الكبير إلى الصغير — يُحفظ تفصيل فريماتها وحده."""
        if not isinstance(payload, dict) or payload.get("timeframe") != "topdown":
            return False
        symbol = str(payload.get("symbol") or "").strip().upper()
        rows = payload.get("frames")
        if not symbol or not isinstance(rows, list):
            return False
        frames: dict[str, dict[str, Any]] = {}
        for row in rows:
            if isinstance(row, dict) and row.get("timeframe") in FRAME_SECONDS:
                frames[row["timeframe"]] = {
                    "direction": _real(row.get("direction")),
                    "alive": bool(row.get("alive")),
                    "closed_at": _real(row.get("closed_at")),
                }
        self._frames[symbol] = frames
        self.frames_seen += 1
        return True

    # ─── الأسئلة ─────────────────────────────────────────────────────────
    def gate(self, symbol: str, side: str, now: float) -> tuple[str, dict[str, Any]]:
        """إذن فريم الساعة: `""` إن وافق الجهة، وإلّا سبب الرفض باسمه."""
        frame = (self._frames.get(symbol) or {}).get(GATE_FRAME)
        big = (self._frames.get(symbol) or {}).get("4h") or {}
        detail = {"gate_frame": GATE_FRAME, "gate_1h": None, "gate_4h": big.get("direction")}
        if frame and frame.get("closed_at") is not None:
            detail["gate_1h"] = frame.get("direction")    # يُسجَّل في الدليل وإن أُطفئ الإذن
        if not HOUR_GATE_OFF:
            if not frame or frame.get("closed_at") is None:
                return GATE_UNKNOWN, detail
            if now - frame["closed_at"] > ALIVE_BARS * FRAME_SECONDS[GATE_FRAME]:
                return GATE_STALE, detail
            direction = frame.get("direction")
            if direction is None or not frame.get("alive"):
                return GATE_UNKNOWN, detail
            agrees = direction > SIDEWAYS if side == "buy" else direction < -SIDEWAYS
            if not agrees:
                return GATE_DISAGREES, detail
        if TREND_GATE_N > 0 and symbol in TREND_GATE_SYMBOLS:
            daily = self.trend(symbol, now)
            detail["trend_1d"] = daily
            if daily is None:
                return TREND_UNKNOWN, detail
            if daily != (1 if side == "buy" else -1):
                return TREND_AGAINST, detail
        return "", detail

    def stop_frame(self, symbol: str) -> str:
        """فريم الوقف والتتبّع لهذا الرمز — الخمس دقائق للناسداك ما دام سلّمها وصل بقممٍ وقيعان،
        وإلّا الربع ساعة (لا يُترك الرمز بلا وقفٍ ريثما تتأكّد أوّل قمّة خمس دقائق بعد الإقلاع)."""
        symbol = str(symbol or "").strip().upper()
        wanted = STOP_FRAME_BY_SYMBOL.get(symbol, STOP_FRAME)
        if wanted != STOP_FRAME:
            book = (self._ladders.get(symbol) or {}).get(wanted) or {}
            if not (book.get("highs") and book.get("lows")):
                return STOP_FRAME
        return wanted

    def exits(self, *, symbol: str, side: str, entry: float, spread: float,
              pad: float, now: float | None = None) -> tuple[str, dict[str, Any]]:
        """الوقف والهدف من البنية — أو سبب الرفض. لا رقمَ من غير مستوىً مؤكَّد."""
        symbol = str(symbol or "").strip().upper()
        side = str(side or "").strip().lower()
        clock = float(now if now is not None else time.time())
        buy = side == "buy"
        why, detail = self.gate(symbol, side, clock)
        if why:
            return why, detail
        ladder = self._ladders.get(symbol)
        if not ladder:
            return NO_LADDER, detail
        if pad is None or pad <= 0.0:
            return PAD_UNKNOWN, detail
        # الوقف: أحدث قاعٍ مؤكَّد تحت الدخول (أو قمّةٍ فوقه للبيع) على فريم وقف الرمز.
        stop_frame = self.stop_frame(symbol)
        rows = (ladder.get(stop_frame) or {}).get("lows" if buy else "highs") or []
        found = [(price, at) for price, at in rows
                 if at <= clock and (price < entry if buy else price > entry)]
        if not found:
            return NO_STOP, detail
        level, level_at = found[-1]
        stop = level - pad if buy else level + pad
        # ٢٠٢٦-١٠-٠٥ (ختم المالك «nq اعتمدناها» على «أدقّ ستوب وأكبر هدف»): الهدف **أبعد**
        # مستوىً على الساعة أو 4س أو اليوم تبلغ نسبتُه 1:3 بعد الكلفة — كان الأقرب، أي أدنى ما
        # تقبله القاعدة لا أكبر ما يعطيه التحليل. والمستويات التي في الطريق إليه تُدار عليها
        # الصفقة في ٥٧٤ (`exit_levels` نفسها): ثلثٌ على الأوّل، ونصف الباقي على الثاني.
        levels = self.exit_levels(symbol=symbol, side=side, entry=entry, stop=stop,
                                  spread=spread, until=clock)
        if levels and levels[-1][1] == DISCOVERY_FRAME:
            detail["price_discovery"] = True
        if not levels:
            return NO_TARGET, detail
        target, frame, target_at, _ratio = levels[-1]
        ratio = net_ratio({"entry_reference": entry, "invalidation_price": stop,
                           "target_price": target}, spread)
        detail.update({"stop_level": level, "stop_level_at": level_at, "stop_frame": stop_frame,
                       "cost_pad": round(pad, 8), "target_frame": frame, "target_level_at": target_at,
                       "net_ratio": round(ratio, 3),
                       "exit_levels": [[round(p, 8), f, a, round(r, 3)] for p, f, a, r in levels]})
        kind_stop = "قاعٍ" if buy else "قمّةٍ"
        kind_target = "قمّةٍ" if buy else "قاعٍ"
        if frame == RIDE_CAP_FRAME:
            target_reason = "أبعد %s مؤكَّد أبعدُ من سقف 9R — الهدف السقف %s (1:%.1f)، ومحطّة 3R ثمّ وقفٌ يتبع %s" % (
                kind_target, _fmt(target), ratio, _NAMES[stop_frame])
        elif frame == DISCOVERY_FRAME:
            target_reason = "لا %s مؤكَّدة في جهة الهدف على الساعة و4س واليوم (منطقةٌ بلا مستوى سابق) — محطّاتٌ %s والهدف %s (1:%.1f)" % (
                kind_target, " و".join("%gR" % r for r in DISCOVERY_R[:-1]), _fmt(target), ratio)
        else:
            target_reason = "%s %s مؤكَّدٍ على %s بنسبة 1:%.1f بعد الكلفة (%s) — و%d مستوى في الطريق" % (
                "أقرب" if TARGET_PICK == "near" else "أبعد",
                kind_target, _NAMES[frame], ratio, _fmt(target), len(levels) - 1)
        return "", {
            "invalidation_price": stop,
            "invalidation_source": "201:%s:%s" % (stop_frame, "swing_low" if buy else "swing_high"),
            "invalidation_reason": "كسرُ آخر %s مؤكَّدٍ على %s (%s) يُبطل الفكرة" % (
                kind_stop, _NAMES[stop_frame], _fmt(level)),
            "target_price": target,
            "target_source": "201:%s:%s" % (frame, "swing_high" if buy else "swing_low"),
            "target_reason": target_reason,
            "evidence": detail,
        }

    def exit_levels(self, *, symbol: str, side: str, entry: float, stop: float,
                    spread: float, until: float) -> list[tuple[float, str, float, float]]:
        """مستويات الخروج من البنية — من الأقرب إلى الأبعد، كلٌّ بنسبة 1:3 فأكثر بعد الكلفة.

        `(السعر · الفريم · لحظة تأكيده · النسبة)`. القمم للشراء والقيعان للبيع، على الساعة
        و4س واليوم، مؤكَّدةٌ حتى `until` وحده (لحظة الإعداد، أو لحظة فتح الصفقة في ٥٧٤) —
        فلا يدخل مستوىً وُلد بعدها. والمستوى لا يُعدّ جديدًا ما لم يبعد عن سابقه **مسافةَ
        الوقف نفسها** (1R): قاعان على ‎4111.52‎ و‎4110.95‎ واحدٌ لا اثنان، ولا يُغلق ثلثُ
        عقدٍ على فرق نصف نقطة. والأبعد يبقى آخرَ القائمة دائمًا — هو الهدف.
        """
        symbol = str(symbol or "").strip().upper()
        buy = str(side or "").strip().lower() == "buy"
        ladder = self._ladders.get(symbol) or {}
        risk = abs(entry - stop)
        found: dict[float, tuple[str, float, float]] = {}
        for frame in TARGET_FRAMES:
            for price, at in (ladder.get(frame) or {}).get("highs" if buy else "lows") or []:
                if at > until or (price <= entry if buy else price >= entry):
                    continue
                ratio = net_ratio({"entry_reference": entry, "invalidation_price": stop,
                                   "target_price": price}, spread)
                if ratio >= MIN_NET_RATIO and price not in found:
                    found[price] = (frame, at, ratio)
        ordered = sorted(found, reverse=not buy)
        if TARGET_PICK == "near" and ordered:
            nearest = ordered[0]      # ١٠-٠٧: أقرب مستوى يعطي 1:3 فأكثر — الأثلاث من مسافته
            return [(nearest, found[nearest][0], found[nearest][1], found[nearest][2])]
        kept: list[float] = []
        for price in ordered:
            if not kept or abs(price - kept[-1]) >= risk:
                kept.append(price)
        if ordered and kept[-1] != ordered[-1]:
            kept[-1] = ordered[-1]
        if not kept and DISCOVERY_ON and risk > 0:
            # ٢٠٢٦-١٠-٠٦ (ختم المالك «… حلّ القمّة التاريخيّة. NQ»): السعر في منطقةٍ بلا مستوى سابق — لا
            # قمّةٌ مؤكَّدة فوقه للشراء (ولا قاعٌ تحته للبيع) على الساعة و4س واليوم أصلًا. فلا يُرفض «بلا هدف»:
            # محطّاتٌ بـ3R و6R و9R صافيةً بعد الكلفة، يُدار عليها كالمستويات (ثلثٌ ثمّ نصف الباقي ثمّ الباقي
            # بوقفٍ يتبع البنية) — فيُركب الاتّجاه بلا سقف 3R. ومستوى حقيقيّ في الجهة يُبطل هذا كلّه،
            # وسلّمٌ فارغٌ حتى `until` ليس «قمّة تاريخيّة» بل جهلٌ بالبنية: يلزم مستوىً معروفٌ واحدٌ على الأقلّ
            # وكلّ المعروف خلف السعر.
            known = [price for frame in DISCOVERY_FRAMES
                     for price, at in (ladder.get(frame) or {}).get("highs" if buy else "lows") or []
                     if at <= until]
            beyond = any((price > entry if buy else price < entry) for price in known)
            if known and not beyond:
                legs = []
                for multiple in (DISCOVERY_R[:1] if TARGET_PICK == "near" else DISCOVERY_R):
                    reward = multiple * (risk + spread) * 1.001 + spread
                    legs.append((entry + reward if buy else entry - reward, DISCOVERY_FRAME, until, multiple))
                return legs
        levels = [(price, found[price][0], found[price][1], found[price][2]) for price in kept]
        if levels and symbol in RIDE_SYMBOLS and risk > 0:
            levels = _ride(levels, buy, entry, risk, spread, until)
        return levels

    def trail_level(self, *, symbol: str, side: str, price: float,
                    until: float) -> float | None:
        """أحدث قمّةٍ مؤكَّدة على الربع ساعة فوق السعر (للبيع) أو قاعٍ تحته (للشراء).

        وقفُ الجزء الأخير يتبعها (٥٧٤) — تتبّعٌ بنيويّ: الوقف خلف آخر بنيةٍ لم تُكسر، لا
        مسافةٌ ثابتة. `None` حين لا مستوى مؤكَّد في جهته.
        """
        symbol = str(symbol or "").strip().upper()
        buy = str(side or "").strip().lower() == "buy"
        rows = ((self._ladders.get(symbol) or {}).get(self.stop_frame(symbol)) or {}).get(
            "lows" if buy else "highs") or []
        found = [level for level, at in rows
                 if at <= until and (level < price if buy else level > price)]
        return found[-1] if found else None


def _ride(levels: list[tuple[float, str, float, float]], buy: bool, entry: float, risk: float,
          spread: float, until: float) -> list[tuple[float, str, float, float]]:
    """ركوب الموجة (`RIDE_SYMBOLS`): محطّة 3R ثمّ الهدف — أبعد مستوىً حقيقيّ ما لم يتجاوز سقف 9R."""
    def at_r(multiple: float) -> float:
        reward = multiple * (risk + spread) * 1.001 + spread
        return entry + reward if buy else entry - reward
    final = levels[-1]
    cap = at_r(DISCOVERY_R[-1])
    if (final[0] > cap) if buy else (final[0] < cap):
        final = (cap, RIDE_CAP_FRAME, until, DISCOVERY_R[-1])
    station = at_r(DISCOVERY_R[0])
    out: list[tuple[float, str, float, float]] = []
    if ((station < final[0]) if buy else (station > final[0])) and abs(final[0] - station) >= risk:
        out.append((station, RIDE_FRAME, until, DISCOVERY_R[0]))
    out.append(final)
    return out


def _fmt(price: float) -> str:
    return ("%.2f" % price) if price >= 100 else ("%.5f" % price)
