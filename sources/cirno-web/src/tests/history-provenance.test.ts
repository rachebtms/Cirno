import { expect, it } from "vitest";
import { parseWebuiThreadPayload } from "@/lib/api/history";
import { ThreadTranscript } from "@/lib/thread-transcript";

const envelope = { message_id: "report-1", session: { id: "worker-1", name: "worker" } };
const payload = (provenance: unknown) => ({ schemaVersion: 3, projection: "events", events: [
  { event: "user_message", chat_id: "router", text: "Background input", starts_turn: true, turn_id: "background-1", provenance },
  { event: "message", chat_id: "router", text: "A visible Router update", turn_id: "background-1", turn_seq: 1 },
] });

it.each(["heartbeat", "scheduled_task", "trigger", "subagent", "continuation", "system", "supervision"])("replays %s input without requiring a worker report envelope", kind => {
  const source = { kind, label: "Background input", id: "origin-1" };
  const owner = new ThreadTranscript();
  expect(owner.accept(parseWebuiThreadPayload(payload({ input_origin: source })), owner.begin("initial"))).toBe(true);
  expect(owner.messages[0].inputOrigin).toEqual(source);
  expect(owner.messages.some(message => message.content === "A visible Router update")).toBe(true);
});

it("accepts conversation source provenance alone or alongside the origin", () => {
  for (const provenance of [{ session_message: envelope }, { session_message: envelope, input_origin: { kind: "conversation", label: "@worker" } }]) {
    expect(parseWebuiThreadPayload(payload(provenance)).events).toHaveLength(2);
  }
});

it.each([null, { input_origin: { kind: "unknown" } }, { input_origin: { kind: "system", label: 42 } }, { session_message: { message_id: 42 } }])("reports malformed provenance instead of silently discarding history: %j", provenance => {
  expect(() => parseWebuiThreadPayload(payload(provenance))).toThrow("Invalid WebUI thread projection event");
});
