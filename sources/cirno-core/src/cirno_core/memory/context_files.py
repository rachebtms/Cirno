"""Bounded owner-selected memory documents for fresh-input snapshots."""

from pathlib import Path

from cirno_core.utils.text import truncate_text_to_tokens


def memory_files_context(home: Path, names: list[str], tokens: int) -> str:
    if not names:
        return ""
    root = (home / "memory").resolve()
    per_file = max(1, tokens // len(names))
    sections = []
    for name in names:
        path = (home / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Fixed memory file escapes Agent Home memory/: {name}")
        # A missing/unreadable selected file is an explicit configuration error,
        # rather than silently removing its instructions from future requests.
        with path.open(encoding="utf-8") as stream:
            text = stream.read(per_file * 8)
        sections.append(f"### {name}\n{truncate_text_to_tokens(text, per_file)}")
    return "\n## Fixed memory files snapshot\n" + truncate_text_to_tokens("\n\n".join(sections), tokens) + "\n[/Fixed memory files snapshot]"
