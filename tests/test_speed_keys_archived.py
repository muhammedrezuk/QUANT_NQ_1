# -*- coding: utf-8 -*-
"""٢٠٢٦-١٠-٠٩ (ختم المالك «NQ» — إلغاء مفاتيح السرعة إلى الأرشيف): حارس السلوك بعد الإلغاء.

أمر المالك: «مفتاح السرعة… نلغيه، ما له شغل» · «الغيه حتّى من اللوحة، ما بدّي شي ميّت يبقى» · «الغيه على
أرشيف». أُرشفت المفاتيح الأربعة (السرعة · الأفق · الحدود · الرئيسي) ومعها ظلّ «شخصيّة الأفق»، فالعقد الآن:

    · لا ملفّ حيّ يستورد `shared.analysis_speed` ولا `shared.horizon_profile` — وكلاهما غائب عن `shared/`.
    · كلّ نافذة = رقمها المكتوب في مانيفست ذرّتها أو في الكود، وكلّ عتبة = رقمها المخزَّن — حتّى وصفوف
      المفاتيح المعتمدة باقية في سجلّ المعايير (هنا بقيمٍ متطرّفة كانت تضرب النوافذ ×5 والعتبات ×2).
    · رقما البطاقة 414 كما كانا: «متوسّط 20» من 151 (`ema_slow_value`) و«المدى على 14» من 153 (`atr_14`).
    · اللوحة لا تعرض صفًّا بلا قارئ، ولا عيار «نطاقيّ» بقي، والعيارات كلّها عامّة.

العزل: سجلّ الجلسة المؤقّت (conftest) أو سجلّ `tmp_path` — لا لمس للحيّ.
"""
from __future__ import annotations

import asyncio
import importlib.util
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml

from build_registry.paths import RegistryAtomRoot
from core.contracts.atom import AtomContext

ROOT = Path(__file__).resolve().parents[1]
ATOM_ROOT = RegistryAtomRoot(ROOT)
ARCHIVED_NAMES = ("ANALYSIS_SPEED", "TRADING_HORIZON", "QUALITY_BAR", "MASTER_KEY",
                  "HORIZON_PROFILE_ACTIVE")
EXTREME_ROWS = (("MASTER_KEY", 1.0), ("ANALYSIS_SPEED", 1.0), ("TRADING_HORIZON", 1.0),
                ("QUALITY_BAR", 100.0), ("HORIZON_PROFILE_ACTIVE", 1.0))


class _Log:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def critical(self, *a, **k): pass


class _Bus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    def subscribe(self, name, handler) -> None:
        pass

    async def publish(self, name, payload) -> None:
        self.published.append((name, payload))


def _seed_archived_rows(path: Path | None = None) -> None:
    from shared.parameter_registry import ParameterRegistry, refresh_gate
    registry = ParameterRegistry(path) if path is not None else ParameterRegistry()
    with registry._lock, registry._connect() as conn:  # noqa: SLF001
        for name, value in EXTREME_ROWS:
            conn.execute(
                """INSERT OR REPLACE INTO parameters(name,scope,value,source,status,version,
                   effective_from,approved_by,approved_at,governs,declared_at)
                   VALUES(?,'global',?,'OWNER','APPROVED',1,1.0,'nq-test',1.0,'archived','archived')""",
                (name, value))
        conn.commit()
    refresh_gate()


def _atom_dir(atom_id: int) -> Path:
    return next(ATOM_ROOT.glob(f"{atom_id}_*"))


def _manifest_config(atom_id: int) -> dict[str, Any]:
    data = yaml.safe_load((_atom_dir(atom_id) / "manifest.yaml").read_text(encoding="utf-8"))
    return dict(data.get("config") or {})


