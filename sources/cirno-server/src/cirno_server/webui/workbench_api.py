"""Authenticated workstation operations; terminal input is owner input, not an LLM tool."""

from __future__ import annotations

import asyncio

from cirno_core.credentials.service import Credentials

from cirno_server.webui.terminals import Terminals
from cirno_server.webui.trace_api import TraceAPI


class WorkbenchAPI:
    def __init__(self, workspaces, sessions):
        self.workspaces, self.sessions = workspaces, sessions
        self.terminals = Terminals()

    async def action(self, payload: dict) -> dict:
        action = payload.get("action", "")
        values = payload.get("values") or {}
        if not isinstance(values, dict):
            raise ValueError("Invalid workbench operation")
        if action.startswith("terminal."):
            operation = action.removeprefix("terminal.")
            if operation == "create":
                return await self.terminals.create(
                    cwd=values.get("cwd") or str(self.workspaces.default_scope().project_path),
                    node_id=values.get("node_id"),
                    cols=values.get("cols", 100),
                    rows=values.get("rows", 30),
                    key=values.get("key"),
                )
            identifier = values["id"]
            if operation == "read":
                return self.terminals.read(identifier, values.get("cursor", 0))
            if operation == "write":
                return await self.terminals.write(identifier, values.get("data", ""))
            if operation == "resize":
                return self.terminals.resize(
                    identifier, values.get("cols", 100), values.get("rows", 30)
                )
            if operation == "close":
                return await self.terminals.close(identifier)
        if action.startswith("credentials."):
            vault = await asyncio.to_thread(Credentials)
            operation = action.removeprefix("credentials.")
            if operation == "list":
                return await asyncio.to_thread(vault.list)
            if operation == "save":
                return await asyncio.to_thread(vault.save, **values)
            if operation == "describe":
                return await asyncio.to_thread(vault.describe, values["id"])
            if operation == "reveal":
                return await asyncio.to_thread(vault.reveal, values["id"])
            if operation == "delete":
                return await asyncio.to_thread(vault.delete, values["id"])
        if action.startswith("trace."):
            return await TraceAPI().action(action.removeprefix("trace."), values)
        raise ValueError("Unknown workbench operation")
