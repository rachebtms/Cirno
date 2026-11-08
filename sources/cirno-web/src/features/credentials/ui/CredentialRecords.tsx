import { Button, Card } from "@heroui/react";
import { KeyRound, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CredentialInfo } from "../model/contracts";

export function CredentialRecords({ records, disabled, deleting, confirm, edit, remove }: {
  records: CredentialInfo[]; disabled: boolean; deleting: string | null;
  confirm: (id: string | null) => void; edit: (record: CredentialInfo) => void; remove: (id: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  return <Card className="credential-records"><ul>{records.map(record => <li key={record.id}>
    <KeyRound size={18} className="credential-record-icon" />
    <Button className="credential-record-label" variant="ghost" isDisabled={disabled} onPress={() => edit(record)}>
      <span><strong>{record.label}</strong><small>{t(`workspace.kind.${record.kind}`)}{record.node_enabled ? ` · ${t("workspace.sshNode")}` : ""} · {t(record.agent_visible ? "workspace.agentVisible" : "workspace.agentHidden")}</small></span>
    </Button>
    {deleting === record.id ? <div className="credential-delete-confirm">
      <span>{t("workspace.deleteRecord")}</span>
      <Button size="sm" variant="ghost" isDisabled={disabled} onPress={() => confirm(null)}>{t("files.cancel")}</Button>
      <Button size="sm" variant="danger" isDisabled={disabled} onPress={() => { void remove(record.id); }}>{t("workspace.delete")}</Button>
    </div> : <Button isIconOnly size="sm" variant="ghost" aria-label={t("workspace.delete")} isDisabled={disabled} onPress={() => confirm(record.id)}><Trash2 size={16} /></Button>}
  </li>)}</ul></Card>;
}
