import {
  networkSafetyFormFromPayload,
  visibleWebuiDefaultAccessMode,
} from "@/features/settings/capabilities/SecuritySettings";
import { useCapabilitySettingsActions } from "@/features/settings/capabilities/useCapabilitySettingsActions";
import { useCapabilitySettingsState } from "@/features/settings/capabilities/useCapabilitySettingsState";
import { webSearchDraftState, webSearchFormFromPayload } from "@/features/settings/web/model/form";
import type {
  ApplySettingsPayload,
  PendingRestartSections,
  SettingsSectionKey,
} from "@/features/settings/contracts";
import { modelPresetUpdate } from "@/features/settings/models/model/presetChanges";
import { agentDraftFromPayload, selectedModelId } from "@/features/settings/models/modelDraft";
import { useModelSettingsActions } from "@/features/settings/models/useModelSettingsActions";
import { useProviderFormsSync } from "./providers/actions/useProviderFormsSync";
import { useProviderAuthorization } from "./providers/oauth/useProviderAuthorization";
import { useModelSettingsState } from "@/features/settings/models/useModelSettingsState";
import { useEditCompletion } from "@/features/settings/shared/useEditCompletion";
import { createSystemSettingsActions } from "@/features/settings/system/createSystemSettingsActions";
import { useRuntimeConfigSettings } from "@/features/settings/runtime/useRuntimeConfiguration";
import { useSystemSettingsEffects } from "@/features/settings/system/useSystemSettingsEffects";
import { useSystemSettingsState } from "@/features/settings/system/useSystemSettingsState";
import {
  writePreferences,
} from "@/features/preferences/store";
import { usePageVisibility } from "@/hooks/usePageVisibility";
import { usePreferences } from "@/hooks/usePreferences";
import { fetchSettings, fetchSettingsUsage } from "@/lib/api";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { isLoopbackHost } from "@/lib/network";
import { useClient } from "@/providers/ClientProvider";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

interface SettingsControllerOptions {
  initialSection: SettingsSectionKey;
  initialSettings: SettingsPayload | null;
  onModelNameChange: (modelName: string | null) => void;
  onSettingsChange?: (payload: SettingsPayload) => void;
  onSectionChange?: (section: SettingsSectionKey) => void;
  onRestart?: () => void;

}

const EMPTY_PENDING_RESTART_SECTIONS: PendingRestartSections = {
  runtime: false,
  browser: false,
};

function pendingRestartSectionsFromPayload(payload: SettingsPayload): PendingRestartSections {
  const sections = payload.restart_required_sections ?? [];
  return {
    runtime: sections.includes("runtime"),
    browser: sections.includes("browser"),
  };
}

