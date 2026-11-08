"""Managed CLI App Skill paths and source URLs."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from cirno_core.apps.cli import resources
from cirno_core.config.home import get_home_path

_SAFE_NAME_RE = re.compile(r"[^a-z0-9_-]+")


def _skill_name(name: str) -> str:
    clean = _SAFE_NAME_RE.sub("-", name.lower()).strip("-")
    clean = clean.replace("_", "-")
    return f"cli-app-{clean or 'app'}"


def cli_app_skill_path(name: str) -> Path:
    """CLI App skills share the agent's Home skill directory."""
    return get_home_path() / "skills" / _skill_name(name) / "SKILL.md"


def _safe_skill_path(value: str) -> str | None:
    if not value.startswith("skills/"):
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return value if parts[-1] == "SKILL.md" else None


def _skill_content_url(
    skill_md: str, *, raw_base: str = resources.CLI_ANYTHING_RAW_BASE
) -> str | None:
    safe_path = _safe_skill_path(skill_md)
    if safe_path:
        return f"{raw_base.rstrip('/')}/{safe_path}"
    parsed = urlparse(skill_md)
    if parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com":
        return None
    raw_prefix = raw_base.rstrip("/") + "/"
    if not skill_md.startswith(raw_prefix):
        return None
    suffix = skill_md.removeprefix(raw_prefix)
    return skill_md if _safe_skill_path(suffix) else None
