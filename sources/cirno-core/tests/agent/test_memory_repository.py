"""Memory precision, scope isolation, revision safety and bounded maintenance."""
import json

import pytest

from cirno.memory.repository import MemoryRepository


@pytest.fixture
def repo(tmp_path):
    return MemoryRepository(tmp_path)


def save(repo, content="核对实验结果 seed=42 alpha=0.001，误差 0.015 m/s", **kwargs):
    return repo.save(content, source="node://test/result.json#L12", session_key="websocket:a", **kwargs)


def settle(repo, token):
    with repo.connect() as db:
        inputs = db.execute("SELECT memory_id,claimed_revision FROM dream_queue WHERE lease=?", (token,)).fetchall()
    for row in inputs:
        record = repo.read(row['memory_id'], maintenance=True)
        if record['revision'] == row['claimed_revision']:
            repo.confirm(token, row['memory_id'], row['claimed_revision'], 'skipped', reason='No durable finding in this test batch', maintenance=True)
    return repo.finish(token)


def test_bilingual_bm25_exact_values_and_short_chinese(repo):
    row = save(repo, title="实验误差", tags=["velocity"])
    for query in ["误差", "seed", "alpha", "42", "velocity", row["id"], '" OR *']:
        result = repo.search(query, session_key="websocket:a")
        if query != '" OR *':
            assert result["memories"][0]["id"] == row["id"]
    assert repo.read(row["id"], session_key="websocket:a")["content"].endswith("0.015 m/s")


def test_scope_isolation_applies_to_read_history_and_search(repo):
    private = save(repo)
    project = save(repo, scope="project", project_id="p1")
    shared = save(repo, scope="user")
    assert {r["id"] for r in repo.search("seed", session_key="websocket:b", project_id="p1")["memories"]} == {project["id"], shared["id"]}
    for operation in (repo.read, repo.history):
        with pytest.raises(PermissionError):
            operation(private["id"], session_key="websocket:b")
    with pytest.raises(ValueError):
        repo.link(shared["id"], private["id"], "related", "different scopes", session_key="websocket:a")


def test_revisions_are_immutable_and_concurrent_updates_rejected(repo):
    old = save(repo)
    new = save(repo, "纠正 seed=43", memory_id=old["id"], expected_revision=1)
    with pytest.raises(ValueError, match="changed"):
        save(repo, "stale edit", memory_id=old["id"], expected_revision=1)
    assert repo.read(old["id"], session_key="websocket:a", revision=1)["content"].startswith("核对")
    assert repo.read(new["id"], session_key="websocket:a")["content"] == "纠正 seed=43"
    assert len(repo.history(new["id"], session_key="websocket:a")) == 2


def test_correction_retains_old_evidence_but_default_search_returns_current(repo):
    old = save(repo, "温度 30 C")
    new = save(repo, "校准后温度 25 C")
    repo.link(new["id"], old["id"], "supersedes", "sensor calibration result", session_key="websocket:a")
    assert [r["id"] for r in repo.search("温度", session_key="websocket:a")["memories"]] == [new["id"]]
    assert len(repo.search("温度", session_key="websocket:a", include_history=True)["memories"]) == 2
    assert "30" in repo.read(old["id"], session_key="websocket:a")["content"]


def test_dream_queue_restarts_and_keeps_edits_made_during_dream(repo):
    row = save(repo)
    token, records = repo.pending()
    assert records[0]["revision"] == 1
    assert MemoryRepository(repo.home).pending() is None
    save(repo, "new evidence", memory_id=row["id"], expected_revision=1)
    settle(repo, token)
    assert repo.status()["pending"] == 1
    token, records = repo.pending()
    assert records[0]["revision"] == 2
    settle(repo, token)
    assert repo.status()["pending"] == 0


def test_failed_dream_is_durable_and_has_backoff(repo):
    save(repo)
    token, _ = repo.pending()
    repo.finish(token, error="provider unavailable")
    assert repo.status()["failed"] == 1
    assert repo.pending() is None
    assert "provider unavailable" in repo.status()["last_dream"]["error"]


