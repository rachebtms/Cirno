"""Build model-facing Skill summaries and explicitly invoked instructions."""

import re
from pathlib import Path

from cirno_core.runtime.context import RuntimeContextBlock
from cirno_core.skills.loader import SkillsLoader
from cirno_core.skills.metadata import SKILL_FRONTMATTER

_SKILL_REFERENCE = re.compile(r"(?<![\w$])\$([A-Za-z0-9_-]+)")


class SkillContext:
    def __init__(self, catalog: SkillsLoader) -> None:
        self.catalog = catalog

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        Load specific skills for inclusion in agent context.

        Args:
            skill_names: List of skill names to load.

        Returns:
            Formatted skills content.
        """
        parts = [
            f"### Skill: {name}\n\n{self._strip_frontmatter(markdown)}"
            for name in skill_names
            if (markdown := self.catalog.load_skill(name))
        ]
        return "\n\n---\n\n".join(parts)

    def get_explicitly_invoked_skills(self, text: str) -> list[str]:
        """Resolve ``$skill-name`` references to enabled, available skills."""
        references = list(_SKILL_REFERENCE.finditer(text))
        if not references:
            return []
        available = {entry["name"] for entry in self.catalog.list_skills(filter_unavailable=True)}
        invoked: list[str] = []
        for match in references:
            requested = match.group(1)
            name = requested
            if name in available and name not in invoked:
                invoked.append(name)
        return invoked

    def build_explicit_skill_runtime_context(
        self,
        text: str,
    ) -> RuntimeContextBlock | None:
        """Load non-always skills explicitly invoked by the current message."""
        with self.catalog.snapshot():
            return self._build_explicit_skill_runtime_context(text)

    def _build_explicit_skill_runtime_context(self, text: str) -> RuntimeContextBlock | None:
        skill_names = self.get_explicitly_invoked_skills(text)
        if not skill_names:
            return None
        always_active = set(self.catalog.get_always_skills())
        skill_names = [name for name in skill_names if name not in always_active]
        content = self.load_skills_for_context(skill_names)
        if not content:
            return None
        return RuntimeContextBlock(
            source="explicit_skills",
            content=(
                f"[Active Skills — instructions for this user turn]\n{content}\n[/Active Skills]"
            ),
        )

    def build_skills_summary(
        self,
        exclude: set[str] | None = None,
        *,
        workspace: Path | None = None,
    ) -> str:
        """
        Build a summary of available skills (name, description, path).

        This is used for progressive loading - the agent can read the full
        skill content using read_file when needed.

        Args:
            exclude: Set of skill names to omit from the summary.
            workspace: Effective project workspace used to choose safe display paths.

        Returns:
            Markdown-formatted skills summary.
        """
        with self.catalog.snapshot():
            return self._build_skills_summary(exclude, workspace=workspace)

    def _build_skills_summary(self, exclude: set[str] | None, *, workspace: Path | None) -> str:
        all_skills = self.catalog.list_skills(filter_unavailable=True)
        if not all_skills:
            return ""

        agent_workspace = self.catalog.workspace.expanduser().resolve()
        project_workspace = (workspace or self.catalog.workspace).expanduser().resolve()
        use_relative_roots = project_workspace == agent_workspace
        sections: list[str] = []
        groups = (
            ("Home skills", "home", self.catalog.home_skills),
            ("Agent Plugin skills", "plugin", self.catalog.workspace / "plugins"),
            ("Built-in skills", "builtin", self.catalog.builtin_skills),
        )
        for label, source, root in groups:
            entries = [
                entry
                for entry in all_skills
                if entry["source"] == source and (not exclude or entry["name"] not in exclude)
            ]
            if not entries:
                continue

            resolved_root = root.expanduser().resolve()
            # Directory tools need the real built-in root; only read_file resolves
            # workspace-relative skills/<name>/... aliases to bundled resources.
            if use_relative_roots and source == "plugin":
                display_root = Path("plugins")
            else:
                display_root = resolved_root
            lines = [f"### {label} (`{display_root}`)"]
            for entry in entries:
                skill_name = entry["name"]
                desc = self.catalog.get_skill_description(skill_name)
                relative_path = Path(entry["path"]).relative_to(root).as_posix()
                lines.append(f"- **{skill_name}** — {desc}  `{relative_path}`")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if not content.startswith("---"):
            return content
        match = SKILL_FRONTMATTER.match(content)
        if match:
            return content[match.end() :].strip()
        return content
