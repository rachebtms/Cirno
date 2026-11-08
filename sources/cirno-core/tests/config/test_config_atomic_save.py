"""Tests for atomic config.json writes."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config


def test_save_config_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.model = "saved-model"
    save_config(config, path)
    loaded = load_config(path)
    assert loaded.agents.defaults.model == "saved-model"


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose POSIX file modes")
def test_save_config_preserves_existing_file_mode(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o600)

    save_config(Config(), path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_config_preserves_existing_file_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    save_config(Config(), path)
    before = path.read_text(encoding="utf-8")

    def boom(source: Path, target: Path) -> None:  # noqa: ARG001
        raise OSError("simulated crash before replace")

    monkeypatch.setattr("cirno_core.utils.atomic_file.replace_atomic", boom)
    with pytest.raises(OSError, match="simulated crash"):
        save_config(Config(), path)

    assert path.read_text(encoding="utf-8") == before
    assert json.loads(before)  # still valid JSON


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose POSIX file modes")
def test_new_config_is_private_even_with_a_public_umask(tmp_path):
    path = tmp_path / "config.json"
    previous = os.umask(0o022)
    try:
        save_config(Config(), path)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
