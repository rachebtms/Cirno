"""MCP results."""

from __future__ import annotations

import json
from typing import Any, cast


def _image_block_data_url(block: Any, types: Any) -> str | None:
    """Return a base64 ``data:`` URL for an MCP image-bearing content block.

    Handles ``ImageContent`` and image blobs inside ``EmbeddedResource``.
    """
    image_cls = getattr(types, "ImageContent", None)
    if image_cls is not None and isinstance(block, image_cls):
        mime = getattr(block, "mimeType", None) or "image/png"
        return f"data:{mime};base64,{block.data}"

    embedded_cls = getattr(types, "EmbeddedResource", None)
    blob_cls = getattr(types, "BlobResourceContents", None)
    if embedded_cls is not None and isinstance(block, embedded_cls):
        resource = getattr(block, "resource", None)
        if blob_cls is not None and isinstance(resource, blob_cls):
            blob_resource = cast(Any, resource)
            mime = getattr(blob_resource, "mimeType", None) or ""
            if isinstance(mime, str) and mime.startswith("image/"):
                return f"data:{mime};base64,{blob_resource.blob}"
    return None


def _mcp_image_tool_result(text_parts: list[str], artifacts: list[dict[str, Any]]) -> str:
    """Build the compact tool result for an MCP call that returned image(s).

    The base64 stays out of the model context entirely — only artifact paths and
    metadata are returned, so the result is small and the channel can deliver the
    saved file via the message tool.
    """
    payload: dict[str, Any] = {
        "artifacts": artifacts,
        "next_step": (
            "These images were returned by an MCP tool and saved as local artifacts. "
            "In the Router conversation, attach the artifact paths with message.media. "
            "In regular conversations, include Markdown image links to the artifact paths "
            "in your reply. Keep base64 data out of the reply."
        ),
    }
    text = "\n".join(part for part in text_parts if part)
    if text:
        payload["text"] = text
    return json.dumps(payload, ensure_ascii=False)
