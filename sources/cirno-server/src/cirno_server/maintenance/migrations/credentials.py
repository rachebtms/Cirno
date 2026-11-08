"""Copy released SDK credential files into the instance without changing shared originals."""

import shutil
from pathlib import Path

from cirno_server.maintenance.migrations.plan import MigrationPlan
from oauth_cli_kit.providers import OPENAI_CODEX_PROVIDER
from oauth_cli_kit.storage import FileTokenStorage


def stage_credentials(instance: Path, plan: MigrationPlan) -> list[str]:
    copied = []
    for provider, filename, app in (
        ("openai_codex", OPENAI_CODEX_PROVIDER.token_filename, "oauth-cli-kit"),
        ("github_copilot", "github-copilot.json", "cirno"),
    ):
        source = FileTokenStorage(token_filename=filename, app_name=app, import_codex_cli=False).get_token_path()
        target = instance / "state/providers" / provider / filename
        if target.exists() or not source.exists():
            continue
        staged = plan.root / "staged/providers" / provider / filename
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.resolve(), staged)
        staged.chmod(0o600)
        plan.install(staged, target)
        copied.append(provider)
    return copied
