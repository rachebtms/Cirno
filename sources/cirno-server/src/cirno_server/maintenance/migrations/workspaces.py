"""Discover v0.1.6 workspace-owned state without scanning project file trees."""

from __future__ import annotations

import json
from pathlib import Path

from cirno_core.config.home import get_default_workspace
from cirno_core.utils.atomic_file import atomic_write_lines, atomic_write_text
from cirno_server.maintenance.migrations.plan import MigrationPlan, merge_identical
from cirno_server.maintenance.migrations.sessions import remap_metadata


def workspaces(instance: Path, config: dict, stores: list[Path]) -> list[Path]:
    configured = (config.get("agents") or {}).get("defaults", {}).get("workspace", get_default_workspace())
    paths = [instance / "workspace", Path(configured).expanduser()]
    for store in stores:
        marker = store / ".workspace"
        if marker.is_file():
            paths.append(Path(marker.read_text().strip()).expanduser())
    saved = instance / "state" / "webui" / "workspace-state.json"
    if saved.exists():
        data = json.loads(saved.read_text())
        paths.extend(Path(value).expanduser() for key in ("recent_projects", "favorite_projects") for value in data.get(key, []))
    return list(dict.fromkeys(path.resolve() for path in paths if path.exists()))


def stage_automations(kind: str, roots: list[Path], instance: Path, plan: MigrationPlan, bindings: dict) -> None:
    filename, records_key = ("jobs.json", "jobs") if kind == "cron" else ("triggers.json", "triggers")
    target = instance / "state" / kind
    sources = []
    for workspace in roots:
        folder = workspace / kind
        catalog = folder / filename
        # v0.1.6 creates these four queue directories even before a first trigger.
        empty_trigger_store = (kind == "triggers" and folder.is_dir()
                               and {item.name for item in folder.iterdir()} == {"inbox", "processing", "failed", "runs", ".lock"})
        pending_cron_actions = kind == "cron" and (folder / "action.jsonl").is_file()
        if catalog.is_file() or empty_trigger_store or pending_cron_actions:
            sources.append(folder)
    if not sources:
        return
    staged = plan.root / "staged" / kind
    records: dict[str, dict] = {}
    for index, source in enumerate(dict.fromkeys(([target] if target.exists() else []) + sources)):
        catalog = source / filename
        payload = json.loads(catalog.read_text()) if catalog.exists() else {"version": 1, records_key: []}
        if payload.get("version") != 1 or not isinstance(payload.get(records_key), list):
            raise ValueError(f"Unsupported {kind} store: {source / filename}")
        for original in payload[records_key]:
            record = remap_metadata(original, bindings.get(str(source.parent.resolve()), {}))
            identifier = record["id"]
            if identifier in records and records[identifier] != record:
                raise ValueError(f"Conflicting {kind} ID {identifier!r} in {source}; originals were not changed")
            records[identifier] = record
        # Preserve run records and queued deliveries alongside the catalog.
        for child in source.iterdir():
            if child.name == "action.jsonl":
                rewritten = plan.root / "staged/actions" / f"{index}.jsonl"
                _stage_actions(child, rewritten, bindings.get(str(source.parent.resolve()), {}))
                merge_identical(rewritten, staged / child.name)
                continue
            if child.name in {filename, ".lock", "jobs.lock"}:
                continue
            merge_identical(child, staged / child.name)
    staged.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write_text(staged / filename, json.dumps({"version": 1, records_key: list(records.values())}, ensure_ascii=False, indent=2))
    plan.install(staged, target)
    for source in sources:
        if source != target:
            plan.retire(source)
        if kind == "cron":
            plan.retire(source.with_name("cron.lock"))


def retire_workspace_markers(roots: list[Path], plan: MigrationPlan) -> None:
    for workspace in roots:
        marker = workspace / ".cirno" / "workspace-id"
        if marker.is_file():
            value = marker.read_text().strip()
            if len(value) == 32 and all(char in "0123456789abcdef" for char in value):
                owned_directory = {child.name for child in marker.parent.iterdir()} == {"workspace-id"}
                plan.retire(marker.parent if owned_directory else marker)


def _stage_actions(source: Path, target: Path, mapping: dict) -> None:
    def records():
        with source.open() as stream:
            for line in stream:
                yield json.dumps(remap_metadata(json.loads(line), mapping), ensure_ascii=False)
    atomic_write_lines(target, records())
