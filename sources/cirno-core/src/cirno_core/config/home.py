"""Instance root and Agent Home paths selected by the global --home option."""

from pathlib import Path

_instance_path: Path | None = None


def set_instance_path(path: Path | None) -> None:
    """Select the instance root for the current CLI invocation."""
    global _instance_path
    _instance_path = path.expanduser().resolve() if path is not None else None


def get_selected_instance_path() -> Path | None:
    """Return the explicit instance root, if one was selected."""
    return _instance_path


def get_instance_path() -> Path:
    """Return the selected instance root, or ~/.cirno."""
    return _instance_path if _instance_path is not None else Path.home() / ".cirno"


def get_home_path() -> Path:
    """Return Agent Home, separate from configuration and runtime state."""
    return get_instance_path() / "home"


def get_default_workspace() -> str:
    """Return the default task directory under the instance root."""
    if _instance_path is not None:
        return str(get_instance_path() / "workspace")
    return "~/.cirno/workspace"
