import { describe, expect, it } from "vitest";
import { projectActivityTimeline } from "@/lib/activity-timeline";
import { groupRouterActivity } from "@/lib/router-activity-timeline";
import type { UIMessage } from "@/lib/contracts/messages";

const heartbeat = (id: string, createdAt: number): UIMessage => ({
  id, turnId: id, role: "user", createdAt, content: `Inspect ${id}`,
  inputOrigin: { kind: "heartbeat", label: "Heartbeat" },
});
const reasoning = (id: string, turnId: string, createdAt: number, latencyMs?: number): UIMessage => ({
  id, turnId, role: "assistant", content: "", reasoning: id, createdAt, latencyMs,
});

describe("Router activity presentation", () => {
  it("folds consecutive turns and heartbeat inputs without changing source messages or counts", () => {
    const messages = [heartbeat("a", 1000), reasoning("first", "a", 4000, 3000),
      heartbeat("b", 100_000), reasoning("second", "b", 105_000, 5000)];
    const snapshot = structuredClone(messages);
    const units = groupRouterActivity(projectActivityTimeline(messages));
    expect(units).toHaveLength(1);
    expect(units[0]).toMatchObject({ type: "activity", sourceMessageCount: 4, turnLatencyMs: 8000,
      startedAtMs: 100_000, elapsedBeforeActiveMs: 3000 });
    if (units[0].type === "activity") expect(units[0].messages.map(message => message.id)).toEqual(["a", "first", "b", "second"]);
    expect(messages).toEqual(snapshot);
  });

  it("keeps visible messages and consolidation reports as boundaries", () => {
    const messages: UIMessage[] = [heartbeat("a", 1), reasoning("first", "a", 2),
      { id: "reply", role: "assistant", content: "Update", createdAt: 3 },
      heartbeat("b", 4), reasoning("second", "b", 5),
      { id: "owner", role: "user", content: "Next", createdAt: 6 },
      heartbeat("c", 7),
      { id: "report", role: "assistant", kind: "compaction", content: "Saved", createdAt: 8 },
      heartbeat("d", 9)];
    const units = groupRouterActivity(projectActivityTimeline(messages));
    expect(units.map(unit => unit.type === "message" ? unit.message.id : "activity"))
      .toEqual(["activity", "reply", "activity", "owner", "activity", "report", "activity"]);
    expect(units.reduce((sum, unit) => sum + unit.sourceMessageCount, 0)).toBe(messages.length);
  });

  it("keeps incoming Worker messages and failed deliveries visible", () => {
    const incoming: UIMessage = { ...heartbeat("incoming", 3), inputOrigin: { kind: "supervision", label: "Worker" },
      sessionMessage: { message_id: "report-1", session: { id: "worker", name: "Worker" } } };
    const failed: UIMessage = { ...heartbeat("failed", 5), deliveryStatus: "failed" };
    const units = groupRouterActivity(projectActivityTimeline([heartbeat("a", 1), incoming, heartbeat("b", 4), failed]));
    expect(units.map(unit => unit.type === "message" ? unit.message.id : "activity"))
      .toEqual(["activity", "incoming", "activity", "failed"]);
  });

  it("counts persisted turn latency only once when its activities are split", () => {
    const message = reasoning("first", "a", 2000);
    expect(groupRouterActivity([
      { type: "activity", messages: [message], sourceMessageCount: 1, startedAtMs: 1000 },
      { type: "activity", messages: [{ ...message, id: "last", createdAt: 5000 }],
        sourceMessageCount: 1, startedAtMs: 1000, turnLatencyMs: 4000 },
    ])[0]).toMatchObject({ turnLatencyMs: 4000, elapsedBeforeActiveMs: 0 });
  });

  it("uses only the current heartbeat start for its live clock, retaining previous elapsed time", () => {
    const units = groupRouterActivity(projectActivityTimeline([
      heartbeat("a", 1000), reasoning("first", "a", 4000, 3000), heartbeat("b", 100_000),
    ]));
    expect(units[0]).toMatchObject({ startedAtMs: 100_000, elapsedBeforeActiveMs: 3000, turnLatencyMs: 3000 });
  });
});
