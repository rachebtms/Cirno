import type { SettingsPayload, WebSearchSettingsUpdate } from "@/lib/contracts/settings";

export const DEFAULT_WEB_SEARCH_FORM: WebSearchSettingsUpdate = {
  provider: "duckduckgo",
  apiKey: "",
  baseUrl: "",
  maxResults: 5,
  timeout: 30,
  useJinaReader: true,
};

export function webSearchFormFromPayload(
  payload: SettingsPayload,
  previous?: WebSearchSettingsUpdate,
): WebSearchSettingsUpdate {
  return {
    provider: payload.web_search.provider,
    apiKey: previous?.provider === payload.web_search.provider ? previous.apiKey ?? "" : "",
    baseUrl: payload.web_search.base_url ?? "",
    maxResults: payload.web_search.max_results,
    timeout: payload.web_search.timeout,
    useJinaReader: payload.web.fetch.use_jina_reader,
  };
}

type WebSearchProviderOption = SettingsPayload["web_search"]["providers"][number];

export function webSearchProviderAcceptsApiKey(provider?: WebSearchProviderOption): boolean {
  return provider?.credential === "api_key" || provider?.credential === "optional_api_key";
}

export function webSearchProviderRequiresApiKey(provider?: WebSearchProviderOption): boolean {
  return provider?.credential === "api_key";
}

export function webSearchDraftState(settings: SettingsPayload, form: WebSearchSettingsUpdate) {
  const provider = settings.web_search.providers.find((row) => row.name === form.provider);
  const apiKey = form.apiKey?.trim() ?? "";
  const baseUrl = form.baseUrl?.trim() ?? "";
  const hasExistingSecret = webSearchProviderAcceptsApiKey(provider) &&
    form.provider === settings.web_search.provider && Boolean(settings.web_search.api_key_hint);
  const jinaReaderDirty = (form.useJinaReader ?? settings.web.fetch.use_jina_reader) !== settings.web.fetch.use_jina_reader;
  return {
    hasExistingSecret,
    invalidNumbers: !Number.isFinite(form.maxResults ?? settings.web_search.max_results) || !Number.isFinite(form.timeout ?? settings.web_search.timeout),
    jinaReaderDirty,
    dirty: form.provider !== settings.web_search.provider || apiKey.length > 0 ||
      baseUrl !== (settings.web_search.base_url ?? "") || form.maxResults !== settings.web_search.max_results ||
      form.timeout !== settings.web_search.timeout || jinaReaderDirty,
    missingCredential: webSearchProviderRequiresApiKey(provider) ? !apiKey && !hasExistingSecret
      : provider?.credential === "base_url" ? !baseUrl : false,
  };
}
