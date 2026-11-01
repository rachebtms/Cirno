# Programmatic tool calling and reply delivery

PTC lets a model combine tool calls and filter their results inside a bounded Python program. It uses Cirno's existing Python runtime, with no additional model or persistent interpreter. The design follows the separation between a program executor and the existing tool pipeline used in DeepSeek Harness; Cirno's implementation lives in `agent/ptc/`.

## Enable PTC

PTC is off by default. Enable the `</>` option in the new-conversation header. The mode is saved per conversation across refreshes and gateway restarts. Temporary conversations retain it only for their existing in-memory lifetime. An existing conversation displays its mode; the mode is not changed during execution.

The model directly receives only `ptc__run(code, description, timeout?)`, plus the available tool SDK. Programs are asynchronous Python function bodies with top-level `await` and `return`:

```python
results = await gather(
    tools.files.list(path="."),
    tools.files.list(path="notes"),
)
print(results)
```

Nested calls use the same conversation-specific tool selection, schemas, permissions, execution hooks and MCP allowlists as native calls. JSON tool results become JSON values; other results remain text. Tool failures raise `ToolError`. Only printed output and the return value enter the model's program result; individual calls retain their own activity records, arguments, results, errors and IDs.

## Execution limits

Each program starts a disposable subprocess; Python variables do not persist between programs. The language provides selected computation builtins, JSON, selected math functions, `gather` and `sleep`, with `import json` and `import math` supported. Other imports, private attributes, reflection and direct file, network or process APIs are excluded. External operations go through Cirno tools. This restricted language does not replace those tools' permission checks.

A program allows up to 64 nested calls. At most four safe read-only calls execute together; other calls execute exclusively. The default deadline is 60 seconds and the maximum is 120 seconds. Output is capped at 16,000 characters and a tool RPC at 4 MiB. Linux workers have a 128 MiB address-space limit. There is no idle PTC worker.

Stop, timeout and outer cancellation cancel unfinished calls and reap the worker. A failed program is not automatically replayed. Completed modifications are not rolled back when a later step fails.

## Reply contracts

Ordinary conversations receive `regular_conversation.md` and reply through ordinary streamed assistant text. Their tool selection excludes `user.message`, including in the PTC SDK. The server also rejects attempts to invoke that tool through a historical implementation name. `user.ask` remains available for non-blocking questions.

The Cirno coordination conversation receives `cirno_conversation.md`. It sends visible replies and attachments through `user.message`; ordinary assistant output is internal execution history, collapsed by default. In PTC it calls `tools.user.message(...)` inside the program. A reply segment already delivered by that tool is not streamed again as a second reply. A later steering input starts a new reply segment.

Historical display cleanup only hides a confirmed duplicate terminal snapshot in the same turn when a message-tool call and actual delivery establish that the same text was already sent. It does not merge identical text across unrelated turns or rewrite raw stored evidence.
