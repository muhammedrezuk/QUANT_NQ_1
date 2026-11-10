# -*- coding: utf-8 -*-
"""§5 / Gate D — تنفيذُ الذرّات الحقيقيّة خارج `EventBus` (ختم `NQ — OPEN REAL ATOM COST`).

## العقد

    مدخلٌ حقيقيّ ⟶ مالكُ Account×Symbol الحقيقيّ ⟶ الخطّة المُجمَّعة
        ⟶ **تنفيذُ ذرّةٍ حقيقيّ** ⟶ قرار ⟶ مخاطر ⟶ نيّةُ أمر

والعقد يسمح به بالبناء: `AtomContext` تحقن `publish` و`subscribe`، والذرّة
«لا تستورد أي وحدة Core مباشرة». فنُمرّر بديلَين ونستدعي المعالجات بأنفسنا.

    ⛔ ولا نسخةَ تجريبيّةً ثانية: نفسُ `manifest.config` الذي يقرؤه
       `core/bootloader.py:279`، ونفسُ `entrypoint`، ونفسُ الذرّة.

## ⛔ الحاجز — يُقرأ قبل أيّ رقم

العقد ادّعاءٌ حتّى يُقرأ الكود، وقراءتُه قالت غير ذلك: من ١٦٣ ذرّةً ساخنة
**١١ تفتح قاعدة**، وواحدةٌ تفتح شبكة، واثنتان تكتبان ملفًّا، وثلاثٌ تنام.
ومنها ٥٥١ (بانِي الأمر) و٥٦٣ (تأكيد التنفيذ) و٥٧٥ (مُرسِل الإدارة).

وتنفيذُها بلا حاجزٍ على جهازٍ تعمل عليه المنصّة وحسابُ ديمو **قد يكتب
أمرًا حقيقيًّا**. فالحاجز ليس احتياطًا: هو شرطُ إجراء القياس أصلًا.

    كلُّ مَخرجٍ **يُرفَض ويُسمّى** — لا يُسمَح صامتًا ولا يُمنَع صامتًا.

وذرّةٌ كلفتُها تعتمد على مَخرجٍ محجوب رقمُها **غير ممثِّل**، فتُعرَض في
`blocked_atoms` ولا تُدمَج في المجموع بلا إعلان.

## النوم يُصفَّر ويُعدّ

`asyncio.sleep` داخل معالجٍ ليس كلفةَ معالجة. يُصفَّر كي لا يُقاس انتظارٌ
عملًا، ويُعدّ كي لا يُخفى أنّ الذرّة تنتظر شيئًا لا يجيء هنا.
"""
from __future__ import annotations

import asyncio
import builtins
import importlib.util
import socket
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

#: أقسامُ الكلفة كما طلبها المالك — بالرقم لا بالاسم.
PHASES = (("analysis", 100, 449), ("decision", 450, 499),
          ("risk", 500, 549), ("intent", 550, 599))


def phase_of(atom_id: str) -> str:
    number = int(atom_id)
    for name, low, high in PHASES:
        if low <= number <= high:
            return name
    return "outside"


class BlockedEffect(RuntimeError):
    """مَخرجٌ رُفض. يحمل اسمَ الذرّة والمَخرج — لا رفضَ مجهول."""


