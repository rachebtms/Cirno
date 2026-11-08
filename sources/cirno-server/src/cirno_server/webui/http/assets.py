"""Assets HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING

from cirno_server.webui.http_utils import accepts_gzip as _accepts_gzip
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_response as _http_response
from websockets.http11 import Response

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class AssetsRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server

    def _serve_static(
        self,
        request_path: str,
        *,
        accept_encoding: str = "",
    ) -> Response | None:
        assert self.server.static_dist_path is not None
        rel = request_path.lstrip("/")
        if not rel:
            rel = "index.html"
        if ".." in rel.split("/") or rel.startswith("/"):
            return _http_error(403, "Forbidden")
        candidate = (self.server.static_dist_path / rel).resolve()
        try:
            candidate.relative_to(self.server.static_dist_path)
        except ValueError:
            return _http_error(403, "Forbidden")
        if not candidate.is_file():
            return None
        ctype, _ = mimetypes.guess_type(candidate.name)
        if ctype is None:
            ctype = "application/octet-stream"
        utf8_text = ctype.startswith("text/") or ctype in {
            "application/javascript",
            "application/json",
        }
        compressible = utf8_text or ctype == "image/svg+xml"
        response_path = candidate
        extra_headers: list[tuple[str, str]] = []
        if compressible:
            extra_headers.append(("Vary", "Accept-Encoding"))
            gzip_candidate = candidate.with_name(f"{candidate.name}.gz")
            if _accepts_gzip(accept_encoding) and gzip_candidate.is_file():
                response_path = gzip_candidate.resolve()
                if not response_path.is_relative_to(self.server.static_dist_path):
                    return _http_error(403, "Forbidden")
                extra_headers.append(("Content-Encoding", "gzip"))
        try:
            body = response_path.read_bytes()
        except OSError as e:
            self.server._log.warning("static: failed to read {}: {}", response_path, e)
            return _http_error(500, "Internal Server Error")
        if utf8_text:
            ctype = f"{ctype}; charset=utf-8"
        if "assets" in candidate.relative_to(self.server.static_dist_path).parts:
            cache = "public, max-age=31536000, immutable"
        else:
            cache = "no-cache"
        return _http_response(
            body,
            status=200,
            content_type=ctype,
            extra_headers=[("Cache-Control", cache), *extra_headers],
        )