def test_derived_memory_cannot_promote_project_fact_to_user_scope(repo):
    source = save(repo, project_id="p1", scope="project")
    derived = save(repo, "Reusable principle", scope="user", based_on=source["id"], project_id="p1", layer="knowledge")
    assert derived["scope"] == "project"
    assert not repo.search("principle", session_key="websocket:b", project_id="p2")["memories"]


def test_evidence_survives_summary_and_repeated_archival(repo):
    messages = [{"role": "user", "content": "Exact seed 23987, threshold 0.00003125"}, {"role": "tool", "content": "score=0.98912345"}]
    first = repo.archive_messages(messages, "websocket:a", "p1")
    second = repo.archive_messages(messages, "websocket:a", "p1")
    assert first["id"] == second["id"]
    restored = repo.read_source(first["id"], session_key="websocket:b", project_id="p1")
    assert json.loads(restored["lines"][1]["text"])["content"] == "score=0.98912345"
    with pytest.raises(PermissionError):
        repo.read_source(first["id"], session_key="websocket:b", project_id="p2")


def test_arbitrary_source_does_not_bypass_file_tool_scope(repo):
    secret = repo.home / "config.json"
    secret.write_text("private token")
    row = repo.save("pointer", source=str(secret), session_key="websocket:a")
    assert "private token" not in json.dumps(repo.read_source(row["id"], session_key="websocket:a"))


def test_task_checkpoint_restores_without_dream_or_model_search(repo):
    row = repo.checkpoint("websocket:a", "Done: A. Next: B. Artifact node://x/123", "tool-result:123")
    restored = MemoryRepository(repo.home)
    assert "Next: B" in restored.task_context("websocket:a")
    assert not restored.task_context("websocket:b")
    assert restored.status()["pending"] == 0
    assert row["layer"] == "task"


def test_manual_edits_deletion_and_rebuild(repo):
    row = save(repo)
    mirror = repo.root / "entries" / (row["id"] + ".md")
    mirror.write_text("Updated keyword entropy")
    assert repo.reconcile()["indexed"] == 1
    assert repo.search("entropy", session_key="websocket:a")["memories"]
    assert repo.reconcile(rebuild=True)["indexed"] == 1
    mirror.unlink()
    assert repo.reconcile()["missing"] == [row["id"]]
    assert not repo.search("entropy", session_key="websocket:a")["memories"]
    assert repo.read(row["id"], session_key="websocket:a")["content"] == "Updated keyword entropy"


def test_profiles_and_legacy_entries_share_search_without_overwriting_sources(repo):
    from cirno.storage.instance import InstanceData
    old = repo.root / "legacy.md"
    old.write_text("legacy source wording")
    InstanceData(repo.home).save("memories", {"id": "old", "source": "url:original", "scope": "user", "kind": "fact", "path": str(old)})
    (repo.home / "USER.md").write_text("Prefer concise answers")
    repo.migrate_legacy()
    repo.sync_profiles()
    repo.migrate_legacy()
    assert repo.search("legacy")["memories"][0]["id"] == "old"
    assert repo.search("concise", layer="profile")["memories"]
    assert old.read_text() == "legacy source wording"


def test_chunked_search_paginates_distinct_records_without_skips(repo):
    ids = {save(repo, ("entropy measurement\n" * 150) + str(index))["id"] for index in range(9)}
    found, offset = [], 0
    while True:
        page = repo.search("entropy", session_key="websocket:a", limit=2, offset=offset)
        found += [record["id"] for record in page["memories"]]
        if not page["has_more"]:
            break
        offset = page["next_offset"]
    assert len(found) == len(set(found)) == len(ids)
    assert set(found) == ids


def test_explicit_task_state_survives_repeated_compaction(repo):
    explicit = repo.checkpoint("websocket:a", "Next: compare exact result 0.98912345; artifact node://n/results.tsv", "tool:result")
    for index in range(3):
        repo.record_compaction("websocket:a", f"lossy summary {index}", "source:example")
    assert repo.read(explicit["id"], session_key="websocket:a")["revision"] == 1
    assert "0.98912345" in MemoryRepository(repo.home).task_context("websocket:a")


