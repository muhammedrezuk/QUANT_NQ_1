import json
import pytest
from tests.learning_test_support import make_atom, manifest_config, validated_tick


def candle(i, price=100.0, **_):
    """٢٠٢٦-١٠-١٢: النماذج على الشموع — شمعة 5د مغلقة بهويّة التِّكّة المصدّقة نفسها."""
    t = validated_tick(i, price=price)
    return {"account_id": t["account_id"], "broker": t["broker"], "symbol": t["symbol"], "timeframe": "5m",
            "close": price, "period_start": 1_790_000_000 + i * 300, "cycle_id": "c%d" % i}

@pytest.mark.asyncio
async def test_live_tick_contract_and_snapshot():
    module, atom, bus = await make_atom(358, manifest_config(358))
    for i in range(140):
        price = 100.0 + i * 0.02
        await atom._on_tick(candle(i, price=price))
    rows = bus.payloads("probability.hurst.state")
    assert len(rows) == 140
    last = rows[-1]
    assert last["timeframe"] == "5m"
    assert last["analysis_mode"] == "candle"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): حقول الحكم منزوعة؛ «trending» اسم حدثٍ لا جهة فيبقى، ومعه الحقيقة الخام.
    for key in ("direction", "strength", "confidence", "weight", "weight_applied",
                "current_depth", "required_depth", "confidence_threshold",
                "strength_threshold", "ratio", "ready", "analysis_state"):
        assert key not in last, f"حقل حكمٍ ظهر: {key}"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "350" and last["atom_id"] == "358"
    assert last["as_of"] == last["timestamp"]
    assert last["signal"] == "trending", last.get("signal")
    md = last["metadata"]
    assert md["hurst"] > 0.5 and md["count"] == manifest_config(358)["window"], md
    assert last["computed_on"] == md["count"]
    json.dumps(await atom.snapshot(), allow_nan=False)
