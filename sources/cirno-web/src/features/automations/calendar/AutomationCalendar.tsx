import { useMemo, useState, type ReactNode } from "react";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { AutomationRunRecord } from "../runs/AutomationRunDialogView";
import {
  addDays,
  dateKey,
  entriesForJobs,
  isSameDay,
  mondayIndex,
  type CalendarCopy,
  type CalendarEntry,
} from "./model";
import { CalendarEntryRow } from "./CalendarEntryRow";
import { DayOverflow } from "./DayOverflow";
import "../automations.css";

export interface AutomationCalendarRunProps {
  job: SessionAutomationJob;
  run: AutomationRunRecord;
  locale: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
export function AutomationCalendar({
  jobs,
  loadingLabel,
  month,
  locale,
  copy,
  onInspect,
  renderRunDialog,
}: {
  jobs: SessionAutomationJob[];
  loadingLabel?: string;
  month: Date;
  locale: string;
  copy: CalendarCopy;
  onInspect: (job: SessionAutomationJob) => void;
  renderRunDialog: (props: AutomationCalendarRunProps) => ReactNode;
}) {
  const [selectedRun, setSelectedRun] = useState<{
    job: SessionAutomationJob;
    run: AutomationRunRecord;
  } | null>(null);
  const [runOpen, setRunOpen] = useState(false);
  const inspect = (entry: CalendarEntry) => {
    if (entry.run) {
      setSelectedRun({ job: entry.job, run: entry.run });
      setRunOpen(true);
    } else onInspect(entry.job);
  };
  const first = addDays(month, -mondayIndex(month));
  const length =
    mondayIndex(month) +
      new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate() >
    35
      ? 42
      : 35;
  const days = Array.from({ length }, (_, index) => addDays(first, index));
  const all = useMemo(
    () =>
      entriesForJobs(jobs).sort((left, right) => left.startMs - right.startMs),
    [jobs],
  );
  const entries = all.filter(
    (entry) =>
      entry.startMs >= first.getTime() &&
      entry.startMs < addDays(first, length).getTime(),
  );
  const byDay = new Map<string, CalendarEntry[]>();
  for (const entry of entries) {
    const key = dateKey(entry.startMs),
      group = byDay.get(key) ?? [];
    group.push(entry);
    byDay.set(key, group);
  }
  const monthLabel = new Intl.DateTimeFormat(locale, {
    month: "long",
    year: "numeric",
  }).format(month);
  const fullDate = new Intl.DateTimeFormat(locale, { dateStyle: "full" });
  const compactDate = new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    weekday: "short",
  });
  const dayNumber = new Intl.DateTimeFormat(locale, { day: "numeric" });
  const weekday = new Intl.DateTimeFormat(locale, { weekday: "short" });
  const today = new Date();
  const content = (
    <>
      <div className="automation-calendar-weekdays" aria-hidden>
        {days.slice(0, 7).map((day) => (
          <span key={dateKey(day)}>{weekday.format(day)}</span>
        ))}
      </div>
      <ol className="automation-calendar-days" aria-label={monthLabel}>
        {days.map((day) => {
          const values = byDay.get(dateKey(day)) ?? [];
          return (
            <li
              key={dateKey(day)}
              className="automation-calendar-day"
              aria-label={fullDate.format(day)}
              data-empty={!values.length || undefined}
              data-outside={day.getMonth() !== month.getMonth() || undefined}
            >
              <time
                className="automation-day-heading"
                aria-label={fullDate.format(day)}
                aria-current={isSameDay(day, today) ? "date" : undefined}
                dateTime={`${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`}
              >
                <span className="automation-day-number">
                  {dayNumber.format(day)}
                </span>
                <span className="automation-day-agenda">
                  {compactDate.format(day)}
                </span>
              </time>
              <div className="automation-day-entries">
                {loadingLabel ? (
                  <div className="automation-day-skeleton" />
                ) : (
                  values.map((entry) => (
                    <CalendarEntryRow
                      key={entry.id}
                      entry={entry}
                      copy={copy}
                      locale={locale}
                      onInspect={inspect}
                    />
                  ))
                )}
                {values.length > 3 && (
                  <DayOverflow
                    entries={values}
                    label={fullDate.format(day)}
                    locale={locale}
                    copy={copy}
                    onInspect={inspect}
                  />
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {!loadingLabel && !entries.length && (
        <p className="automation-empty automation-calendar-empty">
          {copy.noEntries}
        </p>
      )}
    </>
  );
  return (
    <section
      className="automation-calendar"
      data-loading={!!loadingLabel || undefined}
      tabIndex={-1}
    >
      {loadingLabel ? (
        <SkeletonStatus
          label={loadingLabel}
          className="automation-calendar-loading"
        >
          {content}
        </SkeletonStatus>
      ) : (
        content
      )}
      {selectedRun &&
        renderRunDialog({
          ...selectedRun,
          locale,
          open: runOpen,
          onOpenChange: setRunOpen,
        })}
    </section>
  );
}
