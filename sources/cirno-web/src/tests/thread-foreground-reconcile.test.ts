import { expect, it } from "vitest";
import { ThreadTranscript } from "@/lib/thread-transcript";
import type { ThreadProjectionEvent } from "@/lib/contracts/events";

function conversation() {
  const thread = new ThreadTranscript();
  let serial = 0;
  const receive = (...events: ThreadProjectionEvent[]) => events.forEach(event => thread.project(event, {
    createId: () => `received-${++serial}`, now: 100,
  }));
  return { thread, receive };
}

const reply: ThreadProjectionEvent = {
  event: "message", chat_id: "chat", turn_id: "turn", turn_seq: 2, text: "Inspection complete.",
};

it("renders a redelivered reply once while preserving distinct identical replies", () => {
  const { thread, receive } = conversation();
  receive(reply, reply);
  expect(thread.messages.map(row => row.content)).toEqual([reply.text]);
  receive({ ...reply, turn_seq: 3 });
  expect(thread.messages.map(row => row.content)).toEqual([reply.text, reply.text]);
  const restored = new ThreadTranscript([], thread.save());
  restored.project(reply, { createId: () => "reconnected", now: 200 });
  expect(restored.messages).toHaveLength(2);
});

it("does not duplicate an identified stream-end snapshot received again after its answer closed", () => {
  const { thread, receive } = conversation();
  const end: ThreadProjectionEvent = { event: "stream_end", chat_id: "chat", turn_id: "turn", turn_seq: 3, text: "Streamed reply" };
  receive({ event: "delta", chat_id: "chat", turn_id: "turn", turn_seq: 2, text: "Streamed reply" }, end, end);
  expect(thread.messages.map(row => row.content)).toEqual(["Streamed reply"]);
});

it("ignores a redelivered old reply without closing the current live answer", () => {
  const { thread, receive } = conversation();
  receive(reply,
    { event: "delta", chat_id: "chat", turn_id: "next-turn", turn_seq: 1, stream_id: "next-answer", text: "New" },
    reply,
    { event: "delta", chat_id: "chat", turn_id: "next-turn", turn_seq: 2, stream_id: "next-answer", text: " answer" });
  expect(thread.messages.map(row => row.content)).toEqual([reply.text, "New answer"]);
  expect(thread.messages.at(-1)?.isStreaming).toBe(true);
});

it("deduplicates an unsequenced reply by its explicit projection identity", () => {
  const { thread, receive } = conversation();
  const event: ThreadProjectionEvent = { event: "message", chat_id: "chat", projection_id: "delivery-one", text: "Report" };
  receive(event, event, { ...event, projection_id: "delivery-two" });
  expect(thread.messages.map(row => row.content)).toEqual(["Report", "Report"]);
});
