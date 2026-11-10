import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[4]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.contracts.atom import AtomContext, HealthState  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_atom301", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom301"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT


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

    def make_context(self, config):
        return AtomContext(atom_id=301, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _tick(price, symbol="NQ100", timeframe="tick", sequence=0):
    return {"symbol": symbol, "price": price, "volume": 1, "timeframe": "tick",
            "timestamp": sequence}


async def _run(closes, cfg=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg or {"window_size": 20}))
    await atom.start()
    for i, c in enumerate(closes):
        await atom._on_tick(_tick(c, sequence=i))
    out = [p for n, p in bus.published if n == EVENT_OUT]
    return atom, bus, out


async def test_mean_computed():
    print("\n--- test_mean_computed ---")
    _atom, _bus, out = await _run([10, 20, 30])
    last = out[-1]
    assert last["status"] == "ok"
    assert last["metadata"]["value"] == 20, last["metadata"]["value"]
    print(f"OK — متوسط [10,20,30] = {last['metadata']['value']}")


async def test_rolling_window():
    print("\n--- test_rolling_window ---")
    _atom, _bus, out = await _run([10, 20, 30, 40], cfg={"window_size": 3})
    last = out[-1]
    assert last["metadata"]["value"] == 30, last["metadata"]["value"]  # mean of [20,30,40]
    assert last["metadata"]["count"] == 3
    print(f"OK — نافذة متدحرجة(3): متوسط آخر 3 = {last['metadata']['value']}")


async def test_contract_shape_complete():
    print("\n--- test_contract_shape_complete ---")
    _atom, _bus, out = await _run([10, 20, 30])
    last = out[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم ممنوعة.
    for field in ("symbol", "id", "cycle_id", "status", "signal", "warnings", "metadata",
                  "data_completeness", "as_of", "computed_on", "section_id", "atom_id",
                  "contract"):
        assert field in last, f"حقل ناقص بالعقد: {field}"
    for judged in ("score", "confidence", "quality", "weight", "current_depth",
                   "required_depth", "analysis_state", "ready", "direction"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    for field in ("method", "timeframe", "window", "count", "value"):
        assert field in last["metadata"], f"حقل metadata ناقص: {field}"
    assert last["id"] == "mean"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "300" and last["atom_id"] == "301"
    assert last["computed_on"] == last["metadata"]["count"]
    print("OK — عقد الحقائق كامل الحقول")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context({"window_size": 20}))
    h0 = await atom.health_check()
    assert h0.state == HealthState.UNHEALTHY
    await atom.start()
    h1 = await atom.health_check()
    assert h1.state == HealthState.DEGRADED
    await atom._on_tick(_tick(10))
    h2 = await atom.health_check()
    assert h2.state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


async def test_depth_diverges_from_completeness_when_unstable():
    # §١١ — نافذة ممتلئة بالكامل (data_completeness=100) لكن نصفَيها متباعدان
    # جدًّا (10,10 مقابل 90,90) ⇒ المتوسط لم يستقرّ بعد ⇒ current_depth ناضج
    # منخفض رغم اكتمال البيانات — هذا هو الفصل المطلوب (مثال المالك: 100/35).
    print("\n--- test_depth_diverges_from_completeness_when_unstable ---")
    _atom, _bus, out = await _run([10, 10, 90, 90], cfg={"window_size": 4})
    last = out[-1]
    assert last["data_completeness"] == 100.0, last["data_completeness"]
    # ٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): منذ 1.4.0 (التزام 6d72a6e، ٢٠٢٦-٠٩-١٩) نُقل نضج التحليل من
    # `current_depth` إلى `metadata.analysis_maturity` — ورق/التحليل/قياسات/«٢٠٢٦-٠٩-١٩ قسم 300 — لا حافّة
    # إحصائيّة».md:87 («العمق عاد امتلاءَ نافذة … والنضج نُقل إلى metadata.analysis_maturity»)، لأنّ
    # `required_depth=100` امتلاءُ نافذة فكان العمق 82 و69.5 و`NOT_READY` أبدًا. الفصل نفسه يُفحص في خانته.
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): العمق نُزع؛ الحقيقتان الباقيتان امتلاء النافذة ونضج التحليل.
    for judged in ("current_depth", "required_depth"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    assert last["metadata"]["count"] == last["metadata"]["window"] == 4, last["metadata"]
    maturity = last["metadata"]["analysis_maturity"]
    assert maturity < last["data_completeness"], (maturity, last["data_completeness"])
    print(f"OK — data_completeness=100 لكن analysis_maturity={maturity} < 100 (تذبذب بين النصفين)")


async def test_depth_matches_completeness_when_stable():
    # §١١ — نافذة ممتلئة ومتماسكة (نصفاها متقاربان) ⇒ current_depth قريب
    # جدًّا من data_completeness=100 (تحليل ناضج فعلًا لا مجرد امتلاء).
    print("\n--- test_depth_matches_completeness_when_stable ---")
    _atom, _bus, out = await _run([100, 101, 100, 101], cfg={"window_size": 4})
    last = out[-1]
    assert last["data_completeness"] == 100.0, last["data_completeness"]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): العمق نُزع؛ الاستقرار يُقاس من نضج التحليل في metadata وحده.
    assert "current_depth" not in last, last.get("current_depth")
    # ٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): النضج في `metadata.analysis_maturity` منذ 1.4.0 (التزام 6d72a6e).
    assert last["metadata"]["analysis_maturity"] >= 99.0, last["metadata"]
    print(f"OK — data_completeness=100 وanalysis_maturity={last['metadata']['analysis_maturity']} "
          f"قريب منها (استقرار)")


