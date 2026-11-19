import { useCallback, useRef, type Dispatch, type SetStateAction } from "react";
import type { TFunction } from "i18next";

import {
  webSearchProviderAcceptsApiKey,
  webSearchDraftState,
} from "@/features/settings/web/model/form";
import type { CapabilitySettingsState } from "@/features/settings/capabilities/useCapabilitySettingsState";
import type {
  ApplySettingsPayload,
  PendingRestartSections,
} from "@/features/settings/contracts";
import {
  updateNetworkSafetySettings,
  updateWebSearchSettings,
} from "@/lib/api";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload, WebSearchSettingsUpdate } from "@/lib/contracts/settings";
import { networkSafetyFormFromPayload } from "@/features/settings/capabilities/SecuritySettings";

interface CapabilitySettingsActionsOptions {
  state: CapabilitySettingsState;
  settings: SettingsPayload | null;
  client: CirnoClient;
  t: TFunction;
  applyPayload: ApplySettingsPayload;

  setPendingRestartSections: Dispatch<SetStateAction<PendingRestartSections>>;
  installCapabilities: (names: string[]) => Promise<boolean>;
}

export function useCapabilitySettingsActions({
  state,
  settings,
  client,
  applyPayload,

  setPendingRestartSections,
  installCapabilities,
}: CapabilitySettingsActionsOptions) {
  const {
    networkSafetyForm,
    setNetworkSafetySaving,
    setWebSearchForm,
    setWebSearchKeyEditing,
    setWebSearchKeyVisible,
    setWebSearchSaving,
    webSearchForm,
    webSearchKeyEditing,
  } = state;
  const latestWebSearchForm = useRef(webSearchForm);
  latestWebSearchForm.current = webSearchForm;
  const webSearchSaves = useRef(new Map<WebSearchSettingsUpdate, Promise<boolean>>());
  const webSearchSaveTail = useRef(Promise.resolve(true));
  const setError = (section: "web" | "safety", message?: string) =>
    state.setCapabilityErrors((prev) => ({ ...prev, [section]: message }));

  const saveNetworkSafetySettings = async () => {
    if (!settings) return false;
    setError("safety");
    setNetworkSafetySaving(true);
    try {
      const payload = await updateNetworkSafetySettings(client, networkSafetyForm);
      applyPayload(payload, { preserveAgentForm: true, preserveCapabilityForms: true });
      state.setNetworkSafetyForm((current) => current === networkSafetyForm ? networkSafetyFormFromPayload(payload) : current);
      if (!payload.restart_required_sections && payload.requires_restart) {
        setPendingRestartSections((prev) => ({ ...prev, runtime: true }));
      }

      setError("safety");
      return true;
    } catch (err) {
      setError("safety", (err as Error).message);
      return false;
    } finally {
      setNetworkSafetySaving(false);
    }
  };

  const persistWebSearch = async () => {
    if (!settings) return false;
    const draft = webSearchDraftState(settings, webSearchForm);
    if (draft.invalidNumbers || draft.missingCredential) return false;
    const provider = settings.web_search.providers.find((item) => item.name === webSearchForm.provider);
    if (!provider) return false;
    const apiKey = webSearchForm.apiKey?.trim() ?? "";
    const baseUrl = webSearchForm.baseUrl?.trim() ?? "";

    const isCurrentDraft = () => latestWebSearchForm.current === webSearchForm;
    if (isCurrentDraft()) setError("web");
    try {
      if (provider.name === "olostep") {
        if (!(await installCapabilities(["olostep"]))) return false;
        // Installing a dependency does not authorize saving a superseded draft.
        if (!isCurrentDraft()) return true;
      }
      const webFetchRestartRequired =
        (webSearchForm.useJinaReader ?? settings.web.fetch.use_jina_reader) !==
        settings.web.fetch.use_jina_reader;
      const update: WebSearchSettingsUpdate = {
        provider: webSearchForm.provider,
        maxResults: webSearchForm.maxResults,
        timeout: webSearchForm.timeout,
        useJinaReader: webSearchForm.useJinaReader,
      };
      if (
        webSearchProviderAcceptsApiKey(provider) &&
        (apiKey || (provider.credential === "optional_api_key" && webSearchKeyEditing))
      ) {
        update.apiKey = apiKey;
      }
      if (provider.credential === "base_url") update.baseUrl = baseUrl;
      const payload = await updateWebSearchSettings(client, update);
      applyPayload(payload, { preserveAgentForm: true, preserveCapabilityForms: true });
      if (!payload.restart_required_sections && (payload.requires_restart || webFetchRestartRequired)) {
        setPendingRestartSections((prev) => ({ ...prev, browser: true }));
      }

      setWebSearchForm((prev) => prev !== webSearchForm ? prev : ({
        provider: payload.web_search.provider,
        apiKey: undefined,
        baseUrl: payload.web_search.base_url ?? prev.baseUrl ?? "",
        maxResults: payload.web_search.max_results,
        timeout: payload.web_search.timeout,
        useJinaReader: payload.web.fetch.use_jina_reader,
      }));
      if (latestWebSearchForm.current === webSearchForm) {
        setWebSearchKeyVisible(false);
        setWebSearchKeyEditing(false);
      }
      if (isCurrentDraft()) setError("web");
      return true;
    } catch (err) {
      if (isCurrentDraft()) setError("web", (err as Error).message);
      return false;
    }
  };

  const saveWebSearch = () => {
    // Explicit install/retry buttons and autosave share one ordered write queue.
    const existing = webSearchSaves.current.get(webSearchForm);
    if (existing) return existing;
    const request = webSearchSaveTail.current.then(persistWebSearch);
    webSearchSaveTail.current = request;
    webSearchSaves.current.set(webSearchForm, request);
    setWebSearchSaving(true);
    void request.then(() => {
      webSearchSaves.current.delete(webSearchForm);
      if (!webSearchSaves.current.size) setWebSearchSaving(false);
    });
    return request;
  };

  const resetWebSearchDraft = useCallback(() => {
    if (!settings) return;
    setWebSearchForm({
      provider: settings.web_search.provider,
      apiKey: undefined,
      baseUrl: settings.web_search.base_url ?? "",
      maxResults: settings.web_search.max_results,
      timeout: settings.web_search.timeout,
      useJinaReader: settings.web.fetch.use_jina_reader,
    });
    setWebSearchKeyVisible(false);
    setWebSearchKeyEditing(false);
  }, [settings]);

  const handleWebSearchProviderChange = useCallback((provider: string) => {
    if (!settings) return;
    setWebSearchForm((prev) => ({
      provider,
      apiKey: undefined,
      baseUrl: provider === settings.web_search.provider ? settings.web_search.base_url ?? "" : "",
      maxResults: prev.maxResults ?? settings.web_search.max_results,
      timeout: prev.timeout ?? settings.web_search.timeout,
      useJinaReader: prev.useJinaReader ?? settings.web.fetch.use_jina_reader,
    }));
    setWebSearchKeyVisible(false);
    setWebSearchKeyEditing(false);
  }, [settings]);

  return {
    handleWebSearchProviderChange,
    resetWebSearchDraft,
    saveNetworkSafetySettings,
    saveWebSearch,
  };
}
