import { Button, Popover } from "@heroui/react";
import { X } from "lucide-react";
import { useState } from "react";
import { CalendarEntryRow } from "./CalendarEntryRow";
import type { CalendarEntry, CalendarCopy } from "./model";

export function DayOverflow({
  entries,
  label,
  locale,
  copy,
  onInspect,
}: {
  entries: CalendarEntry[];
  label: string;
  locale: string;
  copy: CalendarCopy;
  onInspect: (entry: CalendarEntry) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover isOpen={open} onOpenChange={setOpen}>
      <Button variant="ghost" size="sm" className="automation-day-overflow">
        {copy.more(entries.length - 3)}
      </Button>
      <Popover.Content placement="right top">
        <Popover.Dialog className="automation-day-details" aria-label={label}>
          <div className="automation-command-heading">
            <Popover.Heading>{label}</Popover.Heading>
            <Button
              variant="ghost"
              isIconOnly
              size="sm"
              aria-label={copy.close}
              onPress={() => setOpen(false)}
            >
              <X size={16} />
            </Button>
          </div>
          {entries.map((entry) => (
            <CalendarEntryRow
              key={entry.id}
              entry={entry}
              copy={copy}
              locale={locale}
              onInspect={(value) => {
                setOpen(false);
                onInspect(value);
              }}
            />
          ))}
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  );
}
