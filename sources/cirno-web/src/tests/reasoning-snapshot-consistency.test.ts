import { expect, it } from "vitest";
import { createThreadProjectionState, projectThreadEvent, projectThreadEvents } from "@/lib/thread-event-projection";
import type { ThreadProjectionEvent } from "@/lib/contracts/events";

it.each([false, true].flatMap(identified => ["", "Revised thought", "Provisional thought"].map(snapshot => ({ identified, snapshot }))))(
  "replaces current reasoning with final snapshot $snapshot (identified: $identified)", ({ identified, snapshot }) => {
    const identity = identified ? { stream_id: "reasoning" } : {};
    const events: ThreadProjectionEvent[] = [
      { event: "reasoning_delta", chat_id: "chat", turn_id: "turn", ...identity, text: "Provisional thought" },
      { event: "reasoning_end", chat_id: "chat", turn_id: "turn", ...identity, text: snapshot },
      { event: "turn_end", chat_id: "chat", turn_id: "turn" },
    ];
    let live = createThreadProjectionState();
    events.forEach(event => { live = projectThreadEvent(live, event, { createId: () => "live", now: 100 }); });
    expect(live.messages).toHaveLength(1);
    expect(live.messages[0]).toMatchObject({ reasoning: snapshot, reasoningStreaming: false, isStreaming: false });
    const replay = projectThreadEvents(events)[0];
    expect(replay.reasoning).toBe(snapshot);
    expect(replay.reasoningStreaming).not.toBe(true);
  });

it("does not interrupt an active answer for an empty reasoning snapshot without a matching stream", () => {
  let state = projectThreadEvent(createThreadProjectionState(), {
    event: "delta", chat_id: "chat", turn_id: "turn", stream_id: "answer", text: "Answer",
  }, { createId: () => "answer", now: 100 });
  state = projectThreadEvent(state, {
    event: "reasoning_end", chat_id: "chat", turn_id: "turn", stream_id: "unknown", text: "",
  }, { createId: () => "end", now: 100 });
  expect(state.messages).toHaveLength(1);
  expect(state.activeAssistantId).toBe("answer");
  expect(state.messages[0].content).toBe("Answer");
});

it("keeps accumulated reasoning when the end event omits a snapshot", () => {
  const messages = projectThreadEvents([
    { event: "reasoning_delta", chat_id: "chat", text: "Retained thought" },
    { event: "reasoning_end", chat_id: "chat" },
    { event: "turn_end", chat_id: "chat" },
  ]);
  expect(messages[0].reasoning).toBe("Retained thought");
  expect(messages[0].reasoningStreaming).not.toBe(true);
});

it.each([false, true])("keeps a late reasoning snapshot on its row after answer text begins (identified: %s)", identified => {
  const identity = identified ? { stream_id: "stream" } : {};
  const messages = projectThreadEvents([
    { event: "reasoning_delta", chat_id: "chat", turn_id: "turn", ...identity, text: "Provisional thought" },
    { event: "delta", chat_id: "chat", turn_id: "turn", ...identity, text: "Answer" },
    { event: "reasoning_end", chat_id: "chat", turn_id: "turn", ...identity, text: "Final thought" },
    { event: "delta", chat_id: "chat", turn_id: "turn", ...identity, text: " continues" },
    { event: "turn_end", chat_id: "chat", turn_id: "turn" },
  ]);
  expect(messages).toHaveLength(1);
  expect(messages[0]).toMatchObject({ content: "Answer continues", reasoning: "Final thought" });
});
