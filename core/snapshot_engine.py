"""
Core.snapshot_engine
======================
Article 13 (الدستور الأول والثاني): أي ذرة تدعم Snapshot (تُنفِّذ
snapshot() وتُرجع غير None) تُلتقط تلقائيًا. أي ذرة لا تدعمه (تُرجع
None أو ترث التنفيذ الافتراضي) تُتجاوز دون خطأ — لا حاجة لأي تسجيل
يدوي مسبق.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.registry import Registry

_log = logging.getLogger("quant_nq.core.snapshot_engine")

# مهلة قصوى لكل استدعاء snapshot()/restore() داخل ذرة. بدونها تستطيع
# ذرة واحدة معلّقة أن تجمّد إيقاف Core بأكمله (المادة 81/89).
DEFAULT_ATOM_TIMEOUT_S = 10.0

# ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ختم سلامة اللقطة. كانت JSON خامًا بلا ختم،
# ولقطةٌ تالفة ⟵ استثناء في `restore_hook` ⟵ الذرّة FAILED لا تُقلع. الآن:
#   • الكتابة: `sha256` على نصّ الحمولة القانونيّ نفسه (`json.dumps(state,
#     ensure_ascii=False)` — البايتات التي تُكتب حرفًا) يُلحق حقلًا أخيرًا في الكائن.
#     فالملفّ يبقى JSON يقرؤه كلّ قارئٍ خارجيّ بالمفاتيح نفسها وحقلٍ زائد.
#   • القراءة: JSON لا يُحلَّل أو ختمٌ لا يطابق ⟵ يُعزل الملفّ إلى
#     `<id>.json.corrupt-<وقت>` (لا يُحذف أبدًا)، وتُقلع الذرّة **بلا حالة**، ويُكتب
#     خطأ ويُرفع علمٌ (`integrity_failures`/`integrity_report()`) تقرؤه الصحّة والمحرّك.
#   • لقطةٌ قديمة بلا الحقل تُقرأ كما كانت حرفًا.
INTEGRITY_FIELD = "_snapshot_sha256"
_INTEGRITY_KEY_BYTES = ('"%s": "' % INTEGRITY_FIELD).encode("ascii")
_INTEGRITY_TAIL = re.compile(rb'"%s": "([0-9a-f]{64})"\}\s*' % INTEGRITY_FIELD.encode("ascii"))


@dataclass(slots=True)
class SnapshotReport:
    captured: list[int] = field(default_factory=list)
    restored: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)


class SnapshotEngine:
    def __init__(
        self, registry: Registry, storage_dir: Path, *,
        atom_timeout_s: float = DEFAULT_ATOM_TIMEOUT_S,
    ) -> None:
        self._registry = registry
        self._storage_dir = storage_dir
        self._atom_timeout_s = atom_timeout_s
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        #: آخرُ مجموعةٍ أُعلنت لكلّ نوع، فلا يتكرّر الخبر مع كلّ دورة.
        self._announced: dict[str, set[int]] = {}
        #: ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): لقطاتٌ رُفضت عند القراءة (تحليلٌ أو ختم)
        #: ⟵ عُزلت وأقلعت ذرّتها بلا حالة. علمٌ يبقى مرفوعًا حتّى نهاية العمليّة.
        self.integrity_failures: dict[int, dict[str, Any]] = {}
        self._sweep_orphan_temps()

    def _sweep_orphan_temps(self) -> None:
        """كنس ملفات الكتابة المؤقّتة اليتيمة من تشغيل سابق.

        `_write` ينظّف نفسه عبر `except BaseException`، لكن ذلك لا يعمل
        إذا قُتلت العملية وسط الكتابة — فيبقى ملف بحجم الحمولة كاملة ولا
        شيء يزيله أبدًا. مقيس 2026-09-09: ستة ملفات يتيمة، أكبرها 1145
        ميغابايت راكدًا 51 دقيقة، ومجلد اللقطات 2.7 جيجابايت.

        الحذف هنا آمن حتى لو كان هناك كاتب حيّ: ويندوز يمنع حذف ملف
        مفتوح، فيرتدّ الأمر بـ OSError ونتجاوزه — لا نلمس كتابة جارية.
        """
        for tmp in self._storage_dir.glob(".*.tmp"):
            try:
                size = tmp.stat().st_size
                tmp.unlink()
            except OSError as exc:  # noqa: PERF203 — كاتب حيّ يحتجزه، أو سُحب قبلنا
                _log.warning("تعذّر كنس ملف لقطة مؤقّت %s: %s", tmp.name, exc)
                continue
            _log.warning("كُنس ملف لقطة مؤقّت يتيم: %s (%d بايت)", tmp.name, size)

    async def snapshot_all(self) -> SnapshotReport:
        report = SnapshotReport()
        for record in self._registry.all():
            try:
                state = await asyncio.wait_for(
                    record.instance.snapshot(), timeout=self._atom_timeout_s
                )
                if state is None:
                    report.skipped.append(record.id)
                    continue
                await asyncio.to_thread(self._write, record.id, state)
            except NotImplementedError:
                report.skipped.append(record.id)
                continue
            except Exception as exc:  # noqa: BLE001 — كود ذرة خارجي، أو state غير قابل للتسلسل JSON، أو خطأ قرص
                _log.error("فشل snapshot للذرة %s: %s", record.id, exc)
                report.failed.append(record.id)
                continue

            report.captured.append(record.id)
        self._announce_drops(report)
        return report

    def _announce_drops(self, report: "SnapshotReport") -> None:
        """يُعلن مَن سقط من الحفظ ومَن عاد إليه — **بالتغيّر لا بالقائمة**.

        ⚠️ ٢٠٢٦-٠٩-٢٣ — `report.skipped` كان يُملأ ولا يقرؤه أحد في
        التشغيل: `run_core` ينظر إلى `captured` وحدها وبمستوى DEBUG،
        و`failed` لا يُسجَّل إلّا عند الإغلاق. فذرّةٌ تتوقّف عن الحفظ
        تبقى خضراء بلا سطرٍ واحد.

        المقيس يوم كتابة هذا: الذرّات ١٥١–١٦٥ لم تكتب لقطةً منذ **١١٤
        ساعة** بينما كتبت السبعُ والتسعون الأخرى قبل ٩٦ دقيقة — وبقي
        ذلك صامتًا خمسة أيّام. وثمنُه لم يكن في الحفظ: ٥٠٦ استعاد
        `session` من لقطةٍ بائتة، فلم تتغيّر الجلسة، فلم تُصفَّر نافذةُ
        خسارتها، فاشتعل قاطعُ الـ١٠٪ على نافذةٍ أطول من جلسة.

        ولا تُطبع القائمة: ثمانون ذرّةً لا تدعم اللقطة أصلًا (تُرجع
        `None` بعقد المادة ١٣)، فطباعتها كلّ دورة تُغرق الخبر. يُعلَن
        **الداخل إلى الصمت والخارج منه** — وهو الحدث الذي يستحقّ قراءة.
        """
        for name, now in (("تخطّي", set(report.skipped)),
                          ("فشل", set(report.failed))):
            was = self._announced.setdefault(name, set())
            entered = now - was
            left = was - now
            if entered:
                _log.error("ذرّاتٌ سقطت من حفظ الحالة (%s): %s",
                           name, sorted(entered))
            if left:
                _log.info("ذرّاتٌ عادت إلى حفظ الحالة (%s): %s",
                          name, sorted(left))
            self._announced[name] = now

    async def restore_one(self, atom_id: int) -> bool:
        """Restore one initialized instance before its start phase."""
        record = self._registry.find(atom_id)
        if record is None:
            return False
        state = await asyncio.to_thread(self._read, atom_id)
        if state is None:
            return False
        await asyncio.wait_for(record.instance.restore(state), timeout=self._atom_timeout_s)
        return True

    async def snapshot_one(self, atom_id: int) -> bool:
        record = self._registry.find(atom_id)
        if record is None:
            return False
        state = await asyncio.wait_for(record.instance.snapshot(), timeout=self._atom_timeout_s)
        if state is None:
            return False
        await asyncio.to_thread(self._write, atom_id, state)
        return True

    async def restore_all(self) -> SnapshotReport:
        report = SnapshotReport()
        for record in self._registry.all():
            before = self.integrity_failures.get(record.id)
            try:
                state = await asyncio.to_thread(self._read, record.id)
            except Exception as exc:  # noqa: BLE001 — خطأ قرص عند القراءة
                _log.error("فشل قراءة snapshot المخزَّن للذرة %s: %s", record.id, exc)
                report.failed.append(record.id)
                continue

            if state is None:
                # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): لقطةٌ عُزلت في هذه القراءة (تالفة)
                # فشلٌ معلَن، لا «لا لقطة».
                if self.integrity_failures.get(record.id) is not before:
                    report.failed.append(record.id)
                else:
                    report.skipped.append(record.id)
                continue
            try:
                await asyncio.wait_for(
                    record.instance.restore(state), timeout=self._atom_timeout_s
                )
                report.restored.append(record.id)
            except NotImplementedError:
                report.skipped.append(record.id)
            except Exception as exc:  # noqa: BLE001
                _log.error("فشل استعادة snapshot للذرة %s: %s", record.id, exc)
                report.failed.append(record.id)
        return report

    def discard(self, atom_id: int) -> bool:
        """يحذف لقطة ذرة أُزيلت نهائيًا — يمنع تراكم لقطات يتيمة
        لذرات لم تعد موجودة."""
        path = self._path_for(atom_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def has_snapshot(self, atom_id: int) -> bool:
        return self._path_for(atom_id).exists()

    def _write(self, atom_id: int, state: dict) -> None:
        """كتابة ذرّية: نُسلسل أولًا (فشل التسلسل لا يمسّ الملف القديم)،
        نكتب لملف مؤقت في نفس المجلد، ثم `os.replace` — عملية استبدال
        ذرّية على مستوى نظام الملفات. انقطاع الكهرباء وسط الكتابة يترك
        اللقطة السابقة سليمة بدل ملف JSON مبتور.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): ومعها ختم السلامة حقلًا أخيرًا
        (`INTEGRITY_FIELD`) = `sha256` بايتات النصّ القانونيّ نفسه. تسلسلٌ واحد كما
        كان، والختم على البايتات المكتوبة (يحرّر `hashlib` قفل المفسّر)."""
        if isinstance(state, dict) and INTEGRITY_FIELD in state:
            state = {key: value for key, value in state.items() if key != INTEGRITY_FIELD}
        data = json.dumps(state, ensure_ascii=False)
        body = data.encode("utf-8")
        target = self._path_for(atom_id)
        fd, tmp_name = tempfile.mkstemp(
            dir=self._storage_dir, prefix=f".{atom_id}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                if isinstance(state, dict):
                    digest = hashlib.sha256(body).hexdigest()
                    seal = ('"%s": "%s"}' % (INTEGRITY_FIELD, digest)).encode("ascii")
                    if state:
                        fh.write(memoryview(body)[:-1])
                        fh.write(b", " + seal)
                    else:
                        fh.write(b"{" + seal)
                else:
                    # حالةٌ ليست كائنًا (قائمة/عدد): تُكتب كما كانت بلا ختم.
                    fh.write(body)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def _read(self, atom_id: int) -> dict | None:
        """يقرأ اللقطة ويتحقّق من ختمها إن وُجد.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): JSON لا يُحلَّل (أو بايتات ليست UTF-8)،
        أو ختمٌ لا يطابق ⟵ عزلٌ ثمّ `None` (تُقلع الذرّة بلا حالة) — لا استثناء يُسقط
        إقلاعها. خطأ القرص (`OSError`) يبقى استثناءً كما كان: ليس فسادًا.
        لقطةٌ بلا ختم (قبل هذا الإصدار) تُقرأ كما كانت حرفًا."""
        path = self._path_for(atom_id)
        if not path.exists():
            return None
        raw = path.read_bytes()
        try:
            state = json.loads(raw.decode("utf-8"))
        except ValueError as exc:  # JSONDecodeError وUnicodeDecodeError كلاهما ValueError
            self._quarantine(atom_id, path, "JSON غير صالح: %s" % exc)
            return None
        if isinstance(state, dict) and INTEGRITY_FIELD in state:
            recorded = state.pop(INTEGRITY_FIELD)
            actual = self._payload_digest(raw)
            if actual is None or not isinstance(recorded, str) or actual != recorded:
                self._quarantine(
                    atom_id, path,
                    "ختم السلامة لا يطابق (المسجَّل %s · المحسوب %s)"
                    % (str(recorded)[:80], actual))
                return None
        return state

    @staticmethod
    def _payload_digest(raw: bytes) -> str | None:
        """`sha256` نصّ الحمولة القانونيّ كما كُتب — بلا إعادة تسلسل.

        الختم آخر حقل: `…, "<الحقل>": "<64 ست عشريّ>"}`؛ والنصّ الأصليّ ما قبله مع `}`.
        شكلٌ آخر (حقلٌ في غير موضعه) ⟵ `None` فيُعدّ فسادًا."""
        start = raw.rfind(_INTEGRITY_KEY_BYTES)
        if start < 0 or _INTEGRITY_TAIL.fullmatch(raw, start) is None:
            return None
        head = memoryview(raw)[:start]
        digest = hashlib.sha256()
        if bytes(head[-2:]) == b", ":
            digest.update(head[:-2])
            digest.update(b"}")
        elif bytes(head).strip() == b"{":
            digest.update(b"{}")
        else:
            return None
        return digest.hexdigest()

    def _quarantine(self, atom_id: int, path: Path, reason: str) -> None:
        """يعزل لقطةً تالفة إلى `<id>.json.corrupt-<وقت>` — نقلٌ لا حذف، ويُعلن بصوتٍ عالٍ.

        الاسم الجديد لا يطابق `*.json` ولا `.*.tmp` فلا تستعيده ذرّةٌ ولا يكنسه أحد.
        فإن تعذّر النقل (ملفٌّ محجوز) تُنسخ نسخةٌ معزولة كي لا تمحوها اللقطة الدوريّة
        التالية بـ`os.replace`.

        ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq» — مراجعة الجلسة): ذرّات طريق المال (500–599 و601)
        **لا تُقلع بلا حالتها**: مزلاج القاطع 516 أو دفتر 518 أو إيقاف 552/555 يعود افتراضيًّا
        «مفتوحًا» — فتحٌ صامت. لها يبقى السلوك القديم: اللقطة تبقى مكانها، ويُرمى استثناءٌ فلا
        تُستعاد الذرّة، كما كان كلّ JSON تالف يفعل قبل هذا الإصدار. والعلم يُرفع في الحالتين."""
        if 500 <= int(atom_id) <= 599 or int(atom_id) == 601:
            self.integrity_failures[atom_id] = {
                "reason": reason, "quarantined_to": None, "fail_closed": True,
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            _log.error("⛔ لقطة الذرة %s تالفة — %s. ذرّة طريق مالٍ: لا تُقلع بلا حالتها، "
                       "واللقطة باقية مكانها لفحص المالك.", atom_id, reason)
            raise ValueError("لقطة ذرّة طريق المال %s تالفة — %s" % (atom_id, reason))
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = path.with_name(f"{path.name}.corrupt-{stamp}")
        serial = 1
        while target.exists():
            target = path.with_name(f"{path.name}.corrupt-{stamp}-{serial}")
            serial += 1
        moved: str | None = None
        try:
            path.rename(target)
            moved = str(target)
        except OSError as exc:
            try:
                shutil.copy2(path, target)
                moved = str(target)
                _log.error("تعذّر نقل لقطة الذرة %s التالفة (%s) — حُفظت نسخةٌ معزولة %s",
                           atom_id, exc, target.name)
            except OSError as copy_exc:
                _log.error("تعذّر عزل لقطة الذرة %s التالفة نقلًا ولا نسخًا: %s · %s",
                           atom_id, exc, copy_exc)
        self.integrity_failures[atom_id] = {
            "reason": reason, "quarantined_to": moved,
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _log.error(
            "⛔ لقطة الذرة %s تالفة — %s. عُزلت إلى %s، والذرّة تُقلع **بلا حالتها**: "
            "كلّ ما كانت تحفظه (مزاليج، حدود، نوافذ) عاد إلى الافتراضيّ.",
            atom_id, reason, moved or "؟ (بقيت مكانها)")

    def integrity_report(self) -> dict[str, Any]:
        """علم السلامة للصحّة والمحرّك: من رُفضت لقطته ولماذا وأين عُزلت."""
        return {
            "failed": len(self.integrity_failures),
            "atoms": {str(atom_id): dict(info)
                      for atom_id, info in sorted(self.integrity_failures.items())},
        }

    def _path_for(self, atom_id: int) -> Path:
        return self._storage_dir / f"{atom_id}.json"
