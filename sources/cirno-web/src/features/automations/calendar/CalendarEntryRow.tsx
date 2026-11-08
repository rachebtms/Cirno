import { Button } from "@heroui/react";
import { CircleAlert, Loader2 } from "lucide-react";
import { entryTime, type CalendarCopy, type CalendarEntry } from "./model";

export function CalendarEntryRow({
  entry,
  locale,
  copy,
  onInspect,
}: {
  entry: CalendarEntry;
  locale: string;
  copy: CalendarCopy;
  onInspect: (entry: CalendarEntry) => void;
}) {
  const running = !!entry.job.state.pending && entry.kind === "planned";
  const status = running
    ? copy.running
    : ({ error: copy.failed, ok: copy.completed, skipped: copy.skipped }[
        entry.run?.status ?? ""
      ] ?? copy[entry.kind]);
  const name = entry.job.name || entry.job.id;
  return (
    <Button
      variant="ghost"
      className="automation-calendar-entry"
      data-kind={entry.kind}
      data-failed={entry.run?.status === "error" || undefined}
      aria-label={`${name}, ${entryTime(entry, locale)}, ${status}${entry.job.protected ? `, ${copy.system}` : ""}`}
      aria-haspopup="dialog"
      onPress={() => onInspect(entry)}
    >
      <span className="automation-entry-name">{name}</span>
      <span className="automation-entry-meta">
        {running && <Loader2 size={12} className="animate-spin" />}
        {entry.run?.status === "error" && <CircleAlert size={12} />}
        <time dateTime={new Date(entry.startMs).toISOString()}>
          {entryTime(entry, locale)}
        </time>
        <span>{status}</span>
        {entry.job.protected && <span>{copy.system}</span>}
      </span>
    </Button>
  );
}
