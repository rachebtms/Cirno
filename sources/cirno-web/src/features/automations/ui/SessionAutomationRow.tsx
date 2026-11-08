import { Button } from "@heroui/react";
import { ChevronRight } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { currentLocale } from "@/i18n";
import { fmtDateTime, relativeTime } from "@/lib/format-time";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { cn } from "@/lib/utils";
import {
  automationNeedsAttention,
  isLocalTriggerAutomation,
} from "../model/status";
export function SessionAutomationRow({
  job,
  now,
  onSelect,
}: {
  job: SessionAutomationJob;
  now: number;
  onSelect: (job: SessionAutomationJob) => void;
}) {
  const { t } = useTranslation("common");
  const nextRun = formatNextRun(job, t, now);
  const needsAttention = automationNeedsAttention(job);
  const summary = needsAttention
    ? t("settings.automations.filters.failed", {
        defaultValue: "Needs attention",
      })
    : nextRun.label;
  const statusClass = job.enabled
    ? needsAttention
      ? "bg-destructive"
      : "bg-emerald-500"
    : "bg-muted-foreground/35";

  return (
    <Button
      variant="ghost"
      aria-haspopup="dialog"
      aria-label={`${job.name || job.id}, ${summary}`}
      onPress={() => onSelect(job)}
      className={cn(
        "grid min-h-12 w-full grid-cols-[0.375rem_minmax(0,1fr)_1rem] items-center gap-2.5 rounded-control px-3 py-2 text-left",
        "transition-colors duration-150 settings-hover",
      )}
    >
      <span
        className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusClass)}
        aria-hidden
      />
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-medium leading-5 text-foreground">
          {job.name || job.id}
        </span>
        <span
          className={cn(
            "block truncate text-[11.5px] leading-4 text-muted-foreground",
            needsAttention && "text-destructive",
          )}
          title={needsAttention ? summary : nextRun.title}
        >
          {summary}
        </span>
      </span>
      <ChevronRight className="h-4 w-4 text-muted-foreground/65" aria-hidden />
    </Button>
  );
}

function formatNextRun(job: SessionAutomationJob, t: TFunction, now: number) {
  const locale = currentLocale();
  if (!job.enabled) {
    return { label: t("thread.sessionInfo.next.disabled"), title: "" };
  }
  if (job.state.pending) {
    return { label: t("thread.sessionInfo.next.pending"), title: "" };
  }
  if (isLocalTriggerAutomation(job)) {
    return { label: t("thread.sessionInfo.next.local"), title: "" };
  }
  const next = job.state.next_run_at_ms;
  if (next == null) {
    return { label: t("thread.sessionInfo.next.none"), title: "" };
  }
  return {
    label: t("thread.sessionInfo.next.label", {
      time: relativeTime(next, locale, now),
    }),
    title: fmtDateTime(next, locale),
  };
}
