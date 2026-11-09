"""Advance a patch configuration version without replacing owner state or profiles."""

import json
from dataclasses import dataclass
from pathlib import Path

from cirno_core.config.schema import Config
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_server.maintenance.migrations.plan import MigrationPlan


@dataclass(frozen=True)
class ConfigVersionUpgrade:
    source_version: str
    target_version: str

    def prepare(self, config_path: Path, data: dict, root: Path) -> MigrationPlan:
        data.pop("last_run_version", None)
        data["lastRunVersion"] = self.target_version
        Config.model_validate(data)
        staged = root / "staged" / config_path.name
        atomic_write_text(staged, json.dumps(data, ensure_ascii=False, indent=2))
        plan = MigrationPlan(root)
        plan.install(staged, config_path)
        report = {
            "from": self.source_version, "to": self.target_version,
            "summary": "Configuration version updated. Existing conversations, profiles and settings retained.",
        }
        atomic_write_text(root / "report.json", json.dumps(report, indent=2))
        plan.save()
        return plan
