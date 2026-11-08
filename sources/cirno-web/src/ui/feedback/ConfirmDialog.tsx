import { Alert, Button, Modal } from "@heroui/react";
import { useId, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useMutation } from "@/ui/resources/useMutation";
export function ConfirmDialog({ title, description, action, danger = false, onConfirm, onClose, owner, open = true }: {
  title: string; description: ReactNode; action: string; danger?: boolean;
  onConfirm: () => void | Promise<void>; onClose: () => void; owner?: object; open?: boolean;
}) {
  const { t } = useTranslation();
  const headingId = useId();
  const mounted = useRef({}).current;
  const mutation = useMutation(owner ?? mounted);
  const busy = mutation.busy, error = mutation.error;
  const confirm = () => mutation.run(async () => { await onConfirm(); }, onClose);
  return <Modal.Backdrop isOpen={open} onOpenChange={next => { if (!next && !busy) onClose(); }} isDismissable={!busy} isKeyboardDismissDisabled={busy}><Modal.Container size="sm"><Modal.Dialog role="alertdialog" aria-labelledby={headingId}>
      <Modal.Header><Modal.Heading id={headingId}>{title}</Modal.Heading></Modal.Header>
      <Modal.Body><p>{description}</p>{error && <Alert role="alert" status="danger"><Alert.Description>{error}</Alert.Description></Alert>}</Modal.Body>
      <Modal.Footer><Button variant="secondary" isDisabled={busy} onPress={onClose}>{t("common.cancel")}</Button>
        <Button variant={danger ? "danger" : "primary"} isPending={busy} isDisabled={busy} onPress={() => void confirm()}>{action}</Button></Modal.Footer>
    </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
