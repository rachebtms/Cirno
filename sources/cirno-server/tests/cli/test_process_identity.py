"""The native process title retains Linux's environment and uses the product name."""

import os
import sys
import types

import pytest
from cirno_server.cli.process_identity import set_process_title


@pytest.mark.parametrize(("platform", "noenv"), [("linux", "1"), ("darwin", None)])
def test_process_title_keeps_environment_only_on_linux(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    noenv: str | None,
) -> None:
    titles: list[str] = []
    monkeypatch.setattr("cirno_server.cli.process_identity.sys.platform", platform)
    monkeypatch.delenv("SPT_NOENV", raising=False)
    monkeypatch.setitem(
        sys.modules, "setproctitle", types.SimpleNamespace(setproctitle=titles.append)
    )

    set_process_title("cirno")

    assert os.environ.get("SPT_NOENV") == noenv
    assert titles == ["cirno"]
