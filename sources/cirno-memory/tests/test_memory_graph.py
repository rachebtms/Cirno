"""Graph snapshots preserve visibility and remain bounded without inference."""
import pytest
from cirno_memory.config import MemoryConfig
from cirno_memory.graph import memory_graph
from cirno_memory.repository import MemoryRepository


def test_graph_uses_real_relations_and_checks_both_endpoints(tmp_path):
    repo = MemoryRepository(tmp_path)
    shared = repo.save("Shared", source="test", session_key="a", scope="user")
    private = repo.save("Private", source="test", session_key="a", scope="session")
    # A legacy/corrupt cross-scope edge must not disclose its hidden endpoint.
    with repo.connect() as db:
        db.execute("INSERT INTO links VALUES (?,?,?,?)", (shared["id"], private["id"], "related", "Test evidence"))
    ids = [shared["id"], private["id"]]
    assert memory_graph(repo, ids, session_key="b")["links"] == []
    assert memory_graph(repo, [private["id"]], maintenance=True)["links"] == []
    result = memory_graph(repo, ids, session_key="a")
    assert result == {"links": [{"source": shared["id"], "target": private["id"], "relation": "related"}], "links_truncated": False}
    assert memory_graph(repo, ids, maintenance=True) == result


def test_graph_caps_rows_and_rejects_oversized_requests(tmp_path, monkeypatch):
    import cirno_memory.graph as graph
    repo = MemoryRepository(tmp_path)
    rows = [repo.save(str(i), source="test", session_key="a") for i in range(3)]
    for row in rows[1:]:
        repo.link(rows[0]["id"], row["id"], "supports", "Measured evidence", maintenance=True)
    monkeypatch.setattr(graph, "MAX_GRAPH_LINKS", 1)
    result = memory_graph(repo, [row["id"] for row in rows], maintenance=True)
    assert len(result["links"]) == 1
    assert result["links_truncated"]
    with pytest.raises(ValueError, match="at most 300"):
        memory_graph(repo, ["x"] * 301)
    with pytest.raises(ValueError, match="nonempty strings"):
        memory_graph(repo, [{}])
    assert memory_graph(repo, []) == {"links": [], "links_truncated": False}


@pytest.mark.parametrize("budget", [201, 512, 1024, 8192])
def test_embedding_budget_can_exceed_200_mib(budget):
    assert MemoryConfig(embedding_max_rss_mb=budget).embedding_max_rss_mb == budget
