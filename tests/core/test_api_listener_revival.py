"""حارس مستمع النواة: فشل `accept` واحد لا يجوز أن يقتل المنفذ.

المقيس 2026-09-09 الساعة 16:10:48: `WinError 64` واحد أغلق الاستماع على
8010 نهائيًّا — CPython يغلق مقبس الاستماع نفسه داخل `except OSError` في
`asyncio/proactor_events.py` ثم يكتفي بـ`call_exception_handler`، فلا
استثناء يصل إلى `serve()` ولا حارس يرى شيئًا. والذرّات 453 و581 و406
و622 واصلت النشر والتداول بعده بدقائق: **النظام يتداول والمالك أعمى.**
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from governance.scripts.run_core import _ACCEPT_DEAD_MESSAGE, _ApiSupervisor


class _FakeServer:
    """يحاكي عقد `uvicorn.Server` الذي يعتمده المشرف: `serve()` و`should_exit`."""

    created: list["_FakeServer"] = []

    def __init__(self, config) -> None:  # noqa: ANN001
        self.config = config
        self.should_exit = False
        _FakeServer.created.append(self)

    async def serve(self) -> None:
        while not self.should_exit:
            await asyncio.sleep(0.005)


@pytest.fixture()
def fake_uvicorn(monkeypatch):  # noqa: ANN001, ANN201
    import uvicorn

    _FakeServer.created = []
    monkeypatch.setattr(uvicorn, "Server", _FakeServer)
    monkeypatch.setattr(_ApiSupervisor, "_BACKOFF_S", (0.02,))
    return _FakeServer


@pytest.mark.asyncio
async def test_dead_accept_loop_revives_the_listener(fake_uvicorn) -> None:  # noqa: ANN001
    supervisor = _ApiSupervisor(object(), "127.0.0.1", 8010, logging.getLogger("test.revival"))
    supervisor.install_guard()
    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)
    assert len(fake_uvicorn.created) == 1

    # هذا حرفيًّا ما يفعله asyncio حين تموت حلقة القبول — لا استثناء، بلاغ فقط.
    asyncio.get_running_loop().call_exception_handler(
        {"message": _ACCEPT_DEAD_MESSAGE, "exception": OSError(64, "network name no longer available")}
    )
    await asyncio.sleep(0.25)

    assert supervisor.revivals == 1, "لم يُستأنف المستمع بعد موت حلقة القبول"
    assert len(fake_uvicorn.created) == 2, "لم يُعَد بناء الخادم على مقبس جديد"
    assert fake_uvicorn.created[0].should_exit, "بقي كائن الخادم القديم معلّقًا فوق مقبس مغلق"

    supervisor.should_exit = True
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_unrelated_asyncio_errors_do_not_rebind_the_listener(fake_uvicorn) -> None:  # noqa: ANN001
    """الحارس يعترض بلاغ القبول وحده — لا يبتلع غيره ولا يعيد الربط لأجله."""
    supervisor = _ApiSupervisor(object(), "127.0.0.1", 8010, logging.getLogger("test.revival"))
    supervisor.install_guard()
    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    asyncio.get_running_loop().call_exception_handler(
        {"message": "Task exception was never retrieved", "exception": ValueError("شيء آخر")}
    )
    await asyncio.sleep(0.15)

    assert supervisor.revivals == 0
    assert len(fake_uvicorn.created) == 1

    supervisor.should_exit = True
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_orderly_shutdown_stops_the_supervisor(fake_uvicorn) -> None:  # noqa: ANN001
    """عقد المُنادي محفوظ: `should_exit = True` ثم `await task` ينهي كل شيء."""
    supervisor = _ApiSupervisor(object(), "127.0.0.1", 8010, logging.getLogger("test.revival"))
    supervisor.install_guard()
    task = asyncio.create_task(supervisor.run())
    await asyncio.sleep(0.05)

    supervisor.should_exit = True
    await asyncio.wait_for(task, timeout=2)

    assert fake_uvicorn.created[-1].should_exit, "لم يُنزَل الخادم عند الإيقاف المرتَّب"
    assert supervisor.revivals == 0, "إيقاف مرتَّب حُسب استئنافًا"