class SideEffectGuard:
    """يمنع كلَّ مَخرجٍ خارج `publish` ويُسمّي مَن حاوله.

    ولا يعمل بالتخمين: يُركَّب على العمليّة كلِّها، ويُسجَّل عليه اسمُ
    الذرّة الجارية، فيُنسَب كلُّ محاولةٍ لصاحبها.
    """

    def __init__(self, sandbox: Path | str = "", profiler: Any = None) -> None:
        #: مشرّحٌ اختياريّ — الحاجزُ يعترض المنافذ أصلًا، فالتوقيت يركب معه
        #: ولا يُبنى اعتراضٌ ثانٍ (ختم `NQ — OPEN ATOM INTERNAL PROFILE`).
        self.profiler = profiler
        self.current: str = "?"
        self.sandbox = Path(sandbox) if sandbox else (
            _ROOT / "forex_runtime" / "var" / "parity" / "gate_d" / "sandbox")
        self.db_copies: dict[str, str] = {}
        self.trace_connects = False
        self.connect_sites: Counter[str] = Counter()
        self.attempts: Counter[str] = Counter()
        self.by_atom: dict[str, Counter[str]] = {}
        self.sleeps: Counter[str] = Counter()
        #: مهامُّ خلفيّةٌ مُنعت من الجدولة — تُعرَض، فذرّةٌ تعتمد عليها
        #: رقمُها ناقصٌ ويجب أن يُعرَف ذلك.
        self.tasks: Counter[str] = Counter()
        self._saved: dict[str, Any] = {}

    def _record(self, kind: str) -> None:
        self.attempts[kind] += 1
        self.by_atom.setdefault(self.current, Counter())[kind] += 1
        if self.profiler is not None:
            self.profiler.current = self.current

    def _charge(self, gate: str, spent_ns: int) -> None:
        if self.profiler is not None:
            self.profiler.current = self.current
            self.profiler.charge(gate, spent_ns)

    def sandbox_db(self, database: Any) -> Any:
        """يُعيد نسخةً معزولةً من القاعدة — تُنسَخ مرّةً ثمّ تُعاد.

        و`:memory:` وما شابهه يمرّ كما هو: لا ملفّ يُمَسّ أصلًا.
        """
        text = str(database)
        if not text or text.startswith(":") or text.startswith("file::"):
            return database
        known = self.db_copies.get(text)
        if known is not None:
            return known
        import shutil
        self.sandbox.mkdir(parents=True, exist_ok=True)
        source = Path(text)
        target = self.sandbox / ("%d-%s" % (len(self.db_copies), source.name))
        try:
            if source.exists():
                shutil.copyfile(source, target)
        except Exception:                                      # noqa: BLE001
            # تعذّر النسخ (‏قفلٌ أو حجم) ⟶ قاعدةٌ فارغةٌ في الصندوق،
            # وتُسمّى في التقرير: كلفتُها أقلُّ من الحقيقيّة.
            self.attempts["قاعدةٌ لم تُنسَخ"] += 1
        self.db_copies[text] = str(target)
        return str(target)

    def install(self) -> None:
        import sqlite3
        import subprocess

        guard = self

        def refuse(kind: str):
            def blocked(*_args: Any, **_kwargs: Any):
                guard._record(kind)
                raise BlockedEffect("%s حاولت %s — مرفوضٌ في القياس"
                                    % (guard.current, kind))
            return blocked

        self._saved["sqlite_connect"] = sqlite3.connect
        self._saved["create_connection"] = socket.create_connection
        self._saved["popen"] = subprocess.Popen
        self._saved["open"] = builtins.open
        self._saved["create_task"] = asyncio.create_task
        self._saved["ensure_future"] = asyncio.ensure_future

        # ── القاعدة تُعزَل ولا تُمنَع ────────────────────────────────────
        #
        # ⛔ منعُها أسقط **٣٢ ذرّةً من ١٦٣** عند الإقلاع — والمقيس أنّ
        #    قراءةَ العيارات من القرص كانت جذرَ p99 سابقًا. فذرّةٌ محجوبةٌ
        #    عن قاعدتها رقمُها ليس ناقصًا فحسب، بل **يخفي أثقلَ ما فيها**.
        #
        # والعلاج عزلٌ لا رفض: تُنسَخ القاعدة مرّةً إلى صندوقٍ رمليّ ويُفتَح
        # النسخةُ. فالكلفة حقيقيّةٌ (قرصٌ وSQL)، وحالةُ المنصّة لا تُمَسّ.
        real_connect = self._saved["sqlite_connect"]

        def sandboxed(database: Any, *args: Any, **kwargs: Any):
            guard._record("قاعدة")
            if guard.trace_connects:
                # ⛔ مَن يفتح؟ — يُقرأ من المكدّس لا من الظنّ. كشفتُ ذاكرةً
                #    في `_config` بلا إبطال، فالاتّصالاتُ ليست منها — ولا
                #    أبني علاجًا على موضعٍ مظنون.
                import traceback
                frames = [f for f in traceback.extract_stack()[:-1]
                          if "atom_host" not in f.filename]
                spot = " ← ".join(
                    "%s:%s" % (Path(f.filename).name, f.name)
                    for f in frames[-4:])
                guard.connect_sites[spot] += 1
            start = time.perf_counter_ns()
            connection = real_connect(guard.sandbox_db(database),
                                      *args, **kwargs)
            if guard.profiler is not None:
                guard.profiler.charge("connect", time.perf_counter_ns() - start)
                return guard.profiler.wrap_connection(connection)
            return connection

        sqlite3.connect = sandboxed
        subprocess.Popen = refuse("عمليّة")
        # ⛔ الشبكة تُمنَع عند **الاتّصال** لا عند الصنف.
        #
        #    أوّل صيغةٍ استبدلت `socket.socket` نفسَه بدالّة، فانكسرت حلقةُ
        #    asyncio من داخلها: `ProactorEventLoop` يفحص
        #    `isinstance(x, socket.socket)` وأنبوبُها الذاتيّ يسقط —
        #    «Error on reading from the event loop self pipe». فتعلّق
        #    الإقلاع ولم يُقلِع شيء. الصنف يبقى، والاتّصالُ يُرفَض.
        socket.create_connection = refuse("شبكة")
        for name in ("urllib.request", "requests", "httpx", "aiohttp"):
            module = sys.modules.get(name)
            if module is not None:
                for call in ("urlopen", "get", "post", "request"):
                    if hasattr(module, call):
                        self._saved["%s.%s" % (name, call)] = getattr(module, call)
                        setattr(module, call, refuse("شبكة"))

        real_open = self._saved["open"]

        def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any):
            # القراءةُ مسموحة: الذرّة تقرأ عياراتٍ وجداولَ وهي جزءُ كلفتها.
            # والكتابةُ وحدها تُرفَض — هي التي تُغيّر حالةَ المنصّة.
            if any(flag in mode for flag in ("w", "a", "x", "+")):
                # الصندوقُ الرمليّ مسموحٌ: نسخُ القاعدة ومَخرجُها يقعان فيه،
                # وهو خارج المشروع وخارج حالة المنصّة.
                try:
                    inside = str(Path(file).resolve()).startswith(
                        str(guard.sandbox.resolve()))
                except Exception:                              # noqa: BLE001
                    inside = False
                if not inside:
                    guard._record("كتابة")
                    raise BlockedEffect("%s حاولت كتابة %s — مرفوضٌ في القياس"
                                        % (guard.current, file))
            start = time.perf_counter_ns()
            handle = real_open(file, mode, *args, **kwargs)
            if guard.profiler is not None:
                guard.profiler.charge("fs", time.perf_counter_ns() - start)
                return guard.profiler.wrap_file(handle)
            return handle

        builtins.open = guarded_open

        # ⛔ والمهامُّ الخلفيّة **لا تُشغَّل**: ذرّةٌ تبدأ حلقةً دوريّةً في
        #    `start()` عملُها ليس كلفةَ تِكّة، وتشغيلُها يُلوّث القياس ويُبقي
        #    العمليّة حيّةً بلا نهاية. تُسجَّل ولا تُجدوَل.
        #
        #    ⚠️ ولا يُصفَّر `asyncio.sleep` بديلًا عن ذلك: تصفيرُه يحوّل
        #       `while True: await sleep(1)` إلى دورانٍ محموم. النومُ يبقى
        #       نومًا، والمهمّةُ هي التي لا تُخلَق.
        def no_task(coro: Any, *_args: Any, **_kwargs: Any):
            guard.tasks[guard.current] += 1
            if asyncio.iscoroutine(coro):
                coro.close()
            future: Any = asyncio.Future()
            future.set_result(None)
            return future

        asyncio.create_task = no_task
        asyncio.ensure_future = no_task

        # ── الخيطُ والنوم يُوقَّتان كذلك ─────────────────────────────────
        #
        # `asyncio.to_thread` هو منفذُ القاعدة الحقيقيّ في هذه الذرّات:
        # الكتابةُ تُدفَع إليه، فزمنُه ليس حسابًا بايثونيًّا بل انتظارَ خيط.
        self._saved["to_thread"] = asyncio.to_thread
        self._saved["sleep"] = asyncio.sleep
        real_to_thread = self._saved["to_thread"]
        real_sleep = self._saved["sleep"]

        async def timed_to_thread(func: Any, *args: Any, **kwargs: Any):
            start = time.perf_counter_ns()
            try:
                return await real_to_thread(func, *args, **kwargs)
            finally:
                guard._charge("thread", time.perf_counter_ns() - start)

        async def timed_sleep(delay: float = 0.0, *args: Any, **kwargs: Any):
            guard.sleeps[guard.current] += 1
            start = time.perf_counter_ns()
            try:
                return await real_sleep(delay, *args, **kwargs)
            finally:
                guard._charge("sleep", time.perf_counter_ns() - start)

        asyncio.to_thread = timed_to_thread
        asyncio.sleep = timed_sleep

    def remove(self) -> None:
        import sqlite3
        import subprocess
        if not self._saved:
            return
        sqlite3.connect = self._saved["sqlite_connect"]
        socket.create_connection = self._saved["create_connection"]
        subprocess.Popen = self._saved["popen"]
        builtins.open = self._saved["open"]
        asyncio.create_task = self._saved["create_task"]
        asyncio.ensure_future = self._saved["ensure_future"]
        if "to_thread" in self._saved:
            asyncio.to_thread = self._saved["to_thread"]
            asyncio.sleep = self._saved["sleep"]
        for key, value in self._saved.items():
            if "." in key:
                name, call = key.rsplit(".", 1)
                module = sys.modules.get(name)
                if module is not None:
                    setattr(module, call, value)
        self._saved.clear()

    def report(self) -> dict[str, Any]:
        return {
            "attempts": dict(self.attempts),
            "blocked_atoms": {a: dict(c) for a, c in sorted(self.by_atom.items())},
            "sleeping_atoms": dict(self.sleeps),
            "background_tasks_suppressed": dict(self.tasks),
        }


