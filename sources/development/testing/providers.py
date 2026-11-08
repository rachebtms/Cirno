"""Replay chunk fixtures through the production incremental decoder."""

from collections.abc import Iterable

from cirno_core.providers.chat_completions.streaming import ChatStreamAccumulator
from cirno_core.providers.contracts import LLMResponse


def parse_chat_chunks(chunks: Iterable[object]) -> LLMResponse:
    decoder = ChatStreamAccumulator()
    for chunk in chunks:
        decoder.consume(chunk)
    return decoder.response()