def test_preemption_releases_batch_without_consuming_retry_budget(repo):
    save(repo)
    for _ in range(5):
        token, _ = repo.pending()
        repo.finish(token, preempted=True)
    token, _ = MemoryRepository(repo.home).pending()
    repo.finish(token, error="timeout")
    assert repo.status()["failed"] == 1
    assert repo.retry_failed() == {"retried": 1}
    assert repo.pending() is not None


def test_long_source_lines_are_losslessly_paged(repo):
    text = "start " + "1234567890" * 5000 + " threshold=0.00003125"
    source = repo.archive_messages([{"role": "user", "content": text}], "websocket:a")
    assembled, offset = "", 0
    while True:
        page = repo.read_source(source["id"], session_key="websocket:a", char_offset=offset)
        row = page["lines"][0]
        assembled += row["text"]
        offset = row["next_char_offset"]
        if offset is None:
            break
    assert json.loads(assembled)["content"] == text


def test_derived_update_cannot_change_visibility_of_existing_memory(repo):
    shared = save(repo, scope="user")
    private = save(repo, scope="project", project_id="p1")
    with pytest.raises(ValueError, match="scope"):
        save(repo, memory_id=shared["id"], expected_revision=1, based_on=private["id"], project_id="p1")
    assert repo.read(shared["id"], maintenance=True)["scope"] == "user"


def test_full_rebuild_continues_in_bounded_pages(repo):
    for index in range(13):
        save(repo, f"word {index}")
    assert repo.reconcile(rebuild=True, limit=5)["has_more"]
    assert repo.reconcile(rebuild=True, limit=5)["has_more"]
    last = repo.reconcile(rebuild=True, limit=5)
    assert last["scanned"] == 3 and not last["has_more"]


def test_original_evidence_search_includes_text_beyond_directory_preview(repo):
    row = repo.archive_messages([{"role": "user", "content": "ordinary " * 700 + "preciseseed23987=0.00003125"}], "websocket:a")
    assert "preciseseed23987" not in repo.read(row["id"], session_key="websocket:a")["content"]
    assert repo.search("preciseseed23987", session_key="websocket:a")["memories"][0]["id"] == row["id"]
    repo.reconcile(rebuild=True)
    assert repo.search("preciseseed23987", session_key="websocket:a")["memories"]


def test_deleting_and_restoring_a_profile_updates_search(repo):
    path = repo.home / "USER.md"
    path.write_text("preference entropy")
    repo.sync_profiles()
    path.unlink()
    repo.sync_profiles()
    assert not repo.search("entropy")["memories"]
    path.write_text("preference entropy")
    repo.sync_profiles()
    assert repo.search("entropy")["memories"]


def test_update_preserves_layer_kind_tags_and_evidence_when_unspecified(repo):
    row = repo.save("precise fact", source="node://x", session_key="a", layer="knowledge", kind="fact", tags=["test"], source_refs=[{"memory_id": "evidence"}])
    new = repo.save("corrected fact", source="node://y", session_key="a", memory_id=row["id"], expected_revision=1)
    assert new["layer"] == "knowledge" and new["kind"] == "fact"
    assert new["tags"] == ["test"] and new["source_refs"] == [{"memory_id": "evidence"}]


def test_external_claim_source_can_find_its_captured_conversation(repo):
    row = save(repo)
    archived = repo.archive_messages([{"role": "tool", "name": "memory", "content": json.dumps(row)}], "websocket:a")
    source = repo.read_source(row["id"], session_key="websocket:a")
    assert any(ref.get("memory_id") == archived["id"] for ref in source["source_refs"])
    assert "not external verification" in source["note"]
    with pytest.raises(PermissionError):
        repo.read_source(row["id"], session_key="websocket:other")


