import type { TFunction } from "i18next";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { channelTranslator } from "@/channel-plugins/i18n";
import {
  channelUiOwner,
  channelUiPresentation,
} from "@/channel-plugins/registry";
import { fmtDateTime, relativeTime } from "@/lib/format-time";
import { automationStatusKey, isLocalTriggerAutomation } from "./status";
import { formatCronScheduleSummary } from "./cron-summary";

const HOST_AUTOMATION_CHANNEL_LABELS: Record<string, string> = {
  api: "API",
  cli: "CLI",
};

export function automationChannelLabel(channel: string, t: TFunction): string {
  const key = channel.trim().toLowerCase();
  const presentation = channelUiPresentation(key);
  if (presentation) {
    return channelTranslator(t, channelUiOwner(key))(
      "displayName",
      presentation.displayName,
    );
  }
  const displayName = HOST_AUTOMATION_CHANNEL_LABELS[key];
  return displayName
    ? t(`settings.automations.channels.${key}`, { defaultValue: displayName })
    : channel;
}

export function formatAutomationSchedule(
  job: SessionAutomationJob,
  locale: string,
  tx: (
    key: string,
    fallback: string,
    values?: Record<string, unknown>,
  ) => string,
): string {
  if (job.schedule.kind === "at" && job.schedule.at_ms != null) {
    return tx("settings.automations.schedule.at", "At {{time}}", {
      time: fmtDateTime(job.schedule.at_ms, locale),
    });
  }
  if (job.schedule.kind === "every" && job.schedule.every_ms) {
    return tx("settings.automations.schedule.every", "Every {{duration}}", {
      duration: formatAutomationInterval(job.schedule.every_ms, locale),
    });
  }
  if (job.schedule.kind === "cron" && job.schedule.expr) {
    const summary = formatCronScheduleSummary(job.schedule.expr, locale, tx);
    if (summary) return summary;
    return tx("settings.automations.schedule.custom", "Custom schedule");
  }
  if (isLocalTriggerAutomation(job)) {
    return tx("settings.automations.commandCondition", "Triggered by command");
  }
  return tx("settings.automations.schedule.custom", "Custom schedule");
}

export function formatAutomationNext(
  job: SessionAutomationJob,
  tx: (
    key: string,
    fallback: string,
    values?: Record<string, unknown>,
  ) => string,
): string {
  if (!job.enabled) return tx("settings.automations.next.paused", "Disabled");
  if (job.state.pending)
    return tx("settings.automations.next.pending", "Running now");
  if (isLocalTriggerAutomation(job)) {
    return tx("settings.automations.next.local", "Waiting for trigger");
  }
  if (automationStatusKey(job) === "completed") {
    return tx("settings.automations.status.completed", "Completed");
  }
  if (job.state.next_run_at_ms == null)
    return tx("settings.automations.next.none", "No next run");
  return relativeTime(job.state.next_run_at_ms);
}

export function formatAutomationNextTitle(
  job: SessionAutomationJob,
  locale: string,
  tx: (
    key: string,
    fallback: string,
    values?: Record<string, unknown>,
  ) => string,
): string {
  if (job.state.next_run_at_ms == null) return formatAutomationNext(job, tx);
  return fmtDateTime(job.state.next_run_at_ms, locale);
}

function formatAutomationUnit(
  value: number,
  unit: Intl.NumberFormatOptions["unit"],
  locale: string,
  maximumFractionDigits = 0,
): string {
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: "long",
    maximumFractionDigits,
  }).format(value);
}

export function formatAutomationInterval(ms: number, locale: string): string {
  const units: Array<[Intl.NumberFormatOptions["unit"], number]> = [
    ["day", 86_400_000],
    ["hour", 3_600_000],
    ["minute", 60_000],
    ["second", 1000],
    ["millisecond", 1],
  ];
  for (const [unit, size] of units) {
    if (ms >= size && ms % size === 0)
      return formatAutomationUnit(ms / size, unit, locale);
  }
  const fallbackUnit = ms < 60_000 ? "second" : "minute";
  const fallbackSize = fallbackUnit === "second" ? 1000 : 60_000;
  return formatAutomationUnit(ms / fallbackSize, fallbackUnit, locale, 1);
}
