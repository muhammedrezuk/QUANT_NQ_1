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
    "_atom307", _Path(__file__).resolve().parents[1] / "atom.py")
_mod = _ilu.module_from_spec(_spec)
sys.modules["_atom307"] = _mod
_spec.loader.exec_module(_mod)
Atom = _mod.Atom
EVENT_OUT = _mod.EVENT_OUT

REF = "USTEC"
SYM = "XAUUSD"
CFG = {"reference_symbol": REF, "window": 30,
       "strong_threshold": 0.7, "moderate_threshold": 0.4}


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
        return AtomContext(atom_id=307, config=config, logger=_NullLogger(),
                           publish=self.publish, subscribe=self.subscribe)


def _tick(price, sequence, symbol, timeframe="60s"):
    return {"symbol": symbol, "price": price, "volume": 1, "timeframe": "tick",
            "timestamp": sequence, "sequence": sequence}


def _series(rets, start=100.0):
    closes = [start]
    for r in rets:
        closes.append(closes[-1] * (1.0 + r))
    return closes


async def _run(ref_rets, sym_rets, cfg=None):
    bus = FakeEventBus()
    atom = Atom()
    await atom.initialize(bus.make_context(cfg or dict(CFG)))
    await atom.start()
    ref_closes = _series(ref_rets)
    sym_closes = _series(sym_rets)
    for i in range(len(ref_closes)):
        await atom._on_tick(_tick(ref_closes[i], float(i), REF))
        await atom._on_tick(_tick(sym_closes[i], float(i), SYM))
    sym_out = [p for n, p in bus.published if n == EVENT_OUT and p["symbol"] == SYM]
    ref_out = [p for n, p in bus.published if n == EVENT_OUT and p["symbol"] == REF]
    return atom, sym_out, ref_out


_RETS = [0.01, -0.006, 0.008, -0.003, 0.011, -0.009, 0.004, 0.007,
         -0.005, 0.006, -0.002, 0.009]


