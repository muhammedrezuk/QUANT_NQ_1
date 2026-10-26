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
    "_atom315", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom315"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT

CFG = {"window_size": 20, "high_band": 0.8, "low_band": 0.2}


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
        return AtomContext(atom_id=315, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _tick(price, sequence=0.0, symbol="NQ100", timeframe="60s"):
    return {"symbol": symbol, "price": price, "volume": 1, "timeframe": "tick",
            "timestamp": sequence}


async def _run(closes, cfg=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg or dict(CFG)))
    await atom.start()
    for i, c in enumerate(closes):
        await atom._on_tick(_tick(c, sequence=i))
    out = [p for n, p in bus.published if n == EVENT_OUT]
    return atom, bus, out


async def test_insufficient():
    print("\n--- test_insufficient ---")
    _atom, _bus, out = await _run([10])
    assert out[-1]["status"] == "insufficient_data", out[-1]["status"]
    print("OK — نقطة واحدة: insufficient")


async def test_at_high():
    print("\n--- test_at_high ---")
    _atom, _bus, out = await _run([10, 11, 12, 13, 14])
    last = out[-1]
    assert last["signal"] == "at_high", (last["signal"], last["metadata"])
    print(f"OK — صاعد: at_high (pos={last['metadata']['position']})")


async def test_at_low():
    print("\n--- test_at_low ---")
    _atom, _bus, out = await _run([14, 13, 12, 11, 10])
    last = out[-1]
    assert last["signal"] == "at_low", (last["signal"], last["metadata"])
    print(f"OK — هابط: at_low (pos={last['metadata']['position']})")


async def test_mid():
    print("\n--- test_mid ---")
    _atom, _bus, out = await _run([10, 14, 12])
    last = out[-1]
    assert last["signal"] == "mid", (last["signal"], last["metadata"])
    print(f"OK — وسط: mid (pos={last['metadata']['position']})")


async def test_zero_range():
    print("\n--- test_zero_range ---")
    _atom, _bus, out = await _run([10, 10, 10])
    last = out[-1]
    assert last["signal"] == "mid", last["signal"]
    assert "zero_range" in last["warnings"], last["warnings"]
    print("OK — متطابق: mid + zero_range")


async def test_contract_shape_complete():
    print("\n--- test_contract_shape_complete ---")
    _atom, _bus, out = await _run([10, 12, 11, 13, 10])
    last = out[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم ممنوعة.
    for field in ("symbol", "id", "cycle_id", "status", "signal", "warnings", "metadata",
                  "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert field in last, f"حقل ناقص بالعقد: {field}"
    for judged in ("score", "confidence", "quality", "weight", "current_depth",
                   "required_depth", "analysis_state", "ready"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    for field in ("min", "max", "range", "position"):
        assert field in last["metadata"], f"حقل metadata ناقص: {field}"
    assert last["id"] == "range"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "300" and last["atom_id"] == "315"
    assert last["computed_on"] == last["metadata"]["count"]
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
    await atom._on_tick(_tick(10))
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


async def test_mut_band_threshold_is_sharp():
    """الحدّ عند `high_band` **بالضبط**: موضعٌ يساويه يختلف حكمه عمّا دونه.

    النافذة تُبنى بمدًى معلوم [1.0, 2.0] فيكون الموضع = آخر سعر ناقص الأدنى.
    """
    print("\n--- test_mut_band_threshold_is_sharp ---")
    cfg = _mut_cfg()
    size = int(cfg.get("window_size") or 20)
    high = float(cfg.get("high_band") or 0.8)

    async def at_position(pos, seed):
        atom, published = await _mut_new()
        prices = [1.0, 2.0] + [1.5] * (size - 3) + [1.0 + pos]
        for i, price in enumerate(prices):
            await atom._on_tick(_mut_tick(seq=seed + i, price=price))
        return published[-1][1]

    on_edge = await at_position(high, 9300)
    below = await at_position(high - 0.02, 9400)
    assert on_edge.get("signal") != below.get("signal"), \
        "الموضع عند الحدّ (%.2f) لا يختلف عمّا دونه — الحدّ غير مُختبَر عنده" % high
    print("OK — الحكم يتبدّل عند %.2f بالضبط" % high)


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
    tests = [test_insufficient, test_at_high, test_at_low, test_mid,
             test_zero_range, test_contract_shape_complete, test_health_states,
             test_mut_stopped_atom_publishes_nothing,
             test_mut_incomplete_payload_rejected,
             test_mut_min_points_boundary_is_sharp,
             test_mut_band_threshold_is_sharp,
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
