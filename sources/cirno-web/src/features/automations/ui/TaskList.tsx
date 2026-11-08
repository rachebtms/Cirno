import { Button } from "@heroui/react";
import { CircleAlert, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { formatAutomationSchedule } from "../model/presentation";
import { automationStatusKey } from "../model/status";

export function TaskList({
  jobs,
  loading,
  hasJobs,
  onInspect,
}: {
  jobs: SessionAutomationJob[];
  loading: boolean;
  hasJobs: boolean;
  onInspect: (job: SessionAutomationJob) => void;
}) {
  const { t, i18n } = useTranslation();
  if (loading)
    return (
      <SkeletonStatus
        label={t("settings.automations.loading")}
        className="automation-task-loading"
      >
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            data-automation-task-skeleton
            className="automation-task-skeleton"
          >
            <span />
            <span />
          </div>
        ))}
      </SkeletonStatus>
    );
  if (!jobs.length)
    return (
      <p className="automation-empty">
        {t(
          hasJobs
            ? "settings.automations.noMatches"
            : "settings.automations.empty",
        )}
      </p>
    );
  return (
    <ul className="automation-tasks">
      {jobs.map((job) => {
        const status = automationStatusKey(job);
        return (
          <li key={job.id}>
            <Button
              variant="ghost"
              className="automation-task"
              aria-haspopup="dialog"
              onPress={() => onInspect(job)}
            >
              <span className="automation-task-description">
                <span className="automation-task-name">
                  {job.name || job.id}
                </span>
                <span className="automation-task-schedule">
                  {formatAutomationSchedule(
                    job,
                    i18n.resolvedLanguage ?? i18n.language,
                    (key, fallback, values) =>
                      t(key, { defaultValue: fallback, ...values }),
                  )}
                </span>
              </span>
              {["running", "failed", "paused"].includes(status) && (
                <span className="automation-task-status" data-status={status}>
                  {status === "running" && (
                    <Loader2 className="animate-spin" size={14} />
                  )}
                  {status === "failed" && <CircleAlert size={14} />}
                  {t(`settings.automations.status.${status}`)}
                </span>
              )}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}
