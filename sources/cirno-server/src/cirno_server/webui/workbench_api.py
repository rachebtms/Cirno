"""Authenticated workstation operations; terminal input is owner input, not an LLM tool."""

from __future__ import annotations

import asyncio
from pathlib import Path

from cirno_core.config.loader import get_config_path
from cirno_core.credentials.service import Credentials
from cirno_core.storage.instance import InstanceData
from cirno_core.utils.cancellation import shield_and_drain

from cirno_server.webui.terminals import Terminals
from cirno_server.webui.trace_api import TraceAPI


class WorkbenchAPI:
    def __init__(self, workspaces, sessions, *, source_config_path: Path | None = None):
        self.workspaces, self.sessions = workspaces, sessions
        source = source_config_path if source_config_path is not None else get_config_path()
        self.state_dir = Path(source).expanduser().resolve(strict=False).parent / "state"
        self.terminals = Terminals(state_dir=self.state_dir)

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
            def credentials():
                vault = Credentials(InstanceData(self.state_dir))
                operation = action.removeprefix("credentials.")
                if operation == "list":
                    return vault.list()
                if operation == "save":
                    return vault.save(**values)
                if operation == "describe":
                    return vault.describe(values["id"])
                if operation == "reveal":
                    return vault.reveal(values["id"])
                if operation == "delete":
                    return vault.delete(values["id"])
                raise ValueError("Unknown workbench operation")
            return await shield_and_drain(asyncio.to_thread(credentials))
        if action.startswith("trace."):
            return await TraceAPI().action(action.removeprefix("trace."), values)
        raise ValueError("Unknown workbench operation")
