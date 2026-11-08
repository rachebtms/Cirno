"""Skills loader for agent capabilities."""

import os
import shutil
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from cirno_core.config.home import get_home_path
from cirno_core.skills.metadata import BUILTIN_DOCUMENTS_DIR
from cirno_core.skills.metadata import (
    BUILTIN_SKILLS_DIR as BUILTIN_SKILLS_DIR,
)
from cirno_core.skills.metadata import (
    parse_skill_metadata as parse_skill_metadata,
)
from cirno_core.skills.metadata import (
    valid_skill_metadata as valid_skill_metadata,
)
from cirno_core.skills.runtime_metadata import (
    SkillMetadataError,
    SkillRuntimeMetadata,
    parse_runtime_metadata,
)


@dataclass
class _SkillSnapshot:
    entries: list[dict[str, str]] | None = None
    documents: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, dict[str, object] | None] = field(default_factory=dict)
    binaries: dict[str, bool] = field(default_factory=dict)
    runtime_metadata: dict[str, SkillRuntimeMetadata] = field(default_factory=dict)


class SkillsLoader:
    """
    Loader for agent skills.

    Skills are markdown files (SKILL.md) that teach the agent how to use
    specific tools or perform certain tasks.
    """

    def __init__(
        self,
        workspace: Path,
        builtin_skills_dir: Path | None = None,
        disabled_skills: set[str] | None = None,
    ):
        self.workspace = workspace
        self.home_skills = get_home_path() / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
        self.disabled_skills = disabled_skills or set()
        self._snapshot: ContextVar[_SkillSnapshot | None] = ContextVar(
            "skill_snapshot", default=None
        )

    @contextmanager
    def snapshot(self) -> Generator[None, None, None]:
        """Reuse discovery, documents, metadata, and CLI checks until this scope exits."""
        if self._snapshot.get() is not None:
            yield
            return
        token = self._snapshot.set(_SkillSnapshot())
        try:
            yield
        finally:
            self._snapshot.reset(token)

    def _skill_entries_from_dir(
        self, base: Path, source: str, *, skip_names: set[str] | None = None
    ) -> list[dict[str, str]]:
        if not base.exists():
            return []
        entries: list[dict[str, str]] = []
        for skill_dir in base.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            name = skill_dir.name
            if skip_names is not None and name in skip_names:
                continue
            entries.append({"name": name, "path": str(skill_file), "source": source})
        return entries

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """
        List all available skills.

        Args:
            filter_unavailable: If True, filter out skills with unmet requirements.

        Returns:
            List of skill info dicts with 'name', 'path', 'source'.
        """
        with self.snapshot():
            return self._list_skills(filter_unavailable)

    def _list_skills(self, filter_unavailable: bool) -> list[dict[str, str]]:
        snapshot = self._snapshot.get()
        if snapshot is not None and snapshot.entries is not None:
            skills = snapshot.entries
        else:
            skills = self._discover_skills()
            if snapshot is not None:
                snapshot.entries = skills
        if filter_unavailable:
            return [skill for skill in skills if self.get_skill_availability(skill["name"])[0]]
        return skills

    def _discover_skills(self) -> list[dict[str, str]]:
        from cirno_core.agent.plugins import enabled_agent_plugin_skill_documents

        plugin_skills = enabled_agent_plugin_skill_documents(self.workspace)
        disabled = set(self.disabled_skills)
        skills = self._skill_entries_from_dir(self.home_skills, "home")
        seen_names = {entry["name"] for entry in skills}
        snapshot = self._snapshot.get()
        for skill in plugin_skills:
            if skill.name in seen_names:
                continue
            skills.append(
                {
                    "name": skill.name,
                    "path": str(skill.path),
                    "source": "plugin",
                }
            )
            if snapshot is not None and skill.name not in disabled:
                snapshot.documents[skill.name] = skill.content
                snapshot.metadata[skill.name] = skill.metadata
            seen_names.add(skill.name)
        if self.builtin_skills and self.builtin_skills.exists():
            skills.extend(
                self._skill_entries_from_dir(self.builtin_skills, "builtin", skip_names=seen_names)
            )

        if disabled:
            skills = [s for s in skills if s["name"] not in disabled]

        return sorted(skills, key=lambda skill: skill["name"])

    def load_skill(self, name: str) -> str | None:
        """
        Load a skill by name.

        Args:
            name: Skill name (directory name).

        Returns:
            Skill content or None if not found.
        """
        with self.snapshot():
            return self._load_skill(name)

    def _load_skill(self, name: str) -> str | None:
        skills = self.list_skills(filter_unavailable=False)
        resolved = name
        entry = next((skill for skill in skills if skill["name"] == resolved), None)
        if entry is None:
            return None
        snapshot = self._snapshot.get()
        if snapshot is not None and resolved in snapshot.documents:
            return snapshot.documents[resolved]
        content = Path(entry["path"]).read_text(encoding="utf-8")
        if resolved == "cirno-document" and entry["source"] == "builtin":
            content = content.replace("{documentation_root}", str(BUILTIN_DOCUMENTS_DIR))
        if snapshot is not None:
            snapshot.documents[resolved] = content
        return content

    def get_skill_availability(self, name: str) -> tuple[bool, str]:
        """Return whether a skill can run and why not when it cannot."""
        directory = get_home_path() / "skills" / name
        if directory.is_dir():
            from cirno_core.skills.history import snapshot_skill

            validation = snapshot_skill(directory, document_content=self.load_skill(name))
            if validation is None:
                return False, "SKILL.md is missing"
            if not validation["valid"]:
                return False, "; ".join(validation["errors"])
        try:
            requirements = self.get_skill_requirements(name)
        except SkillMetadataError as error:
            return False, str(error)
        missing = [f"CLI: {command}" for command in requirements["missing_bins"]] + [
            f"ENV: {variable}" for variable in requirements["missing_env"]
        ]
        return not missing, ", ".join(missing)

    def get_skill_requirements(self, name: str) -> dict[str, list[str]]:
        """Return explicit command/env requirements and currently missing entries."""
        requirements = self.get_runtime_metadata(name).requires
        bins, env = requirements.bins, requirements.env
        return {
            "bins": bins,
            "env": env,
            "missing_bins": [value for value in bins if not self._binary_available(value)],
            "missing_env": [value for value in env if not os.environ.get(value)],
        }

    def get_skill_description(self, name: str) -> str:
        """Get the description of a skill from its frontmatter."""
        meta = self.get_skill_metadata(name)
        description = meta.get("description") if meta else None
        if isinstance(description, str) and description:
            return description
        return name  # Fallback to skill name

    def _binary_available(self, command: str) -> bool:
        snapshot = self._snapshot.get()
        if snapshot is not None and command in snapshot.binaries:
            return snapshot.binaries[command]
        available = shutil.which(command) is not None
        if snapshot is not None:
            snapshot.binaries[command] = available
        return available

    def get_always_skills(self) -> list[str]:
        """Get skills marked as always=true that meet requirements."""
        with self.snapshot():
            return self._get_always_skills()

    def _get_always_skills(self) -> list[str]:
        return [
            entry["name"]
            for entry in self.list_skills(filter_unavailable=True)
            if self.get_runtime_metadata(entry["name"]).always
        ]

    def get_runtime_metadata(self, name: str) -> SkillRuntimeMetadata:
        """Return the shared validated runtime declaration for one Skill."""
        snapshot = self._snapshot.get()
        if snapshot is not None and name in snapshot.runtime_metadata:
            return snapshot.runtime_metadata[name]
        metadata = self.get_skill_metadata(name)
        if metadata is None or not valid_skill_metadata(metadata, name):
            raise SkillMetadataError(
                "SKILL.md needs matching name and a non-empty description in YAML frontmatter."
            )
        runtime = parse_runtime_metadata(metadata)
        if snapshot is not None:
            snapshot.runtime_metadata[name] = runtime
        return runtime

    def get_skill_metadata(self, name: str) -> dict[str, object] | None:
        """
        Get metadata from a skill's frontmatter.

        Args:
            name: Skill name.

        Returns:
            Metadata dict or None.
        """
        snapshot = self._snapshot.get()
        if snapshot is not None and name in snapshot.metadata:
            return snapshot.metadata[name]
        metadata = parse_skill_metadata(self.load_skill(name) or "")
        if snapshot is not None:
            snapshot.metadata[name] = metadata
        return metadata
