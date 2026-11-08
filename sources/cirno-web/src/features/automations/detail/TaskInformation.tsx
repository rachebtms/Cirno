import { Button, Popover } from "@heroui/react";
import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { fmtDateTime, relativeTime } from "@/lib/format-time";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import {
  formatAutomationNext,
  formatAutomationNextTitle,
  formatAutomationSchedule,
} from "../model/presentation";
import { isLocalTriggerAutomation } from "../model/status";
import { DetailRow } from "./DetailRow";

export function TaskInformation({
  job,
  locale,
}: {
  job: SessionAutomationJob;
  locale: string;
}) {
  const { t } = useTranslation();
  const tx = (
    key: string,
    fallback: string,
    values?: Record<string, unknown>,
  ) => t(key, { defaultValue: fallback, ...values });
  const last = job.state.last_status;
  const lastStatus = last
    ? ({
        ok: t("settings.automations.status.completed"),
        error: t("settings.automations.status.failed"),
        skipped: t("settings.automations.skipped"),
      }[last] ?? last)
    : null;
  return (
    <Popover>
      <Button
        isIconOnly
        size="sm"
        variant="ghost"
        aria-label={t("settings.automations.taskInfo")}
      >
        <Info size={16} />
      </Button>
      <Popover.Content placement="bottom end">
        <Popover.Dialog
          aria-label={t("settings.automations.taskInfo")}
          className="automation-information"
        >
          <dl>
            <DetailRow label={t("settings.automations.labels.schedule")}>
              {formatAutomationSchedule(job, locale, tx)}
            </DetailRow>
            {!isLocalTriggerAutomation(job) && (
              <DetailRow
                label={t("settings.automations.sort.next")}
                title={formatAutomationNextTitle(job, locale, tx)}
              >
                {formatAutomationNext(job, tx)}
              </DetailRow>
            )}
            <DetailRow
              label={t("settings.automations.sort.last")}
              title={
                job.state.last_run_at_ms != null
                  ? fmtDateTime(job.state.last_run_at_ms, locale)
                  : undefined
              }
            >
              {job.state.last_run_at_ms != null ? (
                <>
                  {lastStatus && <span>{lastStatus} </span>}
                  {relativeTime(job.state.last_run_at_ms)}
                </>
              ) : (
                lastStatus || t("settings.automations.neverRun")
              )}
            </DetailRow>
            {job.schedule.kind === "cron" && job.schedule.tz && (
              <DetailRow label={t("settings.automations.fields.timezone")}>
                {job.schedule.tz}
              </DetailRow>
            )}
            {job.delete_after_run && (
              <DetailRow label={t("settings.automations.oneShot")}>
                {t("settings.automations.oneShotHint")}
              </DetailRow>
            )}
            {job.created_at_ms != null && (
              <DetailRow label={t("settings.automations.labels.created")}>
                {fmtDateTime(job.created_at_ms, locale)}
              </DetailRow>
            )}
            {job.updated_at_ms != null && (
              <DetailRow label={t("settings.automations.labels.updated")}>
                {fmtDateTime(job.updated_at_ms, locale)}
              </DetailRow>
            )}
            <DetailRow label="ID">
              <code>{job.id}</code>
            </DetailRow>
          </dl>
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  );
}
