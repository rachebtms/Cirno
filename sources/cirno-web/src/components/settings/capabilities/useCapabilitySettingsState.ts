import { useState } from "react";
import {
  DEFAULT_NETWORK_SAFETY_FORM,
  networkSafetyFormFromPayload,
} from "@/components/settings/capabilities/SecuritySettings";
import {
  DEFAULT_WEB_SEARCH_FORM,
  webSearchFormFromPayload,
} from "@/components/settings/capabilities/WebSettings";
import type {
  NetworkSafetySettingsUpdate,
  SettingsPayload,
  WebSearchSettingsUpdate,
} from "@/lib/types";

export function useCapabilitySettingsState(initialSettings: SettingsPayload | null) {
  const [capabilityErrors, setCapabilityErrors] = useState<Partial<Record<"web" | "safety", string>>>({});
  const [webSearchSaving, setWebSearchSaving] = useState(false);
  const [networkSafetySaving, setNetworkSafetySaving] = useState(false);
  const [webSearchForm, setWebSearchForm] = useState<WebSearchSettingsUpdate>(() =>
    initialSettings ? webSearchFormFromPayload(initialSettings) : DEFAULT_WEB_SEARCH_FORM,
  );
  const [networkSafetyForm, setNetworkSafetyForm] = useState<NetworkSafetySettingsUpdate>(() =>
    initialSettings ? networkSafetyFormFromPayload(initialSettings) : DEFAULT_NETWORK_SAFETY_FORM,
  );
  const [webSearchKeyVisible, setWebSearchKeyVisible] = useState(false);
  const [webSearchKeyEditing, setWebSearchKeyEditing] = useState(false);

  return {
    capabilityErrors,
    setCapabilityErrors,
    networkSafetyForm,
    networkSafetySaving,
    setNetworkSafetyForm,
    setNetworkSafetySaving,
    setWebSearchForm,
    setWebSearchKeyEditing,
    setWebSearchKeyVisible,
    setWebSearchSaving,
    webSearchForm,
    webSearchKeyEditing,
    webSearchKeyVisible,
    webSearchSaving,
  };
}

export type CapabilitySettingsState = ReturnType<typeof useCapabilitySettingsState>;
