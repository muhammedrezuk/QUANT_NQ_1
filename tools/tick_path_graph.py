# -*- coding: utf-8 -*-
"""مخطّط تبعيّة مسار التِكّة — مستخرَجًا من الكود لا من المانيفست.

**لماذا من الكود:** المانيفست يعلن `subscribes`/`publishes` لكنّ النواة
لا تقرؤها. الاشتراك يحدث حين تنادي الذرّة `context.subscribe(...)` في
كودها (انظر `hot_reload_service._make_bound_subscribe`). فالمانيفست
ورقةٌ والكود حقيقة — وهذه الأداة تقرأ الحقيقة وتُبلّغ عن كذب الورقة.

يُستدعى:  python tools/tick_path_graph.py [--seeds a,b,c] [--divergence]
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATOMS = os.path.join(ROOT, "atoms")

# البذور الافتراضيّة — بنصّ المالك ٢٠٢٦-٠٩-١٧
DEFAULT_SEEDS = ("feed.mt5.tick", "feed.ctrader.raw", "market.depth")

# ما يبقى مركزيًّا بحكم §٣ من ورقة المالك — لا يُنقل مهما قال الرسم
CENTRAL_BY_DECREE = ((500, 599),)

# ذرّاتٌ اشتراكُها/نشرُها تقرّره الإعدادات لا الكود. الحافّة موجودة حيًّا
# ولا أثر لها في أيّ ملفّ بايثون — فتُقرأ من كتلة `config:` في المانيفست.
# ⚠️ ومعنى ذلك أنّ الرسم يتغيّر بتغيّر الإعدادات، لا بتغيّر الكود.
CONFIG_DRIVEN = {
    613: {"subscribes": ["routes/keys"],
          "publishes": ["routes/values", "broker_display_route"],
          "why": "جدول توجيه المزوّدين: feed.*.tick ⟶ market.tick"},
    704: {"subscribes": ["watch_events", "immediate_events"],
          "why": "قائمة الأحداث المسجَّلة في مخزن الأحداث"},
}

# مزخرِفاتٌ تحمل اسم الحدث في وسيطها، والنشر يقع داخل المساعد المشترك
# لا داخل الذرّة. بلا هذا يظهر `structure.section.live` «بلا ناشر» وله
# مستهلكون — والحافّة موجودة حيًّا.
#   section_live(section_id, event_out)   ·   live_analyzer(id, event_out)
DECORATOR_PUBLISHES = {"section_live": 1, "live_analyzer": 1}

# ذرّاتٌ اسمُ حدثها يأتي من **قاعدة بيانات وقت التشغيل**، فلا يُعرف ساكنًا
# بأيّ وسيلة. تُعلَن ولا تُخمَّن — وهذه حدود الرسم الصادقة.
RUNTIME_NAMED = {
    516: "إعادة نشر صندوق الصادر من journal بعد الإقلاع",
    517: "إعادة نشر صندوق الصادر من journal بعد الإقلاع",
    563: "إعادة نشر صندوق الصادر من journal بعد الإقلاع",
    901: "اسم الحدث صفٌّ في قاعدة أوامر المالك",
}


# ───────────────────────── حلّ الثوابت ─────────────────────────

def _literal(node, consts):
    """يحلّ عقدة إلى نصّ إن أمكن، وإلّا None."""
    vals = _literal_multi(node, consts, {})
    return next(iter(vals)) if len(vals) == 1 else None


def _literal_multi(node, consts, loopvars):
    """يعيد **مجموعة** القيم الممكنة للعقدة — تحسبًا للحلقات."""
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.Name):
        if node.id in loopvars:
            return set(loopvars[node.id])
        v = consts.get(node.id)
        return {v} if isinstance(v, str) else set()
    if isinstance(node, ast.Attribute):
        v = consts.get(node.attr)
        return {v} if isinstance(v, str) else set()
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_multi(node.left, consts, loopvars)
        right = _literal_multi(node.right, consts, loopvars)
        return {a + b for a in left for b in right} if left and right else set()
    return set()


def _elements(node, consts):
    """عناصر مجموعةٍ حرفيّة: قائمة عقد، أو None إن تعذّر."""
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return list(node.elts)
    if isinstance(node, ast.Name):
        v = consts.get(node.id)
        if isinstance(v, list):
            return list(v)
        # التكرار على قاموسٍ يعطي مفاتيحه
        if isinstance(v, dict):
            return [ast.Constant(value=k) for k in v]
        return None
    if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
        return _comprehension(node, consts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "zip" and node.args:
            cols = [_elements(a, consts) for a in node.args]
            if any(c is None for c in cols):
                return None
            return [ast.Tuple(elts=list(pair), ctx=ast.Load())
                    for pair in zip(*cols)]
        if node.func.id in ("tuple", "list", "sorted", "set",
                            "frozenset") and node.args:
            return _elements(node.args[0], consts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        # `MAP.items()` / `MAP.keys()` على قاموسٍ حرفيّ
        if node.func.attr in ("items", "keys", "values"):
            base = node.func.value
            d = consts.get(base.id) if isinstance(base, ast.Name) else None
            if isinstance(d, dict):
                if node.func.attr == "keys":
                    return [ast.Constant(value=k) for k in d]
                if node.func.attr == "values":
                    return [ast.Constant(value=v) for v in d.values()
                            if isinstance(v, str)]
                # القيمة قد تكون رقمًا (`_CADENCES`) — المفتاح هو المقصود،
                # ولا تُحذف الأزواج لأجل قيمةٍ غير نصّيّة.
                return [ast.Tuple(elts=[ast.Constant(value=k),
                                        ast.Constant(value=v)], ctx=ast.Load())
                        for k, v in d.items()]
    return None


def _comprehension(node, consts):
    """`tuple(e for e, _ in SOURCES)` — استنباطٌ ببندٍ واحد على مجموعةٍ محلولة."""
    if len(node.generators) != 1:
        return None
    gen = node.generators[0]
    if gen.ifs:
        return None
    src = _elements(gen.iter, consts)
    if src is None:
        return None
    out = []
    for element in src:
        bind = {}
        if isinstance(gen.target, ast.Name):
            vals = _literal_multi(element, consts, {})
            if vals:
                bind[gen.target.id] = vals
        elif isinstance(gen.target, ast.Tuple):
            for i, sub in enumerate(gen.target.elts):
                if not isinstance(sub, ast.Name):
                    continue
                if isinstance(element, (ast.Tuple, ast.List)) and i < len(element.elts):
                    vals = _literal_multi(element.elts[i], consts, {})
                    if vals:
                        bind[sub.id] = vals
        produced = _literal_multi(node.elt, consts, bind)
        if len(produced) != 1:
            return None
        out.append(ast.Constant(value=next(iter(produced))))
    return out


def _bind_loop(for_node, consts):
    """يربط متغيّر الحلقة بمجموعة قيمه الممكنة."""
    out = {}
    elems = _elements(for_node.iter, consts)
    if elems is None:
        return out
    target = for_node.target
    if isinstance(target, ast.Name):
        vals = set()
        for e in elems:
            vals |= _literal_multi(e, consts, {})
        if vals:
            out[target.id] = vals
    elif isinstance(target, ast.Tuple):
        for i, sub in enumerate(target.elts):
            if not isinstance(sub, ast.Name):
                continue
            vals = set()
            for e in elems:
                if isinstance(e, (ast.Tuple, ast.List)) and i < len(e.elts):
                    vals |= _literal_multi(e.elts[i], consts, {})
            if vals:
                out[sub.id] = vals
    return out


def _collect_consts(tree):
    """ثوابت الوحدة: نصوصًا، وقوائمَ نصوص، وقواميسَ نصوص."""
    consts = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = getattr(node, "value", None)
        if value is None:
            continue
        resolved = None
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            resolved = value.value
        elif isinstance(value, (ast.Tuple, ast.List, ast.Set)):
            resolved = list(value.elts)
        elif isinstance(value, ast.Dict):
            # المفتاح وحده يكفي: التكرار على قاموسٍ يعطي مفاتيحه، وكثيرٌ
            # من جداول الأحداث قيمُها صفوفٌ لا نصوص (مثل `_MONITORED`).
            pairs = {}
            for k, v in zip(value.keys, value.values):
                if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                    continue
                pairs[k.value] = (v.value if isinstance(v, ast.Constant)
                                  and isinstance(v.value, str) else None)
            resolved = pairs or None
        if resolved is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if isinstance(t, ast.Name):
                consts[t.id] = resolved
            elif isinstance(t, ast.Attribute):
                consts.setdefault(t.attr, resolved)

    # شوطٌ ثانٍ: ما بُني بنداء أو باستنباط — `tuple(e for e,_ in SRC)`
    # و`frozenset({...})`. يحتاج ثوابت الشوط الأوّل فلا يُحلّ معها.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = getattr(node, "value", None)
        if not isinstance(value, (ast.Call, ast.ListComp,
                                  ast.GeneratorExp, ast.SetComp)):
            continue
        elems = _elements(value, consts)
        if elems is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if isinstance(t, ast.Name):
                consts.setdefault(t.id, elems)
    return consts


def _alias_consts(tree, shared_by_module):
    """`from shared.x import EVENT_A as EVENT_B` — الكنية تُحلّ لأصلها."""
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        mod = node.module.split(".")[-1]
        table = shared_by_module.get(mod)
        if not table:
            continue
        for alias in node.names:
            src = table.get(alias.name)
            if src is not None:
                out[alias.asname or alias.name] = src
    return out


def _helper_bindings(tree, consts):
    """ربط وسائط الدوالّ المساعدة داخل الصنف نفسه.

    نمطٌ متكرّر: `async def _emit(self, event, body): publish(event, body)`
    ثمّ `await self._emit(EVENT_GATE_PASSED, body)`. الاسم معروفٌ عند
    المُنادي لا عند النشر — فيُجمَع من كلّ مواضع النداء.

    والسلسلة قد تكون بمستويين (٨٠٦: وسيطٌ يأتي من وسيط)، فيُكرَّر الحلّ
    حتى الثبات.
    """
    # خريطة: عقدة ⟶ الدالّة التي تحويها، وعقد الحلقات المحيطة
    holder, loops = {}, defaultdict(list)

    def _mark(node, fn, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                holder[child] = fn
                _mark(child, child, [])
                continue
            holder[child] = fn
            loops[child] = list(stack)
            _mark(child, fn, stack + [child] if isinstance(child, ast.For) else stack)

    _mark(tree, None, [])

    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    by_name = defaultdict(list)
    for f in funcs:
        by_name[f.name].append(f)

    out = {}
    for _ in range(4):
        calls = defaultdict(lambda: defaultdict(set))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                    and fn.value.id == "self"):
                continue
            env = {}
            owner = holder.get(node)
            if owner in out:
                env.update(out[owner])
            for loop in loops.get(node, ()):
                env.update(_bind_loop(loop, consts))
            for i, arg in enumerate(node.args):
                vals = _literal_multi(arg, consts, env)
                if vals:
                    calls[fn.attr][i] |= vals

        changed = False
        for name, seen in calls.items():
            for node in by_name.get(name, ()):
                params = [a.arg for a in node.args.args]
                if params and params[0] == "self":
                    params = params[1:]
                binding = dict(out.get(node, {}))
                for i, pname in enumerate(params):
                    if i in seen and binding.get(pname) != seen[i]:
                        binding[pname] = set(seen[i])
                        changed = True
                if binding:
                    out[node] = binding
        if not changed:
            break
    return out


def _walk_scoped(node, consts, loopvars, out, helpers=None):
    """يمشي الشجرة حاملًا ربط متغيّرات الحلقات والوسائط المحيطة."""
    helpers = helpers or {}
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node in helpers:
        inner = dict(loopvars)
        inner.update(helpers[node])
        for child in ast.iter_child_nodes(node):
            _walk_scoped(child, consts, inner, out, helpers)
        return
    if isinstance(node, ast.For):
        inner = dict(loopvars)
        inner.update(_bind_loop(node, consts))
        for child in node.body:
            _walk_scoped(child, consts, inner, out, helpers)
        for child in node.orelse:
            _walk_scoped(child, consts, loopvars, out, helpers)
        _walk_scoped(node.iter, consts, loopvars, out, helpers)
        return
    if isinstance(node, ast.Call):
        fn = node.func
        attr = fn.attr if isinstance(fn, ast.Attribute) else (
            fn.id if isinstance(fn, ast.Name) else None)
        if attr in ("subscribe", "publish") and node.args:
            names = _literal_multi(node.args[0], consts, loopvars)
            if names:
                out["publishes" if attr == "publish" else "subscribes"] |= names
            else:
                out["unresolved"] += 1
    for child in ast.iter_child_nodes(node):
        _walk_scoped(child, consts, loopvars, out, helpers)


def scan_source(path, extra_consts=None, shared_by_module=None):
    """يعيد (يُنشر، يُشترَك، عدد غير المحلول) من ملفّ بايثون واحد."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return set(), set(), 0

    consts = dict(extra_consts or {})
    consts.update(_alias_consts(tree, shared_by_module or {}))
    consts.update(_collect_consts(tree))
    out = {"publishes": set(), "subscribes": set(), "unresolved": 0}
    _walk_scoped(tree, consts, {}, out, _helper_bindings(tree, consts))

    # النشر عبر مزخرِفٍ مشترك — الاسم في وسيط المزخرِف لا في نداء نشر
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name)):
                continue
            idx = DECORATOR_PUBLISHES.get(dec.func.id)
            if idx is None or len(dec.args) <= idx:
                continue
            out["publishes"] |= _literal_multi(dec.args[idx], consts, {})

    return out["publishes"], out["subscribes"], out["unresolved"]


