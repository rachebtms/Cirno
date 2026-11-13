"""Every advertised/legacy input reaches the same control and lifecycle contract."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.agent.loop import AgentLoop
from cirno_core.bus.events import InboundMessage, OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.command.builtin.catalog import BUILTIN_COMMAND_SPECS, USER_SHELL_COMMAND, builtin_command_palette, builtin_command_starts_agent_turn
from cirno_core.command.builtin.registration import register_builtin_commands
from cirno_core.command.builtin.service import cmd_restart
from cirno_core.command.router import CommandContext, CommandRouter


def test_catalog_covers_all_registered_inputs_and_v016_spellings():
    router = CommandRouter()
    register_builtin_commands(router)
    names = {name for spec in BUILTIN_COMMAND_SPECS for name in (spec.command, *spec.aliases)}
    assert set(router._registered_commands()) == names | {USER_SHELL_COMMAND}
    assert {
        "/temporary", "/ptc", "/access", "/resume", "/clear", "/new", "/compact", "/stop", "/restart", "/status",
        "/model", "/history", "/goal", "/trigger", "/dream", "/dream-log", "/dream-restore", "/dream-prompt", "/skill", "/help", "/pairing",
    } <= names
    visible = {row["command"] for row in builtin_command_palette()}
    assert {"/dream-log", "/dream-restore"} <= visible
    assert not {"/dream-prompt", "/pairing", "/compact", "/dream"} & visible
    assert {row["command"] for row in builtin_command_palette(include_hidden=True)} == {spec.command for spec in BUILTIN_COMMAND_SPECS}


@pytest.mark.parametrize("spec", BUILTIN_COMMAND_SPECS, ids=lambda spec: spec.command)
@pytest.mark.parametrize("separator", [" ", "\t", "\n"])
async def test_each_command_and_alias_keeps_argument_routing_and_lifecycle(spec, separator):
    for name in (spec.command, *spec.aliases):
        router = CommandRouter()
        register_builtin_commands(router)
        captured = []

        async def handler(ctx):
            captured.append(ctx.args)
            return OutboundMessage(channel="cli", chat_id="audit", content="handled")

        is_priority = router.is_priority(name)
        if is_priority:
            router.priority(name, handler)
        else:
            router._exact[name] = handler
        if spec.accepts_args:
            router._prefix = [(prefix, handler if prefix == name + " " else registered) for prefix, registered in router._prefix]
        args = "first  line\n第二行" if spec.accepts_args else ""
        raw = f"  {name.upper()}@CirnoBot{separator}{args}  "
        msg = InboundMessage(channel="cli", sender_id="owner", chat_id="audit", content=raw)
        ctx = CommandContext(msg=msg, session=None, key=msg.session_key, raw=raw, loop=MagicMock())
        result = await (router.dispatch_priority(ctx) if is_priority else router.dispatch(ctx))
        assert result.content == "handled"
        assert captured == [args]
        assert builtin_command_starts_agent_turn(raw) is (spec.lifecycle in {"agent_turn", "agent_turn_with_args"} and bool(args))
        if name in {"/consolidate", "/compact", "/dream"}:
            assert router.requires_session_queue(raw)


@pytest.mark.parametrize("content", ["/help", "/history\t5", "/skill", "/model", "/pairing list", "/dream-prompt init", "/stop unexpected"])
async def test_control_input_does_not_need_a_model_or_reach_the_provider(tmp_path, content):
    provider = MagicMock(aclose=AsyncMock())
    agent = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="test", context_window_tokens=128_000)
    agent.runtime_for_session = AsyncMock(side_effect=ValueError("No models configured"))
    try:
        result = await agent.processing.process(InboundMessage(channel="cli", sender_id="owner", chat_id="audit", content=content))
        assert result is not None and result.content
        provider.chat.assert_not_called()
        if content != "/model":
            agent.runtime_for_session.assert_not_called()
        assert builtin_command_starts_agent_turn(content) is False
    finally:
        await agent.aclose()


async def test_restart_rejects_an_agent_input_before_scheduling_any_process_work(monkeypatch):
    schedule = MagicMock()
    monkeypatch.setattr("cirno_core.command.builtin.service.asyncio.create_task", schedule)
    loop = MagicMock()
    msg = InboundMessage(channel="cli", sender_id="agent", chat_id="audit", content="/restart")
    result = await cmd_restart(CommandContext(msg=msg, session=None, key=msg.session_key, raw=msg.content, loop=loop))
    assert "direct user request" in result.content
    schedule.assert_not_called()
