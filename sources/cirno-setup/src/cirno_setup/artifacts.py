"""Verified downloads and replacement of managed tool directories."""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import tempfile
from pathlib import Path

from cirno_setup.context import Context


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def download(context: Context, url: str, expected: str) -> Path:
    cache = context.root / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / expected
    if destination.exists() and digest(destination) == expected:
        return destination
    partial = cache / f"{expected}.partial"
    context.run(
        [
            "/usr/bin/curl",
            "--fail",
            "--location",
            "--retry",
            "3",
            "--retry-all-errors",
            "--connect-timeout",
            "15",
            "--max-time",
            str(context.policy.timeout_seconds),
            "--output",
            str(partial),
            url,
        ]
    )
    if digest(partial) != expected:
        raise ValueError(f"Checksum mismatch downloading {url}")
    partial.replace(destination)
    return destination


def install_archive(context: Context, name: str) -> None:
    artifact = context.artifacts[name][context.architecture]
    archive = download(context, artifact["url"], artifact["sha256"])
    context.managed.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=context.managed) as temporary:
        staging = Path(temporary)
        with tarfile.open(archive) as package:
            package.extractall(staging, filter="data")
        if context.artifacts[name].get("layout") == "flat":
            source = staging / "package"
            source.mkdir()
            for member in list(staging.iterdir()):
                if member != source:
                    member.replace(source / member.name)
            (source / "bin").mkdir()
            (source / name).replace(source / "bin" / name)
        else:
            [source] = staging.iterdir()
        destination = context.managed / name
        previous = context.managed / f".{name}-previous"
        # Recover a replacement interrupted between its two directory renames.
        if previous.exists():
            if destination.exists():
                shutil.rmtree(previous)
            else:
                previous.replace(destination)
        if destination.exists():
            destination.replace(previous)
        try:
            source.replace(destination)
        except OSError:
            if previous.exists():
                previous.replace(destination)
            raise
        if previous.exists():
            shutil.rmtree(previous)
