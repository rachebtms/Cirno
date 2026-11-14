"""Tool-call identity remains separate when a compatible gateway omits indices."""

import json
from itertools import zip_longest

import pytest

from cirno_core.agent.tools.instance_features import InspectSkillTool
from cirno_core.agent.tools.apply_patch import ApplyPatchTool
from cirno_core.agent.tools.filesystem import EditFileTool
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.providers.chat_completions.streaming import ChatStreamAccumulator


def chunk(identity, arguments, *, name=None, index=None):
    call = {"id": identity, "function": {"arguments": arguments}}
    if name is not None:
        call["function"]["name"] = name
    if index is not None:
        call["index"] = index
    return {"choices": [{"delta": {"tool_calls": [call]}}]}


async def test_interleaved_file_calls_preserve_escaped_quotes_through_execution(tmp_path):
    original = 'title = "旧标题"\n'
    updated = 'title = "新标题"\npath = "C:\\papers"\n'
    (tmp_path / "edit.txt").write_text(original)
    arguments = [
        {"path": "edit.txt", "old_text": original, "new_text": updated},
        {"edits": [{"path": "patch.txt", "action": "add", "new_text": updated}]},
    ]
    stream = ChatStreamAccumulator()
    for index, name in enumerate(("files__edit", "files__patch")):
        stream.consume(chunk(f"call_{index}", "", name=name, index=0))
    for pair in zip_longest(*(json.dumps(value, ensure_ascii=False) for value in arguments), fillvalue=""):
        for index, fragment in enumerate(pair):
            if fragment:
                stream.consume(chunk(f"call_{index}", fragment, index=0))
    calls = stream.response().tool_calls
    assert [call.arguments for call in calls] == arguments
    registry = ToolRegistry()
    registry.register(EditFileTool(workspace=tmp_path))
    registry.register(ApplyPatchTool(workspace=tmp_path))
    for call in calls:
        result = await registry.execute(call.name, call.arguments)
        assert not getattr(result, "is_error", False), result
    assert (tmp_path / "edit.txt").read_text() == updated
    assert (tmp_path / "patch.txt").read_text() == updated


@pytest.mark.parametrize("interleaved", [False, True])
def test_distinct_skill_calls_without_indices_do_not_concatenate_json(interleaved):
    stream = ChatStreamAccumulator()
    validate = chunk("call_validate", '{"name":', name="skills__validate")
    history = chunk("call_history", '{"name":', name="skills__history")
    end_validate = chunk("call_validate", '"stss"}')
    end_history = chunk("call_history", '"stss"}')
    chunks = [validate, history, end_validate, end_history] if interleaved else [validate, end_validate, history, end_history]
    deltas = [stream.consume(value).tool_calls[0] for value in chunks]
    calls = stream.response().tool_calls
    assert [(call.id, call.name, call.arguments) for call in calls] == [
        ("call_validate", "skills__validate", {"name": "stss"}),
        ("call_history", "skills__history", {"name": "stss"}),
    ]
    registry = ToolRegistry()
    registry.register(InspectSkillTool())
    for call in calls:
        assert registry.prepare_call(call.name, call.arguments)[2] is None
    assert {delta["index"] for delta in deltas if delta["call_id"] == "call_validate"} == {0}
    assert {delta["index"] for delta in deltas if delta["call_id"] == "call_history"} == {1}


def test_missing_index_continues_the_identified_nonzero_slot():
    stream = ChatStreamAccumulator()
    stream.consume(chunk("call_other", '{}', name="other", index=0))
    stream.consume(chunk("call_skill", '{"name":', name="skills__validate", index=5))
    delta = stream.consume(chunk("call_skill", '"stss"}')).tool_calls[0]
    assert delta["index"] == 5
    assert [call.arguments for call in stream.response().tool_calls] == [{}, {"name": "stss"}]


def test_argument_fragments_are_not_deduplicated_or_repaired():
    stream = ChatStreamAccumulator()
    for fragment in ('{"name":"', 'st', 'st', '"}'):
        stream.consume(chunk("call_skill", fragment, name="skills__validate"))
    assert stream.response().tool_calls[0].arguments == {"name": "stst"}
    malformed = ChatStreamAccumulator()
    malformed.consume(chunk("call_bad", '{"name":"stss"}{}', name="skills__validate"))
    assert malformed.response().tool_calls[0].arguments == '{"name":"stss"}{}'


def test_single_anonymous_delta_continues_the_only_nonzero_slot():
    stream = ChatStreamAccumulator()
    stream.consume(chunk("call_skill", '{"name":', name="skills__validate", index=5))
    assert stream.consume(chunk(None, '"stss"}')).tool_calls[0]["index"] == 5
    assert stream.response().tool_calls[0].arguments == {"name": "stss"}


