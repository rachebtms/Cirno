"""History rendering must not authorize files via a fallback for corrupt policy."""

from types import SimpleNamespace

import pytest
from cirno_core.security.workspace_access import WorkspaceScopeError
from cirno_server.webui.http.history import HistoryRoutes
from cirno_server.webui.http.recovery import RecoveryRoutes


@pytest.mark.parametrize("route", ["history", "subagent"])
def test_invalid_media_policy_is_a_clear_history_error(route):
    def invalid_scope(key):
        raise WorkspaceScopeError("invalid saved workspace policy")

    server = SimpleNamespace(
        check_api_token=lambda request: True,
        workspaces=SimpleNamespace(scope_for_session_key=invalid_scope),
        subagent_manager=SimpleNamespace(read_session=lambda *args: (None, None)),
    )
    if route == "history":
        response = HistoryRoutes(server)._handle_webui_thread_get(None, "websocket:invalid-policy", history=None)
    else:
        response = RecoveryRoutes(server)._handle_subagent_thread_get(None, "websocket:invalid-policy", "task")
    assert response.status_code == 400
    assert response.body == b"invalid saved workspace policy"
