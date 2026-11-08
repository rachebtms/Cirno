import type { ProviderForm } from "../providerForm";
import { providerJsonValue } from "../providerForm";
import type { ProviderRow } from "./contracts";
export function providerEditor(provider: ProviderRow, form: ProviderForm) {
  const oauth = provider.auth_type === "oauth";
  const advanced = Boolean(provider.advanced_fields?.length);
  const dirty =
    oauth &&
    (form.useProxy !== (provider.use_proxy ?? false) ||
      form.extraBody.trim() !== providerJsonValue(provider.extra_body).trim());
  const optionalCredential =
    form.apiKey.trim() ||
    form.apiBase.trim() ||
    form.useProxy ||
    form.extraHeaders.trim() ||
    form.extraBody.trim() ||
    form.extraQuery.trim() ||
    form.thinkingStyle.trim() ||
    form.region.trim() ||
    form.profile.trim();
  const missingCredential =
    !oauth &&
    !provider.configured &&
    ((provider.api_key_required ?? true) ? !form.apiKey.trim() : !optionalCredential);
  return {
    oauth,
    advanced,
    dirty,
    canSave: oauth
      ? advanced && dirty
      : !missingCredential && (!provider.is_custom || Boolean(form.displayName.trim())),
  };
}
