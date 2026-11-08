import { Button, Link, Modal } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { MarkdownText } from "@/components/MarkdownText";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { DetailRow } from "../detail/DetailRow";
import { InlineError } from "@/ui/feedback/InlineError";
import "../automations.css";

export type AutomationRunRecord = NonNullable<
  SessionAutomationJob["state"]["run_history"]
>[number];
export type AutomationRunResult = {
  status: "loading" | "loaded" | "error";
  response: string | null;
  error?: string;
};
export function AutomationRunDialogView({
  job,
  run,
  locale,
  open,
  result,
  onRetry,
  onOpenChange,
}: {
  job: SessionAutomationJob;
  run: AutomationRunRecord;
  locale: string;
  open: boolean;
  result: AutomationRunResult;
  onRetry: () => void;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const status =
    {
      ok: t("settings.automations.status.completed"),
      error: t("settings.automations.status.failed"),
      skipped: t("settings.automations.skipped"),
    }[run.status] ?? t("settings.automations.calendar.recorded");
  const chatKey =
    run.webui_session_key !== undefined
      ? run.webui_session_key
      : job.origin?.channel === "websocket"
        ? job.origin.session_key
        : null;
  return (
    <Modal.Backdrop isOpen={open} onOpenChange={onOpenChange}>
      <Modal.Container size="lg">
        <Modal.Dialog className="automation-run-dialog">
          <Modal.Header>
            <Modal.Heading>{job.name || job.id}</Modal.Heading>
            <Modal.CloseTrigger />
            <time dateTime={new Date(run.run_at_ms).toISOString()}>
              {new Intl.DateTimeFormat(locale, {
                dateStyle: "medium",
                timeStyle: "short",
              }).format(run.run_at_ms)}
            </time>
          </Modal.Header>
          <Modal.Body>
            <dl>
              <DetailRow label={t("settings.automations.runDetails.result")}>
                <span data-failed={run.status === "error" || undefined}>
                  {status}
                </span>
              </DetailRow>
              {run.duration_ms != null && (
                <DetailRow
                  label={t("settings.automations.runDetails.duration")}
                >
                  {new Intl.NumberFormat(locale, {
                    style: "unit",
                    unit: "second",
                    unitDisplay: "short",
                    maximumFractionDigits: run.duration_ms < 1000 ? 3 : 1,
                  }).format(run.duration_ms / 1000)}
                </DetailRow>
              )}
            </dl>
            <InlineError message={run.error} />
            {result.status === "loading" ? (
              <p role="status" className="automation-hint">
                {t("settings.automations.runDetails.loading")}
              </p>
            ) : result.status === "error" ? (
              <div className="automation-run-error">
                <InlineError
                  message={
                    result.error ||
                    t("settings.automations.runDetails.loadError")
                  }
                />
                <Button variant="secondary" size="sm" onPress={onRetry}>
                  {t("settings.automations.runDetails.retry")}
                </Button>
              </div>
            ) : result.response?.trim() ? (
              <MarkdownText>{result.response}</MarkdownText>
            ) : (
              <p className="automation-hint">
                {t(
                  result.response === null
                    ? "settings.automations.runDetails.noOutput"
                    : "settings.automations.runDetails.emptyOutput",
                )}
              </p>
            )}
          </Modal.Body>
          {chatKey && (
            <Modal.Footer>
              <Link href={`#/chat/${encodeURIComponent(chatKey)}`}>
                {t("settings.automations.emptyAction")}
              </Link>
            </Modal.Footer>
          )}
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
