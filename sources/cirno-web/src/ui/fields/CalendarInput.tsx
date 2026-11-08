import { Calendar, DateField, DatePicker, FieldError, Label } from "@heroui/react";
import { CalendarDate } from "@internationalized/date";
import { useTranslation } from "react-i18next";
import { parseLocalDay } from "@/lib/local-date-time";
function calendarDate(value: string) {
  const day = parseLocalDay(value);
  return day ? new CalendarDate(day.getFullYear(), day.getMonth() + 1, day.getDate()) : null;
}
export function CalendarInput({
  label,
  value,
  onChange,
  disabled,
  required,
  min,
  max,
  errorId,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  required?: boolean;
  min?: string;
  max?: string;
  errorId?: string;
}) {
  const { t } = useTranslation();
  return (
    <DatePicker
      isDisabled={disabled}
      isRequired={required}
      value={calendarDate(value)}
      minValue={calendarDate(min ?? "0001-01-01")!}
      maxValue={calendarDate(max ?? "9999-12-31")!}
      onChange={(next) => onChange(next?.toString() ?? "")}
      aria-describedby={errorId}
    >
      <Label>{label}</Label>
      <DateField.Group>
        <DateField.Input>{(segment) => <DateField.Segment segment={segment} />}</DateField.Input>
        <DateField.Suffix>
          <DatePicker.Trigger aria-label={t("common.chooseDate")}>
            <DatePicker.TriggerIndicator />
          </DatePicker.Trigger>
        </DateField.Suffix>
      </DateField.Group>
      <DatePicker.Popover>
        <Calendar>
          <Calendar.Header>
            <Calendar.NavButton slot="previous" />
            <Calendar.Heading />
            <Calendar.NavButton slot="next" />
          </Calendar.Header>
          <Calendar.Grid>
            <Calendar.GridHeader>
              {(day) => <Calendar.HeaderCell>{day}</Calendar.HeaderCell>}
            </Calendar.GridHeader>
            <Calendar.GridBody>{(date) => <Calendar.Cell date={date} />}</Calendar.GridBody>
          </Calendar.Grid>
        </Calendar>
      </DatePicker.Popover>
      <FieldError />
    </DatePicker>
  );
}
