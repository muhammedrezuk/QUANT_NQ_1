# -*- coding: utf-8 -*-
"""GATE 1 — مِرجَع تكافؤ القرار.

## العقد

قبل أن نُبدّل **وسيلة التنفيذ** بالكامل، نسجّل ما يُقرّره المحرّك الحاليّ،
كي لا يُقال بعد الشهر: «صار أسرع، والنتائج اختلفت لأنّ الخطة تعمل بطريقةٍ
أخرى». كلّ اختلافٍ بعد اليوم إمّا **صفر** وإمّا **مُصنَّفٌ مفسَّر**.

## لماذا لا يكلّف المسار الساخن شيئًا

يركب على `subscribe_all`، و[engine.py:314](../engine/engine.py) يحوّل كلّ
مشترِكٍ عامّ إلى **البارد** حتمًا (§٤ من ورقة المالك ٢٠٢٦-٠٩-١٠: «مَن يرى
كلّ حدث لا مكان له داخل دورة تِكّة»). فالمسجّل خارج دورة التِكّة بالبناء،
لا بالاتّفاق.

ومطفأٌ ما لم يُطلَب: بلا `NQ_PARITY` لا يُركَّب أصلًا.

## المفتاح — موجودٌ لا مُختَرَع

النواة تصدر أصلًا هويّةً حتميّة لكلّ دورة قرار:

    cycle_id = "52992818|Raw Trading Ltd|XAUUSD|tick|7292233"
                 الحساب |   الوسيط      | الرمز |الإطار| تسلسل التِكّة

مشتقّةٌ من `sequence` الذي يحمله `market.tick.validated` نفسه. فالشريط
نفسه يعطي المفتاح نفسه على أيّ محرّك — وهذا بالضبط ما يحتاجه التكافؤ.
ولو اخترعنا مفتاحًا جديدًا لاحتجنا إثبات حتميّته أوّلًا.

## ما يُسجَّل

ستّة أحداثٍ تُجمَّع في سجلٍّ واحدٍ لكلّ `cycle_id`:

    market.tick.validated      هويّة التِكّة (التسلسل · السعر · الطابع)
    decision.room.state        القرار المجمَّع (اتّجاه · ثقة · قوّة · إشارة)
    decision.approved.state    البوّابة النهائيّة (موافقة · جانب · درجة · حواجز)
    decision.dispatch.state    نيّة الأمر (قابل للتنفيذ · جانب · طلب)
    decision.gate.passed       خرج أمرٌ فعلًا
    decision.gate.blocked      حُجب ولماذا

والحقول مأخوذةٌ من لقطةٍ حيّة لا من المانيفست — المانيفست يقول ما يُنشَر،
واللقطة تقول ما **فيه**.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Iterable

#: الأحداث الستّة. الترتيب ترتيبُ السلسلة لا الأهمّيّة.
TICK_EVENT = "market.tick.validated"
ROOM_EVENT = "decision.room.state"
APPROVED_EVENT = "decision.approved.state"
DISPATCH_EVENT = "decision.dispatch.state"
GATE_PASSED_EVENT = "decision.gate.passed"
GATE_BLOCKED_EVENT = "decision.gate.blocked"

WATCHED = (TICK_EVENT, ROOM_EVENT, APPROVED_EVENT,
           DISPATCH_EVENT, GATE_PASSED_EVENT, GATE_BLOCKED_EVENT)

#: حقولٌ تُقارَن حرفيًّا — أيّ اختلافٍ فيها عطبٌ حتّى يُصنَّف.
IDENTITY_FIELDS = ("account_id", "broker", "symbol", "timeframe", "sequence")
DECISION_FIELDS = ("signal", "direction", "confidence", "strength", "ratio",
                   "readiness_pct", "sections_present", "room", "status")
APPROVAL_FIELDS = ("approved", "decision_side", "score", "rejection_reason",
                   "rejection_stage", "barrier_names", "warnings")
INTENT_FIELDS = ("executable", "side", "request_id", "dispatched")

#: ⚠️ حقولٌ **لا يجوز أن تغيب** في دورةٍ مكتملة — وعليها وحدها يُقاس
#: `null == null`. وما عداها يغيب بحقّ: `rejection_reason` فارغٌ حين
#: تُوافَق الصفقة، و`request_id` فارغٌ حين لا يُرسَل أمر. فعدُّ تطابقهما
#: فراغًا يجعل البوّابة تشتكي من سلوكٍ سليم، وهو إنذارٌ كاذبٌ يُفقد الثقة.
#
# ٢٠٢٦-٠٩-١٨ (إغلاق GATE 1، الخيار ج): **حقول الغرفة خرجت من هنا.**
# `decision.room.state` قناةُ حالةٍ مدموجة لا سجلٌّ لكلّ دورة — ومفتاح
# الدمج في النواة `(event, account, symbol, id)` بلا `trace_id`، فالأحدث
# يحلّ محلّ الأقدم بالعقد لا بالعطب (مقيس: 66.6٪ ثابتة). واشتراطُ حضورها
# في كلّ دورةٍ ليس ثابتًا صحيحًا لهذه القناة. والهويّة والموافقة تبقيان:
# فهما تصلان لكلّ دورةٍ بلا دمج، وغيابهما عمًى حقيقيّ.
REQUIRED_FIELDS = IDENTITY_FIELDS + ("approved",)

#: بعد هذا العمر تُغلق الدورة ولو لم يصلها قرار — وتُسجَّل ناقصةً **معلَنة**.
DEFAULT_CLOSE_AFTER_S = 8.0
#: مهلةٌ بعد النهاية يلحق فيها المتأخّر بالسجلّ نفسه بدل أن يفتح ثانيًا.
DEFAULT_GRACE_S = 2.0
#: سقف الدورات المفتوحة — حارسٌ لا سياسة.
DEFAULT_MAX_OPEN = 20000


def _num(value: Any) -> Any:
    """رقمٌ مُدوَّر تدويرًا ثابتًا، أو القيمة كما هي.

    ⛔ التدوير هنا **ليس تسامحًا**: مقارنة عائمين بخانةٍ سادسة تُنتج ضجيجًا
    لا معنى له بين تشغيلتين. والتسامح الحقيقيّ — إن لزم — يُصنَّف في
    المقارِن بالاسم، لا يُدفن هنا صامتًا.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    return value


def _barrier_names(barriers: Any) -> list[str]:
    """أسماء الحواجز التي سقطت — مرتّبةً كي لا يكذب الترتيب باختلاف."""
    out: list[str] = []
    if isinstance(barriers, list):
        for row in barriers:
            if isinstance(row, dict) and row.get("value") is False:
                out.append("%s:%s" % (row.get("name") or "؟",
                                      row.get("reason") or "؟"))
    return sorted(out)


