"""Complete and streamed compatible responses share tool execution contracts."""

import json

from cirno_core.providers.chat_completions.complete import parse_response
from cirno_core.providers.chat_completions.streaming import ChatStreamAccumulator


def test_complete_legacy_function_call_preserves_the_executable_call():
    function = {"name": "skills__validate", "arguments": '{"name":"stss"}'}
    complete = parse_response({"choices": [{"message": {"content": None, "function_call": function},
                                           "finish_reason": "function_call"}]})
    stream = ChatStreamAccumulator()
    stream.consume({"choices": [{"delta": {"function_call": function}, "finish_reason": "function_call"}]})
    assert [(call.name, call.arguments) for call in complete.tool_calls] == [
        (call.name, call.arguments) for call in stream.response().tool_calls
    ]
    assert complete.tool_calls[0].id


def test_structured_tools_take_precedence_over_duplicate_legacy_field():
    function = {"name": "skills__validate", "arguments": '{"name":"stss"}'}
    response = parse_response({"choices": [{"message": {
        "tool_calls": [{"id": "modern", "function": function}], "function_call": function,
    }}]})
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "modern"


def test_text_tool_calls_with_reused_ids_have_distinct_result_keys():
    text = "\n".join('<tool_call>' + json.dumps({"id": "same-id", "name": "skills__validate", "arguments": {"name": name}})
                     + '</tool_call>' for name in ("first", "second"))
    response = parse_response({"choices": [{"message": {"content": text}}]})
    assert [call.arguments for call in response.tool_calls] == [{"name": "first"}, {"name": "second"}]
    assert len({call.id for call in response.tool_calls}) == 2
    stream = ChatStreamAccumulator()
    stream.consume(text)
    assert len({call.id for call in stream.response().tool_calls}) == 2
