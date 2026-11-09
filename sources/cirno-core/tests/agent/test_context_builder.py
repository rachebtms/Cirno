"""Tests for ContextBuilder — system prompt and message assembly."""
from cirno_core.providers.messages import sanitize_empty_content

from pathlib import Path

import pytest

from cirno_core.agent.context import ContextBuilder, TranscriptInput
from cirno_core.runtime.context import RuntimeContextBlock
from cirno_core.config.home import set_instance_path


@pytest.fixture(autouse=True)
def isolated_home(tmp_path):
    set_instance_path(tmp_path)
    (tmp_path / "home").mkdir(exist_ok=True)
    yield
    set_instance_path(None)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _builder(tmp_path: Path, **kw) -> ContextBuilder:
    return ContextBuilder(workspace=tmp_path, **kw)


# ---------------------------------------------------------------------------
# _merge_message_content (static)
# ---------------------------------------------------------------------------


class TestMergeMessageContent:
    def test_str_plus_str(self):
        result = ContextBuilder._merge_message_content("hello", "world")
        assert result == "hello\n\nworld"

    def test_empty_left_plus_str(self):
        result = ContextBuilder._merge_message_content("", "world")
        assert result == "world"

    def test_list_plus_list(self):
        left = [{"type": "text", "text": "a"}]
        right = [{"type": "text", "text": "b"}]
        result = ContextBuilder._merge_message_content(left, right)
        assert len(result) == 2
        assert result[0]["text"] == "a"
        assert result[1]["text"] == "b"

    def test_str_plus_list(self):
        right = [{"type": "text", "text": "b"}]
        result = ContextBuilder._merge_message_content("hello", right)
        assert len(result) == 2
        assert result[0]["text"] == "hello"
        assert result[1]["text"] == "b"

    def test_list_plus_str(self):
        left = [{"type": "text", "text": "a"}]
        result = ContextBuilder._merge_message_content(left, "world")
        assert len(result) == 2
        assert result[0]["text"] == "a"
        assert result[1]["text"] == "world"

    def test_none_plus_str(self):
        result = ContextBuilder._merge_message_content(None, "hello")
        assert result == [{"type": "text", "text": "hello"}]

    def test_str_plus_none(self):
        result = ContextBuilder._merge_message_content("hello", None)
        assert result == [{"type": "text", "text": "hello"}]

    def test_none_plus_none(self):
        result = ContextBuilder._merge_message_content(None, None)
        assert result == []

    def test_list_items_not_dicts_wrapped(self):
        result = ContextBuilder._merge_message_content(["raw_item"], None)
        assert result == [{"type": "text", "text": "raw_item"}]


# ---------------------------------------------------------------------------
# _load_bootstrap_files
# ---------------------------------------------------------------------------