def _cycle_key(payload: dict) -> str:
    """`cycle_id` إن وُجد، وإلّا يُبنى من الهويّة نفسها بصيغتها نفسها."""
    cycle = payload.get("cycle_id") or payload.get("decision_id")
    if cycle:
        return str(cycle).removeprefix("dec:")
    account = payload.get("account_id")
    symbol = payload.get("symbol")
    sequence = payload.get("sequence")
    if account and symbol and sequence is not None:
        return "%s|%s|%s|%s|%s" % (account, payload.get("broker") or "",
                                   symbol, "tick", sequence)
    return ""


class ParityRecorder:
    """يجمع الأحداث الستّة في سجلٍّ واحدٍ لكلّ دورة قرار ويكتبه سطرًا.

    الكتابة مؤجّلة ومجمّعة: الأسطر تتراكم في قائمةٍ تحت قفل، ويُصرَّف
    الدفتر من **خارج** الحلقة (`flush`) أو عند بلوغ سقف الدفعة. فلا قرصَ
    داخل معالجٍ ولا في مسار تِكّة.
    """

    def __init__(self, path: str, *, runtime: str = "legacy",
                 close_after_s: float = DEFAULT_CLOSE_AFTER_S,
                 grace_s: float = DEFAULT_GRACE_S,
                 max_open: int = DEFAULT_MAX_OPEN,
                 tape_path: str = "",
                 batch: int = 256) -> None:
        self.path = str(path)
        self.runtime = str(runtime)
        self.close_after_s = float(close_after_s)
        self.grace_s = float(grace_s)
        self.max_open = int(max_open)
        self.batch = int(batch)
        #: شريط المدخلات الخام — **بترتيب وصولها**. هو ما يُغذّى به المرجع
        #: الثاني لاحقًا (`parity mismatches = 0` بمحرّكٍ ثانٍ). فارغٌ = مطفأ.
        self.tape_path = str(tape_path)
        #: (رقم الوصول، اسم الحدث، الحمولة) — يُرمَّز عند التصريف لا هنا.
        self._tape: list[tuple[int, str, Any]] = []
        self.taped = 0
        #: تعثّرُ كتابةٍ يُعدّ ولا يُبتلع — الدفتر يعود ولا يُفقَد.
        self.tape_write_failures = 0

        self._lock = threading.Lock()
        self._open: dict[str, dict[str, Any]] = {}
        self._pending: list[str] = []
        self._ticks_by_seq: dict[str, dict[str, Any]] = {}
        #: ⛔ `decision.room.state` **لا يحمل `cycle_id` ولا `sequence`** —
        #: مقيسٌ من لقطةٍ حيّة ٢٠٢٦-٠٩-١٨. رابطه الوحيد بالقرار هو `trace_id`،
        #: وهو نفسه في `decision.approved.state` للدورة ذاتها. وأوّل صيغةٍ من
        #: هذا المسجّل بنت حمولة اختبارها بـ`cycle_id` مفترَض، فمرّت الحرّاس
        #: خضراء بينما حقول القرار كلّها `null` في التشغيل الحقيقيّ.
        self._room_by_trace: dict[str, dict[str, Any]] = {}
        #: `trace_id ⟶ cycle_id` — كي تجد الغرفةُ **المتأخّرة** دورتَها.
        #: الترتيب ليس مضمونًا: الغرفة قد تصل بعد الموافقة، وبلا هذا الفهرس
        #: تبقى محفوظةً إلى أن تكنسها المكنسة وتُفقد بياناتها.
        self._cycle_by_trace: dict[str, str] = {}
        #: دوراتٌ أُغلقت — **لا يفتحها حدثٌ لاحق ثانيةً** (أمر المالك:
        #: «الدورة تُغلق مرّة واحدة فقط»). مفتاحٌ بلا قيمة، بسقفٍ متحرّك.
        self._closed: "OrderedDict[str, None]" = OrderedDict()

        self.observed = 0
        self.records = 0
        self.dropped_no_key = 0
        self.rooms_held = 0
        self.rooms_joined = 0
        self.rooms_late_joined = 0
        self.late_after_close = 0
        self.evicted = 0
        self.written = 0
        #: أيّ قناةٍ رُكّب عليها — يُقرأ في التقرير فلا يُظنّ المدموجُ كاملًا.
        self.channel = ""
        self._last_sweep = 0.0

    # ── الالتقاط ─────────────────────────────────────────────────────────

    def observe(self, event_name: str, payload: Any) -> None:
        """يُنادى لكلّ حدث. يخرج فورًا لما لا يعنيه — هذا أرخص فحصٍ ممكن."""
        if event_name not in WATCHED or not isinstance(payload, dict):
            return
        self.observed += 1
        now = time.time()
        if self.tape_path:
            # ⛔ كان هنا `json.dumps` لكلّ حدث. والمقيس ٢٠٢٦-٠٩-١٨ أنّ ذلك
            #    يُبطئ مستهلكَ الصندوق البارد، فيبقى في طابوره معلَّقٌ —
            #    و`core/event_bus.py:275` يدمج أيّ حدثٍ قابلٍ للإعادة **ما دام
            #    له نظيرٌ معلَّق**. النتيجة: 9,552 غرفةً مدموجةً من 14,334،
            #    و٥٦ دورةَ قرارٍ بلا غرفة. الدمج لا يقع على صندوقٍ فارغ.
            #    فالترميز يخرج إلى `flush` (خارج الحلقة)، والمعالج يُلحِق
            #    إشارةً فقط. الترتيب محفوظٌ برقم الوصول كما هو.
            # ⛔ **تحت القفل.** كان الإلحاق خارجه، و`flush` يبدّل المرجع
            #    تحته: فتقرأ الحلقةُ القائمةَ القديمة، ويكتبها التصريف،
            #    ثمّ تُلحِق الحلقةُ بها **بعد** كتابتها — فتضيع صامتة.
            #    المقيس ٢٠٢٦-٠٩-١٨: فجوةٌ من 27,406 واقعة في رقم الوصول
            #    (i من 49,212 إلى 76,619) بلا أيّ خطأٍ مسجَّل. وفقدُ مدخلٍ
            #    فشلُ تكافؤٍ لا نقصُ أداء.
            with self._lock:
                self._tape.append((self.taped, event_name, payload))
                self.taped += 1
        # ⛔ المكنسة **قبل** أيّ خروجٍ مبكّر: كانت في الذيل، فمسارُ الغرفة
        #    المحفوظة يعود قبلها ولا يبلغها أبدًا. حارسٌ كشف ذلك بعد أن
        #    نجت طفرةٌ تُسقط الدورة الناقصة صامتة.
        if now - self._last_sweep > 1.0:
            self._sweep(now)
        if event_name == TICK_EVENT:
            self._on_tick(payload, now)
            return
        key = _cycle_key(payload)
        if not key:
            # الغرفة بلا `cycle_id` — إمّا تلحق بدورةٍ مفتوحةٍ بأثرها، وإمّا
            # تُحفَظ حتّى يصل قرارها. والاتّجاهان لازمان: الترتيب غير مضمون.
            if event_name == ROOM_EVENT:
                trace = str(payload.get("trace_id") or "")
                if trace:
                    with self._lock:
                        # ⛔ تُحفَظ **دائمًا** ولو لحقت بدورة. أوّل صيغةٍ كانت
                        #    تعود بعد اللحاق بلا حفظ، فالبوّابة التي تشارك
                        #    الأثر نفسه بعدها لا تجد غرفةً — والمقيس ٧٤ دورةً
                        #    بلا حقول قرار، أكثرها بوّابةٌ وحدها.
                        if len(self._room_by_trace) >= self.max_open:
                            self._room_by_trace.clear()
                            self.evicted += 1
                        self._room_by_trace[trace] = dict(payload)
                        self._room_by_trace[trace]["_seen_at"] = now
                        owner = self._cycle_by_trace.get(trace)
                        row = self._open.get(owner) if owner else None
                        if row is not None and row.get("signal") is None:
                            self._fill_room(row, payload)
                            row["room_joined_by"] = "trace_id:late"
                            self.rooms_late_joined += 1
                    self.rooms_held += 1
                    return
            self.dropped_no_key += 1
            return
        with self._lock:
            if key in self._closed:
                # ⛔ أمر المالك: «لا يجوز لأيّ حدثٍ لاحق أن يفتح سجلّ دورةٍ
                #    جديدة بالمفتاح نفسه». يُعدّ ولا يُفتح ولا يُبتلع صامتًا.
                self.late_after_close += 1
                return
            row = self._open.get(key)
            if row is None:
                row = self._open[key] = self._new_row(key, payload, now)
            trace = str(payload.get("trace_id") or "")
            if trace:
                self._cycle_by_trace[trace] = key
            self._join_room(row, payload)
            if event_name == ROOM_EVENT:
                self._fill_room(row, payload)
            elif event_name == APPROVED_EVENT:
                self._fill_approved(row, payload)
            elif event_name == DISPATCH_EVENT:
                self._fill_dispatch(row, payload)
            elif event_name in (GATE_PASSED_EVENT, GATE_BLOCKED_EVENT):
                self._fill_gate(row, payload, event_name)
            if row["terminal"] and row.get("terminal_at") is None:
                # النهاية لا تُغلق فورًا: تُمهَل `grace_s` كي يلحق المتأخّر
                # (إرسالٌ أو بوّابةٌ ثانية) بالسجلّ نفسه بدل أن يفتح ثانيًا.
                row["terminal_at"] = now
                if self.grace_s <= 0.0:
                    self._close(key, row)

    def _on_tick(self, payload: dict, now: float) -> None:
        """التِكّة لا `cycle_id` لها — تُحفظ بتسلسلها لتُضمّ حين يصل القرار."""
        sequence = payload.get("sequence")
        symbol = payload.get("symbol")
        account = payload.get("account_id")
        if sequence is None or not symbol or not account:
            return
        key = "%s|%s|%s|tick|%s" % (account, payload.get("broker") or "",
                                    symbol, sequence)
        with self._lock:
            if len(self._ticks_by_seq) >= self.max_open:
                self._ticks_by_seq.clear()
                self.evicted += 1
            self._ticks_by_seq[key] = {
                "tick_bid": _num(payload.get("bid")),
                "tick_ask": _num(payload.get("ask")),
                "tick_price": _num(payload.get("price")),
                "tick_timestamp": _num(payload.get("timestamp")),
                "tick_sequence_gap": payload.get("sequence_gap"),
                "tick_out_of_order": payload.get("out_of_order"),
                "tick_provider": payload.get("provider"),
                "tick_trace_id": payload.get("trace_id"),
                "seen_at": now,
            }

    # ── بناء السجلّ ──────────────────────────────────────────────────────

    def _new_row(self, key: str, payload: dict, now: float) -> dict[str, Any]:
        parts = key.split("|")
        row: dict[str, Any] = {
            "runtime": self.runtime,
            "cycle_id": key,
            "account_id": parts[0] if len(parts) > 0 else payload.get("account_id"),
            "broker": parts[1] if len(parts) > 1 else payload.get("broker"),
            "symbol": parts[2] if len(parts) > 2 else payload.get("symbol"),
            "timeframe": parts[3] if len(parts) > 3 else payload.get("timeframe"),
            "sequence": parts[4] if len(parts) > 4 else None,
            "opened_at": now,
            "terminal": False,
            "saw": [],
        }
        for field in DECISION_FIELDS + APPROVAL_FIELDS + INTENT_FIELDS:
            row[field] = None
        row["gate_outcome"] = None
        row["fate"] = None
        tick = self._ticks_by_seq.pop(key, None)
        if tick is not None:
            tick.pop("seen_at", None)
            row.update(tick)
        return row

    def _join_room(self, row: dict, payload: dict) -> None:
        """يضمّ غرفةً محفوظةً بأثرها إلى دورتها — الرابط `trace_id` لا سواه."""
        if row.get("signal") is not None:
            return
        trace = str(payload.get("trace_id") or "")
        if not trace:
            return
        held = self._room_by_trace.get(trace)
        if held is None:
            return
        # ⛔ كانت تُنتزَع (`pop`). والمقيس حيًّا أنّ أكثر من دورةٍ تنحدر من
        #    الأثر نفسه: فأوّل ضامٍّ يبتلع الغرفة، وتبقى الأخرى بلا حقول
        #    قرار. ثمنه ٨٠ دورةً «عمياء» وهي ليست كذلك. تُنسَخ الآن وتُترك
        #    للمكنسة تكنسها بالعمر — فالغرفة حالةُ تِكّةٍ لا ملكَ دورةٍ واحدة.
        self._fill_room(row, {k: v for k, v in held.items() if k != "_seen_at"})
        row["room_joined_by"] = "trace_id"
        self.rooms_joined += 1

    def _fill_room(self, row: dict, payload: dict) -> None:
        row["saw"].append("room")
        for field in ("signal", "direction", "confidence", "strength",
                      "ratio", "readiness_pct", "room", "status"):
            row[field] = _num(payload.get(field))
        present = payload.get("sections_present")
        row["sections_present"] = (sorted(str(s) for s in present)
                                   if isinstance(present, list) else None)
        row.setdefault("room_trace_id", payload.get("trace_id"))

    def _fill_approved(self, row: dict, payload: dict, *, mark: bool = True) -> None:
        if mark:
            row["saw"].append("approved")
        row["approved"] = payload.get("approved")
        row["decision_side"] = payload.get("decision_side") or payload.get("side")
        row["score"] = _num(payload.get("score"))
        rejection = payload.get("rejection")
        if isinstance(rejection, dict):
            row["rejection_reason"] = rejection.get("reason")
            row["rejection_stage"] = str(rejection.get("stage") or "")
        row["barrier_names"] = _barrier_names(payload.get("barriers"))
        warnings = payload.get("warnings")
        row["warnings"] = (sorted(str(w) for w in warnings)
                           if isinstance(warnings, list) else None)
        # ⛔ كان `approved=False` يُنهي الدورة. والمقيس حيًّا أنّ
        #    `decision.gate.blocked` يصل **بعده** بالمفتاح نفسه، فيفتح سجلًّا
        #    ثانيًا لا غرفة فيه ولا قرار — و`load` تفهرس بآخر سطر، فالأعمى
        #    **يدهس** الكامل. النتيجة: تغطية 40٪ وستّون دورةً بلا حقول قرار.
        #    فالنهاية صارت البوّابةَ وحدها، وما لا بوّابة له تُغلقه المكنسة.
        #
        # ٢٠٢٦-٠٩-١٨ (ثانيًا): ورفضٌ لا بوّابة له **مصيرٌ نهائيّ لا نقصٌ** —
        # سلسلة المالك: room ⟶ approved/rejected ⟶ gate ⟶ send/no-send.
        # فالرفض يُنهي بمهلةٍ (تسمح لبوّابةٍ متأخّرة أن تلحق)، وكان يُوصَف
        # `incomplete` ظلمًا: ١٠٧ دورةً من ٢٩٠ وُسمت نقصًا وهي تامّة المصير.
        if payload.get("approved") is False and row.get("gate_outcome") is None:
            row["terminal"] = True
            row["fate"] = "rejected"

    def _fill_dispatch(self, row: dict, payload: dict) -> None:
        row["saw"].append("dispatch")
        row["executable"] = payload.get("executable")
        row["side"] = payload.get("side")
        row["request_id"] = payload.get("request_id")
        row["dispatched"] = True

    def _fill_gate(self, row: dict, payload: dict, event_name: str) -> None:
        """البوّابة نهايةُ الدورة — **وتحمل حمولة الموافقة كاملةً**.

        مقيسٌ حيًّا ٢٠٢٦-٠٩-١٨: `decision.gate.blocked` مصدره `466` نفسه،
        وفيه `approved` و`decision_side` و`score` و`barriers` و`rejection`
        و`signal`. وأوّل صيغةٍ قرأت منه الحواجز وحدها، فبقيت ثلاثٌ وثلاثون
        دورةً «عمياء» وهي ليست عمياء — المسجّل هو من لم يقرأ.
        """
        row["saw"].append("gate")
        row["gate_outcome"] = ("passed" if event_name == GATE_PASSED_EVENT
                               else "blocked")
        if row.get("approved") is None:
            self._fill_approved(row, payload, mark=False)
        elif row.get("barrier_names") in (None, []):
            row["barrier_names"] = _barrier_names(payload.get("barriers"))
        row["gate_state"] = payload.get("gate_state")
        row["fate"] = ("sent" if event_name == GATE_PASSED_EVENT else "blocked")
        row["terminal"] = True

    # ── الإغلاق والتصريف ────────────────────────────────────────────────

    def _close(self, key: str, row: dict) -> None:
        """يُكتب السجلّ **مرّةً واحدة**، ويُختم المفتاح فلا يُفتح ثانيةً."""
        self._open.pop(key, None)
        row.pop("terminal", None)
        row.pop("terminal_at", None)
        row["saw"] = sorted(set(row["saw"]))
        row["closed_at"] = time.time()
        for trace, owner in [(t, o) for t, o in self._cycle_by_trace.items()
                             if o == key]:
            self._cycle_by_trace.pop(trace, None)
        self._closed[key] = None
        while len(self._closed) > self.max_open:
            self._closed.popitem(last=False)
        self._pending.append(json.dumps(row, ensure_ascii=False,
                                        sort_keys=True, default=str))
        self.records += 1

    def _sweep(self, now: float) -> None:
        """دورةٌ لم تبلغ قرارًا تُسجَّل **ناقصةً معلَنة** لا تُنسى صامتة."""
        self._last_sweep = now
        cutoff = now - self.close_after_s
        grace_cutoff = now - self.grace_s
        with self._lock:
            # أوّلًا المنتهية التي انقضت مهلتها — هذه **مكتملة** لا ناقصة.
            ripe = [k for k, r in self._open.items()
                    if r.get("terminal_at") is not None
                    and r["terminal_at"] <= grace_cutoff]
            for key in ripe:
                self._close(key, self._open[key])
            # ثمّ ما بات. و**موافقةٌ لم تبلغ البوّابة مصيرٌ لا نقص**: سلسلة
            # المالك تنتهي بـ`send / no-send`. والمقيس ٢٠٢٦-٠٩-١٨ على ٢٩٣
            # دورةً بلغت البوّابة: p50=0.556 ث · p99=1.153 · **أقصى 1.506** —
            # والنافذة ٨ ث، أي خمسة أضعاف الأقصى. فما لم يبلغها في ٨ ث لم
            # يبلغها قطّ. وكان يُوسَم `incomplete`: ٣١٧ دورةً من ١٬١٩٧.
            stale = [k for k, r in self._open.items() if r["opened_at"] < cutoff]
            for key in stale:
                row = self._open[key]
                if row.get("approved") is True and row.get("gate_outcome") is None:
                    row["fate"] = "not_sent"
                else:
                    row["incomplete"] = True
                self._close(key, row)
            old_ticks = [k for k, t in self._ticks_by_seq.items()
                         if t.get("seen_at", now) < cutoff]
            for key in old_ticks:
                self._ticks_by_seq.pop(key, None)
            old_rooms = [k for k, r in self._room_by_trace.items()
                         if r.get("_seen_at", now) < cutoff]
            for key in old_rooms:
                self._room_by_trace.pop(key, None)

    def flush(self) -> int:
        """يكتب ما تراكم. يُنادى من خارج الحلقة — لا من معالجٍ ولا من تِكّة."""
        with self._lock:
            lines, self._pending = self._pending, []
            tape, self._tape = self._tape, []
        if tape:
            # الترميز هنا لا في المعالج — خارج الحلقة وخارج صندوق البريد.
            try:
                encoded = [json.dumps({"i": i, "name": name, "payload": payload},
                                      ensure_ascii=False, sort_keys=True,
                                      default=str)
                           for i, name, payload in tape]
                os.makedirs(os.path.dirname(self.tape_path) or ".", exist_ok=True)
                with open(self.tape_path, "a", encoding="utf-8") as fh:
                    fh.write("\n".join(encoded) + "\n")
            except Exception:                                  # noqa: BLE001
                # ⛔ الدفتر يعود إلى **رأس** الطابور بترتيبه، فلا تُفقَد
                #    واقعةٌ لأنّ القرص تعثّر. الترتيب جزءٌ من المدخل.
                with self._lock:
                    self._tape[:0] = tape
                self.tape_write_failures += 1
                raise
        if not lines:
            return 0
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        self.written += len(lines)
        return len(lines)

    def close(self) -> int:
        """يُغلق كلّ ما بقي مفتوحًا ويكتبه — لا تُفقد دورةٌ عند الإيقاف."""
        with self._lock:
            for key in list(self._open):
                row = self._open[key]
                if row.get("terminal_at") is None:
                    row["incomplete"] = True
                self._close(key, row)
        return self.flush()

    def stats(self) -> dict[str, int]:
        return {"observed": self.observed, "records": self.records,
                "written": self.written, "pending": len(self._pending),
                "open": len(self._open), "ticks_held": len(self._ticks_by_seq),
                "rooms_held": self.rooms_held, "rooms_joined": self.rooms_joined,
                "rooms_late_joined": self.rooms_late_joined,
                "rooms_waiting": len(self._room_by_trace),
                "channel": self.channel, "taped": self.taped,
                "tape_pending": len(self._tape),
                "tape_write_failures": self.tape_write_failures,
                "late_after_close": self.late_after_close,
                "closed_keys": len(self._closed),
                "dropped_no_key": self.dropped_no_key, "evicted": self.evicted}


