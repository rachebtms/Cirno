import { Button, Link, Modal } from "@heroui/react";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import { InlineError } from "@/ui/feedback/InlineError";
import { SessionAutomationRow } from "../ui/SessionAutomationRow";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
export function SessionTaskList({
  title,
  jobs,
  loading,
  loadError,
  now,
  onInspect,
  calendarHref,
  onOpenCalendar,
}: {
  title: string;
  jobs: SessionAutomationJob[];
  loading: boolean;
  loadError: string | null;
  now: number;
  onInspect: (job: SessionAutomationJob) => void;
  calendarHref?: string;
  onOpenCalendar?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <Modal.Header>
        <Modal.Heading>
          {title || t("thread.sessionInfo.untitled")}
        </Modal.Heading>
        <Modal.CloseTrigger />
      </Modal.Header>
      <Modal.Body>
        <InlineError message={loadError} />
        <div className="session-automation-summary">
          <span>{t("thread.sessionInfo.automations")}</span>
          <span>
            {loading && !jobs.length
              ? "—"
              : t("thread.sessionInfo.count", { count: jobs.length })}
          </span>
        </div>
        {loading && !jobs.length ? (
          <SkeletonStatus
            label={t("thread.sessionInfo.loading")}
            className="space-y-2"
          >
            {[0, 1, 2].map((index) => (
              <div
                key={index}
                data-session-job-skeleton
                className="h-12 rounded-lg bg-surface-secondary"
              />
            ))}
          </SkeletonStatus>
        ) : jobs.length ? (
          jobs.map((job) => (
            <SessionAutomationRow
              key={job.id}
              job={job}
              now={now}
              onSelect={onInspect}
            />
          ))
        ) : !loadError ? (
          <p className="automation-hint">{t("thread.sessionInfo.empty")}</p>
        ) : null}
      </Modal.Body>
      <Modal.Footer>
        {calendarHref ? (
          <Link href={calendarHref} onPress={onOpenCalendar}>
            {t("thread.sessionInfo.openCalendar")}
            <ChevronRight size={15} />
          </Link>
        ) : (
          <Button variant="ghost" size="sm" fullWidth onPress={onOpenCalendar}>
            {t("thread.sessionInfo.openCalendar")}
            <ChevronRight size={15} />
          </Button>
        )}
      </Modal.Footer>
    </>
  );
}