def test_reused_wire_index_with_identified_interleaved_calls_keeps_separate_buffers():
    stream = ChatStreamAccumulator()
    values = [
        chunk("call_first", '{"content":"', name="user__message", index=0),
        chunk("call_second", '{"content":"new message"}', name="user__message", index=0),
        chunk("call_first", 'first message"}', index=0),
    ]
    deltas = [stream.consume(value).tool_calls[0] for value in values]
    assert [delta["index"] for delta in deltas] == [0, 1, 0]
    assert [(call.id, call.arguments) for call in stream.response().tool_calls] == [
        ("call_first", {"content": "first message"}),
        ("call_second", {"content": "new message"}),
    ]


def test_reused_index_can_continue_anonymous_deltas_after_previous_call_is_complete():
    stream = ChatStreamAccumulator()
    stream.consume(chunk("call_first", '{}', name="first", index=0))
    stream.consume(chunk("call_second", '{"name":', name="second", index=0))
    stream.consume(chunk(None, '"stss"}', index=0))
    # A later ordinary wire index must not collide with the normalized slot.
    stream.consume(chunk("call_third", '{"n":', name="third", index=1))
    delta = stream.consume(chunk(None, '3}', index=1)).tool_calls[0]
    assert delta["index"] == 2
    assert [call.arguments for call in stream.response().tool_calls] == [{}, {"name": "stss"}, {"n": 3}]


def test_new_anonymous_wire_index_does_not_reuse_another_calls_normalized_slot():
    stream = ChatStreamAccumulator()
    stream.consume(chunk("call_first", '{}', name="first", index=0))
    stream.consume(chunk("call_second", '{}', name="second", index=0))
    stream.consume(chunk(None, '{"n":3}', name="third", index=1))
    assert [(call.name, call.arguments) for call in stream.response().tool_calls] == [
        ("first", {}), ("second", {}), ("third", {"n": 3}),
    ]


def test_ambiguous_deltas_are_rejected_instead_of_joining_different_calls():
    stream = ChatStreamAccumulator()
    stream.consume(chunk("call_a", '{"name":', name="skills__validate", index=0))
    stream.consume(chunk("call_b", '{"name":', name="skills__validate", index=1))
    with pytest.raises(ValueError, match="missing both index and ID"):
        stream.consume(chunk(None, '"stss"}'))
    reused = ChatStreamAccumulator()
    reused.consume(chunk("call_a", '{"name":', name="skills__validate", index=0))
    reused.consume(chunk("call_b", '{"name":', name="skills__validate", index=0))
    with pytest.raises(ValueError, match="no ID for a reused index"):
        reused.consume(chunk(None, '"stss"}', index=0))
    duplicate = ChatStreamAccumulator()
    duplicate.consume(chunk("reused", '{"name":', name="skills__validate", index=0))
    duplicate.consume(chunk("reused", '{"name":', name="skills__validate", index=1))
    with pytest.raises(ValueError, match="ambiguous ID"):
        duplicate.consume(chunk("reused", '"stss"}'))


@pytest.mark.parametrize(("indexed", "as_sdk"), [
    (False, False), (True, False), ("reused", False), (True, True), ("reused", True),
])
def test_parallel_identical_chinese_questions_keep_distinct_argument_buffers(indexed, as_sdk):
    import json
    question = {"question": "主人，请确认这一轮论文阅读结果。" * 24, "options": ["继续", "暂停"]}
    arguments = [json.dumps(question, ensure_ascii=False), json.dumps(question, ensure_ascii=False), '{"to":"@fili","limit":20}']
    names = ["user__ask", "user__ask", "conversations__read"]
    stream = ChatStreamAccumulator()
    for start in range(0, max(map(len, arguments)), 13):
        calls = []
        for i, text in enumerate(arguments):
            if start >= len(text):
                continue
            call = {"id": f"parallel-{i}", "function": {"arguments": text[start:start + 13]}}
            if start == 0:
                call["function"]["name"] = names[i]
            if indexed:
                call["index"] = 0 if indexed == "reused" else i
            calls.append(call)
        value = {"choices": [{"index": 0, "delta": {"tool_calls": calls}}]}
        if as_sdk:
            from openai.types.chat import ChatCompletionChunk

            value = ChatCompletionChunk.model_validate({
                "id": "fixture", "object": "chat.completion.chunk", "created": 0, "model": "fixture", **value,
            })
        stream.consume(value)
    parsed = stream.response().tool_calls
    assert [call.id for call in parsed] == [f"parallel-{i}" for i in range(3)]
    assert [call.arguments for call in parsed] == [question, question, {"to": "@fili", "limit": 20}]
