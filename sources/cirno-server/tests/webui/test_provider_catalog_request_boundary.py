"""Provider catalog queries keep configured routing and credentials on failure."""
from unittest.mock import Mock

import httpx
import pytest
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_server.webui.settings import api


def setup(tmp_path, monkeypatch):
    config = Config()
    config.providers.deepseek.api_key = 'catalog-secret'
    path = tmp_path / 'config.json'
    get = Mock(return_value=httpx.Response(200, json={'data': []}, request=httpx.Request('GET', 'https://catalog.example/models')))
    monkeypatch.setattr(api.httpx, 'get', get)
    return config, path, get


@pytest.mark.parametrize('use_proxy', [False, True])
def test_catalog_http_uses_only_explicit_proxy_configuration(tmp_path, monkeypatch, use_proxy):
    config, path, get = setup(tmp_path, monkeypatch)
    config.providers.deepseek.use_proxy = use_proxy
    config.network.proxy = 'http://proxy.example:8080'
    save_config(config, path)
    result = api.provider_models_payload({'provider': ['deepseek']}, config_path=path)
    assert result['status'] == 'available'
    assert get.call_args.kwargs.get('trust_env') is False
    assert get.call_args.kwargs.get('proxy') == ('http://proxy.example:8080' if use_proxy else None)


@pytest.mark.parametrize(('field', 'value', 'status'), [
    ('api_base', '${CIRNO_CATALOG_MISSING}', 'missing_api_base'),
    ('api_base', 'https://${CIRNO_CATALOG_MISSING}.catalog.example/v1', 'missing_api_base'),
    ('api_key', '${CIRNO_CATALOG_MISSING}', 'not_configured'),
    ('api_key', 'prefix-${CIRNO_CATALOG_MISSING}', 'not_configured'),
])
def test_catalog_unresolved_environment_does_not_submit_partial_credentials_or_redirect_to_defaults(tmp_path, monkeypatch, field, value, status):
    config, path, get = setup(tmp_path, monkeypatch)
    monkeypatch.delenv('CIRNO_CATALOG_MISSING', raising=False)
    setattr(config.providers.deepseek, field, value)
    save_config(config, path)
    result = api.provider_models_payload({'provider': ['deepseek']}, config_path=path)
    assert result['status'] == status
    get.assert_not_called()


@pytest.mark.parametrize('exception', [httpx.ReadError, httpx.InvalidURL, ValueError])
def test_catalog_failures_do_not_expose_endpoint_or_proxy_secrets(tmp_path, monkeypatch, exception):
    config, path, get = setup(tmp_path, monkeypatch)
    save_config(config, path)
    get.side_effect = exception('request failed at https://user:catalog-secret@catalog.example?key=catalog-secret')
    result = api.provider_models_payload({'provider': ['deepseek']}, config_path=path)
    assert result['status'] == 'error'
    assert 'catalog-secret' not in str(result)
    assert 'user:' not in str(result)
    assert result['message']


@pytest.mark.parametrize('key', [None, 'prefix-${CIRNO_CATALOG_MISSING}'])
def test_optional_catalog_credentials_are_optional_only_when_not_declared(tmp_path, monkeypatch, key):
    config, path, get = setup(tmp_path, monkeypatch)
    monkeypatch.delenv('CIRNO_CATALOG_MISSING', raising=False)
    config.providers.custom.api_base = 'https://catalog.example/v1'
    config.providers.custom.api_key = key
    save_config(config, path)
    result = api.provider_models_payload({'provider': ['custom']}, config_path=path)
    if key is None:
        assert result['status'] == 'available'
        assert 'Authorization' not in get.call_args.kwargs['headers']
    else:
        assert result['status'] == 'not_configured'
        get.assert_not_called()
