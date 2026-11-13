"""Long Goal reminders change only when the live Goal changes."""

from copy import deepcopy

from cirno_core.agent.goals.continuation import GoalContinuation


def test_unchanged_goal_uses_short_nudges_without_rewriting_metadata():
    metadata = {"goal_state": {"goal_id": "one", "status": "active", "objective": "Read and verify scientific papers. " * 80}}
    original = deepcopy(metadata)
    continuation = GoalContinuation()
    first = continuation.message(metadata)
    assert "You have an active sustained goal:" in first
    for _ in range(4):
        following = continuation.message(metadata)
        assert len(following) < 200
        assert metadata["goal_state"]["objective"] not in following
    assert metadata == original
    metadata["goal_state"]["recap"] = "155 papers verified"
    assert "155 papers verified" in continuation.message(metadata)
    assert "unchanged active Goal" in continuation.message(metadata)
    metadata["goal_state"]["goal_id"] = "replacement"
    assert "You have an active sustained goal:" in continuation.message(metadata)


def test_wait_and_pause_stop_nudges_and_resume_refreshes_the_goal():
    continuation = GoalContinuation()
    metadata = {"goal_state": {"status": "active", "objective": "Verify results"}}
    assert continuation.message(metadata)
    for state in ("waiting", "paused", "stopped", "blocked", "completed"):
        metadata["goal_state"]["status"] = state
        assert continuation.message(metadata) is None
    metadata["goal_state"]["status"] = "active"
    assert "You have an active sustained goal:" in continuation.message(metadata)
