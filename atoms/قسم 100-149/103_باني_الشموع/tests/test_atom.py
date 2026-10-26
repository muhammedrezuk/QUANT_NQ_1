import asyncio, importlib.util, sys
from pathlib import Path
root = Path(__file__).resolve().parents[4]; folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location('_t103', folder / 'atom.py')
m = importlib.util.module_from_spec(spec); sys.modules['_t103'] = m; spec.loader.exec_module(m)


class L:
    def __getattr__(self, n): return lambda *a, **k: None


class B:
    def __init__(self): self.e = []
    def subscribe(self, *a): pass
    async def publish(self, n, p): self.e.append((n, p))


def _tick(ts, bid=100, ask=101):
    return {'account_id': 'A', 'broker': 'BR', 'provider': 'MT5', 'symbol': 'NQ',
            'bid': bid, 'ask': ask, 'timestamp': ts}


async def _new(frames):
    b = B(); a = m.Atom()
    await a.initialize(m.AtomContext(103, {'timeframes': frames}, L(), b.publish, b.subscribe))
    await a.start()
    return a, b


async def test_single_frame_backward_compatible():
    a, b = await _new(['60s'])
    await a._on_tick(_tick(1))
    await a._on_tick(_tick(61, 102, 103))
    out = [p for n, p in b.e if n == m.EVENT_OUT]
    assert len(out) == 1 and out[0]['timeframe'] == '60s'
    assert out[0]['open'] == 100.5 and out[0]['period_start'] == 0.0
    print('OK — فريم واحد افتراضي: نفس سلوك 4.1.0 بالضبط')


async def test_factory_builds_frames_in_parallel_batch():
    a, b = await _new(['5s', '60s'])
    for ts in (1, 3, 6, 9):          # فريم 5ث يغلق عند 6 و(لا) — 60ث ما زال يبني
        await a._on_tick(_tick(ts))
    fives = [p for n, p in b.e if n == m.EVENT_OUT and p['timeframe'] == '5s']
    assert len(fives) == 1 and fives[0]['period_start'] == 0.0, fives
    assert not [p for n, p in b.e if n == m.EVENT_OUT and p['timeframe'] == '60s']
    await a._on_tick(_tick(61))      # هنا الدفعة: 5ث يقفل دوره و60ث يقفل دوره سوا
    outs = [p for n, p in b.e if n == m.EVENT_OUT]
    assert {o['timeframe'] for o in outs[-2:]} == {'5s', '60s'}
    h = await a.health_check()
    assert h.details['batch_releases'] >= 1 and h.details['closed_by_frame']['5s'] >= 2
    print('OK — مصنع الفريمات: 5ث و60ث بالتوازي، ودفعات عند التقاطع')


async def test_bad_frames_ignored_default_kept():
    a, b = await _new(['zz', '60s'])
    assert [name for name, _ in a._frames] == ['60s']
    print('OK — فريم تالف يُتجاهل والافتراضي يبقى')


async def main():
    await test_single_frame_backward_compatible()
    await test_factory_builds_frames_in_parallel_batch()
    await test_bad_frames_ignored_default_kept()
    print('103 frame factory tests passed')


if __name__ == '__main__':
    asyncio.run(main())


# ٢٠٢٦-٠٩-١٦ — أُضيفت بعد اختبار طفرات نجا منه ثلاثٌ من هذا الملفّ.
# الاختبارات القديمة تفحص عدد الشموع وإطاراتها وفتحها، ولا تفحص
# أعلاها وأدناها ولا حدود الحرّاس. والشموع يستهلكها 24 ذرّة.


async def test_high_and_low_track_the_real_extremes():
    """`high` أعلى ما مرّ و`low` أدناه — طفرة `max` ← `min` نجت من كل
    اختبار سابق لأنّ لا أحد قرأ الحقلين.

    شمعة بأعلى مقلوب تقلب كل تحليل مدى أو اختراق يُبنى عليها، ولا
    عدّاد يتحرّك ولا شارة تحمرّ.
    """
    a, b = await _new(['60s'])
    for ts, bid, ask in ((1, 100, 101), (5, 108, 109), (9, 94, 95), (13, 102, 103)):
        await a._on_tick(_tick(ts, bid, ask))
    await a._on_tick(_tick(61, 100, 101))          # يغلق الشمعة الأولى
    out = [p for n, p in b.e if n == m.EVENT_OUT][0]
    assert out['open'] == 100.5, out['open']
    assert out['high'] == 108.5, ("أعلى الشمعة", out['high'])
    assert out['low'] == 94.5, ("أدنى الشمعة", out['low'])
    assert out['close'] == 102.5, out['close']
    assert out['high'] >= out['open'] >= out['low']
    assert out['tick_count'] == 4, out['tick_count']
    print('OK — أعلى الشمعة وأدناها يتبعان الطرفين الحقيقيّين')


