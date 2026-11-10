"""الذرّة 120 — تصنيف الأخبار وأثرها: الأصناف بالكلمات، والحركة بعد الخبر على شموعٍ معروفة الأرقام.

٢٠٢٦-١٠-٠٨ (ختم المالك «NQ» — المعرفة أوّلًا): كلّ رقمٍ هنا محسوبٌ باليد قبل التشغيل. لا قاعدة حيّة تُقرأ.
"""
import calendar
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest
import yaml

from core.contracts.atom import AtomContext, HealthState

FOLDER = Path(__file__).resolve().parents[1]
if str(FOLDER) not in sys.path:
    sys.path.insert(0, str(FOLDER))

_spec = importlib.util.spec_from_file_location("_t120_atom", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t120_atom"] = m
_spec.loader.exec_module(m)

import news_category_rules as rules  # noqa: E402

# الأربعاء ٢٠٢٦-١٠-٠٧ 13:00 غرينتش — السوق مفتوح.
T0 = calendar.timegm(time.strptime("2026-10-07 13:00", "%Y-%m-%d %H:%M"))
CONFIG = {"symbol": "USTEC", "price_timeframe": "1m", "keep_news": 200, "recent_per_category": 3,
          "price_buffer_candles": 1500}
# إغلاقات معروفة: الشمعة i تُغلق عند T0 + (i+1)×60. عند T0 (i=-1) = 20000 · عند T0+5د (i=4) = 20100 (+0.5٪)
# · عند T0+15د (i=14) = 19900 (−0.5٪) · عند T0+60د (i=59) = 20400 (+2٪) · وغيرها 20000.
KNOWN = {4: 20100.0, 14: 19900.0, 59: 20400.0}
FORBIDDEN_KEYS = {"direction", "signal", "strength", "confidence", "weight", "score", "probability",
                  "threshold", "depth", "readiness"}
FORBIDDEN_WORDS = ("buy", "sell", "bullish", "bearish", "strong", "weak")


class Bus:
    def __init__(self):
        self.events = []
        self.handlers = {}

    def subscribe(self, name, handler):
        self.handlers.setdefault(name, []).append(handler)

    async def publish(self, name, payload):
        self.events.append((name, payload))

    def payloads(self, name):
        return [p for n, p in self.events if n == name]


class Logger:
    def __getattr__(self, _name):
        return lambda *a, **k: None


async def _atom(config=None, now=T0):
    atom, bus = m.Atom(), Bus()
    await atom.initialize(AtomContext(120, dict(config or CONFIG), Logger(), bus.publish, bus.subscribe))
    await atom.start()
    clock = {"now": now}
    atom._clock = lambda: clock["now"]
    return atom, bus, clock


async def _candles(atom, first, last, prices=KNOWN, symbol="USTEC"):
    for i in range(first, last + 1):
        await atom._on_candle({"symbol": symbol, "timeframe": "1m", "period_start": T0 + i * 60,
                               "close": prices.get(i, 20000.0), "account_id": "A", "broker": "B"})


async def _news(atom, headline, at, source="test_feed"):
    await atom._on_news({"headline": headline, "source": source, "published_at": at, "timestamp": at,
                         "impact_level": "MEDIUM", "sentiment_score": None, "symbols": []})


def _row(atom, headline):
    return next(r for r in atom._rows if r["headline"] == headline)


# ── ١) التصنيف ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("headline, expected", [
    ("Oil major warns of supply squeeze", ["other"]),                 # «warns» ليست حربًا
    ("Warner Bros shares jump after warning", ["other"]),
    ("War in Ukraine escalates", ["geopolitics"]),
    ("Trade wars resume", ["trade"]),                                 # حربٌ بالاسم لا بالسلاح
    ("Price war among airlines deepens", ["other"]),
    ("Fed's Powell says rate cut possible as inflation cools", ["monetary"]),
    ("Rate-cut hopes fade", ["monetary"]),
    ("Trump threatens new tariffs on China", ["trade"]),
    ("Nvidia earnings beat; guidance raised", ["companies"]),
    ("Nonfarm payrolls rise 150K, unemployment steady", ["data"]),
    ("Mexico stocks lower at close of trade; S&P/BMV IPC down 1.01%", ["other"]),
    ("Profit-taking hits tech stocks", ["other"]),
    ("Meta Platforms unveils new headset", ["companies"]),
    ("Metaverse land prices slump", ["other"]),
    # عناوين حقيقيّة من قاعدة الجسر (٢٠٢٦-١٠-٠٨):
    ("Stocks Down Pre-Bell Amid Renewed Middle East Concerns; Traders Parse Fed Meeting Minutes",
     ["monetary", "geopolitics"]),
    ("Inflation on many everyday items was entirely due to tariffs, NY Fed says", ["monetary", "trade"]),
    ("Gold steadies after nine-week low as Hormuz tensions lift Fed hike bets", ["monetary", "geopolitics"]),
    ("Levi Strauss lifts annual profit outlook on tariff refunds, holiday demand", ["trade", "companies"]),
    ("الفيدرالي يبقي الفائدة دون تغيير", ["monetary"]),
    ("صواريخ على إسرائيل والحرب تتّسع", ["geopolitics"]),
    ("اليورو مقابل الدولار", ["other"]),                                # «أبل» لا تطابق «مقابل»
])
def test_classification(headline, expected):
    assert rules.classify(headline) == expected


