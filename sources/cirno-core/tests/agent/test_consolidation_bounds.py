"""Optional learning references must be bounded before reading whole bodies."""

import json
from io import StringIO
from pathlib import Path

import pytest

from cirno_core.memory.consolidation_learning import ConsolidationLearning
from cirno_core.session.keys import ROUTER_SESSION_KEY


@pytest.mark.parametrize("kind", ["profile", "skill", "pending", "knowledge"])
def test_oversized_learning_references_are_not_read_in_full(tmp_path, monkeypatch, kind):
    item = ConsolidationLearning(
        tmp_path, [{"role": "user", "content": "Review calibration"}],
        session_key=ROUTER_SESSION_KEY, project_id=None, context_chars=512, max_updates=8,
    )
    content = "科研" * 512
    if kind in {"profile", "skill"}:
        relative = "USER.md" if kind == "profile" else "skills/calibration/SKILL.md"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        record = None
    else:
        record = item.repo.save(
            content, source="test:large", session_key=ROUTER_SESSION_KEY,
            layer="knowledge" if kind == "knowledge" else "event",
            enqueue=kind == "pending",
        )
        path = tmp_path / record["path"]

    reads = []

    class GuardedReader(StringIO):
        def read(self, size=-1):
            assert 0 < size <= 513, "reference read exceeded the context budget"
            reads.append(size)
            return super().read(size)

    original = Path.open

    def open_path(self, *args, **kwargs):
        if self == path:
            return GuardedReader(content)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)
    context = item.context()
    assert reads
    assert len(context) <= item.context_chars
    if record is None:
        assert relative not in item.documents
    else:
        assert record["id"] not in item.inputs
        assert record["id"] not in item.known


def test_learning_reference_separators_share_the_context_budget(tmp_path):
    budget = sum(
        len(json.dumps({"path": name, "content": ""}, ensure_ascii=False))
        for name in ("SOUL.md", "WORKER.md")
    )
    item = ConsolidationLearning(
        tmp_path, [], session_key=ROUTER_SESSION_KEY,
        project_id=None, context_chars=budget, max_updates=8,
    )
    assert len(item.context()) <= budget
