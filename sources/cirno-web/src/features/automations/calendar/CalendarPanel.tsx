import { Button } from "@heroui/react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Dispatch, SetStateAction } from "react";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { AutomationRunDialog } from "../runs/AutomationRunDialog";
import { AutomationCalendar } from "./AutomationCalendar";

export function MonthNavigation({
  month,
  setMonth,
}: {
  month: Date;
  setMonth: Dispatch<SetStateAction<Date>>;
}) {
  const { t, i18n } = useTranslation();
  return (
    <div className="automation-month-navigation">
      <h2>
        {new Intl.DateTimeFormat(i18n.resolvedLanguage ?? i18n.language, {
          month: "long",
          year: "numeric",
        }).format(month)}
      </h2>
      <Button
        variant="ghost"
        size="sm"
        onPress={() => {
          const today = new Date();
          setMonth(new Date(today.getFullYear(), today.getMonth(), 1));
        }}
      >
        {t("settings.automations.calendar.today")}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        isIconOnly
        aria-label={t("settings.automations.calendar.previousMonth")}
        onPress={() =>
          setMonth(
            (value) => new Date(value.getFullYear(), value.getMonth() - 1, 1),
          )
        }
      >
        <ChevronLeft size={16} />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        isIconOnly
        aria-label={t("settings.automations.calendar.nextMonth")}
        onPress={() =>
          setMonth(
            (value) => new Date(value.getFullYear(), value.getMonth() + 1, 1),
          )
        }
      >
        <ChevronRight size={16} />
      </Button>
    </div>
  );
}
export function CalendarPanel({
  token,
  jobs,
  month,
  loading,
  hasJobs,
  onInspect,
}: {
  token?: string;
  jobs: SessionAutomationJob[];
  month: Date;
  loading: boolean;
  hasJobs: boolean;
  onInspect: (job: SessionAutomationJob) => void;
}) {
  const { t, i18n } = useTranslation();
  const tx = (key: string) => t(`settings.automations.${key}`);
  return (
    <AutomationCalendar
      jobs={jobs}
      month={month}
      locale={i18n.resolvedLanguage ?? i18n.language}
      loadingLabel={loading ? tx("loading") : undefined}
      onInspect={onInspect}
      renderRunDialog={(props) => (
        <AutomationRunDialog token={token} {...props} />
      )}
      copy={{
        planned: tx("calendar.planned"),
        recorded: tx("calendar.recorded"),
        running: tx("status.running"),
        failed: tx("status.failed"),
        completed: tx("status.completed"),
        skipped: tx("skipped"),
        system: tx("filters.system"),
        close: t("common.close"),
        more: (count) => t("settings.automations.calendar.more", { count }),
        noEntries: tx(
          jobs.length ? "calendar.noEntries" : hasJobs ? "noMatches" : "empty",
        ),
      }}
    />
  );
}
