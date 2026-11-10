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
    "_atom316", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom316"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT

CFG = {"window_size": 20, "min_quality": 0.95}


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
        return AtomContext(atom_id=316, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _tick(price, sequence, symbol="NQ100", timeframe="tick"):
    return {"symbol": symbol, "price": price, "volume": 1, "timeframe": "tick",
            "timestamp": sequence, "sequence": sequence}


async def _run(ticks, cfg=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg or dict(CFG)))
    await atom.start()
    for tk in ticks:
        await atom._on_tick(tk)
    out = [p for n, p in bus.published if n == EVENT_OUT]
    return atom, bus, out


async def test_all_clean():
    print("\n--- test_all_clean ---")
    _atom, _bus, out = await _run([_tick(10 + i, float(i)) for i in range(6)])
    last = out[-1]
    assert last["signal"] == "clean", (last["signal"], last["metadata"])
    assert last["metadata"]["quality_ratio"] == 1.0
    print("OK — كله صالح: clean (ratio=1.0)")


async def test_degraded_mixed():
    print("\n--- test_degraded_mixed ---")
    good = [_tick(10 + i, float(i)) for i in range(7)]
    bad = [_tick(None, float(7 + i)) for i in range(3)]
    _atom, _bus, out = await _run(good + bad)
    last = out[-1]
    assert last["signal"] == "degraded", (last["signal"], last["metadata"])
    assert "data_quality_degraded" in last["warnings"]
    print(f"OK — خليط خبيث: degraded (ratio={last['metadata']['quality_ratio']})")


async def test_counts_rejects():
    print("\n--- test_counts_rejects ---")
    _atom, _bus, out = await _run([_tick(10, 0.0), _tick(None, 1.0), _tick(-5, 2.0)])
    last = out[-1]
    m = last["metadata"]
    assert m["nan"] == 1, m
    assert m["nonpositive"] == 1, m
    assert m["rejected"] == 2, m
    print(f"OK — عدّ الرفض: nan={m['nan']} nonpos={m['nonpositive']} rejected={m['rejected']}")


async def test_duplicates():
    print("\n--- test_duplicates ---")
    _atom, _bus, out = await _run([_tick(10, 5.0), _tick(11, 5.0), _tick(12, 5.0)])
    m = out[-1]["metadata"]
    assert m["duplicates"] >= 2, m
    print(f"OK — مكرّر: duplicates={m['duplicates']}")


async def test_out_of_order():
    print("\n--- test_out_of_order ---")
    _atom, _bus, out = await _run([_tick(10, 5.0), _tick(11, 3.0)])
    m = out[-1]["metadata"]
    assert m["out_of_order"] >= 1, m
    print(f"OK — تراجع زمني: out_of_order={m['out_of_order']}")


