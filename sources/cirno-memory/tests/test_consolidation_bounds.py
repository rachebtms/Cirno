"""Consolidation skips oversized inputs without losing their pending revisions."""

import pytest

from cirno_memory.repository import MemoryRepository


def test_consolidation_budget_skips_large_input_but_keeps_complete_later_input(tmp_path):
    repo = MemoryRepository(tmp_path)
    large = repo.save("科研" * 40, source="test:large", session_key="worker:a")
    small = repo.save("Exact small body", source="test:small", session_key="worker:a")
    selected = repo.consolidation_inputs("worker:a", max_chars=20)
    assert [(row["id"], row["content"]) for row in selected] == [(small["id"], "Exact small body")]
    assert repo.read(large["id"], session_key="worker:a")["content"] == "科研" * 40
    assert {row["id"] for row in repo.consolidation_inputs("worker:a", max_chars=100)} == {
        large["id"], small["id"],
    }


@pytest.mark.parametrize("limit", [8, 9])
def test_bounded_complete_body_keeps_hash_validation(tmp_path, limit):
    repo = MemoryRepository(tmp_path)
    record = repo.save("Original", source="test:body", session_key="worker:a")
    assert repo.body_content_within(record, limit) == "Original"
    (tmp_path / record["path"]).write_text("Tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="saved hash"):
        repo.body_content_within(record, limit)
