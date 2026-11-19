"""OAuth catalog identity survives anonymous legacy tokens and sign-out."""

from types import SimpleNamespace

import pytest
from cirno_core.providers import github_copilot_provider as copilot
from cirno_core.providers import openai_codex_provider as codex
from cirno_core.providers import xai_grok_provider as xai
from cirno_core.providers.catalog.contracts import ProviderModelSpec
from cirno_core.providers.oauth_catalog_cache import (
    OAuthCatalogAuthRequiredError,
    OAuthModelCatalog,
)


def setup(monkeypatch, tmp_path, provider, *, account_id=None):
    state = SimpleNamespace(
        token=SimpleNamespace(access="credential-A", account_id=account_id), calls=0
    )
    storage = SimpleNamespace(
        load=lambda: state.token, get_token_path=lambda: tmp_path / "auth.json"
    )

    def fetch(_proxy):
        state.calls += 1
        if state.token is None:
            raise OAuthCatalogAuthRequiredError()
        identity = state.token.access.removeprefix("credential-")
        # A legacy credential can gain its account ID during SDK token refresh.
        state.token = SimpleNamespace(
            access=state.token.access, account_id=state.token.account_id or "account-" + identity
        )
        return (ProviderModelSpec(id="model-" + identity),)

    catalog = OAuthModelCatalog(fallback_models=(), fetch=fetch)
    if provider == "codex":
        monkeypatch.setattr(codex, "token_storage", lambda *_args: storage)
        monkeypatch.setattr(codex, "_OPENAI_CODEX_MODEL_CATALOG", catalog)
        get = codex.get_openai_codex_model_catalog
    elif provider == "xai":
        monkeypatch.setattr(xai, "get_xai_oauth_login_status", lambda: state.token)
        monkeypatch.setattr(xai, "get_xai_oauth_storage_path", storage.get_token_path)
        monkeypatch.setattr(xai, "_XAI_GROK_MODEL_CATALOG", catalog)
        get = xai.get_xai_grok_model_catalog
    else:
        monkeypatch.setattr(copilot, "get_storage", lambda: storage)
        monkeypatch.setattr(copilot, "_GITHUB_COPILOT_MODEL_CATALOG", catalog)
        get = copilot.get_github_copilot_model_catalog
    return state, get


@pytest.mark.parametrize("provider", ["codex", "xai", "copilot"])
@pytest.mark.parametrize("replacement", ["signed_out", "other_legacy_account"])
def test_missing_account_id_never_shares_cached_models_with_another_login(
    monkeypatch, tmp_path, provider, replacement
):
    state, get = setup(monkeypatch, tmp_path, provider)
    assert get().models[0].id == "model-A"
    state.token = (
        None
        if replacement == "signed_out"
        else SimpleNamespace(access="credential-B", account_id=None)
    )
    result = get()
    if replacement == "signed_out":
        assert result.error_kind == "auth_required"
        assert result.models == ()
    else:
        assert result.models[0].id == "model-B"
    assert state.calls == 2


@pytest.mark.parametrize("provider", ["codex", "xai", "copilot"])
def test_known_account_token_refresh_keeps_the_catalog_cache_hit(monkeypatch, tmp_path, provider):
    state, get = setup(monkeypatch, tmp_path, provider, account_id="same-account")
    assert get().source == "remote"
    state.token = SimpleNamespace(access="credential-refreshed", account_id="same-account")
    assert get().source == "cache"
    assert state.calls == 1
