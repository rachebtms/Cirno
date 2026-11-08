import { Alert, Button, Modal } from "@heroui/react";
import { CircleAlert } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import "../automations.css";

interface DeleteProps {
  job: SessionAutomationJob;
  deleting: boolean;
  error?: string | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: (job: SessionAutomationJob) => void | Promise<void>;
}
export function AutomationDeleteDialog({
  job,
  ...props
}: Omit<DeleteProps, "job"> & { job: SessionAutomationJob | null }) {
  const [busy, setBusy] = useState(false);
  const description = useId();
  const disabled = busy || props.deleting;
  return job ? (
    <Modal.Backdrop
      isOpen
      onOpenChange={props.onOpenChange}
      isDismissable={!disabled}
      isKeyboardDismissDisabled={disabled}
    >
      <Modal.Container size="sm">
        <Modal.Dialog role="alertdialog" aria-describedby={description}>
          <AutomationDeleteContent
            key={job.id}
            job={job}
            {...props}
            descriptionId={description}
            onBusyChange={setBusy}
          />
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  ) : null;
}
export function AutomationDeleteContent({
  job,
  deleting,
  error,
  onOpenChange,
  onConfirm,
  descriptionId,
  onBusyChange,
}: DeleteProps & {
  descriptionId?: string;
  onBusyChange?: (busy: boolean) => void;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const locked = useRef(false);
  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [onBusyChange, busy]);
  const disabled = deleting || busy;
  const remove = async () => {
    if (locked.current || deleting) return;
    locked.current = true;
    setBusy(true);
    setFailure("");
    try {
      await onConfirm(job);
    } catch (reason) {
      setFailure(reason instanceof Error ? reason.message : String(reason));
    } finally {
      locked.current = false;
      setBusy(false);
    }
  };
  return (
    <>
      <Modal.Header>
        <Modal.Heading>{t("settings.automations.deleteTitle")}</Modal.Heading>
        <Modal.CloseTrigger isDisabled={disabled} />
      </Modal.Header>
      <Modal.Body>
        <p id={descriptionId}>
          {t("settings.automations.deleteDescription", {
            name: job.name || job.id,
          })}
        </p>
      </Modal.Body>
      <Modal.Footer className="automation-dialog-footer">
        {(failure || error) && (
          <Alert status="danger" role="alert">
            <Alert.Indicator>
              <CircleAlert />
            </Alert.Indicator>
            <Alert.Content>
              <Alert.Description>{failure || error}</Alert.Description>
            </Alert.Content>
          </Alert>
        )}
        <div className="automation-dialog-actions">
          <Button
            autoFocus
            variant="ghost"
            isDisabled={disabled}
            onPress={() => onOpenChange(false)}
          >
            {t("settings.automations.cancel")}
          </Button>
          <Button
            variant="danger"
            isPending={disabled}
            onPress={() => {
              void remove();
            }}
          >
            {t("settings.automations.delete")}
          </Button>
        </div>
      </Modal.Footer>
    </>
  );
}
