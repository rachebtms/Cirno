"""Built-in models commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cirno_core.bus.events import OutboundMessage
from cirno_core.command.router import CommandContext

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.session.model import Session


def _format_preset_names(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names) if names else "(none configured)"


def _model_preset_names(loop: AgentLoop) -> list[str]:
    names = set(loop.model_presets)
    names.add("default")
    return ["default", *sorted(name for name in names if name != "default")]


def _command_error_message(exc: Exception) -> str:
    return str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)


async def _model_command_status(loop: AgentLoop, session: Session) -> str:
    names = _model_preset_names(loop)
    try:
        runtime = await loop.runtime_for_session(session, recover_removed=False)
    except (KeyError, ValueError) as exc:
        return "\n".join(
            [
                "## Model",
                f"- Current selection error: {_command_error_message(exc)}",
                f"- Available presets: {_format_preset_names(names)}",
                "- Switch with `/model <preset>`.",
            ]
        )
    active = runtime.model_preset or "default"
    return "\n".join(
        [
            "## Model",
            f"- Current model: `{runtime.model}`",
            f"- Current preset: `{active}`",
            f"- Available presets: {_format_preset_names(names)}",
        ]
    )


async def cmd_model(ctx: CommandContext) -> OutboundMessage:
    """Show or switch model presets."""
    loop = ctx.loop
    args = ctx.args.strip()
    metadata = {**dict(ctx.msg.metadata or {}), "render_as": "text"}

    if not args:
        session = ctx.session or await loop.sessions.state.get(ctx.key)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=await _model_command_status(loop, session),
            metadata=metadata,
        )

    name = args
    if name not in loop.model_presets:
        matches = [
            identity
            for identity, preset in loop.model_presets.items()
            if (preset.display_name or identity).casefold() == name.casefold()
        ]
        if len(matches) == 1:
            name = matches[0]
    try:
        runtime = await loop.set_session_model_preset(ctx.key, name)
    except (KeyError, ValueError) as exc:
        names = _model_preset_names(loop)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=(
                f"Could not switch model preset: {_command_error_message(exc)}\n\n"
                f"Available presets: {_format_preset_names(names)}"
            ),
            metadata=metadata,
        )

    max_tokens = runtime.generation.max_tokens
    lines = [
        f"Switched model preset to `{runtime.model_preset}`.",
        "- Scope: current session",
        f"- Model: `{runtime.model}`",
        f"- Context window: {runtime.context_window_tokens}",
    ]
    lines.append(f"- Max output tokens: {max_tokens}")
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="\n".join(lines),
        metadata=metadata,
    )
