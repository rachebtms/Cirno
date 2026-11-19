"""An unreadable document must not leak partial counts into successful totals."""

import pytest
from cirno_core.agent.tools.search.grep import GrepTool
from cirno_core.utils.document import DocumentLineSource, LocatedDocumentLine


@pytest.mark.parametrize("include_valid_file", [False, True])
async def test_failed_document_does_not_contribute_unreported_match_counts(
    tmp_path, monkeypatch, include_valid_file
):
    (tmp_path / "broken.pdf").write_bytes(b"fixture")
    if include_valid_file:
        (tmp_path / "good.txt").write_text("needle")
    closed = []

    def partial():
        try:
            yield LocatedDocumentLine("needle", 1, "page=1,line=1")
            raise ValueError("fixture unreadable later page")
        finally:
            closed.append(True)

    monkeypatch.setattr(
        "cirno_core.agent.tools.search.sources.open_document_line_source",
        lambda *_args, **_kwargs: DocumentLineSource(partial()),
    )
    result = await GrepTool(workspace=tmp_path).execute(pattern="needle", output_mode="count")
    assert "could not search 1 documents" in result
    assert "fixture unreadable later page" in result
    if include_valid_file:
        assert "good.txt: 1" in result
        assert "total matches: 1 in 1 files" in result
    else:
        assert "No matches found" in result
        assert "total matches:" not in result
    assert closed == [True]
