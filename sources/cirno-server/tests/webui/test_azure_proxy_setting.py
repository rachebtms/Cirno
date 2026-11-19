"""Azure exposes the proxy setting its runtime now consumes."""

from cirno_core.providers.catalog.direct import AZURE_OPENAI
from cirno_server.webui.settings.providers.state import _provider_advanced_field_names


def test_azure_exposes_only_supported_proxy_option():
    assert _provider_advanced_field_names("azure_openai", AZURE_OPENAI) == ["use_proxy"]
