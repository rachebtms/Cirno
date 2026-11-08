"""API versions are independent of minor product releases and enforced on endpoints."""

import pytest
from cirno_server.api import API_PREFIX, HEALTH_PATH, WEBSOCKET_PATH
from cirno_server.channels.websocket.config import WebSocketConfig


def test_current_major_endpoints():
    assert API_PREFIX == "/v0"
    assert HEALTH_PATH == "/v0/health"
    assert WebSocketConfig().path == WEBSOCKET_PATH == "/v0/ws"


@pytest.mark.parametrize("field", ["path", "token_issue_path"])
@pytest.mark.parametrize(
    "path",
    ["/", "/ws", "/v1/ws", "/v0/", "/v0/a/../ws", "/v0//ws", "/v0/ws?token=x", "/v0/ws#fragment"],
)
def test_configurable_endpoints_require_current_major(field, path):
    with pytest.raises(ValueError):
        WebSocketConfig(**{field: path})


def test_custom_endpoints_remain_available_inside_version_namespace():
    config = WebSocketConfig(path="/v0/connections/", token_issue_path="/v0/connection-tokens")
    assert config.path == "/v0/connections"
    assert config.token_issue_path == "/v0/connection-tokens"
