"""Declared visual inputs and semantic probes shared by model setup and tools."""
from __future__ import annotations

import base64
import secrets
import struct
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from cirno_core.providers.base import LLMProvider
    from cirno_core.providers.contracts import LLMResponse


@dataclass(frozen=True, slots=True)
class MediaCapabilities:
    image: bool | None = None
    video: bool | None = None


_COLORS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255)}


def probe_image(colors: tuple[str, ...]) -> str:
    """Small unlabelled color panels; expected answers never enter the prompt."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    row = b"".join(bytes(_COLORS[color]) * 96 for color in colors)
    pixels = (b"\0" + row) * 128
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 96 * len(colors), 128, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


async def probe_visual_inputs(provider: LLMProvider, *, model: str, video_transport: bool, image: bool = True, video: bool = True) -> dict[str, Any]:
    """Probe actual visual understanding once; service failures remain unknown."""
    import asyncio
    import re
    from importlib.resources import files

    from cirno_core.providers.requests import ProviderRequestExecutor

    async def probe(kind: str) -> dict[str, Any]:
        colors = tuple(secrets.SystemRandom().sample(list(_COLORS), 3))
        if kind == "video" and not video_transport:
            return {"supported": None, "detail": "This request API has no native video input transport. Image frames can still be read with an image-capable model."}
        if kind == "image":
            block = {"type": "image_url", "image_url": {"url": probe_image(colors)}}
            question = "List the three panel colors in the image from left to right. Reply with only their English color names, separated by spaces."
        else:
            clip = files("cirno_core.providers").joinpath("probe_media", "-".join(colors) + ".mp4").read_bytes()
            block = {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + base64.b64encode(clip).decode("ascii")}}
            question = "List the full-screen colors in this video in temporal order, once per scene. Reply with only their English color names, separated by spaces."
        response = await ProviderRequestExecutor(provider).complete(model=model, messages=[{"role": "user", "content": [{"type": "text", "text": question}, block]}], tools=[], max_tokens=2048, temperature=0)
        if response.finish_reason == "error":
            # Rejected media is evidence; auth/rate limits/timeouts are not capability results.
            rejected = response.error_status_code in {400, 415, 422} and any(term in (response.content or "").lower() for term in ("image", "video", "vision", "multimodal", "content type"))
            return {"supported": False if rejected else None, "detail": response.content or response.error_kind or "Provider request failed"}
        seen = tuple(re.findall(r"\b(red|green|blue)\b", (response.content or "").lower()))
        understood = seen == colors
        return {"supported": True if understood else None, "detail": "Visual sample recognized" if understood else "The reply did not identify the visual sample; capability remains unverified."}

    results = await asyncio.gather(*(probe(kind) for kind, enabled in (("image", image), ("video", video)) if enabled))
    return dict(zip((kind for kind, enabled in (("image", image), ("video", video)) if enabled), results))


def media_input_error(provider: LLMProvider, messages: list[dict[str, Any]]) -> LLMResponse | None:
    from cirno_core.providers.contracts import LLMResponse
    capabilities = provider.media_capabilities
    unsupported = {kind for kind, allowed in (("image_url", capabilities.image), ("video_url", capabilities.video)) if allowed is False}
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in cast(list[object], content):
            if isinstance(block, dict) and cast(dict[str, Any], block).get("type") in unsupported:
                return LLMResponse(content="The selected model has this visual input disabled. Choose a compatible model or update its capabilities in Settings.", finish_reason="error", error_kind="unsupported_media")
    return None
