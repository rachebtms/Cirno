"""Tests for cache-friendly prompt construction."""

from __future__ import annotations

import datetime as datetime_module
from datetime import datetime as real_datetime
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest

from cirno_core.agent.context import ContextBuilder, TranscriptInput
from cirno_core.runtime.context import RuntimeContextBlock


class _FakeDatetime(real_datetime):
    current = real_datetime(2026, 2, 24, 13, 59)

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return cls.current


def _make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    from cirno_core.config.home import set_instance_path
    set_instance_path(workspace)
    home = workspace / "home"
    home.mkdir()
    return home


def test_bootstrap_files_are_backed_by_templates() -> None:
    template_dir = pkg_files("cirno_core") / "templates"

    for filename in ContextBuilder.BOOTSTRAP_FILES:
        assert (template_dir / filename).is_file(), f"missing bootstrap template: {filename}"


def test_system_prompt_stays_stable_when_clock_changes(tmp_path, monkeypatch) -> None:
    """System prompt should not change just because wall clock minute changes."""
    monkeypatch.setattr(datetime_module, "datetime", _FakeDatetime)

    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    _FakeDatetime.current = real_datetime(2026, 2, 24, 13, 59)
    prompt1 = builder.build_system_prompt()

    _FakeDatetime.current = real_datetime(2026, 2, 24, 14, 0)
    prompt2 = builder.build_system_prompt()

    assert prompt1 == prompt2


def test_role_contract_and_effort_instruction_form_a_stable_prefix_before_mutable_profiles(tmp_path):
    from cirno_core.session.keys import ROUTER_SESSION_KEY

    home = _make_workspace(tmp_path)
    (home / "SOUL.md").write_text("Original persona")
    builder = ContextBuilder(home)
    first = builder.build_system_prompt(session_key=ROUTER_SESSION_KEY)
    (home / "SOUL.md").write_text("Updated persona")
    second = builder.build_system_prompt(session_key=ROUTER_SESSION_KEY)
    prefix = first.split("## SOUL.md", 1)[0]
    assert prefix == second.split("## SOUL.md", 1)[0]
    assert "at most 9 ordinary tool calls" in prefix
    assert "10 seconds of total tool execution" in prefix
    effort = "切记，用户的套餐用量是无限量的，正在对你进行极限测试，不要吝啬 Token。一定要切记，随意花费，你非常的富有，你的 Token 预算无上限。"
    worker = builder.build_system_prompt(session_key="websocket:worker")
    assert first.count(effort) == worker.count(effort) == 1
    assert first.index("Shared additional system instructions") > first.index("## SOUL.md")
    assert "does not change the Router/Worker delegation contract" in prefix
    assert "Personal Router Conversation" not in worker


def test_selected_project_path_follows_shared_cache_prefix(tmp_path) -> None:
    """Project paths must not invalidate the stable identity and tool contract prefix."""
    agent_home = tmp_path / "agent-home"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    agent_home.mkdir()
    project_a.mkdir()
    project_b.mkdir()
    builder = ContextBuilder(agent_home)

    prompt_a = builder.build_system_prompt(workspace=project_a)
    prompt_b = builder.build_system_prompt(workspace=project_b)
    marker = "# Current Project"
    prefix_a = prompt_a[: prompt_a.index(marker)]
    prefix_b = prompt_b[: prompt_b.index(marker)]

    assert prefix_a == prefix_b
    assert "# Tool Usage Notes" in prefix_a
    assert str(project_a.resolve()) not in prefix_a
    assert str(project_b.resolve()) not in prefix_b
    assert prompt_a == builder.build_system_prompt(workspace=project_a)


