"""Built-in registration commands."""

from __future__ import annotations

from cirno_core.command.router import CommandRouter

from .capabilities import cmd_help, cmd_skill, cmd_trigger
from .catalog import USER_SHELL_COMMAND
from .control import (
    cmd_access,
    cmd_clear,
    cmd_compact,
    cmd_draft_mode,
    cmd_goal,
    cmd_new,
    cmd_resume,
    cmd_stop,
    cmd_user_shell,
)
from .dream import cmd_dream, cmd_dream_prompt
from .dream_history import cmd_dream_log, cmd_dream_restore
from .history import cmd_history
from .models import cmd_model
from .service import cmd_restart, cmd_status


def register_builtin_commands(router: CommandRouter) -> None:
    """Register the default set of slash commands."""
    router.exact("/access", cmd_access)
    router.prefix("/access ", cmd_access)
    for name in ("/temporary", "/ptc"):
        router.exact(name, cmd_draft_mode)
        router.prefix(name + " ", cmd_draft_mode)
    router.priority("/stop", cmd_stop)
    router.priority("/resume", cmd_resume)
    router.priority("/clear", cmd_clear)
    router.priority("/restart", cmd_restart)
    router.priority("/status", cmd_status)
    router.exact("/new", cmd_new)
    router.exact("/compact", cmd_compact, session_queue=True)
    router.exact("/status", cmd_status)
    router.exact("/model", cmd_model)
    router.prefix("/model ", cmd_model)
    router.exact("/history", cmd_history)
    router.prefix("/history ", cmd_history)
    router.exact("/goal", cmd_goal)
    router.prefix("/goal ", cmd_goal)
    router.exact("/trigger", cmd_trigger)
    router.prefix("/trigger ", cmd_trigger)
    router.exact("/dream", cmd_dream)
    router.exact("/dream-log", cmd_dream_log)
    router.prefix("/dream-log ", cmd_dream_log)
    router.exact("/dream-restore", cmd_dream_restore)
    router.prefix("/dream-restore ", cmd_dream_restore)
    router.exact("/dream-prompt", cmd_dream_prompt)
    router.prefix("/dream-prompt ", cmd_dream_prompt)
    router.exact("/skill", cmd_skill)
    router.exact("/help", cmd_help)
    router.exact(USER_SHELL_COMMAND, cmd_user_shell)
    router.prefix(f"{USER_SHELL_COMMAND} ", cmd_user_shell)
