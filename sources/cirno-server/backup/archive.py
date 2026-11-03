"""Disk-backed complete instance backups and offline restore application."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from cirno_core import __version__

FORMAT = "cirno-instance-backup"
MANIFEST = "cirno-backup.json"


class Backups:
    def __init__(self, config_path: Path):
        self.config_path = config_path.resolve()
        self.root = self.config_path.parent
        self.store = self.root / "state" / "backups"

    def recommendations(self, sessions=None):
        from cirno_core.config.loader import load_config
        from cirno_core.storage.instance import InstanceData
        from cirno_core.utils.tool_environment import TOOL_ENV_KEYS
        from cirno_server.webui.workspaces import read_webui_workspace_state

        rows = {}

        def add(raw, kind):
            if not raw:
                return
            path = Path(raw).expanduser()
            if not path.exists():
                return
            resolved = path.resolve()
            key = str(resolved)
            if key not in rows:
                rows[key] = {
                    "path": key,
                    "kind": kind,
                    "included": resolved.is_relative_to(self.root),
                    "directory": path.is_dir(),
                }

        from cirno_core.config.home import get_home_path

        config = load_config(self.config_path)
        add(get_home_path(), "tools")
        add(config.agents.defaults.workspace, "workspace")
        saved = read_webui_workspace_state()
        for raw in saved["recent_projects"] + saved["favorite_projects"]:
            add(raw, "workspace")
        if sessions:
            for row in sessions.list_session_metadata():
                add((row["metadata"].get("workspace_scope") or {}).get("project_path"), "workspace")
        for project in InstanceData(self.root / "state").list("projects"):
            add(project.get("working_directory"), "workspace")
        for value in (
            "~/.config",
            "~/.ssh",
            "~/.gitconfig",
            "~/.git-credentials",
            "~/.netrc",
            "~/.aws",
            "~/.local",
            "~/.cargo",
            "~/.npm",
            "~/.bun",
            "~/.nvm",
            "~/.tea",
            "~/.xurl",
            "~/.summarize",
            "~/.mcporter",
        ):
            add(value, "tools")
        for key in TOOL_ENV_KEYS:
            if key in {"PATH", "BASH_ENV", "VIRTUAL_ENV", "CIRNO_SHELL_VENV"}:
                continue
            add(os.environ.get(key), "tools")
        shell = os.environ.get("CIRNO_SHELL_VENV")
        if shell and not shell.startswith("/app/"):
            add(shell, "tools")
        add(os.environ.get("HOMEBREW_PREFIX"), "tools")
        options = self.store / "folders.json"
        selected = (
            json.loads(options.read_text())
            if options.exists()
            else [
                str(p.resolve())
                for p in (get_home_path(), Path(config.agents.defaults.workspace).expanduser())
                if p.exists() and not p.resolve().is_relative_to(self.root)
            ]
        )
        return {
            "instance": str(self.root),
            "recommended": list(rows.values()),
            "selected": selected,
            "pending_restore": (self.store / "restore-plan.json").exists(),
        }

    def paths(self, values):
        if not isinstance(values, list) or any(not isinstance(p, str) for p in values):
            raise ValueError("Choose a list of existing absolute files or directories.")
        result = []
        for value in values:
            path = Path(value).expanduser()
            if not path.is_absolute() or not path.exists():
                raise ValueError(f"Backup path does not exist: {value}")
            path = path.resolve()
            if self.root == path or path.is_relative_to(self.root):
                continue  # The entire instance is already included.
            if self.root.is_relative_to(path):
                raise ValueError("An extra folder cannot contain the Cirno instance itself.")
            if not any(path == parent or path.is_relative_to(parent) for parent in result):
                result = [p for p in result if not p.is_relative_to(path)]
                result.append(path)
        return result

    def create(self, values):
        roots = self.paths(values)
        self.store.mkdir(parents=True, exist_ok=True)
        self.store.chmod(0o700)
        (self.store / "folders.json").write_text(json.dumps([str(p) for p in roots], indent=2))
        identifier = uuid4().hex
        output = (
            self.store
            / "exports"
            / f"cirno-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{identifier[:8]}.tar.gz"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "format": FORMAT,
            "schema": 1,
            "version": __version__,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "instance": str(self.root),
            "config_name": self.config_path.name,
            "extras": [
                {"path": str(path), "archive": f"extras/{i}", "directory": path.is_dir()}
                for i, path in enumerate(roots)
            ],
        }
        try:
            with (
                tempfile.TemporaryDirectory(dir=self.store) as temp,
                tarfile.open(output, "w:gz") as archive,
            ):
                temp = Path(temp)
                (temp / MANIFEST).write_text(json.dumps(manifest, indent=2))
                archive.add(temp / MANIFEST, arcname=MANIFEST)
                self._add(archive, self.root, "instance", temp, instance=True)
                for i, path in enumerate(roots):
                    self._add(archive, path, f"extras/{i}", temp)
            output.chmod(0o600)
            return output, manifest
        except BaseException:
            output.unlink(missing_ok=True)
            raise

    def _add(self, archive, path, name, temp, *, instance=False):
        archive.members.clear()
        archive.inodes.clear()  # Store hard-linked package files independently for portable extraction.
        if instance and path == self.store:
            # Include preferences, never recursively include exports or staged restores.
            options = self.store / "folders.json"
            if options.exists():
                archive.add(options, arcname=name + "/folders.json")
            return
        if instance and (path.name.endswith(".lock") or path.name == ".docker-bootstrap.lock"):
            return
        if path.name.endswith(("-wal", "-shm")) and _is_sqlite(path.with_name(path.name[:-4])):
            return  # Its committed contents are already in the SQLite snapshot.
        if path.is_symlink():
            archive.add(path, arcname=name, recursive=False)
        elif path.is_dir():
            archive.add(path, arcname=name, recursive=False)
            for child in sorted(path.iterdir()):
                self._add(archive, child, name + "/" + child.name, temp, instance=instance)
        elif path.is_file():
            with path.open("rb") as stream:
                sqlite = stream.read(16) == b"SQLite format 3\x00"
            if sqlite:
                copy = temp / (uuid4().hex + ".sqlite3")
                with (
                    sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source,
                    sqlite3.connect(copy) as target,
                ):
                    source.backup(target)
                os.chmod(copy, path.stat().st_mode & 0o777)
                archive.add(copy, arcname=name, recursive=False)
                copy.unlink()
            else:
                archive.add(path, arcname=name, recursive=False)
        else:
            raise ValueError(f"Cannot back up special file: {path}")

    def inspect(self, uploaded: Path):
        """Validate first, then extract without following archive-provided symlinks."""
        stage = self.store / "staging" / uuid4().hex
        stage.mkdir(parents=True, mode=0o700)
        try:
            manifest = None
            names, links = set(), []
            with tarfile.open(uploaded, "r|gz") as archive:
                for index, member in enumerate(archive):
                    if index == 0:
                        if member.name != MANIFEST or not member.isfile():
                            raise ValueError("Not a Cirno backup.")
                        manifest = json.loads(archive.extractfile(member).read(1024 * 1024 + 1))
                        if (
                            not isinstance(manifest, dict)
                            or manifest.get("format") != FORMAT
                            or manifest.get("schema") != 1
                        ):
                            raise ValueError("Unsupported backup format.")
                        if not isinstance(manifest.get("extras"), list):
                            raise ValueError("Invalid extra-folder manifest.")
                        for i, item in enumerate(manifest["extras"]):
                            if (
                                not isinstance(item, dict)
                                or item.get("archive") != f"extras/{i}"
                                or not isinstance(item.get("directory"), bool)
                                or not isinstance(item.get("path"), str)
                            ):
                                raise ValueError("Invalid extra-folder manifest.")
                        roots = {"instance", *[item["archive"] for item in manifest["extras"]]}
                    path = PurePosixPath(member.name)
                    name = path.as_posix()
                    if path.is_absolute() or ".." in path.parts or name in names:
                        raise ValueError("Unsafe or duplicate backup path.")
                    names.add(name)
                    if name in {"instance", "instance/state", "instance/state/backups"} and not member.isdir():
                        raise ValueError("Backup instance and state paths must be directories.")
                    if (
                        name.startswith("instance/state/backups/")
                        and name != "instance/state/backups/folders.json"
                    ):
                        raise ValueError("A backup cannot replace its restore workspace.")
                    if member.name != MANIFEST and not any(
                        member.name == root or member.name.startswith(root + "/") for root in roots
                    ):
                        raise ValueError("Unexpected backup archive entry.")
                    if not (member.isdir() or member.isfile() or member.issym()):
                        raise ValueError("Unsupported special archive entry.")
                    if member.issym():
                        links.append(member)
                    archive.members.clear()
            if manifest is None:
                raise ValueError("Empty backup.")
            link_names = {item.name for item in links}
            if any(
                any(parent.as_posix() in link_names for parent in PurePosixPath(name).parents)
                for name in names
            ):
                raise ValueError("A backup entry writes through a symbolic link.")
            directories = []
            # Reopen for extraction instead of retaining every TarInfo in memory.
            with tarfile.open(uploaded, "r|gz") as archive:
                for member in archive:
                    target = stage / member.name
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        directories.append((target, member.mode & 0o777))
                    elif member.isfile():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.extractfile(member) as source, target.open("wb") as dest:
                            shutil.copyfileobj(source, dest, 1024 * 1024)
                        target.chmod(member.mode & 0o777)
                    archive.members.clear()
            for member in links:
                target = stage / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(member.linkname)
            for target, mode in reversed(directories):
                target.chmod(mode)
            config_name = manifest["config_name"]
            if (
                not isinstance(config_name, str)
                or not config_name
                or Path(config_name).name != config_name
            ):
                raise ValueError("Unsafe configuration filename.")
            _validate_instance(stage / "instance", config_name)
            (stage / MANIFEST).write_text(json.dumps(manifest))
            return {"id": stage.name, **manifest}
        except BaseException:
            shutil.rmtree(stage)
            raise
        finally:
            uploaded.unlink(missing_ok=True)

    def prepare_restore(self, identifier, extra_targets):
        stage = self._stage(identifier)
        manifest = json.loads((stage / MANIFEST).read_text())
        _validate_instance(stage / "instance", manifest["config_name"])
        if not isinstance(extra_targets, dict) or extra_targets.keys() - {
            item["archive"] for item in manifest["extras"]
        }:
            raise ValueError("Invalid extra-folder restore selection.")
        targets = []
        for item in manifest["extras"]:
            value = extra_targets.get(item["archive"])
            if not value:
                continue
            if not isinstance(value, str):
                raise ValueError("Extra-folder restore locations must be strings.")
            target = Path(value).expanduser()
            if target.is_absolute():
                target = target.resolve()
            if (
                not target.is_absolute()
                or target == Path(target.anchor)
                or target.is_relative_to(self.root)
                or self.root.is_relative_to(target)
            ):
                raise ValueError(
                    "Choose an absolute extra-folder location outside the Cirno instance and filesystem root."
                )
            targets.append(
                {"source": item["archive"], "target": str(target), "directory": item["directory"]}
            )
        plan = {"id": identifier, "config_name": self.config_path.name, "extras": targets}
        path = self.store / "restore-plan.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(plan))
        temporary.chmod(0o600)
        temporary.replace(path)
        return {"restart_required": True}

    def _stage(self, identifier):
        if (
            not isinstance(identifier, str)
            or len(identifier) != 32
            or any(c not in "0123456789abcdef" for c in identifier)
        ):
            raise ValueError("Invalid staged backup ID.")
        stage = self.store / "staging" / identifier
        if not stage.is_dir():
            raise ValueError("Staged backup is unavailable; upload it again.")
        return stage

    def apply_pending(self):
        """Run before opening databases, logging or starting runtime consumers."""
        path = self.store / "restore-plan.json"
        if not path.exists():
            return False
        plan = json.loads(path.read_text())
        stage = self._stage(plan["id"])
        if plan.get("committed"):
            if (self.store / "rollback").exists():
                shutil.rmtree(self.store / "rollback")
            (self.store / "rollback-ready").unlink(missing_ok=True)
            (self.store / "rollback-restored").unlink(missing_ok=True)
            path.unlink()
            shutil.rmtree(stage)
            return True
        manifest = json.loads((stage / MANIFEST).read_text())
        source = stage / "instance"
        _validate_instance(source, manifest["config_name"])
        # External folders are merged, never pruned. A failure keeps the live instance intact.
        for item in plan["extras"]:
            _merge(stage / item["source"], Path(item["target"]))
        rollback = self.store / "rollback"
        # An interrupted prior attempt is rolled back before retrying the intact staged copy.
        if rollback.exists() or (self.store / "rollback-restored").exists():
            _recover_rollback(rollback, self.root)
        rollback.mkdir()
        try:
            for child in list(self.root.iterdir()):
                if child.name == "state":
                    for state in list(child.iterdir()):
                        if state.name != "backups":
                            saved = rollback / "state" / state.name
                            saved.parent.mkdir(exist_ok=True)
                            state.rename(saved)
                else:
                    child.rename(rollback / child.name)
            (self.store / "rollback-ready").touch()
            _merge(source, self.root)
            if manifest["config_name"] != self.config_path.name:
                (self.root / manifest["config_name"]).replace(self.config_path)
            plan["committed"] = True
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(plan))
            temporary.chmod(0o600)
            temporary.replace(path)
        except BaseException:
            _recover_rollback(rollback, self.root)
            raise
        shutil.rmtree(rollback)
        (self.store / "rollback-ready").unlink(missing_ok=True)
        path.unlink()
        shutil.rmtree(stage)
        return True


def _validate_instance(source, config_name):
    # The live restore workspace and rollback both live below state/backups.
    # Replacing any ancestor with a file/link would delete the recovery copy itself.
    for relative in (".", "state", "state/backups"):
        path = source / relative
        if path.is_symlink() or path.exists() and not path.is_dir():
            raise ValueError("Backup instance and state paths must be directories.")
    config = source / config_name
    if config.is_symlink() or not config.is_file():
        raise ValueError("Backup configuration must be a regular file.")
    from cirno_core.config.schema import Config

    Config.model_validate_json(config.read_text())


def _recover_rollback(rollback, root):
    ready = rollback.parent / "rollback-ready"
    restored = rollback.parent / "rollback-restored"
    if not restored.exists():
        if ready.exists():
            _clear_instance(root)
        # Keep every original until the entire recovery succeeds. Moving files
        # out would lose them if another interruption makes us clear root again.
        # These are live originals, including their WAL/SHM files, not snapshots.
        _merge(rollback, root, sqlite_snapshot=False)
        restored.touch()
    if rollback.exists():
        shutil.rmtree(rollback)
    ready.unlink(missing_ok=True)
    restored.unlink(missing_ok=True)


def _clear_instance(root):
    for child in root.iterdir():
        if child.name == "state":
            for state in child.iterdir():
                if state.name != "backups":
                    _remove(state)
        else:
            _remove(child)


def _remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _merge(source, target, *, sqlite_snapshot=True):
    if source.is_dir() and not source.is_symlink():
        if target.is_symlink() or target.exists() and not target.is_dir():
            _remove(target)
        target.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _merge(child, target / child.name, sqlite_snapshot=sqlite_snapshot)
        shutil.copystat(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            _remove(target)
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        else:
            if sqlite_snapshot and _is_sqlite(source):
                for suffix in ("-wal", "-shm"):
                    target.with_name(target.name + suffix).unlink(missing_ok=True)
            shutil.copy2(source, target)


def _is_sqlite(path):
    if not path.is_file() or path.is_symlink():
        return False
    with path.open("rb") as stream:
        return stream.read(16) == b"SQLite format 3\x00"