def test_war_word_boundary_terms():
    assert "geopolitics" not in rules.matched_terms("Analyst warns; Warner; warrant; awareness")
    assert rules.matched_terms("A new war and old wars")["geopolitics"] == ["war", "wars"]


# ── ٢) الحركة بعد الخبر — أرقام معروفة، ولا نظر إلى المستقبل ───────────────────
@pytest.mark.asyncio
async def test_moves_fill_only_when_their_candle_closes():
    atom, bus, clock = await _atom(now=T0 + 120)
    await _candles(atom, -5, 0)                     # آخر إغلاق عند T0+60
    await _news(atom, "War in Ukraine escalates", T0 + 30)
    row = _row(atom, "War in Ukraine escalates")
    assert row["price_at_news"] == pytest.approx(20000.0)     # إغلاق T0 — آخر ما أُغلق قبل T0+30
    assert row["moves"] == {}
    await _candles(atom, 1, 4)                      # آخر إغلاق T0+300 < T0+330: لم تمرّ الخمس دقائق بعد
    assert "5m" not in row["moves"]
    await _candles(atom, 5, 5)                      # إغلاق T0+360 ≥ T0+330 ⟸ يُعرف سعر T0+330 = إغلاق T0+300
    assert row["moves"]["5m"] == pytest.approx(0.5)
    await _candles(atom, 6, 15)
    assert row["moves"]["15m"] == pytest.approx(-0.5)
    await _candles(atom, 16, 59)                    # إغلاق T0+3600 — بعد الخبر بـ59.5 د: لم تمرّ الستّون
    assert "60m" not in row["moves"]
    assert row["no_price"] == []
    await _candles(atom, 60, 60)
    assert row["moves"]["60m"] == pytest.approx(2.0)
    assert not atom._pending(row)


@pytest.mark.asyncio
async def test_late_news_measured_from_past_candles_only():
    atom, bus, clock = await _atom(now=T0 + 4300)
    await _candles(atom, -5, 70)                    # الخبر يصل بعد ساعةٍ وزيادة من نشره (تأخّر الجسر)
    assert atom._closes[-1][0] <= clock["now"]      # كلّ ما في المخزون أُغلق قبل وصول الخبر
    await _news(atom, "Nvidia earnings beat", T0 + 30)
    row = _row(atom, "Nvidia earnings beat")
    assert row["moves"] == {"5m": pytest.approx(0.5), "15m": pytest.approx(-0.5), "60m": pytest.approx(2.0)}


@pytest.mark.asyncio
async def test_gap_gives_no_price_not_a_number():
    atom, bus, clock = await _atom(now=T0 + 2000)
    await _candles(atom, -5, 0)
    await _news(atom, "Fed holds rates", T0 + 30)
    await _candles(atom, 20, 25)                    # انقطاع 19 دقيقة: آخر إغلاقٍ قبل T0+330 هو T0+60
    row = _row(atom, "Fed holds rates")
    assert row["price_at_news"] == pytest.approx(20000.0)
    assert row["no_price"] == ["5m", "15m"] and "60m" not in row["moves"]
    # خبرٌ أقدم من مخزون الشموع كلّه: لا سعر عنده، فلا حركة بعده.
    await _news(atom, "Old tariff story", T0 - 7200)
    old = _row(atom, "Old tariff story")
    assert old["price_at_news"] is None and old["no_price"] == ["5m", "15m", "60m"]


@pytest.mark.asyncio
async def test_duplicate_candles_from_second_account_are_ignored():
    atom, bus, clock = await _atom()
    await _candles(atom, 0, 2)
    await _candles(atom, 0, 2)
    await _candles(atom, 0, 2, symbol="US500")     # رمزٌ آخر لا يُخزَّن
    assert len(atom._closes) == 3 and atom._old_candles == 3


# ── ٣) الحمولة ──────────────────────────────────────────────────────────
def _walk(value, path="facts"):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield ("key", key, path)
            yield from _walk(inner, "%s.%s" % (path, key))
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner, path)
    elif isinstance(value, str):
        yield ("text", value, path)


