import { expect, it, vi } from "vitest";
import { ThreadTranscript } from "@/lib/thread-transcript";
import type { ThreadProjectionEvent } from "@/lib/contracts/events";
import { createStreamClient } from "./stream-client";

function transcript() {
  const thread = new ThreadTranscript();
  let id = 0;
  function receive(event: ThreadProjectionEvent) {
    thread.project(event, { createId: () => `row-${++id}`, now: 1000 });
  }
  receive({ event: "user_message", chat_id: "chat", turn_id: "old", text: "Old question", starts_turn: true });
  receive({ event: "delta", chat_id: "chat", turn_id: "old", text: "Old answer" });
  return { thread, receive };
}

it.each([false, true])("keeps the current answer open after a late old completion (already closed: %s)", closed => {
  const { thread, receive } = transcript();
  if (closed) receive({ event: "turn_end", chat_id: "chat", turn_id: "old", turn_seq: 3 });
  receive({ event: "user_message", chat_id: "chat", turn_id: "new", text: "New question", starts_turn: true });
  receive({ event: "delta", chat_id: "chat", turn_id: "new", stream_id: "answer", text: "New answer" });
  const active = thread.projection.activeAssistantId;
  receive({ event: "turn_end", chat_id: "chat", turn_id: "old", turn_seq: 9, latency_ms: 17 });
  expect(thread.projection.activeAssistantId).toBe(active);
  expect(thread.messages.find(row => row.id === active)?.isStreaming).toBe(true);
  expect(thread.messages.find(row => row.turnId === "new" && row.role === "assistant")?.latencyMs).toBeUndefined();
  expect(thread.messages.find(row => row.turnId === "old" && row.role === "assistant")?.latencyMs).toBe(17);
  receive({ event: "delta", chat_id: "chat", turn_id: "new", stream_id: "answer", text: " continues" });
  expect(thread.messages.filter(row => row.turnId === "new" && row.role === "assistant")).toHaveLength(1);
  expect(thread.messages.at(-1)?.content).toBe("New answer continues");
  receive({ event: "turn_end", chat_id: "chat", turn_id: "new" });
  expect(thread.messages.at(-1)?.isStreaming).not.toBe(true);
});

it("keeps current reasoning open when an older turn completes", () => {
  const { thread, receive } = transcript();
  receive({ event: "user_message", chat_id: "chat", turn_id: "new", text: "New question", starts_turn: true });
  receive({ event: "reasoning_delta", chat_id: "chat", turn_id: "new", stream_id: "thought", text: "Thinking" });
  receive({ event: "turn_end", chat_id: "chat", turn_id: "old" });
  expect(thread.messages.at(-1)?.reasoningStreaming).toBe(true);
  receive({ event: "reasoning_delta", chat_id: "chat", turn_id: "new", stream_id: "thought", text: " more" });
  expect(thread.messages.at(-1)?.reasoning).toBe("Thinking more");
});

it("retains current closed-wire fences when an older turn completes", () => {
  const { thread, receive } = transcript();
  receive({ event: "user_message", chat_id: "chat", turn_id: "new", text: "New question", starts_turn: true });
  receive({ event: "delta", chat_id: "chat", turn_id: "new", stream_id: "answer", text: "Final" });
  receive({ event: "stream_end", chat_id: "chat", turn_id: "new", stream_id: "answer", text: "Final" });
  const fences = [...thread.projection.closedAnswerStreamIds];
  expect(fences).toHaveLength(1);
  receive({ event: "turn_end", chat_id: "chat", turn_id: "old" });
  expect([...thread.projection.closedAnswerStreamIds]).toEqual(fences);
  receive({ event: "delta", chat_id: "chat", turn_id: "new", stream_id: "answer", text: " duplicate" });
  expect(thread.messages.at(-1)?.content).toBe("Final");
});

it("still finalizes legacy uncorrelated completions", () => {
  const { thread, receive } = transcript();
  receive({ event: "turn_end", chat_id: "chat" });
  expect(thread.projection.activeAssistantId).toBeNull();
  expect(thread.messages.at(-1)?.isStreaming).not.toBe(true);
});

it("keeps the current tool-activity segment when an older turn completes", () => {
  const { thread, receive } = transcript();
  receive({ event: "user_message", chat_id: "chat", turn_id: "new", text: "New question", starts_turn: true });
  receive({ event: "message", chat_id: "chat", turn_id: "new", kind: "progress", text: "Checking" });
  const segment = thread.projection.activitySegmentId;
  expect(segment).not.toBeNull();
  receive({ event: "turn_end", chat_id: "chat", turn_id: "old" });
  expect(thread.projection.activitySegmentId).toBe(segment);
  receive({ event: "message", chat_id: "chat", turn_id: "new", kind: "progress", text: "Checked" });
  expect(thread.projection.activitySegmentId).toBe(segment);
});

it("still completes new content from a legacy gateway that reuses a closed turn ID", () => {
  const { thread, receive } = transcript();
  receive({ event: "turn_end", chat_id: "chat", turn_id: "old" });
  receive({ event: "delta", chat_id: "chat", turn_id: "old", stream_id: "next", text: "Another answer" });
  const alias = thread.messages.at(-1)?.turnId;
  expect(alias).not.toBe("old");
  expect(thread.messages.at(-1)?.isStreaming).toBe(true);
  receive({ event: "turn_end", chat_id: "chat", turn_id: "old" });
  expect(thread.messages.at(-1)?.isStreaming).not.toBe(true);
  expect(thread.projection.activeAssistantId).toBeNull();
  expect(thread.projection.turnAliases.size).toBe(0);
});

it("keeps the real transport's existing old-completion fence and goal snapshot", () => {
  const { client, receive } = createStreamClient();
  const event = vi.fn();
  const unsubscribe = client.onChat("chat", event);
  try {
    receive({ event: "goal_status", chat_id: "chat", turn_id: "old", status: "running", started_at: 1 });
    receive({ event: "goal_status", chat_id: "chat", turn_id: "new", status: "running", started_at: 2 });
    receive({ event: "goal_state", chat_id: "chat", goal_state: { active: true, status: "active" } });
    event.mockClear();
    receive({ event: "turn_end", chat_id: "chat", turn_id: "old", goal_state: { active: false, status: "stopped" } });
    expect(client.getRunState("chat").active).toBe(true);
    expect(event).not.toHaveBeenCalled();
    expect(client.getGoalState("chat")).toEqual({ active: true, status: "active" });
    receive({ event: "turn_end", chat_id: "chat", turn_id: "new" });
    expect(event).toHaveBeenCalledTimes(1);
    expect(client.getRunState("chat").active).toBe(false);
  } finally { unsubscribe(); client.close(); }
});
