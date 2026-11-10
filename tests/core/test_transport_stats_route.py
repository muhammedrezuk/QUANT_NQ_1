"""`/api/transport-stats` — كشف عدّادات طبقة النقل.

٢٠٢٦-٠٩-٠٩: الإسقاط في صناديق عمّال طبقة النقل **معدود فعلًا**
(`transport/ownership.py` ⟵ `self.dropped += 1`) لكنّه كان يخرج من
`transport_stats()` وحدها، ولا يناديها أيّ مسار — فقط أداة قياس. النتيجة
المقيسة على نواة حيّة: `feed.ctrader.raw` نُشر ٩٥٨ ومشتركاه اثنان
فالمتوقَّع ١٬٩١٦ تسليمة، والمسجَّل ٣٨٣ — و`dropped` في `/api/bus-stats`
صفر، لأنّه ليس العدّاد الذي يُسقِط.
"""

from __future__ import annotations

import pytest

# ⛔ `starlette.testclient` يستورد `httpx` عند الاستيراد لا عند الاستعمال،
# فغيابه كان يُسقط **جمع** pytest كلّه لا هذا الملفّ وحده:
#     Interrupted: 1 error during collection
# أي أنّ اختبارًا واحدًا في بيئة ناقصة كان يحجب المجموعة عن كلّ جلسة.
# التخطّي هنا يبقي الحارس فعّالًا حيث تتوفّر الحزمة، ويُعلن سببه حيث لا تتوفّر.
pytest.importorskip(
    "httpx", reason="starlette.testclient يتطلّب httpx — يُتخطّى ولا يُسقط الجمع")

from fastapi.testclient import TestClient  # noqa: E402

from core.api.app import create_app  # noqa: E402
from core.event_bus import EventBus
from core.journal import Journal
from core.metrics import Metrics
from core.registry import Registry


def _client(bus) -> TestClient:  # noqa: ANN001
    app = create_app(Registry(), bus, Metrics(), Journal())
    return TestClient(app)


class _BusWithTransport(EventBus):
    def transport_stats(self) -> dict:
        return {"published": 7, "runtime": {"workers": [{"dropped": 3, "coalesced": 1}]}}


def test_transport_stats_is_exposed_when_the_layer_is_active() -> None:
    response = _client(_BusWithTransport()).get("/api/transport-stats")
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["workers"][0]["dropped"] == 3, (
        "عدّاد الإسقاط في عمّال النقل لم يصل إلى المسار — وهو العمى نفسه"
    )


def test_plain_bus_returns_empty_instead_of_failing() -> None:
    """بلا طبقة نقل: ردٌّ فارغ صريح — لا خطأ ولا رقم مخترَع."""
    response = _client(EventBus()).get("/api/transport-stats")
    assert response.status_code == 200
    assert response.json() == {}


def test_bus_stats_and_transport_stats_are_different_surfaces() -> None:
    """المسارَان لا يخلطان: أحدهما عدّادات الناقل، والآخر عدّادات العمّال.

    خلطهما هو ما جعل `dropped=0` يبدو برهانًا على عدم الفقد.
    """
    client = _client(_BusWithTransport())
    bus_stats = client.get("/api/bus-stats").json()
    transport = client.get("/api/transport-stats").json()
    assert "runtime" not in bus_stats
    assert "published" in bus_stats and isinstance(bus_stats["published"], dict)
    assert "runtime" in transport
