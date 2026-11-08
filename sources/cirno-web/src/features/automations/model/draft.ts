import type {
  AutomationUpdatePayload,
  SessionAutomationJob,
} from "@/lib/contracts/automations";
import { isLocalTriggerAutomation } from "./status";
import { localDateTimeInput, parseLocalDateTime } from "@/lib/local-date-time";

export const AUTOMATION_EVERY_UNITS = [
  { value: "millisecond", ms: 1 },
  { value: "second", ms: 1000 },
  { value: "minute", ms: 60_000 },
  { value: "hour", ms: 3_600_000 },
  { value: "day", ms: 86_400_000 },
] as const;
export type AutomationEveryUnit =
  (typeof AUTOMATION_EVERY_UNITS)[number]["value"];
export interface AutomationEditDraft {
  name: string;
  message: string;
  scheduleKind: "at" | "every" | "cron";
  everyValue: string;
  everyUnit: AutomationEveryUnit;
  cronExpr: string;
  tz: string;
  atLocal: string;
}
export type DraftError =
  | "nameRequired"
  | "messageRequired"
  | "intervalRequired"
  | "cronRequired"
  | "timeRequired"
  | "futureRequired";
export type ParsedDraft =
  | { ok: true; value: AutomationUpdatePayload }
  | { ok: false; error: DraftError };
export function automationDraftFromJob(
  job: SessionAutomationJob,
): AutomationEditDraft {
  const ms = job.schedule.every_ms ?? 3_600_000;
  const unit = [...AUTOMATION_EVERY_UNITS]
    .reverse()
    .find((unit) => ms % unit.ms === 0)!;
  return {
    name: job.name,
    message: job.payload.message,
    scheduleKind:
      job.schedule.kind === "at" || job.schedule.kind === "cron"
        ? job.schedule.kind
        : "every",
    everyValue: String(ms / unit.ms),
    everyUnit: unit.value,
    cronExpr: job.schedule.expr ?? "0 9 * * *",
    tz: job.schedule.tz ?? "",
    atLocal: localDateTimeInput(job.schedule.at_ms ?? Date.now() + 3_600_000),
  };
}
export function parseAutomationDraft(
  draft: AutomationEditDraft,
  job: SessionAutomationJob,
  now = Date.now(),
): ParsedDraft {
  const name = draft.name.trim(),
    message = draft.message.trim();
  if (!name) return { ok: false, error: "nameRequired" };
  const namePatch = name === job.name ? {} : { name };
  if (isLocalTriggerAutomation(job)) return { ok: true, value: namePatch };
  if (!message) return { ok: false, error: "messageRequired" };
  let schedule: NonNullable<AutomationUpdatePayload["schedule"]>,
    changed: boolean;
  switch (draft.scheduleKind) {
    case "every": {
      const unit = AUTOMATION_EVERY_UNITS.find(
        (unit) => unit.value === draft.everyUnit,
      )!;
      const value = Number(draft.everyValue),
        ms = value * unit.ms;
      if (
        !Number.isSafeInteger(value) ||
        value <= 0 ||
        !Number.isSafeInteger(ms)
      )
        return { ok: false, error: "intervalRequired" };
      schedule = { kind: "every", every_ms: ms };
      changed = job.schedule.kind !== "every" || ms !== job.schedule.every_ms;
      break;
    }
    case "cron": {
      const expr = draft.cronExpr.trim(),
        tz = draft.tz.trim();
      if (!expr) return { ok: false, error: "cronRequired" };
      schedule = { kind: "cron", expr, ...(tz ? { tz } : {}) };
      changed =
        job.schedule.kind !== "cron" ||
        expr !== job.schedule.expr ||
        tz !== (job.schedule.tz ?? "");
      break;
    }
    case "at": {
      const at = parseLocalDateTime(draft.atLocal);
      if (!at) return { ok: false, error: "timeRequired" };
      changed =
        job.schedule.kind !== "at" ||
        draft.atLocal !== localDateTimeInput(job.schedule.at_ms!);
      if (changed && at.getTime() <= now)
        return { ok: false, error: "futureRequired" };
      schedule = { kind: "at", at_ms: at.getTime() };
      break;
    }
  }
  return {
    ok: true,
    value: {
      ...namePatch,
      ...(draft.message !== job.payload.message
        ? { message: draft.message }
        : {}),
      ...(changed ? { schedule } : {}),
    },
  };
}
