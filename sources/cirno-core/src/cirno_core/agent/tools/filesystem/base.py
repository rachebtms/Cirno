"""Filesystem base behavior and its owned helpers."""

# pyright: reportPrivateUsage=false

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cirno_core.agent.tools.base import Tool
from cirno_core.agent.tools.context import ToolContext
from cirno_core.agent.tools.file_state import FileStates, current_file_states
from cirno_core.agent.tools.filesystem_config import FileToolsConfig
from cirno_core.agent.tools.path_utils import resolve_workspace_path
from cirno_core.config.home import get_home_path
from cirno_core.config.loader import get_config_path
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
        home_path: Path | None = None,
        source_config_path: Path | None = None,
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
        self._home_path = (home_path if home_path is not None else get_home_path()).expanduser().resolve(strict=False)
        self._source_config_path = (source_config_path if source_config_path is not None else get_config_path()).expanduser().resolve(strict=False)
        # Explicit state is used by isolated runners like Dream/subagents.
        # Main AgentLoop tools leave this unset and resolve state from the
        # current async task, which keeps shared tool instances session-safe.
        self._explicit_file_states = file_states
        self._fallback_file_states = FileStates()

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        from cirno_core.skills.metadata import BUILTIN_DOCUMENTS_DIR, BUILTIN_SKILLS_DIR

        agent_workspace = Path(ctx.workspace)
        agent_home = ctx.home_path.expanduser().resolve(strict=False)
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
                agent_home / name for name in ("SOUL.md", "WORKER.md", "USER.md", "AGENTS.md", "HEARTBEAT.md", "BOOTSTRAP.md")
            ],
            extra_write_allowed_dirs=[agent_home / "skills"],
            extra_write_allowed_files=[
                agent_home / name
                for name in ("SOUL.md", "WORKER.md", "USER.md", "AGENTS.md", "HEARTBEAT.md", "BOOTSTRAP.md", "memory/MEMORY.md")
            ],
            file_states=ctx.file_state_store,
            restrict_to_workspace=ctx.config.restrict_to_workspace,
            sandbox_restricts_workspace=sandbox_restricts,
            home_path=agent_home,
            source_config_path=ctx.source_config_path or ctx.instance_config_path,
        )

    @property
    def _file_states(self) -> FileStates:
        if self._explicit_file_states is not None:
            return self._explicit_file_states
        return current_file_states(self._fallback_file_states)

    def _effective_allowed_root(self, access_allowed_root: Path | None) -> Path | None:
        if self._allowed_dir is None:
            return access_allowed_root
        allowed_dir = Path(self._allowed_dir).expanduser().resolve(strict=False)
        if self._workspace is None:
            return allowed_dir
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
                        config_path=self._source_config_path,
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
                    self._resolve_write_path(path)
        except WorkspaceBoundaryError as error:
            return str(error)
        return None

    def _resolve_write_path(self, path: str) -> Path:
        """Authorize a destination without creating a Skill history snapshot."""
        return self._resolve_with_extra(
            path,
            self._extra_write_allowed_dirs,
            self._extra_write_allowed_files,
            include_media_dir=False,
        )

    def _resolve_write(self, path: str) -> Path:
        resolved = self._resolve_write_path(path)
        from cirno_core.skills.history import capture_skill_path

        capture_skill_path(resolved, home=self._home_path)
        return resolved

    def _finish_writes(self, paths: Iterable[Path]) -> None:
        """Retire every committed read receipt, even if one history capture fails."""
        failures: list[str] = []
        for path in paths:
            try:
                self._file_states.record_write(path, home_path=self._home_path)
            except Exception as exc:
                failures.append(f"{path}: {exc}")
        if failures:
            raise RuntimeError(
                "File contents were saved, but Skill history/read-state finalization failed: "
                + "; ".join(failures)
                + ". Do not repeat the write; inspect the saved files before retrying cleanup."
            )

    def _resolve(self, path: str) -> Path:
        return self._resolve_read(path)

    def _display_workspace(self) -> Path | None:
        return current_tool_workspace(self._workspace).project_path
