"""Offline transport configuration checks; no listeners or gateway startup."""

import pytest
from cirno_server.channels.websocket.config import TrustedProxyAuthConfig, WebSocketConfig
from cirno_server.webui.http_utils import is_trusted_proxy_authenticated_request
from pydantic import ValidationError
from websockets.http11 import Request
from websockets.streams import StreamReader


def parse_request(header: str) -> Request:
    reader = StreamReader()
    reader.feed_data(b"GET /v0/ws HTTP/1.1\r\n" + header.encode("utf-8") + b": present\r\n\r\n")
    parser = Request.parse(reader.read_line)
    with pytest.raises(StopIteration) as result:
        next(parser)
    return result.value.value


@pytest.mark.parametrize("name", ["X/Auth", "X:Auth", "X;Auth", "X,Auth", "X\x7fAuth", "X-身份"])
def test_proxy_assertion_rejects_names_that_the_wire_parser_cannot_accept(name):
    # A colon is a field separator, so it selects a different wire header name.
    if ":" in name:
        parsed = parse_request(name)
        assert name not in parsed.headers
    else:
        with pytest.raises(ValueError):
            parse_request(name)
    with pytest.raises(ValidationError, match="valid HTTP header name"):
        TrustedProxyAuthConfig(trusted_peer_cidrs=["127.0.0.1/32"], assertion_header=name)


@pytest.mark.parametrize("name", ["Cf-Access-Jwt-Assertion", "X_Auth", "X!#$%&'*+-.^`|~Token"])
def test_valid_assertion_header_survives_real_parser_and_authenticates_trusted_peer(name):
    from types import SimpleNamespace

    request = parse_request(name)
    config = WebSocketConfig(trusted_proxy_auth=TrustedProxyAuthConfig(
        trusted_peer_cidrs=["127.0.0.1/32"], assertion_header=name,
    ))
    assert is_trusted_proxy_authenticated_request(SimpleNamespace(remote_address=("127.0.0.1", 1)), request.headers, config)
    assert not is_trusted_proxy_authenticated_request(SimpleNamespace(remote_address=("192.0.2.1", 1)), request.headers, config)


@pytest.mark.parametrize("port", [-1, 65536])
def test_listener_rejects_invalid_ports_before_startup(port):
    with pytest.raises(ValidationError, match="port"):
        WebSocketConfig(port=port)


@pytest.mark.parametrize("port", [0, 8765, 65535])
def test_listener_preserves_ephemeral_and_valid_ports(port):
    assert WebSocketConfig(port=port).port == port


@pytest.mark.parametrize("host", ["0:0:0:0:0:0:0:0", "0:0::0", ""])
def test_equivalent_wildcard_hosts_cannot_bypass_auth_configuration_guard(host):
    with pytest.raises(ValidationError, match="token"):
        WebSocketConfig(host=host, websocket_requires_token=False)
    assert WebSocketConfig(host=host, token="fixture", websocket_requires_token=False).token == "fixture"


@pytest.mark.parametrize("url", [
    "ws://example.test:not-a-port/v0/ws", "wss://example.test:65536/v0/ws",
    "ws://:8765/v0/ws", "ws://bad host/v0/ws",
])
def test_public_websocket_url_rejects_unusable_authority(url):
    with pytest.raises(ValidationError, match="public_ws_url"):
        WebSocketConfig(public_ws_url=url)


@pytest.mark.parametrize("url", ["ws://localhost:8765/v0/ws", "wss://[::1]:8765/v0/ws", "wss://example.test/v0/ws"])
def test_valid_public_websocket_url_keeps_existing_path_contract(url):
    assert WebSocketConfig(public_ws_url=url).public_ws_url == url


@pytest.mark.parametrize("draft", [
    {"port": "-1"}, {"port": "65536"},
    {"publicWsUrl": "ws://example.test:no-port/v0/ws"},
    {"publicWsUrl": "wss://user:private-url-password@example.test/v0/ws"},
])
def test_check_and_settings_save_reject_invalid_listener_without_mutation_or_secret_echo(tmp_path, draft):
    from cirno_core.config.loader import save_config
    from cirno_core.config.schema import Config
    from cirno_server.channels.registry import load_channel_plugin
    from cirno_server.channels.validation import validate_channel_config
    from cirno_server.webui.settings.contracts import WebUISettingsError
    from cirno_server.webui.settings.services import WebUISettingsServices
    from cirno_server.webui.settings.system import save_channel_config_values

    path = tmp_path / "config.json"
    save_config(Config.model_validate({"channels": {"websocket": {"token": "private-saved-token", "port": 8765}}}), path)
    original = path.read_bytes()
    result = validate_channel_config("websocket", draft, config_path=path)
    assert result["status"] == "invalid"
    assert result["can_enable"] is False
    settings = WebUISettingsServices.create(path)
    with pytest.raises(WebUISettingsError) as error:
        settings.config.update(lambda config: save_channel_config_values(
            config, "websocket", draft, load_channel_plugin=load_channel_plugin,
        ))
    assert error.value.status == 400
    assert path.read_bytes() == original
    assert "private-saved-token" not in str(result) + str(error.value)
    assert "private-url-password" not in str(result) + str(error.value)


@pytest.mark.parametrize("empty", [None, ""])
def test_empty_numeric_draft_uses_the_same_saved_value_as_settings_write(tmp_path, empty):
    from cirno_core.config.loader import load_config, save_config
    from cirno_core.config.schema import Config
    from cirno_server.channels.registry import load_channel_plugin
    from cirno_server.channels.validation import validate_channel_config
    from cirno_server.webui.settings.services import WebUISettingsServices
    from cirno_server.webui.settings.system import save_channel_config_values

    path = tmp_path / "config.json"
    save_config(Config.model_validate({"channels": {"websocket": {"port": 8765}}}), path)
    draft = {"port": empty}
    result = validate_channel_config("websocket", draft, config_path=path)
    assert result["can_enable"] is True
    saved = WebUISettingsServices.create(path).config.update(lambda config: save_channel_config_values(
        config, "websocket", draft, load_channel_plugin=load_channel_plugin,
    ))
    assert saved == []
    assert load_config(path).channels.websocket["port"] == 8765


def test_feature_enable_checks_local_configuration_but_disable_can_repair_it(tmp_path):
    from cirno_core.config.loader import save_config
    from cirno_core.config.schema import Config
    from cirno_server.channels.registry import load_channel_plugin
    from cirno_server.features.service import (
        OptionalFeatureError,
        read_config_data,
        set_channel_config_enabled,
    )

    path = tmp_path / "config.json"
    save_config(Config.model_validate({"channels": {"websocket": {"enabled": False, "port": -1}}}), path)
    plugin = load_channel_plugin("websocket")
    original = path.read_bytes()
    with pytest.raises(OptionalFeatureError, match="Invalid websocket configuration"):
        set_channel_config_enabled(path, "websocket", plugin, True)
    assert path.read_bytes() == original
    # Lower-level config repair is allowed even if the listener config is bad.
    # The public feature API keeps its separate always-enabled WebUI guard.
    set_channel_config_enabled(path, "websocket", plugin, False)
    assert read_config_data(path)["channels"]["websocket"]["enabled"] is False