export function useSettingsController({
  initialSection,
  initialSettings,
  onModelNameChange,
  onSettingsChange,
  onSectionChange,
  onRestart,

}: SettingsControllerOptions) {
  const { t } = useTranslation();
  const { client, getToken, token } = useClient();
  const pageVisible = usePageVisibility();
  const remoteBrowserAccess =
    typeof window !== "undefined" && !isLoopbackHost(window.location.hostname);
  const [settings, setSettings] = useState<SettingsPayload | null>(() => initialSettings);
  const [loading, setLoading] = useState(() => initialSettings === null);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<SettingsSectionKey>(initialSection);
  const [pendingRestartSections, setPendingRestartSections] = useState<PendingRestartSections>(
    EMPTY_PENDING_RESTART_SECTIONS,
  );
  const previousInitialSettingsRef = useRef(initialSettings);
  const latestInitialSettingsRef = useRef(initialSettings);
  latestInitialSettingsRef.current = initialSettings;
  const restartRefreshRef = useRef<SettingsPayload | null>(null);
  const displayPreferences = usePreferences();
  const setDisplayPreferences = writePreferences;
  const modelState = useModelSettingsState(initialSettings);
  const {
    form, modelPresetEditingId, setForm,
    setModelCallOrder, setModelPresetCreating, setModelPresetEditingId,
  } = modelState;
  const capabilityState = useCapabilitySettingsState(initialSettings);
  const {
    networkSafetyForm, setNetworkSafetyForm, setWebSearchForm, webSearchForm,
  } = capabilityState;
  const draftsRef = useRef({ form, networkSafetyForm, webSearchForm });
  draftsRef.current = { form, networkSafetyForm, webSearchForm };
  const systemState = useSystemSettingsState();
  const featureCatalog = systemState.cirnoFeatures?.features ?? [];

  useEffect(() => {
    setActiveSection(initialSection);
  }, [initialSection]);

  const selectSection = useCallback(
    (section: SettingsSectionKey) => {
      setActiveSection(section);
      onSectionChange?.(section);
    },
    [onSectionChange],
  );
  const applyPayload: ApplySettingsPayload = useCallback(
    (
      payload: SettingsPayload,
      options: { preserveAgentForm?: boolean; preserveCapabilityForms?: boolean } = {},
    ) => {
      setSettings(payload);
      if (!options.preserveAgentForm) {
        const nextForm = agentDraftFromPayload(payload);
        setForm(nextForm);
        setModelPresetEditingId(selectedModelId(payload));
        setModelPresetCreating(false);
      }
      setModelCallOrder(payload.model_call_order ?? []);
      if (!options.preserveCapabilityForms) {
        setWebSearchForm((prev) => webSearchFormFromPayload(payload, prev));
        setNetworkSafetyForm(networkSafetyFormFromPayload(payload));
      }
      if (payload.restart_required_sections) {
        setPendingRestartSections(pendingRestartSectionsFromPayload(payload));
      }
      onSettingsChange?.(payload);
    },
    [onSettingsChange],
  );

  const runtimeConfigState = useRuntimeConfigSettings(settings, client, applyPayload);

  const providerAuthorization = useProviderAuthorization({
    client, busy: Boolean(modelState.providerSaving), remoteBrowserAccess, applyPayload, setError,
  });

  useEffect(() => {
    if (!initialSettings || settings !== null) return;
    applyPayload(initialSettings);
    setLoading(false);
  }, [applyPayload, initialSettings, settings]);

  useEffect(() => {
    const previous = previousInitialSettingsRef.current;
    previousInitialSettingsRef.current = initialSettings;
    if (previous?.requires_restart && !initialSettings?.requires_restart) {
      restartRefreshRef.current = initialSettings;
    } else if (restartRefreshRef.current !== initialSettings) {
      restartRefreshRef.current = null;
    }
    const shouldApplyRestartedSettings =
      restartRefreshRef.current === initialSettings && settings?.requires_restart === true;
    if (!shouldApplyRestartedSettings || !initialSettings) {
      return;
    }
    applyPayload(initialSettings, { preserveAgentForm: true, preserveCapabilityForms: true });
  }, [applyPayload, initialSettings, settings]);

  useEffect(() => {
    let cancelled = false;
    const showLoading = settings === null;
    const requestInitialSettings = latestInitialSettingsRef.current;
    const requestDrafts = draftsRef.current;
    if (showLoading) setLoading(true);
    fetchSettings(getToken())
      .then((payload) => {
        if (!cancelled && latestInitialSettingsRef.current === requestInitialSettings) {
          const current = draftsRef.current;
          applyPayload(payload, {
            preserveAgentForm: current.form !== requestDrafts.form,
            preserveCapabilityForms: current.networkSafetyForm !== requestDrafts.networkSafetyForm ||
              current.webSearchForm !== requestDrafts.webSearchForm,
          });
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled && showLoading) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [applyPayload, getToken]);

  const hasSettings = settings !== null;
  useEffect(() => {
    if (activeSection !== "overview" || !hasSettings || !pageVisible) return;
    let cancelled = false;
    let refreshing = false;
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        const usage = await fetchSettingsUsage(getToken());
        if (!cancelled) {
          setSettings((current) => (current ? { ...current, usage } : current));
        }
      } catch {
        // Usage is best-effort telemetry; the settings snapshot remains usable.
      } finally {
        refreshing = false;
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 5000);
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, [activeSection, getToken, hasSettings, pageVisible]);
  const { refreshAutomations } = useSystemSettingsEffects({
    state: systemState,
    activeSection,
    getToken,
    pageVisible,
  });

  useProviderFormsSync(modelState, settings);

  const modelDirty = useMemo(() => {
    if (!settings) return false;
    const selectedPreset = settings.model_presets.find(
      (preset) => !preset.is_default && preset.id === modelPresetEditingId,
    );
    if (!selectedPreset) return false;
    return Object.keys(modelPresetUpdate(form, selectedPreset,
      settings.model_request_overrides_supported === true)).length > 1;
  }, [form, modelPresetEditingId, settings]);

  const networkSafetyDirty = useMemo(() => {
    if (!settings) return false;
    const currentLocalServiceAccess =
      settings.advanced.webui_allow_local_service_access ?? true;
    const currentDefaultAccess = visibleWebuiDefaultAccessMode(settings.advanced.webui_default_access_mode);
    return (
      networkSafetyForm.webuiAllowLocalServiceAccess !== currentLocalServiceAccess ||
      networkSafetyForm.webuiDefaultAccessMode !== currentDefaultAccess
    );
  }, [networkSafetyForm, settings]);

  const configuredModelProviderOptions = useMemo(
    () =>
      settings?.providers
        .filter((provider) => provider.configured && provider.model_selectable !== false)
        .map((provider) => ({ name: provider.id, label: provider.name })) ?? [],
    [settings],
  );

  const restartViaSettingsSurface = useCallback(async () => {
    onRestart?.();
  }, [onRestart]);

  const systemActions = createSystemSettingsActions({
    state: systemState,
    featureCatalog,
    client,
    token,
    getToken,
    t,
    applyPayload,

    setPendingRestartSections,
    refreshAutomations,
  });
  const { installCapabilities } = systemActions;
  const modelActions = useModelSettingsActions({
    state: modelState,
    settings,
    client,
    t,
    applyPayload,

    setPendingRestartSections,
    setError,
    onModelNameChange,
    providerBusy: providerAuthorization.operation !== null,
    installCapabilities,
    configuredModelProviderOptions,
  });
  const capabilityActions = useCapabilitySettingsActions({
    state: capabilityState,
    settings,
    client,
    t,
    applyPayload,

    setPendingRestartSections,
    installCapabilities,
  });
  const modelEdits = useEditCompletion(form, modelDirty, modelActions.saveModelSettings,
    !modelState.modelPresetCreating && !!form.model.trim(), modelActions.modelEditIdentity);
  const safetyEdits = useEditCompletion(networkSafetyForm, networkSafetyDirty, capabilityActions.saveNetworkSafetySettings);
  const webDraft = settings ? webSearchDraftState(settings, webSearchForm) : null;
  const webEdits = useEditCompletion(webSearchForm, webDraft?.dirty ?? false, capabilityActions.saveWebSearch,
    !webDraft?.missingCredential && !webDraft?.invalidNumbers && (webSearchForm.provider !== "olostep" ||
      featureCatalog.some((feature) => feature.name === "olostep" && feature.installed)));

  return {
    applyPayload,
    client,
    modelState,
    modelActions,
    providerAuthorization,
    capabilityState,
    capabilityActions,
    modelEdits,
    safetyEdits,
    webEdits,
    systemState,
    systemActions,
    activeSection,
    runtimeConfigState,
    error,
    featureCatalog,

    loading,
    displayPreferences,
    modelDirty,
    networkSafetyDirty,
    pendingRestartSections,
    remoteBrowserAccess,
    restartViaSettingsSurface,
    selectSection,
    setDisplayPreferences,
    settings,
    t,
    token,
  };
}

export type SettingsController = ReturnType<typeof useSettingsController>;
