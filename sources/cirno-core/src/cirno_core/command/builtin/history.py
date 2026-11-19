"""Built-in history commands."""

from __future__ import annotations

from typing import Any, cast

from cirno_core.bus.events import OutboundMessage
from cirno_core.command.router import CommandContext
from cirno_core.runtime.context import public_history_message
from cirno_core.session.history_visibility import is_hidden_history_message
from cirno_core.utils.model_messages import content_with_media_breadcrumbs

_HISTORY_DEFAULT_COUNT = 10


_HISTORY_MAX_COUNT = 50


_HISTORY_MAX_CONTENT_CHARS = 200


def _format_history_message(msg: dict[str, Any]) -> str | None:
    """Format a single history message for display. Returns None to skip."""
    role = msg.get("role")
    if role not in ("user", "assistant") or is_hidden_history_message(msg):
        return None
    visible = public_history_message(msg)
    content = content_with_media_breadcrumbs(role, visible.get("content") or "", visible.get("media"))
    if isinstance(content, list):
        parts = [
            text
            for block in cast(list[object], content)
            if (item := cast(dict[str, Any], block) if isinstance(block, dict) else None)
            and item.get("type") == "text"
            and isinstance(text := item.get("text"), str)
        ]
        content = " ".join(parts)
    content = str(content).strip()
    if not content:
        return None
    if len(content) > _HISTORY_MAX_CONTENT_CHARS:
        content = content[:_HISTORY_MAX_CONTENT_CHARS] + "…"
    label = "👤 You" if role == "user" else "🤖 Bot"
    return f"{label}: {content}"


async def cmd_history(ctx: CommandContext) -> OutboundMessage:
    """Show the last N messages of the current session (default 10, max 50).

    Usage: /history [count]
    """
    count = _HISTORY_DEFAULT_COUNT
    if ctx.args.strip():
        try:
            count = max(1, min(int(ctx.args.strip()), _HISTORY_MAX_COUNT))
        except ValueError:
            return OutboundMessage(
                channel=ctx.msg.channel,
                chat_id=ctx.msg.chat_id,
                content="Usage: /history [count] — e.g. /history 5 (default: 10, max: 50)",
                metadata=dict(ctx.msg.metadata or {}),
            )

    session = ctx.session or await ctx.loop.sessions.state.get(ctx.key)
    recent: list[str] = []
    for message in reversed(session.messages):
        formatted = _format_history_message(message)
        if formatted is not None:
            recent.append(formatted)
            if len(recent) >= count:
                break
    recent.reverse()

    if not recent:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="No conversation history yet.",
            metadata=dict(ctx.msg.metadata or {}),
        )

    header = f"Last {len(recent)} message(s):\n"
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=header + "\n".join(recent),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )
