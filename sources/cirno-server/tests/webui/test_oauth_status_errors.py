"""Credential failures remain visible without breaking other provider settings."""

import pytest
from cirno_core.providers.registry import find_by_name
from cirno_server.webui.settings.providers.oauth import oauth_provider_status


@pytest.mark.parametrize(("provider", "reader"), [
    ("openai_codex", "cirno_core.providers.oauth_storage.InstanceOAuthStorage.load"),
    ("github_copilot", "cirno_core.providers.github_copilot_provider.get_github_copilot_login_status"),
    ("xai_grok", "cirno_core.providers.xai_oauth.get_xai_oauth_login_status"),
])
def test_credential_read_error_is_distinct_from_missing_login(monkeypatch, provider, reader):
    def denied(*args, **kwargs):
        raise PermissionError("credential file is not readable")

    monkeypatch.setattr(reader, denied)
    status = oauth_provider_status(find_by_name(provider))
    assert not status["configured"]
    assert status["login_supported"]
    assert "credential file is not readable" in status["error"]

    def missing(*args, **kwargs):
        raise FileNotFoundError("no saved login")

    monkeypatch.setattr(reader, missing)
    status = oauth_provider_status(find_by_name(provider))
    assert not status["configured"]
    assert "error" not in status


@pytest.mark.parametrize(("provider", "filename"), [("openai_codex", "codex.json"), ("github_copilot", "github-copilot.json")])
def test_provider_sign_out_deletes_only_its_instance_login(tmp_path, monkeypatch, provider, filename):
    from types import SimpleNamespace
    from cirno_core.providers.oauth_storage import token_storage
    from cirno_server.webui.settings.providers.oauth import logout_oauth_provider
    from oauth_cli_kit.models import OAuthToken
    monkeypatch.setattr("cirno_core.providers.oauth_storage.get_data_dir", lambda: tmp_path / "state")
    saved = token_storage(provider, filename)
    saved.save(OAuthToken("fixture", "refresh", 1000))
    unrelated = tmp_path / "other-app.json"
    unrelated.write_text("other login")
    logout_oauth_provider({"provider": [provider]}, oauth_flows=SimpleNamespace(clear=lambda name: None), config_path=None, settings_payload=lambda **kwargs: {})
    assert saved.load() is None
    assert unrelated.read_text() == "other login"
