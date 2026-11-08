"""Tests for cirno_core.skills.loader.SkillsLoader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cirno_core.config.home import get_home_path
from cirno_core.skills.loader import SkillsLoader

from sources.development.testing.skills import write_skill


def test_list_skills_empty_when_skills_dir_missing(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    assert loader.list_skills(filter_unavailable=False) == []


def test_list_skills_empty_when_skills_dir_exists_but_empty(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (get_home_path() / "skills").mkdir(parents=True)
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    assert loader.list_skills(filter_unavailable=False) == []


def test_list_skills_workspace_entry_shape_and_source(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    skills_root = get_home_path() / "skills"
    skills_root.mkdir(parents=True)
    skill_path = write_skill(skills_root, "alpha", body="# Alpha")
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    entries = loader.list_skills(filter_unavailable=False)
    assert entries == [
        {"name": "alpha", "path": str(skill_path), "source": "home"},
    ]


def test_list_skills_skips_non_directories_and_missing_skill_md(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    skills_root = get_home_path() / "skills"
    skills_root.mkdir(parents=True)
    (skills_root / "not_a_dir.txt").write_text("x", encoding="utf-8")
    (skills_root / "no_skill_md").mkdir()
    ok_path = write_skill(skills_root, "ok", body="# Ok")
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    entries = loader.list_skills(filter_unavailable=False)
    names = {entry["name"] for entry in entries}
    assert names == {"ok"}
    assert entries[0]["path"] == str(ok_path)


def test_list_skills_workspace_shadows_builtin_same_name(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    ws_path = write_skill(ws_skills, "dup", body="# Workspace wins")

    builtin = tmp_path / "builtin"
    write_skill(builtin, "dup", body="# Builtin")

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    entries = loader.list_skills(filter_unavailable=False)
    assert len(entries) == 1
    assert entries[0]["source"] == "home"
    assert entries[0]["path"] == str(ws_path)


def test_list_skills_merges_workspace_and_builtin(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    ws_path = write_skill(ws_skills, "ws_only", body="# W")
    builtin = tmp_path / "builtin"
    bi_path = write_skill(builtin, "bi_only", body="# B")

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    entries = sorted(loader.list_skills(filter_unavailable=False), key=lambda item: item["name"])
    assert entries == [
        {"name": "bi_only", "path": str(bi_path), "source": "builtin"},
        {"name": "ws_only", "path": str(ws_path), "source": "home"},
    ]


def test_list_skills_builtin_omitted_when_dir_missing(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    ws_path = write_skill(ws_skills, "solo", body="# S")
    missing_builtin = tmp_path / "no_such_builtin"

    loader = SkillsLoader(workspace, builtin_skills_dir=missing_builtin)
    entries = loader.list_skills(filter_unavailable=False)
    assert entries == [{"name": "solo", "path": str(ws_path), "source": "home"}]


def test_list_skills_filter_unavailable_excludes_unmet_bin_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    skills_root = get_home_path() / "skills"
    skills_root.mkdir(parents=True)
    write_skill(
        skills_root,
        "needs_bin",
        metadata_json={"requires": {"bins": ["cirno_test_fake_binary"]}},
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    def fake_which(cmd: str) -> str | None:
        if cmd == "cirno_test_fake_binary":
            return None
        return "/usr/bin/true"

    monkeypatch.setattr("cirno_core.skills.loader.shutil.which", fake_which)

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    assert loader.list_skills(filter_unavailable=True) == []


def test_list_skills_filter_unavailable_includes_when_bin_requirement_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    skills_root = get_home_path() / "skills"
    skills_root.mkdir(parents=True)
    skill_path = write_skill(
        skills_root,
        "has-bin",
        metadata_json={"requires": {"bins": ["cirno_test_fake_binary"]}},
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    def fake_which(cmd: str) -> str | None:
        if cmd == "cirno_test_fake_binary":
            return "/fake/cirno_test_fake_binary"
        return None

    monkeypatch.setattr("cirno_core.skills.loader.shutil.which", fake_which)

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    entries = loader.list_skills(filter_unavailable=True)
    assert entries == [
        {"name": "has-bin", "path": str(skill_path), "source": "home"},
    ]


def test_list_skills_filter_unavailable_false_keeps_unmet_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    skills_root = get_home_path() / "skills"
    skills_root.mkdir(parents=True)
    skill_path = write_skill(
        skills_root,
        "blocked",
        metadata_json={"requires": {"bins": ["cirno_test_fake_binary"]}},
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    monkeypatch.setattr("cirno_core.skills.loader.shutil.which", lambda _cmd: None)

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    entries = loader.list_skills(filter_unavailable=False)
    assert entries == [
        {"name": "blocked", "path": str(skill_path), "source": "home"},
    ]


def test_list_skills_filter_unavailable_excludes_unmet_env_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    skills_root = get_home_path() / "skills"
    skills_root.mkdir(parents=True)
    write_skill(
        skills_root,
        "needs_env",
        metadata_json={"requires": {"env": ["CIRNO_SKILLS_TEST_ENV_VAR"]}},
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    monkeypatch.delenv("CIRNO_SKILLS_TEST_ENV_VAR", raising=False)

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    assert loader.list_skills(filter_unavailable=True) == []


def test_list_skills_openclaw_metadata_parsed_for_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    skills_root = get_home_path() / "skills"
    skills_root.mkdir(parents=True)
    skill_dir = skills_root / "openclaw-skill"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    oc_payload = json.dumps(
        {"openclaw": {"requires": {"bins": ["cirno_oc_bin"]}}}, separators=(",", ":")
    )
    skill_path.write_text(
        "\n".join(
            [
                "---",
                "name: openclaw-skill",
                "description: OpenClaw metadata test",
                f"metadata: {oc_payload}",
                "---",
                "",
                "# OC",
            ]
        ),
        encoding="utf-8",
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    monkeypatch.setattr("cirno_core.skills.loader.shutil.which", lambda _cmd: None)

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    assert loader.list_skills(filter_unavailable=True) == []

    monkeypatch.setattr(
        "cirno_core.skills.loader.shutil.which",
        lambda cmd: "/x" if cmd == "cirno_oc_bin" else None,
    )
    entries = loader.list_skills(filter_unavailable=True)
    assert entries == [
        {"name": "openclaw-skill", "path": str(skill_path), "source": "home"},
    ]


def test_disabled_skills_excluded_from_list(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    write_skill(ws_skills, "alpha", body="# Alpha")
    beta_path = write_skill(ws_skills, "beta", body="# Beta")
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin, disabled_skills={"alpha"})
    entries = loader.list_skills(filter_unavailable=False)
    assert len(entries) == 1
    assert entries[0]["name"] == "beta"
    assert entries[0]["path"] == str(beta_path)
    assert loader.load_skill("alpha") is None


def test_disabled_skills_empty_set_no_effect(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    write_skill(ws_skills, "alpha", body="# Alpha")
    write_skill(ws_skills, "beta", body="# Beta")
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin, disabled_skills=set())
    entries = loader.list_skills(filter_unavailable=False)
    assert len(entries) == 2


def test_bundled_memory_skill_uses_agent_owned_path(tmp_path: Path) -> None:
    memory = SkillsLoader(tmp_path).load_skill("memory")

    assert memory is not None
    assert "memory__search" in memory


def test_disabled_skills_excluded_from_get_always_skills(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    write_skill(ws_skills, "alpha", metadata_json={"always": True}, body="# Alpha")
    write_skill(ws_skills, "beta", metadata_json={"always": True}, body="# Beta")
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin, disabled_skills={"alpha"})
    always = loader.get_always_skills()
    assert "alpha" not in always
    assert "beta" in always


# -- multiline description tests (YAML folded > and literal |) -----------------


def test_build_skills_summary_literal_description(tmp_path: Path) -> None:
    """description: | (YAML literal scalar) should be parsed correctly."""
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    skill_dir = ws_skills / "multi"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\n"
        "name: multi\n"
        "description: |\n"
        "  Line one of description.\n"
        "  Line two of description.\n"
        "---\n\n# Multi\n",
        encoding="utf-8",
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    meta = loader.get_skill_metadata("multi")
    assert meta is not None
    desc = meta.get("description")
    assert isinstance(desc, str)
    assert "Line one" in desc
    assert "Line two" in desc


def test_get_skill_metadata_handles_yaml_types(tmp_path: Path) -> None:
    """yaml.safe_load returns native types; always should be True, not 'true'."""
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    skill_dir = ws_skills / "typed"
    skill_dir.mkdir(parents=True)
    payload = json.dumps(
        {"cirno": {"requires": {"bins": ["gh"]}, "always": True}}, separators=(",", ":")
    )
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        f"---\nname: typed\nmetadata: {payload}\nalways: true\n---\n\n# Typed\n",
        encoding="utf-8",
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()

    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)
    meta = loader.get_skill_metadata("typed")
    assert meta is not None
    # YAML parsed 'true' to Python True
    assert meta.get("always") is True
    # metadata is a parsed dict, not a JSON string
    assert isinstance(meta.get("metadata"), dict)


def test_optional_null_requirements_do_not_make_invalid_list_items_available(
    tmp_path: Path,
) -> None:
    """Null requires/bins/env must not crash skill listing (JSON/YAML nulls)."""
    workspace = tmp_path / "ws"
    ws_skills = get_home_path() / "skills"
    ws_skills.mkdir(parents=True)
    write_skill(
        ws_skills,
        "null-requires",
        metadata_json={"always": True, "requires": None},
        body="# Null requires",
    )
    write_skill(
        ws_skills,
        "null-bins",
        metadata_json={"always": True, "requires": {"bins": None, "env": None}},
        body="# Null bins",
    )
    write_skill(
        ws_skills,
        "null-elems",
        metadata_json={"always": True, "requires": {"bins": [None, ""], "env": [None]}},
        body="# Null elems",
    )
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    loader = SkillsLoader(workspace, builtin_skills_dir=builtin)

    assert loader.get_skill_availability("null-requires") == (True, "")
    assert loader.get_skill_availability("null-bins") == (True, "")
    available, reason = loader.get_skill_availability("null-elems")
    assert not available and "requires.bins.0" in reason
    always = loader.get_always_skills()
    assert set(always) == {"null-requires", "null-bins"}
    listed = {e["name"] for e in loader.list_skills(filter_unavailable=True)}
    assert listed == {"null-requires", "null-bins"}
    assert loader.get_skill_requirements("null-requires") == {
        "bins": [],
        "env": [],
        "missing_bins": [],
        "missing_env": [],
    }


def test_documentation_skill_resolves_docs_without_rewriting_home_override(tmp_path):
    from cirno_core.config.home import get_home_path
    from cirno_core.skills.metadata import BUILTIN_DOCUMENTS_DIR

    loader = SkillsLoader(tmp_path)
    assert str(BUILTIN_DOCUMENTS_DIR / "README.md") in loader.load_skill("cirno-document")
    assert (BUILTIN_DOCUMENTS_DIR / "README.md").is_file()
    override = get_home_path() / "skills/cirno-document/SKILL.md"
    override.parent.mkdir(parents=True)
    override.write_text(
        "Keep the literal {documentation_root} in this custom skill.", encoding="utf-8"
    )
    assert loader.load_skill("cirno-document") == override.read_text(encoding="utf-8")
