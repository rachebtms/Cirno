"""Tool-call identity remains separate when a compatible gateway omits indices."""

import pytest

from cirno_core.agent.tools.instance_features import InspectSkillTool
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.providers.chat_completions.streaming import ChatStreamAccumulator


def chunk(identity, arguments, *, name=None, index=None):
    call = {"id": identity, "function": {"arguments": arguments}}
    if name is not None:
        call["function"]["name"] = name
    if index is not None:
        call["index"] = index
    return {"choices": [{"delta": {"tool_calls": [call]}}]}


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


def test_changed_call_id_cannot_merge_arguments_into_an_occupied_index():
    stream = ChatStreamAccumulator()
    stream.consume(chunk("call_first", '{"content":"unfinished', name="user__message", index=0))
    with pytest.raises(ValueError, match="different call ID; arguments were not combined"):
        stream.consume(chunk("call_second", '{"content":"new message"}', name="user__message", index=0))
    call = stream.response().tool_calls[0]
    assert call.id == "call_first"
    assert call.arguments == '{"content":"unfinished'


def test_ambiguous_deltas_are_rejected_instead_of_joining_different_calls():
    stream = ChatStreamAccumulator()
    stream.consume(chunk("call_a", '{"name":', name="skills__validate", index=0))
    stream.consume(chunk("call_b", '{"name":', name="skills__validate", index=1))
    with pytest.raises(ValueError, match="missing both index and ID"):
        stream.consume(chunk(None, '"stss"}'))
    reused = ChatStreamAccumulator()
    reused.consume(chunk("reused", '{"name":', name="skills__validate", index=0))
    reused.consume(chunk("reused", '{"name":', name="skills__validate", index=1))
    with pytest.raises(ValueError, match="ambiguous ID"):
        reused.consume(chunk("reused", '"stss"}'))


@pytest.mark.parametrize("indexed", [False, True])
def test_parallel_identical_chinese_questions_keep_distinct_argument_buffers(indexed):
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
                call["index"] = i
            calls.append(call)
        stream.consume({"choices": [{"delta": {"tool_calls": calls}}]})
    parsed = stream.response().tool_calls
    assert [call.id for call in parsed] == [f"parallel-{i}" for i in range(3)]
    assert [call.arguments for call in parsed] == [question, question, {"to": "@fili", "limit": 20}]
