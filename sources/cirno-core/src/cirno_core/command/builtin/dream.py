"""Built-in dream commands."""

from __future__ import annotations

from cirno_core.bus.events import OutboundMessage
from cirno_core.command.router import CommandContext
from cirno_core.memory.dream_run import run_dream
from cirno_core.utils.workspace_prompts import initialize_workspace_prompt

from .dream_formatting import dream_no_input_message


async def cmd_dream(ctx: CommandContext) -> OutboundMessage:
    """Run a manual batch through the shared, tracked Dream lifecycle."""

    async def run_and_report() -> None:
        try:
            result = await run_dream(ctx.loop, commit_subject="dream: manual run")
        except Exception as error:
            await ctx.loop.bus.publish_outbound(
                OutboundMessage(
                    channel=ctx.msg.channel,
                    chat_id=ctx.msg.chat_id,
                    content=f"Dream failed: {error}",
                    metadata=dict(ctx.msg.metadata),
                )
            )
            raise
        if result.status == "empty":
            content = dream_no_input_message()
        elif result.status == "completed":
            suffix = "; no memory changes" if not result.changed else ""
            content = f"Dream completed in {result.elapsed:.1f}s{suffix}."
        else:
            content = (
                f"Dream did not complete after {result.elapsed:.1f}s ({result.reason}); "
                "memory cursor was not advanced."
            )
        if result.commit:
            content += f" (commit {result.commit})"
        await ctx.loop.bus.publish_outbound(
            OutboundMessage(
                channel=ctx.msg.channel,
                chat_id=ctx.msg.chat_id,
                content=content,
                metadata={**ctx.msg.metadata, "render_as": "text"},
            )
        )

    ctx.loop.schedule_background(run_and_report())
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="Dreaming...",
    )


async def cmd_dream_prompt(ctx: CommandContext) -> OutboundMessage:
    """Show or set up the workspace Dream memory instructions."""
    store = ctx.loop.context.memory
    path = store.dream.prompt_file
    display_path = path.relative_to(store.workspace).as_posix()
    args = ctx.args.strip().lower()

    if args == "init":
        if not initialize_workspace_prompt(path, store.dream.default_prompt()):
            content = (
                f"Dream memory instructions already exist at `{display_path}`.\n\n"
                "Edit that file, or delete/empty it to return to cirno's default."
            )
        else:
            content = (
                f"Created Dream memory instructions at `{display_path}`.\n\n"
                "Edit that file to teach Dream how to organize memory. "
                "This fully replaces cirno's default Dream guide in Home. "
                "Delete or empty it to return to cirno's default."
            )
    elif args:
        content = "Usage: /dream-prompt [init]"
    elif store.dream.has_prompt_override():
        content = (
            "Dream memory instructions: custom in Home\n\n"
            f"- Path: `{display_path}`\n"
            "- Delete or empty this file to return to cirno's default."
        )
    else:
        content = (
            "Dream memory instructions: cirno default\n\n"
            f"- Editable file: `{display_path}`\n"
            "- Run `/dream-prompt init` to create an editable copy."
        )

    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )
