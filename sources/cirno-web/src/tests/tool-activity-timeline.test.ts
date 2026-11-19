import { expect, it } from "vitest";
import { activityToolEntries } from "@/components/thread/activity/tool-activity-timeline";
import type { UIMessage } from "@/lib/contracts/messages";

it.each([["a", "a", "b"], ["a", "b", "a"]])("retains call order for compacted trace names %s/%s/%s", (...names) => {
  const message: UIMessage = { id: "fixture", role: "tool", kind: "trace", content: "", createdAt: 1,
    traces: ['fixture({"name":"a"})', 'fixture({"name":"b"})'],
    toolEvents: names.map((name, index) => ({ name: "fixture", call_id: String(index), phase: "end", arguments: { name } })) };
  expect(activityToolEntries(message).map(entry => entry.event?.call_id)).toEqual(["0", "1", "2"]);
});

it("retains legacy-only entries alongside call-identified events", () => {
  const message: UIMessage = { id: "fixture", role: "tool", kind: "trace", content: "", createdAt: 1,
    traces: ["legacy_before()", "fixture()", "legacy_after()"],
    toolEvents: [{ name: "fixture", call_id: "first", phase: "end", arguments: {} }, { name: "fixture", call_id: "second", phase: "start", arguments: {} }] };
  const entries = activityToolEntries(message);
  expect(entries.filter(entry => !entry.event).map(entry => entry.line)).toEqual(["legacy_before()", "legacy_after()"]);
  expect(entries.filter(entry => entry.event).map(entry => entry.event?.call_id)).toEqual(["first", "second"]);
});

it("does not create duplicate rows for repeated phases of the same identified call", () => {
  const call = { name: "fixture", call_id: "same", arguments: {} };
  const entries = activityToolEntries({ id: "fixture", role: "tool", kind: "trace", content: "fixture()", createdAt: 1,
    toolEvents: [{ ...call, phase: "start" }, { ...call, phase: "end", result: "complete" }, { ...call, phase: "start" }] });
  expect(entries).toHaveLength(1);
  expect(entries[0].event).toMatchObject({ phase: "end", result: "complete" });
});