async def test_depth_equals_completeness_before_window_full():
    # §١١ — قبل امتلاء النافذة لا سلوك جديد: current_depth يبقى = data_completeness
    # كما كان قبل هذا التعديل (لا بيانات كافية بعد للحكم على الاستقرار).
    print("\n--- test_depth_equals_completeness_before_window_full ---")
    _atom, _bus, out = await _run([10, 90], cfg={"window_size": 4})
    last = out[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): العمق نُزع؛ الحقيقة الباقية امتلاء النافذة = العدد ÷ النافذة.
    assert "current_depth" not in last, last.get("current_depth")
    md = last["metadata"]
    assert last["data_completeness"] == md["count"] / md["window"] * 100.0 == 50.0, (
        last["data_completeness"], md)
    # ٢٠٢٦-١٠-٠١ (ختم المالك «Nq»): ولا نضج يُعلَن قبل امتلاء النافذة (1.4.0، التزام 6d72a6e).
    assert "analysis_maturity" not in last["metadata"], last["metadata"]
    print(f"OK — نافذة غير ممتلئة ⇒ data_completeness={last['data_completeness']} بلا نضج")


# ── فحوص الطفرات (٢٠٢٦-٠٩-١٦) ────────────────────────────────────────────
# أضيفت بعد أن أثبت تعطيبُ الكود عمدًا أنّ أربعة حرّاس لم يكن يمسكها شيء:
# حارس التشغيل، ورفض الحمولة الناقصة، وحمل `sequence` في معرّف الدورة،
# وحدّ القسمة. سياقها مستقلّ عمّا فوق كي لا يتغيّر معناها بتغيّر مساعدٍ آخر.
def _mut_cfg():
    raw = (_Path(__file__).resolve().parents[1] / "manifest.yaml").read_text(encoding="utf-8")
    cfg, blk = {}, raw.split("\nconfig:")
    if len(blk) > 1:
        for line in blk[-1].splitlines():
            s = line.strip()
            if ":" in s and not s.startswith("#") and not s.startswith("-"):
                k, v = s.split(":", 1)
                v = v.strip().strip('"')
                try:
                    cfg[k.strip()] = int(v)
                except ValueError:
                    try:
                        cfg[k.strip()] = float(v)
                    except ValueError:
                        cfg[k.strip()] = v
    return cfg


class _MutLog:
    def __getattr__(self, name):
        return lambda *a, **k: None


async def _mut_new(start=True):
    published = []

    async def _publish(name, payload):
        published.append((name, payload))

    atom = Atom()
    await atom.initialize(AtomContext(atom_id=0, config=_mut_cfg(), logger=_MutLog(),
                                      publish=_publish, subscribe=lambda n, h: None))
    if start:
        await atom.start()
    return atom, published


