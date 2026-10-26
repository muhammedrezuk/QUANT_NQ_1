#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""حارس حقول اللوحة — يكشف «حقلًا تقرؤه اللوحة ولا ينشره ناشره».

لماذا هذا الحارس موجود
======================
أغلى كذبتين وقعتا على لوحة المالك كانتا من نوعٍ واحد:

* ``kill_switch_state`` — انتقل إلى ``accounts[<رقم>].risk`` واللوحة تقرؤه من
  الجذر، فبقي قاطع الأمان يظهر «سليمًا» أبدًا مهما ارتفع.
* ``floating_pnl`` — تقرؤه اللوحة من ``platform.positions.state`` وناشره
  ``portfolio.pnl.state``، فبقي «ربح مفتوح 0.00» وقيمة الحساب تفوق الرصيد.

وكلتاهما **تمرّان من كل الاختبارات ومن ``tsc`` سليمتين**: النوع مُعلَن في
اللوحة، والحقل غائب في الحمولة، و``undefined`` يُقرأ صفرًا أو «سليمًا». لا
يكشفهما إلّا مقارنة ما تقرؤه اللوحة بما ينشره الكود فعلًا — وهذا عمل هذا الملفّ.

قاعدة الصدق في الأداة نفسها
===========================
الأداة لا تدّعي يقينًا لا تملكه. لكل حدث حكمٌ من ثلاثة:

* ``مؤكَّد``    — كل مواضع النشر قواميس حرفيّة، فغياب المفتاح غيابٌ حقيقيّ.
* ``غير مؤكَّد`` — موضع نشرٍ فيه ``**`` أو بناءٌ ديناميكيّ، فلا يصحّ الجزم.
* ``بلا ناشر``  — لا مانيفست يعلن نشره (قد يكون مدخلًا خارجيًّا).

