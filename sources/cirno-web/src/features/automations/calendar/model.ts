import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { AutomationRunRecord } from "../runs/AutomationRunDialogView";

export type CalendarEntry = {
  id: string;
  job: SessionAutomationJob;
  startMs: number;
  kind: "planned" | "recorded";
  run: AutomationRunRecord | null;
};

export type CalendarCopy = {
  planned: string;
  recorded: string;
  running: string;
  failed: string;
  more: (count: number) => string;
  close: string;
  noEntries: string;
  completed: string;
  skipped: string;
  system: string;
};

export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addDays(date: Date, amount: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + amount);
}

export function mondayIndex(date: Date): number {
  return (date.getDay() + 6) % 7;
}

export function dateKey(value: Date | number): string {
  const date = typeof value === "number" ? new Date(value) : value;
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

export function entriesForJobs(jobs: SessionAutomationJob[]): CalendarEntry[] {
  return jobs.flatMap((job) => {
    const history = job.state.run_history ?? [];
    const nextRun = job.enabled ? job.state.next_run_at_ms : null;
    const recordedRuns =
      history.length || job.state.last_run_at_ms == null || nextRun != null
        ? history
        : [
            {
              run_at_ms: job.state.last_run_at_ms,
              status: job.state.last_status ?? "unknown",
              error: job.state.last_error,
            },
          ];
    const recorded = recordedRuns.map((run, index) => ({
      id: `${job.id}:recorded:${run.run_at_ms}:${index}`,
      job,
      startMs: run.run_at_ms,
      kind: "recorded" as const,
      run,
    }));
    return nextRun == null
      ? recorded
      : [
          ...recorded,
          {
            id: `${job.id}:planned:${nextRun}`,
            job,
            startMs: nextRun,
            kind: "planned" as const,
            run: null,
          },
        ];
  });
}

export function entryTime(entry: CalendarEntry, locale: string): string {
  const formatter = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
  });
  return formatter.format(entry.startMs);
}

export function isSameDay(left: Date, right: Date): boolean {
  return dateKey(left) === dateKey(right);
}
