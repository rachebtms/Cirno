"""Tests for CLI Apps loop helpers."""

from cirno.apps.cli.service import CliAppManager, cli_app_skill_path
from cirno.apps.cli.utils import runtime_lines_for_request, session_extra


def test_session_extra_returns_cli_apps_only_when_present() -> None:
    cli_apps = [{"name": "zoom"}]
    assert session_extra({"cli_apps": cli_apps}) == {"cli_apps": cli_apps}
    assert session_extra({}) == {}
    assert session_extra(None) == {}


def test_cli_app_mentions_inject_runtime_metadata(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr("cirno.apps.cli.service.get_runtime_subdir", lambda _name: data_dir)
    manager = CliAppManager(workspace=tmp_path)
    manager._save_installed(
        {
            "zoom": {
                "entry_point": "cli-anything-zoom",
                "source": "harness",
            },
            "krita": {
                "entry_point": "cli-anything-krita",
                "source": "harness",
            },
        }
    )

    lines = runtime_lines_for_request(
        "please use @zoom tonight; ignore @krita?",
        {},
        tmp_path,
    )

    joined = "\n".join(lines)
    assert "CLI App Mention: @zoom" in joined
    assert "tool=apps__run" in joined
    assert "entry_point=cli-anything-zoom" in joined
    assert f"skill={cli_app_skill_path('zoom')}" in joined


def test_structured_cli_app_attachment_resolves_legacy_name_in_home(tmp_path):
    legacy = tmp_path / "skills" / "cli-app-unimol_tools" / "SKILL.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("# Legacy Uni-Mol\n", encoding="utf-8")
    lines = runtime_lines_for_request(
        "please use @unimol_tools",
        {
            "cli_apps": [{
                "name": "unimol_tools",
                "entry_point": "cli-anything-unimol-tools",
            }],
        },
        tmp_path,
    )

    joined = "\n".join(lines)
    assert "CLI App Attachment: @unimol_tools" in joined
    assert "tool=apps__run" in joined
    assert "entry_point=cli-anything-unimol-tools" in joined
    assert f"skill={cli_app_skill_path('unimol_tools')}" in joined
