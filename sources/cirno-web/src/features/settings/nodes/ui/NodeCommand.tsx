import { Alert, Button, Form, Label, Modal, TextArea, TextField } from "@heroui/react";
import { CircleAlert, Play } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { NodesController } from "../model/useNodes";

export function NodeCommand({ nodes }: { nodes: NodesController }) {
  const { t } = useTranslation();
  if (!nodes.target) return null;
  return <Modal.Backdrop isOpen onOpenChange={open => { if (!open) nodes.setTarget(null); }} isDismissable={!nodes.busy} isKeyboardDismissDisabled={nodes.busy}>
    <Modal.Container size="lg"><Modal.Dialog className="node-command-dialog"><Form onSubmit={event => { event.preventDefault(); void nodes.execute(); }}>
      <Modal.Header><Modal.Heading>{t("features.executeCommand")} · {nodes.target.name}</Modal.Heading><Modal.CloseTrigger isDisabled={nodes.busy} /></Modal.Header>
      <Modal.Body><TextField isRequired isDisabled={nodes.busy} value={nodes.command} onChange={nodes.setCommand}>
        <Label>{t("features.command")}</Label><TextArea autoFocus rows={6} autoComplete="off" />
      </TextField>
        {nodes.output !== null && <pre className="node-output" role="status">{nodes.exitCode !== null ? `${t("features.commandExitCode", { code: nodes.exitCode })}\n` : ""}{nodes.output || (nodes.exitCode ? "" : t("features.commandCompleted"))}</pre>}
      </Modal.Body>
      <Modal.Footer className="node-dialog-footer">
        {nodes.error && <Alert status="danger" role="alert"><Alert.Indicator><CircleAlert /></Alert.Indicator><Alert.Content><Alert.Description>{nodes.error}</Alert.Description></Alert.Content></Alert>}
        <div className="node-dialog-buttons"><Button variant="ghost" isDisabled={nodes.busy} onPress={() => nodes.setTarget(null)}>{t("features.close")}</Button>
          <Button type="submit" isPending={nodes.busy} isDisabled={!nodes.command.trim()}><Play size={16} />{t("features.runCommand")}</Button></div>
      </Modal.Footer>
    </Form></Modal.Dialog></Modal.Container>
  </Modal.Backdrop>;
}
