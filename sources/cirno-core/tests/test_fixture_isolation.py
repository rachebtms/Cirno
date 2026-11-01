import time
from pathlib import Path

import pytest

from cirno.llm_usage import LLMCallRecord, get_llm_usage_store
from cirno.pairing import store as pairing_store
from cirno.session.manager import SessionManager
from cirno.config.home import get_home_path


@pytest.mark.parametrize("_iteration", range(2))
def test_runtime_stores_are_isolated_between_parameter_cases(
    tmp_path: Path, _iteration: int,
) -> None:
    sessions = SessionManager(tmp_path.parent / "shared-workspace")
    session = sessions.get_or_create("websocket:fixture-isolation")
    assert session.messages == []
    session.add_message("user", "isolated message")
    sessions.save(session)

    usage = get_llm_usage_store()
    assert usage.recent_calls() == []
    usage.record(LLMCallRecord(
        started_at_ms=int(time.time() * 1000), duration_ms=1, provider="test", model="test",
        source="user", stream=False, finish_reason="stop",
    ))
    assert len(usage.recent_calls()) == 1

    state_path = get_home_path() / "fixture-isolation.txt"
    assert not state_path.exists()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("isolated", encoding="utf-8")
    assert state_path.exists()

    assert not pairing_store.is_approved("test", "isolated-user")
    code = pairing_store.generate_code("test", "isolated-user")
    assert pairing_store.approve_code(code) is not None
    assert pairing_store.is_approved("test", "isolated-user")