# ── التركيب ──────────────────────────────────────────────────────────────

#: ⛔ البادئة `cold:` تجعل `engine.subscribe` يذهب إلى الناقل **البارد
#: بالاسم** ولا يدخل الرسم الساخن إطلاقًا (`engine.py:287`). فلا اشتراكَ
#: مسمّى على المسار الساخن، ولا `subscriber lookup` جديد فيه — وهو شرط
#: المالك الحاسم ٢٠٢٦-٠٩-١٨.
COLD_SUBSCRIBER = "cold:parity"


def install(event_bus: Any, *, path: str = "", runtime: str = "legacy",
            subscriber: str = COLD_SUBSCRIBER) -> ParityRecorder | None:
    """يركّب المسجّل **قناةً باردةً باسم الحدث** — لا `subscribe_all`.

    ## لماذا تغيّرت الطريقة

    كان يركب على `subscribe_all`. والمقيس ٢٠٢٦-٠٩-١٨ أنّ المسار البارد
    يدمج بأحدث قيمةٍ لكلّ `(اسم، رمز)` كلّ ثانية حين يكون للحدث **مشترِكٌ
    عامّ ولا مشترِكَ مسمّى** (`engine.py::_mirror_cold`):

        display_throttle_s  1.0
        display_coalesced   759,198   ⟵ ٧٣٪ من المُمرَّر
        display_flushed     280,348

    فغرفتان لرمزٍ واحدٍ داخل الثانية ⟵ تصل الأحدث وحدها، وتفقد الدورة
    الأولى غرفتها. وثمنُه خمس دورات قرارٍ عمياء من ١٬٨٠٩.

    والاشتراك **بالاسم** يجعل `has_subs` صحيحًا فيُعفى الحدث من الدمج —
    بلا لمس `display_throttle_s` العامّ، وبلا أن يرى بقيةُ البارد فرقًا.

    ## ما لا يتغيّر

    لا شيء في المسار الساخن: `cold:` تُحوّل الاشتراك إلى الناقل البارد
    قبل أيّ `HotSubscription` أو `_graph.add`.

    يعيد `None` حين لا يُطلَب (`NQ_PARITY` غائب) فلا يُركَّب شيء.
    """
    target = path or os.environ.get("NQ_PARITY", "")
    if not target:
        return None
    recorder = ParityRecorder(
        target,
        runtime=runtime or os.environ.get("NQ_PARITY_RUNTIME", "legacy"),
        tape_path=os.environ.get("NQ_PARITY_TAPE", ""))

    def _capture(event_name: str, payload: Any) -> None:
        try:
            recorder.observe(str(event_name), payload)
        except Exception:                                      # noqa: BLE001
            # ⛔ مسجّلٌ يُسقط النواة أسوأ من مسجّلٍ صامت. يُعدّ ولا يرفع.
            recorder.dropped_no_key += 1

    subscribe = getattr(event_bus, "subscribe", None)
    if callable(subscribe) and str(subscriber).startswith("cold:"):
        # ⛔ **معالجٌ واحدٌ لستّة أسماء، لا ستّة معالجات.** الناقل يودع
        #    بـ`_enqueue(id(handler), …)`، فكلّ معالجٍ صندوقُ بريدٍ مستقلّ.
        #    وستّة صناديق تعني أنّ الغرفة والقرار قد يصلان مقلوبَين، فتُغلق
        #    الدورة قبل غرفتها وتبقى عمياء. المقيس: أربع دورات من ١٬٠٩٦.
        #    ومعالجٌ واحدٌ = صندوقٌ واحد = **الترتيب محفوظ** كما اشترط المالك.
        try:
            from core.event_bus import current_event as _current_event
        except Exception:                                      # noqa: BLE001
            _current_event = None

        if _current_event is not None:
            def _one(payload: Any) -> None:
                # اسم الحدث يُقرأ من سياق الناقل: `_invoke` يضعه قبل النداء.
                _capture(str(_current_event.get() or ""), payload)

            for name in WATCHED:
                subscribe(name, _one, subscriber=subscriber,
                          isolate_payload=False)
            recorder.channel = "cold:named(صندوقٌ واحد)"
            return recorder

        for name in WATCHED:
            def _named(payload: Any, _name: str = name) -> None:
                _capture(_name, payload)

            subscribe(name, _named, subscriber=subscriber,
                      isolate_payload=False)
        recorder.channel = "cold:named(صناديق منفصلة)"
        return recorder

    # مسارُ تراجعٍ لناقلٍ بلا `subscribe` مسمّى — يُدمَج ويُعلَن أنّه يُدمَج.
    event_bus.subscribe_all(_capture, subscriber=subscriber,
                            isolate_payload=False)
    recorder.channel = "cold:global(مدموج)"
    return recorder


