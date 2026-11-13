"""Built-in capabilities commands."""

from __future__ import annotations

from cirno_core.bus.events import OutboundMessage
from cirno_core.command.router import CommandContext

from .catalog import build_help_text


async def cmd_retired(ctx: CommandContext) -> OutboundMessage:
    """Keep retired command spellings out of the model while explaining their replacements."""
    command = ctx.raw.split(maxsplit=1)[0].lower()
    content = {
        "/pairing": "Generic channel pairing was retired. Bind your personal Telegram account with the owner PIN in Settings → Telegram.",
        "/dream-prompt": "Dream was merged into Context consolidation. The old prompts/dream.md override is not used by the current checkpoint/learning pipeline. Use Settings → Context consolidation to configure learning and retries; /consolidate runs it in this conversation.",
    }[command]
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id, content=content,
        metadata={**ctx.msg.metadata, "render_as": "text"},
    )


async def cmd_skill(ctx: CommandContext) -> OutboundMessage:
    """List all enabled skills (name and description only)."""
    loop = ctx.loop
    skills = loop.context.skills.list_skills(filter_unavailable=False)
    if not skills:
        content = "No skills available."
    else:
        lines = [f"Available skills ({len(skills)}):", ""]
        for entry in skills:
            desc = loop.context.skills.get_skill_description(entry["name"])
            lines.append(f"- **{entry['name']}** — {desc}")
        content = "\n".join(lines)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata=dict(ctx.msg.metadata or {}),
    )


async def cmd_trigger(ctx: CommandContext) -> OutboundMessage:
    """Create a local trigger bound to the current session."""
    name = ctx.args.strip()
    if not name:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=(
                "Usage: /trigger <name>\n\nCreate a named local trigger bound to this chat session."
            ),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    from cirno_core.triggers.local_store import LocalTriggerStore

    loop = ctx.loop
    store = loop.local_trigger_store
    if store is None:
        from cirno_core.config.paths import get_runtime_subdir

        store = LocalTriggerStore(get_runtime_subdir("triggers"))

    session_key = ctx.key
    trigger = store.create(
        name=name,
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        session_key=session_key,
        sender_id="trigger",
        origin_metadata=dict(ctx.msg.metadata or {}),
    )
    from cirno_core.triggers.invocation import invocation

    command = invocation(store.root, trigger.id)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=(f"Trigger created: {trigger.name}\nID: {trigger.id}\n\nCommand:\n{command}"),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_help(ctx: CommandContext) -> OutboundMessage:
    """Return available slash commands."""
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_help_text(),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )
