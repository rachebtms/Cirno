import { Button, Description, FieldError, Input, Label, TextArea, TextField } from "@heroui/react";
import { Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SSHSessionDraft } from "./session";
import "./session.css";

export function SSHSessionFields({ value, onChange, disabled }: {
  value: SSHSessionDraft; onChange: (next: SSHSessionDraft) => void; disabled: boolean;
}) {
  const { t } = useTranslation();
  const update = (patch: Partial<SSHSessionDraft>) => onChange({ ...value, ...patch });
  return <div className="ssh-session-fields">
    <TextField isRequired isDisabled={disabled} value={value.working_directory} onChange={working_directory => update({ working_directory })}>
      <Label>{t("features.remoteDirectory")}</Label><Input autoComplete="off" /><FieldError />
    </TextField>
    <TextField isDisabled={disabled} value={value.init_script} onChange={init_script => update({ init_script })}>
      <Label>{t("features.nodeInitScript")}</Label><Input autoComplete="off" /><Description>{t("features.nodeInitScriptHint")}</Description>
    </TextField>
    <div className="ssh-environment-heading"><span>{t("features.nodeEnvironment")}</span>
      <Button size="sm" variant="ghost" isDisabled={disabled} onPress={() => update({ environment: [...value.environment, { id: crypto.randomUUID(), name: "", value: "" }] })}><Plus size={14} />{t("features.addVariable")}</Button>
    </div>
    {value.environment.map(entry => <div className="ssh-environment-row" key={entry.id}>
      <TextField isRequired isDisabled={disabled} value={entry.name} onChange={name => update({ environment: value.environment.map(old => old.id === entry.id ? { ...old, name } : old) })}>
        <Label>{t("features.variableName")}</Label><Input pattern="[A-Za-z_][A-Za-z0-9_]*" autoComplete="off" /><FieldError />
      </TextField>
      <TextField isDisabled={disabled} value={entry.value} onChange={next => update({ environment: value.environment.map(old => old.id === entry.id ? { ...old, value: next } : old) })}>
        <Label>{t("features.variableValue")}</Label><TextArea rows={1} autoComplete="off" />
      </TextField>
      <Button isIconOnly size="sm" variant="ghost" isDisabled={disabled} aria-label={t("features.removeVariable")} onPress={() => update({ environment: value.environment.filter(old => old.id !== entry.id) })}><X size={16} /></Button>
    </div>)}
  </div>;
}
