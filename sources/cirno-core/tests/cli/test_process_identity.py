from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cirno.cli.commands import app
from cirno.cli.process_identity import (
    _set_process_title,
    named_executable,
    set_cli_process_identity,
)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["agent"], "cirno-agent"),
        (["gateway", "--background"], "cirno-gateway"),
        (["webui"], "cirno-webui"),
        (["status"], "cirno"),
        ([], "cirno"),
    ],
)
def test_cli_process_identity_uses_product_and_role(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    expected: str,
) -> None:
    titles: list[str] = []
    monkeypatch.setattr("cirno.cli.process_identity.os.name", "posix")
    monkeypatch.setattr("cirno.cli.process_identity._set_process_title", titles.append)

    set_cli_process_identity(args)

    assert titles == [expected]


def test_cli_process_identity_keeps_windows_launcher_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titles: list[str] = []
    monkeypatch.setattr("cirno.cli.process_identity.os.name", "nt")
    monkeypatch.setattr("cirno.cli.process_identity._set_process_title", titles.append)

    set_cli_process_identity(["agent"])

    assert titles == []


@pytest.mark.parametrize(("platform", "noenv"), [("linux", "1"), ("darwin", None)])
def test_process_title_keeps_environment_only_on_linux(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    noenv: str | None,
) -> None:
    titles: list[str] = []
    monkeypatch.setattr("cirno.cli.process_identity.sys.platform", platform)
    monkeypatch.delenv("SPT_NOENV", raising=False)
    monkeypatch.setitem(
        sys.modules, "setproctitle", types.SimpleNamespace(setproctitle=titles.append)
    )

    _set_process_title("cirno-agent")

    assert os.environ.get("SPT_NOENV") == noenv
    assert titles == ["cirno-agent"]


def test_legacy_console_entrypoint_still_sets_subcommand_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr("cirno.cli.commands.set_cli_process_identity", commands.append)

    result = CliRunner().invoke(app, ["webui", "--help"])

    assert result.exit_code == 0
    assert commands == [["webui"]]


def test_legacy_console_entrypoint_routes_bare_command_to_webui(monkeypatch):
    identities, launches = [], []
    monkeypatch.setattr("cirno.cli.commands.set_cli_process_identity", identities.append)
    monkeypatch.setattr("cirno.cli.commands.webui", lambda: launches.append("webui"))
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 0
    assert identities == [["webui"]]
    assert launches == ["webui"]


def test_named_executable_creates_stable_role_symlink(
    tmp_path: Path,
) -> None:
    if os.name == "nt":
        pytest.skip("POSIX symlink naming is not used on Windows")
    executable = tmp_path / "bun"
    executable.write_text("runtime", encoding="utf-8")

    first = Path(
        named_executable(executable.as_posix(), name="cirno-tui", directory=tmp_path / "run")
    )
    second = Path(
        named_executable(executable.as_posix(), name="cirno-tui", directory=tmp_path / "run")
    )

    assert first == second
    assert first.name == "cirno-tui"
    assert first.is_symlink()
    assert first.resolve() == executable


def test_named_executable_uses_original_on_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("cirno.cli.process_identity.os.name", "nt")

    assert (
        named_executable("bun.exe", name="cirno-tui", directory=tmp_path / "run")
        == "bun.exe"
    )