class _Silent:
    """سجلٌّ صامت: كتابةُ السجلّ مَخرجٌ، وكلفتُها ليست كلفةَ تحليل."""

    def __init__(self, guard: SideEffectGuard) -> None:
        self._guard = guard
        self.count = 0

    def _drop(self, *_args: Any, **_kwargs: Any) -> None:
        self.count += 1

    debug = info = warning = error = critical = exception = _drop


class AtomHost:
    """يُقلع ذرّات الخطّة الساخنة ويُشغّلها بنفسه، ويقيس كلَّ استدعاء."""

    def __init__(self, plan: Any, *, guard: SideEffectGuard | None = None) -> None:
        self.plan = plan
        self.guard = guard or SideEffectGuard()
        self.atoms: dict[str, Any] = {}
        self.handlers: dict[str, list[tuple[str, Any]]] = {}
        self.loaded: list[str] = []
        self.failed: dict[str, str] = {}
        self.published: list[tuple[str, str, Any]] = []
        #: نانو ثانيةٍ لكلّ ذرّة — أساسُ التقسيم على الأطوار.
        self.cost_ns: Counter[str] = Counter()
        #: كلفةٌ بالمعالج لا بالذرّة — بلا هذا يبقى «٤٦٥ ثقيلة» بلا موضع.
        self.handler_ns: Counter[tuple[str, str]] = Counter()
        self.handler_calls: Counter[tuple[str, str]] = Counter()
        self.calls: Counter[str] = Counter()
        self.errors: Counter[str] = Counter()
        #: ما قِيس عند حدّ الإقلاع إن جُمِّد — يُعرَض ولا يُدَّعى.
        self.gc_record: dict[str, Any] | None = None
        #: مشرّحُ الداخل — يُمرَّر من الخارج ويركب على حاجز المنافذ نفسه.
        self.profiler = getattr(self.guard, "profiler", None)
        # ── تدقيقُ العُقم (‏`NQ — OPEN CYCLE REDUCTION`) ───────────────────
        #
        # ⛔ يُطفأ افتراضًا: يُجزّئ الحمولة ويُبصمها، وكلفتُه تُفسد أيَّ قياسِ
        #    زمن. يُشغَّل في تشغيلِ تشخيصٍ وحده ولا يدخل مكنسة Gate D.
        #
        # والسؤال الذي يجيبه: من الـ٢٠٧ استدعاءً في الدورة، كم منها
        # **حرّك شيئًا**؟ استدعاءٌ لا ينشر ولا يرى مدخلًا جديدًا مرشّحٌ
        # لأن تقصّه المجموعة المتّسخة. وبلا هذا الرقم يصير التصميم تخمينًا.
        self.audit = False
        self.silent_calls: Counter[str] = Counter()
        self.speaking_calls: Counter[str] = Counter()
        self.repeat_payload: Counter[str] = Counter()
        self.fresh_payload: Counter[str] = Counter()
        #: ⛔ الرقم الحاسم: عددُ الصامتة لا يكفي. لو كانت الصامتةُ رخيصةً
        #:   لما أجدى قصُّها مهما كثُرت. فالكلفة تُفصَل بالمصير لا بالعدد.
        self.silent_ns: Counter[str] = Counter()
        self.speaking_ns: Counter[str] = Counter()
        self._last_seen: dict[tuple[str, str], str] = {}
        self._order = {atom: i for i, atom in enumerate(plan.order)}
        self._folders = self._index_folders()

    @staticmethod
    def _index_folders() -> dict[str, Path]:
        out: dict[str, Path] = {}
        for manifest in sorted((_ROOT / "atoms").rglob("manifest.yaml")):
            out[manifest.parent.name.split("_")[0]] = manifest.parent
        return out

    async def boot(self, *, freeze: bool = False) -> None:
        """يُحمّل ويُقلع كلَّ ذرّةٍ في الخطّة. الفاشلةُ تُسمَّى ولا تُخفى.

        و`freeze` يُجمّد ما بناه الإقلاع **عند حدّه** — ختم المالك
        `NQ — APPLY GC FREEZE AFTER BOOT`. ويقع بعد آخر ذرّةٍ تُقلِع،
        فيشمل الاستيرادَ وتحميلَ الذرّات وتهيئةَ الحالة.
        """
        import yaml

        for atom_id in self.plan.order:
            folder = self._folders.get(atom_id)
            if folder is None:
                self.failed[atom_id] = "لا مجلّد"
                continue
            self.guard.current = atom_id
            try:
                manifest = yaml.safe_load(
                    (folder / "manifest.yaml").read_text(encoding="utf-8"))
                module_name, class_name = str(manifest["entrypoint"]).split(":")
                spec = importlib.util.spec_from_file_location(
                    "nq_host_%s" % atom_id, folder / ("%s.py" % module_name))
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                # ⛔ مجلّد الذرّة على المسار أثناء التحميل: خمسُ ذرّاتٍ
                #    (‏518 · 520 · 552 · 579 · 580) تستورد وحداتٍ مجاورةً
                #    لها، فسقطت بـ`ModuleNotFoundError` ولا علّة فيها —
                #    العلّةُ أنّ مُحمِّلي لم يضع مجلّدها حيث يضعه المُقلِع.
                token = str(folder)
                sys.path.insert(0, token)
                try:
                    spec.loader.exec_module(module)
                finally:
                    if sys.path and sys.path[0] == token:
                        sys.path.pop(0)
                atom = getattr(module, class_name)()
                await self._start(atom_id, atom, manifest)
            except Exception as exc:                           # noqa: BLE001
                self.failed[atom_id] = "%s: %s" % (type(exc).__name__, exc)
        if freeze:
            from hot.gc_gate import freeze_after_boot
            self.gc_record = freeze_after_boot()

    async def _start(self, atom_id: str, atom: Any, manifest: dict) -> None:
        from core.contracts.atom import AtomContext

        async def publish(name: str, payload: Any = None, _a: str = atom_id) -> None:
            if self.profiler is not None:
                start = time.perf_counter_ns()
                self.published.append((_a, str(name), payload))
                self.profiler.current = _a
                self.profiler.charge("publish", time.perf_counter_ns() - start)
                return
            self.published.append((_a, str(name), payload))

        def subscribe(name: str, handler: Any, _a: str = atom_id) -> None:
            self.handlers.setdefault(str(name), []).append((_a, handler))

        context = AtomContext(
            atom_id=int(atom_id), config=manifest.get("config") or {},
            logger=_Silent(self.guard), publish=publish, subscribe=subscribe,
            subscribe_all=lambda handler, _a=atom_id: None)
        await atom.initialize(context)
        await atom.start()
        self.atoms[atom_id] = atom
        self.loaded.append(atom_id)

    @staticmethod
    def coalesce_key(name: str, payload: Any) -> tuple:
        """مفتاحُ الدمج **كما في النواة** — `core/event_bus.py:128`.

        `(اسم الحدث، الحساب، الرمز، المعرّف)` بلا `trace_id`. ولا يُخترَع
        مفتاحٌ ثانٍ: مفتاحان يعنيان دمجَين مختلفَين، فيختلف الرقم عن الحيّ.
        """
        if not isinstance(payload, dict):
            return (name, None, None, None)
        return (name, payload.get("account_id"), payload.get("symbol"),
                payload.get("id"))

    async def cycle(self, event_name: str, payload: Any,
                    *, max_depth: int = 8, coalesce: bool = False
                    ) -> dict[str, Any]:
        """يُشغّل **دورةً كاملة**: مدخلٌ ثمّ تتالي ما يُنشَر، بترتيب الخطّة.

        ⛔ والترتيب ليس ترتيبَ الوصول: المعالجات تُرتَّب بـ`plan.order`،
           وهو ما بنته §5. فما يُقاس هو الدورة كما ستُنفَّذ فعلًا.
        """
        started = time.perf_counter_ns()
        before = len(self.published)
        pending = [(event_name, payload)]
        depth = 0
        handled = 0
        merged = 0
        by_depth: list[int] = []
        while pending and depth < max_depth:
            batch, pending = pending, []
            if coalesce:
                # ⛔ النواة تدمج كلَّ حدثٍ قابلٍ للإعادة **ما دام له نظيرٌ
                #    معلَّق** (`event_bus.py:275`). وحاملٌ بلا دمجٍ يضخّم
                #    العملَ فيُقاس غيرُ ما يجري. يُقاس الوجهان ويُعلَنان.
                seen: dict[tuple, Any] = {}
                for name, body in batch:
                    key = self.coalesce_key(name, body)
                    if key in seen:
                        merged += 1
                    seen[key] = body            # الأحدثُ يحلّ محلّ الأقدم
                batch = list(seen.items())
                batch = [(key[0], body) for key, body in
                         zip(seen.keys(), seen.values())]
            work: list[tuple[int, str, Any, Any]] = []
            for name, body in batch:
                for atom_id, handler in self.handlers.get(name, ()):
                    work.append((self._order.get(atom_id, 10 ** 6),
                                 atom_id, handler, body))
            work.sort(key=lambda row: row[0])
            mark = len(self.published)
            for _rank, atom_id, handler, body in work:
                self.guard.current = atom_id
                if self.audit:
                    said_before = len(self.published)
                    seen_key = (atom_id, getattr(handler, "__qualname__", ""))
                    try:
                        import hashlib
                        import json as _json
                        stamp = hashlib.blake2b(_json.dumps(
                            body, sort_keys=True, default=str).encode("utf-8"),
                            digest_size=8).hexdigest()
                    except Exception:                          # noqa: BLE001
                        stamp = repr(body)[:64]
                    if self._last_seen.get(seen_key) == stamp:
                        self.repeat_payload[atom_id] += 1
                    else:
                        self.fresh_payload[atom_id] += 1
                    self._last_seen[seen_key] = stamp
                t0 = time.perf_counter_ns()
                try:
                    result = handler(body)
                    if asyncio.iscoroutine(result):
                        await result
                except BlockedEffect:
                    self.errors[atom_id] += 1
                except Exception:                              # noqa: BLE001
                    self.errors[atom_id] += 1
                spent = time.perf_counter_ns() - t0
                if self.profiler is not None and self.profiler.enabled:
                    self.profiler.call(atom_id, spent)
                if self.audit:
                    if len(self.published) > said_before:
                        self.speaking_calls[atom_id] += 1
                        self.speaking_ns[atom_id] += spent
                    else:
                        self.silent_calls[atom_id] += 1
                        self.silent_ns[atom_id] += spent
                self.cost_ns[atom_id] += spent
                self.calls[atom_id] += 1
                label = getattr(handler, "__qualname__", None) or repr(handler)
                self.handler_ns[(atom_id, label)] += spent
                self.handler_calls[(atom_id, label)] += 1
                handled += 1
            by_depth.append(len(work))
            pending = [(name, body)
                       for _a, name, body in self.published[mark:]
                       if name in self.handlers]
            depth += 1
        return {
            "wall_ns": time.perf_counter_ns() - started,
            "handled": handled,
            "depth": depth,
            "merged": merged,
            "by_depth": by_depth,
            "published": len(self.published) - before,
        }

    def phase_ns(self) -> dict[str, int]:
        out = {name: 0 for name, _l, _h in PHASES}
        out["outside"] = 0
        for atom_id, value in self.cost_ns.items():
            out[phase_of(atom_id)] += value
        return out

    def report(self) -> dict[str, Any]:
        total = sum(self.cost_ns.values()) or 1
        heaviest = sorted(self.cost_ns.items(), key=lambda kv: -kv[1])[:12]
        return {
            "loaded": len(self.loaded),
            "failed": self.failed,
            "phase_ms": {k: v / 1e6 for k, v in self.phase_ns().items()},
            "heaviest": [(a, round(ns / 1e6, 4), self.calls[a],
                          round(100.0 * ns / total, 1)) for a, ns in heaviest],
            "errors": dict(self.errors),
            "guard": self.guard.report(),
        }