@pytest.mark.asyncio
async def test_payload_counts_minutes_summary_and_no_forbidden_fields():
    # الخبر الجيوسياسيّ عند T0+90: سعره إغلاق T0+60 (i=0) = 20000 · بعد 5 د إغلاق T0+360 (i=5) = 20050 (+0.25٪)
    # · بعد 15 د إغلاق T0+960 (i=15) = 19800 (−1٪) · وآخر إغلاقٍ T0+2820 (i=46) = 19900 (−0.5٪ حتّى الآن).
    atom, bus, clock = await _atom(now=T0 + 2850)
    await _candles(atom, -5, 46, prices={5: 20050.0, 15: 19800.0, 46: 19900.0})
    await _news(atom, "Fed's Powell says inflation cools", T0 - 25 * 3600)      # خارج الأربع والعشرين
    await _news(atom, "Fed minutes show debate on rate path", T0 + 30)
    await _news(atom, "Missiles hit tanker near Hormuz", T0 + 90)
    await _news(atom, "Apple revenue tops estimates", T0 + 150)
    payload = bus.payloads("knowledge.news.state")[-1]
    assert set(payload) == {"id", "status", "symbol", "facts", "computed_at", "summary_ar", "source"}
    assert payload["status"] == "ok" and payload["symbol"] == "USTEC"
    facts = payload["facts"]
    assert facts["news_24h"] == 3 and facts["monetary_24h"] == 1 and facts["geopolitics_24h"] == 1
    assert facts["companies_24h"] == 1 and facts["trade_24h"] == 0 and facts["other_24h"] == 0
    assert facts["last_geopolitics_minutes_ago"] == 46                 # (2850 − 90) / 60
    assert facts["last_news_minutes_ago"] == 45
    geo = facts["latest_by_category"]["geopolitics"][0]
    assert geo["price_at_news"] == pytest.approx(20000.0)
    assert geo["move_5m_pct"] == pytest.approx(0.25) and geo["move_15m_pct"] == pytest.approx(-1.0)
    assert geo["move_60m_pct"] is None and geo["source"] == "test_feed"
    assert geo["move_since_pct"] == pytest.approx(-0.5) and geo["since_minutes"] == pytest.approx(45.5)
    assert facts["last_geopolitics_move_since_pct"] == pytest.approx(-0.5)
    assert len(facts["latest_by_category"]["monetary"]) == 2          # الأحدث أوّلًا، ولو خارج اليوم
    # أوّل عشر حقائق مفردة (يختمها دفتر البطاقات 465 بأسمائها).
    first = list(facts.items())[:10]
    assert all(not isinstance(v, (list, dict)) and (not isinstance(v, str) or len(v) <= 24) for _, v in first)
    assert [k for k, _ in first][:2] == ["news_24h", "monetary_24h"]
    summary = payload["summary_ar"]
    assert "نقديّ 1" in summary and "جيوسياسيّ 1 (قبل 46د" in summary and "شركات 1" in summary
    assert "الناسداك −1.00٪ بعد 15د" in summary
    assert "لا فهمٌ للمضمون" in summary and "لا فهم" in facts["limit_ar"]
    json.dumps(payload, ensure_ascii=False)
    for kind, value, path in _walk(payload):
        low = value.lower()
        if kind == "key":
            assert low not in FORBIDDEN_KEYS and not any(w in low for w in FORBIDDEN_KEYS), path
        assert not any(w in low.split() or w in low for w in FORBIDDEN_WORDS), (path, value)


@pytest.mark.asyncio
async def test_mean_abs_15m_per_category_with_n():
    atom, bus, clock = await _atom(now=T0 + 7200)
    prices = {-1: 20000.0, 14: 19900.0, 29: 20000.0, 44: 20200.0}
    await _candles(atom, -5, 60, prices=prices)
    await _news(atom, "Fed speaker one", T0 + 30)            # 20000 ⟶ 19900 = −0.5٪
    await _news(atom, "Fed speaker two", T0 + 30 + 1800)     # 20000 (T0+1800) ⟶ 20200 (T0+2700) = +1٪
    await _news(atom, "Nonfarm payrolls jump", T0 + 30)      # بيانات: |−0.5|
    await atom._on_pulse({"official_time": T0 + 7200})
    facts = bus.payloads("knowledge.news.state")[-1]["facts"]
    means = facts["abs_move_15m_mean_pct"]
    assert means["monetary"] == {"mean": pytest.approx(0.75), "n": 2}
    assert means["data"] == {"mean": pytest.approx(0.5), "n": 1}
    assert means["geopolitics"] == {"mean": None, "n": 0}


