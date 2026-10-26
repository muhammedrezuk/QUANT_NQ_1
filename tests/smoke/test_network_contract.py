from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: str) -> dict:
    data = yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}
    assert isinstance(data, dict), path
    return data


def test_forex_api_binding_contract() -> None:
    cfg = load_yaml("config/core_forex.yaml")
    assert cfg["api"]["enable_api"] is True
    assert cfg["api"]["host"] == "0.0.0.0"
    assert cfg["api"]["port"] == 8010
    assert cfg["secrets"]["enabled"] is True
    assert cfg["secrets"]["allow_prompt"] is False
    assert cfg["secrets"]["vault_path"] == "../runtime/secrets.enc"


# ٢٠٢٦-٠٩-٠٧ (قرار المالك): حُذفت شجرة الكريبتو — مشروع مستقلّ على
# جهاز آخر. الاختبارات التي تحرسها زالت معها؛ ما بقي يحرس الفوركس.


def test_generic_core_stays_local() -> None:
    cfg = load_yaml("config/core.yaml")
    assert cfg["api"]["host"] == "127.0.0.1"
    assert cfg["api"]["port"] == 8010


def test_public_launchers_run_network_preflight() -> None:
    # ٢٠٢٦-٠٩-٠٧ — `run_crypto.py` حُذف مع شجرة الكريبتو بقرار المالك.
    for path, market in (("scripts/run_forex.py", "forex"),):
        source = (ROOT / path).read_text(encoding="utf-8")
        assert "validate_market" in source, path
        assert f'validate_market("{market}")' in source, path


def test_official_launch_buttons_are_market_specific() -> None:
    # ٢٠٢٦-٠٩-٠٧ (قرار المالك): سوق واحد — زرّ واحد.
    buttons = {"أزرار التشغيل/تشغيل الفوركس الموحد.bat": "forex"}
    for path, market in buttons.items():
        text = (ROOT / path).read_text(encoding="utf-8")
        assert f"scripts\\launch_market.py --market {market}" in text
        assert "--both" not in text
        assert "launch_unified.py" not in text
        assert "governance\\app.py" not in text


def test_hub_loopback_default_and_internal_backend_isolation() -> None:
    text = (ROOT / "governance/unified_hub.py").read_text(encoding="utf-8")
    # ٢٠٢٦-١٠-٠٢ (ختم المالك «صلح كامل nq»): المحور بلا هويّة كان يُربط على 0.0.0.0 افتراضًا
    # فيملك أيّ جهازٍ على الشبكة البوّابة والقاطع والخزنة (تدقيق ٢٠٢٦-١٠-٠٢ ح-01). `6e058b1` جعل
    # الافتراض الحلقة المحلّيّة ويرفض الإقلاع على غيرها — والعقد يتبعه.
    assert 'os.environ.get("QUANT_HUB_HOST", "127.0.0.1")' in text
    assert '"0.0.0.0"' not in text
    assert "if host not in _LOOPBACK_BINDS:" in text
    assert 'BACKENDS = {"forex": ("127.0.0.1", 8092), "crypto": ("127.0.0.1", 8093)}' in text


def test_preflight_fails_without_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    from governance import network_preflight as preflight

    monkeypatch.delenv("QUANT_CORE_API_KEY", raising=False)
    monkeypatch.delenv("QUANT_GOV_API_KEY", raising=False)
    monkeypatch.setattr(preflight, "_load_api_key_from_vault", lambda market, cfg: None)
    with pytest.raises(RuntimeError, match="requires an API key"):
        preflight.ensure_api_credential("forex", load_yaml("config/core_forex.yaml"))


def test_preflight_accepts_environment_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    from governance import network_preflight as preflight

    monkeypatch.setenv("QUANT_CORE_API_KEY", "smoke-test-key")
    assert preflight.ensure_api_credential("forex", load_yaml("config/core_forex.yaml")) == "smoke-test-key"
