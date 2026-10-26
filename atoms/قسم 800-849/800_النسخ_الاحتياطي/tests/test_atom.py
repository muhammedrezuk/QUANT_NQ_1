import asyncio
import inspect
import os
import sys
import tarfile
import tempfile
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom800", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom800"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_DAY = _mod.EVENT_DAY
EVENT_DONE = _mod.EVENT_DONE
EVENT_PULSE = _mod.EVENT_PULSE

# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): النسخة في نافذة الصيانة وحدها، لا على
# نبض اليوم. الإثنين ٢٠٢٦-١٠-٠٥ 17:30 بتوقيت نيويورك (21:30 غرينتش) داخل استراحة الوسيط اليوميّة،
# والأيّام التالية حتّى الخميس داخلها أيضًا بالساعة نفسها.
IN_WINDOW = 1_791_235_800.0
DAY_S = 86_400.0
# الخميس ٢٠٢٦-١٠-٠٨ منتصف ليل غرينتش = 03:00 بتوقيت الجهاز — موعد نبض اليوم القديم والسوق مفتوح.
DAY_PULSE_0300 = 1_791_417_600.0


class _NullLogger:
    def debug(self, *a): pass
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


class FakeEventBus:
    def __init__(self):
        self.published = []
        self._handlers = {}

    def subscribe(self, name, handler):
        self._handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.published.append((name, payload))
        for h in self._handlers.get(name, []):
            r = h(payload)
            if inspect.isawaitable(r):
                await r

    def make_context(self, cfg):
        return AtomContext(atom_id=800, config=cfg, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _dirs():
    root = tempfile.mkdtemp()
    src = os.path.join(root, "store")
    bak = os.path.join(root, "backups")
    os.makedirs(src)
    with open(os.path.join(src, "data.txt"), "w") as f:
        f.write("hello")
    return root, src, bak


async def _make(bus, src, bak, keep=7, interval=1, min_bytes=1):
    atom = Atom()
    await atom.initialize(bus.make_context(
        {"backup_dir": bak, "source_dirs": [src], "keep_last_n": keep,
         "interval_days": interval, "min_source_bytes": min_bytes}))
    await atom.start()
    return atom


def _backups(bak):
    if not os.path.isdir(bak):
        return []
    return sorted(f for f in os.listdir(bak)
                  if f.startswith("backup_") and f.endswith(".tar.gz"))


async def _settle(atom):
    """ينتظر النسخةَ المجدولة — لا يُغيّر العقد، يقف مقام مرور الوقت.

    منذ ٢٠٢٦-٠٩-٢٣ لا يُنتظَر النسخُ في المعالج (كان يحجبه دقائق ويُقطع،
    فمضت خمسة أيّام بلا نسخة). فقراءةُ القرص فور النشر صارت سباقًا مع
    مهمّةٍ خلفيّة. و**متى** تكتمل يُختبَر وحده في
    `test_backup_is_scheduled_not_awaited_in_the_handler` — وهناك بلا
    هذه المساعدة.
    """
    task = getattr(atom, "_backup_task", None)
    if task is not None and not task.done():
        await task


async def test_backup_in_maintenance_window():
    print("\n--- test_backup_in_maintenance_window ---")
    root, src, bak = _dirs()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, src, bak)
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        await _settle(atom)
        bks = _backups(bak)
        assert bks == ["backup_%d.tar.gz" % IN_WINDOW], bks
        with tarfile.open(os.path.join(bak, bks[0]), "r:gz") as tar:
            names = tar.getnames()
        assert any(n.endswith("data.txt") for n in names), names
        done = [p for n, p in bus.published if n == EVENT_DONE][-1]
        assert done["file_count"] == 1 and done["timestamp"] == IN_WINDOW, done
        print(f"OK — نسخ احتياطي في نافذة الصيانة (بلا time.time): {bks[0]} · محتوى={names}")
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