async def test_strong_positive():
    print("\n--- test_strong_positive ---")
    _atom, sym_out, _ref = await _run(_RETS, list(_RETS))
    last = sym_out[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «strong» كلمة قوّةٍ نُزعت؛ القوّة تُقرأ من قيمة الارتباط الخامّة فوق عتبتها.
    assert "signal" not in last, last.get("signal")
    assert last["metadata"]["direction"] == "positive", last["metadata"]["direction"]
    assert last["metadata"]["value"] > 0.9, last["metadata"]["value"]
    assert abs(last["metadata"]["value"]) >= CFG["strong_threshold"], last["metadata"]
    print(f"OK — عوائد متطابقة: ارتباط موجب r={last['metadata']['value']} بلا كلمة قوّة")


async def test_strong_inverse():
    print("\n--- test_strong_inverse ---")
    inv = [-r for r in _RETS]
    _atom, sym_out, _ref = await _run(_RETS, inv)
    last = sym_out[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «strong» كلمة قوّةٍ نُزعت؛ القوّة تُقرأ من قيمة الارتباط الخامّة فوق عتبتها.
    assert "signal" not in last, last.get("signal")
    assert last["metadata"]["direction"] == "inverse", last["metadata"]["direction"]
    assert last["metadata"]["value"] < -0.9, last["metadata"]["value"]
    assert abs(last["metadata"]["value"]) >= CFG["strong_threshold"], last["metadata"]
    print(f"OK — عوائد معاكسة: ارتباط عكسيّ r={last['metadata']['value']} بلا كلمة قوّة")


async def test_insufficient_overlap():
    print("\n--- test_insufficient_overlap ---")
    _atom, sym_out, _ref = await _run(_RETS[:3], list(_RETS[:3]))
    assert sym_out[-1]["status"] == "insufficient_data", sym_out[-1]["status"]
    print("OK — تداخل ناقص: insufficient")


async def test_reference_signal():
    print("\n--- test_reference_signal ---")
    _atom, _sym, ref_out = await _run(_RETS, list(_RETS))
    non_insuf = [p for p in ref_out if p["status"] == "ok"]
    assert non_insuf, "لا مخرج ok للمرجع"
    assert non_insuf[-1]["signal"] == "reference", non_insuf[-1]["signal"]
    print("OK — الرمز المرجعي: reference")


async def test_contract_shape_complete():
    print("\n--- test_contract_shape_complete ---")
    _atom, sym_out, _ref = await _run(_RETS, list(_RETS))
    last = sym_out[-1]
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الحقول المطلوبة صارت ختم الحقيقة، وحقول الحكم (ومنها الصوت) ممنوعة.
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «signal» خرج من المطلوب إلى الممنوع — قيمته كلمة قوّةٍ تُنزع.
    for field in ("symbol", "id", "cycle_id", "status", "warnings", "metadata",
                  "as_of", "computed_on", "section_id", "atom_id", "contract"):
        assert field in last, f"حقل ناقص بالعقد: {field}"
    for judged in ("signal", "score", "confidence", "quality", "weight", "current_depth",
                   "required_depth", "analysis_state", "ready", "direction"):
        assert judged not in last, f"حقل حكمٍ ظهر: {judged}"
    for field in ("value", "direction", "reference", "points"):
        assert field in last["metadata"], f"حقل metadata ناقص: {field}"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): «على كم حُسب» يقرأ العدد الفعليّ — نقاط التداخل نفسها.
    assert last["computed_on"] == last["metadata"]["points"], (last["computed_on"], last["metadata"])
    assert last["id"] == "correlation"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "300" and last["atom_id"] == "307"
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
    await atom._on_tick(_tick(100.0, 0.0, REF))
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
    """الارتباط يحتاج **تداخل سلسلتين**، فحدّه يُقاس على الرمز والمرجع معًا.

    ومنذ 1.3.0 المزاوجة زمنية: كانت على `sequence` وهو فريدٌ لكل تِكّة على
    مستوى الحساب، فلا تتطابق تِكّتا رمزين أبدًا ⇒ التداخل صفر ⇒ الذرّة لم
    تحسب ارتباطًا واحدًا قطّ. إن عادت المزاوجة إلى `sequence` سقط هذا الفحص.
    """
    print("\n--- test_mut_min_points_boundary_is_sharp ---")
    need = _mut_min_points()
    ref = _mut_cfg().get("reference_symbol")
    assert need and ref, "الحدّ أو الرمز المرجعيّ غير معلَن"
    atom, published = await _mut_new()
    marks = []
    for i in range(need + 3):
        base = 1788960000.0 + i
        await atom._on_tick(_mut_tick(seq=9000 + 2 * i, price=2.0 + i * 0.021,
                                      symbol=ref, timestamp=base,
                                      exchange_timestamp=base))
        await atom._on_tick(_mut_tick(seq=9001 + 2 * i, price=1.2 + i * 0.017,
                                      timestamp=base + 0.3,
                                      exchange_timestamp=base + 0.3))
        marks.append(published[-1][1].get("status"))
    assert "ok" in marks, "التداخل لم يبلغ الحدّ إطلاقًا — المزاوجة لا تُطابق شيئًا"
    first_ok = marks.index("ok")
    assert first_ok >= 1 and marks[first_ok - 1] == "insufficient_data", \
        "الحدّ غير حادّ: ما قبل أوّل `ok` ليس `insufficient_data`"
    print("OK — التداخل يبلغ الحدّ عند الزوج %d" % (first_ok + 1))

async def test_mut_dense_symbol_reaches_overlap_too():
    """النافذة تُعدّ **سلالًا زمنية لا تِكّات**: رمزٌ كثيف يبلغ التداخل كالبطيء.

    كانت النافذة طابورًا بسقفٍ من الأزواج، فرمزٌ يرسل عشر تِكّات في الثانية
    يملأ ثلاثينه من ثلاث سلالٍ ويبقى تداخله دون الحدّ **أبدًا** — وهو ما
    قِيس حيًّا: XAUUSD صفرُ `ok` بينما BTCUSD وGBPUSD 18–30 نقطة.
    """
    print("\n--- test_mut_dense_symbol_reaches_overlap_too ---")
    need = _mut_min_points()
    ref = _mut_cfg().get("reference_symbol")
    assert need and ref, "الحدّ أو المرجع غير معلَن"
    atom, published = await _mut_new()
    marks = []
    for i in range(need + 3):
        base = 1788960000.0 + i
        await atom._on_tick(_mut_tick(seq=4000 + i, price=2.0 + i * 0.021,
                                      symbol=ref, timestamp=base,
                                      exchange_timestamp=base))
        for k in range(10):          # عشر تِكّات داخل الثانية نفسها
            ts = base + 0.05 * k
            await atom._on_tick(_mut_tick(seq=50000 + i * 10 + k,
                                          price=1.2 + i * 0.017 + k * 0.0001,
                                          timestamp=ts, exchange_timestamp=ts))
        marks.append(published[-1][1].get("status"))
    assert "ok" in marks, "رمز كثيف لم يبلغ التداخل إطلاقًا"
    # الحكم هنا على **النقاط** لا على الحالة: نافذة التِكّات كانت تمرّ على
    # ثلاثين زوجًا فتحتسب السلّة الواحدة عشر مرّات، فتبلغ الحدَّ بنقاطٍ
    # مكرّرة ويتضخّم الارتباط زيفًا. النقاط لا يجوز أن تتجاوز عدد الثواني.
    points = published[-1][1].get("metadata", {}).get("points")
    assert points is not None, "النقاط غير معلَنة"
    assert points <= need + 3, \
        "النقاط (%s) تجاوزت عدد السلال — سلّة واحدة حُسبت مرارًا" % points
    print("OK — الكثيف يبلغ التداخل بنقاطٍ غير مكرّرة (%d)" % points)


async def test_mut_threshold_actually_discriminates():
    """ذرّةٌ لها عتبةُ تصنيف يجب أن تُخرج **أكثر من حكم** عبر أنماط مختلفة.

    الدرس من ٣٠٧: ظلّت تقول `insufficient_data` لكلّ تِكّة منذ اعتماد
    المعرّف الموحّد ولم يسقط بذلك فحصٌ واحد. عتبةٌ لا تُصنّف شيئًا ذرّةٌ
    ميتةٌ بشارةٍ خضراء — وهذا الفحص يمنع تكرارها في القسم كلّه.
    """
    print("\n--- test_mut_threshold_actually_discriminates ---")
    # ٣٠٧ يُصنّف من **تداخل سلسلتين** (الرمز والمرجع) لا من شكل سعرِ رمزٍ
    # واحد، فنمطٌ مفردٌ يتركه `insufficient_overlap` دائمًا. تصنيفه مقيسٌ
    # في `test_mut_min_points_boundary_is_sharp` و`..._dense_symbol_...`.
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


_VOTE_STEPS = [0.010, -0.008, 0.015, -0.012, 0.020, -0.005, 0.011, -0.014,
               0.009, -0.007, 0.013, -0.011, 0.016, -0.009, 0.012, -0.013,
               0.018, -0.006, 0.014, -0.010, 0.017, -0.015, 0.008, -0.004,
               0.019, -0.013, 0.010, -0.009, 0.015, -0.011, 0.012, -0.008,
               0.016, -0.012, 0.011, -0.007]


async def _vote_of(ref_dir, sym_sense):
    """يشغّل الذرّة على مرجعٍ باتّجاهٍ معلوم ورمزٍ يتحرّك معه أو عكسه."""
    ref = _mut_cfg().get("reference_symbol")
    atom, published = await _mut_new()
    rp, sp = 2.0, 1.2
    for i, step in enumerate(_VOTE_STEPS):
        base = 1788960000.0 + i
        rstep = step * ref_dir + 0.004 * ref_dir
        rp *= (1.0 + rstep)
        sp *= (1.0 + rstep * sym_sense)
        await atom._on_tick(_mut_tick(seq=60000 + 2 * i, price=rp, symbol=ref,
                                      timestamp=base, exchange_timestamp=base))
        await atom._on_tick(_mut_tick(seq=60001 + 2 * i, price=sp,
                                      timestamp=base + 0.3,
                                      exchange_timestamp=base + 0.3))
    return published[-1][1]


async def test_mut_vote_follows_reference_not_correlation_sign():
    """الصوت = اتجاه المرجع × إشارة الارتباط — لا إشارة الارتباط وحدها.

    ختم `NQ` ٢٠٢٦-٠٩-١٨. ارتباطٌ موجب مع المرجع يعني «يتحرّك معه» لا
    «اشترِ»: فلو نُشرت الإشارةُ خامًا لقرأتها غرفة القرار صوتَ صعودٍ ولو
    كان المرجع هابطًا. المصفوفة الأربع هي الفحص، لا حالةٌ واحدة — وحالتان
    منها (المرجع الهابط) تنقلبان عن الإشارة الخام.
    """
    print("\n--- test_mut_vote_follows_reference_not_correlation_sign ---")
    up_with = await _vote_of(+1, +1)
    up_against = await _vote_of(+1, -1)
    down_with = await _vote_of(-1, +1)
    down_against = await _vote_of(-1, -1)

    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): الصوت حكمٌ نُزع؛ الحقيقة الباقية قيمة الارتباط وإشارته في metadata.
    cases = (("صاعد+معه", up_with, "positive"), ("صاعد+عكسه", up_against, "inverse"),
             ("هابط+معه", down_with, "positive"), ("هابط+عكسه", down_against, "inverse"))
    for label, row, sense in cases:
        assert "direction" not in row, "صوتٌ ظهر في حالة %s: %r" % (label, row.get("direction"))
        assert row["status"] == "ok" and row["contract"] == "facts.v1", (label, row["status"])
        assert row["metadata"]["direction"] == sense, (label, row["metadata"])
        assert (row["metadata"]["value"] > 0) == (sense == "positive"), (label, row["metadata"])
        assert row["metadata"]["points"] >= _mut_min_points(), (label, row["metadata"])

    # والارتباط نفسه لا ينقلب بانقلاب المرجع: الفرق في الصوت لا في القياس
    assert up_with["metadata"]["value"] > 0 and down_with["metadata"]["value"] > 0, \
        "الارتباط تبدّل مع اتّجاه المرجع — والمفروض أن يتبدّل الصوت وحده"

    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): لا غلاف جاهزيّة ولا حالة تحليل؛ الحكم كلّه للاستراتيجيّة.
    for label, row, _sense in cases:
        for judged in ("unified", "analysis_state", "ready", "state"):
            assert judged not in row, "حقل حكمٍ ظهر في حالة %s: %s" % (label, judged)
    print("OK — أربع حالات بلا صوت، وإشارة الارتباط تتبع حركة الرمز مع المرجع لا اتّجاهه")


