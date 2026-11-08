import { Button, Modal } from "@heroui/react";
import { useTranslation } from "react-i18next";

export function RestartExitDialog({ leave, onClose, onRestart }: { leave: (() => void) | null; onClose: () => void; onRestart: () => void }) {
  const { t } = useTranslation();
  return <Modal.Backdrop isOpen={leave !== null} onOpenChange={open => { if (!open) onClose(); }} ><Modal.Container size="sm"><Modal.Dialog>
      <Modal.Header><Modal.Heading>{t("settings.exit.title")}</Modal.Heading></Modal.Header>
      <Modal.Body><p>{t("settings.exit.description")}</p></Modal.Body>
      <Modal.Footer><Button variant="secondary" onPress={() => { onClose(); leave?.(); }}>{t("settings.exit.later")}</Button>
        <Button onPress={() => { onClose(); onRestart(); }}>{t("app.system.restartAction")}</Button></Modal.Footer>
    </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