class TestLoadBootstrapFiles:
    def test_no_bootstrap_files(self, tmp_path):
        builder = _builder(tmp_path / "home")
        assert builder._load_bootstrap_files() == ""

    def test_empty_bootstrap_files(self, tmp_path):
        (tmp_path / "home" / "AGENTS.md").write_text("\n", encoding="utf-8")
        builder = _builder(tmp_path / "home")
        assert builder._load_bootstrap_files() == ""

    def test_agents_md(self, tmp_path):
        (tmp_path / "home" / "AGENTS.md").write_text("Be helpful.", encoding="utf-8")
        builder = _builder(tmp_path / "home")
        result = builder._load_bootstrap_files()
        assert "## AGENTS.md" in result
        assert "Be helpful." in result

    def test_multiple_bootstrap_files(self, tmp_path):
        (tmp_path / "home" / "AGENTS.md").write_text("Rules.", encoding="utf-8")
        (tmp_path / "home" / "SOUL.md").write_text("Soul.", encoding="utf-8")
        builder = _builder(tmp_path / "home")
        result = builder._load_bootstrap_files()
        assert "## AGENTS.md" in result
        assert "## SOUL.md" in result
        assert "Rules." in result
        assert "Soul." in result

    def test_all_bootstrap_files(self, tmp_path):
        for name in ContextBuilder.BOOTSTRAP_FILES:
            (tmp_path / "home" / name).write_text(f"Content of {name}", encoding="utf-8")
        builder = _builder(tmp_path / "home")
        result = builder._load_bootstrap_files()
        for name in ContextBuilder.BOOTSTRAP_FILES:
            assert f"## {name}" in result

    def test_legacy_tools_md_is_not_bootstrapped(self, tmp_path):
        (tmp_path / "home" / "TOOLS.md").write_text("workspace tool notes", encoding="utf-8")
        builder = _builder(tmp_path / "home")
        result = builder._load_bootstrap_files()
        assert "TOOLS.md" not in result
        assert "workspace tool notes" not in result

    def test_utf8_content(self, tmp_path):
        (tmp_path / "home" / "AGENTS.md").write_text("用中文回复", encoding="utf-8")
        builder = _builder(tmp_path / "home")
        result = builder._load_bootstrap_files()
        assert "用中文回复" in result

    def test_selected_project_supplies_only_agents_file(self, tmp_path):
        agent_home = tmp_path / "agent-home" / "home"
        project = tmp_path / "project"
        agent_home.mkdir(parents=True)
        project.mkdir(parents=True)
        (agent_home / "AGENTS.md").write_text("global project rules", encoding="utf-8")
        (agent_home / "WORKER.md").write_text("global worker", encoding="utf-8")
        (agent_home / "USER.md").write_text("global user", encoding="utf-8")
        (project / "AGENTS.md").write_text("selected project rules", encoding="utf-8")
        (project / "SOUL.md").write_text("project soul collision", encoding="utf-8")
        (project / "USER.md").write_text("project user collision", encoding="utf-8")

        set_instance_path(agent_home.parent)
        result = ContextBuilder(agent_home).build_system_prompt(workspace=project)

        assert "selected project rules" in result
        assert "global project rules" in result
        assert "global worker" in result
        assert "global user" in result
        assert "project soul collision" not in result
        assert "project user collision" not in result

    def test_selected_project_without_agents_does_not_fall_back(self, tmp_path):
        agent_home = tmp_path / "agent-home" / "home"
        project = tmp_path / "project"
        agent_home.mkdir(parents=True)
        project.mkdir(parents=True)
        (agent_home / "AGENTS.md").write_text("default workspace rules", encoding="utf-8")

        set_instance_path(agent_home.parent)
        result = ContextBuilder(agent_home).build_system_prompt(workspace=project)

        assert "default workspace rules" in result

    def test_unmodified_agents_and_user_templates_are_skipped(self, tmp_path):
        from cirno_core.utils.home_templates import sync_home_templates

        sync_home_templates(silent=True)

        result = ContextBuilder(tmp_path / "home")._load_bootstrap_files()

        assert "## AGENTS.md" not in result
        assert "## USER.md" not in result
        assert "## SOUL.md" in result

    def test_customized_user_template_is_loaded(self, tmp_path):
        from cirno_core.utils.home_templates import sync_home_templates

        sync_home_templates(silent=True)
        (tmp_path / "home" / "USER.md").write_text("User prefers Chinese.", encoding="utf-8")

        result = ContextBuilder(tmp_path / "home")._load_bootstrap_files()

        assert "## USER.md" in result
        assert "User prefers Chinese." in result


# ---------------------------------------------------------------------------
# _is_template_content (static)
# ---------------------------------------------------------------------------


