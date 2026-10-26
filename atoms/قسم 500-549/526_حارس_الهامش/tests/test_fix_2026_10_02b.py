"""إصلاح ٢٠٢٦-١٠-٠٢ (ب) في 526 (ختم المالك «صلح كامل nq») — ملفٌّ جديد، والقديم لا يُمسّ.

كان الحارس يقدّر الهامش برافعة **الحساب** (1:5000) للمؤشّرات والبتكوين، ويضرب `margin_initial`
في الحجم مباشرةً لليورو والذهب — فمرّت إلى الوسيط 48 أمرًا ردّها `RETCODE_10019` (لا مال)،
ورُدّ اليورو دائمًا. الآن معادلةُ ميتاتريدر لكلّ `calc_mode` بمعدّل هامش الرمز المقيس.
كلّ اختبارٍ هنا يسقط على 1.4.0 وينجح على 1.5.0 (عدا الحرّاس المسمّاة «حارس»).
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("_t526_fix_b", FOLDER / "atom.py")
m = importlib.util.module_from_spec(_spec)
sys.modules["_t526_fix_b"] = m
_spec.loader.exec_module(m)

ACC, BROKER = "52992818", "Raw Trading Ltd"

# مواصفات الجسر الحيّ كما قُرئت ٢٠٢٦-١٠-٠٢ (`symbol_specs_v2` · وضع القراءة فقط).
SPECS = {
    "USTEC": {"calc_mode": 2, "contract_size": 1.0, "margin_initial": 0.0, "margin_maintenance": 0.0,
              "tick_value": 0.01, "tick_size": 0.01, "currency_margin": "USD", "currency_profit": "USD"},
    "US30": {"calc_mode": 2, "contract_size": 1.0, "margin_initial": 0.0, "margin_maintenance": 0.0,
             "tick_value": 0.01, "tick_size": 0.01, "currency_margin": "USD", "currency_profit": "USD"},
    "US500": {"calc_mode": 2, "contract_size": 1.0, "margin_initial": 0.0, "margin_maintenance": 0.0,
              "tick_value": 0.01, "tick_size": 0.01, "currency_margin": "USD", "currency_profit": "USD"},
    "BTCUSD": {"calc_mode": 2, "contract_size": 1.0, "margin_initial": 0.0, "margin_maintenance": 0.0,
               "tick_value": 0.01, "tick_size": 0.01, "currency_margin": "USD", "currency_profit": "USD"},
    "XAUUSD": {"calc_mode": 0, "contract_size": 100.0, "margin_initial": 100.0, "margin_maintenance": 0.0,
               "tick_value": 1.0, "tick_size": 0.01, "currency_margin": "XAU", "currency_profit": "USD"},
    "EURUSD": {"calc_mode": 0, "contract_size": 100000.0, "margin_initial": 100000.0,
               "margin_maintenance": 0.0, "tick_value": 1.0, "tick_size": 1e-05,
               "currency_margin": "EUR", "currency_profit": "USD"},
    "GBPUSD": {"calc_mode": 0, "contract_size": 100000.0, "margin_initial": 100000.0,
               "margin_maintenance": 0.0, "tick_value": 1.0, "tick_size": 1e-05,
               "currency_margin": "GBP", "currency_profit": "USD"},
}

# حالاتٌ حقيقيّة من الجسر (`commands`) والهامش الحرّ قبلها من `portfolio.db` (قراءة فقط):
# (رقم الأمر، الرمز، الحجم، السعر، الهامش الحرّ، ردّ الوسيط)
REAL_CASES = [
    (231, "EURUSD", 0.14, 1.163635, 9608.56, "OK"),
    (2353, "USTEC", 3.5, 30338.05, 1184.44, "OK"),
    (2367, "USTEC", 3.4, 30274.8, 948.07, "OK"),
    (2386, "XAUUSD", 0.11, 4191.4, 787.33, "OK"),
    (2398, "US30", 3.7, 51346.65, 567.06, "RETCODE_10019"),
    (2406, "XAUUSD", 0.01, 4173.035, 434.04, "OK"),
    (2436, "USTEC", 45.4, 30541.75, 695.67, "RETCODE_10019"),
    (2439, "US30", 5.5, 51304.65, 768.41, "RETCODE_10019"),
    (2456, "USTEC", 41.6, 30590.15, 756.63, "RETCODE_10019"),
    (2457, "US30", 6.0, 51239.65, 739.25, "RETCODE_10019"),
    (2458, "USTEC", 8.8, 30520.45, 732.01, "RETCODE_10019"),
    (2461, "USTEC", 17.8, 30524.75, 284.23, "RETCODE_10019"),
    (2463, "USTEC", 8.7, 30528.95, 588.3, "RETCODE_10019"),
    (2464, "USTEC", 35.7, 30572.15, 596.86, "RETCODE_10019"),
    (2465, "USTEC", 40.0, 30557.45, 569.56, "RETCODE_10019"),
    (2466, "US500", 17.8, 7688.15, 603.44, "RETCODE_10019"),
    (2478, "USTEC", 3.6, 30334.75, 268.34, "RETCODE_10019"),
    (2515, "BTCUSD", 0.45, 86263.87, 660.69, "OK"),
    (2518, "BTCUSD", 0.85, 86321.29, 644.69, "OK"),
    (2526, "US500", 0.6, 7729.45, 895.95, "OK"),
    (2527, "US30", 0.6, 51400.4, 718.17, "OK"),
    (2528, "US500", 1.1, 7735.05, 718.53, "OK"),
    (2531, "US30", 0.5, 51401.4, 827.89, "OK"),
]


class _Log:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Bus:
    def __init__(self):
        self.e = []

    def subscribe(self, *a):
        pass

    async def publish(self, name, payload):
        self.e.append((name, payload))

    def last(self):
        return [p for n, p in self.e if n == m.EVENT_OUT][-1]


def _run(coro):
    return asyncio.run(coro)


async def _atom(free_margin, symbol, broker=BROKER, currency="USD", spec=None):
    bus = _Bus()
    atom = m.Atom()
    await atom.initialize(m.AtomContext(526, {"margin_buffer_pct": 0.1}, _Log(),
                                        bus.publish, bus.subscribe))
    await atom.start()
    await atom._on_account({"account_id": ACC, "broker": broker, "leverage": 5000,
                            "currency": currency})
    await atom._on_truth_free_margin({"account_id": ACC, "broker": broker,
                                      "free_margin": free_margin})
    await atom._on_truth_equity({"account_id": ACC, "broker": broker, "equity": free_margin})
    row = {"account_id": ACC, "symbol": symbol, **(spec if spec is not None else SPECS[symbol])}
    await atom._on_specs({"symbols": [row]})
    return atom, bus


async def _order(free_margin, symbol, volume, price, rid="r1", **kw):
    atom, bus = await _atom(free_margin, symbol, **kw)
    await atom._on_order({"request_id": rid, "account_id": ACC, "symbol": symbol,
                          "action": "OPEN", "side": "BUY", "volume": volume,
                          "reference_price": price})
    return bus.last()


def test_audit_case_ustec_31_lots_is_refused_before_the_broker():
    """USTEC 31.2 لوت على 30293.8 والهامش الحرّ 721.91$ (الأمر 2383 — ردّه الوسيط 10019).
    القديم: 31.2×1×30293.8÷5000 = 189$ فيمرّ. الجديد: ×0.005 = 4,725.83$ فيُردّ هنا."""
    out = _run(_order(721.91, "USTEC", 31.2, 30293.8))
    assert out["approved"] is False and out["reason"] == "INSUFFICIENT_FREE_MARGIN", out
    assert abs(out["required_margin"] - 4725.83) < 0.01, out["required_margin"]


def test_gold_margin_matches_the_broker_2_09():
    """الذهب 0.01 لوت على 4172.57: الوسيط حجز 2.09$ (portfolio.db). القديم 1.00$."""
    out = _run(_order(797.26, "XAUUSD", 0.01, 4172.57))
    assert out["approved"] is True, out
    assert abs(out["required_margin"] - 2.09) < 0.01, out["required_margin"]


def test_eurusd_is_no_longer_refused_by_unit_error():
    """اليورو 0.14 لوت: الوسيط حجز 3.26$ (09-10). القديم 0.14×100000 = 14,000$ فيُردّ دائمًا."""
    out = _run(_order(797.26, "EURUSD", 0.14, 1.163635))
    assert out["approved"] is True, out
    assert abs(out["required_margin"] - 3.258) < 0.01, out["required_margin"]


def test_real_broker_verdicts_are_reproduced():
    """كلّ أمرٍ ردّه الوسيط 10019 يتجاوز الهامش الحرّ بالمعادلة الجديدة، وكلّ مقبولٍ يسعه."""
    for cid, symbol, volume, price, free, verdict in REAL_CASES:
        out = _run(_order(free, symbol, volume, price, rid="c%d" % cid))
        required = out["required_margin"]
        assert required is not None, (cid, out)
        if verdict == "OK":
            assert required <= free and out["approved"] is True, (cid, required, free, out["reason"])
        else:
            assert required > free and out["approved"] is False, (cid, required, free)


def test_unmeasured_rate_fails_closed():
    """GBPUSD لم يُتداول قطّ، فلا معدّل مقيس له — يُردّ باسمه لا بتقديرٍ مخترَع."""
    out = _run(_order(797.26, "GBPUSD", 0.01, 1.35))
    assert out["approved"] is False and out["reason"] == "MARGIN_RATE_UNKNOWN", out
    out = _run(_order(797.26, "USTEC", 0.1, 30000.0, broker="Another Broker Ltd"))
    assert out["approved"] is False and out["reason"] == "MARGIN_RATE_UNKNOWN", out


def test_unsupported_calc_mode_fails_closed():
    spec = {**SPECS["USTEC"], "calc_mode": 32}   # SYMBOL_CALC_MODE_EXCH_STOCKS
    out = _run(_order(797.26, "USTEC", 0.1, 30000.0, spec=spec))
    assert out["approved"] is False and out["reason"] == "MARGIN_CALC_MODE_UNSUPPORTED", out


def test_cross_currency_fails_closed():
    """هامشٌ بعملةٍ لا تُحوَّل بسعر الرمز نفسه (لا عملة ربح ولا هامش = عملة الحساب)."""
    out = _run(_order(797.26, "EURUSD", 0.1, 1.16, currency="EUR"))
    assert out["approved"] is True, out   # هامش EUR وحساب EUR ⟸ بلا تحويل
    spec = {**SPECS["EURUSD"], "currency_margin": "EUR", "currency_profit": "JPY"}
    out = _run(_order(797.26, "EURUSD", 0.1, 160.0, spec=spec))
    assert out["approved"] is False and out["reason"] == "MARGIN_PER_VOLUME_MISSING", out


def test_broker_per_volume_figure_wins_when_present():
    """حارس: رقمُ الوسيط نفسه (`OrderCalcMargin` لكلّ لوت) يُقدَّم على أيّ معادلة."""
    spec = {**SPECS["USTEC"], "margin_per_volume": 150.0}
    out = _run(_order(797.26, "USTEC", 2.0, 30000.0, spec=spec))
    assert out["required_margin"] == 300.0 and out["margin_estimated"] is False, out


def test_mt5_formula_table():
    """معادلات ميتاتريدر لكلّ وضع، بمعدّلٍ مُعطى (المرجع: وثائق ENUM_SYMBOL_CALC_MODE)."""
    def per_lot(spec, price, leverage, currency, rate):
        return m.margin_per_lot(spec, price, leverage, currency, rate)

    def near(got, want):
        value, why = got
        return value is not None and abs(value - want) < 1e-9 and why == ""

    base = {"contract_size": 10.0, "tick_value": 2.0, "tick_size": 0.5, "margin_initial": 0.0,
            "currency_margin": "USD", "currency_profit": "USD"}
    # FOREX: ContractSize ÷ Leverage × Rate (بعملة الهامش؛ وتُحوَّل بسعر الرمز إن كانت عملةُ
    # الربح عملةَ الحساب — اليورو والذهب)
    assert near(per_lot({**base, "calc_mode": 0}, 2.0, 100.0, "USD", 1.5), 0.15)
    assert near(per_lot({**base, "calc_mode": 0, "currency_margin": "EUR"}, 2.0, 100.0, "USD", 1.0), 0.2)
    # FOREX: margin_initial إن وُجد يحلّ محلّ حجم العقد
    assert near(per_lot({**base, "calc_mode": 0, "margin_initial": 40.0}, 2.0, 100.0, "USD", 1.0), 0.4)
    # FOREX_NO_LEVERAGE: ContractSize × Rate
    assert near(per_lot({**base, "calc_mode": 5}, 2.0, 100.0, "USD", 0.5), 5.0)
    # FUTURES: InitialMargin × Rate — وبلا هامش ابتدائيّ لا رقم
    assert near(per_lot({**base, "calc_mode": 1, "margin_initial": 300.0}, 2.0, 100.0, "USD", 1.0), 300.0)
    assert per_lot({**base, "calc_mode": 1}, 2.0, 100.0, "USD", 1.0)[0] is None
    # CFD: ContractSize × Price × Rate — بلا رافعة الحساب
    assert near(per_lot({**base, "calc_mode": 2}, 2.0, 100.0, "USD", 0.005), 0.1)
    # CFDINDEX: ContractSize × Price × TickValue ÷ TickSize × Rate
    assert near(per_lot({**base, "calc_mode": 3}, 2.0, 100.0, "USD", 0.1), 8.0)
    # CFDLEVERAGE: ContractSize × Price ÷ Leverage × Rate
    assert near(per_lot({**base, "calc_mode": 4}, 2.0, 100.0, "USD", 1.0), 0.2)
    assert per_lot({**base, "calc_mode": 32}, 2.0, 100.0, "USD", 1.0) == (None, "MARGIN_CALC_MODE_UNSUPPORTED")


def test_management_orders_never_need_margin():
    """حارس: أوامر الإدارة تمرّ بلا هامشٍ جديد كما كانت."""
    async def go():
        atom, bus = await _atom(1.0, "USTEC")
        await atom._on_order({"request_id": "m1", "account_id": ACC, "symbol": "USTEC",
                              "action": "CLOSE", "volume": 50.0, "reference_price": 30000.0})
        return bus.last()
    out = _run(go())
    assert out["approved"] is True and out["reason"] == "MANAGEMENT_NO_NEW_MARGIN", out


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_"):
            _fn()
            print("OK", _name)
    print("526 fix 2026-10-02b: كلّ الاختبارات خضراء")
