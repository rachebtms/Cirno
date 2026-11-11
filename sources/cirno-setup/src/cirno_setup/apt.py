"""Persist APT package intent and archives, then restore missing system packages."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, cast

APT_CONFIG_DIR = Path("/etc/apt/apt.conf.d")
APT_PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?(?:=[a-zA-Z0-9.+:~_-]+)?")
DEFAULT_TIMEOUT = 1800


class AptPolicy(Protocol):
    restore_apt: bool


class AptContext(Protocol):
    home: Path
    assets: Path
    apt_updated: bool

    @property
    def policy(self) -> AptPolicy: ...

    @property
    def root(self) -> Path: ...

    def run(self, arguments: list[str], *, env_override: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]: ...


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as output:
        temporary = Path(output.name)
        output.write(json.dumps(value, indent=2) + "\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def configure_cache(context: AptContext) -> None:
    cache = context.root / "apt" / "archives"
    if not cache.resolve().is_relative_to(context.root.resolve()):
        raise ValueError("APT cache must stay inside the instance tool directory")
    (cache / "partial").mkdir(parents=True, exist_ok=True)
    (APT_CONFIG_DIR / "docker-clean").unlink(missing_ok=True)
    (APT_CONFIG_DIR / "99cirno-cache").write_text(
        f"Dir::Cache::archives {json.dumps(str(cache))};\n",
        encoding="utf-8",
    )


def manual_packages() -> set[str]:
    result = subprocess.run(
        ["/usr/bin/apt-mark", "showmanual"],
        check=True,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.splitlines())


def snapshot_base(path: Path) -> None:
    write_json(path, sorted(manual_packages()))


def record(context: AptContext, *, managed: bool | None = None) -> None:
    import fcntl

    directory = context.root / "apt"
    if not directory.resolve().is_relative_to(context.root.resolve()):
        raise ValueError("APT package records must stay inside the instance tool directory")
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(directory / "record.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        base_path = context.assets / "base-apt-packages.json"
        if not base_path.exists():
            base_path = directory / "base-packages.json"
        base = set(json.loads(base_path.read_text()))
        current = manual_packages()
        managed_packages = set(package_record(context, "managed.json"))
        observed = set(package_record(context, "observed.json"))
        managed_transaction = os.environ.get("CIRNO_APT_MANAGED") == "1" if managed is None else managed
        if not managed_transaction:
            managed_packages.difference_update(current - observed)
        write_json(directory / "managed.json", sorted(managed_packages))
        write_json(directory / "observed.json", sorted(current))
        write_json(directory / "packages.json", sorted(current - base - managed_packages))
    # The normal backup process runs as the Cirno user.
    uid = (context.home / ".cirno").stat().st_uid
    gid = (context.home / ".cirno").stat().st_gid
    for parent, directories, files in os.walk(directory):
        for path in [Path(parent), *(Path(parent) / name for name in directories + files)]:
            os.chown(path, uid, gid, follow_symlinks=False)


def observe(context: AptContext) -> None:
    path = context.root / "apt/observed.json"
    current = sorted(manual_packages())
    write_json(path, current)
    if not (context.assets / "base-apt-packages.json").exists() and not (path.parent / "base-packages.json").exists():
        write_json(path.parent / "base-packages.json", current)
    owner = (context.home / ".cirno").stat()
    for item in (path, path.parent / "base-packages.json"):
        if item.exists():
            os.chown(item, owner.st_uid, owner.st_gid, follow_symlinks=False)


def recorded_packages(context: AptContext) -> list[str]:
    return package_record(context, "packages.json")


def package_record(context: AptContext, filename: str) -> list[str]:
    path = context.root / "apt" / filename
    packages: object = json.loads(path.read_text()) if path.exists() else []
    if not isinstance(packages, list) or any(
        not isinstance(name, str) or not APT_PACKAGE.fullmatch(name) for name in cast(list[object], packages)
    ):
        raise ValueError(f"Invalid APT package record: {path}")
    return cast(list[str], packages)


def installed_packages() -> dict[str, str]:
    result = subprocess.run(
        ["/usr/bin/dpkg-query", "-W", "-f=${Package}\t${binary:Package}\t${Version}\t${Status}\n"],
        check=True,
        text=True,
        capture_output=True,
    )
    installed: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, qualified_name, version, status = line.split("\t", 3)
        if status == "install ok installed":
            installed[name] = installed[qualified_name] = version
    return installed


def restore(context: AptContext) -> None:
    wanted = {
        name.partition("=")[0]: name
        for name in (recorded_packages(context) if context.policy.restore_apt else [])
    }
    installed = installed_packages()
    missing: list[str] = []
    for specification in wanted.values():
        name, _, version = specification.partition("=")
        if name not in installed or (version and installed[name] != version):
            missing.append(specification)
    if not missing:
        print("[tools] APT dependencies are present", flush=True)
        return
    install(context, missing)


def install(context: AptContext, specifications: list[str], *, managed: bool = False) -> None:
    installed = installed_packages()
    missing: list[str] = []
    for specification in specifications:
        name, _, version = specification.partition("=")
        if name not in installed or (version and installed[name] != version):
            missing.append(specification)
    if not missing:
        return
    directory = context.root / "apt" / "archives"
    (directory / "partial").mkdir(parents=True, exist_ok=True)
    if not context.apt_updated:
        context.run(["/usr/bin/apt-get", "update"])
        context.apt_updated = True
    if managed:
        previous = set(package_record(context, "managed.json"))
        previous.update(item.partition("=")[0] for item in missing)
        write_json(context.root / "apt/managed.json", sorted(previous))
    context.run([
        "/usr/bin/apt-get", "-o", f"Dir::Cache::archives={directory}",
        "-y", "--no-install-recommends", "install", "--", *missing,
    ], env_override={"DEBIAN_FRONTEND": "noninteractive", "CIRNO_APT_MANAGED": "1" if managed else "0"})
    record(context, managed=managed)
