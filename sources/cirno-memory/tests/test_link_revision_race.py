import pytest
from cirno_memory.repository import MemoryRepository


@pytest.mark.parametrize("relation", ["derived_from", "supports", "supersedes"])
def test_link_rechecks_evidence_revision_at_transaction_commit(tmp_path, monkeypatch, relation):
    repo = MemoryRepository(tmp_path)
    source = repo.save("Claim", source="test", session_key="a")
    target = repo.save("Original evidence", source="test", session_key="a")
    read = repo.read

    def concurrent_update(identity, **access):
        record = read(identity, **access)
        if identity == target["id"]:
            repo.save(
                "Corrected evidence",
                source="test",
                session_key="a",
                memory_id=identity,
                expected_revision=1,
            )
        return record

    monkeypatch.setattr(repo, "read", concurrent_update)
    with pytest.raises(ValueError, match="changed"):
        repo.link(
            source["id"],
            target["id"],
            relation,
            "Exact reference",
            session_key="a",
            expected_target_revision=1,
        )
    assert read(source["id"], session_key="a")["links"] == []
    assert read(target["id"], session_key="a")["status"] == "active"
