import { Alert, Button, Form, Input, Label, Modal, TextField } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { DirectoryModel, FileEntry } from "../model/useDirectory";

export function CreateEntryDialog({ kind, directory, onClose, onCreated }: {
  kind: FileEntry["kind"]; directory: DirectoryModel; onClose: () => void; onCreated: (entry: FileEntry) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function create() {
    setSaving(true); setError("");
    try { const entry = await directory.create(kind, name.trim()); onCreated(entry); onClose(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSaving(false); }
  }
  return <Modal.Backdrop isOpen onOpenChange={open => { if (!open && !saving) onClose(); }} isDismissable={!saving} isKeyboardDismissDisabled={saving}><Modal.Container size="sm"><Modal.Dialog>
      <Modal.Header><Modal.Heading>{t(`files.${kind === "file" ? "newFile" : "newFolder"}`)}</Modal.Heading><p className="files-dialog-path">{directory.directory?.path}</p></Modal.Header>
      <Form onSubmit={event => { event.preventDefault(); void create(); }}>
        <Modal.Body><TextField isRequired isDisabled={saving} value={name} onChange={setName}><Label>{t("files.name")}</Label><Input autoFocus /></TextField>
          {error && <Alert status="danger" role="alert"><Alert.Description>{error}</Alert.Description></Alert>}
        </Modal.Body>
        <Modal.Footer><Button variant="secondary" isDisabled={saving} onPress={onClose}>{t("files.cancel")}</Button>
          <Button type="submit" isPending={saving} isDisabled={!name.trim()}>{t("files.create")}</Button></Modal.Footer>
      </Form>
    </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
