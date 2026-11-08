"""Browser and native tools must share comparison and rollback ownership."""

import asyncio
from threading import Event

import pytest

from cirno_core.agent.tools.apply_patch import ApplyPatchTool
from cirno_core.agent.tools.filesystem import EditFileTool, WriteFileTool
from cirno_core.agent.tools.filesystem.edit_io import PreparedEdit
from cirno_core.agent.tools.filesystem.patch_plan import PatchPlan
from cirno_core.security.workspace_access import build_workspace_scope
from cirno_server.webui import workspace_files
from cirno_server.webui.file_preview import WebUIFilePreviewError


async def wait(event: Event) -> None:
    assert await asyncio.wait_for(asyncio.to_thread(event.wait, 4), 5)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_type", ["edit", "patch"])
async def test_browser_and_agent_cannot_both_accept_the_same_original(
    tmp_path, monkeypatch, tool_type
):
    path = tmp_path / "shared.md"
    path.write_text("original")
    scope = build_workspace_scope(tmp_path, "restricted")
    revision = workspace_files.read_workspace_file(str(path), scope=scope)["revision"]
    writing, release, committing = Event(), Event(), Event()
    write = workspace_files.atomic_write_text

    def delayed_browser_write(target, content):
        writing.set()
        assert release.wait(5)
        write(target, content)

    plan_type = PreparedEdit if tool_type == "edit" else PatchPlan
    commit = plan_type.commit

    def observed_commit(plan, cancelled=None):
        committing.set()
        return commit(plan, cancelled)

    monkeypatch.setattr(workspace_files, "atomic_write_text", delayed_browser_write)
    monkeypatch.setattr(plan_type, "commit", observed_commit)
    browser = asyncio.create_task(
        asyncio.to_thread(
            workspace_files.save_workspace_file,
            str(path),
            "browser change",
            revision,
            scope=scope,
        )
    )
    agent = None
    try:
        await wait(writing)
        if tool_type == "edit":
            operation = EditFileTool(workspace=tmp_path).execute(
                path=str(path),
                old_text="original",
                new_text="agent change",
            )
        else:
            operation = ApplyPatchTool(workspace=tmp_path).execute(
                edits=[
                    {
                        "path": str(path),
                        "action": "replace",
                        "old_text": "original",
                        "new_text": "agent change",
                    }
                ]
            )
        agent = asyncio.create_task(operation)
        await wait(committing)
        # A waiting commit must neither freeze the runtime nor block another file.
        other = await asyncio.wait_for(
            WriteFileTool(workspace=tmp_path).execute(path="independent.txt", content="available"),
            3,
        )
        assert "Error" not in other
        assert not agent.done()
    finally:
        release.set()
        await browser
        if agent is not None:
            result = await agent
    assert "changed while preparing" in result
    assert path.read_text() == "browser change"


@pytest.mark.asyncio
async def test_browser_cannot_save_a_partially_published_patch_that_is_rolled_back(
    tmp_path, monkeypatch
):
    from cirno_core.agent.tools.filesystem import patch_plan

    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_text("original first")
    second.write_text("original second")
    scope = build_workspace_scope(tmp_path, "restricted")
    partial, release = Event(), Event()
    write = patch_plan.atomic_write_text

    def fail_second(target, content):
        if target == second and content == "changed second\n":
            partial.set()
            assert release.wait(5)
            raise OSError("Disk write failed")
        write(target, content)

    monkeypatch.setattr(patch_plan, "atomic_write_text", fail_second)
    agent = asyncio.create_task(
        ApplyPatchTool(workspace=tmp_path).execute(
            edits=[
                {
                    "path": str(first),
                    "action": "replace",
                    "old_text": "original first",
                    "new_text": "changed first",
                },
                {
                    "path": str(second),
                    "action": "replace",
                    "old_text": "original second",
                    "new_text": "changed second",
                },
            ]
        )
    )
    browser = None
    try:
        await wait(partial)
        revision = workspace_files.read_workspace_file(str(first), scope=scope)["revision"]
        browser = asyncio.create_task(
            asyncio.to_thread(
                workspace_files.save_workspace_file,
                str(first),
                "browser change",
                revision,
                scope=scope,
            )
        )
        await asyncio.sleep(0)
    finally:
        release.set()
        result = await agent
    assert "Disk write failed" in result
    assert browser is not None
    with pytest.raises(WebUIFilePreviewError) as error:
        await browser
    assert error.value.status == 409
    assert first.read_text() == "original first"
    assert second.read_text() == "original second"