ولا يُعلَن خرقٌ إلّا على ``مؤكَّد``. وما عداه يُدرَج «يحتاج عينًا» بالاسم، لا
يُبتلع صمتًا ولا يُرفع إنذارًا كاذبًا. وهذا هو الفرق بين حارسٍ يُوثَق به
وحارسٍ يُعلَّم تجاهله.
"""
from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# الحارس نفسه يجب أن يُسمَع: طرفيّة ويندوز هنا cp1256 فتُسقط الرموز، وقد
# انفجر `check_events.py` قبل عرض ما وجده. الإخراج يُفرض UTF-8 أوّلًا.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

UI_SRC = ROOT / "governance" / "ui" / "src"
ATOMS = ROOT / "atoms"

# أنواع لا تُعلن حقولًا (قواميس عامّة) — تُقرأ حقولها من الاستعمال لا من النوع.
GENERIC_TYPES = {"Payload", "Record<string,unknown>", "Record<string,any>", "unknown", "any"}

# ─── ما فُحص باليد وثبت نشره، مع موضع الدليل ───
#
# هذه أحداثٌ يبني ناشرها حمولته من متغيّر، فلا تستطيع الأداة الجزم. فُحصت
# واحدًا واحدًا في كود ناشرها يوم ٢٠٢٦-٠٩-١٦، وتُذكر هنا **بموضع الدليل** لا
# بكلمة «موثوق»: من شكّ فليفتح السطر. وهذا ليس إسكاتًا — تبقى معروضة في
# التقرير موسومةً «مقيسة»، ولا تُرفع خرقًا.
VERIFIED = {
    ("execution.reference_divergence.state", "classification"):
        "582/atom.py:269-366 — {**base, 'classification': …} في كل المسارات",
    # ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): خرج («horizon.profile.state»،
    # «formula_version») — اللوحة لم تعد تقرؤه، وناشره (ظلّ شخصيّة الأفق في 523) أُرشف.
    ("measurement.latency.state", "p99_ms"):
        "820/atom.py:164-176 — {'section': …, **latency} و latency فيه p99_ms",
    ("platform.account.state", "balance"): "619/atom.py:173",
    ("platform.account.state", "equity"): "619/atom.py:173",
    ("platform.account.state", "margin"): "619/atom.py:173",
    ("platform.account.state", "free_margin"): "619/atom.py:173",
    ("platform.account.state", "leverage"): "619/atom.py:173",
    ("system.alert.state", "alerts"): "831/atom.py:209",
    ("system.alert.state", "total"): "831/atom.py:208",
    # ٢٠٢٦-٠٩-١٨ — حقول سجلّ الأوامر، فُحصت في كود ناشرها قبل عرضها على
    # «شو صاير» و«التنفيذ». الناشر يمرّر `body` كاملًا فلا تجزم الأداة.
    ("trading.final_decision", "reward_risk_ratio"):
        "552/atom.py:500-502 — body['reward_risk_ratio'] ثمّ publish(EVENT_FINAL, body) بالسطر 506",
    ("trading.final_decision", "risk_dollars"):
        "552/atom.py:503-505 — body['risk_dollars'] قبل النشر بسطرٍ واحد",
    ("trading.final_decision", "risk_budget"):
        "551/atom.py:127 — ضمن _DIRECT_FIELDS فيعبر إلى جسد الأمر كما هو",
    ("trading.final_decision", "reward_risk_min"):
        "552/atom.py:515 — بلا شرط قبل النشر بسطرين (صفرٌ = لا حارس للنسبة)",
    ("trading.final_decision", "risk_budget_bounds"): "552/atom.py:516 — بلا شرط",
    ("execution.order.rejected", "rejection"): "552/atom.py:338-340",
    ("execution.order.rejected", "barrier"): "552/atom.py:326-327",
    ("execution.order.rejected", "stage"): "552/atom.py:325",
    ("execution.order.rejected", "reason"): "552/atom.py:325",
    ("execution.order.rejected", "volume"): "552/atom.py:322 عبر _ORDER_FIELDS",
    ("execution.order.rejected", "reference_price"): "552/atom.py:322 عبر _ORDER_FIELDS",
    ("execution.order.rejected", "stop_loss"): "552/atom.py:322 عبر _ORDER_FIELDS",
    ("execution.order.rejected", "take_profit"): "552/atom.py:322 عبر _ORDER_FIELDS",
    ("execution.order.built", "reward_risk"): "551/atom.py:926 — وهو عيارٌ ثابت لا نسبة الأمر",
    # نتيجة الصفقة: **ناشران** لهذا الحدث، وشكلاهما مختلفان. الحقول الثمانية
    # كلُّها من ٥٦٣ لا من ٥١٧ — و٥١٧ ينشر `pnl`/`gross_pnl` ولا ينشر `profit`
    # ولا الجهة ولا الأسعار. فمن قرأها ظنًّا أنّها من ٥١٧ يقرأ غيابًا.
    ("market.outcome.realized", "profit"): "563/atom.py:261 — body قاموس حرفيّ يُنشر بالسطر 274",
    ("market.outcome.realized", "side"): "563/atom.py:264",
    ("market.outcome.realized", "volume"): "563/atom.py:265",
    ("market.outcome.realized", "entry_price"): "563/atom.py:266",
    ("market.outcome.realized", "exit_price"): "563/atom.py:267",
    ("market.outcome.realized", "event_type"): "563/atom.py:268",
    ("market.outcome.realized", "reason"): "563/atom.py:268",
    ("market.outcome.realized", "ticket"): "563/atom.py:269",
    # ٢٠٢٦-١٠-٠٥ (ختم المالك «NQ وأبنيها»): بطاقة «ميزانيّة الأصول» — فُحص ناشراها قبل العرض.
    ("risk.asset_ledger.state", "ledgers"):
        "518/atom.py:487 — {'ledgers': ledgers, …} من _ledger_payload المنشورة بالسطر 492",
    ("asset.portfolio.state", "portfolios"):
        "519/atom.py:261-268 — self._last = {'portfolios': …} ثمّ publish(EVENT_OUT, self._last)",
    ("asset.portfolio.state", "halted_accounts"):
        "519/atom.py:264 و341-346 — في المسارين: الدفتر وإعادة نشر النيّة",
}

# حقول ظرف النقل يضيفها الناقل لا الذرّة — وجودها في اللوحة ليس خرقًا.
ENVELOPE_FIELDS = {
    "timestamp", "received_at", "event_name", "name", "component", "source",
    "stream_sequence", "dropped_total", "stream_gap", "seq", "ts", "emitted_at",
    "published_at", "account_id", "broker", "symbol", "read_only",
}


# ─────────────────────────── جانب اللوحة ───────────────────────────

READ_RE = re.compile(
    r"(?:const|let)\s+(?P<var>[A-Za-z_]\w*)\s*=\s*"
    r"(?:useStore\(\s*\((?:s)\)\s*=>\s*)?"
    r"(?:s\.)?(?P<map>symbolStreams|streams)\[['\"](?P<event>[a-zA-Z][\w.]+)['\"]\]\s*\)?"
    r"(?:\s*as\s+(?P<cast>[^\n]+?))?\s*$",
    re.MULTILINE,
)

IFACE_RE = re.compile(
    r"(?:interface\s+(?P<iname>[A-Za-z_]\w*)\s*\{(?P<ibody>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\}"
    r"|type\s+(?P<tname>[A-Za-z_]\w*)\s*=\s*\{(?P<tbody>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\})",
    re.MULTILINE,
)

FIELD_RE = re.compile(r"(?:^|[{;,\n])\s*(?P<f>[A-Za-z_]\w*)\s*\??\s*:")


# ─── الطريق الثاني: أحداثٌ تُصبّ في سجلٍّ مكتوبٍ بنوعٍ واحد ───
#
# ٢٠٢٦-٠٩-١٨ — ثغرةٌ في هذا الحارس نفسه، كشفَها أنّي كدتُ أقع فيها: أضفتُ
# حقلين إلى `ExecOrderRec` وقرأتُهما في صفحتين، **وخرج الحارس أخضر** — لأنّه
# لا يرى إلّا `streams['<حدث>']`. وهذه السجلّات تُملأ في `engine.ts` بنشر
# الحمولة كما هي:
#
#     if (name === 'trading.final_decision') st.pushExecOrder({ ...(payload …
#
# فالحقل يصل الشاشة من حدثٍ لا يُسمّى عند القراءة. وقد كتبتُ فعلًا
# `value` و`threshold` في الجذر وهما داخل `rejection` — كذبةٌ كانت ستعيش
# صامتةً: بطاقةٌ تقول «انرفض» بلا رقمٍ أبدًا.
#
# القاعدة هنا **اتّحاد** لا تقاطع: حقلٌ واحد يكفيه ناشرٌ واحد من روافد
# السجلّ، لأنّ `kind` يفرّق بينها. وما لا ينشره أيُّ رافدٍ لا مصدر له البتّة.
SINK_RE = re.compile(
    r"name\s*===\s*['\"](?P<event>[a-zA-Z][\w.]+)['\"]\s*\)\s*"
    r"(?:st|useStore\.getState\(\))\.(?P<sink>push[A-Za-z]\w*)\(\s*\{\s*\.{3}\(?\s*payload"
)
SINK_TYPE_RE = re.compile(
    r"(?P<sink>push[A-Za-z]\w*)\s*:\s*\(\s*\w+\s*:\s*(?P<type>[A-Za-z_]\w*)\s*\)"
)
# يضيفها المحرّك نفسه وقت الصبّ، لا الذرّة — فليست خرقًا.
SYNTHETIC_RECORD_FIELDS = {"kind"}


BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT_RE = re.compile(r"(?<!:)//[^\n]*")


def strip_comments(text: str) -> str:
    """يُسقط التعليقات قبل قراءة «الاستعمال الفعليّ».

    ٢٠٢٦-٠٩-١٦: بعد إصلاح خرقَين كاذبَين، بقي ثالث: الأداة قرأت **تعليقي أنا**
    الذي يشرح الخطأ (``pick(proposed, ['state','status','decision'])``) فحسبته
    استعمالًا قائمًا. أي أنّ توثيق الإصلاح كان يُبقي الإنذار مرفوعًا إلى الأبد.
    وحارسٌ يشتكي من شرحِ إصلاحه يُطفأ، فلا يُصلَح بتغيير التعليق بل بتصحيح
    الأداة. (``(?<!:)`` يمنع قصّ ``https://``.)
    """
    return LINE_COMMENT_RE.sub(" ", BLOCK_COMMENT_RE.sub(" ", text))


def _top_level_only(body: str) -> str:
    """يُسقط كل ما بداخل أقواس متداخلة — تبقى مفاتيح المستوى الأوّل وحدها.

    ٢٠٢٦-٠٩-١٦: أوّل تشغيل للأداة رفع خرقًا كاذبًا على ``dial.profile.state``
    (``dial`` و``hedge_target``)، وهما حقلان **داخل** ``profiles[]`` لا في جذر
    الحمولة. الأداة كانت تقرأ العمق كأنّه سطح. وحارسٌ يرفع كاذبًا مرّة يُعلَّم
    تجاهله إلى الأبد، فالتصحيح قبل أيّ حكم على المقيس.
    """
    out: list[str] = []
    depth = 0
    for ch in body:
        if ch in "{<([":
            depth += 1
            continue
        if ch in "}>)]":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def _fields_of_body(body: str) -> set[str]:
    return {m.group("f") for m in FIELD_RE.finditer(_top_level_only(body))}


def collect_ui_types(files: list[Path]) -> dict[str, set[str]]:
    """كل نوع مُعلَن في الواجهة وحقوله — تُجمع من الملفّات كلّها مرّة واحدة."""
    types: dict[str, set[str]] = {}
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in IFACE_RE.finditer(text):
            name = m.group("iname") or m.group("tname")
            body = m.group("ibody") or m.group("tbody") or ""
            if name:
                types.setdefault(name, set()).update(_fields_of_body(body))
    return types


def _scope_after(text: str, start: int) -> str:
    """نطاق الدالّة الحاوية للقراءة — من موضعها إلى أوّل ``}`` بأوّل السطر.

    ٢٠٢٦-٠٩-١٦: الأداة رفعت خرقًا رابعًا كاذبًا على ``horizon.profile.state``
    (``approvable`` · ``status`` · ``value``). والسبب أنّها تمسح **الملفّ كلّه**
    بحثًا عن ``p.<حقل>``، وفي ``Settings.tsx`` متغيّرٌ آخر اسمه ``p`` داخل
    ``params.filter((p) => p.approvable)`` بعد ثلاثمئة سطر — لا علاقة له
    بالحدث. فصار المسح محصورًا بنطاق الدالّة الحاوية. (تقريبٌ يعتمد تنسيق
    هذا المشروع: نهاية الدالّة ``}`` بأوّل السطر.)
    """
    end = re.search(r"\n\}", text[start:])
    return text[start: start + (end.end() if end else len(text) - start)]


def _cast_fields(cast: str, types: dict[str, set[str]], var: str, text: str) -> tuple[set[str], str]:
    """حقول ما تعتقده اللوحة عن الحدث، ومن أين عُرفت."""
    cast = (cast or "").strip().rstrip(";")
    cast = re.sub(r"\|\s*undefined\s*$", "", cast).strip()
    flat = cast.replace(" ", "")

    if cast.startswith("{"):
        return _fields_of_body(cast), "نوع مضمَّن"

    if cast and flat not in GENERIC_TYPES and re.fullmatch(r"[A-Za-z_]\w*", cast):
        if cast in types:
            return set(types[cast]), f"النوع {cast}"
        return set(), "نوع غير معروف"

    # قاموس عامّ: الحقول تُقرأ من الاستعمال الفعليّ للمتغيّر في الملفّ نفسه.
    #
    # ٢٠٢٦-٠٩-١٦: `\b` وحدها كانت تلتقط الاسم **داخل نصّ اسم الحدث نفسه** —
    # فـ`'adaptation.limits.state'` أعطت المتغيّر `limits` حقلًا وهميًّا اسمه
    # `state`، ورُفع خرقٌ كاذب. الحدّ الآن يمنع سبقَ حرفٍ أو نقطةٍ أو علامة
    # اقتباس، فلا يُقرأ جزءُ نصٍّ استعمالًا.
    edge = rf"(?<![\w.'\"]){re.escape(var)}"
    used: set[str] = set()
    used.update(re.findall(rf"{edge}\??\.([A-Za-z_]\w*)", text))
    used.update(re.findall(rf"{edge}\??\[['\"]([A-Za-z_]\w*)['\"]\]", text))
    for lst in re.findall(rf"pick\(\s*{re.escape(var)}\s*,\s*\[([^\]]*)\]", text):
        used.update(re.findall(r"['\"]([A-Za-z_]\w*)['\"]", lst))
    return used, "الاستعمال الفعليّ"


def scan_ui() -> dict[str, dict[str, set[str]]]:
    files = sorted(p for p in UI_SRC.rglob("*.ts*") if p.is_file())
    types = collect_ui_types(files)
    reads: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for path in files:
        text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for m in READ_RE.finditer(text):
            event = m.group("event")
            fields, origin = _cast_fields(
                m.group("cast") or "", types, m.group("var"), _scope_after(text, m.start()))
            rel = path.relative_to(ROOT).as_posix()
            for f in fields - ENVELOPE_FIELDS:
                reads[event][f].add(f"{rel} ({origin})")
    return reads


def scan_record_sinks() -> list[tuple[str, str, set[str], set[str]]]:
    """(اسم النوع · اسم الصبّ · الأحداث الرافدة · حقول النوع) لكل سجلٍّ مُصبّ."""
    files = sorted(p for p in UI_SRC.rglob("*.ts*") if p.is_file())
    types = collect_ui_types(files)
    feeders: dict[str, set[str]] = defaultdict(set)
    sink_type: dict[str, str] = {}
    for path in files:
        text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for m in SINK_RE.finditer(text):
            feeders[m.group("sink")].add(m.group("event"))
        for m in SINK_TYPE_RE.finditer(text):
            sink_type.setdefault(m.group("sink"), m.group("type"))
    out: list[tuple[str, str, set[str], set[str]]] = []
    for sink, events in sorted(feeders.items()):
        tname = sink_type.get(sink)
        fields = types.get(tname or "", set())
        if not tname or not fields:
            continue
        out.append((tname, sink, events, fields - ENVELOPE_FIELDS - SYNTHETIC_RECORD_FIELDS))
    return out


# ─────────────────────────── جانب الذرّات ───────────────────────────

def publishers_by_event() -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = defaultdict(list)
    for mf in sorted(ATOMS.glob("*/*/manifest.yaml")):
        try:
            data = yaml.safe_load(mf.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for ev in data.get("publishes") or []:
            out[str(ev)].append(mf.parent / "atom.py")
    return out


def _const_map(tree: ast.AST) -> dict[str, str]:
    consts: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    consts[tgt.id] = node.value.value
    return consts


def payload_keys(atom_py: Path) -> dict[str, tuple[set[str], bool]]:
    """لكل حدث ينشره هذا الملفّ: مفاتيحه الحرفيّة، وهل فيه بناءٌ غير حرفيّ."""
    try:
        tree = ast.parse(atom_py.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return {}
    consts = _const_map(tree)
    found: dict[str, tuple[set[str], bool]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "publish"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            event = first.value
        elif isinstance(first, ast.Name) and first.id in consts:
            event = consts[first.id]
        else:
            continue
        keys: set[str] = set()
        dynamic = True
        if len(node.args) > 1 and isinstance(node.args[1], ast.Dict):
            payload = node.args[1]
            dynamic = False
            for k in payload.keys:
                if k is None:                       # **spread — بناء غير حرفيّ
                    dynamic = True
                elif isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
                else:
                    dynamic = True
        prev_keys, prev_dyn = found.get(event, (set(), False))
        found[event] = (prev_keys | keys, prev_dyn or dynamic)
    return found


# ─────────────────────────── الحكم ───────────────────────────

def main() -> int:
    reads = scan_ui()
    pubs = publishers_by_event()

    breaches: list[str] = []
    needs_eye: list[str] = []
    verified: list[str] = []
    no_publisher: list[str] = []
    checked = 0

    for event in sorted(reads):
        atoms = pubs.get(event) or []
        if not atoms:
            no_publisher.append(event)
            continue
        keys: set[str] = set()
        dynamic = False
        for atom_py in atoms:
            ev_keys, ev_dyn = payload_keys(atom_py).get(event, (set(), True))
            keys |= ev_keys
            dynamic = dynamic or ev_dyn
        checked += 1
        missing = [f for f in sorted(reads[event]) if f not in keys]
        for f in [f for f in missing if (event, f) in VERIFIED]:
            verified.append(f"{event}.{f} — {VERIFIED[(event, f)]}")
        missing = [f for f in missing if (event, f) not in VERIFIED]
        if not missing:
            continue
        where = " · ".join(sorted({w for f in missing for w in reads[event][f]}))
        line = f"{event} ← {', '.join(missing)}   [{where}]"
        (needs_eye if dynamic else breaches).append(line)

    # ─── السجلّات المُصبّة: حقلُ النوع يحتاج رافدًا واحدًا ينشره ───
    sinks = scan_record_sinks()
    sink_lines: list[str] = []
    for tname, sink, events, fields in sinks:
        union: set[str] = set()
        dyn_events: list[str] = []
        for event in sorted(events):
            for atom_py in pubs.get(event) or []:
                ev_keys, ev_dyn = payload_keys(atom_py).get(event, (set(), True))
                union |= ev_keys
                if ev_dyn:
                    dyn_events.append(event)
        if not union and not dyn_events:
            continue
        missing = sorted(f for f in fields if f not in union)
        # حقلٌ فُحص بيدي في كود ناشره يُذكر بموضع دليله لا يُسكَت.
        for f in [f for f in missing if any((e, f) in VERIFIED for e in events)]:
            src = next(VERIFIED[(e, f)] for e in sorted(events) if (e, f) in VERIFIED)
            verified.append(f"{tname}.{f} — {src}")
        missing = [f for f in missing if not any((e, f) in VERIFIED for e in events)]
        if not missing:
            continue
        mark = "؟" if dyn_events else "❌"
        line = (f"{tname} (عبر {sink}) ← {', '.join(missing)}"
                f"   [الروافد: {' · '.join(sorted(events))}]")
        (sink_lines if dyn_events else breaches).append(f"{mark} {line}")

    print("حارس حقول اللوحة — ما تقرؤه اللوحة مقابل ما ينشره الكود")
    print(f"أحداثٌ تقرؤها اللوحة: {len(reads)} · منها بناشرٍ مُعلَن: {checked}")
    print(f"سجلّات مُصبّة من أحداث: {len(sinks)}")
    print()

    if sink_lines:
        print(f"سجلّات — حقولٌ بلا رافدٍ ينشرها ({len(sink_lines)}):")
        for line in sink_lines:
            print(f"  {line}")
        print()

    if no_publisher:
        print(f"أحداث بلا ناشر مُعلَن ({len(no_publisher)}) — مدخلات خارجيّة أو نشرٌ غير مصرَّح:")
        for ev in no_publisher:
            print(f"  · {ev}")
        print()

    if verified:
        print(f"مقيسة باليد ({len(verified)}) — ناشرها ديناميكيّ وفُحص سطرُه:")
        for line in sorted(verified):
            print(f"  ✓ {line}")
        print()

    if needs_eye:
        print(f"يحتاج عينًا ({len(needs_eye)}) — الناشر يبني حمولته ديناميكيًّا، فلا جزم:")
        for line in needs_eye:
            print(f"  ؟ {line}")
        print()

    if breaches:
        print(f"❌ حقول تُقرأ ولا تُنشَر ({len(breaches)}) — الناشر قاموس حرفيّ، فالغياب يقين:")
        for line in breaches:
            print(f"  ❌ {line}")
        return 1

    print("✅ لا حقل تقرؤه اللوحة من ناشرٍ حرفيٍّ لا ينشره.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
