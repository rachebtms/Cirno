import { Input, Label, TextField } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { CustomProviderDraft, ProviderAdvancedField } from "../providerForm";
import { ProviderAdvancedOptions } from "../ProviderAdvancedOptions";
import { ProviderAPIControl } from "../ProviderAPIControl";
import { ProviderSecretField } from "./ProviderSecretField";
const customFields: ProviderAdvancedField[] = ["extra_headers", "extra_body", "extra_query", "use_proxy", "thinking_style"];
export function CustomProviderEditor({ draft, onChange, disabled, apiSupported, onConfigureProxy }: {
  draft: CustomProviderDraft; onChange: (value: Partial<CustomProviderDraft>) => void;
  disabled: boolean; apiSupported?: boolean; onConfigureProxy?: () => void;
}) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  return <fieldset disabled={disabled} className="provider-fields min-w-0 border-0 p-0"><TextField isDisabled={disabled} isRequired value={draft.name} onChange={name => onChange({ name })}>
    <Label>{t("settings.providers.customProviderName")}</Label><Input autoFocus placeholder={t("settings.providers.customProviderNamePlaceholder")} /></TextField>
    <TextField isDisabled={disabled} isRequired value={draft.apiBase} onChange={apiBase => onChange({ apiBase })}><Label>{t("settings.byok.apiBase")}</Label><Input placeholder="https://api.example.com/v1" spellCheck={false} autoComplete="off" /></TextField>
    <ProviderSecretField value={draft.apiKey} onChange={apiKey => onChange({ apiKey })} visible={visible} onToggle={() => setVisible(!visible)} disabled={disabled} />
    <ProviderAdvancedOptions fields={customFields} form={draft} onChange={onChange} onConfigureProxy={onConfigureProxy}>
      {apiSupported && <ProviderAPIControl value={draft.api} onChange={api => onChange({ api })} />}
    </ProviderAdvancedOptions>
  </fieldset>;
}
