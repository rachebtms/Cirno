"""Command authorization for workspace, network and configured command patterns."""

from __future__ import annotations

import os
import re
from pathlib import Path

from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.sandbox import normalize_bind_paths
from cirno_core.agent.tools.shell.tokens import extract_absolute_paths, split_shell_segments
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.config.paths import get_media_dir
from cirno_core.processes import platform
from cirno_core.security.workspace_access import current_scope_allows_loopback
from cirno_core.security.workspace_policy import is_path_within

WORKSPACE_BOUNDARY_NOTE = (
    "\n\nNote: this is a hard policy boundary, not a transient failure. "
    "Do NOT retry with shell tricks (symlinks, base64 piping, alternative "
    "tools, working_dir overrides). If the user genuinely needs this "
    "resource, tell them you cannot reach it under the current "
    "restrict_to_workspace policy and ask how to proceed."
)


DEFAULT_DENY_PATTERNS = [
    r"\brm\s+-[rf]{1,2}\b",  # rm -r, rm -rf, rm -fr
    r"\bdel\s+/[fq]\b",  # del /f, del /q
    r"\brmdir\s+/s\b",  # rmdir /s
    r"(?:^|[;&|]\s*)format(?!=)\b",  # format (as standalone command only)
    r"\b(mkfs|diskpart)\b",  # disk operations
    r"\bdd\s+if=",  # dd
    r">\s*/dev/sd",  # write to disk
    r"\b(shutdown|reboot|poweroff)\b",  # system power
    r":\(\)\s*\{.*\};\s*:",  # fork bomb
    # Block writes to cirno internal state files (#2989).
    # history.jsonl / .dream_cursor are managed by append_history();
    # direct writes corrupt the cursor format and crash /dream.
    r">>?\s*\S*(?:history\.jsonl|\.dream_cursor)",  # > / >> redirect
    r"\btee\b[^|;&<>]*(?:history\.jsonl|\.dream_cursor)",  # tee / tee -a
    r"\b(?:cp|mv)\b(?:\s+[^\s|;&<>]+)+\s+\S*(?:history\.jsonl|\.dream_cursor)",  # cp/mv target
    r"\bdd\b[^|;&<>]*\bof=\S*(?:history\.jsonl|\.dream_cursor)",  # dd of=
    r"\bsed\s+-i[^|;&<>]*(?:history\.jsonl|\.dream_cursor)",  # sed -i
]


