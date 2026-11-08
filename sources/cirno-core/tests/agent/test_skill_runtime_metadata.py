"""Invalid Skill requirements remain visible errors across all Skill sources."""

import json

import pytest

from cirno_core.config.home import get_home_path
from cirno_core.skills.loader import SkillsLoader
from cirno_core.skills.runtime_metadata import SkillMetadataError, parse_runtime_metadata


@pytest.mark.parametrize(
    "metadata, field",
    [
        ({"metadata": "{broken"}, "invalid JSON"),
        ({"metadata": "null"}, "expected an object"),
        ({"metadata": []}, "metadata: expected an object"),
        ({"metadata": {"cirno": None}}, "metadata.cirno"),
        ({"metadata": {"cirno": {"requires": "git"}}}, "requires"),
        ({"metadata": {"cirno": {"requires": {"bins": "git"}}}}, "requires.bins"),
        ({"metadata": {"cirno": {"requires": {"env": False}}}}, "requires.env"),
        ({"metadata": {"cirno": {"requires": {"bins": [None]}}}}, "requires.bins.0"),
        ({"metadata": {"cirno": {"requires": {"env": [""]}}}}, "requires.env.0"),
        ({"metadata": {"cirno": {"always": "false"}}}, "always"),
        ({"always": "false"}, "always"),
        ({"metadata": {"cirno": {"install": "brew install git"}}}, "install"),
    ],
)
def test_invalid_runtime_declarations_name_the_failed_field(metadata, field):
    with pytest.raises(SkillMetadataError, match=field):
        parse_runtime_metadata(metadata)


@pytest.mark.parametrize("namespace", ["cirno", "openclaw"])
def test_mapping_and_json_extensions_share_the_same_contract(namespace):
    value = {namespace: {"always": True, "requires": {"bins": [" git "], "env": None}}}
    mapping = parse_runtime_metadata({"metadata": value})
    encoded = parse_runtime_metadata({"metadata": json.dumps(value)})
    assert mapping == encoded
    assert mapping.always and mapping.requires.bins == ["git"]
    assert mapping.requires.env == []


def test_optional_null_lists_are_distinct_from_invalid_members():
    assert parse_runtime_metadata({"metadata": {"cirno": {"requires": None}}}).requires.bins == []
    assert (
        parse_runtime_metadata({"metadata": {"cirno": {"requires": {"bins": None}}}}).requires.bins
        == []
    )


@pytest.mark.parametrize("source", ["home", "builtin"])
def test_invalid_requirements_never_become_available_or_always_active(tmp_path, source):
    root = get_home_path() / "skills" if source == "home" else tmp_path / "builtin"
    directory = root / "broken"
    directory.mkdir(parents=True)
    document = directory / "SKILL.md"
    document.write_text(
        "---\nname: broken\ndescription: Broken requirements\nmetadata:\n  cirno:\n    always: true\n    requires:\n      bins: git\n---\nInstructions remain readable.\n"
    )
    loader = SkillsLoader(tmp_path, builtin_skills_dir=tmp_path / "builtin")

    assert any(entry["name"] == "broken" for entry in loader.list_skills(filter_unavailable=False))
    assert "Instructions remain readable" in loader.load_skill("broken")
    available, reason = loader.get_skill_availability("broken")
    assert not available and "requires.bins" in reason
    assert "broken" not in loader.get_always_skills()
    assert not any(entry["name"] == "broken" for entry in loader.list_skills())
    with pytest.raises(SkillMetadataError, match="requires.bins"):
        loader.get_skill_requirements("broken")
