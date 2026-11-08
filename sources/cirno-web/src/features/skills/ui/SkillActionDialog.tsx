import "./skill-detail.css";
import { Button, Modal } from "@heroui/react";
import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import type { useMutation } from "@/ui/resources/useMutation";
export function SkillActionDialog({
  title,
  description,
  action,
  danger,
  operation,
  onConfirm,
  onClose,
}: {
  title: string;
  description: ReactNode;
  action: string;
  danger?: boolean;
  operation: ReturnType<typeof useMutation>;
  onConfirm: () => unknown;
  onClose: () => void;
}) {
  const { t } = useTranslation(),
    descriptionId = useId();
  return (
    <Modal.Backdrop
      isOpen
      isDismissable={!operation.busy}
      isKeyboardDismissDisabled={operation.busy}
      onOpenChange={(open) => {
        if (!open && !operation.busy) onClose();
      }}
    >
      <Modal.Container size="sm">
        <Modal.Dialog role="alertdialog" aria-describedby={descriptionId}>
          <Modal.Header>
            <Modal.Heading>{title}</Modal.Heading>
          </Modal.Header>
          <Modal.Body>
            <div id={descriptionId} className="skill-action-description">
              {description}
            </div>
          </Modal.Body>
          <Modal.Footer className="skill-action-footer">
            <InlineError message={operation.error} />
            <div className="skill-actions">
              <Button autoFocus variant="secondary" isDisabled={operation.busy} onPress={onClose}>
                {t("common.cancel")}
              </Button>
              <Button
                variant={danger ? "danger" : "primary"}
                isPending={operation.busy}
                onPress={() => {
                  void onConfirm();
                }}
              >
                {action}
              </Button>
            </div>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