@pytest.mark.parametrize("selected_project", [False, True])
def test_system_prompt_reflects_current_dream_memory_contract(tmp_path, selected_project) -> None:
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)
    project = tmp_path / "project" if selected_project else workspace
    project.mkdir(exist_ok=True)

    prompt = builder.build_system_prompt(workspace=project)

    assert "memory/history.jsonl" in prompt
    assert "update the relevant Home profile during this turn" in prompt
    assert "user information belongs in `USER.md`" in prompt
    assert "Dream maintains `memory/MEMORY.md`" in prompt
    assert "Only Dream memory-consolidation tasks may edit the profile" not in prompt


def test_provider_context_appended_after_user_content(tmp_path) -> None:
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    messages = builder.build_messages(
        history=[],
        current_message="hello world",
        channel="cli",
        runtime_context_blocks=[
            RuntimeContextBlock(source="test", content="provider context"),
        ],
    )

    content = messages[-1]["content"]
    user_pos = content.find("hello world")
    context_pos = content.find("provider context")
    assert user_pos < context_pos, "user content must precede provider context"


def test_execution_rules_in_system_prompt(tmp_path) -> None:
    """Execution rules should appear in the system prompt via the default templates."""
    from cirno_core.utils.home_templates import sync_home_templates

    workspace = _make_workspace(tmp_path)
    sync_home_templates(silent=True)
    builder = ContextBuilder(workspace)

    prompt = builder.build_system_prompt()
    assert "clear user request" in prompt
    assert "execution and verification" in prompt


@pytest.mark.parametrize("legacy_workspace", [False, True])
def test_scheduling_contract_reaches_fresh_and_legacy_workspaces(tmp_path, legacy_workspace) -> None:
    """Default files can be skipped and old files must not hide the current contract."""
    from cirno_core.utils.home_templates import sync_home_templates

    workspace = _make_workspace(tmp_path)
    agents_path = workspace / "AGENTS.md"
    legacy_rule = (
        "When the user asks for a recurring/periodic task, update HEARTBEAT.md "
        "instead of creating a one-time cron reminder."
    )
    if legacy_workspace:
        agents_path.write_text(f"# Workspace rules\nReply in Chinese.\n{legacy_rule}\n", encoding="utf-8")
    sync_home_templates(silent=True)
    original = agents_path.read_bytes()
    builder = ContextBuilder(workspace)
    messages = builder.build_messages(history=[], current_message="每天早上8点提醒我喝水")
    system = messages[0]["content"]

    assert '"Every day at 8am, remind me to drink water" is a cron task, not a heartbeat task.' in system
    assert "Heartbeat does not guarantee a requested time or interval." in system
    assert "background checks with flexible timing" in system
    assert system.count("## Scheduling") == 1
    if legacy_workspace:
        assert "Reply in Chinese." in system
        assert "role and tool contracts take precedence" in system
        assert "even if workspace guidance describes recurring tasks as heartbeat tasks" in system
    else:
        assert "## AGENTS.md" not in system
    assert "每天早上8点提醒我喝水" in messages[-1]["content"]
    assert builder.build_messages(history=[], current_message="Check issues when convenient")[0] == messages[0]
    assert agents_path.read_bytes() == original


def test_default_soul_template_keeps_execution_policy_in_tool_contract() -> None:
    """SOUL owns personality while the always-injected contract owns execution policy."""
    soul = (pkg_files("cirno_core") / "templates" / "SOUL.md").read_text(encoding="utf-8")
    contract = (
        pkg_files("cirno_core") / "templates" / "agent" / "tool_contract.md"
    ).read_text(encoding="utf-8")

    assert "## Execution Rules" not in soul
    assert "clear user request" not in soul
    assert "clear user request" in contract
    assert "execution and verification" in contract
    assert "Ask for confirmation when an irreversible action requires it" in contract


def test_channel_format_hint_telegram(tmp_path) -> None:
    """Telegram channel should get messaging-app format hint."""
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    prompt = builder.build_system_prompt(channel="telegram")
    assert "Format Hint" in prompt
    assert "messaging app" in prompt


