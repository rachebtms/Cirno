"""Credential failures remain visible without breaking other provider settings."""

import pytest

from cirno.providers.registry import find_by_name
from cirno.webui.settings.models import oauth_provider_status


@pytest.mark.parametrize(("provider", "reader"), [
    ("openai_codex", "oauth_cli_kit.storage.FileTokenStorage.load"),
    ("github_copilot", "cirno.providers.github_copilot_provider.get_github_copilot_login_status"),
    ("xai_grok", "cirno.providers.xai_oauth.get_xai_oauth_login_status"),
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