class TestIsTemplateContent:
    def test_nonexistent_template_returns_false(self):
        assert ContextBuilder._is_template_content("anything", "nonexistent/path.md") is False

    def test_content_matching_template(self):
        from importlib.resources import files as pkg_files
        tpl = pkg_files("cirno_core") / "templates" / "memory" / "MEMORY.md"
        if not tpl.is_file():
            pytest.skip("MEMORY.md template not bundled")
        original = tpl.read_text(encoding="utf-8")
        assert ContextBuilder._is_template_content(original, "memory/MEMORY.md") is True

    def test_modified_content_returns_false(self):
        from importlib.resources import files as pkg_files
        tpl = pkg_files("cirno_core") / "templates" / "memory" / "MEMORY.md"
        if not tpl.is_file():
            pytest.skip("MEMORY.md template not bundled")
        assert ContextBuilder._is_template_content("totally different", "memory/MEMORY.md") is False


# ---------------------------------------------------------------------------
# Bundled bootstrap templates
# ---------------------------------------------------------------------------


class TestBundledToolContract:
    def test_tool_contract_contains_shared_execution_policy(self):
        from importlib.resources import files as pkg_files

        tpl = pkg_files("cirno_core") / "templates" / "agent" / "tool_contract.md"
        content = tpl.read_text(encoding="utf-8")

        assert "clear user request as authorization" in content
        assert "execution and verification" in content
        assert "irreversible action" in content
        assert "Wait for tool results" in content

    def test_tool_contract_is_injected_without_workspace_file(self, tmp_path):
        builder = _builder(tmp_path / "home")
        prompt = builder.build_system_prompt()

        assert "# Tool Usage Notes" in prompt
        assert "clear user request as authorization" in prompt


# ---------------------------------------------------------------------------
# build_user_content
# ---------------------------------------------------------------------------


