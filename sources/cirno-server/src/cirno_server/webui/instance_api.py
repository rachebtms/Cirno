"""Authenticated instance features shared by settings and conversation tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

from cirno_core.config.home import get_home_path
from cirno_core.nodes.service import Nodes
from cirno_core.session.router_session import ensure_router_session
from cirno_core.skills.history import inspect_skill
from cirno_core.storage.instance import InstanceData


async def instance_action(
    payload: dict, *, sessions, bus, config_path: Path | None = None
) -> dict:
    data = await asyncio.to_thread(InstanceData)
    action = payload.get("action", "")
    values = payload.get("values") or {}
    if action == "models.probe":
        from cirno_server.webui.model_capabilities import probe_model_capabilities
        return await probe_model_capabilities(values, config_path=config_path)
    if action.startswith("telegram."):
        from cirno_server.webui.telegram_api import telegram_action
        return await telegram_action(action, values)
    if action == "approvals.decide":
        from cirno_core.agent.approval.service import OperationApproval
        from cirno_core.utils.cancellation import shield_and_drain
        return await shield_and_drain(OperationApproval(sessions, bus).decide(values.get("id"), values.get("approved")))
    if action.startswith("inbox."):
        from cirno_core.notifications.inbox import NotificationInbox
        inbox = NotificationInbox()
        if action == "inbox.list":
            return await asyncio.to_thread(
                inbox.list, category=values.get("category"), before=values.get("before"),
                after=values.get("after"), limit=values.get("limit", 50),
            )
        if action == "inbox.read":
            await asyncio.to_thread(inbox.read, identifiers=values.get("ids"), category=values.get("category"))
            return {"ok": True}
        if action == "inbox.open":
            item = await asyncio.to_thread(inbox.get, values["id"])
            key = item.get("session_key")
            session = await sessions.state.read_header(key) if key else None
            generation = item["data"].get("session_generation")
            if session is None or not session.policy.persist or generation and session.generation != generation:
                await asyncio.to_thread(inbox.unavailable, item["id"])
                return {"session_key": None}
            return {"session_key": key}
        raise ValueError("Unknown inbox action")
    if action == "conversations.edit":
        from cirno_core.bus.outbound_events import (
            SessionUpdatedEvent,
            UserInputEvent,
            outbound_message_for_event,
        )
        from cirno_core.utils.cancellation import shield_and_drain
        async def edit_and_queue():
            with bus.admission.activity():
                message = await sessions.state.edit_user_input(values["session_key"], values["turn_id"], values["content"])
                await bus.publish_outbound(outbound_message_for_event(channel="websocket", chat_id=message.chat_id,
                    event=SessionUpdatedEvent(scope="reset"), metadata={}))
                # As with ordinary admission, every viewer receives the human
                # input before any model output, even if execution beats the ack.
                await bus.publish_outbound(outbound_message_for_event(
                    channel="websocket", chat_id=message.chat_id,
                    event=UserInputEvent(content=message.content,
                        created_at_ms=int(message.timestamp.timestamp() * 1000), provenance={}),
                    metadata=message.metadata,
                ))
                await bus.publish_inbound(message)
                return {"ok": True, "turn_id": message.metadata["webui_turn_id"]}
        return await shield_and_drain(edit_and_queue())
    if action == "bootstrap":
        key = await ensure_router_session(sessions)
        return {
            "projects": await asyncio.to_thread(data.list, "projects"),
            "router_session_key": key,
        }
    if action in {"router.heartbeat", "router.heartbeat.update"}:
        from cirno_server.webui.router_heartbeat import router_heartbeat_action
        return await router_heartbeat_action(action, values, sessions=sessions, bus=bus, config_path=config_path)
    if action.startswith("projects."):
        return await sessions.projects.action(action.removeprefix("projects."), values, bus=bus)
    if action == "nodes.list":
        return await asyncio.to_thread(Nodes(data).catalog)
    if action == "nodes.settings.save":
        from cirno_core.nodes.policy import save_policy
        policy = await asyncio.to_thread(save_policy, data, values)
        return {"job_settings": policy.model_dump()}
    if action == "nodes.save":
        node = await asyncio.to_thread(Nodes(data).save_node, values)
        return {"node": node, "nodes": await asyncio.to_thread(Nodes(data).list_nodes)}
    if action == "nodes.delete":
        await asyncio.to_thread(Nodes(data).remove_node, values["id"])
        return {"nodes": await asyncio.to_thread(Nodes(data).list_nodes)}
    if action == "nodes.scan":
        return await Nodes(data).scan_host_key(values["host"], int(values.get("port", 22)))
    if action == "nodes.execute":
        command = str(values.get("command", "")).strip()
        if not command:
            raise ValueError("A command is required")
        timeout = int(values.get("timeout", 120))
        if not 1 <= timeout <= 3600:
            raise ValueError("Command timeout must be between 1 and 3600 seconds")
        result = await Nodes(data).execute_command(values["id"], command, timeout=timeout)
        return {**result.to_dict(), "output": "\n".join(part for part in (result.output, result.connection_warning) if part)}
    if action == "nodes.test":
        return {"output": await Nodes(data).execute(values["id"], 'printf "SSH connection ready"')}
    if action in {"nodes.job", "nodes.stop"}:
        return {"job": await Nodes(data).inspect_job(values["id"], stop=action == "nodes.stop")}
    if action in {"skills.validate", "skills.history"}:
        return await asyncio.to_thread(inspect_skill, values["name"], action.split(".")[1])
    if action.startswith("memory."):
        from cirno_memory.repository import MemoryRepository
        def memory_action():
            repo = MemoryRepository(get_home_path())
            repo.sync_profiles()
            if action in {"memory.list", "memory.graph"}:
                from cirno_core.config.loader import load_config
                from cirno_memory.graph import DEFAULT_GRAPH_NODES, graph_ids, graph_node_limit, memory_graph
                from cirno_memory.search import search
                max_nodes = graph_node_limit(values.get("max_nodes", DEFAULT_GRAPH_NODES)) if action == "memory.graph" else DEFAULT_GRAPH_NODES
                ids = graph_ids(values.get("ids", []), max_nodes=max_nodes) if action == "memory.graph" else []
                limit = int(values.get("limit", 10))
                if action == "memory.graph":
                    if len(ids) == max_nodes:
                        raise ValueError("Graph is full; narrow the filters to explore other memories")
                    limit = min(limit, max_nodes - len(ids))
                config = load_config()
                result = search(repo, str(values.get("query", "")), config.agents.defaults.memory,
                                   mode=str(values.get("mode", "bm25")), maintenance=True,
                                   scope=values.get("scope"), layer=values.get("layer"), tags=values.get("tags"),
                                   include_history=bool(values.get("include_history")),
                                   since=values.get("since"), until=values.get("until"), time_field=values.get("time_field", "observed_at"), time_zone=values.get("time_zone") or config.agents.defaults.timezone,
                                   limit=limit, offset=int(values.get("offset", 0)))
                if action == "memory.graph":
                    ids = list(dict.fromkeys([*ids, *(record["id"] for record in result["memories"])]))
                    result.update(memory_graph(repo, ids, maintenance=True, max_nodes=max_nodes))
                return result
            if action == "memory.status":
                from cirno_core.memory.consolidation_receipts import outcomes
                return {**repo.status(), **repo.receipts(limit=6), **outcomes(repo)}
            if action == "memory.tags":
                return repo.list_tags(maintenance=True, prefix=str(values.get("prefix", "")), limit=int(values.get("limit", 30)), offset=int(values.get("offset", 0)))
            if action == "memory.read":
                return repo.read(values["id"], revision=values.get("revision"), maintenance=True)
            if action == "memory.history":
                return {"revisions": repo.history(values["id"], maintenance=True)}
            if action == "memory.source":
                return repo.read_source(values["id"], revision=values.get("revision"), start_line=int(values.get("start_line", 1)),
                                        char_offset=int(values.get("char_offset", 0)), limit=5, maintenance=True)
            if action == "memory.reindex":
                return repo.reconcile(rebuild=True, limit=100)
            if action == "memory.retry":
                from cirno_core.memory.consolidation_receipts import retry_learning
                return retry_learning(repo)
            raise ValueError("Unknown memory action")
        result = await asyncio.to_thread(memory_action)
        if action in {"memory.list", "memory.graph"} and sessions is not None:
            titles = {}
            projects = {}
            for record in result["memories"]:
                if record["scope"] == "user":
                    continue
                key = record.get("session_key")
                if key and key not in titles:
                    metadata = await sessions.state.read_metadata(key)
                    titles[key] = (metadata or {}).get("metadata", {}).get("title") or key
                project = record.get("project_id") if record["scope"] == "project" else None
                if project and project not in projects:
                    try:
                        projects[project] = (await asyncio.to_thread(data.get, "projects", project))["name"]
                    except KeyError:
                        projects[project] = project
                record["owner_title"] = " / ".join(value for value in (projects.get(project), titles.get(key)) if value)
        return result
    raise ValueError("Unknown instance action")
