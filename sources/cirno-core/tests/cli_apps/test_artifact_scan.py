"""Artifact scans have real enumeration bounds and remain inside their working tree."""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from cirno_core.apps.cli import output


def test_directory_enumeration_stops_at_the_scan_budget(tmp_path, monkeypatch):
    files = [tmp_path / f"result-{index}.txt" for index in range(3)]
    for path in files:
        path.write_text("result")
    consumed = []
    closed = []

    def bounded_entries():
        for path in files:
            consumed.append(path)
            yield path
        raise AssertionError("Scan enumerated more entries than its configured budget")

    @contextmanager
    def scandir(directory):
        assert Path(directory) == tmp_path
        try:
            yield (SimpleNamespace(path=str(path)) for path in bounded_entries())
        finally:
            closed.append(True)

    monkeypatch.setattr(output, "_MAX_ARTIFACT_SCAN_PATHS", 3)
    monkeypatch.setattr(Path, "iterdir", lambda path: bounded_entries())
    monkeypatch.setattr("os.scandir", scandir)
    assert set(output._iter_artifact_candidates(tmp_path)) == set(files)
    assert consumed == files
    assert closed == [True]


def test_artifact_symlink_cannot_escape_working_tree(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "private-result.txt"
    outside.write_text("outside result")
    (project / "shortcut.txt").symlink_to(outside)
    own = project / "result.txt"
    own.write_text("own result")
    (project / "result-alias.txt").symlink_to(own)
    assert output._artifact_snapshot(project) == {own: (own.stat().st_mtime_ns, own.stat().st_size)}


def test_unresolvable_symlink_does_not_abort_artifact_report(tmp_path):
    (tmp_path / "loop.txt").symlink_to("loop.txt")
    assert output._artifact_snapshot(tmp_path) == {}