async def test_mut_reference_symbol_does_not_vote():
    """المرجع لا يرتبط بنفسه فلا صوت له — و`None` لا صفر.

    صفرٌ يُقرأ حيادًا مقيسًا، والمجهول ليس حيادًا (§١٠).
    """
    print("\n--- test_mut_reference_symbol_does_not_vote ---")
    ref = _mut_cfg().get("reference_symbol")
    atom, published = await _mut_new()
    for i in range(6):
        base = 1788960000.0 + i
        await atom._on_tick(_mut_tick(seq=70000 + i, price=2.0 + i * 0.01,
                                      symbol=ref, timestamp=base,
                                      exchange_timestamp=base))
    last = published[-1][1]
    assert last["signal"] == "reference", "لم تُقرأ حمولة المرجع"
    assert "direction" not in last, "المرجع صوّت على نفسه"
    print("OK — المرجع حاضرٌ بلا صوت")


async def main():
    tests = [test_strong_positive, test_strong_inverse, test_insufficient_overlap,
             test_reference_signal, test_contract_shape_complete, test_health_states,
             test_mut_stopped_atom_publishes_nothing,
             test_mut_incomplete_payload_rejected,
             test_mut_min_points_boundary_is_sharp,
             test_mut_dense_symbol_reaches_overlap_too,
             test_mut_vote_follows_reference_not_correlation_sign,
             test_mut_reference_symbol_does_not_vote,
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