class TestBuildUserContent:
    def test_no_media_returns_string(self, tmp_path):
        builder = _builder(tmp_path / "home")
        result = builder.build_user_content("hello", None)
        assert result == "hello"

    def test_empty_media_returns_string(self, tmp_path):
        builder = _builder(tmp_path / "home")
        result = builder.build_user_content("hello", [])
        assert result == "hello"

    def test_nonexistent_media_file_returns_string(self, tmp_path):
        builder = _builder(tmp_path / "home")
        result = builder.build_user_content("hello", ["/nonexistent/image.png"])
        assert result == "hello"

    def test_non_image_file_returns_string(self, tmp_path):
        txt = tmp_path / "doc.txt"
        txt.write_text("not an image", encoding="utf-8")
        builder = _builder(tmp_path / "home")
        result = builder.build_user_content("hello", [str(txt)])
        assert result == "hello"

    def test_valid_image_returns_list(self, tmp_path):
        png = tmp_path / "test.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        builder = _builder(tmp_path / "home")
        result = builder.build_user_content("hello", [str(png)])
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == {"type": "text", "text": f"[image: {png}]"}
        assert result[1]["type"] == "image_url"
        assert result[1]["image_url"]["url"].startswith("data:image/png;base64,")
        assert result[2]["type"] == "text"
        assert result[2]["text"] == "hello"

    def test_images_keep_paired_paths_in_provider_visible_content(self, tmp_path):
        from cirno_core.providers.openai_responses.converters import convert_user_message

        paths = [tmp_path / "original.png", tmp_path / "uploaded.png"]
        for index, path in enumerate(paths):
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([index]) * 16)
        content = _builder(tmp_path / "home").build_user_content("compare these", [str(path) for path in paths])
        clean = sanitize_empty_content([{"role": "user", "content": content}])[0]
        converted = convert_user_message(clean["content"])["content"]
        image_indexes = [index for index, block in enumerate(converted) if block["type"] == "input_image"]
        assert len(image_indexes) == 2
        for index, path in zip(image_indexes, paths, strict=True):
            assert index > 0
            assert converted[index - 1] == {"type": "input_text", "text": f"[image: {path}]"}
        assert converted[-1] == {"type": "input_text", "text": "compare these"}

    def test_image_meta_includes_path(self, tmp_path):
        png = tmp_path / "test.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        builder = _builder(tmp_path / "home")
        result = builder.build_user_content("hello", [str(png)])
        assert result[1]["_meta"]["path"] == str(png)


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    def test_role_profiles_are_separate_and_memory_and_preferences_are_shared(self, tmp_path):
        home = tmp_path / "home"
        (home / "SOUL.md").write_text("Coordinator persona marker", encoding="utf-8")
        (home / "WORKER.md").write_text("Execution persona marker", encoding="utf-8")
        (home / "USER.md").write_text("Shared user preference marker", encoding="utf-8")
        builder = _builder(home)
        builder.memory.write_memory("Shared verified knowledge marker")
        for key, expected, excluded in (
            ("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "Coordinator persona marker", "Execution persona marker"),
            ("websocket:worker", "Execution persona marker", "Coordinator persona marker"),
        ):
            messages = builder.build_messages([], "Check memory", session_key=key)
            assert expected in messages[0]["content"]
            assert excluded not in messages[0]["content"]
            assert "Shared user preference marker" in messages[0]["content"]
            assert "Shared verified knowledge marker" in str(messages)
        internal = builder.build_system_prompt(session_key="dream:shared")
        assert "Coordinator persona marker" in internal and "Execution persona marker" in internal

    def test_includes_identity_section(self, tmp_path):
        builder = _builder(tmp_path / "home")
        result = builder.build_system_prompt()

        assert "## Runtime\n" in result
        assert "Agent profile: WORKER.md and USER.md" in result
        assert "History log: memory/history.jsonl" in result

    def test_default_identity_uses_relative_agent_paths(self, tmp_path):
        result = ContextBuilder(tmp_path / "home")._get_identity()

        assert "Agent profile: SOUL.md and USER.md" in result
        assert "History log: memory/history.jsonl" in result
        assert "Custom skills: skills/{skill-name}/SKILL.md" in result

    def test_selected_project_identity_keeps_agent_data_in_agent_workspace(self, tmp_path):
        agent_home = tmp_path / "agent-home" / "home"
        project = tmp_path / "project"
        agent_home.mkdir(parents=True)
        project.mkdir(parents=True)

        set_instance_path(agent_home.parent)
        result = ContextBuilder(agent_home)._get_identity(workspace=project)

        assert f"{agent_home.resolve()}/SOUL.md" in result
        assert f"{agent_home.resolve()}/SOUL.md" in result
        assert f"Custom skills: {agent_home.resolve()}/skills/" in result

    def test_includes_bootstrap_files(self, tmp_path):
        (tmp_path / "home" / "AGENTS.md").write_text("Be helpful and concise.", encoding="utf-8")
        builder = _builder(tmp_path / "home")
        result = builder.build_system_prompt()
        assert "Be helpful and concise." in result

    def test_includes_session_summary(self, tmp_path):
        builder = _builder(tmp_path / "home")
        summary = {
            "text": "Previous chat about Python.",
            "last_active": "2026-08-19T10:00:00",
        }
        result = builder.build_system_prompt(session_summary=summary)
        assert "Previous chat about Python." in result
        assert "[Archived Context Summary]" in result

    def test_nothing_summary_builds_the_prompt_without_archived_context(self, tmp_path):
        builder = _builder(tmp_path / "home")
        summary = {"text": "(nothing)", "last_active": "2026-08-19T10:00:00"}
        assert builder.build_system_prompt(session_summary=summary) == builder.build_system_prompt()

    def test_sections_separated_by_separator(self, tmp_path):
        (tmp_path / "home" / "AGENTS.md").write_text("Rules.", encoding="utf-8")
        builder = _builder(tmp_path / "home")
        summary = {"text": "Summary.", "last_active": "2026-08-19T10:00:00"}
        result = builder.build_system_prompt(session_summary=summary)
        assert "\n\n---\n\n" in result

    def test_no_bootstrap_no_summary(self, tmp_path):
        builder = _builder(tmp_path / "home")
        result = builder.build_system_prompt()
        assert "## AGENTS.md" not in result
        assert "[Archived Context Summary]" not in result


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def test_optional_arguments_are_keyword_only(self, tmp_path):
        builder = _builder(tmp_path / "home")

        with pytest.raises(TypeError):
            builder.build_system_prompt(["legacy-skill"])
        with pytest.raises(TypeError):
            builder.build_messages([], "hello", ["legacy-skill"])

    def test_basic_empty_history(self, tmp_path):
        builder = _builder(tmp_path / "home")
        messages = builder.build_messages([], "hello")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "hello" in str(messages[1]["content"])

    def test_public_builder_preserves_assistant_role_compatibility(self, tmp_path):
        from cirno_core.agent import ContextBuilder as PublicContextBuilder

        builder = PublicContextBuilder(tmp_path / "home")
        messages = builder.build_messages(
            history=[{"role": "assistant", "content": "previous result"}],
            current_message="subagent result",
            current_role="assistant",
            runtime_context_blocks=[
                RuntimeContextBlock(source="test", content="user-only runtime context"),
            ],
        )

        assert len(messages) == 2
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == "previous result\n\nsubagent result"
        assert "user-only runtime context" not in messages[-1]["content"]
        assert "_meta" not in messages[-1]

    def test_compatibility_builder_merges_system_role_without_history(self, tmp_path):
        builder = _builder(tmp_path / "home")

        messages = builder.build_messages([], "system event", current_role="system")

        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        assert str(messages[0]["content"]).endswith("system event")

    def test_explicit_skill_reference_loads_full_instructions_for_this_turn(self, tmp_path):
        skill_dir = tmp_path / "home" / "skills" / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: review\n"
            "description: Review changes.\n"
            "---\n\n"
            "# Review workflow\n\nFollow the unique review checklist.",
            encoding="utf-8",
        )
        builder = _builder(tmp_path / "home")

        messages = builder.build_messages([], "Please $review this patch and use $review carefully.")
        plain_messages = builder.build_messages([], "Please review this patch carefully.")

        system_prompt = messages[0]["content"]
        user_prompt = messages[-1]["content"]
        assert system_prompt == plain_messages[0]["content"]
        assert "Follow the unique review checklist." not in system_prompt
        assert "Please $review this patch" in user_prompt
        assert "[Active Skills — instructions for this user turn]" in user_prompt
        assert "### Skill: review" in user_prompt
        assert "Follow the unique review checklist." in user_prompt
        assert user_prompt.count("### Skill: review") == 1
        assert messages[-1]["_meta"]["runtime_context"]["sources"] == [
            "explicit_skills"
        ]

    def test_unknown_skill_reference_does_not_change_active_skills(self, tmp_path):
        messages = _builder(tmp_path / "home").build_messages([], "Keep the shell literal $HOME.")

        assert "# Active Skills" not in messages[0]["content"]

    def test_runtime_context_is_not_injected_by_default(self, tmp_path):
        builder = _builder(tmp_path / "home")
        messages = builder.build_messages([], "hello", channel="cli")
        user_msg = str(messages[-1]["content"])
        assert user_msg == "hello"

    def test_explicit_runtime_context_blocks_are_appended(self, tmp_path):
        builder = _builder(tmp_path / "home")
        messages = builder.build_messages(
            [],
            "please use @zoom tonight",
            runtime_context_blocks=[
                RuntimeContextBlock(
                    source="cli_apps",
                    content="CLI App Attachment: @zoom (installed; tool=run_cli_app).",
                ),
            ],
        )
        user_msg = str(messages[-1]["content"])

        assert "CLI App Attachment: @zoom" in user_msg
        assert "tool=run_cli_app" in user_msg
        assert user_msg.index("please use @zoom tonight") < user_msg.index(
            "CLI App Attachment: @zoom"
        )
        assert messages[-1]["_meta"]["runtime_context"]["sources"] == ["cli_apps"]

    def test_consecutive_same_role_merged(self, tmp_path):
        builder = _builder(tmp_path / "home")
        history = [{"role": "user", "content": "previous user message"}]
        messages = builder.build_messages(history, "new message")
        assert len(messages) == 2  # system + merged user
        assert "previous user message" in str(messages[1]["content"])
        assert "new message" in str(messages[1]["content"])

    def test_structured_transcript_preserves_fresh_turn_boundary(self, tmp_path):
        builder = _builder(tmp_path / "home")
        transcript = TranscriptInput(
            history=[{"role": "user", "content": "previous user message"}],
            current_message="new message",
        )

        messages = builder.build_transcript(transcript)

        assert [message["role"] for message in messages] == ["system", "user", "user"]
        assert messages[-2]["content"] == "previous user message"
        assert messages[-1]["content"] == "new message"
        assert transcript.message_count == 3

    def test_current_message_can_be_built_without_history_merge(self, tmp_path):
        builder = _builder(tmp_path / "home")
        current = builder.build_current_message(
            "new message",
            runtime_context_blocks=[
                RuntimeContextBlock(source="test", content="fresh context"),
            ],
        )

        assert current["role"] == "user"
        assert "new message" in current["content"]
        assert "fresh context" in current["content"]
        assert current["_meta"]["runtime_context"]["sources"] == ["test"]

    def test_system_input_keeps_runtime_provenance_in_transcript_and_compatibility(self, tmp_path):
        builder = _builder(tmp_path / "home")
        blocks = [RuntimeContextBlock(source="event", content="received_at: 2026-11-08T17:33:17Z")]
        transcript = TranscriptInput(history=[], current_message="wake", current_role="system", runtime_context_blocks=blocks)
        for messages in (builder.build_transcript(transcript), builder.build_messages([], "wake", current_role="system", runtime_context_blocks=blocks)):
            current = messages[-1]
            assert current["role"] == "system"
            assert "received_at: 2026-11-08T17:33:17Z" in current["content"]
            assert current["_meta"]["runtime_context"]["sources"] == ["event"]

    def test_different_role_appended(self, tmp_path):
        builder = _builder(tmp_path / "home")
        history = [{"role": "assistant", "content": "previous response"}]
        messages = builder.build_messages(history, "new message")
        assert len(messages) == 3  # system + assistant + user

    def test_media_with_history(self, tmp_path):
        png = tmp_path / "img.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        builder = _builder(tmp_path / "home")
        history = [{"role": "assistant", "content": "see this"}]
        messages = builder.build_messages(history, "check image", media=[str(png)])
        user_msg = messages[-1]["content"]
        assert isinstance(user_msg, list)
        assert any(b.get("type") == "image_url" for b in user_msg)


