from __future__ import annotations

from types import SimpleNamespace

import pytest

from cirno_core.bus.events import InboundMessage
from cirno_core.command.builtin.catalog import build_help_text, builtin_command_palette
from cirno_core.command.builtin.dream import cmd_dream
from cirno_core.command.builtin.dream_history import cmd_dream_log, cmd_dream_restore
from cirno_core.command.router import CommandContext
from cirno_core.utils.gitstore import CommitInfo


class _FakeStore:
    def __init__(self, git, last_dream_cursor=1):
        self.git = git
        self.journal = SimpleNamespace(get_last_dream_cursor=lambda: last_dream_cursor)


class _FakeGit:
    def __init__(
        self,
        *,
        initialized: bool = True,
        commits: list[CommitInfo] | None = None,
        diff_map: dict[str, tuple[CommitInfo, str] | None] | None = None,
        revert_result: str | None = None,
    ):
        self._initialized = initialized
        self._commits = commits or []
        self._diff_map = diff_map or {}
        self._revert_result = revert_result
        self.revert_calls: list[tuple[str, str | None]] = []

    def is_initialized(self) -> bool:
        return self._initialized

    def log(
        self,
        max_entries: int = 20,
        message_prefix: str | None = None,
    ) -> list[CommitInfo]:
        commits = self._commits
        if message_prefix is not None:
            commits = [c for c in commits if c.message.startswith(message_prefix)]
        return commits[:max_entries]

    def show_commit_diff(
        self,
        sha: str,
        max_entries: int = 20,
        message_prefix: str | None = None,
    ):
        result = self._diff_map.get(sha)
        if (
            result
            and message_prefix is not None
            and not result[0].message.startswith(message_prefix)
        ):
            return None
        return result

    def revert(self, sha: str, *, message_prefix: str | None = None) -> str | None:
        self.revert_calls.append((sha, message_prefix))
        return self._revert_result

    def auto_commit(self, message: str) -> str | None:
        return None


def _make_ctx(
    raw: str, git: _FakeGit, *, args: str = "", last_dream_cursor: int = 1
) -> CommandContext:
    msg = InboundMessage(channel="cli", sender_id="u1", chat_id="direct", content=raw)
    store = _FakeStore(git, last_dream_cursor=last_dream_cursor)
    loop = SimpleNamespace(consolidator=SimpleNamespace(store=store))
    return CommandContext(msg=msg, session=None, key=msg.session_key, raw=raw, args=args, loop=loop, is_user_turn=True)


@pytest.mark.asyncio
async def test_dream_log_latest_is_more_user_friendly() -> None:
    commit = CommitInfo(
        sha="abcd1234", message="dream: 2026-04-04, 2 change(s)", timestamp="2026-04-04 12:00"
    )
    diff = "diff --git a/SOUL.md b/SOUL.md\n--- a/SOUL.md\n+++ b/SOUL.md\n@@ -1 +1 @@\n-old\n+new\n"
    git = _FakeGit(commits=[commit], diff_map={commit.sha: (commit, diff)})

    out = await cmd_dream_log(_make_ctx("/dream-log", git))

    assert "## Dream Update" in out.content
    assert "Here is the latest Dream memory change." in out.content
    assert "- Commit: `abcd1234`" in out.content
    assert "- Changed files: `SOUL.md`" in out.content
    assert "Use `/dream-restore abcd1234` to undo this change." in out.content
    assert "```diff" in out.content


@pytest.mark.asyncio
async def test_dream_log_latest_skips_non_dream_commit() -> None:
    backup = CommitInfo(
        sha="bbbb2222",
        message="backup: workspace snapshot",
        timestamp="2026-04-04 13:00",
    )
    dream = CommitInfo(
        sha="abcd1234",
        message="dream: latest",
        timestamp="2026-04-04 12:00",
    )
    diff = "diff --git a/SOUL.md b/SOUL.md\n"
    git = _FakeGit(
        commits=[backup, dream],
        diff_map={dream.sha: (dream, diff), backup.sha: (backup, "unrelated diff")},
    )

    out = await cmd_dream_log(_make_ctx("/dream-log", git))

    assert "`abcd1234`" in out.content
    assert "`bbbb2222`" not in out.content


@pytest.mark.asyncio
async def test_dream_log_missing_commit_guides_user() -> None:
    git = _FakeGit(diff_map={})

    out = await cmd_dream_log(_make_ctx("/dream-log deadbeef", git, args="deadbeef"))

    assert "Couldn't find Dream change `deadbeef`." in out.content
    assert "Use `/dream-restore` to list recent versions" in out.content


@pytest.mark.asyncio
async def test_dream_log_before_first_run_is_clear() -> None:
    git = _FakeGit(initialized=False)

    out = await cmd_dream_log(_make_ctx("/dream-log", git, last_dream_cursor=0))

    assert "Dream has not run yet." in out.content
    assert "Context consolidation" in out.content
    assert "Settings" in out.content


