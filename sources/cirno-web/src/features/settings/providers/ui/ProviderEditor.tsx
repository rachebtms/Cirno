import { Alert, Description } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { ProviderRow, ProviderSettingsProps } from "../model/contracts";
import { providerEditor } from "../model/providerEditor";
import { providerFormFromRow } from "../providerForm";
import { ProviderAdvancedOptions } from "../ProviderAdvancedOptions";
import { ProviderRequestOptions } from "../ProviderRequestOptions";
import { ProviderAPIControl } from "../ProviderAPIControl";
import { ModelAPIControl } from "../../models/ModelAPIControl";
import { ProviderConnectionFields } from "./ProviderConnectionFields";
import { ProviderOAuthFields } from "./ProviderOAuthFields";
export function ProviderEditor({ provider, options, disabled }: { provider: ProviderRow; options: ProviderSettingsProps; disabled: boolean }) {
  const { t } = useTranslation();
  const form = options.providerForms[provider.id] ?? providerFormFromRow(provider);
  const state = providerEditor(provider, form);
  const change = (value: Partial<typeof form>) => options.onChangeProviderForm(provider.id, value);
  const support = { bedrock: "bedrock", azure_openai: "azure" }[provider.id];
  const feature = options.cirnoFeatures?.features.find(item => item.name === support);
  return <div className="provider-fields">
    {feature && !feature.installed && <Description>{t("settings.capabilities.providerInstallOnSave")}</Description>}
    {support && options.capabilityError && <Alert status="danger" role="alert"><Alert.Description>{options.capabilityError}</Alert.Description></Alert>}
    {state.oauth ? <ProviderOAuthFields provider={provider} options={options} disabled={disabled} dirty={state.dirty} />
      : <ProviderConnectionFields provider={provider} form={form} options={options} disabled={disabled} />}
    <ProviderRequestOptions providerName={provider.id} apiConfigurable={provider.provider_api_configurable === true} form={form} onChange={change} />
    {(!state.oauth || state.advanced) && <ProviderAdvancedOptions fields={provider.advanced_fields ?? []} form={form} onChange={change} onConfigureProxy={options.onConfigureProxy}>
      {!state.oauth && provider.provider_api_configurable && (provider.id === "openai"
        ? <ModelAPIControl provider={provider} title={t("settings.providers.defaultAPI")} description={t("settings.providers.openaiDefaultAPIDescription")} value={form.api} onChange={api => change({ api })} />
        : <ProviderAPIControl value={form.api} onChange={api => change({ api })} />)}
    </ProviderAdvancedOptions>}
  </div>;
}