class CommandPolicy:
    def __init__(
        self, config: ExecToolConfig, *, restrict_to_workspace: bool, allow_local_services: bool
    ):
        self.config = config
        self.restrict_to_workspace = restrict_to_workspace
        self.webui_allow_local_service_access = allow_local_services
        self.deny_patterns = [*config.deny_patterns, *DEFAULT_DENY_PATTERNS]
        self.allow_patterns = config.allow_patterns
        self.sandbox_ro_binds = [
            Path(path) for path in normalize_bind_paths(config.sandbox_ro_binds)
        ]
        self.sandbox_rw_binds = [
            Path(path) for path in normalize_bind_paths(config.sandbox_rw_binds)
        ]

    _BENIGN_DEVICE_PATHS: frozenset[str] = frozenset(
        {
            "/dev/null",
            "/dev/zero",
            "/dev/full",
            "/dev/random",
            "/dev/urandom",
            "/dev/stdin",
            "/dev/stdout",
            "/dev/stderr",
            "/dev/tty",
        }
    )

    def check(
        self,
        command: str,
        cwd: str,
        *,
        restrict_to_workspace: bool | None = None,
        workspace_root: str | None = None,
    ) -> str | None:
        """Apply command patterns, network policy and allowed filesystem roots."""
        cmd = command.strip()
        lower = cmd.lower()

        # allow_patterns take priority over deny_patterns so that users can
        # exempt specific commands (e.g. "rm -rf" inside a build directory)
        # from the hardcoded deny list via configuration. A chained command is
        # only explicitly allowed when every top-level shell segment matches.
        segments = split_shell_segments(lower)
        explicitly_allowed = (
            bool(self.allow_patterns)
            and bool(segments)
            and all(
                any(re.fullmatch(pattern, segment) for pattern in self.allow_patterns)
                for segment in segments
            )
        )
        if not explicitly_allowed:
            for pattern in self.deny_patterns:
                if re.search(pattern, lower):
                    return ToolResult.error("Error: Command blocked by deny pattern filter")

            if self.allow_patterns:
                return ToolResult.error(
                    "Error: Command blocked by allowlist filter (not in allowlist)"
                )

        from cirno_core.security.network import contains_internal_url

        if contains_internal_url(
            cmd,
            allow_loopback=current_scope_allows_loopback(
                enabled=self.webui_allow_local_service_access,
            ),
        ):
            # The runner turns this marker into a non-retryable security hint.
            return ToolResult.error(
                "Error: Command blocked by safety guard (internal/private URL detected)"
            )

        should_restrict = (
            self.restrict_to_workspace if restrict_to_workspace is None else restrict_to_workspace
        )
        if should_restrict:
            if "..\\" in cmd or "../" in cmd:
                return ToolResult.error(
                    "Error: Command blocked by safety guard (path traversal detected)"
                    + WORKSPACE_BOUNDARY_NOTE
                )

            cwd_path = Path(cwd).resolve()
            resolved_workspace = (
                Path(workspace_root).expanduser().resolve() if workspace_root else None
            )
            sandbox_bind_roots = self.active_sandbox_bind_roots(resolved_workspace or cwd_path)

            for raw in extract_absolute_paths(cmd):
                try:
                    expanded = os.path.expandvars(raw.strip())
                    # Python's expanduser() intentionally does not implement
                    # shell directory-stack forms. ``~+`` is the active cwd,
                    # while ``~-`` and indexed forms can resolve outside it;
                    # normalize the former and fail closed on the latter.
                    if expanded == "~+":
                        p = cwd_path
                    elif expanded.startswith("~+/"):
                        p = (cwd_path / expanded[3:]).resolve()
                    elif re.match(r"^~(?:-|[+-]\d+)(?:/|$)", expanded):
                        return ToolResult.error(
                            "Error: Command blocked by safety guard "
                            "(path outside working dir)" + WORKSPACE_BOUNDARY_NOTE
                        )
                    else:
                        try:
                            home_path = Path(expanded).expanduser()
                        except RuntimeError:
                            return ToolResult.error(
                                "Error: Command blocked by safety guard "
                                "(path outside working dir)" + WORKSPACE_BOUNDARY_NOTE
                            )
                        p = home_path.resolve()
                    # Match against the un-resolved path first.  On Linux,
                    # /dev/stderr is a symlink to /proc/self/fd/2 and
                    # ``Path.resolve()`` would mask the device-file intent.
                    if self.is_benign_device_path(expanded):
                        continue
                except (OSError, RuntimeError, ValueError) as exc:
                    raise ValueError(f"Command path {raw!r} could not be resolved: {exc}") from exc

                if self.is_benign_device_path(str(p)):
                    continue

                media_path = get_media_dir().resolve()
                allowed = is_path_within(p, cwd_path) or is_path_within(p, media_path)
                if not allowed and resolved_workspace is not None:
                    allowed = is_path_within(p, resolved_workspace)
                if not allowed and sandbox_bind_roots:
                    allowed = any(is_path_within(p, root) for root in sandbox_bind_roots)
                if p.is_absolute() and not allowed:
                    return ToolResult.error(
                        "Error: Command blocked by safety guard (path outside working dir)"
                        + WORKSPACE_BOUNDARY_NOTE
                    )

        return None

    @classmethod
    def is_benign_device_path(cls, path: str) -> bool:
        """Return True for kernel device files that should never be workspace-blocked."""
        if path in cls._BENIGN_DEVICE_PATHS:
            return True
        return path.startswith("/dev/fd/")

    def active_sandbox_bind_roots(
        self,
        workspace_root: Path | None = None,
    ) -> list[Path]:
        if self.config.sandbox not in ("bwrap", "seatbelt") or platform.IS_WINDOWS:
            return []
        roots = [*self.sandbox_ro_binds, *self.sandbox_rw_binds]
        if workspace_root is None:
            return roots
        return [root for root in roots if not is_path_within(workspace_root, root)]
