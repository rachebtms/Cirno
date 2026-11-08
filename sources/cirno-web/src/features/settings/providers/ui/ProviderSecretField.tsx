import { Button, InputGroup, Label, TextField } from "@heroui/react";
import { Eye, EyeOff, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";
export function ProviderSecretField({ value, onChange, visible, onToggle, hint, onEdit, disabled }: {
  value: string; onChange: (value: string) => void; visible: boolean; onToggle: () => void;
  hint?: string | null; onEdit?: () => void; disabled?: boolean;
}) {
  const { t } = useTranslation();
  return <TextField value={hint ? "" : value} onChange={onChange} isDisabled={disabled} isReadOnly={Boolean(hint)}>
    <Label>{t("settings.byok.apiKey")}</Label>
    <InputGroup><InputGroup.Input type={hint || visible ? "text" : "password"} placeholder={hint ?? t("settings.byok.apiKeyPlaceholder")} autoComplete="off" spellCheck={false} />
      <InputGroup.Suffix><Button isIconOnly variant="ghost" size="sm" isDisabled={disabled}
        aria-label={hint ? t("settings.actions.edit") : t(`settings.byok.${visible ? "hideApiKey" : "showApiKey"}`)}
        onPress={hint ? onEdit : onToggle}>{hint ? <Pencil size={16} /> : visible ? <EyeOff size={16} /> : <Eye size={16} />}</Button></InputGroup.Suffix>
    </InputGroup>
  </TextField>;
}
