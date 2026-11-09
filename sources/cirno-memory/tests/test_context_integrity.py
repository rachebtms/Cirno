"""Role profiles, immutable evidence, scope identity and bounded recall."""

from io import StringIO
from pathlib import Path
import hashlib

import pytest

from cirno_memory.paging import PAGE_CHARS, source_page
from cirno_memory.config import MemoryConfig
from cirno_memory.repository import MemoryRepository


def test_worker_profile_is_indexed_updated_and_retired_without_changing_router_profile(tmp_path):
    worker = tmp_path / "WORKER.md"
    worker.write_text("workeridentityalpha preference")
    (tmp_path / "SOUL.md").write_text("routeridentityalpha preference")
    repo = MemoryRepository(tmp_path)
    repo.sync_profiles()
    result = repo.search("workeridentityalpha", purpose="knowledge")["memories"][0]
    assert result["source"] == "WORKER.md" and result["scope"] == "user"
    worker.write_text("workeridentitybeta preference")
    repo.sync_profiles()
    assert not repo.search("workeridentityalpha")["memories"]
    worker.unlink()
    repo.sync_profiles()
    assert not repo.search("workeridentitybeta")["memories"]
    assert repo.search("routeridentityalpha")["memories"]


@pytest.mark.parametrize("historical", [False, True])
def test_read_rejects_tampered_current_or_historical_immutable_body(tmp_path, historical):
    repo = MemoryRepository(tmp_path)
    first = repo.save("Original", source="test:source", session_key="a")
    second = repo.save("Corrected", source="test:source", session_key="a", memory_id=first["id"], expected_revision=1)
    (tmp_path / (first if historical else second)["path"]).write_text("Tampered")
    with pytest.raises(ValueError, match="saved hash"):
        repo.read(first["id"], session_key="a", revision=1 if historical else None)


def test_same_project_evidence_can_merge_across_workers_without_changing_origin(tmp_path):
    repo = MemoryRepository(tmp_path)
    evidence = [repo.save(f"Measurement {key}", source=f"test:{key}", session_key=key,
                          project_id="project", scope="project") for key in ("a", "b")]
    knowledge = repo.save("Finding", source="memory:" + evidence[0]["id"], session_key="a",
                          project_id="project", layer="knowledge", based_on=evidence[0]["id"])
    updated = repo.save("Corroborated finding", source="memory:" + evidence[1]["id"], session_key="b",
                        project_id="project", memory_id=knowledge["id"], expected_revision=1,
                        based_on=evidence[1]["id"])
    assert updated["scope"] == "project" and updated["session_key"] == "a"
    assert updated["based_on"] == evidence[1]["id"]
    with pytest.raises(PermissionError):
        repo.read(updated["id"], session_key="other", project_id="different")


def test_shared_user_records_can_link_even_when_created_in_different_projects(tmp_path):
    repo = MemoryRepository(tmp_path)
    records = [repo.save(f"Shared preference {key}", source=f"test:{key}", session_key=key,
                         project_id=key, scope="user") for key in ("a", "b")]
    assert repo.link(records[0]["id"], records[1]["id"], "related", "Same shared owner")


class BoundedReader(StringIO):
    def readline(self, size=-1):
        assert 0 < size <= PAGE_CHARS + 1
        return super().readline(size)

    def read(self, size=-1):
        assert 0 < size <= PAGE_CHARS + 1
        return super().read(size)


def test_source_pages_bound_total_output_and_reads_and_reconstruct_long_unicode_lines():
    text = "start\n" + "科研" * 30_000 + "\n" + "tail\n" * 30
    line, offset, parts = 1, 0, []
    while True:
        page = source_page(BoundedReader(text), start_line=line, char_offset=offset, limit=20)
        assert sum(len(row["text"]) for row in page["lines"]) <= PAGE_CHARS
        parts.extend(row["text"] for row in page["lines"])
        last = page["lines"][-1]
        if last["next_char_offset"] is not None:
            line, offset = last["line"], last["next_char_offset"]
        elif page["next_line"] is not None:
            line, offset = page["next_line"], 0
        else:
            break
    assert "".join(parts) == text
    assert source_page(BoundedReader(text), start_line=3, char_offset=0, limit=1)["lines"][0]["text"] == "tail\n"


def test_memory_source_pointer_obeys_the_same_page_budget(tmp_path):
    repo = MemoryRepository(tmp_path)
    evidence = repo.save("x" * 40_000, source="test:source", session_key="a")
    derived = repo.save("Finding", source="memory:" + evidence["id"], session_key="a", based_on=evidence["id"])
    page = repo.read_source(derived["id"], session_key="a", limit=1)
    assert len(page["content"]) == PAGE_CHARS
    assert page["lines"][0]["next_char_offset"] == PAGE_CHARS
    continued = repo.read_source(derived["id"], session_key="a", limit=1, char_offset=PAGE_CHARS)
    assert len(continued["content"]) == PAGE_CHARS


def test_archive_index_streams_long_lines_and_retains_tail_and_line_numbers(tmp_path, monkeypatch):
    repo = MemoryRepository(tmp_path)
    original_open = Path.open

    class SourceReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def readline(self, size=-1):
            assert 0 < size <= 1400
            return self.stream.readline(size)

    def bounded_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.parent == repo.root / "sources" and path.suffix == ".jsonl":
            return SourceReader(stream)
        return stream

    monkeypatch.setattr(Path, "open", bounded_open)
    record = repo.archive_messages([
        {"role": "tool", "content": "prefix " * 15_000 + "uniquelongtail"},
        {"role": "user", "content": "nextlinemarker"},
    ], "a")
    for query, line in (("uniquelongtail", 1), ("nextlinemarker", 2)):
        result = repo.search(query, session_key="a")["memories"][0]
        assert result["id"] == record["id"] and result["start_line"] == result["end_line"] == line
        assert query in result["snippet"]