def test_index_rebuild_recovers_profiles_after_fts_loss(repo):
    (repo.home / "USER.md").write_text("preference quantum")
    repo.sync_profiles()
    with repo.connect() as db:
        db.execute("DELETE FROM memory_fts")
    assert not repo.search("quantum")["memories"]
    repo.reconcile(rebuild=True)
    assert repo.search("quantum")["memories"]


def test_dream_batch_contains_only_one_visibility_scope(repo):
    a = save(repo, "p1 evidence", scope="project", project_id="p1")
    b = save(repo, "p2 evidence", scope="project", project_id="p2")
    token, rows = repo.pending()
    assert [row["id"] for row in rows] == [a["id"]]
    settle(repo, token)
    _, rows = repo.pending()
    assert [row["id"] for row in rows] == [b["id"]]


def test_derived_knowledge_keeps_original_evidence_revision(repo):
    original = save(repo, "observation threshold=0.001")
    derived = repo.save("distilled threshold=0.001", source="memory:" + original["id"], session_key="websocket:a", based_on=original["id"], layer="knowledge")
    save(repo, "corrected threshold=0.002", memory_id=original["id"], expected_revision=1)
    source = repo.read_source(derived["id"], session_key="websocket:a")
    assert "0.001" in source["content"] and "0.002" not in source["content"]
    assert source["source_refs"][0]["revision"] == 1
    assert repo.read(original["id"], session_key="websocket:a")["content"].endswith("0.002")


def test_large_profile_is_indexed_in_bounded_parts_and_shortening_removes_stale_tail(repo):
    path = repo.home / "USER.md"
    path.write_text("prefix " + "x" * 70000 + " uniquetailkeyword")
    repo.sync_profiles()
    assert repo.search("uniquetailkeyword")["memories"]
    path.write_text("short profile")
    repo.sync_profiles()
    assert not repo.search("uniquetailkeyword")["memories"]
    assert repo.search("short")["memories"]


def test_new_revision_gets_a_fresh_dream_retry_budget(repo):
    row = save(repo)
    with repo.connect() as db:
        db.execute("UPDATE dream_queue SET attempts=3,error='old failure' WHERE memory_id=?", (row['id'],))
    save(repo, "new evidence", memory_id=row['id'], expected_revision=1)
    token, batch = repo.pending()
    assert batch[0]['revision'] == 2
    assert repo.renew(token) == 1
    assert repo.pending() is None
    settle(repo, token)
    assert repo.status()['pending'] == 0


def test_superseded_records_are_not_stuck_in_pending_dream_count(repo):
    old = save(repo, 'old result')
    new = save(repo, 'new result')
    repo.link(new['id'], old['id'], 'supersedes', 'new evidence', session_key='websocket:a')
    assert repo.status()['pending'] == 1


def test_non_enqueuing_update_keeps_existing_batch_acknowledgeable(repo):
    row = save(repo)
    token, _ = repo.pending()
    save(repo, 'corrected evidence', memory_id=row['id'], expected_revision=1, enqueue=False)
    settle(repo, token)
    next_token, batch = repo.pending()
    assert batch[0]['revision'] == 2
    settle(repo, next_token)
    assert repo.status()['pending'] == 0


def test_non_dream_layer_removes_obsolete_queue_entry(repo):
    row = save(repo)
    save(repo, 'explicit checkpoint', memory_id=row['id'], expected_revision=1, layer='task', enqueue=False)
    assert repo.pending() is None
    assert repo.status()['pending'] == 0


def test_legacy_history_keeps_its_original_recorded_time_and_readable_event(repo):
    repo.ingest_history(7, 'Old precise event 0.00003125', 'websocket:a', timestamp='2024-01-02 03:04')
    row = repo.read('history-7', session_key='websocket:a')
    assert row['created_at'] == '2024-01-02 03:04' and row['observed_at'] == '2024-01-02 03:04'
    event = repo.read_source('history-7', session_key='websocket:a')
    assert event['source'].startswith('memory/revisions/')
    assert '0.00003125' in event['content']
