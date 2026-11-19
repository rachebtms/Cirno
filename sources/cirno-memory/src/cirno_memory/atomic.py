"""Publish synchronized memory files before committing their catalog records."""

from __future__ import annotations

import errno
import os
from pathlib import Path


def sync_directory(directory: Path) -> None:
    if os.name == "nt":
        return  # Windows does not support opening directories with os.open.
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno != errno.EINVAL:
                raise
    finally:
        os.close(descriptor)


def ensure_directory(directory: Path) -> None:
    """Persist newly created directory links as well as the eventual file link."""
    missing = []
    ancestor = directory
    while not ancestor.exists():
        missing.append(ancestor)
        ancestor = ancestor.parent
    directory.mkdir(parents=True, exist_ok=True)
    for created in reversed(missing):
        sync_directory(created.parent)


def publish_file(temporary: Path, destination: Path) -> None:
    """The caller must flush and fsync its stream before publishing it here."""
    temporary.replace(destination)
    sync_directory(destination.parent)
