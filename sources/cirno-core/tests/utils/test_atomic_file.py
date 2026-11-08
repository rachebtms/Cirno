"""Atomic publication, durable completion and visible filesystem failures."""

import errno
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from cirno_core.utils import atomic_file
from cirno_core.utils.atomic_file import atomic_write_lines, atomic_write_text


def test_atomic_write_text_fsyncs_file_and_parent_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(atomic_file, "_DIRECTORY_FSYNC_SUPPORTED", True)
    target = tmp_path / "pairing.json"
    fsync_calls: list[int] = []
    closed_fds: list[int] = []

    def fake_fsync(fd: int) -> None:
        fsync_calls.append(fd)

    with monkeypatch.context() as patch:
        patch.setattr(atomic_file.os, "fsync", fake_fsync)
        patch.setattr(atomic_file.os, "open", lambda path, flags: 12345)
        patch.setattr(atomic_file.os, "close", lambda fd: closed_fds.append(fd))

        atomic_write_text(target, '{"approved": {}}')

    assert target.read_text(encoding="utf-8") == '{"approved": {}}'
    assert len(fsync_calls) == 2
    assert fsync_calls[0] != 12345
    assert fsync_calls[1] == 12345
    assert closed_fds == [12345]


def test_windows_directory_sync_is_skipped_without_suppressing_file_sync(tmp_path, monkeypatch):
    target = tmp_path / "pairing.json"
    synced = []
    monkeypatch.setattr(atomic_file, "_DIRECTORY_FSYNC_SUPPORTED", False)
    monkeypatch.setattr(
        atomic_file.os, "open", lambda *_: pytest.fail("Unsupported directory open")
    )
    monkeypatch.setattr(atomic_file.os, "fsync", synced.append)
    atomic_write_text(target, '{"pending": {}}')
    assert target.read_text() == '{"pending": {}}'
    assert len(synced) == 1


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_atomic_write_text_creates_parent_and_replaces_exact_content(
    tmp_path: Path,
    newline: str,
) -> None:
    target = tmp_path / "runs" / "record.json"
    atomic_write_text(target, "old")
    assert target.read_text(encoding="utf-8") == "old"

    content = f'{{{newline}  "message": "café"{newline}}}{newline}'
    atomic_write_text(target, content)
    assert target.read_bytes() == content.encode("utf-8")

    atomic_write_text(target, "")
    assert target.read_text(encoding="utf-8") == ""


def test_atomic_write_lines_round_trip_replaces_target(tmp_path: Path) -> None:
    """Missing newline insertion or a non-atomic partial write drops records."""
    target = tmp_path / "history.jsonl"
    target.write_text("old\n", encoding="utf-8")

    atomic_write_lines(target, ['{"a": 1}', "café"])

    assert target.read_text(encoding="utf-8") == '{"a": 1}\ncafé\n'
    assert target.read_bytes() == '{"a": 1}\ncafé\n'.encode("utf-8")
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("name", ["status.json", "更新状态-🐈.json"])
def test_atomic_record_reader_does_not_block_concurrent_replacement(
    tmp_path: Path, name: str
) -> None:
    """The update UI can poll while a detached worker commits its next phase."""
    from cirno_core.utils.atomic_file import open_atomic_snapshot, read_atomic_bytes

    target = tmp_path / name
    atomic_write_lines(target, ['{"phase":"checking"}'])
    with open_atomic_snapshot(target) as previous:
        atomic_write_lines(target, ['{"phase":"stopping"}'])
        assert previous.read() == b'{"phase":"checking"}\n'
        assert read_atomic_bytes(target) == b'{"phase":"stopping"}\n'
    assert read_atomic_bytes(target, max_bytes=2) == b'{"'