@pytest.mark.parametrize("current_project", [None, "new-project"])
def test_originating_session_cannot_access_project_memory_after_leaving_project(tmp_path, current_project):
    repo = MemoryRepository(tmp_path)
    hidden = repo.save("scopemarker project fact", source="test", session_key="a", project_id="old-project",
                       scope="project", layer="knowledge", tags=["privateproject"])
    own = repo.save("scopemarker private note", source="test", session_key="a", layer="knowledge")
    access = {"session_key": "a", "project_id": current_project}
    for operation in (repo.read, repo.history, repo.read_source):
        with pytest.raises(PermissionError):
            operation(hidden["id"], **access)
    with pytest.raises(PermissionError):
        repo.save("Changed", source="test", memory_id=hidden["id"], expected_revision=1, **access)
    for query in ("scopemarker", ""):
        assert [row["id"] for row in repo.search(query, **access)["memories"]] == [own["id"]]
    assert not repo.search(hidden["id"], **access)["memories"]
    assert not repo.list_tags(**access)["tags"]
    assert repo.status(maintenance=False, **access)["counts"] == {"knowledge": 1}
    assert repo.read(hidden["id"], session_key="b", project_id="old-project")["scope"] == "project"


@pytest.fixture
def semantic_search(monkeypatch):
    import cirno_memory.embedding as embedding

    class Worker:
        peak_mb = 0

        def __init__(self, config):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, texts, **options):
            result = {"vectors": [[1., 0.]]}
            if options.get("chunked"):
                result.update(chunks=[{"chunk_index": 0, "start_char": 0, "end_char": len(texts[0])}], has_more=False)
            return result

    monkeypatch.setattr(embedding, "EmbeddingWorker", Worker)
    monkeypatch.setattr(embedding, "_fingerprint", lambda config: "test")

    def search(repo, **access):
        return embedding.search(repo, "marker", MemoryConfig(embedding_enabled=True), mode="semantic", **access)

    return search


def test_semantic_index_and_cached_vectors_obey_current_project_access(tmp_path, semantic_search):
    repo = MemoryRepository(tmp_path)
    record = repo.save("marker private project knowledge", source="test", session_key="a", project_id="old",
                       scope="project", layer="knowledge")
    assert semantic_search(repo, session_key="a", project_id="old")["memories"][0]["id"] == record["id"]
    assert not semantic_search(repo, session_key="a", project_id="new")["memories"]
    with repo.connect(vectors=True) as db:
        db.execute("DELETE FROM vector_records")
        db.execute("DELETE FROM vector_chunks")
    assert not semantic_search(repo, session_key="a", project_id="new")["memories"]
    with repo.connect(vectors=True) as db:
        assert db.execute("SELECT count(*) FROM vector_records").fetchone()[0] == 0


@pytest.mark.parametrize("already_indexed", [False, True])
def test_semantic_search_reports_corrupt_bodies_before_indexing_or_returning_a_snippet(tmp_path, semantic_search, already_indexed):
    repo = MemoryRepository(tmp_path)
    record = repo.save("marker verified knowledge", source="test", session_key="a", layer="knowledge")
    if already_indexed:
        assert semantic_search(repo, session_key="a")["engine"] == "semantic"
    (tmp_path / record["path"]).write_text("marker altered text")
    result = semantic_search(repo, session_key="a")
    assert result["engine"] == "bm25" and "saved hash" in result["warning"]
    assert all("altered text" not in row["snippet"] for row in result["memories"])


def test_checkpoints_follow_project_slots_and_reuse_visible_legacy_state(tmp_path):
    repo = MemoryRepository(tmp_path)
    legacy_id = "task-" + hashlib.sha256(b"a").hexdigest()[:32]
    repo.save("Legacy milestone", source="test", session_key="a", scope="project", project_id="old",
              layer="task", memory_id=legacy_id, enqueue=False)
    assert "Legacy milestone" in repo.task_context("a", project_id="old")
    old = repo.checkpoint("a", "Old project milestone", "test", project_id="old", expected_revision=1)
    assert old["id"] == legacy_id and old["revision"] == 2
    assert not repo.task_context("a", project_id="new")
    assert not repo.task_context("a")
    new = repo.record_compaction("a", "New project summary", "test", project_id="new")
    assert new["id"] != legacy_id and new["scope"] == "project" and new["project_id"] == "new"
    explicit = repo.checkpoint("a", "New project milestone", "test", project_id="new", expected_revision=1)
    assert repo.record_compaction("a", "Lossy summary", "test", project_id="new") is None
    assert "New project milestone" in repo.task_context("a", project_id="new")
    assert "Old project milestone" in repo.task_context("a", project_id="old")
    private = repo.checkpoint("a", "Unfiled task milestone", "test")
    assert len({legacy_id, explicit["id"], private["id"]}) == 3
    assert "Unfiled task milestone" in repo.task_context("a")
    assert "New project milestone" not in repo.task_context("a")


def test_corrupt_dream_input_does_not_claim_or_consume_any_of_the_batch(tmp_path):
    repo = MemoryRepository(tmp_path)
    repo.save("Valid first input", source="test", session_key="a")
    corrupted = repo.save("Second input", source="test", session_key="a")
    (tmp_path / corrupted["path"]).write_text("Altered second input")
    with pytest.raises(ValueError, match="saved hash"):
        repo.pending()
    with repo.connect() as db:
        rows = db.execute("SELECT lease,attempts FROM dream_queue").fetchall()
        assert len(rows) == 2 and all(row["lease"] is None and row["attempts"] == 0 for row in rows)
