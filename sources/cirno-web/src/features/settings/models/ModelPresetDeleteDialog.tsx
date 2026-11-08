import { Button, Modal } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { SettingsPayload } from "@/lib/contracts/settings";
export function ModelPresetDeleteDialog({ preset, deleting, onOpenChange, onConfirm }: {
  preset: SettingsPayload["model_presets"][number] | null; deleting: boolean; onOpenChange: (open: boolean) => void; onConfirm: () => void;
}) {
  const { t } = useTranslation();
  return <Modal.Backdrop isOpen={preset !== null} onOpenChange={open => { if (!deleting) onOpenChange(open); }} isDismissable={!deleting} isKeyboardDismissDisabled={deleting}><Modal.Container size="sm"><Modal.Dialog role="alertdialog">
      <Modal.Header><Modal.Heading>{t("settings.models.deletePresetTitle")}</Modal.Heading></Modal.Header>
      <Modal.Body><p>{t("settings.models.deletePresetHelp", { name: preset?.name ?? "" })}</p></Modal.Body>
      <Modal.Footer><Button variant="secondary" isDisabled={deleting} onPress={() => onOpenChange(false)}>{t("settings.actions.cancel")}</Button>
        <Button variant="danger" isPending={deleting} onPress={onConfirm}>{t("settings.actions.delete")}</Button></Modal.Footer>
    </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
