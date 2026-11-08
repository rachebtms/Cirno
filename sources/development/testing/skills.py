"""Create complete Skill documents for catalog and prompt integration tests."""

import json
from pathlib import Path


def write_skill(
    base: Path,
    name: str,
    *,
    metadata_json: dict | None = None,
    body: str = "# Skill\n",
) -> Path:
    """Create ``base / name / SKILL.md`` with optional cirno metadata JSON."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True)
    lines = ["---", f"name: {name}", f"description: {name} skill"]
    if metadata_json is not None:
        payload = json.dumps({"cirno": metadata_json}, separators=(",", ":"))
        lines.append(f'metadata: {payload}')
    lines.extend(["---", "", body])
    path = skill_dir / "SKILL.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