def _mut_tick(seq=4242, price=1.2345, **over):
    num = price if isinstance(price, (int, float)) and not isinstance(price, bool) else None
    tick = {"symbol": "EURUSD", "account_id": "A", "broker": "BR", "provider": "CTRADER",
            "bid": num - 0.0001 if num is not None else None,
            "ask": num + 0.0001 if num is not None else None,
            "price": price, "volume": 1.0, "timestamp": 1788960000.0,
            "exchange_timestamp": 1788960000.0, "received_at": 1788960000.1,
            "sequence": seq}
    tick.update(over)
    return tick


async def test_mut_stopped_atom_publishes_nothing():
    print("\n--- test_mut_stopped_atom_publishes_nothing ---")
    atom, published = await _mut_new(start=False)
    await atom._on_tick(_mut_tick())
    assert not published, "ذرّة لم تُشغَّل نشرت — حارس التشغيل بلا حارس"
    print("OK — الموقوفة صامتة")


async def test_mut_incomplete_payload_rejected():
    print("\n--- test_mut_incomplete_payload_rejected ---")
    atom, published = await _mut_new()
    await atom._on_tick(_mut_tick(symbol=""))
    assert not published, "حمولة بلا رمز عُولجت"
    await atom._on_tick(_mut_tick(price=None))
    assert not published, "حمولة بلا سعر عُولجت"
    await atom._on_tick(_mut_tick(price="نصّ"))
    assert not published, "سعر غير رقميّ عُولج"
    print("OK — الناقصة تُرفض بثلاث صور")


async def test_mut_cycle_id_carries_sequence():
    print("\n--- test_mut_cycle_id_carries_sequence ---")
    atom, published = await _mut_new()
    await atom._on_tick(_mut_tick(seq=987654))
    assert published, "لم يُنشر شيء من تِكّة سليمة"
    cid = str(published[-1][1].get("cycle_id") or "")
    assert cid.endswith("|987654"), "التسلسل سقط من معرّف الدورة: %s" % cid
    atom2, pub2 = await _mut_new()
    await atom2._on_tick(_mut_tick(seq=111))
    cid2 = str(pub2[-1][1].get("cycle_id") or "")
    assert cid2 != cid, "تِكّتان مختلفتان بمعرّف واحد"
    print("OK — المعرّف يحمل التسلسل ويتبدّل بتبدّله")


def _mut_min_points():
    """الحدّ الأدنى المعلَن في الذرّة — يُقرأ من نصّها لا من اسم وحدةٍ يتبدّل."""
    import re as _re
    src = (_Path(__file__).resolve().parents[1] / "atom.py").read_text(encoding="utf-8")
    m = _re.search(r"^_MIN_(?:POINTS|OVERLAP)\s*=\s*(\d+)", src, _re.M)
    return int(m.group(1)) if m else None


async def test_mut_min_points_boundary_is_sharp():
    """الحدّ يُختبر **عنده** لا في وسطه (حكم ٢٠٢٦-٠٩-١٦).

    نقطةٌ واحدة دون الحدّ يجب أن تعطي حكمًا مختلفًا عن الحكم عنده؛ وإلّا
    فإزاحةُ الحدّ نقطةً واحدة (`<` ⇢ `<=`) تمرّ بلا أن يسقط فحصٌ واحد.
    """
    print("\n--- test_mut_min_points_boundary_is_sharp ---")
    need = _mut_min_points()
    if need is None:
        print("OK — لا حدّ نقاط معلَن في هذه الذرّة")
        return
    atom, published = await _mut_new()
    marks = []
    for i in range(need + 2):
        await atom._on_tick(_mut_tick(seq=8000 + i, price=1.2 + i * 0.017))
        payload = published[-1][1] if published else {}
        marks.append((payload.get("status"), payload.get("signal"),
                      tuple(payload.get("warnings") or ())))
    assert len(marks) >= need, "لم تُنشر نقاط كافية لقياس الحدّ"
    below, at = marks[need - 2], marks[need - 1]
    assert below != at, (
        "الحكم عند الحدّ (%d) لا يختلف عمّا دونه بنقطة — الحدّ غير مُختبَر عنده" % need)
    print("OK — الحكم يتبدّل عند النقطة %d بالضبط" % need)


