import { Button, Modal } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { DocumentViewModel } from "../model/useDocumentView";
export function DiscardDocumentDialog({ model }: { model: DocumentViewModel }) {
  const { t } = useTranslation();
  return <Modal.Backdrop isOpen={model.pending !== null} onOpenChange={open => { if (!open) model.setPending(null); }} ><Modal.Container size="sm"><Modal.Dialog role="alertdialog">
      <Modal.Header><Modal.Heading>{t("files.discardTitle")}</Modal.Heading></Modal.Header>
      <Modal.Body><p>{t("files.discardDescription")}</p></Modal.Body>
      <Modal.Footer><Button variant="secondary" onPress={() => model.setPending(null)}>{t("files.cancel")}</Button>
        <Button variant="danger" onPress={model.discard}>{t("files.discard")}</Button></Modal.Footer>
    </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
