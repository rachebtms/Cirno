"""Bundled Home templates and initial profile creation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


def sync_home_templates(*, silent: bool = False) -> list[str]:
    """Initialize profile, memory, prompts and Skills in Home without overwriting files."""
    from importlib.resources import files as pkg_files

    tpl = pkg_files("cirno_core") / "templates"
    if not tpl.is_dir():
        raise FileNotFoundError(f"Bundled Home templates are missing: {tpl}")

    added: list[str] = []

    def _write(src: Any, dest: Path) -> None:
        content = src.read_text(encoding="utf-8") if src else ""
        if dest.exists():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        added.append(str(dest))

    from cirno_core.config.home import get_home_path

    agent_home = get_home_path()
    agent_home.mkdir(parents=True, exist_ok=True)
    for item in tpl.iterdir():
        if item.name.endswith(".md") and not item.name.startswith("."):
            _write(item, agent_home / item.name)
    _write(tpl / "memory" / "MEMORY.md", agent_home / "memory" / "MEMORY.md")
    _write(tpl / "prompts" / "README.md", agent_home / "prompts" / "README.md")
    _write(None, agent_home / "memory" / "history.jsonl")
    (agent_home / "skills").mkdir(exist_ok=True)

    if added and not silent:
        from rich.console import Console

        for name in added:
            Console().print(f"  [dim]Created {name}[/dim]")

    # Initialize git for memory version control
    try:
        from cirno_core.utils.gitstore import GitStore

        gs = GitStore(
            agent_home,
            tracked_files=[
                "SOUL.md", "WORKER.md",
                "USER.md",
                "memory/MEMORY.md",
            ],
        )
        gs.init()
    except Exception:
        logger.exception("Failed to initialize git store for {}", agent_home)

    return added


def load_bundled_template(template_name: str) -> str | None:
    """Read a bundled template file from the cirno package."""
    from importlib.resources import files as pkg_files

    tpl = pkg_files("cirno_core") / "templates" / template_name
    return tpl.read_text(encoding="utf-8") if tpl.is_file() else None