# ── المقارنة ─────────────────────────────────────────────────────────────

def load(path: str, *, report: dict | None = None) -> dict[str, dict]:
    """يقرأ سجلًّا ويفهرسه بـ`cycle_id`.

    ⚠️ **الازدواج يُعدّ لا يُبتلع.** الصيغة الأولى كانت تدهس بآخر سطر بصمت،
    فسجلٌّ أعمى وصل متأخّرًا محا سجلًّا كاملًا — وظهر الأثر تغطيةً ٤٠٪ لا
    خطأً. و`duplicate_cycle_ids` أحد شروط إغلاق البوّابة، فيجب أن يُرى.
    """
    rows: dict[str, dict] = {}
    duplicates: dict[str, int] = {}
    lines = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            lines += 1
            key = row.get("cycle_id")
            if not key:
                continue
            key = str(key)
            if key in rows:
                duplicates[key] = duplicates.get(key, 1) + 1
            rows[key] = row
    if report is not None:
        report["lines"] = lines
        report["unique"] = len(rows)
        report["duplicate_cycle_ids"] = len(duplicates)
        report["duplicate_examples"] = sorted(duplicates.items(),
                                              key=lambda kv: -kv[1])[:5]
    return rows


#: ما يُقارَن، مصنّفًا. الاسم يظهر في التقرير كما هو.
COMPARED: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("الهويّة", IDENTITY_FIELDS),
    ("القرار", DECISION_FIELDS),
    ("الموافقة", APPROVAL_FIELDS),
    ("نيّة الأمر", INTENT_FIELDS),
    ("البوّابة", ("gate_outcome", "fate")),
)


