import type { SessionAutomationJob } from "@/lib/contracts/automations";

export type AutomationFilter =
  | "all"
  | "active"
  | "paused"
  | "failed"
  | "system";
export type AutomationAction = "enable" | "disable" | "delete" | "run";
export function isLocalTriggerAutomation(job: SessionAutomationJob | null) {
  return (
    !!job &&
    (job.kind === "local_trigger" ||
      job.payload.kind === "local_trigger" ||
      job.schedule.kind === "local")
  );
}
export const automationTriggerCommand = (job: SessionAutomationJob) =>
  job.trigger?.command || job.payload.command || job.payload.message || "";
export const automationNeedsAttention = (job: SessionAutomationJob) =>
  job.state.last_status === "error" || Boolean(job.state.last_error);
export function automationStatusKey(
  job: SessionAutomationJob,
): "active" | "running" | "paused" | "failed" | "completed" | "idle" {
  if (job.state.pending) return "running";
  if (!job.enabled) return "paused";
  if (automationNeedsAttention(job)) return "failed";
  if (isLocalTriggerAutomation(job)) return "active";
  if (
    job.delete_after_run &&
    job.state.next_run_at_ms == null &&
    job.state.last_status === "ok"
  )
    return "completed";
  return job.state.next_run_at_ms != null ? "active" : "idle";
}
export function automationMatchesFilter(
  job: SessionAutomationJob,
  filter: AutomationFilter,
) {
  const status = automationStatusKey(job);
  const filters = {
    all: true,
    active: status === "active" || status === "running",
    paused: status === "paused",
    failed: automationNeedsAttention(job),
    system: !!job.protected,
  };
  return filters[filter];
}
