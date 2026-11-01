"""Authenticated instance features shared by settings and conversation tools."""

from __future__ import annotations

import asyncio

from cirno.storage.instance import InstanceData
from cirno.nodes.service import Nodes
from cirno.skills.history import inspect_skill

from cirno.session.keys import CIRNO_SESSION_KEY

GLOBAL_SESSION_KEY = CIRNO_SESSION_KEY


async def ensure_global_session(sessions):
    session = await sessions.state.get(GLOBAL_SESSION_KEY)
    if not session.metadata.get("is_global") or session.metadata.get("title") != "Cirno":
        await sessions.state.update_metadata(GLOBAL_SESSION_KEY, {"is_global": True, "title": "Cirno", "webui": True})
    return GLOBAL_SESSION_KEY


async def instance_action(
    payload: dict, *, sessions, bus
) -> dict:
    data = InstanceData()
    action = payload.get("action", "")
    values = payload.get("values") or {}
    if action.startswith("telegram."):
        from cirno.channels.telegram.binding import TelegramBinding
        binding = TelegramBinding()
        if action == "telegram.status":
            return binding.status()
        if action == "telegram.pin":
            return binding.issue_pin()
        if action == "telegram.settings":
            return binding.update(values)
        if action == "telegram.unbind":
            return binding.unbind()
        raise ValueError("Unknown Telegram binding action")
    if action.startswith("inbox."):
        from cirno.notifications.inbox import NotificationInbox
        inbox = NotificationInbox()
        if action == "inbox.list":
            await asyncio.to_thread(inbox.sync_pairing)
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
    if action == "bootstrap":
        key = await ensure_global_session(sessions)
        return {
            "projects": await asyncio.to_thread(data.list, "projects"),
            "global_session_key": key,
        }
    if action == "projects.list":
        return {"projects": await asyncio.to_thread(data.list, "projects")}
    if action == "projects.save":
        name = str(values.get("name", "")).strip()
        if not name or len(name) > 120:
            raise ValueError("Project name must contain 1–120 characters")
        if values.get("id"):
            data.get("projects", values["id"])
        project = data.save(
            "projects",
            {
                "id": values.get("id"),
                "name": name,
                "description": str(values.get("description", ""))[:4000],
                "working_directory": str(values.get("working_directory", "")).strip(),
            },
        )
        return {"project": project, "projects": data.list("projects")}
    if action == "projects.assign":
        project_id = values.get("project_id")
        if project_id:
            data.get("projects", project_id)
        key = values["session_key"]
        if key == GLOBAL_SESSION_KEY:
            raise ValueError("The global conversation cannot belong to a project")
        if await sessions.state.read_metadata(key) is None:
            raise KeyError("Conversation not found")
        await sessions.state.update_metadata(key, {"project_id": project_id})
        return {"ok": True}
    if action == "projects.delete":
        project_id = values["id"]
        data.get("projects", project_id)
        for row in await asyncio.to_thread(sessions.list_session_metadata):
            if row["metadata"].get("project_id") == project_id:
                await sessions.state.update_metadata(row["key"], {"project_id": None})
        data.delete("projects", project_id)
        return {"projects": data.list("projects")}
    if action == "nodes.list":
        return {"nodes": Nodes(data).list_nodes(), "jobs": data.list("node_jobs")}
    if action == "nodes.save":
        node = Nodes(data).save_node(values)
        return {"node": node, "nodes": Nodes(data).list_nodes()}
    if action == "nodes.delete":
        if any(
            job["node_id"] == values["id"]
            and job.get("state") in {"running", "submitting", "submission_unknown"}
            for job in data.list("node_jobs")
        ):
            raise ValueError("Stop or resolve this Node’s jobs before deleting its connection")
        data.delete("nodes", values["id"])
        return {"nodes": Nodes(data).list_nodes()}
    if action == "nodes.scan":
        return await Nodes(data).scan_host_key(values["host"], int(values.get("port", 22)))
    if action == "nodes.execute":
        command = str(values.get("command", "")).strip()
        if not command:
            raise ValueError("A command is required")
        timeout = int(values.get("timeout", 120))
        if not 1 <= timeout <= 3600:
            raise ValueError("Command timeout must be between 1 and 3600 seconds")
        return {"output": await Nodes(data).execute(values["id"], command, timeout=timeout)}
    if action == "nodes.test":
        return {"output": await Nodes(data).execute(values["id"], 'printf "SSH connection ready"')}
    if action in {"nodes.job", "nodes.stop"}:
        return {"job": await Nodes(data).inspect_job(values["id"], stop=action == "nodes.stop")}
    if action in {"skills.validate", "skills.history"}:
        return await asyncio.to_thread(inspect_skill, values["name"], action.split(".")[1], data.home)
    if action.startswith("memory."):
        from cirno.memory.repository import MemoryRepository
        def memory_action():
            repo = MemoryRepository()
            repo.migrate_legacy()
            repo.sync_profiles()
            if action == "memory.list":
                from cirno.config.loader import load_config
                from cirno.memory.search import search
                config = load_config()
                return search(repo, str(values.get("query", "")), config.agents.defaults.memory,
                                   mode=str(values.get("mode", "bm25")), maintenance=True,
                                   scope=values.get("scope"), layer=values.get("layer"), tags=values.get("tags"),
                                   include_history=bool(values.get("include_history")),
                                   since=values.get("since"), until=values.get("until"), time_field=values.get("time_field", "observed_at"), time_zone=values.get("time_zone") or config.agents.defaults.timezone,
                                   limit=int(values.get("limit", 10)), offset=int(values.get("offset", 0)))
            if action == "memory.status":
                return {**repo.status(), **repo.receipts(limit=6)}
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
                return repo.retry_failed()
            raise ValueError("Unknown memory action")
        result = await asyncio.to_thread(memory_action)
        if action == "memory.list" and sessions is not None:
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