# ── ٤) المصدر الغائب والمدخل الفاسد لا يكسران ─────────────────────────────
@pytest.mark.asyncio
async def test_missing_sources_and_bad_input():
    atom, bus, clock = await _atom()
    await atom._on_pulse({"official_time": T0})
    first = bus.payloads("knowledge.news.state")[-1]
    assert first["status"] == "no_news_yet" and first["facts"]["news_24h"] == 0
    assert "لم يصل خبرٌ بعد" in first["summary_ar"]
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED and "لم يصل خبرٌ بعد" in health.message
    await atom._on_news({"headline": "", "published_at": T0})
    await atom._on_news({"headline": "No time on this one"})
    await atom._on_candle({"symbol": "USTEC", "timeframe": "1m", "period_start": T0, "close": None})
    assert atom._rejected == {"no_headline": 1, "no_published_at": 1, "bad_candle": 1}
    await _news(atom, "Iran talks stall", T0 - 60)            # لا شموع أصلًا ⟸ الحركة معلّقة لا مخترعة
    facts = bus.payloads("knowledge.news.state")[-1]["facts"]
    view = facts["latest_by_category"]["geopolitics"][0]
    assert view["price_at_news"] is None and view["move_5m_pct"] is None and facts["pending_moves"] == 1
    health = await atom.health_check()
    assert health.state == HealthState.DEGRADED and "لا شموع دقيقة" in health.message
    await _candles(atom, -2, 0)
    health = await atom.health_check()
    assert health.state == HealthState.HEALTHY and "أخبار محفوظة=1" in health.message


# ── ٥) الحفظ والاستعادة ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_snapshot_restore_round_trip_and_dedup_after_restart():
    atom, bus, clock = await _atom(now=T0 + 1200)
    await _candles(atom, -5, 15)
    await _news(atom, "War in Ukraine escalates", T0 + 30)
    await _news(atom, "Fed holds rates", T0 + 30)
    state = json.loads(json.dumps(await atom.snapshot()))
    again, bus2, clock2 = await _atom(now=T0 + 1200)
    await again.restore(state)
    assert [r["headline"] for r in again._rows] == ["War in Ukraine escalates", "Fed holds rates"]
    assert _row(again, "Fed holds rates")["moves"] == {"5m": pytest.approx(0.5), "15m": pytest.approx(-0.5)}
    assert again._abs_mean["monetary"] == [pytest.approx(0.5), 1] and len(again._closes) == 21
    await _news(again, "War in Ukraine escalates", T0 + 30)          # بداية 616 الدافئة تعيده بعد الإقلاع
    assert len(again._rows) == 2 and again._duplicates == 1
    await _candles(again, 16, 60)                                   # ما علّق قبل الإقلاع يُملأ بعده
    assert _row(again, "Fed holds rates")["moves"]["60m"] == pytest.approx(2.0)
    assert again._abs_mean["monetary"][1] == 1                      # الخمس عشرة لا تُعدّ مرّتين


@pytest.mark.asyncio
async def test_keeps_last_200_and_survives_garbage_state():
    atom, bus, clock = await _atom(now=T0 + 300 * 60)
    for i in range(205):
        await _news(atom, "Headline number %d" % i, T0 + i * 60)
    assert len(atom._rows) == 200 and atom._rows[0]["headline"] == "Headline number 5"
    facts = bus.payloads("knowledge.news.state")[-1]["facts"]
    assert facts["stored_news"] == 200 and facts["counts_24h_complete"] is False
    other, _, _ = await _atom()
    await other.restore({"rows": [None, {"headline": "x"}, {"time": T0}], "closes": [[1, "a"], "z"],
                         "abs_mean": {"monetary": "bad"}, "seen": [3]})
    assert len(other._rows) == 0 and other._rejected["bad_restored_row"] == 3 and other._closes == []
    await other.restore("not a dict")


# ── ٦) البيان ───────────────────────────────────────────────────────────
def test_manifest_contract():
    manifest = yaml.safe_load((FOLDER / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["id"] == 120 and manifest["name"] == "News Category Knowledge"
    assert manifest["version"] == m.ATOM_VERSION
    assert manifest["publishes"] == ["knowledge.news.state"]
    assert set(manifest["subscribes"]) == {"market_data.news_received", "market_data.candle_closed", "SYS_5MIN"}
    assert set(manifest["config"]) == set(manifest["config_schema"]["properties"]) == set(CONFIG)
    assert manifest["config_schema"]["additionalProperties"] is False
    assert manifest["metadata"]["name_ar"] and manifest["metadata"]["max_idle_s"] > 0