async def test_day_pulse_outside_window_does_not_back_up():
    """نبض اليوم (03:00 بتوقيت الجهاز والسوق مفتوح) لا ينسخ — يُعدّ، والنسخة تنتظر النافذة."""
    print("\n--- test_day_pulse_outside_window_does_not_back_up ---")
    root, src, bak = _dirs()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, src, bak)
        await bus.publish(EVENT_DAY, {"official_time": DAY_PULSE_0300})
        await bus.publish(EVENT_PULSE, {"official_time": DAY_PULSE_0300 + 1})
        await _settle(atom)
        assert not _backups(bak) and atom._backup_task is None, _backups(bak)
        assert atom._maintenance.held_outside == 1, atom._maintenance.held_outside
        assert atom._catchup_verdict["status"] == "NEVER_RAN"
        # ٢٠٢٦-١٠-١٢ (أمر المالك «NQ»: «إذا السستم كان واقف لحظة اللقطة، لازم مع أوّل إقلاع ياخد لقطة»): قبل عشر دقائق
        # من الإقلاع لا نسخة، وبعدها تقع النسخة الفائتة فورًا — لا تنتظر نافذة الليلة القادمة.
        await bus.publish(EVENT_PULSE, {"official_time": DAY_PULSE_0300 + 300})
        await _settle(atom)
        assert not _backups(bak), _backups(bak)
        await bus.publish(EVENT_PULSE, {"official_time": DAY_PULSE_0300 + 1 + 600})
        await _settle(atom)
        done = [p for n, p in bus.published if n == EVENT_DONE]
        assert len(done) == 1 and done[0]["trigger"] == "BOOT_NEVER_RAN", done
        print("OK — نبض اليوم أُمسك (١) · والنسخة الفائتة وقعت بعد الإقلاع بعشر دقائق")
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


async def test_interval_skip():
    print("\n--- test_interval_skip ---")
    root, src, bak = _dirs()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, src, bak, interval=1)
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        await _settle(atom)
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW + 600})  # النافذة نفسها
        await _settle(atom)
        assert _backups(bak) == ["backup_%d.tar.gz" % IN_WINDOW], "second within window skipped"
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW + DAY_S})  # نافذة الغد
        await _settle(atom)
        assert len(_backups(bak)) == 2, "next window runs"
        print("OK — مرّةً واحدة في كلّ نافذة، والفاصل من official_time")
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


async def test_retention():
    print("\n--- test_retention ---")
    root, src, bak = _dirs()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, src, bak, keep=2, interval=1)
        stamps = [IN_WINDOW + day * DAY_S for day in range(3)]
        for t in stamps:
            await bus.publish(EVENT_PULSE, {"official_time": t})
            await _settle(atom)
        bks = _backups(bak)
        assert bks == ["backup_%d.tar.gz" % t for t in stamps[1:]], bks
        print(f"OK — احتفاظ بآخر N نسخة فقط (keep=2): {bks}")
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


async def test_health_states():
    print("\n--- test_health_states ---")
    root, src, bak = _dirs()
    try:
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"backup_dir": bak, "source_dirs": [src], "keep_last_n": 7,
             "interval_days": 1, "min_source_bytes": 1}))
        assert (await atom.health_check()).state == HealthState.UNHEALTHY
        await atom.start()
        # قاعدة الصدق (أمر المالك ٢٠٢٦-٠٨-١٩): «لم تعمل بعد» مع جدولة مسلّحة
        # وبلا خطأ = جاهزية سليمة برسالة صادقة، لا تعثّر.
        ready = await atom.health_check()
        assert ready.state == HealthState.HEALTHY and "READY" in ready.message, ready.message
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        await _settle(atom)
        assert (await atom.health_check()).state == HealthState.HEALTHY
        print("OK — الصحة: UNHEALTHY -> HEALTHY(جاهز) -> HEALTHY(backups)")
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


async def test_excluded_patterns_are_skipped_and_counted():
    """الأرشيفُ المغلق لا يُنسَخ — والاستثناء يُعلَن بعدده.

    ⚠️ مقيس ٢٠٢٦-٠٩-٢٣: `var/store` **٢٦٫٤ ج.ب** منها **١٠٫٤٨ في اثني عشر
    ملفّ `archive.closed.*`**، ونما ٧٫٤ ج.ب في يوم. وكلفةُ نسخِها ليست قرصًا
    فقط: تزاحمُ النسخة مع المخازن رفع `sqlite` إلى **٤٫٨ ثانية** للإدراج
    الواحد، فامتلأ بفر ٧٠٧ عند ١٠٬٠٠٠ **وأُسقط ١٬٣٤٩ قرارًا**. فالنسخُ كان
    يكلّف قرارات. وهي ملفّاتٌ **مغلقة لا تتغيّر**، فنسخُها يوميًّا تكرار.
    """
    print("\n--- test_excluded_patterns_are_skipped_and_counted ---")
    root, src, bak = _dirs()
    try:
        # أرشيفان مغلقان، وملفٌّ حيّ يجب أن يبقى
        for name in ("archive.closed.1.db", "archive.closed.2.db"):
            with open(os.path.join(src, name), "wb") as fh:
                fh.write(b"\0" * 64)
        bus = FakeEventBus()
        atom = Atom()
        await atom.initialize(bus.make_context(
            {"backup_dir": bak, "source_dirs": [src], "keep_last_n": 7,
             "interval_days": 1, "min_source_bytes": 1,
             "exclude_patterns": ["*/archive.closed.*", "archive.closed.*"]}))
        await atom.start()
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        await _settle(atom)

        bks = _backups(bak)
        assert bks, "ما كُتبت نسخة"
        with tarfile.open(os.path.join(bak, bks[0]), "r:gz") as tar:
            names = tar.getnames()
        assert any(n.endswith("data.txt") for n in names), names
        assert not any("archive.closed" in n for n in names), names
        assert atom.last_excluded == 2, atom.last_excluded
        print("OK — استُثني ٢ ومحتوى النسخة %s" % names)
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


