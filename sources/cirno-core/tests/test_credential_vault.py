import json

import pytest
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.utils.progress_events import build_tool_event_start_payload






@pytest.mark.parametrize("name", ["credential", "credentials.store", "credentials__store"])
def test_credential_tool_checkpoint_and_activity_redact_values(name):
    call = ToolCallRequest(
        id="secret-call",
        name=name,
        arguments={"action": "store", "value": "DO_NOT_LOG", "label": "Account"},
    )
    assert "DO_NOT_LOG" not in json.dumps(call.to_openai_tool_call())
    assert "DO_NOT_LOG" not in json.dumps(build_tool_event_start_payload(call))
    assert call.arguments["value"] == "DO_NOT_LOG"  # Execution still receives the actual secret.




def test_malformed_credential_call_can_be_checkpointed_before_validation():
    raw = '{"username": "DO_NOT_LOG", "value": "DO_NOT_LOG"'
    call = ToolCallRequest(id="malformed-credential", name="credentials.store", arguments=raw)
    assert "DO_NOT_LOG" not in json.dumps(call.to_openai_tool_call())
    assert call.arguments == raw