def compare(left: dict[str, dict], right: dict[str, dict],
            *, ignore: Iterable[str] = ()) -> dict[str, Any]:
    """يقارن مرجعين ويُصنّف كلّ اختلاف — ولا يبتلع واحدًا.

    لا «تسامح» ضمنيّ: حقلٌ يختلف يظهر باسمه وبعدد مرّاته وبمثالٍ حيّ.
    قرارُ قبولِ اختلافٍ ما قرارُ المالك، لا قرارُ هذه الدالّة.
    """
    skip = set(ignore)
    # ⛔ مقارنةُ سجلٍّ بنفسه تُعطي «تكافؤًا» دائمًا — وهي أخطر إذنٍ كاذب:
    #    تُغلق بوّابةً بُنيت كلّها لتقارن **محرّكين**. فتُكشَف بالاسم هنا،
    #    و`closure` ترفض أن تحسبها إثباتًا.
    runtimes = {str(r.get("runtime") or "") for r in left.values()}
    runtimes |= {str(r.get("runtime") or "") for r in right.values()}
    self_comparison = (left is right) or len(runtimes) < 2
    only_left = sorted(set(left) - set(right))
    only_right = sorted(set(right) - set(left))
    shared = sorted(set(left) & set(right))

    by_field: dict[str, dict[str, Any]] = {}
    vacuous_by_field: dict[str, int] = {}
    vacuous_cycles = 0
    identical = 0
    for key in shared:
        a, b = left[key], right[key]
        differing = []
        vacuous_here = 0
        for group, fields in COMPARED:
            for field in fields:
                if field in skip:
                    continue
                left_v, right_v = a.get(field), b.get(field)
                if left_v != right_v:
                    differing.append((group, field))
                elif (left_v is None and field in REQUIRED_FIELDS
                      and cycle_kind(a) == KIND_DECISION):
                    # ⛔ `null == null` في حقلٍ لا يجوز أن يغيب ليس تطابقًا —
                    #    لا شيءَ قُورِن. يُعدّ ولا يُخفى في خانة «متطابق»،
                    #    وإلّا منحت البوّابة إذنًا على لا شيء.
                    vacuous_here += 1
                    vacuous_by_field[field] = vacuous_by_field.get(field, 0) + 1
        if vacuous_here:
            vacuous_cycles += 1
        if not differing:
            identical += 1
            continue
        for group, field in differing:
            slot = by_field.setdefault(field, {
                "group": group, "count": 0, "example": None})
            slot["count"] += 1
            if slot["example"] is None:
                slot["example"] = {"cycle_id": key,
                                   "left": a.get(field), "right": b.get(field)}
    return {
        "left_total": len(left),
        "right_total": len(right),
        "shared": len(shared),
        "identical": identical,
        "differing": len(shared) - identical,
        "only_left": only_left[:50],
        "only_left_count": len(only_left),
        "only_right": only_right[:50],
        "only_right_count": len(only_right),
        "by_field": dict(sorted(by_field.items(),
                                key=lambda kv: -kv[1]["count"])),
        # `null == null` — مطابقاتٌ فارغة **على دورات القرار وحدها**. صفرٌ
        # شرطُ إغلاقٍ لا رفاهية. ودورةُ البوّابة بلا غرفةٍ بحقٍّ، فعدُّها
        # فراغًا يناقض التصنيف نفسه ويُعيد الخلط الذي حكم المالك بإزالته.
        "vacuous_matches": sum(vacuous_by_field.values()),
        "vacuous_cycles": vacuous_cycles,
        # سجلٌّ قُورن بنفسه — لا يُحتجّ به على تكافؤ محرّكين.
        "self_comparison": self_comparison,
        "vacuous_by_field": dict(sorted(vacuous_by_field.items(),
                                        key=lambda kv: -kv[1])),
        "parity": (len(shared) == len(left) == len(right)
                   and identical == len(shared) and len(shared) > 0
                   and not vacuous_by_field),
    }


