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
    module, atom, bus = await make_atom(353, manifest_config(353))
    for i in range(450):
        price = 100.0 + i * 0.03
        await atom._on_tick(candle(i, price=price))
    rows = bus.payloads("probability.breakout.state")
    assert len(rows) == 450
    last = rows[-1]
    assert last["timeframe"] == "5m"
    assert last["analysis_mode"] == "candle"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): حقول الحكم وكلمة الجهة منزوعة، والحقيقة الخام وختمها باقيان.
    for key in ("direction", "strength", "confidence", "weight", "weight_applied",
                "current_depth", "required_depth", "confidence_threshold",
                "strength_threshold", "ratio", "ready", "analysis_state", "signal"):
        assert key not in last, f"حقل حكمٍ ظهر: {key}"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "350" and last["atom_id"] == "353"
    assert last["as_of"] == last["timestamp"]
    md = last["metadata"]
    assert md["upper"] > md["lower"] and md["distance"] > 0, md
    json.dumps(await atom.snapshot(), allow_nan=False)
