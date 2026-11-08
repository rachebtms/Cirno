"""No-follow traversal includes Windows junction semantics and visible stat failures."""

import os
import stat
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from cirno_core.utils.directory_tree import walk_tree


def test_windows_junction_is_yielded_as_a_link_without_scanning_its_target(tmp_path, monkeypatch):
    # Windows reports junctions as directories carrying FILE_ATTRIBUTE_REPARSE_POINT.
    child = SimpleNamespace(
        path=str(tmp_path / "external"),
        name="external",
        stat=lambda **kwargs: SimpleNamespace(
            st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
        ),
    )

    @contextmanager
    def scandir(path):
        assert path == tmp_path, "Traversal descended into the junction target"
        yield iter([child])

    monkeypatch.setattr(os, "scandir", scandir)
    entries = list(walk_tree(tmp_path))
    assert len(entries) == 1
    assert entries[0].is_symlink and not entries[0].is_dir


def test_entry_stat_failure_is_not_an_empty_tree(tmp_path, monkeypatch):
    def fail(**kwargs):
        raise OSError("Cannot inspect tree entry")

    @contextmanager
    def scandir(path):
        yield iter([SimpleNamespace(path=str(tmp_path / "entry"), name="entry", stat=fail)])

    monkeypatch.setattr(os, "scandir", scandir)
    with pytest.raises(OSError, match="Cannot inspect tree entry"):
        list(walk_tree(tmp_path))
