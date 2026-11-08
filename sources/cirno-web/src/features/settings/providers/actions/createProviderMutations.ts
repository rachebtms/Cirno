import { updateProviderSettings, createProviderSettings } from "@/lib/api";
import type { ProviderSettingsUpdate } from "@/lib/contracts/models";
import {
  CUSTOM_PROVIDER_CREATION_KEY,
  providerFormFromRow,
  type CustomProviderDraft,
} from "../providerForm";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { ModelSettingsActionsOptions } from "../../modelOperations";
export function createProviderMutations({
  state,
  settings,
  client,
  t,
  applyPayload,
  setPendingRestartSections,
  setError,
  installCapabilities,
  providerBusy,
}: ModelSettingsActionsOptions) {
  const {
    providerSaving,
    providerForms,
    setProviderOperation,
    setProviderForms,
    setVisibleProviderKeys,
    setEditingProviderKeys,
  } = state;
  const saveProvider = async (providerName: string): Promise<boolean> => {
    if (providerSaving || providerBusy) return false;
    const provider = settings?.providers.find((item) => item.id === providerName);
    if (!provider) return false;
    const isOauthProvider = provider.auth_type === "oauth";
    const providerForm = providerForms[providerName] ?? providerFormFromRow(provider);
    const apiKey = providerForm.apiKey.trim();
    if (
      !isOauthProvider &&
      !provider.configured &&
      (provider.api_key_required ?? true) &&
      !apiKey
    ) {
      setError(t("settings.byok.apiKeyRequired"));
      return false;
    }
    setProviderOperation({ provider: providerName, action: "save" });
    try {
      const supportName =
        providerName === "bedrock" ? "bedrock" : providerName === "azure_openai" ? "azure" : null;
      if (supportName && !(await installCapabilities([supportName]))) return false;
      const update: ProviderSettingsUpdate = { provider: providerName };
      if (!isOauthProvider) {
        update.apiKey = apiKey || undefined;
        update.apiBase = providerForm.apiBase.trim();
        if (provider.is_custom) update.displayName = providerForm.displayName.trim();
        if (provider.provider_api_configurable) update.api = providerForm.api;
      }
      for (const field of provider.advanced_fields ?? []) {
        if (field === "use_proxy") update.use_proxy = providerForm.useProxy;
        if (field === "extra_headers") {
          update.extraHeaders = providerForm.extraHeaders.trim();
        }
        if (field === "extra_body") update.extraBody = providerForm.extraBody.trim();
        if (field === "extra_query") update.extraQuery = providerForm.extraQuery.trim();
        if (field === "thinking_style") {
          update.thinkingStyle = providerForm.thinkingStyle.trim();
        }
        if (field === "region") update.region = providerForm.region.trim();
        if (field === "profile") update.profile = providerForm.profile.trim();
      }
      const payload = await updateProviderSettings(client, update);
      applyPayload(payload, {
        preserveAgentForm: true,
        preserveCapabilityForms: true,
      });
      if (payload.requires_restart) {
        setPendingRestartSections((prev) => ({ ...prev, runtime: true }));
      }

      setProviderForms((prev) => {
        const next = { ...prev };
        delete next[providerName];
        return next;
      });
      setVisibleProviderKeys((prev) => ({ ...prev, [providerName]: false }));
      setEditingProviderKeys((prev) => ({ ...prev, [providerName]: false }));
      setError(null);
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    } finally {
      setProviderOperation(null);
    }
  };

  const createCustomProvider = async (
    draft: CustomProviderDraft,
  ): Promise<SettingsPayload | null> => {
    if (providerSaving || providerBusy) return null;
    setProviderOperation({
      provider: CUSTOM_PROVIDER_CREATION_KEY,
      action: "create",
    });
    try {
      const payload = await createProviderSettings(client, {
        name: draft.name.trim(),
        apiKey: draft.apiKey.trim() || undefined,
        apiBase: draft.apiBase.trim(),
        ...(settings?.provider_api_configuration_supported ? { api: draft.api } : {}),
        use_proxy: draft.useProxy,
        extraHeaders: draft.extraHeaders.trim(),
        extraBody: draft.extraBody.trim(),
        extraQuery: draft.extraQuery.trim(),
        thinkingStyle: draft.thinkingStyle.trim(),
      });
      applyPayload(payload, {
        preserveAgentForm: true,
        preserveCapabilityForms: true,
      });
      setError(null);
      return payload;
    } catch (err) {
      setError((err as Error).message);
      return null;
    } finally {
      setProviderOperation(null);
    }
  };

  return { saveProvider, createCustomProvider };
}
