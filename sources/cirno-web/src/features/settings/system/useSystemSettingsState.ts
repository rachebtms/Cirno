import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLifetime } from "@/ui/resources/useLifetime";

import type { AutomationFilter } from "@/features/automations";
import {
  DEFAULT_CUSTOM_MCP_FORM,
  type AppsKindFilter,
  type CustomMcpForm,
} from "@/features/settings/apps/model/contracts";
import type { AutomationsPayload, SessionAutomationJob } from "@/lib/contracts/automations";
import type { CliAppsPayload } from "@/lib/contracts/apps";
import type { McpOAuthFlowPayload, McpPresetsPayload } from "@/lib/contracts/mcp";
import type { CirnoFeatureInfo, CirnoFeaturesPayload } from "@/lib/contracts/channels";

export type CirnoFeatureInstallRequest = {
  feature: CirnoFeatureInfo;
  installOnly: boolean;
};

export function useSystemSettingsState() {
  const [cliApps, setCliApps] = useState<CliAppsPayload | null>(null);
  const [cirnoFeatures, setCirnoFeatures] = useState<CirnoFeaturesPayload | null>(null);
  const [mcpPresets, setMcpPresets] = useState<McpPresetsPayload | null>(null);
  const [automations, setAutomations] = useState<AutomationsPayload | null>(null);
  const [cliAppsLoading, setCliAppsLoading] = useState(true);
  const [cirnoFeaturesLoading, setCirnoFeaturesLoading] = useState(true);
  const [mcpPresetsLoading, setMcpPresetsLoading] = useState(true);
  const [automationsLoading, setAutomationsLoading] = useState(true);
  const [cliAppsAction, setCliAppsAction] = useState<string | null>(null);
  const cliAppsActionRef = useRef<string | null>(null);
  const cliAppsRevisionRef = useRef(0);
  const [cirnoFeatureAction, setCirnoFeatureAction] = useState<string | null>(null);
  const cirnoFeatureActionRef = useRef<string | null>(null);
  const cirnoFeaturesRevisionRef = useRef(0);
  const [cirnoFeatureConfirm, setCirnoFeatureConfirm] =
    useState<CirnoFeatureInstallRequest | null>(null);
  const [mcpPresetAction, setMcpPresetAction] = useState<string | null>(null);
  const mcpActionRef = useRef<string | null>(null);
  const mcpRevisionRef = useRef(0);
  const mcpRefreshRef = useRef<(() => void) | null>(null);
  const [mcpOAuthFlow, setMcpOAuthFlow] = useState<McpOAuthFlowPayload | null>(null);
  const mcpOAuthFlowRef = useRef<McpOAuthFlowPayload | null>(null);
  const mcpOAuthPopupRef = useRef<Window | null>(null);
  const mcpOAuthNavigatedUrlRef = useRef<string | null>(null);
  const mcpOAuthCompletingRef = useRef(false);
  const mcpOAuthCancellingRef = useRef(false);
  const mcpOAuthRevisionRef = useRef(0);
  const mcpOAuthMonitorRef = useRef(0);
  const mcpOAuthWaitRef = useRef<(() => void) | null>(null);
  const [mcpOAuthPopupBlocked, setMcpOAuthPopupBlocked] = useState(false);
  const [mcpOAuthCallbackUrl, setMcpOAuthCallbackUrl] = useState("");
  const [mcpOAuthCompleting, setMcpOAuthCompleting] = useState(false);
  const [mcpOAuthCallbackError, setMcpOAuthCallbackError] = useState<string | null>(null);
  const [appsQuery, setAppsQuery] = useState("");
  const [automationsFilter, setAutomationsFilter] = useState<AutomationFilter>("all");
  const [cliAppsMessage, setCliAppsMessage] = useState<string | null>(null);
  const [cliAppsError, setCliAppsError] = useState<string | null>(null);
  const [cliAppsReadError, setCliAppsReadError] = useState<string | null>(null);
  const [cirnoFeaturesError, setCirnoFeaturesError] = useState<string | null>(null);
  const [cirnoFeaturesReadError, setCirnoFeaturesReadError] = useState<string | null>(null);
  const [cliAppsFocusName, setCliAppsFocusName] = useState<string | null>(null);
  const [appsKindFilter, setAppsKindFilter] = useState<AppsKindFilter>("cli");
  const [mcpMessage, setMcpMessage] = useState<string | null>(null);
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [automationsError, setAutomationsError] = useState<string | null>(null);
  const [automationAction, setAutomationAction] = useState<string | null>(null);
  const automationActionRef = useRef<string | null>(null);
  const automationsRevisionRef = useRef(0);
  const systemSettingsOwner = useMemo(() => Symbol("system settings"), []);
  const isSystemSettingsCurrent = useLifetime(systemSettingsOwner);
  const publishCirnoFeatures = useCallback((payload: CirnoFeaturesPayload) => {
    if (!isSystemSettingsCurrent()) return;
    cirnoFeaturesRevisionRef.current += 1;
    setCirnoFeatures(payload);
    setCirnoFeaturesLoading(false);
    setCirnoFeaturesReadError(null);
    setCirnoFeaturesError(null);
  }, [isSystemSettingsCurrent]);
  const automationRefreshTimersRef = useRef(new Set<number>());
  useEffect(() => {
    const timers = automationRefreshTimersRef.current;
    return () => {
      for (const timer of timers) window.clearTimeout(timer);
      timers.clear();
      mcpOAuthFlowRef.current = null;
      mcpOAuthRevisionRef.current += 1;
      mcpOAuthMonitorRef.current += 1;
      mcpOAuthWaitRef.current?.();
      const popup = mcpOAuthPopupRef.current;
      mcpOAuthPopupRef.current = null;
      mcpOAuthNavigatedUrlRef.current = null;
      try {
        if (popup && !popup.closed) popup.close();
      } catch {
        // A cross-origin authorization page can restrict its WindowProxy.
      }
    };
  }, []);
  const [automationPendingDelete, setAutomationPendingDelete] =
    useState<SessionAutomationJob | null>(null);
  const [automationPendingEdit, setAutomationPendingEdit] =
    useState<SessionAutomationJob | null>(null);
  const [mcpFieldValues, setMcpFieldValues] = useState<Record<string, Record<string, string>>>({});
  const [customMcpForm, setCustomMcpForm] = useState<CustomMcpForm>(DEFAULT_CUSTOM_MCP_FORM);
  const [mcpConfigImport, setMcpConfigImport] = useState("");

  return {
    appsKindFilter,
    appsQuery,
    automationAction,
    automationActionRef,
    automationsRevisionRef,
    isSystemSettingsCurrent,
    automationRefreshTimersRef,
    automationPendingDelete,
    automationPendingEdit,
    automations,
    automationsError,
    automationsFilter,
    automationsLoading,
    cliApps,
    cliAppsAction,
    cliAppsActionRef,
    cliAppsRevisionRef,
    cliAppsError: cliAppsError ?? cliAppsReadError,
    cliAppsFocusName,
    cliAppsLoading,
    cliAppsMessage,
    customMcpForm,
    mcpConfigImport,
    mcpError,
    mcpFieldValues,
    mcpMessage,
    mcpOAuthCallbackError,
    mcpOAuthCallbackUrl,
    mcpOAuthCompleting,
    mcpOAuthFlow,
    mcpOAuthFlowRef,
    mcpOAuthNavigatedUrlRef,
    mcpOAuthCompletingRef,
    mcpOAuthCancellingRef,
    mcpOAuthRevisionRef,
    mcpOAuthMonitorRef,
    mcpOAuthWaitRef,
    mcpOAuthPopupBlocked,
    mcpOAuthPopupRef,
    mcpPresetAction,
    mcpActionRef,
    mcpRevisionRef,
    mcpRefreshRef,
    mcpPresets,
    mcpPresetsLoading,
    cirnoFeatureAction,
    cirnoFeatureActionRef,
    cirnoFeaturesRevisionRef,
    cirnoFeatureConfirm,
    cirnoFeatures,
    cirnoFeaturesError: cirnoFeaturesError ?? cirnoFeaturesReadError,
    cirnoFeaturesLoading,
    setAppsKindFilter,
    setAppsQuery,
    setAutomationAction,
    setAutomationPendingDelete,
    setAutomationPendingEdit,
    setAutomations,
    setAutomationsError,
    setAutomationsFilter,
    setAutomationsLoading,
    setCliApps,
    setCliAppsAction,
    setCliAppsError,
    setCliAppsReadError,
    setCliAppsFocusName,
    setCliAppsLoading,
    setCliAppsMessage,
    setCustomMcpForm,
    setMcpConfigImport,
    setMcpError,
    setMcpFieldValues,
    setMcpMessage,
    setMcpOAuthCallbackError,
    setMcpOAuthCallbackUrl,
    setMcpOAuthCompleting,
    setMcpOAuthFlow,
    setMcpOAuthPopupBlocked,
    setMcpPresetAction,
    setMcpPresets,
    setMcpPresetsLoading,
    setCirnoFeatureAction,
    setCirnoFeatureConfirm,
    setCirnoFeatures,
    publishCirnoFeatures,
    setCirnoFeaturesError,
    setCirnoFeaturesReadError,
    setCirnoFeaturesLoading,
  };
}

export type SystemSettingsState = ReturnType<typeof useSystemSettingsState>;
