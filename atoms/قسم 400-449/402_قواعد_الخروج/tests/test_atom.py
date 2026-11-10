import json
import pytest
from tests.learning_test_support import make_atom,manifest_config,validated_tick
@pytest.mark.asyncio
async def test_descriptive_tick_contract():
 module,atom,bus=await make_atom(402,manifest_config(402))
 for i in range(80):
  price=100.0+i*.03
  await atom._on_tick(validated_tick(i,price=price))
 rows=bus.payloads("strategy.invalidation_quality.state");assert len(rows)==80
 card=rows[-1];assert card["timeframe"]=="tick" and card["analysis_mode"]=="live_tick"
 assert str(card.get("signal")).upper() not in ("BUY","SELL","ENTRY","EXIT","CLOSE")
 # ٢٠٢٦-١٠-٠٧ (عقد الحقائق، ختم المالك «NQ»): حقول الحكم منزوعة؛ يبقى اسم الحدث والحقيقة الوصفيّة وختم العقد.
 for key in ("direction","strength","confidence","current_depth","required_depth","weight","weight_applied","ratio","ready","state"):
  assert key not in card,f"حقل حكمٍ ظهر: {key}"
 assert card["contract"]=="facts.v1" and card["section_id"]=="400" and card["atom_id"]=="402"
 assert card["as_of"]==card["timestamp"] and card["signal"]=="strategic_hypothesis_health"
 md=card["metadata"]
 assert 0<=md["hypothesis_health"]<=100 and 0<=md["invalidation_pressure"]<=100,md
 assert abs(md["hypothesis_health"]+md["invalidation_pressure"]-100)<1e-6,md
 json.dumps(await atom.snapshot(),allow_nan=False)
