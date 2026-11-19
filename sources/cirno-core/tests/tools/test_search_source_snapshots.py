"""Search bounds the bytes actually observed, using a replaceable snapshot."""

import io
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from cirno_core.agent.tools.search import sources
from cirno_core.agent.tools.search.grep import GrepTool


async def test_grep_rejects_growth_after_initial_file_size_check(tmp_path, monkeypatch):
    path = tmp_path / "fixture.txt"
    path.write_text("needle with more bytes")
    stat = Path.stat

    def stale_size(self, *args, **kwargs):
        result = stat(self, *args, **kwargs)
        if self == path:
            fields = list(result)
            fields[6] = 1
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(Path, "stat", stale_size)
    monkeypatch.setattr(GrepTool, "_MAX_EXPLICIT_FILE_BYTES", 8)
    result = await GrepTool(workspace=tmp_path).execute(pattern="needle", path=path.name)
    assert getattr(result, "is_error", False)
    assert "grew beyond" in result


def test_text_search_uses_atomic_snapshot_instead_of_exclusive_open(tmp_path, monkeypatch):
    path = tmp_path / "fixture.txt"
    path.write_text("fixture")
    opened = Mock(return_value=io.BytesIO(b"\xef\xbb\xbfneedle\nsecond"))
    monkeypatch.setattr(sources, "open_atomic_snapshot", opened, raising=False)

    def deny_exclusive_open(*args, **kwargs):
        raise PermissionError("exclusive open unavailable during replacement")

    monkeypatch.setattr(Path, "open", deny_exclusive_open)
    source = sources.open_source(path, None, 100)
    assert [line.text for line in source.lines] == ["needle", "second"]
    opened.assert_called_once_with(path)


@pytest.mark.parametrize("size", [7, 8])
def test_text_search_accepts_exact_limit_and_closes_snapshot(tmp_path, monkeypatch, size):
    snapshot = io.BytesIO(b"x" * size)
    monkeypatch.setattr(sources, "open_atomic_snapshot", lambda _path: snapshot, raising=False)
    source = sources.open_source(tmp_path / "fixture.txt", None, 8)
    assert [line.text for line in source.lines] == ["x" * size]
    assert snapshot.closed
