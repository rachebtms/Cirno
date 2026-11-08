"""Keep catalog preferences while retiring the old chat-only layout metadata."""

import json
from pathlib import Path

from cirno_server.maintenance.migrations.cirno_identity import remap
from cirno_server.maintenance.migrations.plan import MigrationPlan
from cirno_server.webui.sidebar_state import normalize_webui_sidebar_state


def stage_conversation_preferences(instance: Path, plan: MigrationPlan) -> int:
    path = instance / "state/webui/sidebar-state.json"
    if not path.exists():
        return 0
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Conversation preferences must be a JSON object")
    staged = plan.root / "staged/conversation-preferences.json"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(json.dumps(normalize_webui_sidebar_state(remap(raw)), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan.install(staged, path)
    layout = raw.get("workbench")
    tabs = layout.get("tabs") if isinstance(layout, dict) else None
    return len(tabs) if isinstance(tabs, dict) else 0
