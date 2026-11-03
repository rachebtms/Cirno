import { expect, it } from "vitest";
import { liveContextUsage, visibleContextTokens } from "@/lib/live-context";
import type { UIMessage } from "@/lib/types";

it("updates an explicitly estimated context during reasoning and tool output", () => {
  const base = { contextTokens: 1000, contextWindowTokens: 8000 };
  const old: UIMessage = { id: "old", role: "assistant", content: "done", createdAt: 1, usage: { context_tokens: 1000 } };
  const reasoning: UIMessage = { id: "live", role: "assistant", content: "", reasoning: "Planning. ".repeat(30), isStreaming: true, createdAt: 2 };
  const first = liveContextUsage(base, [old, reasoning], true)!;
  const tools: UIMessage = { id: "tools", role: "tool", kind: "trace", content: "", createdAt: 3,
    toolEvents: [{ phase: "end", name: "nodes__execute", arguments: { command: "python experiment.py" }, result: "output\n".repeat(100) }] };
  const second = liveContextUsage(base, [old, { ...reasoning, reasoning: reasoning.reasoning + " More thought." }, tools], true)!;
  expect(first.contextTokens).toBeGreaterThan(1000);
  expect(second.contextTokens).toBeGreaterThan(first.contextTokens);
  expect(second.estimated).toBe(true);
  expect(liveContextUsage({ ...base, contextTokens: 1400 }, [], false)).toEqual({ ...base, contextTokens: 1400 });
});

it("adds only output generated after a fresh measurement and resets after compaction", () => {
  const messages: UIMessage[] = [{ id: "live", role: "assistant", createdAt: 1, content: "", reasoning: "Thought" }];
  const measured = visibleContextTokens(messages);
  expect(liveContextUsage({ contextTokens: 50 }, messages, true, measured)?.contextTokens).toBe(50);
  const compact: UIMessage = { id: "compact", role: "assistant", content: "", createdAt: 2, kind: "compaction", compaction: { id: "c", phase: "succeeded", context_tokens: 10 } };
  expect(liveContextUsage({ contextTokens: 10 }, [...messages, compact], true)?.contextTokens).toBe(10);
});