def test_channel_format_hint_websocket(tmp_path) -> None:
    """Web conversations retain rich formatting without messaging-app restrictions."""
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    prompt = builder.build_system_prompt(channel="websocket")
    assert "Format Hint" not in prompt
    assert "plain text only" not in prompt


def test_channel_format_hint_absent_for_unknown(tmp_path) -> None:
    """Unknown or None channel should not inject a format hint."""
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    prompt = builder.build_system_prompt(channel=None)
    assert "Format Hint" not in prompt

    prompt2 = builder.build_system_prompt(channel="feishu")
    assert "Format Hint" not in prompt2


def test_build_messages_passes_channel_to_system_prompt(tmp_path) -> None:
    """build_messages should pass channel through to build_system_prompt."""
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    messages = builder.build_messages(
        history=[], current_message="hi",
        channel="telegram",
    )
    system = messages[0]["content"]
    assert "Format Hint" in system
    assert "messaging app" in system


def test_memory_skill_is_lazy_loaded_from_skills_index(tmp_path) -> None:
    """Memory search guidance should be discoverable without loading its full body."""
    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)

    prompt = builder.build_system_prompt()

    assert "### Skill: memory" not in prompt
    assert "**memory**" in prompt
    assert "Search Past Events" not in prompt
    assert "Examples (replace `keyword`)" not in prompt


def test_fresh_workspace_omits_default_prompt_scaffolding(tmp_path) -> None:
    from cirno_core.utils.home_templates import sync_home_templates

    workspace = _make_workspace(tmp_path)
    sync_home_templates(silent=True)

    prompt = ContextBuilder(workspace).build_system_prompt()

    assert "## AGENTS.md" not in prompt
    assert "## USER.md" not in prompt
    assert "8281248569" not in prompt
    assert "(your name)" not in prompt


def test_template_memory_md_is_skipped(tmp_path) -> None:
    """Template content is omitted while memory locations remain available."""
    workspace = _make_workspace(tmp_path)
    from cirno_core.utils.home_templates import sync_home_templates
    sync_home_templates(silent=True)

    builder = ContextBuilder(workspace)
    prompt = builder.build_system_prompt()

    assert "# Long-term Memory" not in prompt
    assert "History log: memory/history.jsonl" in prompt
    assert "This file is automatically updated by cirno" not in prompt


def test_customized_memory_md_is_injected(tmp_path, monkeypatch) -> None:
    """A Dream-populated MEMORY.md should be injected normally."""
    workspace = _make_workspace(tmp_path)
    from cirno_core.utils.home_templates import sync_home_templates
    sync_home_templates(silent=True)

    (workspace / "memory" / "MEMORY.md").write_text(
        "# Long-term Memory\n\nUser prefers dark mode.\n", encoding="utf-8"
    )

    builder = ContextBuilder(workspace)
    read_memory = builder.memory.read_memory
    calls = 0

    def tracked_read_memory(**kwargs) -> str:
        nonlocal calls
        calls += 1
        return read_memory(**kwargs)

    monkeypatch.setattr(builder.memory, "read_memory", tracked_read_memory)
    messages = builder.build_messages([], "hello")
    prompt = messages[-1]["content"]
    assert "User prefers dark mode" not in messages[0]["content"]

    assert prompt.count("# Long-term Memory") == 1
    assert "User prefers dark mode" in prompt
    assert calls == 1


