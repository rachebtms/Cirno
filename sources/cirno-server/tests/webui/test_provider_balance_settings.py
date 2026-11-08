"""Balance settings survive edits and reloads without exposing credentials."""

import json
from unittest.mock import Mock

import httpx
import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.providers.factory import provider_signature
from cirno_server.webui.settings import api
from cirno_server.webui.settings.balance import provider_balance_payload
from cirno_server.webui.settings.contracts import WebUISettingsError


def test_independent_balance_endpoint_roundtrips_redacts_and_does_not_change_model_runtime(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    config = Config()
    config.agents.defaults.model = 'deepseek-chat'
    config.agents.defaults.provider = 'deepseek'
    config.providers.deepseek.api_key = 'model-secret'
    config.providers.deepseek.api_base = 'https://models.example/v1'
    save_config(config, path)
    before = provider_signature(config)
    billing = {'endpoint': 'https://billing.example/account', 'format': 'json', 'amount_path': '/data/balance', 'currency': 'CNY', 'api_key': 'billing-secret'}
    payload = api.update_provider_settings({'provider': ['deepseek'], 'balance': [json.dumps(billing)]}, config_path=path)
    row = next(provider for provider in payload['providers'] if provider['id'] == 'deepseek')
    assert row['balance']['api_key'] != 'billing-secret'
    assert 'billing-secret' not in json.dumps(payload)
    row['balance']['currency'] = 'credits'
    api.update_provider_settings({'provider': ['deepseek'], 'balance': [json.dumps(row['balance'])]}, config_path=path)
    restored = load_config(path)
    assert restored.providers.deepseek.balance.api_key == 'billing-secret'
    assert restored.providers.deepseek.api_base == 'https://models.example/v1'
    assert provider_signature(restored) == before
    get = Mock(return_value=httpx.Response(200, json={'data': {'balance': '21.50'}}, request=httpx.Request('GET', billing['endpoint'])))
    # The operation owns the HTTP request; use a transport stub without touching inference.
    import cirno_core.providers.balance as service
    original = service.query_balance
    monkeypatch.setattr('cirno_server.webui.settings.balance.query_balance', lambda *args, **kwargs: original(*args, **kwargs, http_get=get))
    result = provider_balance_payload({'provider_id': ['deepseek']}, config_path=path)
    assert result['balances'] == [{'amount': '21.50', 'currency': 'credits'}]
    assert get.call_args.args == (billing['endpoint'],)
    api.update_provider_settings({'provider': ['deepseek'], 'balance': ['null']}, config_path=path)
    assert provider_balance_payload({'provider_id': ['deepseek']}, config_path=path)['status'] == 'disabled'
    assert get.call_count == 1


def test_unknown_provider_is_reported(tmp_path):
    path = tmp_path / 'config.json'
    save_config(Config(), path)
    with pytest.raises(WebUISettingsError) as error:
        provider_balance_payload({'provider_id': ['missing']}, config_path=path)
    assert error.value.status == 404


@pytest.mark.asyncio
async def test_balance_route_requires_owner_authentication_and_stays_disabled_by_default(tmp_path):
    import time

    from cirno_core.bus.queue import MessageBus
    from cirno_core.session.manager import SessionManager
    from cirno_server.channels.websocket.config import WebSocketConfig
    from cirno_server.webui.services import build_server_services
    from websockets.datastructures import Headers
    from websockets.http11 import Request

    path = tmp_path / 'config.json'
    save_config(Config(), path)
    sessions = SessionManager(tmp_path / 'workspace', sessions_root=tmp_path / 'state' / 'sessions')
    gateway = build_server_services(config=WebSocketConfig(), bus=MessageBus(), session_manager=sessions,
        static_dist_path=None, workspace_path=tmp_path / 'workspace', config_path=path,
        default_restrict_to_workspace=False, runtime_model_name=None,  )
    url = '/v0/settings/provider-balance?provider_id=deepseek'
    denied = await gateway.http.dispatch(None, Request(url, Headers()))
    assert denied.status_code == 401
    gateway.tokens.api_tokens['owner-test'] = time.monotonic() + 60
    allowed = await gateway.http.dispatch(None, Request(url, Headers([('Authorization', 'Bearer owner-test')])))
    assert allowed.status_code == 200
    assert json.loads(allowed.body) == {'provider_id': 'deepseek', 'status': 'disabled', 'balances': []}


@pytest.mark.parametrize('provider_id', ['openai_codex', 'xai_grok'])
def test_oauth_provider_balance_configuration_survives_save(tmp_path, provider_id):
    from cirno_core.config.balance import ProviderBalanceConfig
    config = Config()
    getattr(config.providers, provider_id).balance = ProviderBalanceConfig(endpoint='https://billing.example/account', api_key='balance-only-secret')
    path = tmp_path / 'config.json'
    save_config(config, path)
    assert getattr(load_config(path).providers, provider_id).balance.api_key == 'balance-only-secret'
