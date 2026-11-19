"""Keep distinct imported records and filesystem artifacts distinct."""

import json
import shutil
import sqlite3
from contextlib import closing

import pytest
from cirno_core.session.canonical_history import initialize_archive_index
from cirno_server.maintenance.migrations.plan import MigrationPlan, merge_identical
from cirno_server.maintenance.migrations.sessions import stage_sessions
from cirno_server.maintenance.migrations.workspaces import stage_automations


def copied_stores(released, released_store):
    instance, workspace, _ = released
    first = released_store(instance, workspace, "a" * 32)
    second = first.with_name("b" * 32)
    shutil.copytree(first, second)
    return instance, workspace, first, second


def test_embedded_nul_cannot_make_different_catalog_rows_identical(released, released_store):
    instance, workspace, first, second = copied_stores(released, released_store)
    for source, title, preview in ((first, "Study\0A", "Result"), (second, "Study", "A\0Result")):
        with closing(sqlite3.connect(source / "sessions.sqlite3")) as db, db:
            db.execute("UPDATE sessions SET title=?,preview=?", (title, preview))
    plan = MigrationPlan(instance / "state/migrations/test")
    report = stage_sessions([first, second], instance, workspace, plan)
    assert report["conversations"] == 2
    assert len(report["renamed"]) == 1
    plan.save()
    plan.apply()
    with closing(sqlite3.connect(instance / "state/sessions/instance/sessions.sqlite3")) as db:
        assert {row[0] for row in db.execute("SELECT preview FROM sessions")} == {"Result", "A\0Result"}


@pytest.mark.parametrize("archive_kind", ["different", "identical", "missing"])
def test_deduplication_includes_released_transcript_files(released, released_store, archive_kind):
    instance, workspace, first, second = copied_stores(released, released_store)
    for index, source in enumerate((first, second)):
        with closing(sqlite3.connect(source / "sessions.sqlite3")) as db, db:
            initialize_archive_index(db)
            db.execute("INSERT INTO runtime_archives VALUES (?,?,?,?,?)", (
                "websocket:research", "generation", 0, 1, "evidence/history.jsonl",
            ))
        evidence = source / "evidence/history.jsonl"
        evidence.parent.mkdir()
        if archive_kind == "missing" and index:
            continue
        text = "Second archived result" if archive_kind == "different" and index else "First archived result"
        evidence.write_text(json.dumps({"role": "assistant", "content": text}) + "\n")
    plan = MigrationPlan(instance / "state/migrations/test")
    report = stage_sessions([first, second], instance, workspace, plan)
    assert report["conversations"] == (1 if archive_kind == "identical" else 2)
    plan.save()
    plan.apply()
    final = instance / "state/sessions/instance"
    with closing(sqlite3.connect(final / "sessions.sqlite3")) as db:
        archives = [final / row[0] for row in db.execute("SELECT path FROM runtime_archives")]
    if archive_kind == "different":
        assert {json.loads(path.read_text())["content"] for path in archives} == {
            "First archived result", "Second archived result",
        }
    elif archive_kind == "identical":
        assert json.loads(archives[0].read_text())["content"] == "First archived result"
    else:
        assert sum(path.exists() for path in archives) == 1


@pytest.mark.parametrize("source_kind,target_kind", [("link", "file"), ("file", "link"), ("link", "link")])
def test_merge_rejects_different_artifact_kinds_or_link_targets(tmp_path, create_symlink, source_kind, target_kind):
    for name in ("first.txt", "second.txt"):
        (tmp_path / name).write_text("Same bytes, different identity")
    source, target = tmp_path / "source", tmp_path / "target"
    for path, kind, link in ((source, source_kind, "first.txt"), (target, target_kind, "second.txt")):
        if kind == "link":
            create_symlink(path, link)
        else:
            path.write_text("Same bytes, different identity")
    with pytest.raises(ValueError, match="Conflicting migration artifact"):
        merge_identical(source, target)
    assert source.is_symlink() == (source_kind == "link")
    assert target.is_symlink() == (target_kind == "link")


@pytest.mark.parametrize("kind", ["file", "link", "dangling_link"])
def test_merge_still_accepts_identical_files_and_exact_link_targets(tmp_path, create_symlink, kind):
    source, target = tmp_path / "source", tmp_path / "target"
    if kind == "file":
        source.write_text("Same record")
        target.write_text("Same record")
    else:
        if kind == "link":
            (tmp_path / "record.txt").write_text("Same record")
        create_symlink(source, "record.txt")
        create_symlink(target, "record.txt")
    merge_identical(source, target)
    assert source.is_symlink() == target.is_symlink() == (kind != "file")


def test_automation_link_conflict_stops_before_retiring_originals(tmp_path, create_symlink):
    instance = tmp_path / "instance"
    roots = [tmp_path / "workspace-one", tmp_path / "workspace-two"]
    for index, workspace in enumerate(roots):
        folder = workspace / "cron"
        runs = folder / "runs"
        runs.mkdir(parents=True)
        (folder / "jobs.json").write_text('{"version":1,"jobs":[]}')
        name = f"result-{index}.json"
        (runs / name).write_text('{"status":"completed"}')
        create_symlink(runs / "latest.json", name)
    plan = MigrationPlan(instance / "state/migrations/test")
    with pytest.raises(ValueError, match="Conflicting migration artifact"):
        stage_automations("cron", roots, instance, plan, {})
    assert not plan.path.exists()
    assert not (instance / "state/cron").exists()
    for index, workspace in enumerate(roots):
        assert (workspace / "cron/runs/latest.json").readlink().name == f"result-{index}.json"
