"""Built-in command catalog and router registration."""

from .catalog import build_help_text, builtin_command_palette, builtin_command_starts_agent_turn
from .registration import register_builtin_commands

__all__ = [
    "build_help_text",
    "builtin_command_palette",
    "builtin_command_starts_agent_turn",
    "register_builtin_commands",
]
