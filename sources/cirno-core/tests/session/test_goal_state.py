"""Tests for ``goal_state`` session metadata helpers."""

from __future__ import annotations

import pytest

from cirno_core.session.goal_state import (
    GOAL_STATE_KEY,
    MAX_GOAL_OBJECTIVE_CHARS,
    explicit_goal_requested,
    goal_state_runtime_lines,
    goal_state_ws_blob,
    parse_goal_state,
    resume_goal_state,
    sustained_goal_active,
)


@pytest.mark.parametrize("recap", [
    "Execution stopped: error", "Execution failed (connection): request interrupted",
    "Automatic continuation limit reached.", "Verified 170 papers; next: review methods",
])
def test_resume_removes_runtime_stop_recap_but_keeps_verified_progress(recap):
    goal = {"status": "blocked", "objective": "Read papers", "recap": recap,
            "wake_at": "2030-01-01T00:00:00Z", "ended_at": "2029-01-01T00:00:00Z"}
    resumed = resume_goal_state(goal)
    assert resumed["status"] == "active" and resumed["resumed_at"]
    assert "wake_at" not in resumed and "ended_at" not in resumed
    assert resumed.get("recap") == (recap if recap.startswith("Verified") else None)
    assert goal["status"] == "blocked" and goal["recap"] == recap
    assert resume_goal_state(goal, recap="Resume from the checked artifacts")["recap"] == "Resume from the checked artifacts"


def test_runtime_lines_empty_when_no_metadata():
    assert goal_state_runtime_lines(None) == []
    assert goal_state_runtime_lines({}) == []


def test_runtime_lines_empty_when_completed():
    meta = {
        GOAL_STATE_KEY: {"status": "completed", "objective": "was doing X"},
    }
    assert goal_state_runtime_lines(meta) == []


def test_runtime_lines_include_objective_when_active():
    meta = {
        GOAL_STATE_KEY: {
            "status": "active",
            "objective": "Ship the fix.",
            "ui_summary": "fix",
        },
    }
    lines = goal_state_runtime_lines(meta)
    assert "Goal (active):" in lines
    assert "Ship the fix." in lines
    assert any("Summary: fix" in ln for ln in lines)


def test_runtime_lines_preserve_maximum_accepted_objective():
    objective = "x" * MAX_GOAL_OBJECTIVE_CHARS

    lines = goal_state_runtime_lines(
        {GOAL_STATE_KEY: {"status": "active", "objective": objective}}
    )

    assert lines[:2] == ["Goal (active):", objective]
    assert "goals__update" in lines[2]
    assert "tools.goals.update(action='complete')" in lines[2]


def test_goal_state_key_takes_precedence_over_legacy():
    meta = {
        GOAL_STATE_KEY: {"status": "active", "objective": "New key wins.", "ui_summary": "n"},
        "thread_goal": {"status": "active", "objective": "Ignored.", "ui_summary": "o"},
    }
    lines = goal_state_runtime_lines(meta)
    assert "New key wins." in lines
    assert "Ignored." not in "".join(lines)


def test_parse_goal_state_accepts_json_string():
    assert parse_goal_state('{"status":"active","objective":"x"}') == {
        "status": "active",
        "objective": "x",
    }


@pytest.mark.parametrize("damaged", ["{", "[]", [], 42, False])
def test_damaged_goal_is_not_silently_treated_as_inactive(damaged):
    with pytest.raises(ValueError, match="Stored Goal state"):
        sustained_goal_active({GOAL_STATE_KEY: damaged})


def test_goal_state_ws_blob_inactive_when_missing_or_completed():
    assert goal_state_ws_blob(None) == {"active": False}
    assert goal_state_ws_blob({}) == {"active": False}
    assert goal_state_ws_blob({GOAL_STATE_KEY: {"status": "completed", "objective": "x"}}) == {
        "active": False,
    }


def test_goal_state_ws_blob_active_shape():
    meta = {
        GOAL_STATE_KEY: {
            "status": "active",
            "objective": "Build feature.",
            "ui_summary": "feat",
        },
    }
    assert goal_state_ws_blob(meta) == {
        "active": True,
        "status": "active",
        "ui_summary": "feat",
        "objective": "Build feature.",
        "continuation_rounds": 0,
    }


def test_goal_state_ws_blob_preserves_blocked_state_for_host_attention():
    meta = {
        GOAL_STATE_KEY: {
            "status": "blocked",
            "objective": "Deploy safely.",
            "ui_summary": "Approval required",
            "recap": "Production access is required.",
        },
    }
    assert goal_state_ws_blob(meta) == {
        "active": False,
        "status": "blocked",
        "ui_summary": "Approval required",
        "objective": "Deploy safely.",
        "recap": "Production access is required.",
        "continuation_rounds": 0,
    }


def test_sustained_goal_active_false_when_missing_or_completed():
    assert sustained_goal_active(None) is False
    assert sustained_goal_active({}) is False
    assert sustained_goal_active({GOAL_STATE_KEY: {"status": "completed", "objective": "x"}}) is False


def test_sustained_goal_active_true_when_active():
    meta = {GOAL_STATE_KEY: {"status": "active", "objective": "Run long task."}}
    assert sustained_goal_active(meta) is True


def test_explicit_goal_requested_only_reads_command_metadata():
    assert explicit_goal_requested({}) is False
    message_meta = {"original_command": "/goal", "goal_requested": True}
    assert explicit_goal_requested(message_meta) is True
