import { Label, TimeField } from "@heroui/react";
import { Time } from "@internationalized/date";
import { useTranslation } from "react-i18next";
import { CalendarInput } from "@/ui/fields/CalendarInput";

export function RunAtPicker({
  value,
  onChange,
  disabled = false,
  errorId,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  errorId?: string;
}) {
  const { t } = useTranslation();
  const [dayValue, timeValue = ""] = value.split("T");
  const time = /^([01]\d|2[0-3]):[0-5]\d$/.test(timeValue) ? timeValue.split(":").map(Number) : null;
  return (
    <div className="automation-date-time">
      <CalendarInput
        label={t("settings.automations.fields.runDate")}
        value={dayValue}
        disabled={disabled}
        errorId={errorId}
        onChange={(day) => onChange(`${day}T${timeValue}`)}
      />
      <TimeField
        isDisabled={disabled}
        granularity="minute"
        hourCycle={24}
        value={time && new Time(time[0], time[1])}
        onChange={(next) => onChange(`${dayValue}T${next?.toString().slice(0, 5) ?? ""}`)}
        aria-describedby={errorId}
      >
        <Label>{t("settings.automations.fields.runTime")}</Label>
        <TimeField.Group>
          <TimeField.Input>{(segment) => <TimeField.Segment segment={segment} />}</TimeField.Input>
        </TimeField.Group>
      </TimeField>
    </div>
  );
}