def _load(atom_id: int):
    spec = importlib.util.spec_from_file_location(
        "_speed_archive_atom_%d" % atom_id, _atom_dir(atom_id) / "atom.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _candle(index: int, timeframe: str = "5m") -> dict[str, Any]:
    close = 100.0 + (index % 7) * 0.9 - (index % 3) * 0.4 + index * 0.05
    rng = 1.0 + (index % 5) * 0.3
    return {"symbol": "NQ", "account_id": "52992818", "timeframe": timeframe,
            "period_start": float(index * 300), "open": close, "high": close + rng / 2.0,
            "low": close - rng / 2.0, "close": close, "volume": 10.0 + index % 4,
            "tick_count": 10.0 + index % 4}


async def _first_ok(atom_id: int, candles: int = 140) -> tuple[int | None, list[dict[str, Any]]]:
    module = _load(atom_id)
    bus = _Bus()
    atom = module.Atom()
    await atom.initialize(AtomContext(atom_id=atom_id, config=_manifest_config(atom_id),
                                      logger=_Log(), publish=bus.publish,
                                      subscribe=bus.subscribe))
    await atom.start()
    first = None
    for index in range(1, candles + 1):
        before = len(bus.published)
        await atom._on_candle(_candle(index))
        mine = [p for n, p in bus.published[before:] if n == module.EVENT_OUT]
        if first is None and mine and mine[-1].get("status") == "ok":
            first = index
    await atom.stop()
    return first, [p for n, p in bus.published if n == module.EVENT_OUT]


def _expected_first_ok(atom_id: int) -> int:
    cfg = _manifest_config(atom_id)
    if atom_id == 152:
        return max(cfg["roc_period"], cfg["impulse_window"], cfg["persistence_window"],
                   cfg["min_candles"]) + 1
    if atom_id in (151, 153, 154, 155):
        return int(cfg["min_candles"])
    if atom_id in (162, 163):
        return int(cfg["baseline_window"]) + 1
    if atom_id == 164:
        return int(cfg["baseline_window"])
    if atom_id == 201:
        return int(cfg["lookback"]) * 2 + 1
    raise AssertionError(atom_id)


def test_no_live_file_imports_the_archived_modules():
    assert not (ROOT / "shared" / "analysis_speed.py").exists()
    assert not (ROOT / "shared" / "horizon_profile.py").exists()
    pattern = re.compile(r"^\s*(from|import)\s+shared(\.|\s+import\s+)\s*(analysis_speed|horizon_profile)\b",
                         re.M)
    offenders = []
    me = Path(__file__).resolve()
    for folder in ("atoms", "shared", "governance", "core", "backtest", "hot", "tests", "engine"):
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "built" in path.parts or "__pycache__" in path.parts or path.resolve() == me:
                continue
            if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_dials_carry_no_archived_key_and_none_is_scoped():
    from shared.decision_dials import DIALS
    assert not set(ARCHIVED_NAMES) & set(DIALS)
    assert not [name for name, spec in DIALS.items() if spec.get("scoped")]
    assert not [name for name, spec in DIALS.items() if str(spec.get("atom")) == "150"]


def test_apply_command_is_global_even_with_account_and_symbol(tmp_path: Path):
    from shared.decision_dials import apply_command
    from shared.parameter_registry import ParameterRegistry
    registry = ParameterRegistry(tmp_path / "params.db")
    applied = apply_command({"name": "RISK_DIAL", "value": 40.0, "command_id": "c-1",
                             "operator": "nq", "approved_at": 1.0, "account_id": "52992818",
                             "symbol": "XAUUSD", "confirm": True},
                            atom_id="581", registry=registry)
    assert applied is not None and applied["scope"] == "global" and applied["approved"] is True
    assert registry.get("RISK_DIAL", "52992818\x1fXAUUSD") is None


@pytest.mark.parametrize("atom_id", [151, 152, 153, 154, 155, 162, 163, 164, 201])
def test_candle_windows_are_the_manifest_numbers_even_with_archived_rows(atom_id: int):
    _seed_archived_rows()
    first, events = asyncio.run(_first_ok(atom_id))
    assert first == _expected_first_ok(atom_id), (atom_id, first, _expected_first_ok(atom_id))
    assert not any("analysis_speed" in p or "limits_factor" in p for p in events)


def test_trend_mean_20_for_card_414_is_the_plain_ema_and_available_at_manifest_count():
    _seed_archived_rows()
    cfg = _manifest_config(151)
    module = _load(151)
    bus = _Bus()
    atom = module.Atom()

    async def run() -> None:
        await atom.initialize(AtomContext(atom_id=151, config=cfg, logger=_Log(),
                                          publish=bus.publish, subscribe=bus.subscribe))
        await atom.start()
        for index in range(1, 61):
            await atom._on_candle(_candle(index, "1h"))
        await atom.stop()

    asyncio.run(run())
    closes = [_candle(index, "1h")["close"] for index in range(1, 61)]
    alpha = 2.0 / (cfg["ema_slow"] + 1.0)
    ema = closes[0]
    for close in closes[1:]:
        ema = alpha * close + (1.0 - alpha) * ema
    oks = [p for n, p in bus.published if n == module.EVENT_OUT and p.get("status") == "ok"]
    assert cfg["ema_slow"] == 20
    assert oks and abs(oks[-1]["metadata"]["ema_slow_value"] - ema) < 1e-9
    assert oks[0]["metadata"]["candles"] == cfg["min_candles"]


def test_range_on_14_for_card_414_and_the_manifest_atr_window():
    _seed_archived_rows()
    cfg = _manifest_config(153)
    first, events = asyncio.run(_first_ok(153, candles=60))
    trs = []
    previous = None
    for index in range(1, 61):
        candle = _candle(index)
        high, low = candle["high"], candle["low"]
        trs.append(high - low if previous is None
                   else max(high - low, abs(high - previous), abs(low - previous)))
        previous = candle["close"]
    meta = events[-1]["metadata"]
    assert abs(meta["atr_14"] - round(sum(trs[-14:]) / 14, 5)) < 1e-9
    window = cfg["atr_window"]
    assert abs(meta["atr"] - round(sum(trs[-window:]) / window, 5)) < 1e-9


def test_structure_phase_ceiling_is_the_written_four():
    module = _load(208)
    atom = module.Atom()
    assert module._ESTABLISHED_MAX == 4
    assert atom._phase("uptrend", 4) == module.PHASE_ESTABLISHED
    assert atom._phase("uptrend", 5) == module.PHASE_EXTENDED
    assert not hasattr(module, "limits_factor")


@pytest.mark.asyncio
async def test_tick_kernel_windows_and_thresholds_are_the_written_numbers(tmp_path, monkeypatch):
    import clock
    from shared.live_analysis import LONG_WINDOW, RECENT_WINDOW, SESSION_WINDOW, LiveAnalyzerKernel
    assert (RECENT_WINDOW, LONG_WINDOW, SESSION_WINDOW) == (12, 24, 32)
    monkeypatch.setenv("QUANT_ANALYSIS_SETTINGS_DB", str(tmp_path / "analysis_settings.db"))
    _seed_archived_rows()
    published: list[dict[str, Any]] = []

    class _Context:
        config: dict[str, Any] = {}

        def subscribe(self, name, handler) -> None:
            pass

        async def publish(self, name, payload) -> None:
            published.append(payload)

    kernel = LiveAnalyzerKernel("trend", "analysis.trend.state")
    await kernel.initialize(_Context())
    kernel.start()
    base = clock.now()
    for index in range(13):
        await kernel.on_tick({"account_id": "A", "broker": "BR", "symbol": "NQ",
                              "bid": 20000 + index, "ask": 20000.25 + index,
                              "price": 20000.125 + index, "volume": 5,
                              "timestamp": base + index * 0.01})
    last = published[-1]
    assert last["data_completeness"] == pytest.approx(12 / 24 * 100.0)
    assert last["required_depth"] == 60.0 and last["confidence_threshold"] == 60.0
    assert last["stale_after_effective_s"] == 5.0
    assert "analysis_speed" not in last and "limits_factor" not in last


def _load_server():
    spec = importlib.util.spec_from_file_location("speed_archive_server", ROOT / "governance" / "server.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_panel_endpoints_do_not_show_rows_without_a_reader(tmp_path: Path, monkeypatch):
    from shared.decision_dials import declare
    from shared.parameter_registry import DECLARED, ParameterRegistry
    db = tmp_path / "params.db"
    declare(ParameterRegistry(db))
    _seed_archived_rows(db)
    server = _load_server()
    names = {row["name"] for row in server.parameters_rows(db)["parameters"]}
    assert set(DECLARED) <= names and not set(ARCHIVED_NAMES) & names
    with sqlite3.connect(db) as conn:
        stored = {row[0] for row in conn.execute("SELECT name FROM parameters")}
    assert set(ARCHIVED_NAMES) <= stored

    from backtest import full_panel
    monkeypatch.setattr(full_panel, "SETTINGS_DB", db)
    monkeypatch.setattr(full_panel, "TICKS_DB", tmp_path / "absent_ticks.db")
    monkeypatch.setattr(full_panel, "HISTORY_DB", tmp_path / "absent_history.db")
    listed = {row["name"] for row in full_panel.catalog()["parameters"]}
    assert listed and not set(ARCHIVED_NAMES) & listed
