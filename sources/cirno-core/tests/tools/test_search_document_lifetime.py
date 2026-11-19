"""Search cancellation retains workers and releases admitted document owners."""

import asyncio
import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cirno_core.agent.tools.search.find import FindFilesTool
from cirno_core.agent.tools.search.grep import GrepTool
from cirno_core.utils import document


@pytest.mark.parametrize("tool_type", [FindFilesTool, GrepTool])
@pytest.mark.parametrize("failure", [None, InterruptedError, OSError])
async def test_search_stop_waits_for_worker_cleanup(tmp_path, monkeypatch, tool_type, failure):
    entered, release, cleaned = Event(), Event(), Event()
    tool = tool_type(workspace=tmp_path)

    def blocked_scan(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(3), "test did not release search worker"
            if failure:
                raise failure("fixture worker stopped")
            return "finished"
        finally:
            cleaned.set()

    monkeypatch.setattr(tool, "_execute_sync", blocked_scan)
    task = asyncio.create_task(
        tool.execute(**({"pattern": "fixture"} if tool_type is GrepTool else {}))
    )
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done(), "Stop completed before the owned scan had exited"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(cleaned.wait, 2)


@pytest.mark.parametrize(
    "finish", ["unstarted", "partial", "exhausted", "error", "empty", "invalid"]
)
def test_pdf_search_closes_reader_on_every_exit(tmp_path, monkeypatch, finish):
    extract = Mock(return_value="needle\nsecond line")
    if finish == "error":
        extract.side_effect = ValueError("fixture parse failure")
    reader = SimpleNamespace(
        pages=[]
        if finish == "empty"
        else [SimpleNamespace(get_contents=lambda: None, extract_text=extract)],
        close=Mock(),
    )
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=Mock(return_value=reader)))
    if finish == "invalid":
        with pytest.raises(document.PdfPageRangeError):
            document._open_pdf_line_source(tmp_path / "fixture.pdf", "invalid")
    else:
        source = document._open_pdf_line_source(tmp_path / "fixture.pdf", None)
        if finish == "partial":
            next(source.lines)
        elif finish == "error":
            with pytest.raises(ValueError, match="fixture parse failure"):
                next(source.lines)
        elif finish in {"exhausted", "empty"}:
            list(source.lines)
        close = getattr(source.lines, "close", lambda: None)
        close()
        close()
    reader.close.assert_called_once()


@pytest.mark.parametrize("finish", ["unstarted", "partial", "exhausted", "error"])
def test_xlsx_search_closes_workbook_on_every_exit(tmp_path, monkeypatch, finish):
    rows = Mock(return_value=iter([("needle",), ("second line",)]))
    if finish == "error":
        rows.side_effect = ValueError("fixture row failure")
    worksheet = SimpleNamespace(title="fixture", reset_dimensions=Mock(), iter_rows=rows)
    workbook = SimpleNamespace(worksheets=[worksheet], close=Mock())
    monkeypatch.setattr(document, "_check_office_archive", lambda _path: None)
    monkeypatch.setitem(
        sys.modules, "openpyxl", SimpleNamespace(load_workbook=Mock(return_value=workbook))
    )
    source = document._open_xlsx_line_source(tmp_path / "fixture.xlsx")
    if finish == "partial":
        next(source.lines)
    elif finish == "error":
        with pytest.raises(ValueError, match="fixture row failure"):
            next(source.lines)
    elif finish == "exhausted":
        list(source.lines)
    source.lines.close()
    source.lines.close()
    workbook.close.assert_called_once()


@pytest.mark.parametrize("suffix", [".pdf", ".xlsx"])
@pytest.mark.parametrize("mode", ["content", "count", "files_with_matches"])
async def test_public_document_search_preserves_results_and_closes_owner(
    tmp_path, monkeypatch, suffix, mode
):
    path = tmp_path / ("fixture" + suffix)
    path.write_bytes(b"fixture")
    close = Mock()
    if suffix == ".pdf":
        reader = SimpleNamespace(
            pages=[SimpleNamespace(get_contents=lambda: None, extract_text=lambda: "needle")],
            close=close,
        )
        monkeypatch.setitem(
            sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda *_a, **_k: reader)
        )
        locator = "page=1,line=1"
    else:
        worksheet = SimpleNamespace(
            title="Data",
            reset_dimensions=Mock(),
            iter_rows=lambda **_k: iter([("other", "needle")]),
        )
        workbook = SimpleNamespace(worksheets=[worksheet], close=close)
        monkeypatch.setattr(document, "_check_office_archive", lambda _path: None)
        monkeypatch.setitem(
            sys.modules, "openpyxl", SimpleNamespace(load_workbook=lambda *_a, **_k: workbook)
        )
        locator = "sheet='Data',row=1,cell=B1"
    result = await GrepTool(workspace=tmp_path).execute(
        pattern="needle", path=path.name, output_mode=mode, fixed_strings=True
    )
    assert not getattr(result, "is_error", False)
    assert path.name in result
    if mode == "content":
        assert locator in result and "needle" in result
    elif mode == "count":
        assert result.startswith(f"{path.name}: 1")
        assert "total matches: 1 in 1 files" in result
    else:
        assert result == path.name
    close.assert_called_once()
