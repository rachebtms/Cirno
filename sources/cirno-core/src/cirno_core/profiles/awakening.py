"""Seed first-use guidance only when an owner registers a new instance."""
from pathlib import Path

from cirno_core.config.home import get_home_path
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_core.utils.prompt_templates import render_template


def initialize_awakening(*, home: Path | None = None) -> None:
    path = (home if home is not None else get_home_path()) / "BOOTSTRAP.md"
    if not path.exists():
        atomic_write_text(path, render_template("agent/awakening.md"))


def awakening_prompt(*, home: Path | None = None) -> str:
    path = (home if home is not None else get_home_path()) / "BOOTSTRAP.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""
