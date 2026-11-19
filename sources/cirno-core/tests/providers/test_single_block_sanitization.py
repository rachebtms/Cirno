"""Single content objects receive the same boundary cleaning as block lists."""

from copy import deepcopy

import pytest
from cirno_core.providers.messages import sanitize_empty_content


@pytest.mark.parametrize("message", [
    {"role": "user", "content": {"type": "text", "text": "Hello", "_meta": {"path": "/private/notes"}}},
    {"role": "tool", "content": {"type": "image_url", "image_url": {"url": "data:image/png;base64,FAKE"}, "_meta": {"path": "/private/image.png"}}},
    {"role": "user", "content": {"type": "text", "text": ""}},
    {"role": "assistant", "content": {"type": "text", "text": ""}, "tool_calls": [{"id": "call_fixture"}]},
])
def test_single_content_block_matches_list_form_without_mutating_source(message):
    original = deepcopy(message)
    as_list = {**message, "content": [deepcopy(message["content"])]}
    expected = sanitize_empty_content([as_list])
    result = sanitize_empty_content([message])
    assert result == expected
    assert message == original
    content = result[0]["content"]
    if isinstance(content, list):
        assert all("_meta" not in block for block in content)
