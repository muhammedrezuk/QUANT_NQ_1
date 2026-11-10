# -*- coding: utf-8 -*-
"""§5 / Gate D — الأداء والسعة (ختم `NQ — OPEN GATE D`).

## السؤال المطروح — بلا ثابتٍ مفترَض

محرّك Gate C يُجمّع الصفوف ولا ينفّذ الذرّات المئةَ واثنتين وستّين. فقياسُه
وحده يقيس السقالة. ولو افترضتُ كلفةَ تِكّةٍ من ذاكرتي لبنيتُ الحكم على رقمٍ
لم يُقَس اليوم. فالسؤال يُقلَب:

    عند `N` عاملًا و`R` تِكّة/ث ⟶ **كم من العمل لكلّ تِكّة يُحتمَل بصفر فقد؟**

هذا يُقاس بلا افتراض. ولحظةَ تُقاس كلفةُ الذرّات يُقرأ الجواب منه مباشرةً
بدل أن يُعاد القياس كلُّه.

## البناء

    الشريط المجمَّد (البصمة نفسها)
          ↓ توجيهٌ بالملكيّة — مرّةً قبل التوقيت
    نصيبُ كلّ عاملٍ مرتَّبًا بأرقامه العالميّة
          ↓ ضخٌّ **بالجدول** لا بأقصى سرعة
    إطاراتٌ ثنائيّة (نفسُ إطار Gate A) ⟶ أنبوب
          ↓
    عمليّةٌ مستقلّةٌ لكلّ عامل — `_is_gil_enabled() == True` فالخيطُ سراب

## ما لا يدخل التوقيت الساخن (§٧ من ورقة المالك)

التخزينُ واللوحةُ والقياسُ والسجلّ خارج المسار. ولا يُشغَّل هنا منها شيء.

    python tools/gate_d.py run --workers 6 --rate 120 --cost-ms 4 --seconds 20
    python tools/gate_d.py sweep --rate 120 --seconds 12
    python tools/gate_d.py headroom --rate 120 --seconds 12
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hot import frame, parity, planner, shard  # noqa: E402
from tools.gate_b import read_single_run  # noqa: E402
from transport.ownership import OwnershipRegistry, ownership_key  # noqa: E402

TAPE = (ROOT / "forex_runtime" / "var" / "parity" / "frozen"
        / "tape-20260918-154724.jsonl")
SCRATCH = ROOT / "forex_runtime" / "var" / "parity" / "gate_d"
#: الإطار الواحد = شريحةُ تِكّةٍ واحدةٍ لعاملٍ واحد. لا تجميعَ عبر الشرائح.
#:
#: ⛔ والتجميعُ بالعدد **صنع التأخّر الذي كنتُ أقيسه**: عاملان عند ٣٠
#: تِكّة/ث يعني ٥٩ واقعة/ث لكلٍّ، فامتلاءُ ٣٢ يستغرق ٠٫٥٤ ث — فقِيس
#: `p50 = 403 م.ث` والمعالج عند ٠٫٢٪. أي أنّ المقياس كان يقيس حاملَه.
#: ثمّ أُضيف حدٌّ زمنيّ فبقي `p50 = 1/rate` بالضبط، لأنّ الفحص يقع بعد
#: الإلحاق وحده والحلقةُ تنام بعده. والعلاج النهائيّ أن تُبعَث الشريحة
#: كاملةً عند موعدها: لا صندوقَ يُمسَك أصلًا.

#: ما يُدار دورانًا في آخر المهلة. و`sleep` على ويندوز يتجاوز موعدَه ولو
#: بدقّة مِلّي ثانية، فيُترَك هامشٌ يُدار — والباقي نومٌ لا يسرق نواة.
SPIN_S = 0.002
#: تشغيلُ الذرّات الحقيقيّة داخل كلّ عامل — ختم `NQ — RERUN GATE D UNDER FREEZE`.
REAL_ATOMS = False


# ── تهيئةٌ تُسجَّل مع الرقم، لا تُدَّعى ─────────────────────────────────

def provenance() -> dict[str, Any]:
    """يربط القياس بنسخةٍ بعينها — رقمٌ بلا نسخةٍ رقمٌ بلا معنى.

    ⚠️ وأمرُ المالك: قيمةُ إعدادٍ في شجرة العمل **ليست حقيقةً عن الفرع
    المنشور**. فتُسجَّل بصمةُ الملفّ وحالتُه في git، ويُقال إن كان معدَّلًا
    غير ملتزَم — ولا يُبنى حكمُ أداءٍ على قيمةٍ لم تُربَط بنسخة التشغيل.
    """
    def run(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=str(ROOT),
                                  capture_output=True, text=True,
                                  timeout=20).stdout.strip()
        except Exception:                                      # noqa: BLE001
            return "?"

    config = ROOT / "config" / "core_forex.yaml"
    digest = "?"
    if config.exists():
        digest = hashlib.sha256(config.read_bytes()).hexdigest()[:16]
    dirty = [line for line in run("status", "--short").splitlines() if line]
    return {
        "head": run("rev-parse", "--short", "HEAD"),
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "config_sha256_16": digest,
        "config_uncommitted": any("core_forex.yaml" in line for line in dirty),
        "worktree_dirty": dirty,
        "python": sys.version.split()[0],
        "gil_enabled": getattr(sys, "_is_gil_enabled", lambda: True)(),
    }


# ── المدخل: يُوجَّه مرّةً واحدةً قبل التوقيت ────────────────────────────

def routed_stream(workers: int) -> tuple[list[list[tuple[int, str, dict]]], dict]:
    """يقرأ الشريط ويوزّعه على العمّال بالملكيّة، **مقطَّعًا بالتِكّات**.

    التوجيه جزءٌ من المسار لكنّه يقع عند المُغذّي لا عند العامل، فيُنجَز
    **خارج النافذة المُقاسة**: إبقاؤه داخل حلقة الضخّ يجعل المُغذّي هو
    المقياس بدل المحرّك.

    والتقطيعُ بالتِكّة مقصود: التِكّة هي المدخل، وما بعدها حتّى التِكّة
    التالية أحداثُ دورتها. فيضخّ المُغذّي شريحةً كاملةً عند موعدها بدل
    أن يستيقظ لكلّ واقعة.

    ⛔ وهذا ما أصلح العطب: الضخُّ واقعةً واقعة كان يوقظ المُغذّي ٤٧٠ مرّةً
       في الثانية، فيتراكم انحراف `sleep` حتّى بلغ تأخّرُه ١٤٫٩ م.ث
       (‏١٠٨ مرّة خلف الجدول) — وظهر ذلك `p99 = 10.9 م.ث` للمحرّك وهو
       تأخّرُ الحامل. ومعه كان الدوران يلتهم ٤١٪ من نواة.
    """
    rows = read_single_run(TAPE)
    registry = OwnershipRegistry(workers)
    slots: list[list[tuple[int, str, dict]]] = []
    no_owner = 0
    for _index, name, payload in rows:
        key = ownership_key(payload)
        if key is None:
            no_owner += 1
            continue
        if name == parity.TICK_EVENT or not slots:
            slots.append([])
        slots[-1].append((registry.owner_for(key), name, payload))
    # ── نصيبُ المالك الأثقل من التِكّات ─────────────────────────────────
    #
    # ⛔ هو مقامُ الحكم لا `1/rate`: الدورة لا يلزمها أن تنتهي قبل التِكّة
    #    التالية **عالميًّا**، بل قبل التِكّة التالية **لمالكها**. وهذا ما
    #    ختمه المالك رقمًا: 24.52 · 19.62 · 12.26 م.ث عند 120 · 150 · 240.
    per_owner: dict[str, int] = {}
    for slot in slots:
        for _worker, name, payload in slot:
            if name == parity.TICK_EVENT:
                key = ownership_key(payload)
                if key is not None:
                    per_owner[key.text] = per_owner.get(key.text, 0) + 1
    total = sum(per_owner.values()) or 1
    heaviest = max(per_owner.items(), key=lambda kv: kv[1], default=("?", 0))
    return slots, {
        "records": len(rows), "ticks": len(slots), "no_owner": no_owner,
        "records_per_tick": len(rows) / max(len(slots), 1),
        "owners": len(per_owner),
        "heaviest_owner": heaviest[0],
        "heaviest_share": heaviest[1] / total,
    }


def _fine_timer(enable: bool) -> None:
    """يرفع دقّة مؤقّت ويندوز إلى مِلّي ثانية — وإلّا فالجدول يكذب.

    ⛔ `time.sleep` على ويندوز يُقرَّب إلى حبيبة المُجدوِل (‏١٥٫٦ م.ث
    افتراضًا). فنومُ ٦٫٥ م.ث ينام ١٥ — وتظهر تلك الزيادة **تأخّرَ محرّكٍ**
    وهي تأخّرُ مؤقّت. والاستدعاء محلّيٌّ للعمليّة ويُعاد ضبطه عند الانتهاء.
    """
    try:
        import ctypes
        winmm = ctypes.WinDLL("winmm")
        (winmm.timeBeginPeriod if enable else winmm.timeEndPeriod)(1)
    except Exception:                                          # noqa: BLE001
        pass


def run_point(*, workers: int, rate: float, cost_ms: float, seconds: float,
              shards: list, shape: dict, label: str) -> dict[str, Any]:
    """نقطةُ قياسٍ واحدة: يضخّ بالجدول لمدّةٍ ثابتة ويجمع ما قاسه العمّال."""
    # ── الجدول بالتِكّة لا بالواقعة ──────────────────────────────────────
    #
    # ⛔ أوّل صيغةٍ جدولت بالواقعة: `due = t0 + i/records_per_s`. والنسبة
    #    ٣٫٩٢ واقعة/تِكّة **متوسّطٌ على الشريط كلّه**، ومزيجُ أوّله يخالفه.
    #    فقِيس خرجٌ ٣٤٫٣ تِك/ث عند هدف ٣٠ — رقمٌ مجاملٌ لا عطبَ فيه إلّا أنّه
    #    ليس ما طُلب. والتِكّة هي المدخل الحقيقيّ، وما بعدها من حدث دورتها.
    #
    #    فصار موعدُ التِكّة `t0 + k/rate`، وأحداثُ دورتها تَرِث موعدَها.
    # نافذةُ المالك الأثقل — الحدُّ الذي ختمه المالك، لا `1/rate`.
    deadline_s = 1.0 / (rate * shape["heaviest_share"])
    budget_ticks = int(rate * seconds)

    out_dir = SCRATCH / label
    result_q: Any = mp.Queue()
    pipes, procs = [], []
    for index in range(workers):
        receiver, sender = mp.Pipe(duplex=False)
        proc = mp.Process(
            target=shard.run_shard, args=(receiver, result_q),
            kwargs=dict(index=index, workers=workers,
                        out_path=str(out_dir / ("w%d" % index)),
                        tick_rate=rate,
                        tick_cost_ns=int(cost_ms * 1e6),
                        deadline_s=deadline_s, real_atoms=REAL_ATOMS),
            daemon=True)
        proc.start()
        receiver.close()
        pipes.append(sender)
        procs.append(proc)

    # ── لا يبدأ الجدول حتّى يُقلع آخرُ عامل ─────────────────────────────
    import struct
    for _ in range(workers):
        message = result_q.get()
        if "ready" not in message:
            raise SystemExit("⛔ رسالةٌ غير متوقَّعة قبل الجاهزيّة")
    boot_done = time.time()
    t0 = boot_done + 0.05
    for sender in pipes:
        sender.send_bytes(struct.pack("<d", t0))

    # ── الضخّ بالجدول ────────────────────────────────────────────────────
    sent = 0
    overrun_s = 0.0
    behind = 0
    _fine_timer(True)
    feeder_cpu0 = time.process_time()
    feeder_wall0 = time.perf_counter()
    for slot in range(budget_ticks):
        due = t0 + slot / rate
        now = time.time()
        if now < due:
            gap = due - now
            if gap > SPIN_S:
                time.sleep(gap - SPIN_S)
            while time.time() < due:      # الميلّيان الأخيران دورانًا
                pass
        else:
            lag = now - due
            if lag > overrun_s:
                overrun_s = lag
            if lag > deadline_s:
                behind += 1
        # شريحةٌ كاملةٌ تُبعَث عند موعدها: تِكّةٌ وأحداثُ دورتها. والفهرس
        # على السلك هو **ترتيب التِكّة**، فيحسب العامل موعدَه منه بلا
        # رسالةٍ إضافيّة: `due = t0 + slot / rate`.
        buffers: list[list] = [[] for _ in range(workers)]
        for owner, name, payload in shards[slot % len(shards)]:
            buffers[owner].append((slot, name, payload))
            sent += 1
        for w in range(workers):
            if buffers[w]:
                pipes[w].send_bytes(frame.encode(buffers[w]))
    feeder_cpu = time.process_time() - feeder_cpu0
    feeder_wall = time.perf_counter() - feeder_wall0
    _fine_timer(False)
    # ⛔ كان هنا تصريفٌ ثانٍ لـ`buffers` — وهي الآن محلّيّةٌ داخل الحلقة
    #    وقد أُرسلت فعلًا، فكانت الشريحة الأخيرة تُبعَث مرّتين ويظهر
    #    «فقدٌ سالب» (‏المعالَج أكثر من المُرسَل). الخاتمةُ وحدها تبقى.
    for w in range(workers):
        pipes[w].send_bytes(b"")

    results = [result_q.get() for _ in range(workers)]
    for proc in procs:
        proc.join(timeout=60)
    results.sort(key=lambda r: r["worker"])

    processed = sum(r["records"] for r in results)
    ticks = sum(r["ticks"] for r in results)
    cpu = sum(r["cpu_s"] for r in results)
    # ⛔ الخرج يُقسَم على **نافذة الضخّ المقيسة** لا على المدّة بين أوّل
    #    تِكّةٍ وآخرها: تلك أقصرُ من النافذة فتُظهر خرجًا أعلى من المطلوب
    #    (٤٤٫٥ تِك/ث عند هدف ٣٠ في أوّل تشغيل) — وهو رقمٌ مجامل.
    return {
        "label": label, "workers": workers, "rate": rate,
        "cost_ms": cost_ms, "seconds": seconds,
        "deadline_ms": deadline_s * 1000.0,
        "sent": sent, "processed": processed,
        "input_loss": sent - processed,
        "ticks": ticks,
        "feeder_wall_s": feeder_wall,
        "throughput_tick_s": ticks / feeder_wall if feeder_wall > 0 else 0.0,
        "cpu_total_s": cpu, "feeder_cpu_s": feeder_cpu,
        "cpu_per_worker_s": [round(r["cpu_s"], 3) for r in results],
        "cpu_busy_pct": 100.0 * cpu / (seconds * workers) if seconds else 0.0,
        "p50_ms": max(r["p50"] for r in results) * 1000.0,
        "p95_ms": max(r["p95"] for r in results) * 1000.0,
        "p99_ms": max(r["p99"] for r in results) * 1000.0,
        # كلفةُ المحرّك وحدها: من وصول الإطار إلى اكتمال المعالجة
        "svc_p50_ms": max(r["svc_p50"] for r in results) * 1000.0,
        "svc_p95_ms": max(r["svc_p95"] for r in results) * 1000.0,
        "svc_p99_ms": max(r["svc_p99"] for r in results) * 1000.0,
        "svc_max_ms": max(r["svc_max"] for r in results) * 1000.0,
        "max_lag_ms": max(r["max_lag"] for r in results) * 1000.0,
        "oldest_pending_ms": max(r["oldest_pending"] for r in results) * 1000.0,
        "deadline_misses": sum(r["deadline_misses"] for r in results),
        "schedule_misses": sum(r["schedule_misses"] for r in results),
        "max_batch_depth": max(r["max_batch_depth"] for r in results),
        "atoms_booted": max(r["atoms_booted"] for r in results),
        "atom_p50_ms": max(r["atom_p50"] for r in results),
        "atom_p95_ms": max(r["atom_p95"] for r in results),
        "atom_p99_ms": max(r["atom_p99"] for r in results),
        "atom_max_ms": max(r["atom_max"] for r in results),
        "gc_frozen": max(r["gc_frozen"] for r in results),
        "lag_drift_ms": max(r["lag_drift_ms"] for r in results),
        "busy_fraction": max(r["busy_fraction"] for r in results),
        "frames_with_backlog": sum(r["frames_with_backlog"] for r in results),
        "frames": sum(r["frames"] for r in results),
        "feeder_overrun_ms": overrun_s * 1000.0,
        "feeder_behind": behind,
        "owner_violations": sum(r["owner_violations"] for r in results),
        "dropped_no_owner": sum(r["dropped_no_owner"] for r in results),
        "ns_per_spin": round(max(r["ns_per_spin"] for r in results), 3),
        "per_worker": results,
    }


def valid(point: dict) -> bool:
    """أبلغ الحاملُ المعدّلَ المطلوب أصلًا؟ — يُسأل **قبل** الحكم.

    ⛔ حاملٌ لا يضخّ بالمعدّل لا يشهد على محرّك. وانحرافُ `sleep` على
       ويندوز يبلغ مِلّي ثوانٍ، فإن تجاوز الموعدَ النهائيّ فالنقطة
       **قياسٌ غير صالح** لا رسوبُ محرّك.
    """
    return point["feeder_overrun_ms"] <= point["deadline_ms"]


def stable(point: dict) -> bool:
    """**لا تراكم**: صفرُ فقدٍ، وتأخّرٌ لا ينمو، وعاملٌ لم يُشبَع.

    وهذا حدُّ **السعة**: يقول إنّ الوارد لا يسبق الخدمة. ويرتفع بعدد
    العمّال، لأنّ أعمالَ مالكين مختلفين تجري معًا.
    """
    return (point["input_loss"] == 0
            and point["owner_violations"] == 0
            and point["dropped_no_owner"] == 0
            and point["lag_drift_ms"] <= point["deadline_ms"]
            and point["busy_fraction"] < 0.95)


def verdict(point: dict) -> bool:
    """السعةُ **وأن تكتمل كلُّ دورةٍ داخل زمن تِكّة**.

    ⚠️ والحدّان مختلفان ولا يُخلَطان — وقد خلطتُهما فقِيس أنّ ٤ عمّالٍ
    يحتملون أقلَّ من عاملٍ واحد (٣٫٣٣ مقابل ٤٫١٧ م.ث) والمعالجُ عند ١١٪:

        حدُّ التأخّر    كم عملٍ يسع **داخل دورةٍ واحدة**؟
                        ⟵ تسلسليٌّ بطبعه، فلا يرفعه عاملٌ إضافيّ
        حدُّ السعة     كم دورةً في الثانية تُخدَم بلا تراكم؟
                        ⟵ يرتفع بعدد العمّال

    والتجاوزُ يُحسَب على ما يملكه العامل (وصولُ الإطار ⟶ الاكتمال) لا على
    الجدول: الجدول يحمل انحرافَ المُغذّي، والحكمُ به يُسقط البوّابة على
    حاملها — وهي الغلطة التي وقعت في Gate C ثمّ صُحِّحت.
    """
    return stable(point) and point["deadline_misses"] == 0


def line(point: dict) -> str:
    return ("%s %2dع · %5.1f تِك/ث │ خرج %6.1f · "
            "دورة p50 %5.2f p95 %6.2f p99 %6.2f أقصى %7.2f · "
            "ذرّات p99 %6.2f · معالج %5.1f٪ · طابور %d · أقدم %6.2f · "
            "فقد %d · تجاوز %d · انجراف %+5.2f · إشباع %.2f"
            % (("✅" if verdict(point) else ("◐" if stable(point) else "⛔"))
               if valid(point) else "⚠️",
               point["workers"], point["rate"],
               point["throughput_tick_s"], point["svc_p50_ms"],
               point["svc_p95_ms"], point["svc_p99_ms"], point["svc_max_ms"],
               point["atom_p99_ms"], point["cpu_busy_pct"],
               point["max_batch_depth"], point["oldest_pending_ms"],
               point["input_loss"], point["deadline_misses"],
               point["lag_drift_ms"], point["busy_fraction"]))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    mode = sys.argv[1]
    opts = {}
    for i, a in enumerate(sys.argv):
        if a.startswith("--") and i + 1 < len(sys.argv):
            opts[a[2:]] = sys.argv[i + 1]
    rate = float(opts.get("rate", 120))
    seconds = float(opts.get("seconds", 12))
    cost_ms = float(opts.get("cost-ms", 0))
    workers = int(opts.get("workers", 6))
    global REAL_ATOMS
    REAL_ATOMS = "--real" in sys.argv

    info = provenance()
    # ⛔ حارسُ البيئة (ختم المالك): الشجرةُ تتحرّك من جلسةٍ موازية، فكلُّ
    #    تشغيلٍ يحمل بصمتَه. وتشغيلان اختلفت فيهما هذه لا يُخلطان.
    info["plan_fingerprint"] = planner.compile_plan(
        known_external=planner.external_events()).summary()["fingerprint"]
    info["real_atoms"] = REAL_ATOMS
    info["gc_freeze_at_boot"] = True
    print("النسخة: %s @ %s · بايثون %s · GIL %s"
          % (info["head"], info["branch"], info["python"], info["gil_enabled"]))
    print("بصمة الإعداد: %s%s · بصمة الخطّة: %s"
          % (info["config_sha256_16"],
             "  ⚠️ معدَّلٌ غير ملتزَم" if info["config_uncommitted"] else "",
             info["plan_fingerprint"][:16]))
    print("ذرّاتٌ حقيقيّة: %s · تجميدٌ عند الإقلاع: نعم"
          % ("نعم" if REAL_ATOMS else "لا — حِملٌ مُعايَر"))
    if not TAPE.exists():
        raise SystemExit("⛔ لا شريطَ مجمَّد")

    if mode == "run":
        shards, shape = routed_stream(workers)
        print("الشريط: %d واقعة · %d تِكّة · %d مالك · الأثقل %s (%.1f٪) "
              "⟶ نافذته %.2f م.ث\n"
              % (shape["records"], shape["ticks"], shape["owners"],
                 shape["heaviest_owner"], 100 * shape["heaviest_share"],
                 1000.0 / (rate * shape["heaviest_share"])))
        point = run_point(workers=workers, rate=rate, cost_ms=cost_ms,
                          seconds=seconds, shards=shards, shape=shape,
                          label="run-w%d-r%d-c%s" % (workers, rate, cost_ms))
        print(line(point))
        (SCRATCH / "last.json").parent.mkdir(parents=True, exist_ok=True)
        (SCRATCH / "last.json").write_text(
            json.dumps(point, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if verdict(point) else 1

    if mode == "sweep":
        counts = [int(x) for x in opts.get("counts", "1,2,4,6,8,12,24").split(",")]
        print()
        results = []
        for n in counts:
            shards, shape = routed_stream(n)
            point = run_point(workers=n, rate=rate, cost_ms=cost_ms,
                              seconds=seconds, shards=shards, shape=shape,
                              label="sweep-w%d-r%d" % (n, rate))
            results.append(point)
            print(line(point))
        out = SCRATCH / ("sweep-r%d-c%s.json" % (rate, cost_ms))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"provenance": info, "points": results},
                                  ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print("\nكُتب: %s" % out.name)
        return 0

    if mode == "headroom":
        # ما أكبرُ كلفةِ تِكّةٍ يحتملها هذا العدد عند هذا المعدّل؟
        #
        # والسُّلَّم **نسبيٌّ لا مطلق**: السقف النظريّ لعاملٍ مستقلٍّ تمامًا
        # هو `N/rate`، فيُجرَّب حوله بكسورٍ منه. وسُلَّمٌ مطلقٌ واحدٌ لكلّ
        # الأعداد يضيّع عشراتِ التشغيلات على نطاقٍ لا يعني العدد المُختبَر.
        counts = [int(x) for x in opts.get("counts", "1,2,4,6,8,12").split(",")]
        ratios = [float(x) for x in opts.get(
            "ratios", "0.25,0.5,0.75,0.9,1.0,1.15").split(",")]
        absolute = ([float(x) for x in opts["costs"].split(",")]
                    if "costs" in opts else None)
        print()
        table = {}
        for n in counts:
            shards, shape = routed_stream(n)
            ceiling = 1000.0 * n / rate          # السقف النظريّ م.ث/تِكّة
            strict, capacity, last = 0.0, 0.0, None
            # سُلَّمٌ مطلقٌ إن طُلب: حدُّ التأخّر خاصّةُ **دورةٍ واحدة**،
            # فلا يُقاس بسُلَّمٍ يكبر بعدد العمّال — وإلّا لم يُجرَّب عند
            # الأعداد الكبيرة إلّا ما هو فوقه أصلًا (فخرج «صفر» لأربعة).
            ladder = absolute or [round(ceiling * r, 2) for r in ratios]
            for cost in ladder:
                point = run_point(workers=n, rate=rate, cost_ms=cost,
                                  seconds=seconds, shards=shards, shape=shape,
                                  label="head-w%d-r%d-c%s" % (n, rate, cost))
                print("   %s" % line(point))
                if not valid(point) or not stable(point):
                    break            # نفدت السعة — لا معنى لمتابعة السُّلَّم
                capacity, last = cost, point
                if verdict(point):
                    strict = cost
            table[n] = {
                "capacity_ms": capacity,        # بلا تراكم
                "latency_ms": strict,           # وبلا تجاوزِ زمنِ تِكّة
                "theoretical_ms": round(ceiling, 2),
                "capacity_pct": round(100.0 * capacity / ceiling, 1),
                "cpu_busy_pct": round(last["cpu_busy_pct"], 1) if last else 0.0,
            }
            print("   ⟶ %2d عامل: سعةً %.2f م.ث/تِكّة (%.0f٪ من %.2f نظريّة) · "
                  "وبحدّ تأخّرٍ %.2f · المعالج %.0f٪\n"
                  % (n, capacity, table[n]["capacity_pct"], ceiling, strict,
                     table[n]["cpu_busy_pct"]))
        out = SCRATCH / ("headroom-r%d.json" % rate)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"provenance": info, "rate": rate,
                                   "headroom_ms": table},
                                  ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print("كُتب: %s" % out.name)
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
