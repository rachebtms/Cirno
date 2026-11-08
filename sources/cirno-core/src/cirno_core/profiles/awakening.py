"""Seed first-use guidance only when an owner registers a new instance."""
from pathlib import Path

from cirno_core.config.home import get_home_path
from cirno_core.utils.prompt_templates import render_template
from cirno_core.utils.atomic_file import atomic_write_text


def initialize_awakening() -> None:
    path = get_home_path() / "BOOTSTRAP.md"
    if not path.exists():
        atomic_write_text(path, render_template("agent/awakening.md"))


def awakening_prompt() -> str:
    path: Path = get_home_path() / "BOOTSTRAP.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""