async def test_contract_shape_complete():
    print("\n--- test_contract_shape_complete ---")
    _atom, _bus, out = await _run([_tick(10, 0.0), _tick(11, 1.0)])
    last = out[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم ممنوعة.
    for field in ("symbol", "id", "cycle_id", "status", "signal", "warnings", "metadata",
                  "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert field in last, f"حقل ناقص بالعقد: {field}"
    for judged in ("score", "confidence", "quality", "weight", "current_depth",
                   "required_depth", "analysis_state", "ready"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    for field in ("received", "valid", "rejected", "duplicates", "out_of_order",
                  "quality_ratio"):
        assert field in last["metadata"], f"حقل metadata ناقص: {field}"
    assert last["id"] == "quality"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "300" and last["atom_id"] == "316"
    print("OK — عقد الحقائق كامل الحقول")


async def test_health_states():
    print("\n--- test_health_states ---")
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(dict(CFG)))
    h0 = await atom.health_check()
    assert h0.state == HealthState.UNHEALTHY
    await atom.start()
    h1 = await atom.health_check()
    assert h1.state == HealthState.DEGRADED
    await atom._on_tick(_tick(10, 0.0))
    h2 = await atom.health_check()
    assert h2.state == HealthState.HEALTHY
    print("OK — الصحة: UNHEALTHY→DEGRADED→HEALTHY")


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
    # ٣١٦ تقيس الجودة، فالسعر المفقود **خبرٌ تنشره** لا شيء تتجاهله —
    # حارسها على الرمز وحده. أمّا إبلاغها عن الرداءة ففي الفحص التالي.
    atom, published = await _mut_new()
    await atom._on_tick(_mut_tick(symbol=""))
    assert not published, "حمولة بلا رمز عُولجت"
    print("OK — بلا رمز تُرفض، والسعر المفقود خبرٌ لا تجاهل")


async def test_mut_quality_reports_degraded():
    """٣١٦ يجب أن تقدر على قول «رديء» — فلترٌ لا يحجب أبدًا قد يكون أعمى.
    (سؤال جلسة القرار ٢٠٢٦-٠٩-١٦: ٤٦١ عنده `seen=9997 blocked=0`.)"""
    print("\n--- test_mut_quality_reports_degraded ---")
    atom, published = await _mut_new()
    for i in range(30):
        await atom._on_tick(_mut_tick(seq=5000 + i))
    assert published[-1][1]["signal"] == "clean", "تِكّات سليمة لم تُقرأ نظيفة"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الدرجة نُزعت؛ الحقيقة نسبة الصالح في metadata.quality_ratio.
    assert "score" not in published[-1][1], published[-1][1].get("score")
    assert published[-1][1]["metadata"]["quality_ratio"] == 1.0, "نسبة النظيف ليست 1"
    assert published[-1][1]["warnings"] == [], published[-1][1]["warnings"]
    atom2, pub2 = await _mut_new()
    for i in range(30):
        await atom2._on_tick(_mut_tick(seq=6000 + i, price=None))
    assert pub2[-1][1]["signal"] == "degraded", "سعر مفقود لم يُبلَّغ عنه"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الرداءة تُقرأ من النسبة وعدّاد المفقود والتحذير، لا من درجة.
    assert "score" not in pub2[-1][1], pub2[-1][1].get("score")
    assert pub2[-1][1]["metadata"]["quality_ratio"] == 0.0, "نسبة الرديء ليست صفرًا"
    assert pub2[-1][1]["metadata"]["nan"] == 30, pub2[-1][1]["metadata"]
    assert "data_quality_degraded" in pub2[-1][1]["warnings"]
    atom3, pub3 = await _mut_new()
    for i in range(30):
        await atom3._on_tick(_mut_tick(seq=7000 + i, price=-1.0))
    assert pub3[-1][1]["signal"] == "degraded", "سعر سالب لم يُبلَّغ عنه"
    print("OK — نظيف=1.0 · مفقود=صفر · سالب=رديء: الفلتر يقيس شيئًا")


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


async def test_mut_quality_threshold_is_sharp():
    """الحدّ عند `min_quality` **بالضبط**: نسبةٌ تساويه نظيفة، وأقلّ منه بخطوةٍ رديئة.

    إزاحةُ المقارنة (`>=` ⇢ `>`) تمرّ بلا أن يسقط فحصٌ واحد ما لم تُقَس
    النسبةُ عند الحدّ نفسه لا في وسط المدى.
    """
    print("\n--- test_mut_quality_threshold_is_sharp ---")
    cfg = _mut_cfg()
    size = int(cfg.get("window_size") or 20)
    need = float(cfg.get("min_quality") or 0.95)
    bad = int(round(size * (1.0 - need)))
    assert bad >= 1, "الحدّ لا يسمح بأيّ خطأ — لا حدّ يُقاس"

    async def ratio_with(bad_count, seed):
        atom, published = await _mut_new()
        for i in range(size):
            price = None if i < bad_count else 1.5
            await atom._on_tick(_mut_tick(seq=seed + i, price=price))
        return published[-1][1]

    at_edge = await ratio_with(bad, 9100)
    below = await ratio_with(bad + 1, 9200)
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): رسالة الفشل تقرأ النسبة من metadata بعد نزع الدرجة.
    assert at_edge["signal"] == "clean", \
        "نسبةٌ تساوي الحدّ لم تُقرأ نظيفة (نسبة=%s)" % at_edge["metadata"].get("quality_ratio")
    assert below["signal"] == "degraded", \
        "نسبةٌ دون الحدّ بخطوة لم تُقرأ رديئة (نسبة=%s)" % below["metadata"].get("quality_ratio")
    print("OK — نظيفٌ عند الحدّ، ورديءٌ دونه بخطوة واحدة")


async def test_mut_threshold_actually_discriminates():
    """ذرّةٌ لها عتبةُ تصنيف يجب أن تُخرج **أكثر من حكم** عبر أنماط مختلفة.

    الدرس من ٣٠٧: ظلّت تقول `insufficient_data` لكلّ تِكّة منذ اعتماد
    المعرّف الموحّد ولم يسقط بذلك فحصٌ واحد. عتبةٌ لا تُصنّف شيئًا ذرّةٌ
    ميتةٌ بشارةٍ خضراء — وهذا الفحص يمنع تكرارها في القسم كلّه.
    """
    print("\n--- test_mut_threshold_actually_discriminates ---")
    # ٣١٦ يُصنّف بجودة البيانات لا بشكل السعر: أنماطٌ سليمة كلّها تُقرأ
    # `clean` بحقّ. تصنيفه مقيسٌ في `test_mut_quality_reports_degraded`
    # و`test_mut_quality_threshold_is_sharp`.
    print("OK — التصنيف مقيسٌ في فحصَين أخصّ من هذا")
    return
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


async def test_mut_crossed_spread_is_not_clean():
    """السبريد المقلوب أو الصفريّ عيبُ جودةٍ لا سعرٌ سليم.

    ١١٢ يرفضه على مسار التِكّة بالاسم نفسه (`crossed_spread`)، وكانت ٣١٦
    تعدّه **نظيفًا بدرجة ١٠٠** فيصل فلترَ الشروط ٤٦١ حكمٌ كاذب عن جودةٍ
    لم تُقَس. الفحص يغطّي الجهات الثلاث: مقلوب، وصفريّ، وسليم.
    """
    print("\n--- test_mut_crossed_spread_is_not_clean ---")
    size = int(_mut_cfg().get("window_size") or 20)

    async def feed(seed, **over):
        atom, published = await _mut_new()
        for i in range(size):
            await atom._on_tick(_mut_tick(seq=seed + i, price=1.5, **over))
        return published[-1][1]

    crossed = await feed(40000, bid=1.6, ask=1.4)
    assert crossed["signal"] == "degraded", "سبريدٌ مقلوب قُرئ نظيفًا"
    assert crossed["metadata"]["crossed_spread"] == size, \
        "المقلوب لم يُعدّ: %s" % crossed["metadata"].get("crossed_spread")

    zero = await feed(41000, bid=1.5, ask=1.5)
    assert zero["signal"] == "degraded", "سبريدٌ صفريّ قُرئ نظيفًا"

    healthy = await feed(42000)
    assert healthy["signal"] == "clean", "سبريدٌ سليم قُرئ رديئًا"
    assert healthy["metadata"]["crossed_spread"] == 0
    print("OK — المقلوب والصفريّ رديئان، والسليم نظيف")


async def test_mut_price_off_quote_blocks():
    """السعر خارج نطاق اقتباسه **يُبطل صلاحية التِكّة** — ختم `NQ` ٢٠٢٦-٠٩-١٨.

    كان عدّادًا يُعلَن ولا يحجب حتّى يُقاس وقوعه؛ فقِيس صفرًا في 3,616 تِكّة
    مستقبَلة، فأذن المالك بالحجب. والسبريد المقلوب يسبقه في السلسلة كي
    يُوسَم بسببه الأخصّ (`crossed_spread`) لا بخروج السعر عن نطاقٍ مقلوب.
    """
    print("\n--- test_mut_price_off_quote_blocks ---")
    size = int(_mut_cfg().get("window_size") or 20)

    async def feed(seed, **over):
        atom, published = await _mut_new()
        for i in range(size):
            await atom._on_tick(_mut_tick(seq=seed + i, **over))
        return published[-1][1]

    off = await feed(43000, price=1.9, bid=1.4, ask=1.5)   # السعر فوق الطلب
    assert off["metadata"]["price_off_quote"] == size, \
        "الخارج عن الاقتباس لم يُعدّ: %s" % off["metadata"].get("price_off_quote")
    assert off["signal"] == "degraded", "الخارج عن الاقتباس لم يُبطل الصلاحية"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحجب باقٍ في البطاقة: صالحٌ صفر ونسبةٌ صفر وتحذير، بلا درجة.
    assert "score" not in off and "quality" not in off, (off.get("score"), off.get("quality"))
    assert off["metadata"]["quality_ratio"] == 0.0, "نسبةُ نافذةٍ كلّها خارج اقتباسها ليست صفرًا"
    assert off["metadata"]["valid"] == 0 and off["metadata"]["rejected"] == size, off["metadata"]
    assert "data_quality_degraded" in off["warnings"], off["warnings"]

    below = await feed(43500, price=1.1, bid=1.4, ask=1.5)  # وتحت العرض
    assert below["metadata"]["price_off_quote"] == size

    healthy = await feed(44000, price=1.5)
    assert healthy["metadata"]["price_off_quote"] == 0, "سعرٌ داخل اقتباسه عُدّ خارجًا"
    print("OK — يُعدّ ويحجب في الجهتين، والسليم لا يُمسّ")


async def main():
    tests = [test_all_clean, test_degraded_mixed, test_counts_rejects,
             test_duplicates, test_out_of_order, test_contract_shape_complete,
             test_health_states,
             test_mut_stopped_atom_publishes_nothing,
             test_mut_incomplete_payload_rejected,
             test_mut_quality_reports_degraded,
             test_mut_crossed_spread_is_not_clean,
             test_mut_price_off_quote_blocks,
             test_mut_quality_threshold_is_sharp,
             test_mut_min_points_boundary_is_sharp,
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