async def test_zero_spread_tick_builds_no_candle():
    """`ask == bid` دفتر معطوب — القاعدة موحّدة مع 112 و106 و115.

    طفرة `ask <= bid` ← `ask < bid` نجت: شمعة تُبنى من سعرٍ يُشترى
    ويُباع بالقيمة عينها. الحدّ هو التساوي نفسه لا الانقلاب.
    """
    a, b = await _new(['60s'])
    await a._on_tick(_tick(1, 100, 100))           # سبريد صفريّ
    assert a.unusable_dropped == 1, a.unusable_dropped
    await a._on_tick(_tick(2, 101, 100))           # مقلوب
    assert a.unusable_dropped == 2
    await a._on_tick(_tick(3, 100, 101))           # سليم
    assert a.unusable_dropped == 2
    await a._on_tick(_tick(61, 100, 101))
    out = [p for n, p in b.e if n == m.EVENT_OUT]
    assert len(out) == 1 and out[0]['tick_count'] == 1, out
    print('OK — السبريد الصفريّ والمقلوب لا يبنيان شمعة، ويُعدّان')


async def test_repeated_sequence_is_dropped_at_the_boundary():
    """`seq <= last` — التسلسل **المكرّر** يُسقط كالمتراجع.

    طفرة `<=` ← `<` نجت لأنّ الاختبارات كانت تستعمل تسلسلًا متراجعًا
    فقط. والتكرار هو الحالة الواقعيّة: إعادة إرسال من الوسيط.
    """
    a, b = await _new(['60s'])
    await a._on_tick({**_tick(1), 'sequence': 10})
    await a._on_tick({**_tick(2), 'sequence': 10})   # الحدّ: مكرّر
    assert a.out_of_order_dropped == 1, a.out_of_order_dropped
    await a._on_tick({**_tick(3), 'sequence': 9})    # متراجع
    assert a.out_of_order_dropped == 2
    await a._on_tick({**_tick(4), 'sequence': 11})   # متقدّم
    assert a.out_of_order_dropped == 2
    print('OK — التسلسل المكرّر يُسقط كالمتراجع، والمتقدّم يمرّ')

def test_four_hour_and_day_follow_the_broker_day_like_the_history_db():
    """٢٠٢٦-١٠-٠٨ (تدقيق الإغلاق — «الحيّ = المقيس»): الأربع ساعات واليوم على يوم الوسيط (إغلاق نيويورك)،
    كقاعدة تاريخ سي‑تريدر التي قيست بها البطاقة 414 — والساعة وما دونها على غرينتش كما كانت."""
    import calendar as _cal
    import importlib.util as _u
    from pathlib import Path as _P
    spec = _u.spec_from_file_location("_t103_align", _P(__file__).resolve().parents[1] / "atom.py")
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    at = lambda s: float(_cal.timegm(__import__("time").strptime(s, "%Y-%m-%d %H:%M")))
    hhmm = lambda t: __import__("time").strftime("%H:%M", __import__("time").gmtime(t))
    # صيفًا (+3): الأربع ساعات تبدأ 01/05/09/13/17/21 غرينتش، واليوم 21:00.
    assert hhmm(mod.frame_period_start(at("2026-10-07 07:20"), 14400)) == "05:00"
    assert hhmm(mod.frame_period_start(at("2026-10-07 07:20"), 86400)) == "21:00"
    # شتاءً (+2): 02/06/10…، واليوم 22:00.
    assert hhmm(mod.frame_period_start(at("2026-01-14 07:20"), 14400)) == "06:00"
    assert hhmm(mod.frame_period_start(at("2026-01-14 07:20"), 86400)) == "22:00"
    # الساعة وما دونها لم تتغيّر.
    assert hhmm(mod.frame_period_start(at("2026-10-07 07:20"), 3600)) == "07:00"
    assert hhmm(mod.frame_period_start(at("2026-10-07 07:22"), 300)) == "07:20"
    # افتتاح الأحد مساءً يبدأ يوم الاثنين (لا «يوم أحدٍ» من ساعتين): الأحد 22:05 غرينتش صيفًا ⟵ يومٌ يبدأ 21:00.
    assert hhmm(mod.frame_period_start(at("2026-10-04 22:05"), 86400)) == "21:00"