def test_memory_budget_and_checkpoint_restore_are_independent_of_dream(tmp_path, monkeypatch):
    from cirno_memory.repository import MemoryRepository
    home = tmp_path / "home"
    (home / "memory").mkdir(exist_ok=True)
    original = "shared overview\n" + ("bounded memory " * 4000) + "SHARED_TAIL_NOT_INJECTED"
    (home / "memory" / "MEMORY.md").write_text(original)
    repo = MemoryRepository(home)
    repo.checkpoint("websocket:long", "Goal: verify 0.00003125. Next: read node://n/result.tsv#L9", "test:milestone")
    monkeypatch.setattr(MemoryRepository, "search", lambda *a, **k: pytest.fail("No automatic recall on reply"))
    builder = ContextBuilder(tmp_path / "separate-workspace")
    builder.memory_context_tokens = 256
    builder.checkpoint_context_tokens = 256
    messages = builder.build_transcript(TranscriptInput(history=[], current_message="continue"), session_key="websocket:long")
    prompt = messages[0]["content"]
    assert "shared overview" not in prompt
    assert "shared overview" in messages[-1]["content"]
    assert "SHARED_TAIL_NOT_INJECTED" not in prompt
    assert "Next: read node://n/result.tsv#L9" not in prompt
    assert "Next: read node://n/result.tsv#L9" in messages[-1]["content"]
    assert (home / "memory" / "MEMORY.md").read_text() == original
    assert not (tmp_path / "separate-workspace" / "memory").exists()
