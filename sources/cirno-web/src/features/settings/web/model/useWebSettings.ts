import { useEditCompletion } from "../../shared/useEditCompletion";
import { webSearchDraftState, webSearchProviderAcceptsApiKey } from "./form";
import type { WebSettingsProps } from "./contracts";

export function useWebSettings(options: WebSettingsProps) {
  const { settings, form } = options;
  const provider = settings.web_search.providers.find(row => row.name === form.provider);
  const draft = webSearchDraftState(settings, form);
  const installRequired = form.provider === "olostep" && options.olostepFeature?.installed !== true;
  const localEdits = useEditCompletion(form, draft.dirty, options.onSave, !options.editCompletion && !draft.missingCredential && !draft.invalidNumbers && !installRequired);
  const edits = options.editCompletion ?? localEdits;
  const showKey = webSearchProviderAcceptsApiKey(provider);
  const hint = draft.hasExistingSecret && !options.keyEditing ? settings.web_search.api_key_hint : undefined;
  return { provider, ...draft, installRequired, edits, showKey, hint,
    change: <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => options.onChangeForm(current => ({ ...current, [key]: value })),
    selectProvider: (id: string) => { edits.complete(); options.onChangeProvider(id); } };
}