def _config_block(path):
    """كتلة `config:` من المانيفست — لا `config_schema:`.

    قارئٌ لجزءٍ من YAML يكفي لما نحتاجه: نصّ · قائمة بشرطات · خريطة
    بمستوًى واحد. ولا يُستعمل لغير هذه المفاتيح المعلَنة أعلاه.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return {}
    out, key, inside = {}, None, False
    scalar = re.compile(r'^  ([A-Za-z0-9_]+):\s*(.*)$')
    item = re.compile(r'^\s+-\s*["\']?([A-Za-z0-9_.*]+)["\']?\s*$')
    nested = re.compile(r'^    ([A-Za-z0-9_.*]+):\s*["\']?([A-Za-z0-9_.*]+)["\']?\s*$')
    for raw in lines:
        if re.match(r"^[A-Za-z_]", raw):
            inside = raw.startswith("config:")
            key = None
            continue
        if not inside:
            continue
        m = scalar.match(raw)
        if m:
            key, rest = m.group(1), m.group(2).strip()
            if rest and not rest.startswith("#"):
                if rest.startswith("["):
                    out[key] = [x.strip().strip('"\'')
                                for x in rest.strip("[]").split(",") if x.strip()]
                else:
                    out[key] = rest.strip('"\'')
                key = None
            else:
                out[key] = out.get(key) or {}
            continue
        if key is None:
            continue
        m = nested.match(raw)
        if m and isinstance(out.get(key), dict):
            out[key][m.group(1)] = m.group(2)
            continue
        m = item.match(raw)
        if m:
            if not isinstance(out.get(key), list):
                out[key] = []
            out[key].append(m.group(1))
    return out


def config_events(aid, manifest_path):
    """أحداثُ الذرّة التي تقرّرها الإعدادات — subscribes, publishes."""
    spec = CONFIG_DRIVEN.get(aid)
    if not spec:
        return set(), set()
    cfg = _config_block(manifest_path)
    result = {"subscribes": set(), "publishes": set()}
    for side in ("subscribes", "publishes"):
        for ref in spec.get(side, ()):
            if "/" in ref:
                name, part = ref.split("/", 1)
                value = cfg.get(name)
                if isinstance(value, dict):
                    result[side] |= set(value.keys() if part == "keys"
                                        else value.values())
            else:
                value = cfg.get(ref)
                if isinstance(value, list):
                    result[side] |= {str(x) for x in value}
                elif isinstance(value, str):
                    result[side].add(value)
    return result["subscribes"], result["publishes"]


def read_manifest(path):
    """قراءة publishes/subscribes بلا مكتبة YAML — الحقول قوائم بسيطة."""
    pub, sub, key = [], [], None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return set(), set()
    item = re.compile(r'^\s+-\s*["\']?([A-Za-z0-9_.*]+)["\']?\s*$')
    for raw in lines:
        if raw.startswith("publishes:"):
            key = pub
            continue
        if raw.startswith("subscribes:"):
            key = sub
            continue
        if re.match(r"^[a-zA-Z_]", raw):
            key = None
            continue
        m = item.match(raw)
        if m and key is not None:
            key.append(m.group(1))
    return set(pub), set(sub)


# ───────────────────────── بناء الرسم ─────────────────────────

def shared_consts():
    """ثوابت `shared/` — مسطّحةً، وموزّعةً على الوحدات للكنى."""
    flat, by_module = {}, {}
    shared = os.path.join(ROOT, "shared")
    if not os.path.isdir(shared):
        return flat, by_module
    for fname in sorted(os.listdir(shared)):
        if not fname.endswith(".py"):
            continue
        try:
            with open(os.path.join(shared, fname), "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except (OSError, SyntaxError, ValueError):
            continue
        table = _collect_consts(tree)
        by_module[fname[:-3]] = table
        for k, v in table.items():
            flat.setdefault(k, v)
    return flat, by_module


def build_graph():
    extra, by_module = shared_consts()
    atoms = {}
    for section in sorted(os.listdir(ATOMS)):
        sdir = os.path.join(ATOMS, section)
        if not os.path.isdir(sdir):
            continue
        for folder in sorted(os.listdir(sdir)):
            adir = os.path.join(sdir, folder)
            src = os.path.join(adir, "atom.py")
            if not os.path.isfile(src):
                continue
            m = re.match(r"^(\d+)_", folder)
            if not m:
                continue
            aid = int(m.group(1))
            # وحداتٌ شقيقة بجانب الذرّة — مثل `halt_gate.py` عند ٥٧٦
            local = dict(by_module)
            for sib in sorted(os.listdir(adir)):
                if not sib.endswith(".py") or sib == "atom.py":
                    continue
                try:
                    with open(os.path.join(adir, sib), "r", encoding="utf-8") as fh:
                        local[sib[:-3]] = _collect_consts(ast.parse(fh.read()))
                except (OSError, SyntaxError, ValueError):
                    continue
            pub, sub, unres = scan_source(src, extra, local)
            man = os.path.join(adir, "manifest.yaml")
            csub, cpub = config_events(aid, man)
            sub |= csub
            pub |= cpub
            mpub, msub = read_manifest(man)
            atoms[aid] = {
                "name": folder, "section": section,
                "config_subscribes": csub, "config_publishes": cpub,
                "publishes": pub, "subscribes": sub, "unresolved": unres,
                "m_publishes": mpub, "m_subscribes": msub,
            }
    return atoms


def closure(atoms, seeds):
    """الإغلاق المتعدّي: كلّ مستهلكٍ للبذور، ثمّ كلّ ما ينشره، تكرارًا."""
    events = set(seeds)
    members = set()
    while True:
        grew = False
        for aid, a in atoms.items():
            if aid in members:
                continue
            if a["subscribes"] & events:
                members.add(aid)
                if not a["publishes"] <= events:
                    events |= a["publishes"]
                grew = True
        if not grew:
            return members, events


def is_central(aid):
    return any(lo <= aid <= hi for lo, hi in CENTRAL_BY_DECREE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=",".join(DEFAULT_SEEDS))
    ap.add_argument("--divergence", action="store_true")
    args = ap.parse_args()
    seeds = tuple(s.strip() for s in args.seeds.split(",") if s.strip())

    atoms = build_graph()
    producers, consumers = defaultdict(set), defaultdict(set)
    for aid, a in atoms.items():
        for e in a["publishes"]:
            producers[e].add(aid)
        for e in a["subscribes"]:
            consumers[e].add(aid)

    print("مخطّط تبعيّة مسار التِكّة — من الكود")
    print("=" * 72)
    print("الذرّات المفحوصة: %d" % len(atoms))
    unres = sum(a["unresolved"] for a in atoms.values())
    blind = sorted(aid for aid, a in atoms.items() if a["unresolved"])
    declared = set(CONFIG_DRIVEN) | set(RUNTIME_NAMED)
    truly_blind = [a for a in blind if a not in declared]
    print("نداءات لا تُحلّ ساكنًا: %d في %d ذرّة" % (unres, len(blind)))
    for aid in blind:
        if aid in CONFIG_DRIVEN:
            print("   [إعدادات] %-4d %s" % (aid, CONFIG_DRIVEN[aid]["why"]))
            print("             ⟹ حافّتها مقروءةٌ من المانيفست ومحقونةٌ في الرسم")
        elif aid in RUNTIME_NAMED:
            print("   [تشغيل ] %-4d %s" % (aid, RUNTIME_NAMED[aid]))
            print("             ⟹ لا تُعرف ساكنًا بأيّ وسيلة — تُعلَن ولا تُخمَّن")
    if truly_blind:
        print("   🔴 عمياء بلا تفسير: %s"
              % " ".join(str(x) for x in truly_blind))
    else:
        print("   ✅ لا نقطة عمياء بلا تفسير — الرسم مُغلق")

    only_code, only_man = [], []
    for aid, a in atoms.items():
        cs, ms = a["subscribes"], a["m_subscribes"]
        if any("*" in x for x in ms):
            continue
        if cs - ms:
            only_code.append((aid, sorted(cs - ms)))
        if ms - cs:
            only_man.append((aid, sorted(ms - cs)))
    print()
    print("-" * 72)
    print("١) الكود مقابل المانيفست — الاشتراكات")
    print("   يشترك في الكود ولا يعلنه المانيفست : %d ذرّة" % len(only_code))
    print("   يعلنه المانيفست ولا يشترك في الكود : %d ذرّة" % len(only_man))
    if args.divergence:
        for aid, ev in sorted(only_code)[:50]:
            print("      [كود+] %s : %s" % (aid, ", ".join(ev)))
        for aid, ev in sorted(only_man)[:50]:
            print("      [ورق+] %s : %s" % (aid, ", ".join(ev)))

    members, events = closure(atoms, seeds)
    print()
    print("-" * 72)
    print("٢) الإغلاق المتعدّي")
    print("   البذور : %s" % " · ".join(seeds))
    print("   الأعضاء: %d ذرّة من %d" % (len(members), len(atoms)))
    print("   الأحداث: %d" % len(events))
    buckets = defaultdict(list)
    for aid in sorted(members):
        buckets[(aid // 50) * 50].append(aid)
    print()
    print("   التوزيع:")
    for lo in sorted(buckets):
        tag = "  ⛔ مركزيّ بحكم §٣" if is_central(lo) else ""
        print("      %3d-%3d : %3d%s" % (lo, lo + 49, len(buckets[lo]), tag))

    print()
    print("-" * 72)
    print("٣) الحدّ — الأحداث المنقسمة عند القطع المقترَح")
    print("   ⚠️ لا يُقاس الانقسام على الإغلاق نفسه: الإغلاق يضمّ كلّ")
    print("      مستهلكٍ بالبناء، فالنتيجة صفرٌ حتمًا وحارسٌ كهذا يكذب.")
    print("   القطع المقترَح: الكتلة المنقولة = الإغلاق ناقص مركزيّ §٣.")
    movable = {a for a in members if not is_central(a)}
    split = []
    for e in sorted(events):
        cons = consumers.get(e, set())
        if not cons:
            continue
        inside, outside = cons & movable, cons - movable
        if inside and outside:
            split.append((e, sorted(inside), sorted(outside)))
    print()
    print("   🔴 المنقسمة عند هذا القطع: %d حدثًا من %d"
          % (len(split), len(events)))
    print("   وكلّ واحدٍ منها يكسر `EVENT-COMPLETE OWNERSHIP`:")
    for e, ins, outs in split[:24]:
        print("      [منقسم] %-32s منقول %2d · مركزيّ %s"
              % (e, len(ins), " ".join(str(x) for x in outs[:6])))
    if len(split) > 24:
        print("      ... و%d غيرها" % (len(split) - 24))

    print()
    print("-" * 72)
    print("٤) المدخلات الخارجيّة — ما تحتاجه الكتلة ولا تنتجه")
    needed = set()
    for aid in members:
        needed |= atoms[aid]["subscribes"]
    external = []
    for e in sorted(needed - set(seeds)):
        prods = producers.get(e, set())
        if prods and not (prods & members):
            external.append((e, sorted(prods)))
    orphan = sorted(e for e in (needed - set(seeds)) if not producers.get(e))
    print("   %d حدثًا يأتي من ذرّةٍ خارج الكتلة:" % len(external))
    for e, p in external[:30]:
        print("      [خارجيّ] %-34s <- %s" % (e, " ".join(str(x) for x in p[:8])))
    if len(external) > 30:
        print("      ... و%d غيرها" % (len(external) - 30))
    print()
    print("   %d حدثًا بلا ناشرٍ ذرّيّ (النواة/النقل أو ميت):" % len(orphan))
    for e in orphan[:20]:
        print("      [بلا ناشر] %s" % e)
    if len(orphan) > 20:
        print("      ... و%d غيرها" % (len(orphan) - 20))

    print()
    print("-" * 72)
    print("٥) عبور §٣ — أعضاء الإغلاق الذين لا يُنقلون")
    central = sorted(a for a in members if is_central(a))
    print("   %d ذرّة داخل الإغلاق ومركزيّة بالحكم:" % len(central))
    if central:
        print("      %s" % " ".join(str(x) for x in central))
    movable = members - set(central)
    print()
    print("   الأحداث التي تعبر من الكتلة المنقولة إليهم — نقطة القطع:")
    crossing = set()
    for aid in central:
        for e in atoms[aid]["subscribes"]:
            if producers.get(e, set()) & movable:
                crossing.add(e)
    for e in sorted(crossing):
        print("      [قطع] %s  <- %s"
              % (e, " ".join(str(x) for x in sorted(producers[e] & movable)[:8])))
    if not crossing:
        print("      (لا شيء — الحدّ نظيف)")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    raise SystemExit(main())
