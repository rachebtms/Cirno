"""Resumable staged replacements with originals retained outside working directories."""

from __future__ import annotations

import filecmp
import json
import shutil
from pathlib import Path

from cirno_core.utils.atomic_file import atomic_write_text


def copy_path(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        target.symlink_to(source.readlink())
    elif source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target)


def merge_identical(source: Path, target: Path) -> None:
    """Merge disjoint artifacts; reject different files sharing an owned path."""
    if not target.exists() and not target.is_symlink():
        copy_path(source, target)
        return
    if source.is_dir() and not source.is_symlink() and target.is_dir() and not target.is_symlink():
        for child in source.iterdir():
            merge_identical(child, target / child.name)
        return
    if source.is_symlink() and target.is_symlink() and source.readlink() == target.readlink():
        return
    if source.is_file() and target.is_file() and filecmp.cmp(source, target, shallow=False):
        return
    raise ValueError(f"Conflicting migration artifact: {source} and {target}")


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def preserve_sqlite_sidecars(staged: Path, target: Path, original: Path) -> None:
    """Old committed WAL frames belong to the retained original, not its replacement."""
    if not staged.is_file():
        return
    with staged.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\x00":
            return
    for suffix in ("-wal", "-shm", "-journal"):
        source, saved = Path(str(target) + suffix), Path(str(original) + suffix)
        if source.exists():
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists():
                raise FileExistsError(f"Migration sidecar already has an original: {saved}")
            source.rename(saved)


class MigrationPlan:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "plan.json"
        self.installs: list[dict] = []
        self.retirements: list[dict] = []

    def install(self, staged: Path, target: Path) -> None:
        if target.is_symlink():
            raise ValueError(f"Migration target must not be a symbolic link: {target}")
        self.installs.append({"staged": str(staged), "target": str(target),
                              "original": str(self.root / "originals" / f"target-{len(self.installs)}"),
                              "done": False})

    def retire(self, source: Path) -> None:
        if source.exists() or source.is_symlink():
            if any(source == Path(item["source"]) for item in self.retirements):
                return
            self.retirements.append({"source": str(source), "saved": str(self.root / "originals" / f"retired-{len(self.retirements)}"), "done": False})

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        atomic_write_text(self.path, json.dumps({"installs": self.installs, "retirements": self.retirements}, indent=2))

    @classmethod
    def load(cls, root: Path) -> MigrationPlan:
        plan = cls(root)
        data = json.loads(plan.path.read_text())
        plan.installs, plan.retirements = data["installs"], data["retirements"]
        return plan

    def apply(self) -> None:
        for item in self.installs:
            if item["done"]:
                continue
            staged, target, original = (Path(item[key]) for key in ("staged", "target", "original"))
            # A missing staged path means its atomic rename already completed.
            if staged.exists():
                preserve_sqlite_sidecars(staged, target, original)
                if target.exists():
                    original.parent.mkdir(parents=True, exist_ok=True)
                    target.rename(original)
                target.parent.mkdir(parents=True, exist_ok=True)
                staged.rename(target)
            elif not target.exists():
                raise FileNotFoundError(f"Migration staging and target are missing: {target}")
            item["done"] = True
            self.save()
        for item in self.retirements:
            if item["done"]:
                continue
            source, saved = Path(item["source"]), Path(item["saved"])
            if not saved.exists() and not saved.is_symlink():
                temporary = saved.with_name(saved.name + ".copying")
                if temporary.exists() or temporary.is_symlink():
                    remove_path(temporary)
                copy_path(source, temporary)
                temporary.rename(saved)
            if source.exists() or source.is_symlink():
                remove_path(source)
            item["done"] = True
            self.save()
        (self.root / "completed").touch(mode=0o600)
