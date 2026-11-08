"""One-shot, dependency-free Python computation worker for PTC.

No application imports or credentials enter this process. Programs use a small
Python subset; all external effects go through the parent's guarded tool RPC.
"""
from __future__ import annotations

import ast
import asyncio
import builtins
import json
import math
import sys
from types import SimpleNamespace

MAX_OUTPUT = 16000
MAX_FRAME = 4 * 1024 * 1024


def send(frame):
    sys.stdout.write(json.dumps(frame, ensure_ascii=True, allow_nan=False) + "\n")
    sys.stdout.flush()


def validate(code):
    class ModuleAliases(ast.NodeTransformer):
        def visit_Import(self, node):
            statements = []
            for alias in node.names:
                if alias.name not in {"json", "math"} or (alias.asname and alias.asname.startswith("_")):
                    raise ValueError("Imports are limited to the provided json and math helpers")
                statements.append(ast.Assign(targets=[ast.Name(id=alias.asname or alias.name, ctx=ast.Store())],
                                             value=ast.Name(id=alias.name, ctx=ast.Load())))
            return statements

    tree = ModuleAliases().visit(ast.parse(code, mode="exec"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.ImportFrom, ast.ClassDef, ast.Global, ast.Nonlocal)):
            raise ValueError("Imports, classes and global/nonlocal declarations are unavailable in PTC")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Private names are unavailable in PTC")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in {"format", "format_map"}):
            raise ValueError("Private attributes and string format methods are unavailable; use f-strings")
        if isinstance(node, ast.ExceptHandler) and node.name and node.name.startswith("__"):
            raise ValueError("Private names are unavailable in PTC")
        if isinstance(node, ast.arg) and node.arg.startswith("__"):
            raise ValueError("Private names are unavailable in PTC")
    return tree


async def main(payload):
    loop = asyncio.get_running_loop()
    pending = {}
    output = []
    output_size = 0
    sequence = 0

    async def read_replies():
        while True:
            line = await asyncio.to_thread(sys.stdin.readline, MAX_FRAME + 1)
            if not line:
                for future in pending.values():
                    if not future.done():
                        future.set_exception(RuntimeError("PTC host disconnected"))
                return
            if len(line) > MAX_FRAME:
                raise ValueError("Tool response exceeded PTC transport limit")
            reply = json.loads(line)
            future = pending.pop(reply["id"], None)
            if future is not None:
                if reply.get("error"):
                    future.set_exception(ToolError(reply["error"]))
                else:
                    future.set_result(reply.get("result"))

    class Tools:
        def __init__(self, prefix=""):
            self.prefix = prefix

        def __getattr__(self, name):
            name = self.prefix + name
            if any(tool.startswith(name + "__") for tool in payload["tools"]):
                return Tools(name + "__")
            if name not in payload["tools"]:
                raise ValueError(f"Tool {name!r} is not available")

            async def call(args=None, **kwargs):
                nonlocal sequence
                if args is not None and kwargs:
                    raise ValueError("Use one argument object or named arguments")
                params = args if args is not None else kwargs
                if not isinstance(params, dict):
                    raise ValueError("Tool arguments must be an object")
                sequence += 1
                if sequence > 64:
                    raise ValueError("PTC permits at most 64 tool calls per program")
                identity = sequence
                future = loop.create_future()
                pending[identity] = future
                send({"type": "call", "id": identity, "name": name, "arguments": params})
                return await future
            return call

    def emit(*values, sep=" ", end="\n"):
        nonlocal output_size
        text = sep.join(str(value) for value in values) + end
        output_size += len(text)
        if output_size > MAX_OUTPUT:
            raise ValueError("PTC output exceeds 16000 characters; filter or summarize before printing")
        output.append(text)

    tree = validate(payload["code"])
    # An async function body gives programs top-level await and return.
    function = ast.AsyncFunctionDef(name="program", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
                                   body=tree.body or [ast.Pass()], decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    names = ("abs all any bool dict enumerate filter float int isinstance len list map max min next pow range repr reversed round set sorted str sum tuple zip Exception ValueError KeyError TypeError RuntimeError").split()
    namespace = {
        "__builtins__": {name: getattr(builtins, name) for name in names},
        "tools": Tools(), "print": emit, "gather": asyncio.gather, "sleep": asyncio.sleep,
        "json": SimpleNamespace(loads=json.loads, dumps=json.dumps),
        "math": SimpleNamespace(**{name: getattr(math, name) for name in ("ceil", "floor", "sqrt", "log", "exp", "isfinite", "pi")}),
        "ToolError": ToolError,
    }
    reader = asyncio.create_task(read_replies())
    try:
        exec(compile(module, "<ptc>", "exec"), namespace)
        value = await namespace["program"]()
        if value is not None:
            emit(json.dumps(value, ensure_ascii=False, allow_nan=False))
        send({"type": "done", "output": "".join(output)})
    except Exception as exc:
        send({"type": "done", "output": "".join(output), "error": f"{type(exc).__name__}: {exc}"})
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)


class ToolError(Exception):
    pass


if __name__ == "__main__":
    try:
        # Linux enforces a worker-only memory ceiling. No heavyweight runtime is loaded.
        if sys.platform == "linux":
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
        payload = json.loads(sys.stdin.readline(MAX_FRAME + 1))
        asyncio.run(main(payload))
    except Exception as exc:
        send({"type": "done", "error": f"{type(exc).__name__}: {exc}", "output": ""})
