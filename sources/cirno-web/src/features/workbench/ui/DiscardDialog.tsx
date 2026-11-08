import { Button, Modal } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { WorkbenchModel } from "../model/useWorkbench";
export function DiscardDialog({ model }: { model: WorkbenchModel }) {
  const { t } = useTranslation();
  const current = model.tabs.find(tab => tab.id === model.pendingClose);
  return <Modal.Backdrop isOpen={model.pendingClose !== null} onOpenChange={open => { if (!open) model.setPendingClose(null); }} ><Modal.Container size="sm"><Modal.Dialog role="alertdialog">
      <Modal.Header><Modal.Heading>{t("files.discardTitle")}</Modal.Heading></Modal.Header>
      <Modal.Body><p>{t(current?.type === "credentials" ? "workspace.discardDescription" : "files.discardDescription")}</p></Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onPress={() => model.setPendingClose(null)}>{t("files.cancel")}</Button>
        <Button variant="danger" onPress={() => {
          const id = model.pendingClose; model.setPendingClose(null); if (id) void model.close(id);
        }}>{t("files.discard")}</Button>
      </Modal.Footer>
    </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
