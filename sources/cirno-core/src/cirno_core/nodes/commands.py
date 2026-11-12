"""Separate a remote program's exit status from SSH transport failures."""

from __future__ import annotations

import shlex
import re
from dataclasses import dataclass
from uuid import uuid4

_TRANSIENT_CONNECTION = re.compile(r"connection (?:reset|refused|timed out|closed)|closed by remote host|broken pipe|server not responding", re.IGNORECASE)
_PERMANENT_CONNECTION = re.compile(r"permission denied|authentication failed|host key verification failed|remote host identification has changed|bad configuration option|bad owner or permissions", re.IGNORECASE)


class SSHProcessError(RuntimeError):
    def __init__(self, result: CommandResult):
        self.result = result
        super().__init__(f"OpenSSH exited with {result.exit_code}\n{result.output}".rstrip())

    @property
    def reconnectable(self) -> bool:
        return self.result.exit_code == 255 and not _PERMANENT_CONNECTION.search(self.result.stderr) and bool(_TRANSIENT_CONNECTION.search(self.result.stderr))


class CommandOutcomeUnknown(RuntimeError):
    def __init__(self, result: CommandResult):
        self.result = result
        self.message = (
            "SSH command outcome unconfirmed: no complete exit-status receipt was received. "
            "The command may already have run; do not repeat it automatically."
        )
        if result.connection_warning:
            self.message += " " + result.connection_warning
        super().__init__(f"{self.message}\nSSH exit code: {result.exit_code}\n{result.output}".rstrip())

    def to_dict(self) -> dict:
        return {"state": "execution_unknown", "resubmit_safe": False, "ssh_exit_code": self.result.exit_code,
                "stdout": self.result.stdout, "stderr": self.result.stderr, "error": self.message}


class SSHCommandTimeout(TimeoutError):
    def __init__(self, result: CommandResult):
        self.result = result
        super().__init__(result.connection_warning)


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    connection_warning: str | None = None

    @property
    def output(self) -> str:
        return self.stdout + (("\n" if self.stdout else "") + self.stderr if self.stderr else "")

    def checked(self) -> CommandResult:
        if self.exit_code:
            raise SSHProcessError(self)
        return self

    def to_dict(self) -> dict[str, str | int]:
        return {"stdout": self.stdout, "stderr": self.stderr, "exit_code": self.exit_code,
                **({"connection_warning": self.connection_warning} if self.connection_warning else {})}


def command_envelope(script: str) -> tuple[str, str]:
    marker = "CIRNO_COMMAND_EXIT_" + uuid4().hex + ":"
    # The command runs in its own shell, so `exit`, `exec` and `set -e` cannot
    # bypass the outer status receipt. Even program exit 255 is unambiguous.
    wrapped = script + f'; cirno_status=$?; printf "\\n{marker}%s\\n" "$cirno_status" >&2; exit 0'
    return "sh -c " + shlex.quote(wrapped), marker


def command_result(transport: CommandResult, marker: str) -> CommandResult:
    stderr, separator, status = transport.stderr.rpartition("\n" + marker)
    code, newline, diagnostics = status.partition("\n")
    if not separator or not newline or not code.isdigit() or not 0 <= int(code) <= 255:
        raise CommandOutcomeUnknown(transport)
    # A complete receipt proves the program ended even if the tunnel closed
    # before SSH finished its own shutdown. Retain any subsequent diagnostics.
    reason = transport.connection_warning or f"SSH exit {transport.exit_code}"
    warning = (f"SSH session ended after receiving the remote command completion receipt ({reason.rstrip('.')}). "
               "The command result is confirmed; do not repeat it.") if transport.exit_code or transport.connection_warning else None
    stderr += ("\n" if stderr and diagnostics and not stderr.endswith("\n") else "") + diagnostics
    return CommandResult(transport.stdout, stderr, int(code), warning)
