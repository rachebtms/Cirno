"""CLI-Anything catalog, install state, and safe CLI execution."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from cirno_core.apps.cli import branding, command_support, contracts, paths, records, resources
from cirno_core.apps.cli import output as cli_output
from cirno_core.apps.cli.catalog import RegistryCatalog
from cirno_core.apps.cli.commands import CliCommands
from cirno_core.apps.cli.process import run_cli
from cirno_core.apps.protocol import app_manifest, compact_dict
from cirno_core.config.paths import get_runtime_subdir
from cirno_core.security.workspace_policy import is_path_within
from cirno_core.skills.metadata import parse_skill_metadata, valid_skill_metadata
from loguru import logger

_MENTION_RE = re.compile(r"(^|[\s([{])@([a-z0-9_-]+)\b", re.IGNORECASE)


def _now() -> float:
    return time.time()


class CliAppManager:
    """Manage CLI-Anything registry entries and local install state."""

    def __init__(
        self,
        *,
        workspace: Path,
        data_dir: Path | None = None,
        runtime: contracts.CliAppsRuntimeConfig | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.data_dir = Path(data_dir) if data_dir is not None else get_runtime_subdir("cli-apps")
        self.runtime = runtime or contracts.CliAppsRuntimeConfig()
        self.commands = CliCommands(self.runtime)
        self.registry = RegistryCatalog(self.data_dir, self.runtime)
        self.installed = records.InstalledApps(self.data_dir / "installed.json")

    def installed_names(self) -> list[str]:
        """Return registry names explicitly installed through CLI Apps."""
        return sorted(str(name) for name in self.installed.read())

    def _manifest_source(self, app: dict[str, Any]) -> str:
        source = str(app.get("_source") or "harness")
        if source == "extensions":
            return "cirno-extension"
        return f"cli-anything:{source}"

    def _trust_registry(self, app: dict[str, Any]) -> str:
        return (
            "cirno-extension" if str(app.get("_source") or "") == "extensions" else "cli-anything"
        )

    def mentioned_installed_apps(self, text: str) -> list[dict[str, str]]:
        """Return installed CLI Apps referenced as ``@name`` in user text."""
        if "@" not in text:
            return []
        installed = self.installed.read()
        if not installed:
            return []
        installed_by_name = {
            str(name).lower(): (str(name), records._as_object_dict(data) or {})
            for name, data in installed.items()
        }
        seen: set[str] = set()
        mentions: list[dict[str, str]] = []
        for match in _MENTION_RE.finditer(text):
            wanted = str(match.group(2)).lower()
            if wanted in seen or wanted not in installed_by_name:
                continue
            installed_name, data = installed_by_name[wanted]
            seen.add(wanted)
            entry_point = str(data.get("entry_point") or "")
            mentions.append(
                {
                    "name": installed_name,
                    "entry_point": entry_point,
                    "source": str(data.get("source") or ""),
                    "skill": str(paths.cli_app_skill_path(installed_name)),
                    "tool": "run_cli_app",
                }
            )
        return mentions

    def _app_payload(
        self,
        app: dict[str, Any],
        installed: dict[str, Any],
    ) -> dict[str, Any]:
        name = str(app["name"])
        entry_point = str(app.get("entry_point") or "")
        install_supported = self.commands._install_supported(app)
        is_installed = name in installed
        available = bool(entry_point and shutil.which(entry_point))
        if is_installed and available:
            status = "installed"
        elif is_installed:
            status = "missing"
        elif not install_supported:
            status = "unsupported"
        elif available:
            status = "available"
        else:
            status = "not_installed"
        logo_url, brand_color = branding._brand_payload(app)
        return {
            "name": name,
            "display_name": app.get("display_name") or name,
            "category": app.get("category") or "uncategorized",
            "description": branding._catalog_description(app),
            "requires": app.get("requires") or "",
            "source": app.get("_source") or "harness",
            "entry_point": entry_point,
            "install_supported": install_supported,
            "installed": is_installed,
            "available": available,
            "status": status,
            "logo_url": logo_url,
            "brand_color": brand_color,
            "skill_installed": paths.cli_app_skill_path(name).is_file(),
            "manifest": self._manifest_payload(app, logo_url=logo_url, brand_color=brand_color),
        }

    def _package_ref(self, app: dict[str, Any]) -> dict[str, Any] | None:
        strategy = self.commands._strategy(app)
        name = ""
        if strategy == "pip":
            try:
                uninstall = self.commands._pip_uninstall_argv(app)
            except contracts.CliAppError:
                uninstall = None
            name = uninstall[-1] if uninstall else ""
        elif strategy == "npm":
            name = str(app.get("npm_package") or "").strip()
        elif strategy in {"brew", "uv"}:
            try:
                uninstall = self.commands._argv_for_action(app, "uninstall")
            except contracts.CliAppError:
                uninstall = None
            if uninstall:
                name = uninstall[-1]
        if not strategy or strategy in {"unsupported", "bundled"}:
            return None
        return compact_dict({"manager": strategy, "name": name})

    def _manifest_payload(
        self,
        app: dict[str, Any],
        *,
        logo_url: str | None,
        brand_color: str | None,
    ) -> dict[str, Any]:
        name = str(app["name"])
        entry_point = str(app.get("entry_point") or "")
        strategy = self.commands._strategy(app)
        skill_path = str(paths.cli_app_skill_path(name))
        plugin_path = str(paths.cli_app_skill_path(name).parent)
        capabilities = [
            compact_dict(
                {
                    "type": "cli",
                    "entry_point": entry_point,
                    "package": self._package_ref(app),
                }
            ),
            {"type": "skill", "path": skill_path},
        ]
        install_supported = self.commands._install_supported(app)
        install = compact_dict(
            {
                "supported": install_supported,
                "strategy": strategy,
                "managed_paths": [plugin_path],
                "verification": ["entry_point_available"] if entry_point else [],
            }
        )
        remove = compact_dict(
            {
                "supported": strategy != "unsupported",
                "strategy": strategy,
                "managed_paths": [plugin_path],
                "verification": (
                    ["package_manager_ok", "entry_point_absent", "managed_paths_absent"]
                    if strategy not in {"bundled", "unsupported"}
                    else ["cirno_state_absent", "managed_paths_absent"]
                ),
            }
        )
        return app_manifest(
            app_id=name,
            display_name=str(app.get("display_name") or name),
            version=str(app.get("version") or ""),
            description=branding._catalog_description(app),
            category=str(app.get("category") or "uncategorized"),
            source=self._manifest_source(app),
            logo_url=logo_url,
            brand_color=brand_color,
            capabilities=capabilities,
            install=install,
            remove=remove,
            trust={
                "registry": self._trust_registry(app),
                "level": "catalog",
                "review_status": "catalog_entry",
            },
        )

    def payload(self, *, force_refresh: bool = False, cache_only: bool = False) -> dict[str, Any]:
        apps, updated = self.registry.catalog(force_refresh=force_refresh, cache_only=cache_only)
        installed = self.installed.read()
        rows = [self._app_payload(app, installed) for app in apps]
        rows.sort(key=lambda item: (str(item["category"]), str(item["display_name"]).lower()))
        return {
            "apps": rows,
            "installed_count": sum(1 for item in rows if item["installed"]),
            "catalog_updated_at": updated,
        }

    def installed_payload(self) -> dict[str, Any]:
        installed = self.installed.read()
        cached_apps, _ = self.registry.catalog(cache_only=True)
        cached_by_name = {
            str(app.get("name") or "").lower(): app for app in cached_apps if app.get("name")
        }
        rows: list[dict[str, Any]] = []
        for name, raw_entry in sorted(installed.items()):
            entry = records._as_object_dict(raw_entry)
            if entry is None:
                entry = {}
            strategy = str(entry.get("strategy") or "bundled")
            cached_app = cached_by_name.get(str(name).lower(), {})
            app: dict[str, Any] = {
                "name": str(name),
                "display_name": str(
                    cached_app.get("display_name") or entry.get("display_name") or name
                ),
                "category": str(cached_app.get("category") or entry.get("category") or "installed"),
                "description": str(cached_app.get("description") or entry.get("description") or ""),
                "requires": str(cached_app.get("requires") or entry.get("requires") or ""),
                "_source": str(entry.get("source") or "local"),
                "entry_point": str(entry.get("entry_point") or ""),
                "package_manager": strategy,
                "logo_url": cached_app.get("logo_url") or entry.get("logo_url"),
                "brand_color": cached_app.get("brand_color") or entry.get("brand_color"),
            }
            rows.append(self._app_payload(app, installed))
        return {
            "apps": rows,
            "installed_count": len(rows),
            "catalog_updated_at": None,
        }

    def _installed_entry(self, app: dict[str, Any]) -> dict[str, Any]:
        entry_point = str(app.get("entry_point") or "")
        strategy = self.commands._strategy(app)
        entry: dict[str, Any] = {
            "version": app.get("version") or "unknown",
            "entry_point": entry_point,
            "source": app.get("_source") or "harness",
            "strategy": strategy,
            "installed_at": int(_now()),
        }
        for field in (
            "display_name",
            "category",
            "description",
            "requires",
            "logo_url",
            "brand_color",
        ):
            value = app.get(field)
            if value not in (None, ""):
                entry[field] = value
        resolved = shutil.which(entry_point) if entry_point else None
        if resolved:
            entry["entry_point_path"] = resolved
        if strategy == "pip":
            distribution = command_support._console_script_distribution(entry_point)
            if distribution:
                entry["pip_distribution"] = distribution
        return entry

    def _fetch_skill_content(self, app: dict[str, Any]) -> str | None:
        skill_md = str(app.get("skill_md") or "").strip()
        if not skill_md:
            return None
        url = paths._skill_content_url(
            skill_md, raw_base=str(app.get("_raw_base") or resources.CLI_ANYTHING_RAW_BASE)
        )
        if not url:
            return None
        try:
            response = httpx.get(url, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
            text = response.text
        except httpx.HTTPError as exc:
            logger.warning("Could not download CLI App skill for {}: {}", app.get("name"), exc)
            return None
        if "SKILL.md" not in url and not text.lstrip().startswith("---"):
            return None
        return text if len(text) < 250_000 else None

    def _fallback_skill(self, app: dict[str, Any]) -> str:
        name = str(app.get("name") or "unknown")
        display = str(app.get("display_name") or name)
        entry = str(app.get("entry_point") or f"cli-anything-{name}")
        description = (branding._catalog_description(app) or f"Use {display} from cirno.")[:1024]
        return f"""---
