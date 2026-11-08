import { Alert, Button, Form, Input, Label, Modal, TextField } from "@heroui/react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ProjectSummary } from "@/lib/contracts/conversations";
import { useMutation } from "@/ui/resources/useMutation";
import { useComposingEscape } from "@/ui/fields/useComposingEscape";
import { useConversationCatalog } from "../catalog/context";
export function ProjectDialog({ project, onClose, open }: { project: ProjectSummary | null; onClose: () => void; open: boolean }) {
  const { t } = useTranslation();
  const headingId = useId();
  const catalog = useConversationCatalog();
  const composition = useComposingEscape();
  const [name, setName] = useState(project?.name ?? "");
  const [directory, setDirectory] = useState(project?.working_directory ?? "");
  const mutation = useMutation(catalog.owner);
  const saving = mutation.busy, error = mutation.error;
  const save = () => mutation.run(() => catalog.saveProject({
    ...(project ? { id: project.id } : {}), name: name.trim(), working_directory: directory.trim(),
  }), onClose);
  return <Modal.Backdrop isOpen={open} onOpenChange={next => { if (!next && !saving) onClose(); }} isDismissable={!saving} isKeyboardDismissDisabled={saving}><Modal.Container size="sm"><Modal.Dialog aria-labelledby={headingId} className="conversation-project-dialog">
    <Modal.Header><Modal.Heading id={headingId}>{project ? t("conversationCatalog.renameProject", { name: project.name }) : t("conversationCatalog.newProject")}</Modal.Heading></Modal.Header>
    <Form {...composition} onSubmit={event => { event.preventDefault(); void save(); }}>
      <Modal.Body className="flex flex-col gap-4">
        <TextField isRequired isDisabled={saving} value={name} onChange={setName}><Label>{t("conversationCatalog.projectName")}</Label><Input autoFocus maxLength={120} /></TextField>
        <TextField isDisabled={saving} value={directory} onChange={setDirectory}><Label>{t("conversationCatalog.directory")}</Label><Input maxLength={4096} /></TextField>
        {error && <Alert status="danger" role="alert"><Alert.Description>{error}</Alert.Description></Alert>}
      </Modal.Body>
      <Modal.Footer><Button variant="secondary" isDisabled={saving} onPress={onClose}>{t("common.cancel")}</Button>
        <Button type="submit" isPending={saving} isDisabled={saving || !name.trim()}>{t(project ? "chat.renameSave" : "conversationCatalog.create")}</Button></Modal.Footer>
    </Form>
  </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
