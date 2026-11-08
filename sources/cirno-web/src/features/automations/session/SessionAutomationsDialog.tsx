import { headerControlClassName } from "@/components/thread/header-control";
import "@/features/automations/automations.css";
import { Button, Modal } from "@heroui/react";
import { CalendarClock } from "lucide-react";
import { lazy, Suspense, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { SurfaceErrorBoundary } from "@/components/SurfaceErrorBoundary";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import { InlineError } from "@/ui/feedback/InlineError";
import { SessionTaskList } from "./SessionTaskList";
import type { AutomationAction } from "@/features/automations/model/status";
import { currentLocale } from "@/i18n";
import type {
  AutomationUpdatePayload,
  SessionAutomationJob,
} from "@/lib/contracts/automations";

const DetailContent = lazy(() =>
  import("@/features/automations/detail/AutomationDetailDialog").then(
    (module) => ({ default: module.AutomationDetailContent }),
  ),
);
const EditContent = lazy(() =>
  import("@/features/automations/edit/AutomationEditDialog").then((module) => ({
    default: module.AutomationEditContent,
  })),
);
const DeleteContent = lazy(() =>
  import("@/features/automations/ui/AutomationDeleteDialog").then((module) => ({
    default: module.AutomationDeleteContent,
  })),
);
type Screen =
  | { kind: "list" }
  | { kind: "detail" | "edit" | "delete"; job: SessionAutomationJob };

export function SessionAutomationsDialog({
  title,
  jobs,
  loading,
  loadError,
  now,
  onAction,
  onEdit,
  onSurfacesOpenChange,
  calendarHref,
  onOpenCalendar,
}: {
  title: string;
  jobs: SessionAutomationJob[];
  loading: boolean;
  loadError: string | null;
  now: number;
  onAction: (
    action: AutomationAction,
    job: SessionAutomationJob,
  ) => Promise<SessionAutomationJob[]>;
  onEdit: (
    job: SessionAutomationJob,
    values: AutomationUpdatePayload,
  ) => Promise<SessionAutomationJob[]>;
  onSurfacesOpenChange?: (open: boolean) => void;
  calendarHref?: string;
  onOpenCalendar?: () => void;
}) {
  const { t } = useTranslation();
  const [{ view: active, open }, setOverlay] = useState<{
    view: Screen;
    open: boolean;
  }>({ view: { kind: "list" }, open: false });
  const [actionKey, setActionKey] = useState<string | null>(null),
    [error, setError] = useState<string | null>(null);
  const [contentBusy, setContentBusy] = useState(false);
  const inFlight = useRef(false),
    description = useId();
  const busy = contentBusy || actionKey !== null;
  useEffect(() => {
    setOverlay((current) => {
      const view = current.view;
      if (!current.open || view.kind !== "detail") return current;
      const live = jobs.find((job) => job.id === view.job.id);
      return {
        ...current,
        view: live ? { kind: "detail", job: live } : { kind: "list" },
      };
    });
  }, [jobs]);
  useEffect(() => {
    onSurfacesOpenChange?.(open);
  }, [onSurfacesOpenChange, open]);
  const show = (next: Screen) => {
    setError(null);
    setOverlay({ view: next, open: true });
  };
  const inspect = (job: SessionAutomationJob) => show({ kind: "detail", job });
  const close = () => {
    if (active.kind === "edit" || active.kind === "delete") inspect(active.job);
    else setOverlay((current) => ({ ...current, open: false }));
  };
  const mutate = async (
    key: string,
    operation: () => Promise<SessionAutomationJob[]>,
    complete: (jobs: SessionAutomationJob[]) => void,
  ) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setActionKey(key);
    setError(null);
    try {
      complete(await operation());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      inFlight.current = false;
      setActionKey(null);
    }
  };
  const act = (action: AutomationAction, job: SessionAutomationJob) =>
    mutate(
      `${action}:${job.id}`,
      () => onAction(action, job),
      (next) => {
        if (action === "delete") show({ kind: "list" });
        else inspect(next.find((row) => row.id === job.id) ?? job);
      },
    );
  const edit = (job: SessionAutomationJob, values: AutomationUpdatePayload) =>
    mutate(
      `update:${job.id}`,
      () => onEdit(job, values),
      (next) => inspect(next.find((row) => row.id === job.id) ?? job),
    );
  const placeholder = (failed: boolean) => (
    <>
      <Modal.Header>
        <Modal.Heading>
          {active.kind === "list" ? title : active.job.name || active.job.id}
        </Modal.Heading>
        <Modal.CloseTrigger />
      </Modal.Header>
      <Modal.Body>
        {failed ? (
          <InlineError message={t("thread.sessionInfo.loadFailed")} />
        ) : (
          <SkeletonStatus
            label={t("thread.sessionInfo.loading")}
            className="h-24"
          >
            <div className="h-24 rounded-lg bg-surface-secondary" />
          </SkeletonStatus>
        )}
      </Modal.Body>
    </>
  );
  const content =
    active.kind === "list" ? (
      <SessionTaskList
        title={title}
        jobs={jobs}
        loading={loading}
        loadError={loadError}
        now={now}
        onInspect={inspect}
        calendarHref={calendarHref}
        onOpenCalendar={onOpenCalendar}
      />
    ) : (
      <SurfaceErrorBoundary
        key={`${active.kind}:${active.job.id}`}
        fallback={placeholder(true)}
      >
        <Suspense fallback={placeholder(false)}>
          {active.kind === "detail" && (
            <DetailContent
              job={active.job}
              locale={currentLocale()}
              actionKey={actionKey}
              error={error}
              onBusyChange={setContentBusy}
              onAction={act}
              onRequestEdit={(job) => show({ kind: "edit", job })}
              onRequestDelete={(job) => show({ kind: "delete", job })}
            />
          )}
          {active.kind === "edit" && (
            <EditContent
              job={active.job}
              saving={actionKey !== null}
              error={error}
              onBusyChange={setContentBusy}
              onSave={edit}
              onOpenChange={close}
            />
          )}
          {active.kind === "delete" && (
            <DeleteContent
              job={active.job}
              deleting={actionKey !== null}
              error={error}
              onBusyChange={setContentBusy}
              descriptionId={description}
              onConfirm={(job) => act("delete", job)}
              onOpenChange={close}
            />
          )}
        </Suspense>
      </SurfaceErrorBoundary>
    );
  return (
    <Modal
      isOpen={open}
      onOpenChange={(value) => {
        if (value) show({ kind: "list" });
        else close();
      }}
    >
      <Button
        variant="ghost"
        className={headerControlClassName}
        isIconOnly
        size="sm"
        aria-label={t("thread.header.sessionInfo")}
      >
        <CalendarClock size={17} />
      </Button>
      <Modal.Backdrop isDismissable={!busy} isKeyboardDismissDisabled={busy}>
        <Modal.Container size="lg">
          <Modal.Dialog
            className={
              active.kind === "edit"
                ? "automation-edit-dialog"
                : "automation-detail-dialog"
            }
            role={active.kind === "delete" ? "alertdialog" : "dialog"}
            aria-describedby={
              active.kind === "delete" ? description : undefined
            }
          >
            {content}
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </Modal>
  );
}
