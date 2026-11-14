import { messageVariant } from "@/features/messages/model/messageVariant";
import type { TurnUnit } from "@/lib/activity-timeline";
import type { UIMessage } from "@/lib/contracts/messages";

type ActivityUnit = Extract<TurnUnit, { type: "activity" }>;
interface RunTiming {
  start: number;
  end: number;
  latency?: number;
}

/** Router work stays in one disclosure until a visible conversation message.
 * Runtime inputs remain in its details; persisted messages and turn IDs stay intact.
 */
export function groupRouterActivity(units: TurnUnit[]): TurnUnit[] {
  const result: TurnUnit[] = [];
  let messages: UIMessage[] = [];
  let sourceMessageCount = 0;
  let runKey = "";
  const timings = new Map<string, RunTiming>();

  const append = (unit: ActivityUnit) => {
    sourceMessageCount += unit.sourceMessageCount;
    for (const message of unit.messages) {
      if (message.turnId) runKey = message.turnId;
      else if (message.role === "user" || !runKey) runKey = message.id;
      const start = unit.startedAtMs ?? message.createdAt;
      const timing = timings.get(runKey) ?? { start, end: message.createdAt };
      timing.start = Math.min(timing.start, start);
      timing.end = Math.max(timing.end, message.createdAt);
      if (unit.turnLatencyMs !== undefined) timing.latency = unit.turnLatencyMs;
      timings.set(runKey, timing);
      messages.push(message);
    }
  };
  const flush = () => {
    if (!messages.length) return;
    const runs = [...timings.values()];
    const durations = runs.map(run => run.latency ?? Math.max(0, run.end - run.start));
    const total = durations.reduce((sum, duration) => sum + duration, 0);
    result.push({
      type: "activity", messages, sourceMessageCount,
      turnLatencyMs: total,
      startedAtMs: runs.at(-1)?.start,
      elapsedBeforeActiveMs: total - durations.at(-1)!,
    });
    messages = [];
    sourceMessageCount = 0;
    runKey = "";
    timings.clear();
  };

  for (const unit of units) {
    if (unit.type === "activity") append(unit);
    else if (messageVariant(unit.message) === "system" && unit.message.deliveryStatus !== "failed") {
      append({ type: "activity", messages: [unit.message], sourceMessageCount: unit.sourceMessageCount,
        startedAtMs: unit.message.createdAt });
    } else {
      flush();
      result.push(unit);
    }
  }
  flush();
  return result;
}
