import { Button, Card, Form, Input, Label, ListBox, Select, Switch, Description, TextArea, TextField } from "@heroui/react";
import { Eye, Save, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SecretInput } from "@/ui/fields/SecretInput";
import { SSHCredentialFields } from "./SSHCredentialFields";
import { credentialKinds, type CredentialDraft, type CredentialKind, type CredentialPatch } from "../model/contracts";

export function CredentialEditor({ draft, busy, update, cancel, reveal, save, scan, fingerprints, loadSSH, visible, toggleVisible }: {
  draft: CredentialDraft; busy: boolean; visible: boolean; toggleVisible: () => void;
  update: (patch: CredentialPatch) => void;
  cancel: () => void; reveal: () => Promise<void>; save: () => Promise<void>; scan: () => Promise<void>; fingerprints: string; loadSSH: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const concealed = draft.kind === "password" || draft.kind === "token";
  return <Card className="credential-editor"><Card.Content>
    <Form onSubmit={event => { event.preventDefault(); void save(); }}>
      <TextField isRequired isDisabled={busy} value={draft.label} onChange={label => update({ label })}>
        <Label>{t("workspace.label")}</Label><Input autoFocus maxLength={120} />
      </TextField>
      <Select isDisabled={busy} value={draft.kind} onChange={kind => { if (kind !== null) update({ kind: String(kind) as CredentialKind }); }}>
        <Label>{t("workspace.recordType")}</Label>
        <Select.Trigger><Select.Value>{t(`workspace.kind.${draft.kind}`)}</Select.Value><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox>{credentialKinds.map(kind => <ListBox.Item key={kind} id={kind} textValue={t(`workspace.kind.${kind}`)}>
          {t(`workspace.kind.${kind}`)}<ListBox.ItemIndicator />
        </ListBox.Item>)}</ListBox></Select.Popover>
      </Select>
      {draft.kind === "password" && <TextField isDisabled={busy} value={draft.username} onChange={username => update({ username })}>
        <Label>{t("workspace.username")}</Label><Input autoComplete="off" maxLength={4096} />
      </TextField>}
      {draft.kind === "ssh" ? <>
        {!draft.sshLoaded && <Button variant="secondary" isDisabled={busy} onPress={() => { void loadSSH(); }}>{t("workspace.loadSSH")}</Button>}
        <SSHCredentialFields visible={visible} toggleVisible={toggleVisible} draft={draft} disabled={busy || !draft.sshLoaded} update={update} scan={scan} fingerprints={fingerprints} />
      </> : <TextField isRequired={!draft.id} isDisabled={busy} value={draft.value} onChange={value => update({ value })}>
        <Label>{t("workspace.secretValue")}</Label>
        {concealed ? <SecretInput visible={visible} onToggle={toggleVisible} disabled={busy} /> : <TextArea autoComplete="off" rows={6} />}
        {draft.id && <Description>{t("workspace.keepSecret")}</Description>}
      </TextField>}
      <Switch isSelected={draft.agentVisible} isDisabled={busy} onChange={agentVisible => update({ agentVisible })}>
        <Switch.Content><Switch.Control><Switch.Thumb /></Switch.Control><Label>{t("workspace.agentVisibility")}</Label></Switch.Content><Description>{t("workspace.agentVisibilityHint")}</Description>
      </Switch>
      <div className="credential-editor-actions">
        {draft.id && <Button size="sm" variant="secondary" isDisabled={busy || (draft.kind === "ssh" ? !draft.sshLoaded || !!draft.ssh.password || !draft.ssh.has_password : !!draft.value || !!draft.username)} onPress={() => { void reveal(); }}>
          <Eye size={16} />{t("workspace.reveal")}
        </Button>}
        <div className="credential-editor-submit">
          <Button variant="ghost" isDisabled={busy} onPress={cancel}><X size={16} />{t("files.cancel")}</Button>
          <Button type="submit" isPending={busy} isDisabled={!draft.label.trim() || (draft.kind === "ssh" ? !draft.sshLoaded : !draft.id && !draft.value)}><Save size={16} />{t("files.save")}</Button>
        </div>
      </div>
    </Form>
  </Card.Content></Card>;
}
