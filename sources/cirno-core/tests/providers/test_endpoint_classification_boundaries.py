"""Endpoint metadata is based on actual hosts and cannot crash on malformed URLs."""
import pytest
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_core.providers.endpoints import (
    is_local_endpoint,
    uses_opencode_affinity,
    uses_openrouter_attribution,
)
from cirno_core.providers.model_api import is_direct_openai_base
from cirno_core.providers.registry import find_by_name
from cirno_core.providers.routing import resolve_automatic_model_api


@pytest.mark.parametrize('endpoint', ['http://[', 'http://[broken-ipv6]/v1'])
def test_malformed_endpoint_does_not_crash_locality_or_affinity_classification(endpoint):
    assert is_local_endpoint(None, endpoint) is False
    assert uses_opencode_affinity(None, endpoint) is False


@pytest.mark.parametrize('endpoint', ['http://localhost.:8000/v1', 'http://host.docker.internal.:11434/v1'])
def test_absolute_local_dns_names_keep_local_transport_policy(endpoint):
    assert is_local_endpoint(None, endpoint) is True


@pytest.mark.parametrize(('endpoint', 'expected'), [
    ('https://openrouter.ai/api/v1', True),
    ('https://sub.openrouter.ai/v1', True),
    ('https://openrouter.ai.evil.example/v1', False),
    ('https://other.example/openrouter/v1', False),
    ('https://user:openrouter@other.example/v1', False),
])
def test_openrouter_attribution_matches_the_host_not_url_text(endpoint, expected):
    assert uses_openrouter_attribution(None, endpoint) is expected


@pytest.mark.parametrize('endpoint', [
    'https://api.openai.com.evil.example/v1',
    'https://other.example/api.openai.com/v1',
    'https://api.openai.com@other.example/v1',
    'https://api.openai.com:65536/v1',
    'https://[api.openai.com/v1',
])
def test_non_openai_origins_do_not_enable_direct_openai_protocols(endpoint):
    config = Config()
    config.providers.openai.api_key = 'fixture'
    config.providers.openai.api_base = endpoint
    preset = ModelPresetConfig(model='gpt-5', provider='openai')
    assert is_direct_openai_base(endpoint) is False
    assert resolve_automatic_model_api(config, preset=preset) == ('openai', 'chat_completions')


@pytest.mark.parametrize('endpoint', [None, 'https://api.openai.com/v1', 'https://api.openai.com/v1?label=openrouter'])
def test_direct_openai_identity_keeps_automatic_responses_defaults(endpoint):
    config = Config()
    config.providers.openai.api_key = 'fixture'
    config.providers.openai.api_base = endpoint
    preset = ModelPresetConfig(model='gpt-5', provider='openai')
    assert is_direct_openai_base(endpoint) is True
    assert resolve_automatic_model_api(config, preset=preset) == ('openai', 'responses')


def test_explicit_provider_metadata_preserves_proxy_attribution_and_affinity():
    assert uses_openrouter_attribution(find_by_name('openrouter'), 'https://gateway.example/v1') is True
    assert uses_opencode_affinity(find_by_name('opencode'), 'https://gateway.example/v1') is True
