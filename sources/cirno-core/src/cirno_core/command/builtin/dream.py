"""Hidden compatibility spelling for context consolidation."""

from __future__ import annotations

from cirno_core.command.router import CommandContext


async def cmd_dream(ctx: CommandContext) -> None:
    """Legacy alias for the same session-bound consolidation operation."""
    from .control import cmd_compact

    await cmd_compact(ctx)