def test_atomic_write_lines_empty_input_replaces_file_with_empty(tmp_path: Path) -> None:
    target = tmp_path / "history.jsonl"
    target.write_text("old\n", encoding="utf-8")

    atomic_write_lines(target, [])

    assert target.read_text(encoding="utf-8") == ""
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
@pytest.mark.parametrize(
    "write",
    [atomic_write_text, lambda path, text: atomic_write_lines(path, [text])],
    ids=["text", "lines"],
)
def test_atomic_writes_clean_temp_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
    write: Callable[[Path, str], None],
) -> None:
    """A failed replace must not leave a temp file or change the target."""
    target = tmp_path / "history.jsonl"
    target.write_text("kept\n", encoding="utf-8")

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise error_type("replace failed")

    monkeypatch.setattr("cirno_core.utils.atomic_file.replace_atomic", fail_replace)

    with pytest.raises(error_type, match="replace failed"):
        write(target, "new")

    assert target.read_text(encoding="utf-8") == "kept\n"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_lines_leaves_unrelated_tmp_sibling(tmp_path: Path) -> None:
    """A unique temp name must not clobber a sibling ``*.tmp`` file."""
    target = tmp_path / "history.jsonl"
    stale = target.with_name(target.name + ".tmp")
    stale.write_text("stale", encoding="utf-8")

    atomic_write_lines(target, ["fresh"])

    assert target.read_text(encoding="utf-8") == "fresh\n"
    assert stale.read_text(encoding="utf-8") == "stale"


def test_atomic_write_lines_skips_fsync_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "session.jsonl"
    fsync_calls: list[int] = []
    monkeypatch.setattr(atomic_file.os, "fsync", lambda fd: fsync_calls.append(fd))

    atomic_write_lines(target, ["line"], fsync=False)

    assert target.read_text(encoding="utf-8") == "line\n"
    assert fsync_calls == []


def test_posix_directory_permission_error_is_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A POSIX directory permission failure must not report durable success."""
    target = tmp_path / "history.jsonl"
    opened: list[tuple[object, int]] = []
    real_open = atomic_file.os.open

    def open_directory(path: object, flags: int, *args: object, **kwargs: object) -> int:
        opened.append((path, flags))
        if flags == os.O_RDONLY:
            raise PermissionError("directory open denied")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(atomic_file, "_DIRECTORY_FSYNC_SUPPORTED", True)
    monkeypatch.setattr(atomic_file.os, "open", open_directory)

    with pytest.raises(PermissionError, match="directory open denied"):
        atomic_write_lines(target, ["ok"])

    assert target.read_text(encoding="utf-8") == "ok\n"
    assert opened == [(str(atomic_file.io_path(tmp_path)), os.O_RDONLY)]


@pytest.mark.parametrize("error_number", [errno.EINVAL, errno.EIO], ids=["unsupported", "io-error"])
@pytest.mark.parametrize(
    ("write", "expected_content"),
    [(atomic_write_text, "ok"), (lambda path, text: atomic_write_lines(path, [text]), "ok\n")],
    ids=["text", "lines"],
)
def test_atomic_writes_directory_fsync_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
    write: Callable[[Path, str], None],
    expected_content: str,
) -> None:
    """Only unsupported directory fsync errors are ignored; descriptors always close.

    The directory fd is faked so both supported/unsupported filesystem paths
    can be checked without depending on the host filesystem.
    """
    monkeypatch.setattr(atomic_file, "_DIRECTORY_FSYNC_SUPPORTED", True)
    target = tmp_path / "session.jsonl"
    directory_fd = 12345
    fsync_calls = 0
    real_fsync = atomic_file.os.fsync
    real_open = atomic_file.os.open
    real_close = atomic_file.os.close
    opened: list[tuple[object, int]] = []
    closed: list[int] = []

    def tracking_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if flags == os.O_RDONLY:
            opened.append((path, directory_fd))
            return directory_fd
        return real_open(path, flags, *args, **kwargs)

    def tracking_close(fd: int) -> None:
        closed.append(fd)
        if fd != directory_fd:
            real_close(fd)

    def fsync_then_error(fd: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 1:
            real_fsync(fd)
            return
        raise OSError(error_number, "directory fsync failed")

    monkeypatch.setattr(atomic_file.os, "open", tracking_open)
    monkeypatch.setattr(atomic_file.os, "close", tracking_close)
    monkeypatch.setattr(atomic_file.os, "fsync", fsync_then_error)

    if error_number == errno.EINVAL:
        write(target, "ok")
    else:
        with pytest.raises(OSError) as exc_info:
            write(target, "ok")
        assert exc_info.value.errno == error_number

    assert target.read_text(encoding="utf-8") == expected_content
    assert fsync_calls == 2
    assert opened == [(str(atomic_file.io_path(tmp_path)), directory_fd)]
    assert closed == [directory_fd]
