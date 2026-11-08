"""The supported v0.1.6 storage/configuration import, staged before replacement."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from cirno_core.config.schema import Config
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_server.maintenance.migrations.channel_pairing import stage_pairing_retirement
from cirno_server.maintenance.migrations.configuration import import_configuration
from cirno_server.maintenance.migrations.conversation_preferences import (
    stage_conversation_preferences,
)
from cirno_server.maintenance.migrations.credentials import stage_credentials
from cirno_server.maintenance.migrations.journal import stage_initial_dream_cursor
from cirno_server.maintenance.migrations.plan import MigrationPlan
from cirno_server.maintenance.migrations.sessions import stage_sessions, stores_at
from cirno_server.maintenance.migrations.workspaces import (
    retire_workspace_markers,
    stage_automations,
    workspaces,
)


class Import016:
    source_version = "0.1.6"
    target_version = "0.2.0"

    def prepare(self, config_path: Path, data: dict, root: Path) -> MigrationPlan:
        if (root / "staged").exists():
            shutil.rmtree(root / "staged")
        instance = config_path.parent
        sources = stores_at(instance / "state" / "sessions")
        roots = workspaces(instance, data, sources)
        plan = MigrationPlan(root)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        default = data.get("agents", {}).get("defaults", {}).get("workspace")
        workspace = Path(default).expanduser().resolve() if default else instance / "workspace"
        report = stage_sessions(sources, instance, workspace, plan)
        for kind in ("cron", "triggers"):
            stage_automations(kind, roots, instance, plan, report.get("bindings", {}))
        report["retired_chat_groups"] = stage_conversation_preferences(instance, plan)
        report["oauth_credentials_copied"] = stage_credentials(instance, plan)
        report["initialized_dream_cursor"] = stage_initial_dream_cursor(instance, plan)
        report["retired_pairing_notices"] = stage_pairing_retirement(instance, plan)
        retire_workspace_markers(roots, plan)
        for name in (".instance-store", ".workspace-initialization.lock"):
            plan.retire(instance / "state" / "sessions" / name)
        import_configuration(data, self.target_version, config_path)
        Config.model_validate(data)
        staged_config = root / "staged" / config_path.name
        atomic_write_text(staged_config, json.dumps(data, ensure_ascii=False, indent=2))
        plan.install(staged_config, config_path)
        report.update({"from": self.source_version, "to": self.target_version,
                       "workspaces": [str(path) for path in roots]})
        atomic_write_text(root / "report.json", json.dumps(report, indent=2))
        plan.save()
        return plan