#: صنفا الدورة. حكم المالك ٢٠٢٦-٠٩-١٨ بعد القياس:
#:
#:     approved ↔ room = 263/263      gate ↔ room = 64/94
#:     فجوة التسلسل بين العمياء وأقرب مبصرة = 7..21 تِكّة
#:
#: فالبوّابة قد تكون **إعادة تقييمٍ لاحقة** على تِكّةٍ أحدث من التي وُلد
#: عليها القرار. واشتراطُ غرفةٍ لكلّ `cycle_id` يخلط المسارين، ويجعل
#: المسجّل **يفرض بنيةً غير موجودةٍ في النواة**. فيُصنَّف ولا يُخفى.
KIND_DECISION = "decision"
KIND_GATE = "gate"


#: محاور المقارنة الستّة كما سمّاها المالك في ختم `NQ — GATE B`.
#: كلّ محورٍ يُحسَب **على حدة** ويُعرَض باسمه، فلا يُخفي أحدُها الآخر.
#: `cycle_kind` مشتقٌّ لا محفوظ — يُحسب بـ`cycle_kind(row)`.
AXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cycle_identity", IDENTITY_FIELDS),
    ("cycle_kind", ("__kind__",)),
    ("decision", DECISION_FIELDS + ("approved", "decision_side", "score")),
    ("risk", ("barrier_names", "rejection_reason", "rejection_stage",
              "warnings")),
    ("order_intent", INTENT_FIELDS + ("gate_outcome", "fate", "gate_state")),
)


