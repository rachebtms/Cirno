import { expect, it } from "vitest";
import { normalizeActivityTimeline } from "@/lib/activity-timeline";
import { projectThreadEvents } from "@/lib/thread-event-projection";
import type { ThreadProjectionEvent } from "@/lib/contracts/events";

const event = (phase: "start" | "end" | "error", call_id = "delivery"): ThreadProjectionEvent => ({
  event: "message", chat_id: "b1ec9323-2155-5f24-bc56-1da2f59aeecb", turn_id: "turn", kind: "tool_hint", text: "",
  tool_events: [{ call_id, name: "user.message", phase, arguments: { content: "Hello" },
    ...(phase === "end" ? { result: "Message sent to websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb" } : {}),
    ...(phase === "error" ? { error: "Delivery failed" } : {}),
  }],
});
const answer: ThreadProjectionEvent = {
  event: "message", chat_id: "b1ec9323-2155-5f24-bc56-1da2f59aeecb", turn_id: "turn", text: "Hello", render_as: "text",
};

it.each(["end", "error"] as const)("updates the first delivery row across its reply bubble on %s", phase => {
  const messages = projectThreadEvents([event("start"), answer, event(phase)]);
  const units = normalizeActivityTimeline(messages, { preserveReplyBoundaries: true });
  expect(units.map(unit => unit.type)).toEqual(["activity", "message"]);
  expect(units[0]).toMatchObject({ messages: [{ toolEvents: [{ phase }] }], sourceMessageCount: 1 });
  expect(units[1]).toMatchObject({ message: { content: "Hello" }, sourceMessageCount: 2 });
  expect(messages[0].toolEvents?.[0].phase).toBe("start");
});

it("preserves two deliberate identical messages with separate invocation IDs", () => {
  const messages = projectThreadEvents([
    event("start"), answer, event("end"),
    event("start", "second"), answer, event("end", "second"),
  ]);
  const units = normalizeActivityTimeline(messages, { preserveReplyBoundaries: true });
  expect(units.map(unit => unit.type)).toEqual(["activity", "message", "activity", "message"]);
  expect(units.filter(unit => unit.type === "activity").flatMap(unit => unit.messages)
    .flatMap(row => row.toolEvents ?? []).map(call => call.call_id)).toEqual(["delivery", "second"]);
  expect(units.reduce((count, unit) => count + unit.sourceMessageCount, 0)).toBe(messages.length);
});