async def test_orphaned_temp_files_are_cleared_on_start():
    """يتامى النسخ المقتولة تُمسح عند الإقلاع — ولا يُمسّ شيءٌ غيرها.

    ⚠️ نزيفٌ مقيس ٢٠٢٦-٠٩-٢٣: **٣٫٦١ جيجابايت في يومين**. تنظيفي مكتوبٌ في
    `except BaseException` وهو لا يُنفَّذ حين تُقتل العمليّة — والنسخة تستغرق
    أطول من الفاصل بين الإقلاعات، فثلاثة إقلاعاتٍ قتلت ثلاثًا وتركت أيتامًا
    أكبرُها ١٬٣٣١ م.ب. وكلُّ إقلاعٍ يزيدها.
    """
    print("\n--- test_orphaned_temp_files_are_cleared_on_start ---")
    root, src, bak = _dirs()
    try:
        os.makedirs(bak, exist_ok=True)
        # ثلاثة أيتام، ونسخةٌ نهائيّة، وملفٌّ غريب — يُمسّ الأيتام وحدهم
        for name, size in ((".backup.aaa.tar.gz.tmp", 2048),
                           (".backup.bbb.tar.gz.tmp", 4096),
                           (".backup.ccc.tar.gz.tmp", 1024)):
            with open(os.path.join(bak, name), "wb") as fh:
                fh.write(b"\0" * size)
        keep = os.path.join(bak, "backup_999.tar.gz")
        with open(keep, "wb") as fh:
            fh.write(b"\0" * 10)
        stranger = os.path.join(bak, "snapshot_x.zip")
        with open(stranger, "wb") as fh:
            fh.write(b"\0" * 10)

        bus = FakeEventBus()
        atom = await _make(bus, src, bak, min_bytes=1)

        assert atom.orphans_cleared == 3, atom.orphans_cleared
        assert atom.orphan_bytes_cleared == 7168, atom.orphan_bytes_cleared
        left = sorted(os.listdir(bak))
        assert not any(n.startswith(".backup.") for n in left), left
        assert "backup_999.tar.gz" in left, "مُسحت نسخةٌ نهائيّة"
        assert "snapshot_x.zip" in left, "مُسح ملفٌّ ليس لي"
        print("OK — مُسح ٣ أيتام (٧٬١٦٨ بايت) · والنهائيّ والغريب سالمان")
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


async def test_backup_is_scheduled_not_awaited_in_the_handler():
    """النسخ يُجدوَل ولا يحجب المعالج — ولو استغرق دقائق.

    ⚠️ عطبٌ سبّبتُه أنا: قبل ٢٠٢٦-٠٩-١٩ كانت النسخة ٢٧ ك.ب من شجرةٍ شبحيّة
    فارغة فلا يُحسّ انتظارُها، ثمّ وجّهتُها إلى المخزن الحقيقيّ (١٥٫١ ج.ب)
    وتركتُها تُنتظَر. المقيس ٢٠٢٦-٠٩-٢٣: `handler timeout subscriber=800`
    ثلاثًا في يوم، و**آخر نجاحٍ ٢٠٢٦-٠٩-١٨ — خمسة أيّام بلا نسخة**،
    و`backup_count` عالقٌ عند ١٠. الإصلاح صوّب الوجهة وقتل العمليّة.
    """
    print("\n--- test_backup_is_scheduled_not_awaited_in_the_handler ---")
    root, src, bak = _dirs()
    try:
        bus = FakeEventBus()
        atom = await _make(bus, src, bak, min_bytes=1)
        slow = __import__("threading").Event()
        real = atom._run_backup

        def slow_backup(now):
            slow.wait(timeout=10)          # نسخةٌ بطيئة كالتي قِيست حيًّا
            return real(now)
        atom._run_backup = slow_backup

        started = time.perf_counter()
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        elapsed = time.perf_counter() - started

        assert elapsed < 0.050, (
            "المعالج انتظر النسخة %.3f ث والميزانية ٠٫٠٥٠" % elapsed)
        assert atom._backup_task is not None, "ما جُدولت النسخة"

        # ونبضةٌ ثانية في النافذة نفسها لا تجدول شيئًا، ونداءٌ مباشرٌ والنسخةُ جارية ⟹ يُتخطّى
        # ولا تتوازى نسختان
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW + 1})
        assert atom.backup_skipped == 0, atom.backup_skipped
        assert atom._schedule_backup(IN_WINDOW + 2, "direct") is False
        assert atom.backup_skipped == 1, atom.backup_skipped

        slow.set()
        await atom._backup_task               # وتكتمل فعلًا — لا فقد
        assert atom.backup_count == 1, atom.backup_count
        assert _backups(bak), "ما كُتبت النسخة بعد اكتمال المهمّة"
        print("OK — المعالج رجع بـ%.4f ث · تُخطّي ١ · والنسخة اكتملت" % elapsed)
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