def axis_value(row: dict, field: str) -> Any:
    """قيمةُ حقلٍ في محور — و`__kind__` يُشتقّ من `saw` لا يُقرأ من السجلّ."""
    if field == "__kind__":
        return cycle_kind(row)
    return row.get(field)


def compare_axes(left: dict[str, dict], right: dict[str, dict]) -> dict[str, Any]:
    """يقارن محورًا محورًا — حرفيًّا، بلا تسويةٍ صامتة ولا إسقاطِ صفٍّ مخالف.

    ختم `NQ — GATE B`: العدّ والهويّة والصنف والقرار والمخاطر ونيّة الأمر،
    كلٌّ برقمه. و`self_comparison` يُرفَع حين يكون الجانبان زمنَ تشغيلٍ واحدًا
    — فمقارنةُ سجلٍّ بنفسه لا تُثبت شيئًا.
    """
    runtimes = {str(r.get("runtime") or "") for r in left.values()}
    runtimes |= {str(r.get("runtime") or "") for r in right.values()}
    shared = sorted(set(left) & set(right))
    axes: dict[str, dict[str, Any]] = {}
    for axis, fields in AXES:
        slot: dict[str, Any] = {"mismatches": 0, "by_field": {},
                                "example": None}
        for key in shared:
            a, b = left[key], right[key]
            for field in fields:
                if axis_value(a, field) != axis_value(b, field):
                    slot["mismatches"] += 1
                    slot["by_field"][field] = slot["by_field"].get(field, 0) + 1
                    if slot["example"] is None:
                        slot["example"] = {
                            "cycle_id": key, "field": field,
                            "left": axis_value(a, field),
                            "right": axis_value(b, field)}
        axes[axis] = slot
    total = sum(slot["mismatches"] for slot in axes.values())
    return {
        "output_count_left": len(left),
        "output_count_right": len(right),
        "output_count_match": len(left) == len(right),
        "shared": len(shared),
        "only_left": sorted(set(left) - set(right))[:20],
        "only_left_count": len(set(left) - set(right)),
        "only_right": sorted(set(right) - set(left))[:20],
        "only_right_count": len(set(right) - set(left)),
        "axes": axes,
        "mismatches": total,
        "self_comparison": (left is right) or len(runtimes) < 2,
    }


def format_axes(result: dict[str, Any]) -> str:
    lines = [
        "output_count   A=%d  B=%d  %s" % (
            result["output_count_left"], result["output_count_right"],
            "متطابق" if result["output_count_match"] else "⛔ مختلف"),
        "مشترك          %d · في A فقط %d · في B فقط %d" % (
            result["shared"], result["only_left_count"],
            result["only_right_count"]),
        "self_comparison %s" % result["self_comparison"],
        "",
    ]
    for axis, _fields in AXES:
        slot = result["axes"][axis]
        mark = "✅" if not slot["mismatches"] else "⛔"
        lines.append("  %s %-16s mismatches = %d" % (mark, axis, slot["mismatches"]))
        if slot["example"]:
            example = slot["example"]
            lines.append("       %s: %r ⟵ %r  (%s)" % (
                example["field"], example["left"], example["right"],
                str(example["cycle_id"])[-34:]))
    lines.append("")
    lines.append("مجموع الاختلافات = %d" % result["mismatches"])
    return "\n".join(lines)


def cycle_kind(row: dict) -> str:
    """دورةُ قرارٍ إن وصلها `decision.approved.state`، وإلّا دورةُ بوّابة."""
    return KIND_DECISION if "approved" in (row.get("saw") or ()) else KIND_GATE


def coverage(rows: dict[str, dict]) -> dict[str, Any]:
    """كم دورةً تحمل بيانات قرارٍ فعليّة — **حارسُ عمى البوّابة**.

    مرجعٌ نصفُ دوراته حقولُ قرارها `null` يُعلن «تكافؤًا» على لا شيء:
    `null == null` يمرّ دائمًا. فالتغطية تُقاس وتُعرَض قبل أيّ حكمٍ بالتكافؤ،
    ومن يقرأ الحكم يعرف على كم قُيس.
    """
    total = len(rows)
    decision = [r for r in rows.values() if cycle_kind(r) == KIND_DECISION]
    gate = [r for r in rows.values() if cycle_kind(r) == KIND_GATE]
    d_room = sum(1 for r in decision if r.get("signal") is not None)
    g_room = sum(1 for r in gate if r.get("signal") is not None)
    with_approval = sum(1 for r in rows.values() if r.get("approved") is not None)
    with_tick = sum(1 for r in rows.values() if r.get("tick_bid") is not None)
    incomplete = sum(1 for r in rows.values() if r.get("incomplete"))
    return {
        "cycles": total,
        # ── مسار القرار: عليه وحده تُحكَم البوّابة ──────────────────────
        "decision_cycles": len(decision),
        "decision_room_coverage": (round(d_room / len(decision), 4)
                                   if decision else 0.0),
        "blind_decision_cycles": len(decision) - d_room,
        # ── تعريف المالك ٢٠٢٦-٠٩-١٨: لا يُدّعى أنّ الحدث وصل، بل يُثبَت
        #    **لماذا لم يصل**. فالصمت المقصود يُفصَل عن الصمت المجهول.
        #    ⚠️ و`room_cut_unchanged` يبقى صفرًا ما لم توجد علامةٌ تُثبته —
        #    والمقيس ٢٠٢٦-٠٩-١٨ أنّ `cutoff` **لا يقطع** `decision.room.state`
        #    أصلًا (`top_cut` لا يذكره · دلتا ١٥٠ ث = صفر). فما لا دليل عليه
        #    يبقى `room_missing`، ولا يُنقل إلى خانةٍ مبرَّرة بلا إثبات.
        "room_received": d_room,
        "room_cut_unchanged": sum(1 for r in decision
                                  if r.get("room_cut_reason")),
        "room_missing": sum(1 for r in decision
                            if r.get("signal") is None
                            and not r.get("room_cut_reason")),
        # ── مسار البوّابة: يُقاس مستقلًّا ولا يُحوَّل إلى فشلِ تغطية ──────
        "gate_cycles": len(gate),
        "gate_only": sum(1 for r in gate
                         if set(r.get("saw") or ()) <= {"gate"}),
        "gate_with_room": g_room,
        "duplicate_gate_cycles": 0,      # يُملأ من تقرير القراءة
        # ── مشتركٌ بين المسارين ────────────────────────────────────────
        "approval_coverage": round(with_approval / total, 4) if total else 0.0,
        "tick_coverage": round(with_tick / total, 4) if total else 0.0,
        "incomplete": incomplete,
    }


