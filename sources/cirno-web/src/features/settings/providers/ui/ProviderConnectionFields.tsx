import { Input, Label, TextField } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { ProviderSettingsProps, ProviderRow } from "../model/contracts";
import type { ProviderForm } from "../providerForm";
import { ProviderSecretField } from "./ProviderSecretField";
export function ProviderConnectionFields({ provider, form, options, disabled }: {
  provider: ProviderRow; form: ProviderForm; options: ProviderSettingsProps; disabled: boolean;
}) {
  const { t } = useTranslation();
  const change = (value: Partial<ProviderForm>) => options.onChangeProviderForm(provider.id, value);
  const editing = !provider.api_key_hint || options.editingProviderKeys[provider.id];
  return <div className="provider-fields">
    {provider.is_custom && <TextField value={form.displayName} onChange={displayName => change({ displayName })} isDisabled={disabled}><Label>{t("settings.providers.customProviderName")}</Label><Input /></TextField>}
    <ProviderSecretField value={form.apiKey} onChange={apiKey => change({ apiKey })} disabled={disabled}
      visible={Boolean(options.visibleProviderKeys[provider.id])} onToggle={() => options.onToggleProviderKey(provider.id)}
      hint={editing ? undefined : provider.api_key_hint} onEdit={() => options.onToggleProviderKeyEditing(provider.id)} />
    <TextField value={form.apiBase} onChange={apiBase => change({ apiBase })} isDisabled={disabled}>
      <Label>{t("settings.byok.apiBase")}</Label><Input placeholder={provider.default_api_base ?? t("settings.byok.apiBasePlaceholder")} autoComplete="off" spellCheck={false} />
    </TextField>
  </div>;
}
