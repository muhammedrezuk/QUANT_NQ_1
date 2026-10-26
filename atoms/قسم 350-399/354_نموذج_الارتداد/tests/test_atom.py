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
    module, atom, bus = await make_atom(354, {**manifest_config(354), 'tick_window': 32})  # ١٠-١٢: منطق النموذج بنافذته الأصليّة، مستقلًّا عن عيار ١٠-١٠
    for i in range(70):
        price = 100.0 + i * 0.03 if i < 69 else 100.2
        await atom._on_tick(candle(i, price=price))
    rows = bus.payloads("probability.pullback.state")
    assert len(rows) == 70
    last = rows[-1]
    assert last["timeframe"] == "5m"
    assert last["analysis_mode"] == "candle"
    # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): حقول الحكم وكلمة الجهة منزوعة، والحقيقة الخام وختمها باقيان.
    for key in ("direction", "strength", "confidence", "weight", "weight_applied",
                "current_depth", "required_depth", "confidence_threshold",
                "strength_threshold", "ratio", "ready", "analysis_state", "signal"):
        assert key not in last, f"حقل حكمٍ ظهر: {key}"
    assert last["contract"] == "facts.v1"
    assert last["section_id"] == "350" and last["atom_id"] == "354"
    assert last["as_of"] == last["timestamp"]
    md = last["metadata"]
    assert md["trend"] > 0 and md["deviation"] < 0, md
    json.dumps(await atom.snapshot(), allow_nan=False)
