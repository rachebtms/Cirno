"""Settings pass Copilot's saved proxy policy into the device login flow."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cirno_core.config.schema import Config
from cirno_core.providers import github_copilot_oauth
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.providers.oauth import login_oauth_provider


@pytest.mark.parametrize("enabled", [False, True])
def test_copilot_settings_login_uses_saved_proxy_switch(monkeypatch, enabled):
    config = Config()
    config.network.proxy = "http://proxy.test:8080"
    config.providers.github_copilot.use_proxy = enabled
    flow = SimpleNamespace(start=Mock(), authorization_url="https://github.test/device", user_code="CODE", remaining_seconds=60)
    constructor = Mock(return_value=flow)
    monkeypatch.setattr(github_copilot_oauth, "GitHubCopilotOAuthFlow", constructor)
    registry = SimpleNamespace(clear=Mock(), register=Mock(), remove=Mock())
    result = login_oauth_provider(config, {"provider": ["github_copilot"]}, oauth_flows=registry, config_path=None)
    constructor.assert_called_once_with(proxy="http://proxy.test:8080" if enabled else None)
    assert result["status"] == "authorization_required"
    assert result["user_code"] == "CODE"
    registry.register.assert_called_once_with("github_copilot", result["flow_id"], flow)
    flow.start.assert_called_once()


def test_missing_proxy_environment_stops_login_before_replacing_flow(monkeypatch):
    config = Config()
    config.network.proxy = "${CIRNO_TEST_COPILOT_MISSING_PROXY}"
    config.providers.github_copilot.use_proxy = True
    monkeypatch.delenv("CIRNO_TEST_COPILOT_MISSING_PROXY", raising=False)
    constructor = Mock(side_effect=AssertionError("invalid configuration started login"))
    monkeypatch.setattr(github_copilot_oauth, "GitHubCopilotOAuthFlow", constructor)
    registry = SimpleNamespace(clear=Mock())
    with pytest.raises(WebUISettingsError):
        login_oauth_provider(config, {"provider": ["github_copilot"]}, oauth_flows=registry, config_path=None)
    registry.clear.assert_not_called()
    constructor.assert_not_called()