#: شروط إغلاق GATE 1 كما ختمها المالك ٢٠٢٦-٠٩-١٨ — لا واحدٌ منها يُساوَم.
CLOSURE_CRITERIA = (
    ("duplicate_cycle_ids", "duplicate_cycle_ids"),
    ("incomplete", "incomplete"),
    ("approval_coverage", "approval_coverage"),
    ("vacuous_matches", "null==null (هويّة وموافقة)"),
    ("mutation_guards", "mutation guards"),
    ("self_comparison", "self_comparison = false"),
    ("replay_identical", "outputs A == outputs B"),
)


def closure(rows: dict[str, dict], *, load_report: dict | None = None,
            replay_result: dict | None = None,
            mutation_caught: int = 0, mutation_total: int = 21) -> dict[str, Any]:
    """هل أُغلقت GATE 1؟ سبعةُ شروطٍ بالرقم، ولا حكم إلّا باجتماعها.

    ## ما تُثبته البوّابة — وما لا تُثبته (ختم المالك ٢٠٢٦-٠٩-١٨)

    تُثبت أنّ المرجع **صالحٌ للحكم**: هويّةُ الدورة واحدةٌ ومصيرُها واحد،
    والموافقة تصل كاملةً، والحرّاس تكشف العطب المتعمَّد، والمرجع **حتميّ**
    — نفسُ الشريط يعطي نفسَ المخرجات حرفًا.

    ولا تُثبت تكافؤ محرّكين؛ ذاك قبولُ §٥ لا إغلاقُ GATE 1، وإلّا صارت
    الحلقة: البوّابة تنتظر §٥ و§٥ ينتظر البوّابة.

    ⚠️ و`replay_result` **مقارنةُ إعادتين** لا مقارنةُ سجلٍّ بنفسه. فإن
    جاءت `self_comparison` صحيحةً سقط الشرطان معًا.
    """
    cov = coverage(rows)
    dupes = int((load_report or {}).get("duplicate_cycle_ids", 0))
    rep = replay_result or {}
    self_cmp = bool(rep.get("self_comparison", True))
    shared = int(rep.get("shared", 0))
    identical = int(rep.get("identical", 0))
    ratio = (round(identical / shared, 4) if shared else 0.0)
    drift = (int(rep.get("differing", 0)) + int(rep.get("only_left_count", 0))
             + int(rep.get("only_right_count", 0)))
    vacuous = int(rep.get("vacuous_matches", 0))
    checks = {
        "duplicate_cycle_ids": (dupes, 0, dupes == 0),
        "incomplete": (cov["incomplete"], 0, cov["incomplete"] == 0),
        "approval_coverage": (cov["approval_coverage"], 1.0,
                              cov["decision_cycles"] > 0
                              and cov["approval_coverage"] >= 1.0),
        # الفراغ يُقاس على الهويّة والموافقة وحدهما — حقول الغرفة خرجت من
        # الشرط لأنّ قناتها مدموجةٌ بالعقد، لا لأنّ الفراغ صار مقبولًا.
        "vacuous_matches": (vacuous, 0,
                            replay_result is not None and vacuous == 0),
        "mutation_guards": ("%d/%d" % (mutation_caught, mutation_total),
                            "%d/%d" % (mutation_total, mutation_total),
                            mutation_total > 0 and mutation_caught >= mutation_total),
        # ⛔ لا إغلاق بمقارنةِ سجلٍّ بنفسه: ذاك يُعطي تكافؤًا دائمًا.
        "self_comparison": (self_cmp, False,
                            replay_result is not None and not self_cmp),
        "replay_identical": ("%s (%d/%d · انحراف %d)"
                             % (ratio, identical, shared, drift), 1.0,
                             shared > 0 and ratio >= 1.0 and drift == 0),
    }
    return {"cycles": cov["cycles"], "coverage": cov, "checks": checks,
            "closed": all(ok for _m, _l, ok in checks.values())}


def format_closure(result: dict[str, Any]) -> str:
    cov = result.get("coverage") or {}
    lines = ["شروط إغلاق GATE 1 — %d دورة (%d قرار · %d بوّابة)\n"
             % (result["cycles"], cov.get("decision_cycles", 0),
                cov.get("gate_cycles", 0))]
    for key, label in CLOSURE_CRITERIA:
        measured, limit, ok = result["checks"][key]
        lines.append("  %-4s %-32s المقيس=%-10s الحدّ=%s"
                     % ("✅" if ok else "⛔", label, measured, limit))
    if cov:
        lines += ["",
                  "الغرفة — قناةُ حالةٍ مدموجة، تُقاس ولا يُحكَم بها:",
                  "  room_received          %d" % cov.get("room_received", 0),
                  "  room_absent            %d   (دُمجت بحالةٍ أحدث لنفس Account×Symbol)"
                  % cov.get("room_missing", 0),
                  "",
                  "مسار البوّابة — يُقاس ولا يُحكَم به:",
                  "  gate_cycles            %d" % cov.get("gate_cycles", 0),
                  "  gate_only              %d" % cov.get("gate_only", 0),
                  "  gate_with_room         %d" % cov.get("gate_with_room", 0),
                  "  duplicate_gate_cycles  %d" % cov.get("duplicate_gate_cycles", 0)]
    lines.append("\nالحكم: %s" % ("✅ GATE 1 مغلقة — يُفتح §5"
                                  if result["closed"] else
                                  "⛔ GATE 1 غير مغلقة — لا يُفتح §5"))
    return "\n".join(lines)


def format_report(result: dict[str, Any]) -> str:
    """تقريرٌ يُقرأ بالعين — رقمٌ أوّلًا ثمّ التصنيف."""
    lines = [
        "سجلّ المرجع  = %d دورة" % result["left_total"],
        "سجلّ الجديد  = %d دورة" % result["right_total"],
        "مشترك        = %d" % result["shared"],
        "متطابق       = %d" % result["identical"],
        "مختلف        = %d" % result["differing"],
        "في المرجع فقط = %d" % result["only_left_count"],
        "في الجديد فقط = %d" % result["only_right_count"],
        "",
        "الحكم: %s" % ("✅ تكافؤ تامّ" if result["parity"]
                       else "⛔ لا تكافؤ — الاختلاف مصنّفٌ أدناه"),
    ]
    if result["by_field"]:
        lines += ["", "%-22s %-12s %-8s %s" % ("الحقل", "الفئة", "مرّات", "مثال")]
        for field, slot in result["by_field"].items():
            example = slot["example"] or {}
            lines.append("%-22s %-12s %-8d %s ⟵ %s  (%s)" % (
                field, slot["group"], slot["count"],
                json.dumps(example.get("left"), ensure_ascii=False)[:28],
                json.dumps(example.get("right"), ensure_ascii=False)[:28],
                str(example.get("cycle_id"))[:44]))
    return "\n".join(lines)
