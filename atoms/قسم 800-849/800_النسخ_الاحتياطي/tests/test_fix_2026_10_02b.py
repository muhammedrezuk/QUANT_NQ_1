"""٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq») — حرّاس إصلاح النسخ الاحتياطيّ (2.8.0).

المقيس قبل الإصلاح: لا نسخة ناجحة منذ ٢٠٢٦-٠٩-١٨ 13:59 UTC. السبب في الكود:
بعد `backup()` كان يُقرأ عدد صفحات **الأصل الحيّ الآن** ويُقارن بالنسخة، والأصل
يكبر كلّ ثوانٍ (`archive.db` +448 صفحة في ثلاثين ثانية بقراءةٍ فقط) — فتُرمى النسخة
«partial copy». ومعه: `-wal`/`-shm` يُنسخان خامًا، والتحقّق عدُّ أعضاء بلا فتح قاعدة،
والفشل بلا سطر سجلّ، والتدريج في `%TEMP%` (48.6 ج.ب بقايا بلا أثر).

كلّ مخزنٍ هنا في `tmp_path`. لا قاعدة حيّة تُلمس.
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sqlite3
import sys
import tarfile
import threading
from pathlib import Path

import yaml

FOLDER = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
for _p in (str(ROOT), str(FOLDER)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.contracts.atom import AtomContext, HealthState  # noqa: E402

_spec = importlib.util.spec_from_file_location("_atom800_fix_b", FOLDER / "atom.py")
mod = importlib.util.module_from_spec(_spec)
sys.modules["_atom800_fix_b"] = mod
_spec.loader.exec_module(mod)

MANIFEST = yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8"))


class _Logger:
    def __init__(self):
        self.errors = []

    def error(self, msg, *args):
        self.errors.append(msg % args if args else msg)

    def __getattr__(self, name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.published = []
        self.handlers = {}

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload=None):
        self.published.append((name, payload))
        for handler in self.handlers.get(name, []):
            result = handler(payload)
            if inspect.isawaitable(result):
                await result

    def of(self, name):
        return [p for n, p in self.published if n == name]


def _make_db(path: Path, rows: int = 200, wal: bool = True) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), check_same_thread=False)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
    con.execute("CREATE INDEX IF NOT EXISTS t_v ON t(v)")
    con.executemany("INSERT INTO t (v) VALUES (?)", [("row-%06d" % i,) for i in range(rows)])
    con.commit()
    return con


async def _atom(tmp_path: Path, logger=None, **over):
    bus = _Bus()
    cfg = {"backup_dir": str(tmp_path / "backups"), "source_dirs": [str(tmp_path / "store")],
           "keep_last_n": 7, "interval_days": 1, "min_source_bytes": 1,
           "staging_dir": str(tmp_path / "backups" / "staging")}
    cfg.update(over)
    atom = mod.Atom()
    await atom.initialize(AtomContext(800, cfg, logger or _Logger(), bus.publish, bus.subscribe))
    await atom.start()
    return atom, bus


# ٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — الصيانة في استراحة السوق): النسخة تقع في نافذة الصيانة وحدها —
# الإثنين ٢٠٢٦-١٠-٠٥ 17:30 بتوقيت نيويورك داخل استراحة الوسيط، فالنبضة هناك هي ما يشغّلها.
IN_WINDOW = 1_791_235_800.0


async def _run(atom, bus, when=IN_WINDOW):
    await bus.publish(mod.EVENT_PULSE, {"official_time": when})
    task = atom._backup_task
    if task is not None:
        await task


def _archive_names(tmp_path: Path) -> list[str]:
    found = sorted((tmp_path / "backups").glob("backup_*.tar.gz"))
    assert found, "ما كُتبت نسخة"
    with tarfile.open(found[-1], "r:gz") as tar:
        return tar.getnames()


class _GrowingSource:
    """مصدرٌ حيّ يكتب غيرُنا فيه لحظةَ انتهاء النسخ — كما تكتب 707 و712 كلّ ثوانٍ.

    يلفّ اتّصال القراءة: بعد `backup()` يُدرَج في الأصل من اتّصالٍ آخر، فيكبر عدد
    صفحاته. أيّ كودٍ يعيد قراءة الأصل بعد النسخ ويقارنه بالنسخة يرمي «partial copy».
    """

    def __init__(self, real, path):
        self._real = real
        self._path = path

    def backup(self, target, *args, **kwargs):
        self._real.backup(target, *args, **kwargs)
        writer = sqlite3.connect(self._path)
        writer.executemany("INSERT INTO t (v) VALUES (?)",
                           [("late-%06d" % i + "x" * 200,) for i in range(400)])
        writer.commit()
        writer.close()

    def __getattr__(self, name):
        return getattr(self._real, name)


async def test_live_source_that_grows_during_copy_still_backs_up(tmp_path, monkeypatch):
    """الإصلاح الأوّل: لا مقارنة بأصلٍ حيّ — النسخة المتّسقة تمرّ وإن كتب غيرُنا."""
    store = tmp_path / "store"
    store.mkdir()
    holder = _make_db(store / "live.db", rows=500)
    real_connect = sqlite3.connect

    def connect(target, *args, **kwargs):
        con = real_connect(target, *args, **kwargs)
        if isinstance(target, str) and target.endswith("?mode=ro") and "live.db" in target:
            return _GrowingSource(con, str(store / "live.db"))
        return con

    monkeypatch.setattr(sqlite3, "connect", connect)
    logger = _Logger()
    atom, bus = await _atom(tmp_path, logger)
    await _run(atom, bus)
    monkeypatch.setattr(sqlite3, "connect", real_connect)
    holder.close()
    assert not bus.of(mod.EVENT_FAILED), bus.of(mod.EVENT_FAILED)
    done = bus.of(mod.EVENT_DONE)
    assert done and done[0]["checks"]["checked"] == 1, done
    assert atom.backup_count == 1 and logger.errors == []


async def test_journals_are_never_copied_raw_and_each_copy_opens_clean(tmp_path):
    """الإصلاح الثاني والثالث: لا `-wal`/`-shm` خامًا، وكلّ نسخةٍ تُفتح وتُفحص."""
    store = tmp_path / "store"
    store.mkdir()
    keep_open = [_make_db(store / "a.db"), _make_db(store / "b.db", rows=50)]
    (store / "notes.txt").write_text("x", encoding="utf-8")
    assert (store / "a.db-wal").exists() and (store / "a.db-shm").exists()
    atom, bus = await _atom(tmp_path)
    await _run(atom, bus)
    for con in keep_open:
        con.close()
    names = _archive_names(tmp_path)
    assert not [n for n in names if n.endswith(("-wal", "-shm", "-journal"))], names
    assert {Path(n).name for n in names} == {"a.db", "b.db", "notes.txt"}, names
    done = bus.of(mod.EVENT_DONE)[0]
    assert done["checks"]["checked"] == 2 and not done["checks"]["failed"], done
    assert done["checks"]["integrity_check"] == 2, done
    assert done["skipped_journals"] >= 4, done
    # النسخة نفسها تُفتح من الأرشيف وتمرّ الفحص الكامل — استرجاعٌ مُجرَّب لا مفترض.
    out = tmp_path / "restore"
    with tarfile.open(sorted((tmp_path / "backups").glob("backup_*.tar.gz"))[-1], "r:gz") as tar:
        tar.extractall(out, filter="data")
    for db in out.rglob("*.db"):
        con = sqlite3.connect(str(db))
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok", db
        assert con.execute("SELECT COUNT(*) FROM t").fetchone()[0] > 0
        con.close()
    # لا بقايا تدريج بعد نجاح.
    assert list((tmp_path / "backups" / "staging").iterdir()) == []


async def test_failed_check_is_loud_degraded_and_set_aside_not_deleted(tmp_path, monkeypatch):
    """الإصلاح الرابع والخامس: الفشل سطر ERROR وصحّة متدهورة، والمخرَج يُنحّى ولا يُمسح."""
    store = tmp_path / "store"
    store.mkdir()
    _make_db(store / "a.db", wal=False).close()
    monkeypatch.setattr(mod, "_verify_copy",
                        lambda path, limit: ("integrity_check", "row 3 missing from index t_v"))
    logger = _Logger()
    atom, bus = await _atom(tmp_path, logger)
    await _run(atom, bus)
    failed = bus.of(mod.EVENT_FAILED)
    assert failed and "row 3 missing" in failed[0]["reason"], failed
    assert failed[0]["checks"]["failed"], failed
    assert any("BACKUP_FAILED" in line and "row 3 missing" in line for line in logger.errors), logger.errors
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED and "row 3 missing" in health.message
    assert not list((tmp_path / "backups").glob("backup_*.tar.gz"))
    staging = tmp_path / "backups" / "staging"
    aside = [p for p in staging.iterdir() if p.name.startswith("incomplete-")]
    assert len(aside) == 1 and not list(staging.glob("run-*")), list(staging.iterdir())
    kept = sorted(p.name for p in aside[0].iterdir())
    assert "backup.tar.gz.tmp" in kept and "0.db" in kept, kept
    assert failed[0]["partial_output"] == str(aside[0])
    snap = await atom.snapshot()
    assert snap["incomplete"]["dirs"] == 1 and snap["incomplete"]["bytes"] > 0, snap
    # والسبب يعبر الإقلاع: صحّةُ مثيلٍ مستعاد متدهورة بالسبب نفسه.
    again, _bus = await _atom(tmp_path)
    await again.restore(snap)
    restored = await again.health_check()
    assert restored.state == HealthState.DEGRADED and "row 3 missing" in restored.message


async def test_unreadable_database_fails_loud_too(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    (store / "broken.db").write_bytes(b"this is not a database" * 400)
    logger = _Logger()
    atom, bus = await _atom(tmp_path, logger)
    await _run(atom, bus)
    assert bus.of(mod.EVENT_FAILED) and logger.errors
    assert (await atom.health_check()).state == HealthState.DEGRADED


async def test_killed_run_is_set_aside_on_start_and_named(tmp_path):
    """تشغيلةٌ قُتلت مع العمليّة لا تمرّ بمسار الفشل — تُنحّى عند الإقلاع وتُعلَن."""
    staging = tmp_path / "backups" / "staging"
    run = staging / "run-20261002T121109Z"
    run.mkdir(parents=True)
    (run / "1.db").write_bytes(b"\0" * 4096)
    (tmp_path / "store").mkdir()
    legacy = tmp_path / "backups" / ".backup.zz.tar.gz.tmp"
    legacy.write_bytes(b"\0" * 100)
    logger = _Logger()
    atom, _bus = await _atom(tmp_path, logger)
    assert not run.exists() and (staging / "incomplete-20261002T121109Z" / "1.db").exists()
    assert not legacy.exists() and list(staging.glob("incomplete-legacy-*/.backup.zz.tar.gz.tmp"))
    assert atom.orphans_cleared == 2 and atom.orphan_bytes_cleared == 4196
    assert any("BACKUP_RUN_INTERRUPTED" in line for line in logger.errors), logger.errors
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED and "INTERRUPTED" in health.message
    assert health.details["incomplete"]["dirs"] == 2


async def test_old_success_degrades_health_by_official_clock(tmp_path):
    (tmp_path / "store").mkdir()
    atom, bus = await _atom(tmp_path)
    await atom.restore({"last_success": 1_000_000.0, "backup_count": 10})
    atom._catchup_done = True          # لا نسخة الآن — يُقاس الحكم على العمر وحده
    await bus.publish(mod.EVENT_PULSE, {"official_time": 1_000_000.0 + 14 * 86400.0})
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED and "BACKUP_STALE" in health.message


def test_staging_folder_and_check_dial_are_declared_in_the_manifest():
    cfg = MANIFEST["config"]
    props = MANIFEST["config_schema"]["properties"]
    assert cfg["staging_dir"].startswith("var/backups"), cfg
    assert int(cfg["full_check_max_bytes"]) >= 1
    assert "staging_dir" in props and "full_check_max_bytes" in props
    source = inspect.getsource(mod.Atom._run_backup)
    assert "TemporaryDirectory" not in source and "mkstemp" not in source
