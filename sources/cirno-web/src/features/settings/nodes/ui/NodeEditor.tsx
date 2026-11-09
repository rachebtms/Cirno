import { SSHSessionFields } from "@/components/ssh/SSHSessionFields";
import { Alert, Button, Form, Label, ListBox, Modal, Select } from "@heroui/react";
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
        <Select isRequired isDisabled={nodes.busy || !!draft.id} value={draft.credential_id || null} onChange={key => { if (key !== null) void nodes.selectCredential(String(key)); }}>
          <Label>{t("workspace.sshCredential")}</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
          <Select.Popover><ListBox items={options}>{record => <ListBox.Item id={record.id} textValue={record.label}>{record.label}<ListBox.ItemIndicator /></ListBox.Item>}</ListBox></Select.Popover>
        </Select>
        {!options.length && <p className="node-help">{t("workspace.noSSHCredentials")}</p>}
        <SSHSessionFields value={draft} onChange={next => nodes.setDraft(old => old && ({ ...old, ...next }))} disabled={nodes.busy} />
      </Modal.Body>
      <Modal.Footer className="node-dialog-footer">
        {nodes.error && <Alert status="danger" role="alert"><Alert.Indicator><CircleAlert /></Alert.Indicator><Alert.Content><Alert.Description>{nodes.error}</Alert.Description>{!nodes.credentialReady && draft.credential_id && <Button size="sm" onPress={() => void nodes.selectCredential(draft.credential_id)}>{t("common.retry")}</Button>}</Alert.Content></Alert>}
        <div className="node-dialog-buttons"><Button variant="ghost" isDisabled={nodes.busy} onPress={() => nodes.setDraft(null)}>{t("features.cancel")}</Button>
          <Button type="submit" isPending={nodes.busy} isDisabled={!draft.credential_id || !nodes.credentialReady || nodes.busy}>{t("features.save")}</Button></div>
      </Modal.Footer>
    </Form></Modal.Dialog></Modal.Container>
  </Modal.Backdrop>;
}
