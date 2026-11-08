"""Balances have separate credentials and routing, and failures never become zero."""

from unittest.mock import Mock

import httpx
import pytest

from cirno_core.config.balance import ProviderBalanceConfig
from cirno_core.providers.balance import BalanceQueryError, query_balance


def response(value, status=200):
    return httpx.Response(status, json=value, request=httpx.Request('GET', 'https://billing.example/balance'))


def test_deepseek_balances_preserve_currency_and_decimal_precision():
    get = Mock(return_value=response({'balance_infos': [
        {'currency': 'CNY', 'total_balance': '102.123456789012345678'},
        {'currency': 'USD', 'total_balance': '0.05'},
    ]}))
    settings = ProviderBalanceConfig(endpoint='https://billing.example/balance', api_key='billing-secret')
    assert query_balance(settings, provider_key='model-secret', proxy='http://proxy:8080', http_get=get) == [
        {'amount': '102.123456789012345678', 'currency': 'CNY'}, {'amount': '0.05', 'currency': 'USD'}]
    get.assert_called_once_with('https://billing.example/balance', headers={
        'Accept': 'application/json', 'Authorization': 'Bearer billing-secret'},
        timeout=10.0, follow_redirects=False, proxy='http://proxy:8080', trust_env=False)
    assert 'billing-secret' not in repr(settings)


def test_custom_json_pointer_handles_arrays_and_escaped_keys():
    settings = ProviderBalanceConfig(endpoint='http://localhost/billing', format='json', amount_path='/data/0/a~1b~0c', currency='credits')
    get = Mock(return_value=response({'data': [{'a/b~c': '-0.25'}]}))
    assert query_balance(settings, provider_key='provider-secret', http_get=get) == [{'amount': '-0.25', 'currency': 'credits'}]
    assert get.call_args.kwargs['headers']['Authorization'] == 'Bearer provider-secret'


@pytest.mark.parametrize('payload', [
    {}, {'balance': True}, {'balance': None}, {'balance': 'NaN'}, {'balance': 'not a number'},
])
def test_missing_or_invalid_balances_report_an_error(payload):
    settings = ProviderBalanceConfig(endpoint='https://billing.example', format='json')
    with pytest.raises(BalanceQueryError):
        query_balance(settings, provider_key=None, http_get=Mock(return_value=response(payload)))


@pytest.mark.parametrize('status', [302, 401, 429, 500])
def test_http_failures_do_not_expose_response_credentials(status):
    settings = ProviderBalanceConfig(endpoint='https://billing.example', api_key='billing-secret')
    with pytest.raises(BalanceQueryError, match=f'HTTP {status}') as error:
        query_balance(settings, provider_key=None, http_get=Mock(return_value=response({'error': 'billing-secret'}, status)))
    assert 'billing-secret' not in str(error.value)
