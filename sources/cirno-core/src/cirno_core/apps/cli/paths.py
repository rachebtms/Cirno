"""Managed CLI App Skill paths and source URLs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

from cirno_core.apps.cli import resources
from cirno_core.config.home import get_home_path
from cirno_core.skills.metadata import SKILL_NAME, parse_skill_metadata

_SAFE_NAME_RE = re.compile(r"[^a-z0-9_-]+")


def _skill_name(name: str) -> str:
    clean = _SAFE_NAME_RE.sub("-", name.lower()).strip("-")
    clean = clean.replace("_", "-")
    legacy = f"cli-app-{clean or 'app'}"
    if "_" not in name and len(legacy) <= 64 and SKILL_NAME.fullmatch(legacy):
        return legacy  # Retain existing valid managed paths and fixed injections.
    return _suffixed_skill_name(name)


def _suffixed_skill_name(name: str) -> str:
    clean = _SAFE_NAME_RE.sub("-", name.lower()).replace("_", "-")
    clean = re.sub("-+", "-", clean).strip("-") or "app"
    digest = hashlib.sha256(name.lower().encode()).hexdigest()[:10]
    return f"cli-app-{clean[:45].rstrip('-')}-{digest}"


def _managed_skill_owner(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8") as stream:
            text = stream.read(250_000)
    except (OSError, UnicodeError):
        return None
    metadata = parse_skill_metadata(text) or {}
    owner = metadata.get("cirno_cli_app")
    if isinstance(owner, str):
        return owner.casefold()
    # Skills generated before ownership was recorded already name their app in
    # this managed note. Keep those folders and existing fixed injections.
    _, marker, note = text.partition("<!-- cirno-cli-app-note -->")
    match = re.search(r'Use the `apps__run` tool with `name="([^"\n]+)"` for command execution\.', note)
    return match[1].casefold() if marker and match else None


def cli_app_skill_path(name: str) -> Path:
    """CLI App skills share the agent's Home skill directory."""
    root = get_home_path() / "skills"
    suffixed = root / _suffixed_skill_name(name) / "SKILL.md"
    if _managed_skill_owner(suffixed) == name.casefold():
        return suffixed
    clean = _SAFE_NAME_RE.sub("-", name.lower()).strip("-").replace("_", "-")
    legacy_name = f"cli-app-{clean or 'app'}"
    if len(legacy_name) <= 64 and SKILL_NAME.fullmatch(legacy_name):
        legacy = root / legacy_name / "SKILL.md"
        owner = _managed_skill_owner(legacy)
        if owner == name.casefold() or (
            owner is None
            and _skill_name(name) == legacy_name
            and not legacy.parent.exists()
            and not legacy.parent.is_symlink()
        ):
            return legacy
    return suffixed


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
