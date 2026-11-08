"""Slash command routing and built-in handlers."""

from cirno_core.command.builtin.registration import register_builtin_commands
from cirno_core.command.router import CommandContext, CommandRouter

__all__ = ["CommandContext", "CommandRouter", "register_builtin_commands"]
