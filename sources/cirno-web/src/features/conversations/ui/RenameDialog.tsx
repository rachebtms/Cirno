import { Alert, Button, Form, Input, Label, Modal, TextField } from "@heroui/react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useConversationCatalog } from "../catalog/context";
import { useMutation } from "@/ui/resources/useMutation";
import { useComposingEscape } from "@/ui/fields/useComposingEscape";
export function RenameDialog({ sessionKey, title, onClose, open }: { sessionKey: string; title: string; onClose: () => void; open: boolean }) {
  const { t } = useTranslation();
  const headingId = useId();
  const catalog = useConversationCatalog();
  const composition = useComposingEscape();
  const [draft, setDraft] = useState(title);
  const mutation = useMutation(catalog.owner);
  const busy = mutation.busy, error = mutation.error;
  const save = () => mutation.run(() => catalog.rename(sessionKey, draft.trim()), onClose);
  return <Modal.Backdrop isOpen={open} onOpenChange={next => { if (!next && !busy) onClose(); }} isDismissable={!busy} isKeyboardDismissDisabled={busy}><Modal.Container size="sm"><Modal.Dialog aria-labelledby={headingId}>
    <Modal.Header><Modal.Heading id={headingId}>{t("chat.rename")}</Modal.Heading></Modal.Header>
    <Form {...composition} onSubmit={event => { event.preventDefault(); void save(); }}><Modal.Body>
      <TextField validationBehavior="aria" value={draft} onChange={next => { setDraft(next); mutation.clear(); }} isDisabled={busy} isInvalid={Boolean(error)} isRequired>
        <Label>{t("chat.renamePlaceholder")}</Label><Input autoFocus maxLength={160} />
      </TextField>
      {error && <Alert status="danger" role="alert"><Alert.Description>{error}</Alert.Description></Alert>}
    </Modal.Body><Modal.Footer><Button variant="secondary" isDisabled={busy} onPress={onClose}>{t("common.cancel")}</Button>
      <Button type="submit" isPending={busy} isDisabled={busy || !draft.trim()}>{t("chat.renameSave")}</Button></Modal.Footer></Form>
  </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
