"""Optional PTC transport over the existing tool execution pipeline."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from cirno.agent.tools.base import Tool, ToolResult
from cirno.agent.tools.registry import ToolRegistry

Dispatch = Callable[[str, dict[str, Any], int], Awaitable[tuple[Any, bool]]]


class RunCodeTool(Tool):
    _plugin_discoverable = False
    name = "run_code"
    description = (
        "Execute a Python async function body to orchestrate tools and filter their results. "
        "Use await tools.name({...}) or await tools.name(key=value). Only print/return output "
        "is returned to the model; tool calls still appear in the execution log. "
        "Use await gather(...) for independent read-only calls, loops and conditions for dependent work. "
        "No file/network/process access or private attributes. Only json/math imports are supported. Built-ins, json.loads/dumps, "
        "math, gather and sleep are provided. Each call starts fresh; state does not persist. "
        "Existing tool permissions apply. Failure may follow completed effects; inspect before retrying."
    )
    parameters = {"type": "object", "properties": {
        "code": {"type": "string", "minLength": 1, "maxLength": 32000},
        "description": {"type": "string", "description": "Short description in the user's language", "maxLength": 200},
        "timeout": {"type": "integer", "minimum": 1, "maximum": 120, "description": "Program deadline in seconds (default 60), including nested tool waits"},
    }, "required": ["code", "description"]}

    async def execute(self, **kwargs):
        return ToolResult.error("run_code must execute through the agent tool pipeline")

    async def run(self, code: str, dispatch: Dispatch, names: list[str], *, timeout: int = 60, **kwargs):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-S", "-u", str(Path(__file__).with_name("worker.py")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={key: value for key, value in os.environ.items() if key in {"SYSTEMROOT", "WINDIR"}},
            limit=4 * 1024 * 1024 + 1,
        )
        tasks: set[asyncio.Task] = set()
        assert process.stdin and process.stdout

        async def handle(frame):
            try:
                try:
                    result, error = await dispatch(frame["name"], frame["arguments"], frame["id"])
                except Exception as exc:
                    result, error = f"{type(exc).__name__}: {exc}", True
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except (ValueError, TypeError):
                        pass  # Plain-text tools retain their text result.
                reply = {"id": frame["id"], "error": str(result)} if error else {"id": frame["id"], "result": result}
                encoded = (json.dumps(reply, ensure_ascii=True, default=str, allow_nan=False) + "\n").encode()
                if len(encoded) > 4 * 1024 * 1024:
                    encoded = (json.dumps({"id": frame["id"], "error": "Tool response exceeds 4 MiB; use a bounded query"}) + "\n").encode()
                process.stdin.write(encoded)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass  # Program ended or was stopped while this call settled.

        try:
            async with asyncio.timeout(timeout):
                process.stdin.write((json.dumps({"code": code, "tools": names}) + "\n").encode())
                await process.stdin.drain()
                calls = 0
                while line := await process.stdout.readline():
                    frame = json.loads(line)
                    if frame.get("type") == "done":
                        output = frame.get("output", "")
                        if frame.get("error"):
                            return ToolResult.error(f"{output}\n{frame['error']}\nEarlier tool effects may have completed; do not replay blindly.")
                        return output or "Program completed without printed output."
                    if frame.get("type") != "call" or calls >= 64:
                        return ToolResult.error("Invalid or excessive PTC tool calls")
                    calls += 1
                    task = asyncio.create_task(handle(frame))
                    tasks.add(task)
                detail = (await process.stderr.read(4096)).decode("utf-8", errors="replace").strip() if process.stderr else ""
                return ToolResult.error("PTC worker exited before returning a result" + (f": {detail}" if detail else ""))
        except TimeoutError:
            return ToolResult.error("PTC deadline exceeded. Earlier tool effects may have completed; inspect before retrying.")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            process.stdin.close()
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass  # Child exited between the status check and kill.
            await process.wait()


class PtcToolRegistry(ToolRegistry):
    """Expose only run_code; retain the already-filtered registry for subcalls."""
    def __init__(self, native: ToolRegistry):
        super().__init__()
        self.native = native
        self.register(RunCodeTool())

    def sdk_prompt(self) -> str:
        declarations = [schema["function"] for schema in self.native.get_definitions()]
        declarations = [{**item, "name": item["name"].replace("__", ".")} for item in declarations]
        delivery = (
            "To communicate with the user, await tools.user.message(content=...) inside ptc__run. "
            if self.native.has("message") else
            "Reply to the user with normal assistant text. user.message is not available in this regular conversation. "
        )
        return (
            "PTC Mode is enabled for this conversation. ptc__run is the only directly callable tool. "
            "Call the tools below from Python as await tools.group.operation({...}) or named arguments. "
            "Tool results are parsed JSON when possible, otherwise strings. "
            "Use print/return to keep only relevant results. Catch ToolError to handle a rejected subcall. "
            "Independent read-only calls may use await gather(...); execute dependent or mutating calls sequentially. "
            + delivery
            + "To ask asynchronously, use tools.user.ask. Goal and permission rules still apply.\n"
            "Available tool declarations (name, description, parameters):\n"
            + json.dumps(declarations, ensure_ascii=False, separators=(",", ":"))
        )


class PtcCallGate:
    """Honor native concurrency safety: up to four reads, exclusive mutations."""
    def __init__(self):
        self.condition = asyncio.Condition()
        self.active = 0
        self.exclusive = False
        self.waiting_exclusive = 0

    @asynccontextmanager
    async def enter(self, parallel: bool):
        async with self.condition:
            if not parallel:
                self.waiting_exclusive += 1
            try:
                await self.condition.wait_for(lambda: not self.exclusive and (
                    self.active < 4 and not self.waiting_exclusive if parallel else self.active == 0
                ))
                self.active += 1
                self.exclusive = not parallel
            finally:
                if not parallel:
                    self.waiting_exclusive -= 1
        try:
            yield
        finally:
            async with self.condition:
                self.active -= 1
                self.exclusive = False
                self.condition.notify_all()
