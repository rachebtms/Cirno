"""Project operations shared by authenticated UI actions and Cirno tools."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from cirno_core.bus.outbound_events import SessionUpdatedEvent, outbound_message_for_event
from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY
from cirno_core.storage.instance import InstanceData
from cirno_core.utils.cancellation import shield_and_drain

if TYPE_CHECKING:
    from cirno_core.bus.queue import MessageBus
    from cirno_core.session.manager import SessionManager


class Projects:
    def __init__(self, sessions: SessionManager, data: InstanceData | None = None):
        self.sessions = sessions
        self.data = data if data is not None else InstanceData()
        self._lock = asyncio.Lock()

    async def action(self, action: str, values: dict, *, bus: MessageBus | None = None) -> dict:
        # A cancelled request must not abandon membership cleanup halfway through.
        return await shield_and_drain(self._action(action, values, bus))

    async def open_conversation(self, key: str, metadata: dict[str, Any], project_id: str | None) -> None:
        """Persist membership under the same owner as Project deletion."""
        await shield_and_drain(self._open_conversation(key, metadata, project_id))

    async def _open_conversation(self, key: str, metadata: dict[str, Any], project_id: str | None) -> None:
        async with self._lock:
            if project_id is not None:
                if not isinstance(project_id, str) or not project_id.strip():
                    raise ValueError("Project ID must be nonempty text or null")
                if key == ROUTER_SESSION_KEY:
                    raise ValueError("The Router conversation cannot belong to a Project")
                try:
                    await asyncio.to_thread(self.data.get, "projects", project_id)
                except KeyError as error:
                    raise ValueError("Project not found") from error
            await self.sessions.state.open_with_metadata(key, {**metadata, "project_id": project_id})

    async def _action(self, action: str, values: dict, bus: MessageBus | None) -> dict:
        async with self._lock:
            if action == "list":
                return {"projects": await asyncio.to_thread(self.data.list, "projects")}
            if action == "get":
                project = await asyncio.to_thread(self.data.get, "projects", values["id"])
                rows = await self.sessions.state.list_metadata()
                return {"project": project, "conversations": [
                    {"session_key": row["key"], "title": row["metadata"].get("title", ""),
                     "handle": row["metadata"].get("session_handle")}
                    for row in rows if row["metadata"].get("project_id") == project["id"]
                ]}
            if action in {"create", "update", "save"}:
                project = await self._save(action, values)
                result = {"project": project, "projects": await asyncio.to_thread(self.data.list, "projects")}
            elif action == "assign":
                await self._assign(values)
                result = {"ok": True}
            elif action == "delete":
                await self._delete(values["id"])
                result = {"projects": await asyncio.to_thread(self.data.list, "projects")}
            else:
                raise ValueError(f"Unknown Project action: {action}")
            if bus is not None:
                await bus.publish_outbound(outbound_message_for_event(
                    channel="websocket", chat_id=ROUTER_CHAT_ID,
                    event=SessionUpdatedEvent(scope="projects"), metadata={},
                ))
            return result

    async def _save(self, action: str, values: dict) -> dict:
        identifier = values.get("id")
        if action == "update" and not identifier:
            raise ValueError("A Project ID is required to update a Project")
        if action == "create" and identifier:
            raise ValueError("Creating a Project does not accept an existing ID")
        record = await asyncio.to_thread(self.data.get, "projects", identifier) if identifier else {}
        for field, maximum in (("name", 120), ("description", 4000), ("working_directory", 4096)):
            value = values.get(field, record.get(field, ""))
            if not isinstance(value, str):
                raise ValueError(f"Project {field} must be text")
            value = value.strip()
            if len(value) > maximum or (field == "name" and not value):
                raise ValueError(f"Project {field} must contain {'1' if field == 'name' else '0'}–{maximum} characters")
            record[field] = value
        return await asyncio.to_thread(self.data.save, "projects", record)

    async def _assign(self, values: dict) -> None:
        identifier = values.get("project_id")
        if identifier:
            await asyncio.to_thread(self.data.get, "projects", identifier)
        key = values["session_key"]
        if key == ROUTER_SESSION_KEY:
            raise ValueError("The Router conversation cannot belong to a Project")
        header = await self.sessions.state.read_header(key)
        if header is None:
            raise KeyError("Conversation not found")
        await self.sessions.state.mutate_metadata(
            key, lambda metadata: metadata.update(project_id=identifier or None),
            expected_generation=header.generation,
        )

    async def _delete(self, identifier: str) -> None:
        await asyncio.to_thread(self.data.get, "projects", identifier)
        for row in await self.sessions.state.list_metadata():
            if row["metadata"].get("project_id") == identifier:
                await self._assign({"session_key": row["key"], "project_id": None})
        await asyncio.to_thread(self.data.delete, "projects", identifier)