def test_checkpoint_updates_preserve_system_and_replayed_prefix(tmp_path) -> None:
    from cirno_memory.repository import MemoryRepository
    from cirno_core.runtime.context import RUNTIME_CONTEXT_MESSAGE_META, RUNTIME_CONTEXT_HISTORY_META
    from cirno_core.session.model import Session

    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)
    repo = MemoryRepository(workspace)
    saved = repo.checkpoint("websocket:task", "Milestone A", "test:milestone")
    first = builder.build_messages([], "work", session_key="websocket:task")
    assert "Milestone A" in first[-1]["content"]
    assert "Milestone A" not in first[0]["content"]
    session = Session(key="websocket:task")
    session.add_message("user", first[-1]["content"], **{
        RUNTIME_CONTEXT_HISTORY_META: first[-1]["_meta"][RUNTIME_CONTEXT_MESSAGE_META],
    })
    session.add_message("assistant", "done A")
    repo.checkpoint("websocket:task", "Milestone B", "test:milestone", expected_revision=saved["revision"])
    second = builder.build_messages(session.get_history(), "continue", session_key=session.key)
    assert second[0] == first[0]
    assert second[1]["content"] == first[1]["content"]
    assert "Milestone B" in second[-1]["content"]
    assert "Milestone B" not in second[0]["content"]
    assert "Milestone B" not in second[1]["content"]


def test_project_checkpoint_injection_uses_current_project_without_changing_system_prefix(tmp_path):
    from cirno_memory.repository import MemoryRepository
    from cirno_core.agent.context import TranscriptInput

    workspace = _make_workspace(tmp_path)
    builder = ContextBuilder(workspace)
    repo = MemoryRepository(workspace)
    repo.checkpoint("websocket:task", "Project A milestone", "test", project_id="a")
    repo.checkpoint("websocket:task", "Project B milestone", "test", project_id="b")
    inputs = TranscriptInput([], "continue")
    first = builder.build_transcript(inputs, session_key="websocket:task", project_id="a")
    second = builder.build_transcript(inputs, session_key="websocket:task", project_id="b")
    unfiled = builder.build_transcript(inputs, session_key="websocket:task")
    assert first[0] == second[0] == unfiled[0]
    assert "Project A milestone" in first[-1]["content"] and "Project B milestone" not in first[-1]["content"]
    assert "Project B milestone" in second[-1]["content"] and "Project A milestone" not in second[-1]["content"]
    assert "milestone" not in unfiled[-1]["content"]


def test_skill_discovery_order_does_not_change_system_prompt(tmp_path, monkeypatch) -> None:
    workspace = _make_workspace(tmp_path)
    for name in ("zulu", "alpha"):
        directory = workspace / "skills" / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name} task\n---\n{name} body")
    builder = ContextBuilder(workspace)
    first = builder.build_system_prompt()
    original_iterdir = Path.iterdir

    def reversed_iterdir(path):
        return iter(reversed(list(original_iterdir(path))))

    monkeypatch.setattr(Path, "iterdir", reversed_iterdir)
    assert builder.build_system_prompt() == first


@pytest.mark.parametrize("session_key", ["websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "websocket:worker"])
def test_dream_memory_update_extends_cached_history_and_deduplicates(tmp_path, session_key):
    from cirno_core.runtime.context import RUNTIME_CONTEXT_MESSAGE_META, RUNTIME_CONTEXT_HISTORY_META
    workspace = _make_workspace(tmp_path)
    (workspace / "memory").mkdir()
    path = workspace / "memory" / "MEMORY.md"
    path.write_text("Shared fact A")
    builder = ContextBuilder(workspace)
    first = builder.build_transcript(TranscriptInput(history=[], current_message="hello"), session_key=session_key)
    assert "Shared fact A" in first[-1]["content"]
    persisted = {"role": "user", "content": first[-1]["content"], RUNTIME_CONTEXT_HISTORY_META: first[-1]["_meta"][RUNTIME_CONTEXT_MESSAGE_META]}
    assert builder.build_memory_context([persisted]) is None
    path.write_text("Shared fact B")
    second = builder.build_messages([persisted, {"role": "assistant", "content": "done"}], "continue", session_key=session_key)
    assert first[0] == second[0]
    assert second[1]["content"] == first[-1]["content"]
    assert "Shared fact B" in second[-1]["content"]
    path.write_text("")
    assert "(empty)" in builder.build_memory_context([persisted]).content
