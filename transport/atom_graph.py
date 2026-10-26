"""رسم خريطة أحداث الذرّات — من ينتج ماذا، ومن يستهلكه، وأين الحدّ.

هذه الوحدة في `transport/` لا في `tools/` عمدًا: **الإقلاع يشتقّ منها حدّ
العملية**، وكود الإنتاج لا يستورد من أدوات التشخيص.

قرار المالك ٢٠٢٦-٠٩-١٠: «ما يعبر العمليات = أقل معلومة لازمة للقرار»،
و«لا نكرر خطأ 160» — فالحدّ يُشتقّ من الرسم البيانيّ لا يُكتب قائمةً تَنسى.

المقيس على هذه الشجرة:

    مستضاف                     يُنتَج   يعبر
    قسم التحليل 150-199          16      4
    + البنية والسيولة 200-299    35      7
    + 300-399                    77     16
    + القرار 400-499            103     16     ⟵ 85% يبقى داخلًا
    كلّ القابل للتقسيم (173)    237     43     ⟵ أسوأ

فالحدّ ليس «استضِف كلّ ما يُقسَّم» — بل حيث يقلّ العبور.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

#: بنى تدلّ على اعتماد الترتيب: تاريخٌ أو «السابق».
ORDER_MARKS = ("deque(", "prev_", "_prev", "last_", "_last", "history",
               "_window", "rolling")

class _AtomScan(ast.NodeVisitor):
    """يمسح شجرة ذرّة واحدة ويجمع الأدلّة — لا يحكم."""

    def __init__(self) -> None:
        self.subscribes: list[str] = []
        self.publishes: list[str] = []
        self.self_writes: set[str] = set()
        self.state_names: set[str] = set()
        #: قراءات حالة بمفتاحٍ يحمل صفةً من `self` — دليل عبور النطاق.
        self.cross_reads: list[str] = []
        self.consts: dict[str, str] = {}

    # ── جمع الثوابت النصّية لحلّ أسماء الأحداث ──────────────────────────
    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.consts[target.id] = node.value.value
        for target in node.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) \
               and target.value.id == "self":
                self.self_writes.add(target.attr)
                if isinstance(node.value, (ast.Dict, ast.DictComp)):
                    self.state_names.add(target.attr)
                elif isinstance(node.value, ast.Call):
                    called = getattr(node.value.func, "id", "") or \
                        getattr(node.value.func, "attr", "")
                    if called in {"dict", "defaultdict", "deque", "OrderedDict"}:
                        self.state_names.add(target.attr)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        target = node.target
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) \
           and target.value.id == "self":
            self.self_writes.add(target.attr)
            self.state_names.add(target.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr in ("subscribe", "subscribe_all") and node.args:
                self.subscribes.append(self._event(node.args[0]))
            elif func.attr == "publish" and node.args:
                self.publishes.append(self._event(node.args[0]))
            elif func.attr == "get" and isinstance(func.value, ast.Attribute):
                self._check_cross(func.value, node.args[0] if node.args else None)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
        if isinstance(node.value, ast.Attribute):
            self._check_cross(node.value, node.slice)
        self.generic_visit(node)

    # ── الأدلّة ─────────────────────────────────────────────────────────
    def _event(self, node: ast.AST) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self.consts.get(node.id, "?" + node.id)
        if isinstance(node, ast.Attribute):
            return "?" + node.attr
        return "?"

    def _check_cross(self, container: ast.Attribute, key: ast.AST | None) -> None:
        """مفتاحُ قراءةٍ يحمل `self.<صفة>` = قراءة نطاقٍ لا يأتي من الحمولة.

        هذا هو نمط 160 بعينه: `self._state.get((self._anchor, timeframe))`.
        """
        if key is None:
            return
        if not (isinstance(container.value, ast.Name) and container.value.id == "self"):
            return
        for node in ast.walk(key):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
               and node.value.id == "self":
                self.cross_reads.append("self.%s[… self.%s …]"
                                        % (container.attr, node.attr))
                return


def scan_atom(directory: Path) -> dict[str, Any]:
    scan = _AtomScan()
    source_all = ""
    for path in sorted(directory.rglob("*.py")):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        source_all += text
        try:
            scan.visit(ast.parse(text))
        except SyntaxError:
            return {"parse_failed": True}
    return {
        "parse_failed": False,
        "subscribes": sorted({s for s in scan.subscribes if s}),
        "publishes": sorted({p for p in scan.publishes if p}),
        "state_names": sorted(scan.state_names),
        "cross_reads": sorted(set(scan.cross_reads)),
        "order_marks": sorted({m for m in ORDER_MARKS if m in source_all}),
    }


def boundary_events(evidence: dict, hosted: set) -> dict:
    """أحداثٌ تُنتَج **داخل** مجموعة مستضافة ويستهلكها من هو **خارجها**.

    هذه وحدها هي التي يجب أن تعبر حدود العملية (قرار المالك ٢٠٢٦-٠٩-١٠:
    «ما يعبر العمليات = أقل معلومة لازمة للقرار»). وما لا يستهلكه إلّا
    ساكنُ العملية نفسها **يبقى داخلها**.

    ⛔ **وتُشتقّ ولا تُكتب بيد.** قائمةٌ يدويّة تَنسى حدثًا فيختفي مستهلِكه
    صامتًا — وهو أخطر من بطء: ذرّةٌ تنتظر ما لن يصل ولا تشتكي. وعند ١٢٠٠
    ذرّة تصير القائمة اليدويّة مستحيلة أصلًا.

    والمقيس على قسم التحليل (150-166): من ~١٧ حدثًا يُنتَج لكلّ شمعة،
    يعبر **أربعة** فقط — والباقي لا يستهلكه إلّا 150 داخل القسم.
    """
    hosted = {str(name) for name in hosted}
    produced_inside: dict[str, set[str]] = {}
    for name in hosted:
        for event in evidence.get(name, {}).get("publishes", []):
            produced_inside.setdefault(event, set()).add(name)

    crossing: dict[str, list[str]] = {}
    for name, item in evidence.items():
        if name in hosted:
            continue
        for event in item.get("subscribes", []):
            if event in produced_inside:
                crossing.setdefault(event, []).append(name)
    return {event: sorted(consumers) for event, consumers in sorted(crossing.items())}



CLASS_PURE = "PURE"
CLASS_STATEFUL = "STATEFUL"
CLASS_ORDER_SENSITIVE = "ORDER_SENSITIVE"
CLASS_DEPENDENT = "DEPENDENT"
CLASS_CROSS_SCOPE = "CROSS_SCOPE"
CLASS_PIPELINE = "PIPELINE"
CLASS_UNKNOWN = "UNKNOWN"

#: ترتيب الشدّة: الأشدّ يغلب عند اجتماع أكثر من سبب.
SEVERITY = (CLASS_CROSS_SCOPE, CLASS_DEPENDENT, CLASS_ORDER_SENSITIVE,
            CLASS_STATEFUL, CLASS_PIPELINE, CLASS_PURE, CLASS_UNKNOWN)



def classify(evidence: dict[str, Any], produced_elsewhere: set[str],
             sibling_events: set[str]) -> tuple[str, list[str]]:
    """يحكم من الأدلّة — و`UNKNOWN` حين لا يستطيع.

    ⚠️ **`DEPENDENT` نسبيّ لا مطلق.** أوّل صيغة من هذا الفاحص عدّت كلّ ذرّة
    تستهلك ناتج ذرّةٍ أخرى اعتماديّةً، فأعطت **183 من 237** — ومنها 151-165
    التي **أثبت القياس أنّها تُقسَّم** (تطابق 80/80 على ستّ عمليّات).

    والفرق الذي أسقط القاعدة الأولى: الذرّة التي تستهلك شمعةً ينتجها
    103 ليست معتمِدةً على «مجموعة أخرى» — هي **مرحلة تالية في الأنبوب**.
    و§١٣ تقصد الاعتماد على نتيجة تُحسَب **في الفَتَحة نفسها**: ذرّةٌ تنتظر
    ناتج زميلتها لنفس التِكّة، فتبقى خلف الجَمْع.

    لذلك يُحسب `DEPENDENT` **بالنسبة إلى جذرٍ** (`--root`): من يستهلك حدثًا
    يُنتَج داخل فَتَحة ذلك الجذر هو المعتمِد. وبلا جذر لا يُدّعى الاعتماد.
    """
    if evidence.get("parse_failed"):
        return CLASS_UNKNOWN, ["تعذّر تحليل المصدر"]
    reasons: list[str] = []
    verdicts: list[str] = []

    if evidence["cross_reads"]:
        verdicts.append(CLASS_CROSS_SCOPE)
        reasons.append("تقرأ حالة بمفتاحٍ من `self`: %s" % evidence["cross_reads"][:2])

    from_siblings = [event for event in evidence["subscribes"]
                     if event in sibling_events]
    if from_siblings:
        verdicts.append(CLASS_DEPENDENT)
        reasons.append("تنتظر ناتج زميلةٍ في الفَتَحة نفسها: %s" % from_siblings[:2])

    upstream = [event for event in evidence["subscribes"]
                if event in produced_elsewhere and event not in sibling_events]
    if upstream:
        verdicts.append(CLASS_PIPELINE)
        reasons.append("مرحلة تالية لـ: %s" % upstream[:2])

    unresolved = [event for event in evidence["subscribes"] if event.startswith("?")]
    if unresolved:
        verdicts.append(CLASS_UNKNOWN)
        reasons.append("اسم حدثٍ لم يُحلّ: %s" % unresolved[:2])

    if evidence["order_marks"]:
        verdicts.append(CLASS_ORDER_SENSITIVE)
        reasons.append("بنية تاريخيّة: %s" % evidence["order_marks"][:3])

    if evidence["state_names"]:
        verdicts.append(CLASS_STATEFUL)
        reasons.append("حالة مقيمة: %s" % evidence["state_names"][:3])

    if not verdicts:
        return CLASS_PURE, ["لا حالة ولا تاريخ ولا اعتماد مكتشف"]
    for level in SEVERITY:
        if level in verdicts:
            return level, reasons
    return CLASS_UNKNOWN, reasons


def _fanout_events(evidence: dict[str, dict[str, Any]], root: str) -> set[str]:
    """الأحداث التي تُولَد **داخل** فَتَحة الجذر — عبر انتشارٍ متعدٍّ.

    من يستهلك واحدًا منها ينتظر زميلته، فيبقى خلف الجَمْع (§16).
    """
    if not root:
        return set()
    frontier = {root}
    produced: set[str] = set()
    seen_atoms: set[str] = set()
    while frontier:
        nxt: set[str] = set()
        for name, item in evidence.items():
            if name in seen_atoms:
                continue
            if frontier & set(item.get("subscribes", [])):
                seen_atoms.add(name)
                fresh = set(item.get("publishes", [])) - produced
                produced |= fresh
                nxt |= fresh
        frontier = nxt
    return produced


def run(atoms_root: Path, root: str = "") -> dict[str, Any]:
    directories = [d for d in sorted(atoms_root.rglob("atom.py"))]
    evidence: dict[str, dict[str, Any]] = {}
    for path in directories:
        evidence[path.parent.name] = scan_atom(path.parent)

    # خريطة الإنتاج: أيّ حدث تنشره ذرّة (لأيّ ذرّة أخرى تستهلكه).
    produced: dict[str, set[str]] = {}
    for name, item in evidence.items():
        for event in item.get("publishes", []):
            produced.setdefault(event, set()).add(name)

    siblings = _fanout_events(evidence, root)
    rows = []
    for name, item in sorted(evidence.items()):
        others = {event for event, owners in produced.items() if owners - {name}}
        mine = set(item.get("publishes", []))
        verdict, reasons = classify(item, others, siblings - mine)
        rows.append({
            "atom": name,
            "class": verdict,
            "reasons": reasons,
            "subscribes": item.get("subscribes", []),
            "publishes": item.get("publishes", []),
        })
    return {"atoms": len(rows), "root": root,
            "fanout_events": sorted(siblings)[:40], "rows": rows}


