"""Skill prompt formatting, explicit invocation and per-build snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest
from cirno_core.agent.context import ContextBuilder
from cirno_core.agent.tools.filesystem import ListDirTool, WriteFileTool
from cirno_core.agent.tools.search import GrepTool
from cirno_core.config.home import get_home_path
from cirno_core.skills import loader as agent_skills
from cirno_core.skills.context import SkillContext
from cirno_core.skills.loader import SkillsLoader

from sources.development.testing.skills import write_skill


def test_disabled_skills_excluded_from_build_skills_summary(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    write_skill(ws_skills, "alpha", body="# Alpha")
    write_skill(ws_skills, "beta", body="# Beta")
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin, disabled_skills={"alpha"})
    summary = SkillContext(loader).build_skills_summary()
    assert "alpha" not in summary
    assert "beta" in summary


def test_build_skills_summary_keeps_builtin_root_absolute_in_agent_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    home_skills = get_home_path() / "skills"
    home_skills.mkdir(parents=True)
    workspace_path = write_skill(home_skills, "alpha", body="# Alpha")
    builtin = tmp_path / "builtin"
    builtin_path = write_skill(builtin, "beta", body="# Beta")

    summary = SkillContext(
        SkillsLoader(workspace, builtin_skills_dir=builtin)
    ).build_skills_summary()

    assert str(home_skills) in summary
    assert f"### Built-in skills (`{builtin.resolve()}`)" in summary
    assert str(workspace_path) not in summary
    assert str(builtin_path) not in summary
    assert f"### Home skills (`{home_skills.resolve()}`)" in summary
    assert "`alpha/SKILL.md`" in summary
    assert "`beta/SKILL.md`" in summary


async def test_builtin_summary_root_supports_restricted_reference_search(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    builtin = tmp_path / "builtin"
    write_skill(builtin, "documentation", body="# Documentation")
    references = builtin / "documentation" / "references"
    references.mkdir()
    guide = references / "usage.md"
    guide.write_text("Choose a timezone", encoding="utf-8")
    summary = SkillContext(
        SkillsLoader(workspace, builtin_skills_dir=builtin)
    ).build_skills_summary()
    heading = next(line for line in summary.splitlines() if line.startswith("### Built-in skills"))
    reference_path = str(Path(heading.split("`")[1]) / "documentation" / "references")
    options = {
        "workspace": workspace,
        "allowed_dir": workspace,
        "restrict_to_workspace": True,
        "extra_read_allowed_dirs": [builtin],
    }

    listing = await ListDirTool(**options).execute(path=reference_path)
    matches = await GrepTool(**options).execute(
        pattern="timezone",
        path=reference_path,
        glob="*.md",
        output_mode="files_with_matches",
    )

    assert "usage.md" in listing
    assert "usage.md" in matches
    rejected = await WriteFileTool(**options).execute(path=str(guide), content="replace")
    assert rejected.is_error
    assert guide.read_text(encoding="utf-8") == "Choose a timezone"


def test_build_skills_summary_keeps_absolute_roots_for_selected_project(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    home_skills = get_home_path() / "skills"
    home_skills.mkdir(parents=True)
    write_skill(home_skills, "alpha", body="# Alpha")
    builtin = tmp_path / "builtin"
    write_skill(builtin, "beta", body="# Beta")
    project = tmp_path / "project"
    project.mkdir()

    summary = SkillContext(
        SkillsLoader(workspace, builtin_skills_dir=builtin)
    ).build_skills_summary(
        workspace=project,
    )

    assert summary.count(str(home_skills.resolve())) == 1
    assert summary.count(str(builtin.resolve())) == 1
    assert str(project.resolve()) not in summary


def test_explicit_skill_references_resolve_available_enabled_names_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "ws"
    skills_root = get_home_path() / "skills"
    skills_root.mkdir(parents=True)
    write_skill(skills_root, "alpha", body="# Alpha")
    write_skill(skills_root, "beta", body="# Beta")
    write_skill(
        skills_root,
        "blocked",
        metadata_json={"requires": {"env": ["MISSING_SKILL_TEST_ENV"]}},
        body="# Blocked",
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    monkeypatch.delenv("MISSING_SKILL_TEST_ENV", raising=False)
    loader = SkillsLoader(
        workspace,
        builtin_skills_dir=builtin,
        disabled_skills={"beta"},
    )

    invoked = SkillContext(loader).get_explicitly_invoked_skills(
        "Use $alpha, then $unknown, $alpha again, $beta, and $blocked."
    )

    assert invoked == ["alpha"]


def test_multiple_explicit_skills_share_one_ordered_runtime_context(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    skills_root = get_home_path() / "skills"
    skills_root.mkdir(parents=True)
    write_skill(skills_root, "alpha", body="Alpha instructions")
    write_skill(skills_root, "beta", body="Beta instructions")
    write_skill(
        skills_root,
        "always",
        metadata_json={"always": True},
        body="Always instructions",
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)

    context = SkillContext(loader).build_explicit_skill_runtime_context(
        "Use $beta, then $alpha, $beta again, and $always."
    )

    assert context is not None
    assert context.source == "explicit_skills"
    assert context.content.count("### Skill: beta") == 1
    assert context.content.count("### Skill: alpha") == 1
    assert context.content.index("### Skill: beta") < context.content.index("### Skill: alpha")
    assert "### Skill: always" not in context.content


def test_plain_message_skips_explicit_skill_discovery(tmp_path: Path, monkeypatch) -> None:
    loader = SkillsLoader(tmp_path)

    def unexpected_discovery():
        pytest.fail("ordinary chat must not scan skills for explicit references")

    monkeypatch.setattr(loader, "_discover_skills", unexpected_discovery)
    assert SkillContext(loader).build_explicit_skill_runtime_context("Explain this project") is None


@pytest.mark.parametrize("explicit", [False, True])
def test_prompt_reads_skills_once_and_refreshes_on_next_build(
    tmp_path: Path,
    monkeypatch,
    explicit: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    skills = get_home_path() / "skills"
    alpha = write_skill(skills, "alpha", metadata_json={"always": True}, body="First instructions")
    beta = write_skill(skills, "beta", metadata_json={"requires": {"bins": ["prompt-test-cli"]}})
    builder = ContextBuilder(workspace)
    builder.skills = SkillsLoader(workspace, builtin_skills_dir=builtin)
    documents = {alpha, beta}
    reads: list[Path] = []
    parses: list[str] = []
    original_read = Path.read_text
    original_parse = agent_skills.parse_skill_metadata
    original_discover = builder.skills._discover_skills
    discoveries = 0
    command_available = False
    checks: list[str] = []

    def discover():
        nonlocal discoveries
        discoveries += 1
        return original_discover()

    def read(path, *args, **kwargs):
        if path in documents:
            reads.append(path)
        return original_read(path, *args, **kwargs)

    def parse(content):
        parses.append(content)
        return original_parse(content)

    def which(command):
        checks.append(command)
        return "installed-command" if command_available else None

    def build_prompt():
        if explicit:
            messages = builder.build_messages(history=[], current_message="Use $alpha and $beta")
            return "\n".join(message["content"] for message in messages)
        return builder.build_system_prompt()

    monkeypatch.setattr(builder.skills, "_discover_skills", discover)
    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(agent_skills, "parse_skill_metadata", parse)
    monkeypatch.setattr("cirno_core.skills.loader.shutil.which", which)
    first = build_prompt()
    assert "First instructions" in first
    assert "**beta**" not in first
    assert discoveries == 1
    assert all(reads.count(path) == 1 for path in documents)
    assert len(parses) == len(documents)
    assert checks == ["prompt-test-cli"]

    alpha.write_text(
        original_read(alpha).replace("First instructions", "Updated instructions"), encoding="utf-8"
    )
    beta.write_text(
        original_read(beta).replace("description: beta skill", "description: Updated description"),
        encoding="utf-8",
    )
    command_available = True
    documents.add(write_skill(skills, "gamma", body="New skill"))
    reads.clear()
    parses.clear()
    checks.clear()
    second = build_prompt()
    assert "Updated instructions" in second and "First instructions" not in second
    assert "Updated description" in second
    assert "**beta**" in second
    assert "**gamma**" in second
    assert discoveries == 2
    assert all(reads.count(path) == 1 for path in documents)
    assert len(parses) == len(documents)
    assert checks == ["prompt-test-cli"]


def test_build_skills_summary_folded_description(tmp_path: Path) -> None:
    """description: > (YAML folded scalar) should be parsed correctly."""
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    skill_dir = ws_skills / "pdf"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\n"
        "name: pdf\n"
        "description: >\n"
        "  Use this skill when visual quality and design identity matter for a PDF.\n"
        '  CREATE (generate from scratch): "make a PDF".\n'
        "---\n\n# PDF Skill\n",
        encoding="utf-8",
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    summary = SkillContext(loader).build_skills_summary()
    assert "pdf" in summary
    assert "visual quality" in summary
