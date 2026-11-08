"""Logins belong to an instance; unreadable credentials are visible and writes are atomic."""

import os

import pytest
from cirno_core.config.loader import set_config_path
from cirno_core.providers.oauth_storage import InstanceOAuthStorage, token_storage
from oauth_cli_kit.models import OAuthToken


def test_provider_credentials_are_isolated_between_instances(tmp_path):
    set_config_path(tmp_path / "first/config.json")
    first = token_storage("openai_codex", "codex.json")
    first.save(OAuthToken("access-fixture", "refresh-fixture", 1000, "account-fixture"))
    assert first.path == tmp_path / "first/state/providers/openai_codex/codex.json"
    set_config_path(tmp_path / "second/config.json")
    assert token_storage("openai_codex", "codex.json").load() is None
    assert first.load().account_id == "account-fixture"
    if os.name != "nt":
        assert first.path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("content", ['{invalid', '[]', '{"access":"TOP_SECRET","refresh":null,"expires":1}'])
def test_malformed_credentials_report_location_without_exposing_token(tmp_path, content):
    path = tmp_path / "codex.json"
    path.write_text(content)
    with pytest.raises(ValueError) as error:
        InstanceOAuthStorage(path).load()
    assert str(path) in str(error.value)
    assert "TOP_SECRET" not in str(error.value)
    assert path.read_text() == content


def test_failed_refresh_write_preserves_previous_login(tmp_path, monkeypatch):
    storage = InstanceOAuthStorage(tmp_path / "codex.json")
    storage.save(OAuthToken("old", "refresh-old", 1000))
    previous = storage.path.read_bytes()
    def fail_replace(source, target):
        raise OSError("Disk full")
    monkeypatch.setattr("cirno_core.utils.atomic_file.replace_atomic", fail_replace)
    with pytest.raises(OSError, match="Disk full"):
        storage.save(OAuthToken("new", "refresh-new", 2000))
    assert storage.path.read_bytes() == previous
    assert not list(tmp_path.glob("*.tmp"))


def test_global_sdk_override_cannot_redirect_an_instance_login(tmp_path, monkeypatch):
    shared = tmp_path / "shared-sdk.json"
    shared.write_text("unrelated login")
    monkeypatch.setenv("OAUTH_CLI_KIT_TOKEN_PATH", str(shared))
    set_config_path(tmp_path / "instance/config.json")
    storage = token_storage("openai_codex", "codex.json")
    assert storage.load() is None
    storage.save(OAuthToken("owned-access", "owned-refresh", 1000))
    assert shared.read_text() == "unrelated login"
    assert storage.load().access == "owned-access"


def test_sign_out_waits_for_refresh_then_keeps_credentials_deleted(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from cirno_core.providers.oauth_storage import available_codex_token
    storage = InstanceOAuthStorage(tmp_path / "codex.json")
    storage.save(OAuthToken("old", "old-refresh", 1))
    entered, release, deleted = threading.Event(), threading.Event(), threading.Event()
    def refresh(**kwargs):
        token = kwargs["storage"].load()
        entered.set()
        assert release.wait(3)
        assert token.access == "old"
        updated = OAuthToken("new", "new-refresh", 2000)
        kwargs["storage"].save(updated)
        return updated
    def sign_out():
        InstanceOAuthStorage(storage.path).delete()
        deleted.set()
    monkeypatch.setattr("cirno_core.providers.oauth_storage.get_token", refresh)
    with ThreadPoolExecutor(2) as pool:
        refreshing = pool.submit(available_codex_token, storage=storage)
        assert entered.wait(1)
        logout = pool.submit(sign_out)
        try:
            assert not deleted.wait(0.05)
        finally:
            release.set()
        refreshing.result(timeout=3)
        logout.result(timeout=3)
    assert deleted.is_set()
    assert storage.load() is None
