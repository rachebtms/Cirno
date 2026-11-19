"""Stop avoids subsequent document work and closes admitted parser resources."""

import asyncio
import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cirno_core.agent.tools.filesystem import ReadFileTool
from cirno_core.utils.document import (
    DocumentLineSource,
    LocatedDocumentLine,
    PdfPageRangeError,
    extract_pdf_pages,
)


@pytest.mark.parametrize("suffix", [".docx", ".xlsx", ".pptx"])
async def test_stop_closes_office_iterator_without_scanning_remaining_lines(
    tmp_path, monkeypatch, suffix
):
    path = tmp_path / ("fixture" + suffix)
    path.write_bytes(b"PK")
    entered, release, closed = Event(), Event(), Event()
    produced = []

    def lines():
        try:
            for number in range(1, 6):
                if number == 2:
                    entered.set()
                    assert release.wait(3), "test did not release document parser"
                produced.append(number)
                yield LocatedDocumentLine("fixture", number, "")
        finally:
            closed.set()

    monkeypatch.setattr(
        "cirno_core.utils.document.open_document_line_source",
        lambda _path: DocumentLineSource(lines()),
    )
    task = asyncio.create_task(ReadFileTool(workspace=tmp_path).execute(path=path.name))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert produced == [1, 2]
        assert closed.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("pages", ["2-3", "invalid", None])
def test_pdf_extraction_keeps_page_ranges_and_closes_reader(tmp_path, monkeypatch, pages):
    extracts = [Mock(return_value=f"page {n}") for n in range(1, 5)]
    reader = SimpleNamespace(
        pages=[
            SimpleNamespace(get_contents=lambda: None, extract_text=extract) for extract in extracts
        ],
        close=Mock(),
    )
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=Mock(return_value=reader)))
    if pages == "invalid":
        with pytest.raises(PdfPageRangeError):
            extract_pdf_pages(tmp_path / "fixture.pdf", pages=pages)
        assert not any(extract.called for extract in extracts)
    else:
        result = extract_pdf_pages(tmp_path / "fixture.pdf", pages=pages, max_pages=2)
        start = 1 if pages else 0
        assert (result.total_pages, result.start_page, result.end_page) == (4, start, start + 1)
        assert result.text == "\n\n".join(
            f"--- Page {n + 1} ---\npage {n + 1}" for n in range(start, start + 2)
        )
        assert [extract.called for extract in extracts] == [
            start <= index <= start + 1 for index in range(4)
        ]
    reader.close.assert_called_once()


def test_pdf_stop_before_open_does_not_create_reader(tmp_path, monkeypatch):
    factory = Mock()
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=factory))
    cancelled = Event()
    cancelled.set()
    with pytest.raises(InterruptedError):
        extract_pdf_pages(tmp_path / "fixture.pdf", cancelled=cancelled)
    factory.assert_not_called()


async def test_stop_pdf_skips_later_pages_and_closes_reader(tmp_path, monkeypatch):
    path = tmp_path / "fixture.pdf"
    path.write_bytes(b"%PDF")
    entered, release = Event(), Event()
    produced = []

    def extract(number):
        produced.append(number)
        if number == 1:
            entered.set()
            assert release.wait(3), "test did not release PDF parser"
        return "fixture page"

    reader = SimpleNamespace(
        pages=[
            SimpleNamespace(
                get_contents=lambda: None, extract_text=lambda number=n: extract(number)
            )
            for n in range(1, 5)
        ],
        close=Mock(),
    )
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=Mock(return_value=reader)))
    task = asyncio.create_task(ReadFileTool(workspace=tmp_path).execute(path=path.name))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert produced == [1]
        reader.close.assert_called_once()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
