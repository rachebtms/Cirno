"""Source version bumps must retain a complete offline upgrade path."""

import tomllib
from pathlib import Path

from cirno_server.maintenance.migrations.registry import MIGRATIONS


def test_upgrade_registry_reaches_current_source_version():
    root = Path(__file__).resolve().parents[4]
    target = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    version, seen = "0.1.6", set()
    while version != target:
        assert version not in seen, f"Upgrade cycle at {version}"
        seen.add(version)
        assert version in MIGRATIONS, f"Missing upgrade from {version} to source version {target}"
        version = MIGRATIONS[version].target_version
