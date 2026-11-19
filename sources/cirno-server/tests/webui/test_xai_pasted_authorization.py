"""Correctable xAI input errors retain the owned settings login flow."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cirno_core.providers.xai_oauth import XAIOAuthInputError
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.providers.oauth import complete_oauth_provider


def test_xai_input_error_returns_400_without_removing_pending_flow():
    flow = SimpleNamespace(complete=Mock(side_effect=XAIOAuthInputError("Copy the latest callback URL.")))
    registry = SimpleNamespace(get=Mock(return_value=flow), remove=Mock())
    payload = Mock(side_effect=AssertionError("invalid input must not publish signed-in settings"))
    with pytest.raises(WebUISettingsError) as error:
        complete_oauth_provider({"provider": ["xai_grok"], "flow_id": ["owned"]}, "wrong-input", oauth_flows=registry, config_path=None, settings_payload=payload)
    assert error.value.status == 400
    registry.remove.assert_not_called()
    payload.assert_not_called()
    flow.complete.assert_called_once_with("wrong-input")


def test_xai_valid_pasted_callback_is_forwarded_without_changing_pending_ownership():
    flow = SimpleNamespace(complete=Mock(return_value=None))
    registry = SimpleNamespace(get=Mock(return_value=flow), remove=Mock())
    callback = "http://127.0.0.1:54321/callback?code=fake&state=fake"
    result = complete_oauth_provider({"provider": ["xai_grok"], "flow_id": ["owned"]}, callback, oauth_flows=registry, config_path=None, settings_payload=Mock())
    assert result == {"status": "pending", "provider": "xai_grok", "flow_id": "owned"}
    flow.complete.assert_called_once_with(callback)
    registry.remove.assert_not_called()