async def test_relative_source_is_anchored_to_the_code_root():
    """مصدرٌ نسبيّ لا يُحلّ نسبةً إلى مجلد التشغيل — ولو تبدّل المجلد.

    هذه هي العلّة التي أخرجت ثلاثة أسابيع من النسخ صدفةً فارغة: ``var/store``
    كان يُقرأ نسبةً إلى مجلد العمل فيصيب شجرةً شبحيّة (٥٠ ملفًّا، ١٫٠ م.ب) بدل
    المخزن الحيّ (٥١ ملفًّا، ١٥٫٣ جيجابايت). مقيس ٢٠٢٦-٠٩-١٩.
    """
    print("\n--- test_relative_source_is_anchored_to_the_code_root ---")
    root = _mod._code_root()
    assert root is not None, "لم يُعثر على جذر الكود"
    here = os.getcwd()
    try:
        os.chdir(tempfile.mkdtemp())
        anchored = _mod._anchor("config")
    finally:
        os.chdir(here)
    assert _Path(anchored).is_absolute(), "المصدر بقي نسبيًّا: %s" % anchored
    assert anchored == str((root / "config").resolve()), (
        "أُرسي على غير جذر الكود: %s" % anchored)
    print("OK — المصدر النسبيّ يُرسى على جذر الكود ولو بُدِّل مجلد التشغيل")


async def test_shell_copies_do_not_pass_as_a_backup():
    """خمسون صدفةً فارغة ليست نسخة — والعدد لا يحرس، البايت يحرس.

    `file_count == 0` كان الحارس الوحيد، فمرّت كلّ نسخةٍ فارغة لأنّ خمسين
    ليست صفرًا.
    """
    print("\n--- test_shell_copies_do_not_pass_as_a_backup ---")
    root, src, bak = _dirs()
    try:
        bus = FakeEventBus()
        # الملفّ خمسة بايتات ("hello")، والعتبة أكبر منه بكثير
        atom = await _make(bus, src, bak, min_bytes=1_000_000)
        await bus.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        await _settle(atom)
        assert not _backups(bak), "نسخةٌ دون العتبة كُتبت"
        failed = [p for n, p in bus.published if n == _mod.EVENT_FAILED]
        assert failed, "لم يُنطق الفشل"
        assert "too small" in failed[0]["reason"], failed[0]["reason"]
        assert atom.backup_count == 0, "عُدّت نسخةٌ لم تُكتب"
        # وبعتبةٍ يبلغها المحتوى تمرّ: الحارس يميّز ولا يمنع كلّ شيء
        bus2 = FakeEventBus()
        atom2 = await _make(bus2, src, bak, min_bytes=1)
        await bus2.publish(EVENT_PULSE, {"official_time": IN_WINDOW})
        await _settle(atom2)
        assert _backups(bak), "الحارس منع نسخةً صالحة"
        assert atom2.backup_count == 1
        done = [p for n, p in bus2.published if n == EVENT_DONE]
        assert done[0]["source_bytes"] == 5, done[0]["source_bytes"]
        print("OK — الأصداف تُردّ، والنسخة الصالحة تمرّ · source_bytes منشور")
    finally:
        __import__("shutil").rmtree(root, ignore_errors=True)


async def main():
    tests = [test_excluded_patterns_are_skipped_and_counted,
             test_orphaned_temp_files_are_cleared_on_start,
             test_backup_is_scheduled_not_awaited_in_the_handler,
             test_backup_in_maintenance_window,
             test_day_pulse_outside_window_does_not_back_up, test_interval_skip, test_retention,
             test_health_states, test_relative_source_is_anchored_to_the_code_root,
             test_shell_copies_do_not_pass_as_a_backup]
    failed = []
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            failed.append((t.__name__, str(e))); print(f"FAILED: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e))); print(f"ERROR: {t.__name__}: {e!r}")
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}"); sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())
