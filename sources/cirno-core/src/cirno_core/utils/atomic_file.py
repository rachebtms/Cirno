"""Standard-library atomic record replacement, also used by the update worker."""

from __future__ import annotations

import errno
import os
import stat
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from cirno_core.utils.file_transactions import file_write_transaction

_DIRECTORY_FSYNC_SUPPORTED = os.name != "nt"


def io_path(path: Path) -> Path:
    """Use Windows' extended namespace for I/O, without changing stored identities."""
    if os.name != "nt":
        return path
    name = str(path)
    if name.startswith(("\\\\?\\", "\\\\.\\")):
        return path
    # Extended paths bypass Win32 normalization and must be absolute. Normalize
    # ordinary relative paths, separators and dot segments before adding a prefix.
    name = os.path.abspath(name)
    if name.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + name[2:])
    return Path("\\\\?\\" + name)


def open_atomic_snapshot(path: Path) -> BinaryIO:
    """Read one inode without preventing its atomic replacement on Windows."""
    if os.name != "nt":
        return path.open("rb")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # GENERIC_READ; FILE_SHARE_READ | WRITE | DELETE; OPEN_EXISTING.
    # Python's normal open omits SHARE_DELETE. Pair this handle with the POSIX
    # rename below so a short status poll cannot block journal commits.
    handle = create(str(io_path(path)), 0x80000000, 1 | 2 | 4, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close(handle)
        raise
    # open_osfhandle transfers handle ownership to the file descriptor.
    return os.fdopen(descriptor, "rb")


def replace_atomic(source: Path, destination: Path) -> None:
    """Publish a new inode while existing snapshot readers retain the old one."""
    if os.name != "nt":
        os.replace(source, destination)
        return
    source, destination = io_path(source), io_path(destination)
    import ctypes
    from ctypes import wintypes

    class RenameInfo(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("RootDirectory", wintypes.HANDLE),
                    ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * 1)]

    # MoveFileExW (Python's os.replace) rejects an open destination even when
    # readers share DELETE. FileRenameInfoEx provides atomic POSIX replacement
    # on modern Windows: old readers keep their snapshot, new readers see this
    # commit. Do not unlink first or fall back to copying a partially written file.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    rename = kernel.SetFileInformationByHandle
    rename.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    rename.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # DELETE | SYNCHRONIZE; share READ | WRITE | DELETE; OPEN_EXISTING.
    handle = create(str(source), 0x10000 | 0x100000, 1 | 2 | 4, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    unsupported = False
    try:
        name = str(destination).encode("utf-16-le")
        buffer = ctypes.create_string_buffer(ctypes.sizeof(RenameInfo) + len(name))
        info = RenameInfo.from_buffer(buffer)
        info.Flags = 1 | 2  # REPLACE_IF_EXISTS | POSIX_SEMANTICS (not IGNORE_READONLY).
        info.FileNameLength = len(name)
        ctypes.memmove(ctypes.addressof(buffer) + RenameInfo.FileName.offset, name, len(name))
        if not rename(handle, 22, buffer, len(buffer)):  # FileRenameInfoEx
            error = ctypes.get_last_error()
            # Older Windows/filesystems can lack this information class. Keep
            # their existing atomic rename behavior, never a delete/copy gap.
            # Sharing/permission errors are not treated as missing capability.
            if error not in (1, 50, 87):  # INVALID_FUNCTION, NOT_SUPPORTED, INVALID_PARAMETER
                raise ctypes.WinError(error)
            unsupported = True
    finally:
        close(handle)
    if unsupported:
        os.replace(source, destination)


def read_atomic_bytes(path: Path, *, max_bytes: int = -1) -> bytes:
    """Read a snapshot while permitting writers to atomically publish the next."""
    with open_atomic_snapshot(path) as stream:
        return stream.read(max_bytes)


def _fsync_directory_after_replace(directory: Path) -> None:
    """Fsync a directory, ignoring only unsupported platforms/filesystems."""
    if not _DIRECTORY_FSYNC_SUPPORTED:
        return
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        try:
            os.fsync(fd)
        except OSError as exc:
            if exc.errno != errno.EINVAL:
                raise
    finally:
        os.close(fd)


def _atomic_write_chunks(path: Path, chunks: Iterable[bytes], *, fsync: bool) -> None:
    with file_write_transaction([path]):
        _replace_chunks(path, chunks, fsync=fsync)


def _replace_chunks(path: Path, chunks: Iterable[bytes], *, fsync: bool) -> None:
    path = io_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = 0o600
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "xb") as handle:
            os.chmod(tmp, mode)
            for chunk in chunks:
                handle.write(chunk)
            if fsync:
                handle.flush()
                os.fsync(handle.fileno())
        replace_atomic(tmp, path)
        if fsync:
            _fsync_directory_after_replace(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
    """Durably replace exact UTF-8 text, retaining permissions; new files are private."""
    _atomic_write_chunks(path, (content.encode("utf-8"),), fsync=True)


def atomic_write_lines(path: Path, lines: Iterable[str], *, fsync: bool = True) -> None:
    """Stream UTF-8 records into one atomic replacement, adding missing newlines."""
    _atomic_write_chunks(
        path, ((line if line.endswith("\n") else line + "\n").encode("utf-8") for line in lines),
        fsync=fsync,
    )


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Durably replace bytes using the same commit and permission rules as text."""
    _atomic_write_chunks(path, (content,), fsync=True)
