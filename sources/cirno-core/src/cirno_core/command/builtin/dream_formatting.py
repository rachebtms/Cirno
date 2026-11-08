"""Built-in dream formatting commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cirno_core.utils.gitstore import CommitInfo


def dream_no_input_message() -> str:
    return "\n".join(
        [
            "Dream has no eligible memory batch to process right now.",
            "Compaction adds new entries from `memory/history.jsonl` to the persistent queue.",
            "Use `/compact` to archive this conversation, or review pending and failed batches in Settings → Dream consolidation.",
            "A batch may also be leased by another run or waiting for its retry delay. Use `/dream-prompt` to inspect consolidation instructions.",
        ]
    )


def changed_memory_files(diff: str) -> list[str]:
    """Extract changed file paths from a unified diff."""
    files: list[str] = []
    seen: set[str] = set()
    for line in diff.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        path = parts[3]
        if path.startswith("b/"):
            path = path[2:]
        if path in seen:
            continue
        seen.add(path)
        files.append(path)
    return files


def format_changed_files(diff: str) -> str:
    files = changed_memory_files(diff)
    if not files:
        return "No tracked memory files changed."
    return ", ".join(f"`{path}`" for path in files)


DREAM_COMMIT_PREFIX = "dream:"


def format_dream_log(
    commit: CommitInfo,
    diff: str,
    *,
    requested_sha: str | None = None,
) -> str:
    files_line = format_changed_files(diff)
    lines = [
        "## Dream Update",
        "",
        "Here is the selected Dream memory change."
        if requested_sha
        else "Here is the latest Dream memory change.",
        "",
        f"- Commit: `{commit.sha}`",
        f"- Time: {commit.timestamp}",
        f"- Changed files: {files_line}",
    ]
    if diff:
        lines.extend(
            [
                "",
                f"Use `/dream-restore {commit.sha}` to undo this change.",
                "",
                "```diff",
                diff.rstrip(),
                "```",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Dream recorded this version, but there is no file diff to display.",
            ]
        )
    return "\n".join(lines)


def format_dream_restore_choices(commits: list[CommitInfo]) -> str:
    lines = [
        "## Dream Restore",
        "",
        "Choose a Dream memory version to restore. Latest first:",
        "",
    ]
    for c in commits:
        lines.append(f"- `{c.sha}` {c.timestamp} - {c.subject()}")
    lines.extend(
        [
            "",
            "Preview a version with `/dream-log <sha>` before restoring it.",
            "Restore a version with `/dream-restore <sha>`.",
        ]
    )
    return "\n".join(lines)