async def test_mut_flat_window_depth_is_full():
    """نافذة بقيم متطابقة: المدى صفرٌ بالضبط — والحدّ يُختبر عنده.

    الحارس `value_range <= 0` لو صار `< 0` لمرّ الصفرُ إلى القسمة فانهارت
    الذرّة؛ ولو حُذف الفرع لقُرئ عمقُ سوقٍ ساكنة خطأً.
    """
    print("\n--- test_mut_flat_window_depth_is_full ---")
    atom, published = await _mut_new()
    size = int(_mut_cfg().get("window_size") or 20)
    for i in range(size + 2):
        await atom._on_tick(_mut_tick(seq=7700 + i, price=1.5))
    payload = published[-1][1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): العمق نُزع؛ حارس المدى الصفريّ يُقاس في نضج التحليل بـmetadata.
    assert "current_depth" not in payload, payload.get("current_depth")
    maturity = payload.get("metadata", {}).get("analysis_maturity")
    assert maturity == 100.0, "نافذة مسطّحة لم تُقرأ نضجًا كاملًا: %r" % maturity
    assert payload.get("data_completeness") == 100.0, "النافذة لم تمتلئ أصلًا"
    print("OK — المدى صفر ⇒ نضج كامل بلا قسمة على صفر")

async def test_mut_threshold_actually_discriminates():
    """ذرّةٌ لها عتبةُ تصنيف يجب أن تُخرج **أكثر من حكم** عبر أنماط مختلفة.

    الدرس من ٣٠٧: ظلّت تقول `insufficient_data` لكلّ تِكّة منذ اعتماد
    المعرّف الموحّد ولم يسقط بذلك فحصٌ واحد. عتبةٌ لا تُصنّف شيئًا ذرّةٌ
    ميتةٌ بشارةٍ خضراء — وهذا الفحص يمنع تكرارها في القسم كلّه.
    """
    print("\n--- test_mut_threshold_actually_discriminates ---")
    cfg = _mut_cfg()
    dials = [k for k in cfg
             if k.endswith(("threshold", "ratio", "band", "multiplier", "quality"))]
    if not dials:
        print("OK — لا عتبة تصنيف معلَنة في هذه الذرّة")
        return
    size = int(cfg.get("window_size") or 20)
    patterns = (
        ("صاعد", lambda i: 1.0 + i * 0.05),
        ("هابط", lambda i: 3.0 - i * 0.05),
        ("مسطّح", lambda i: 1.5),
        ("متذبذب", lambda i: 1.5 + (0.3 if i % 2 else -0.3)),
        ("قافز", lambda i: 1.5 if i < size else 9.0),
    )
    seen = {}
    for n, (label, fn) in enumerate(patterns):
        atom, published = await _mut_new()
        for i in range(size + 2):
            await atom._on_tick(_mut_tick(seq=20000 + n * 200 + i, price=fn(i)))
        seen[label] = published[-1][1].get("signal") if published else None
    distinct = {v for v in seen.values() if v is not None}
    assert len(distinct) > 1, \
        "عتبةٌ معلَنة (%s) ولا تُصنّف: حكمٌ واحد لكلّ نمط ⇒ %s" % (dials, seen)
    print("OK — العتبة تُصنّف فعلًا: %s" % sorted(distinct))


async def main():
    tests = [test_mean_computed, test_rolling_window,
             test_contract_shape_complete, test_health_states,
             test_depth_diverges_from_completeness_when_unstable,
             test_depth_matches_completeness_when_stable,
             test_depth_equals_completeness_before_window_full,
             test_mut_stopped_atom_publishes_nothing,
             test_mut_incomplete_payload_rejected,
             test_mut_min_points_boundary_is_sharp,
             test_mut_flat_window_depth_is_full,
             test_mut_threshold_actually_discriminates,
             test_mut_cycle_id_carries_sequence]
    failed = []
    for t in tests:
        try:
            await t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAILED: {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, repr(e)))
            print(f"ERROR: {t.__name__}: {e!r}")
    print("\n" + "=" * 60)
    if failed:
        print(f"فشل {len(failed)} من أصل {len(tests)}")
        sys.exit(1)
    print(f"نجح كل الاختبارات ({len(tests)}/{len(tests)})")


if __name__ == "__main__":
    asyncio.run(main())
