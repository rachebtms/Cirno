"""Built-in catalog commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from cirno_core.command.router import normalize_command_text

CommandLifecycle = Literal[
    "side_channel",
    "finalize_active_turn",
    "stop_active_turn",
    "agent_turn",
    "agent_turn_with_args",
]


USER_SHELL_COMMAND = "/__shell"


@dataclass(frozen=True)
class BuiltinCommandSpec:
    command: str
    title: str
    description: str
    icon: str
    arg_hint: str = ""
    lifecycle: CommandLifecycle = "side_channel"
    accepts_args: bool = False
    aliases: tuple[str, ...] = ()
    hidden: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "arg_hint": self.arg_hint,
            "lifecycle": self.lifecycle,
            "accepts_args": self.accepts_args,
            **({"aliases": list(self.aliases)} if self.aliases else {}),
            **({"hidden": True} if self.hidden else {}),
        }


BUILTIN_COMMAND_SPECS: tuple[BuiltinCommandSpec, ...] = (
    BuiltinCommandSpec(
        "/temporary",
        "Temporary conversation",
        "Choose temporary mode before creating a conversation.",
        "square-pen",
        "on|off",
        accepts_args=True,
    ),
    BuiltinCommandSpec(
        "/ptc",
        "PTC mode",
        "Choose programmatic tool calling before creating a conversation.",
        "code",
        "on|off",
        accepts_args=True,
    ),
    BuiltinCommandSpec(
        "/access",
        "Access mode",
        "Choose Default, independent AI review, or Full Access.",
        "shield",
        "default|review|full",
        accepts_args=True,
    ),
    BuiltinCommandSpec(
        "/resume",
        "Continue stopped task",
        "Continue the stopped request from saved context without replaying completed tool calls.",
        "play",
    ),
    BuiltinCommandSpec(
        "/clear",
        "Clear Router context",
        "Clear the Router conversation's context. This does not undo file or environment changes.",
        "eraser",
        lifecycle="finalize_active_turn",
    ),
    BuiltinCommandSpec(
        "/new",
        "New chat",
        "Reset this chat and start a fresh conversation.",
        "square-pen",
        lifecycle="finalize_active_turn",
    ),
    BuiltinCommandSpec(
        "/consolidate",
        "Consolidate context",
        "Save a task checkpoint and optional learning. Use /consolidate retry [source-id] to retry deferred learning without replacing the checkpoint.",
        "archive",
        "[retry [source-id]]",
        accepts_args=True,
        aliases=("/compact", "/dream"),
    ),
    BuiltinCommandSpec(
        "/stop",
        "Stop current task",
        "Cancel the active agent turn for this chat.",
        "square",
        lifecycle="stop_active_turn",
    ),
    BuiltinCommandSpec(
        "/restart",
        "Restart Cirno",
        "Restart the Cirno service.",
        "rotate-cw",
    ),
    BuiltinCommandSpec(
        "/status",
        "Show status",
        "Display runtime, provider, and channel status.",
        "activity",
    ),
    BuiltinCommandSpec(
        "/model",
        "Switch model preset",
        "Show or switch the active model preset.",
        "brain",
        "[preset]",
        accepts_args=True,
    ),
    BuiltinCommandSpec(
        "/history",
        "Show conversation history",
        "Print the last N persisted conversation messages.",
        "history",
        "[n]",
        accepts_args=True,
    ),
    BuiltinCommandSpec(
        "/goal",
        "Start long-running goal",
        "Tell the agent to treat the request as a long-running goal.",
        "activity",
        "<goal>",
        lifecycle="agent_turn_with_args",
        accepts_args=True,
    ),
    BuiltinCommandSpec(
        "/trigger",
        "Create named local trigger",
        "Create a named CLI trigger bound to this chat session.",
        "zap",
        "<name>",
        accepts_args=True,
    ),
    BuiltinCommandSpec(
        "/dream-log",
        "Legacy memory history",
        "Inspect saved legacy memory Git changes. Current record revisions are available in Memory.",
        "book-open",
        "[commit]",
        accepts_args=True,
    ),
    BuiltinCommandSpec(
        "/dream-restore",
        "Restore legacy memory change",
        "List or undo a saved legacy memory Git change. Preview it with /dream-log first.",
        "undo-2",
        "[commit]",
        accepts_args=True,
    ),
    BuiltinCommandSpec(
        "/dream-prompt", "Legacy Dream instructions", "Dream has been merged into context consolidation.",
        "file-text", "[init]", accepts_args=True, hidden=True,
    ),
    BuiltinCommandSpec(
        "/pairing", "Legacy channel pairing", "Use the channel's current owner binding in Settings.",
        "shield", "[action]", accepts_args=True, hidden=True,
    ),
    BuiltinCommandSpec(
        "/skill",
        "List skills",
        "List all enabled skills available to the agent.",
        "wrench",
    ),
    BuiltinCommandSpec(
        "/help",
        "Show help",
        "List available slash commands.",
        "circle-help",
    ),
)


def builtin_command_palette(*, include_hidden: bool = False) -> list[dict[str, Any]]:
    """Return structured command metadata for UI command palettes."""
    return [spec.as_dict() for spec in BUILTIN_COMMAND_SPECS if include_hidden or not spec.hidden]


def builtin_command_starts_agent_turn(text: str) -> bool:
    """Return whether WebUI ingress should expect a normal agent lifecycle."""
    normalized = normalize_command_text(text)
    command, separator, args = normalized.partition(" ")
    spec = next(
        (item for item in BUILTIN_COMMAND_SPECS if command.lower() in (item.command, *item.aliases)),
        None,
    )
    if spec is None:
        return True
    if separator and not spec.accepts_args:
        return False  # Registered argument errors are control replies, never model turns.
    if spec.lifecycle == "agent_turn":
        return True
    return spec.lifecycle == "agent_turn_with_args" and bool(args.strip())


def build_help_text() -> str:
    """Build canonical help text shared across channels."""
    lines = ["❄️ Cirno commands:"]
    for spec in BUILTIN_COMMAND_SPECS:
        if spec.hidden:
            continue
        command = spec.command
        if spec.arg_hint:
            command = f"{command} {spec.arg_hint}"
        lines.append(f"{command} — {spec.description}")
    return "\n".join(lines)
