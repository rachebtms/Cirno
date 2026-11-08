"""Large media stays bounded, range-complete and bound to its signed snapshot."""

import tracemalloc

import pytest


@pytest.mark.parametrize("suffix", [".pdf", ".mp4"])
async def test_large_full_download_has_bounded_memory(tmp_path, media_client, suffix):
    gateway, client = media_client
    source = tmp_path / ("large" + suffix)
    size = 128 * 1024 * 1024
    with source.open("wb") as output:
        output.truncate(size)
    url = gateway.sign_or_stage_media_path(source)["url"]
    tracemalloc.start()
    try:
        async with client.get(url) as response:
            assert response.status == 200
            assert response.content_length == size
            received = 0
            async for chunk in response.content.iter_chunked(64 * 1024):
                received += len(chunk)
            assert received == size
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024, f"128 MiB download retained {peak} bytes"


@pytest.mark.parametrize(
    ("header", "status", "body", "content_range"),
    [
        ("bytes=2-5", 206, b"2345", "bytes 2-5/10"),
        ("bytes=-3", 206, b"789", "bytes 7-9/10"),
        ("bytes=7-", 206, b"789", "bytes 7-9/10"),
        ("bytes=8-100", 206, b"89", "bytes 8-9/10"),
        ("bytes=10-", 416, None, "bytes */10"),
        ("bytes=0-2,4-5", 416, None, "bytes */10"),
        ("bytes=", 416, None, "bytes */10"),
    ],
)
async def test_all_formats_share_exact_range_semantics(
    tmp_path, media_client, header, status, body, content_range
):
    gateway, client = media_client
    source = tmp_path / "research.txt"
    source.write_bytes(b"0123456789")
    url = gateway.sign_or_stage_media_path(source)["url"]
    async with client.get(url, headers={"Range": header}) as response:
        assert response.status == status
        assert response.headers["Content-Range"] == content_range
        if body is not None:
            assert await response.read() == body


async def test_range_larger_than_the_old_limit_is_not_truncated(tmp_path, media_client):
    gateway, client = media_client
    source = tmp_path / "experiment.webm"
    size = 16 * 1024 * 1024 + 1
    with source.open("wb") as output:
        output.truncate(size)
    url = gateway.sign_or_stage_media_path(source)["url"]
    async with client.get(url, headers={"Range": "bytes=0-"}) as response:
        assert response.status == 206
        assert response.headers["Content-Range"] == f"bytes 0-{size - 1}/{size}"
        assert sum([len(chunk) async for chunk in response.content.iter_chunked(65536)]) == size


async def test_head_empty_download_and_compressed_sibling(tmp_path, media_client, monkeypatch):
    gateway, client = media_client
    source = tmp_path / "report.pdf"
    source.write_bytes(b"signed file")
    source.with_suffix(".pdf.gz").write_bytes(b"unsigned sibling")
    url = gateway.sign_or_stage_media_path(source)["url"]
    from cirno_server.webui.media import http

    real_open = http.open_atomic_snapshot

    class MetadataOnly:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, *_):
            pytest.fail("HEAD must not read the file body")

    with monkeypatch.context() as patch:
        patch.setattr(http, "open_atomic_snapshot", lambda path: MetadataOnly(real_open(path)))
        async with client.head(url) as response:
            assert response.status == 200
            assert response.content_length == len(b"signed file")
            assert await response.read() == b""
    async with client.get(url, headers={"Accept-Encoding": "gzip"}) as response:
        assert "Content-Encoding" not in response.headers
        assert await response.read() == b"signed file"
    source.write_bytes(b"")
    async with client.get(url) as response:
        assert response.status == 200
        assert response.content_length == 0
        assert await response.read() == b""


async def test_borrowed_attachment_rechecks_scope_and_svg_stays_sandboxed(tmp_path, media_client):
    gateway, client = media_client
    source = tmp_path / "figure.svg"
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    url = gateway.local_attachment_url(str(source), session_key="websocket:research")
    async with client.get(url) as response:
        assert response.status == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert "sandbox" in response.headers["Content-Security-Policy"]
    source.unlink()
    source.symlink_to(tmp_path.parent / "outside.svg")
    async with client.get(url) as response:
        assert response.status in {403, 404}
        assert await response.read() != b"private"
