import { Alert, Button, FieldError, Form, Input, Label, ListBox, Modal, Select, TextField } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { CircleAlert } from "lucide-react";
import type { NodesController } from "../model/useNodes";

export function NodeEditor({ nodes }: { nodes: NodesController }) {
  const { t } = useTranslation(), draft = nodes.draft;
  if (!draft) return null;
  const options = nodes.credentials.filter(record => !record.node_enabled || record.id === draft.id);
  return <Modal.Backdrop isOpen onOpenChange={open => { if (!open) nodes.setDraft(null); }} isDismissable={!nodes.busy} isKeyboardDismissDisabled={nodes.busy}>
    <Modal.Container size="lg"><Modal.Dialog className="node-editor-dialog"><Form onSubmit={event => { event.preventDefault(); void nodes.save(); }}>
      <Modal.Header><Modal.Heading>{t(draft.id ? "features.edit" : "features.addNode")}</Modal.Heading><Modal.CloseTrigger isDisabled={nodes.busy} /></Modal.Header>
      <Modal.Body>
        <p className="node-help">{t("workspace.sshNodePickerHint")}</p>
        <Select isRequired isDisabled={nodes.busy || !!draft.id} value={draft.credential_id || null} onChange={key => nodes.setDraft(old => old && ({ ...old, credential_id: String(key ?? "") }))}>
          <Label>{t("workspace.sshCredential")}</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
          <Select.Popover><ListBox items={options}>{record => <ListBox.Item id={record.id} textValue={record.label}>{record.label}<ListBox.ItemIndicator /></ListBox.Item>}</ListBox></Select.Popover>
        </Select>
        {!options.length && <p className="node-help">{t("workspace.noSSHCredentials")}</p>}
        <TextField isRequired isDisabled={nodes.busy} value={draft.working_directory} onChange={working_directory => nodes.setDraft(old => old && ({ ...old, working_directory }))}>
          <Label>{t("features.remoteDirectory")}</Label><Input /><FieldError />
        </TextField>
      </Modal.Body>
      <Modal.Footer className="node-dialog-footer">
        {nodes.error && <Alert status="danger" role="alert"><Alert.Indicator><CircleAlert /></Alert.Indicator><Alert.Content><Alert.Description>{nodes.error}</Alert.Description></Alert.Content></Alert>}
        <div className="node-dialog-buttons"><Button variant="ghost" isDisabled={nodes.busy} onPress={() => nodes.setDraft(null)}>{t("features.cancel")}</Button>
          <Button type="submit" isPending={nodes.busy} isDisabled={!draft.credential_id}>{t("features.save")}</Button></div>
      </Modal.Footer>
    </Form></Modal.Dialog></Modal.Container>
  </Modal.Backdrop>;
}
