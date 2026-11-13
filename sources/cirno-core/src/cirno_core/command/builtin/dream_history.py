"""Built-in dream history commands."""

from __future__ import annotations

from cirno_core.bus.events import OutboundMessage
from cirno_core.command.router import CommandContext

from .dream_formatting import (
    DREAM_COMMIT_PREFIX,
    format_changed_files,
    format_dream_log,
    format_dream_restore_choices,
)


async def cmd_dream_log(ctx: CommandContext) -> OutboundMessage:
    """Show what the last Dream changed.

    Default: diff of the latest Dream commit versus its parent.
    With /dream-log <sha>: diff of that specific commit.
    """
    if len(ctx.args.split()) > 1:
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content="Usage: /dream-log [commit]",
            metadata={**ctx.msg.metadata, "render_as": "text"},
        )
    store = ctx.loop.consolidator.store
    git = store.git

    if not git.is_initialized():
        if store.journal.get_last_dream_cursor() == 0:
            msg = (
                "Dream has not run yet. Use Context consolidation in Settings, or `/consolidate` in a conversation.\n\n"
                "Use Settings → Context consolidation for context and learning settings."
            )
        else:
            msg = "Dream history is not available because memory versioning is not initialized."
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=msg,
            metadata={**ctx.msg.metadata, "render_as": "text"},
        )

    args = ctx.args.strip()

    if args:
        # Show diff of a specific commit
        sha = args.split()[0]
        result = git.show_commit_diff(sha)
        if not result:
            content = (
                f"Couldn't find Dream change `{sha}`.\n\n"
                "Use `/dream-restore` to list recent versions, "
                "or `/dream-log` to inspect the latest one."
            )
        else:
            commit, diff = result
            content = format_dream_log(commit, diff, requested_sha=sha)
    else:
        # Default: show the latest Dream commit's diff
        commits = git.log(max_entries=1, message_prefix=DREAM_COMMIT_PREFIX)
        result = (
            git.show_commit_diff(
                commits[0].sha,
                max_entries=1,
                message_prefix=DREAM_COMMIT_PREFIX,
            )
            if commits
            else None
        )
        if result:
            commit, diff = result
            content = format_dream_log(commit, diff)
        else:
            content = (
                "Dream memory has no saved versions yet.\n\n"
                "Use Settings → Context consolidation for context and learning settings."
            )

    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**ctx.msg.metadata, "render_as": "text"},
    )


async def cmd_dream_restore(ctx: CommandContext) -> OutboundMessage:
    """Restore memory files from a previous dream commit.

    Usage:
        /dream-restore          — list recent commits
        /dream-restore <sha>    — revert a specific commit
    """
    if len(ctx.args.split()) > 1:
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content="Usage: /dream-restore [commit]",
            metadata={**ctx.msg.metadata, "render_as": "text"},
        )
    if ctx.args.strip():
        from .control import _human_control_required

        denied = _human_control_required(ctx)
        if denied is not None:
            return denied
    store = ctx.loop.consolidator.store
    git = store.git
    if not git.is_initialized():
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Dream history is not available because memory versioning is not initialized.",
            metadata={**ctx.msg.metadata, "render_as": "text"},
        )

    args = ctx.args.strip()
    if not args:
        # Show recent Dream commits for the user to pick
        commits = git.log(max_entries=10, message_prefix=DREAM_COMMIT_PREFIX)
        if not commits:
            content = "Dream memory has no saved versions to restore yet."
        else:
            content = format_dream_restore_choices(commits)
    else:
        sha = args.split()[0]
        result = git.show_commit_diff(sha, message_prefix=DREAM_COMMIT_PREFIX)
        if not result:
            content = (
                f"Couldn't restore Dream change `{sha}`.\n\n"
                "Only Dream memory versions can be restored. "
                "Use `/dream-restore` to list recent versions."
            )
        else:
            changed_files = format_changed_files(result[1])
            new_sha = git.revert(sha, message_prefix=DREAM_COMMIT_PREFIX)
            if new_sha:
                content = (
                    f"Restored Dream memory to the state before `{sha}`.\n\n"
                    f"- New safety commit: `{new_sha}`\n"
                    f"- Restored files: {changed_files}\n\n"
                    f"Use `/dream-log {new_sha}` to inspect the restore diff."
                )
            else:
                content = (
                    f"Couldn't restore Dream change `{sha}`.\n\n"
                    "It may be the first saved version with no earlier state to restore."
                )
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**ctx.msg.metadata, "render_as": "text"},
    )
