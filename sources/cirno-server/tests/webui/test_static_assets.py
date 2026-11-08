from __future__ import annotations

import gzip
from pathlib import Path
from unittest.mock import MagicMock

from cirno_server.webui.http import ServerHTTPHandler
from cirno_server.webui.http.assets import AssetsRoutes


def _handler(static_dist_path: Path) -> ServerHTTPHandler:
    handler = object.__new__(ServerHTTPHandler)
    handler.static_dist_path = static_dist_path
    handler._log = MagicMock()
    handler.assets_routes = AssetsRoutes(handler)
    return handler


def test_static_asset_serves_precompressed_gzip_variant(tmp_path) -> None:
    source = b"const message = 'hello';\n" * 200
    asset = tmp_path / "assets" / "app-abc123.js"
    asset.parent.mkdir()
    asset.write_bytes(source)
    compressed = gzip.compress(source, mtime=0)
    asset.with_name(f"{asset.name}.gz").write_bytes(compressed)

    response = _handler(tmp_path).assets_routes._serve_static(
        "/assets/app-abc123.js",
        accept_encoding="br, gzip; q=0.8",
    )

    assert response is not None
    assert response.headers["Content-Encoding"] == "gzip"
    assert response.headers["Vary"] == "Accept-Encoding"
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert response.headers["Content-Type"] == "application/javascript; charset=utf-8"
    assert int(response.headers["Content-Length"]) == len(compressed)
    assert gzip.decompress(response.body) == source


def test_static_asset_preserves_identity_when_gzip_is_rejected(tmp_path) -> None:
    source = b"body { color: black; }\n" * 200
    asset = tmp_path / "assets" / "app-abc123.css"
    asset.parent.mkdir()
    asset.write_bytes(source)
    asset.with_name(f"{asset.name}.gz").write_bytes(gzip.compress(source, mtime=0))

    response = _handler(tmp_path).assets_routes._serve_static(
        "/assets/app-abc123.css",
        accept_encoding="gzip;q=0, br",
    )

    assert response is not None
    assert "Content-Encoding" not in response.headers
    assert response.headers["Vary"] == "Accept-Encoding"
    assert response.body == source


def test_root_uses_precompressed_index_without_long_term_cache(tmp_path) -> None:
    source = b"<!doctype html><div id='root'></div>" * 100
    index = tmp_path / "index.html"
    index.write_bytes(source)
    compressed = gzip.compress(source, mtime=0)
    index.with_name("index.html.gz").write_bytes(compressed)

    response = _handler(tmp_path).assets_routes._serve_static(
        "/",
        accept_encoding="gzip",
    )

    assert response is not None
    assert response.headers["Content-Encoding"] == "gzip"
    assert response.headers["Cache-Control"] == "no-cache"
    assert gzip.decompress(response.body) == source
