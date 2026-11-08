"""One instance-owned conversation store; task directories never select data."""

from pathlib import Path

from cirno_core.config.paths import get_runtime_subdir


class SessionLocation:
    def __init__(self, workspace: Path, *, sessions_root: Path | None = None):
        workspace = Path(workspace).expanduser().resolve()
        root = (Path(sessions_root) if sessions_root is not None else get_runtime_subdir("sessions")).expanduser().resolve()
        if root == workspace or root.is_relative_to(workspace):
            raise ValueError("session storage must be outside the agent workspace")
        selected = root / "instance"
        if selected.is_symlink():
            raise ValueError(f"session storage must not be a symbolic link: {selected}")
        selected.mkdir(parents=True, exist_ok=True, mode=0o700)
        selected.chmod(0o700)
        workspace.mkdir(parents=True, exist_ok=True)
        self.workspace, self.sessions_dir = workspace, selected
