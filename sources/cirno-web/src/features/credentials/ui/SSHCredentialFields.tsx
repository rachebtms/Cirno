import { SSHSessionFields } from "@/components/ssh/SSHSessionFields";
import { Button, Description, FieldError, Input, Label, ListBox, Select, Switch, TextArea, TextField } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { CredentialDraft, CredentialPatch, SSHFields } from "../model/contracts";

export function SSHCredentialFields({ draft, disabled, update, scan, fingerprints }: {
  draft: CredentialDraft; disabled: boolean; update: (patch: CredentialPatch) => void;
  scan: () => Promise<void>; fingerprints: string;
}) {
  const { t } = useTranslation();
  const change = (patch: Partial<SSHFields>) => update({ ssh: { ...draft.ssh, ...patch } });
  const auth = [{ id: "key", label: t("features.keyAuthentication") }, { id: "password", label: t("features.passwordAuthentication") }];
  return <>
    <div className="credential-ssh-grid">
      {(["host", "username"] as const).map(key => <TextField key={key} isRequired isDisabled={disabled} value={draft.ssh[key]} onChange={value => change({ [key]: value })}>
        <Label>{t(key === "host" ? "features.host" : "features.sshUser")}</Label><Input autoComplete="off" /><div className="credential-validation"><FieldError /></div>
      </TextField>)}
      <TextField isRequired isDisabled={disabled} value={draft.ssh.port} onChange={port => change({ port })}>
        <Label>{t("features.sshPort")}</Label><Input type="number" min={1} max={65535} step={1} /><div className="credential-validation"><FieldError /></div>
      </TextField>
      <Select isDisabled={disabled} value={draft.ssh.auth_method} onChange={key => { if (key !== null) change({ auth_method: key as "key" | "password" }); }}>
        <Label>{t("features.authentication")}</Label><Select.Trigger><Select.Value>{auth.find(row => row.id === draft.ssh.auth_method)?.label}</Select.Value><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox items={auth}>{row => <ListBox.Item id={row.id} textValue={row.label}>{row.label}<ListBox.ItemIndicator /></ListBox.Item>}</ListBox></Select.Popover>
      </Select>
    </div>
    {draft.ssh.auth_method === "password" ? <TextField isRequired={!draft.ssh.has_password} isDisabled={disabled} value={draft.ssh.password} onChange={password => change({ password })}>
      <Label>{t("features.password")}</Label><Input type="password" autoComplete="new-password" />
      {draft.ssh.has_password && <Description>{t("features.keepPassword")}</Description>}<div className="credential-validation"><FieldError /></div>
    </TextField> : <TextField isDisabled={disabled} value={draft.ssh.identity_file} onChange={identity_file => change({ identity_file })}>
      <Label>{t("features.identityFile")}</Label><Input autoComplete="off" />
    </TextField>}
    <TextField isDisabled={disabled} value={draft.ssh.host_key} onChange={host_key => change({ host_key })}>
      <Label>{t("features.hostKey")}</Label><TextArea autoComplete="off" rows={3} />
    </TextField>
    <Button variant="secondary" size="sm" isDisabled={disabled || !draft.ssh.host.trim() || !/^\d+$/.test(draft.ssh.port) || Number(draft.ssh.port) < 1 || Number(draft.ssh.port) > 65535} onPress={() => { void scan(); }}>{t("features.scanKey")}</Button>
    {fingerprints && <div role="status" className="credential-fingerprints"><p>{t("features.fingerprintNotice")}</p><pre>{fingerprints}</pre></div>}
    <Switch isSelected={draft.nodeEnabled} isDisabled={disabled} onChange={nodeEnabled => update({ nodeEnabled })}>
      <Switch.Content><Switch.Control><Switch.Thumb /></Switch.Control><Label>{t("workspace.sshNodeAccess")}</Label></Switch.Content><Description>{t("workspace.sshNodeAccessHint")}</Description>
    </Switch>
    {draft.nodeEnabled && <SSHSessionFields value={draft.session} onChange={session => update({ session })} disabled={disabled} />}
  </>;
}
