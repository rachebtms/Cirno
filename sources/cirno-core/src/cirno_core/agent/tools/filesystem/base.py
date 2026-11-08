"""Filesystem base behavior and its owned helpers."""

# pyright: reportPrivateUsage=false

from pathlib import Path
from typing import Any

from cirno_core.agent.tools.base import Tool
from cirno_core.agent.tools.context import ToolContext
from cirno_core.agent.tools.file_state import FileStates, current_file_states
from cirno_core.agent.tools.filesystem_config import FileToolsConfig
from cirno_core.agent.tools.path_utils import resolve_workspace_path
from cirno_core.config.home import get_home_path
from cirno_core.security.workspace_access import current_tool_workspace


class FileTool(Tool):
    """Shared base for filesystem tools — common init and path resolution."""

    config_key = "file"

    @classmethod
    def config_cls(cls):
        return FileToolsConfig

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:
        return ctx.config.file.enable

    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
        extra_read_allowed_dirs: list[Path] | None = None,
        extra_write_allowed_dirs: list[Path] | None = None,
        extra_write_allowed_files: list[Path] | None = None,
        file_states: FileStates | None = None,
        restrict_to_workspace: bool | None = None,
        sandbox_restricts_workspace: bool = False,
        extra_read_allowed_files: list[Path] | None = None,
    ):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._extra_read_allowed_dirs = list(extra_read_allowed_dirs or [])
        self._extra_read_allowed_files = list(extra_read_allowed_files or [])
        self._extra_write_allowed_dirs = list(extra_write_allowed_dirs or [])
        self._extra_write_allowed_files = list(extra_write_allowed_files or [])
        self._restrict_to_workspace = (
            bool(restrict_to_workspace)
            if restrict_to_workspace is not None
            else allowed_dir is not None
        )
        self._sandbox_restricts_workspace = sandbox_restricts_workspace
        # Explicit state is used by isolated runners like Dream/subagents.
        # Main AgentLoop tools leave this unset and resolve state from the
        # current async task, which keeps shared tool instances session-safe.
        self._explicit_file_states = file_states
        self._fallback_file_states = FileStates()

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        from cirno_core.skills.metadata import BUILTIN_DOCUMENTS_DIR, BUILTIN_SKILLS_DIR

        agent_workspace = Path(ctx.workspace)
        agent_home = get_home_path().resolve()
        restrict = ctx.config.restrict_to_workspace or ctx.config.exec.sandbox
        sandbox_restricts = bool(ctx.config.exec.sandbox)
        allowed_dir = agent_workspace if restrict else None
        # Agent-owned skills stay available from project scopes. History is a narrower
        # capability: expose only the append-only log, not the surrounding memory directory.
        return cls(
            workspace=agent_workspace,
            allowed_dir=allowed_dir,
            extra_read_allowed_dirs=[
                BUILTIN_SKILLS_DIR,
                BUILTIN_DOCUMENTS_DIR,
                agent_home / "skills",
                agent_home / "skills-history",
                agent_home / "memory",
            ],
            extra_read_allowed_files=[
                agent_home / name for name in ("SOUL.md", "WORKER.md", "USER.md", "AGENTS.md", "HEARTBEAT.md")
            ],
            extra_write_allowed_dirs=[agent_home / "skills"],
            extra_write_allowed_files=[
                agent_home / name
                for name in ("SOUL.md", "WORKER.md", "USER.md", "AGENTS.md", "HEARTBEAT.md", "memory/MEMORY.md")
            ],
            file_states=ctx.file_state_store,
            restrict_to_workspace=ctx.config.restrict_to_workspace,
            sandbox_restricts_workspace=sandbox_restricts,
        )

    @property
    def _file_states(self) -> FileStates:
        if self._explicit_file_states is not None:
            return self._explicit_file_states
        return current_file_states(self._fallback_file_states)

    def _effective_allowed_root(self, access_allowed_root: Path | None) -> Path | None:
        if self._allowed_dir is None or self._workspace is None:
            return access_allowed_root
        allowed_dir = Path(self._allowed_dir).expanduser().resolve(strict=False)
        workspace = Path(self._workspace).expanduser().resolve(strict=False)
        if allowed_dir == workspace:
            return access_allowed_root
        return allowed_dir

    def _resolve_with_extra(
        self,
        path: str,
        extra_allowed_dirs: list[Path] | None,
        extra_allowed_files: list[Path] | None,
        *,
        include_media_dir: bool,
        extra_files_require_allowed_root: bool = False,
    ) -> Path:
        access = current_tool_workspace(
            self._workspace,
            restrict_to_workspace=self._restrict_to_workspace,
            sandbox_restricts_workspace=self._sandbox_restricts_workspace,
        )
        allowed_root = self._effective_allowed_root(access.allowed_root)
        if extra_files_require_allowed_root and allowed_root is None:
            extra_allowed_files = None
        return resolve_workspace_path(
            path,
            access.project_path,
            allowed_root,
            extra_allowed_dirs,
            extra_allowed_files,
            include_media_dir=include_media_dir,
        )

    def _resolve_read(self, path: str) -> Path:
        plugin_skill_dirs: list[Path] = []
        if self._workspace is not None:
            from cirno_core.agent.plugins import enabled_agent_plugin_skill_dirs

            access = current_tool_workspace(
                self._workspace,
                restrict_to_workspace=self._restrict_to_workspace,
                sandbox_restricts_workspace=self._sandbox_restricts_workspace,
            )
            if self._effective_allowed_root(access.allowed_root) is not None:
                candidate = Path(path).expanduser()
                if not candidate.is_absolute() and access.project_path is not None:
                    candidate = access.project_path / candidate
                plugin_skill_dirs = list(
                    enabled_agent_plugin_skill_dirs(
                        Path(self._workspace),
                        requested_path=candidate.resolve(strict=False),
                    )
                )
        return self._resolve_with_extra(
            path,
            [*self._extra_read_allowed_dirs, *plugin_skill_dirs],
            self._extra_read_allowed_files,
            include_media_dir=True,
            extra_files_require_allowed_root=True,
        )

    def approval_reason(self, params: dict[str, Any]) -> str | None:
        from cirno_core.security.workspace_policy import WorkspaceBoundaryError

        paths = (
            [edit["path"] for edit in params.get("edits", [])]
            if self.name == "apply_patch"
            else [params.get("path", ".")]
        )
        try:
            for path in paths:
                if self.read_only:
                    self._resolve_read(path)
                else:
                    # The write resolver also snapshots Skills: preflight must not.
                    self._resolve_with_extra(
                        path,
                        self._extra_write_allowed_dirs,
                        self._extra_write_allowed_files,
                        include_media_dir=False,
                    )
        except WorkspaceBoundaryError as error:
            return str(error)
        return None

    def _resolve_write(self, path: str) -> Path:
        resolved = self._resolve_with_extra(
            path,
            self._extra_write_allowed_dirs,
            self._extra_write_allowed_files,
            include_media_dir=False,
        )
        from cirno_core.skills.history import capture_skill_path

        capture_skill_path(resolved)
        return resolved

    def _resolve(self, path: str) -> Path:
        return self._resolve_read(path)

    def _display_workspace(self) -> Path | None:
        return current_tool_workspace(self._workspace).project_path