@pytest.mark.asyncio
async def test_dream_log_without_saved_versions_mentions_prompt_command() -> None:
    git = _FakeGit(initialized=True, commits=[])

    out = await cmd_dream_log(_make_ctx("/dream-log", git))

    assert "Dream memory has no saved versions yet." in out.content
    assert "Settings" in out.content


@pytest.mark.asyncio
async def test_dream_restore_lists_versions_with_next_steps() -> None:
    commits = [
        CommitInfo(sha="abcd1234", message="dream: latest", timestamp="2026-04-04 12:00"),
        CommitInfo(sha="cccc3333", message="backup: workspace", timestamp="2026-04-04 10:00"),
        CommitInfo(sha="bbbb2222", message="dream: older", timestamp="2026-04-04 08:00"),
    ]
    git = _FakeGit(commits=commits)

    out = await cmd_dream_restore(_make_ctx("/dream-restore", git))

    assert "## Dream Restore" in out.content
    assert "Choose a Dream memory version to restore." in out.content
    assert "`abcd1234` 2026-04-04 12:00 - dream: latest" in out.content
    assert "`bbbb2222` 2026-04-04 08:00 - dream: older" in out.content
    assert "backup: workspace" not in out.content
    assert "Preview a version with `/dream-log <sha>`" in out.content
    assert "Restore a version with `/dream-restore <sha>`." in out.content


@pytest.mark.asyncio
async def test_dream_restore_success_mentions_files_and_followup() -> None:
    commit = CommitInfo(sha="abcd1234", message="dream: latest", timestamp="2026-04-04 12:00")
    diff = (
        "diff --git a/SOUL.md b/SOUL.md\n"
        "--- a/SOUL.md\n"
        "+++ b/SOUL.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/memory/MEMORY.md b/memory/MEMORY.md\n"
        "--- a/memory/MEMORY.md\n"
        "+++ b/memory/MEMORY.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    git = _FakeGit(
        diff_map={commit.sha: (commit, diff)},
        revert_result="eeee9999",
    )

    out = await cmd_dream_restore(_make_ctx("/dream-restore abcd1234", git, args="abcd1234"))

    assert "Restored Dream memory to the state before `abcd1234`." in out.content
    assert "- New safety commit: `eeee9999`" in out.content
    assert "- Restored files: `SOUL.md`, `memory/MEMORY.md`" in out.content
    assert "Use `/dream-log eeee9999` to inspect the restore diff." in out.content
    assert git.revert_calls == [("abcd1234", "dream:")]


@pytest.mark.asyncio
async def test_dream_restore_rejects_non_dream_commit_clearly() -> None:
    commit = CommitInfo(
        sha="cccc3333",
        message="backup: workspace",
        timestamp="2026-04-04 10:00",
    )
    git = _FakeGit(
        diff_map={commit.sha: (commit, "unrelated diff")},
        revert_result="eeee9999",
    )

    out = await cmd_dream_restore(_make_ctx("/dream-restore cccc3333", git, args="cccc3333"))

    assert "Only Dream memory versions can be restored." in out.content
    assert "Use `/dream-restore` to list recent versions." in out.content
    assert git.revert_calls == []


@pytest.mark.parametrize("command", ["/consolidate", "/compact", "/dream"])
def test_unified_command_and_legacy_aliases_are_session_queued_and_have_one_palette_entry(command):
    from cirno_core.command.router import CommandRouter
    from cirno_core.command.builtin.registration import register_builtin_commands

    router = CommandRouter()
    register_builtin_commands(router)
    assert router.requires_session_queue(command)
    assert router.is_dispatchable_command(command)
    commands = {item["command"] for item in builtin_command_palette()}
    assert "/consolidate" in commands
    assert not {"/compact", "/dream", "/dream-prompt"} & commands
    assert "/consolidate" in build_help_text()


async def test_legacy_dream_function_awaits_the_shared_operation_without_background_work(
    monkeypatch,
):
    from unittest.mock import AsyncMock, MagicMock

    compact = AsyncMock()
    monkeypatch.setattr("cirno_core.command.builtin.control.cmd_compact", compact)
    ctx = MagicMock()
    await cmd_dream(ctx)
    compact.assert_awaited_once_with(ctx)
    ctx.loop.schedule_background.assert_not_called()


@pytest.mark.parametrize("handler, command", [(cmd_dream_log, "/dream-log"), (cmd_dream_restore, "/dream-restore")])
async def test_history_commands_preserve_control_correlation_and_validate_all_arguments(handler, command):
    git = _FakeGit()
    ctx = _make_ctx(command, git)
    ctx.msg.metadata = {"turn_id": "control-turn"}
    result = await handler(ctx)
    assert result.metadata == {"turn_id": "control-turn", "render_as": "text"}
    ctx.args = "abc123 unexpected"
    result = await handler(ctx)
    assert "Usage:" in result.content
    assert git.revert_calls == []


async def test_agent_input_cannot_restore_legacy_memory():
    git = _FakeGit()
    ctx = _make_ctx("/dream-restore abc123", git, args="abc123")
    ctx.is_user_turn = False
    result = await cmd_dream_restore(ctx)
    assert "direct user request" in result.content
    assert git.revert_calls == []