name: {paths._skill_name(name)}
description: {json.dumps(description, ensure_ascii=False)}
---

# {display}

Use this skill when the user asks cirno to operate {display} through its installed CLI app.

If the user attached `@{name}` in chat, treat that as the selected app for the current turn.

## Commands

```bash
{entry} --help
{entry} --json --help
```

Prefer machine-readable output when the CLI supports `--json`.
"""

    def _with_cirno_skill_note(self, content: str, app: dict[str, Any]) -> str:
        name = str(app.get("name") or "unknown")
        skill_name = paths._skill_name(name)
        metadata = parse_skill_metadata(content)
        if metadata is None or not valid_skill_metadata(
            metadata | {"name": skill_name}, skill_name
        ):
            content = self._fallback_skill(app)
        content, replaced = re.subn(r"(?m)^name\s*:.*$", f"name: {skill_name}", content, count=1)
        if not replaced:
            content = content.replace("---\n", f"---\nname: {skill_name}\n", 1)
        marker = "<!-- cirno-cli-app-note -->"
        if marker in content:
            return content
        note = f"""{marker}
## Cirno execution

Use the `apps__run` tool with `name="{name}"` for command execution. Do not invoke this CLI through shell unless the user explicitly asks. Prefer this skill when Runtime Context mentions `@{name}` as a CLI App Attachment.
"""
        lines = content.splitlines(keepends=True)
        if lines and lines[0].strip() == "---":
            for index, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    return (
                        "".join(lines[: index + 1])
                        + "\n"
                        + note
                        + "\n"
                        + "".join(lines[index + 1 :])
                    )
        return note + "\n" + content

    def install_skill(self, app: dict[str, Any]) -> Path:
        name = str(app["name"])
        path = paths.cli_app_skill_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self._fetch_skill_content(app) or self._fallback_skill(app)
        path.write_text(self._with_cirno_skill_note(content, app), encoding="utf-8")
        return path

    def remove_skill(self, name: str) -> None:
        directory = paths.cli_app_skill_path(name).parent
        if directory.is_dir():
            shutil.rmtree(directory)

    def _record_installed(self, app: dict[str, Any]) -> dict[str, Any]:
        entry = self._installed_entry(app)
        self.installed.put(str(app["name"]), entry)
        self.install_skill(app)
        return entry

    def install(self, name: str) -> dict[str, Any]:
        app = self.registry.get_app(name)
        if not self.commands._install_supported(app):
            raise contracts.CliAppError("this CLI app uses an unsupported install strategy")
        strategy = self.commands._strategy(app)
        entry_point = str(app.get("entry_point") or "")
        if entry_point and shutil.which(entry_point):
            self._record_installed(app)
            return self.payload() | {
                "last_action": {
                    "ok": True,
                    "message": f"CLI for {app['display_name']} is already available.",
                    "installed": True,
                    "verification": [
                        "entry_point_available",
                        "state_recorded",
                        "managed_paths_present",
                    ],
                }
            }
        if strategy == "bundled":
            detect_cmd = str(app.get("detect_cmd") or app.get("entry_point") or "")
            if detect_cmd and command_support._command_exists(detect_cmd):
                self._record_installed(app)
                return self.payload() | {
                    "last_action": {
                        "ok": True,
                        "message": f"CLI for {app['display_name']} is available.",
                        "installed": True,
                        "verification": ["entry_point_available", "state_recorded"],
                    }
                }
            note = (
                app.get("install_notes") or f"{app['display_name']} is bundled with its parent app."
            )
            raise contracts.CliAppError(str(note))
        argv = self.commands._argv_for_action(app, "install")
        assert argv is not None
        result = self.commands._run_argv(argv, timeout=self.runtime.install_timeout)
        if strategy == "npm" and result.returncode != 0:
            result = self.commands._retry_stale_npm_install(app, argv, result)
        if result.returncode != 0:
            raise contracts.CliAppError(
                cli_output._truncate(result.stderr or result.stdout or "install failed"), status=500
            )
        self._record_installed(app)
        return self.payload() | {
            "last_action": {
                "ok": True,
                "message": f"Installed CLI for {app['display_name']}.",
                "installed": True,
                "verification": ["package_manager_ok", "state_recorded", "managed_paths_present"],
            }
        }

    def update(self, name: str) -> dict[str, Any]:
        app = self.registry.get_app(name, force_refresh=True)
        if str(app["name"]) not in self.installed.read():
            raise contracts.CliAppError("CLI app is not installed")
        if self.commands._strategy(app) == "bundled":
            self._record_installed(app)
            return self.payload() | {
                "last_action": {
                    "ok": True,
                    "message": f"Checked {app['display_name']}.",
                    "installed": True,
                    "verification": ["state_recorded"],
                }
            }
        argv = self.commands._argv_for_action(app, "update")
        assert argv is not None
        result = self.commands._run_argv(argv, timeout=self.runtime.install_timeout)
        if result.returncode != 0:
            raise contracts.CliAppError(
                cli_output._truncate(result.stderr or result.stdout or "update failed"), status=500
            )
        self._record_installed(app)
        return self.payload() | {
            "last_action": {
                "ok": True,
                "message": f"Updated CLI for {app['display_name']}.",
                "installed": True,
                "verification": ["package_manager_ok", "state_recorded", "managed_paths_present"],
            }
        }

    def uninstall(self, name: str) -> dict[str, Any]:
        app = self.registry.get_app(name)
        installed = self.installed.read()
        if str(app["name"]) not in installed:
            raise contracts.CliAppError("CLI app is not installed")
        raw_installed_entry = installed.get(str(app["name"]))
        installed_entry = records._as_object_dict(raw_installed_entry)
        if installed_entry is None:
            installed_entry = {}
        strategy = self.commands._strategy(app)
        entry_point = str(app.get("entry_point") or "").strip()
        managed_entry_path = str(installed_entry.get("entry_point_path") or "").strip()
        if strategy != "bundled":
            argv = self.commands._argv_for_action(app, "uninstall", installed_entry=installed_entry)
            assert argv is not None
            result = self.commands._run_argv(argv, timeout=self.runtime.install_timeout)
            if result.returncode != 0:
                raise contracts.CliAppError(
                    cli_output._truncate(result.stderr or result.stdout or "uninstall failed"),
                    status=500,
                )
            still_managed = bool(managed_entry_path and Path(managed_entry_path).exists())
            still_available = bool(entry_point and shutil.which(entry_point))
            if still_managed or (not managed_entry_path and still_available):
                reason = (
                    f"the recorded entry point at {managed_entry_path} still exists"
                    if still_managed
                    else f"{entry_point} is still available on PATH"
                )
                message = (
                    f"Uninstall for {app['display_name']} completed, but {reason}, "
                    "so cirno kept it installed."
                )
                return self.payload() | {
                    "last_action": {
                        "ok": False,
                        "message": message,
                        "removed": False,
                        "still_available": True,
                        "verification_failed": ["entry_point_absent"],
                    }
                }
        else:
            still_available = bool(entry_point and shutil.which(entry_point))
        self.installed.remove(str(app["name"]))
        self.remove_skill(str(app["name"]))
        if strategy == "bundled" and still_available:
            message = (
                f"Removed {app['display_name']} from cirno. {entry_point} "
                "is still available because it is managed outside cirno."
            )
        elif still_available:
            message = (
                f"Uninstalled CLI for {app['display_name']}, but another {entry_point} "
                "is still available on PATH."
            )
        else:
            message = f"Uninstalled CLI for {app['display_name']}."
        return self.payload() | {
            "last_action": {
                "ok": True,
                "message": message,
                "removed": True,
                "still_available": still_available,
                "verification": ["state_absent", "managed_paths_absent"]
                if still_available
                else ["entry_point_absent", "state_absent", "managed_paths_absent"],
            }
        }

    def test(self, name: str) -> dict[str, Any]:
        app = self.registry.get_app(name)
        entry = str(app.get("entry_point") or "")
        resolved = shutil.which(entry)
        if not entry or not resolved:
            raise contracts.CliAppError(f"{entry or name} is not available on PATH")
        result = self.commands._run_argv(
            [resolved, "--help"], timeout=min(self.runtime.run_timeout, 30)
        )
        ok = result.returncode == 0
        output = cli_output._truncate((result.stdout or result.stderr or "").strip(), 3000)
        return self.payload() | {
            "last_action": {
                "ok": ok,
                "message": f"{entry} --help exited {result.returncode}",
                "output": output,
            }
        }

    def _resolve_cwd(
        self,
        working_dir: str | None,
        *,
        restrict_to_workspace: bool,
    ) -> Path:
        cwd = Path(working_dir).expanduser() if working_dir else self.workspace
        cwd = cwd.resolve(strict=False)
        workspace = self.workspace.resolve(strict=False)
        if restrict_to_workspace and not is_path_within(cwd, workspace):
            raise contracts.CliAppError("working_dir is outside the configured workspace")
        return cwd

    def run(
        self,
        name: str,
        args: list[str] | None = None,
        *,
        json_output: bool = False,
        working_dir: str | None = None,
        timeout: int | None = None,
        restrict_to_workspace: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> str:
        app = self.registry.get_app(name)
        installed = self.installed.read()
        if str(app["name"]) not in installed:
            raise contracts.CliAppError(f"CLI app '{name}' is not installed")
        cwd = self._resolve_cwd(working_dir, restrict_to_workspace=restrict_to_workspace)
        entry = str(installed[str(app["name"])].get("entry_point") or app.get("entry_point") or "")
        resolved = shutil.which(entry)
        if not entry or not resolved:
            raise contracts.CliAppError(f"{entry or name} is not available on PATH")
        clean_args = [str(arg) for arg in (args or [])]
        if json_output and "--json" not in clean_args:
            clean_args = ["--json", *clean_args]
        effective_timeout = max(1, min(timeout or self.runtime.run_timeout, 600))
        artifact_snapshot = cli_output._artifact_snapshot(cwd)
        try:
            result = run_cli(
                [resolved, *clean_args], cwd=cwd, timeout=effective_timeout,
                env=self.commands._subprocess_env(), cancel_event=cancel_event,
            )
        except subprocess.TimeoutExpired:
            return f"CLI app '{name}' timed out after {effective_timeout}s"
        output = [
            f"CLI app '{name}' exited {result.returncode}.",
            f"Command: {entry} {' '.join(shlex.quote(arg) for arg in clean_args)}".rstrip(),
        ]
        if result.stdout:
            output.append("\nSTDOUT:\n" + result.stdout.rstrip())
        if result.stderr:
            output.append("\nSTDERR:\n" + result.stderr.rstrip())
        artifacts = cli_output._changed_artifacts(cwd, artifact_snapshot)
        if artifacts:
            output.append(
                "\nArtifacts created or updated:\n"
                + "\n".join(cli_output._format_artifact_lines(cwd, artifacts))
            )
            if any(
                path.suffix.lower() in cli_output._INLINE_ARTIFACT_EXTENSIONS for path in artifacts
            ):
                output.append(
                    "\nTo show a preview in WebUI, reference a raster artifact with Markdown "
                    "using its workspace-relative path, for example `![diagram](diagram.png)`."
                )
        return cli_output._truncate("\n".join(output))
