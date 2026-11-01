import { useRef, useState } from "react";

import type { AutomationFilter } from "@/components/settings/system/AutomationsSettings";
import {
  DEFAULT_CUSTOM_MCP_FORM,
  type AppsKindFilter,
  type CustomMcpForm,
} from "@/components/settings/system/AppsSettings";
import type {
  AutomationsPayload,
  CliAppsPayload,
  McpOAuthFlowPayload,
  McpPresetsPayload,
  CirnoFeatureInfo,
  CirnoFeaturesPayload,
  SessionAutomationJob,
} from "@/lib/types";

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
  const [cirnoFeatureAction, setCirnoFeatureAction] = useState<string | null>(null);
  const cirnoFeatureActionRef = useRef<string | null>(null);
  const [cirnoFeatureConfirm, setCirnoFeatureConfirm] =
    useState<CirnoFeatureInstallRequest | null>(null);
  const [mcpPresetAction, setMcpPresetAction] = useState<string | null>(null);
  const [mcpOAuthFlow, setMcpOAuthFlow] = useState<McpOAuthFlowPayload | null>(null);
  const mcpOAuthFlowRef = useRef<McpOAuthFlowPayload | null>(null);
  const mcpOAuthPopupRef = useRef<Window | null>(null);
  const mcpOAuthNavigatedUrlRef = useRef<string | null>(null);
  const [mcpOAuthPopupBlocked, setMcpOAuthPopupBlocked] = useState(false);
  const [mcpOAuthCallbackUrl, setMcpOAuthCallbackUrl] = useState("");
  const [mcpOAuthCompleting, setMcpOAuthCompleting] = useState(false);
  const [mcpOAuthCallbackError, setMcpOAuthCallbackError] = useState<string | null>(null);
  const [appsQuery, setAppsQuery] = useState("");
  const [automationsFilter, setAutomationsFilter] = useState<AutomationFilter>("all");
  const [cliAppsMessage, setCliAppsMessage] = useState<string | null>(null);
  const [cliAppsError, setCliAppsError] = useState<string | null>(null);
  const [cirnoFeaturesError, setCirnoFeaturesError] = useState<string | null>(null);
  const [cliAppsFocusName, setCliAppsFocusName] = useState<string | null>(null);
  const [appsKindFilter, setAppsKindFilter] = useState<AppsKindFilter>("cli");
  const [mcpMessage, setMcpMessage] = useState<string | null>(null);
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [automationsError, setAutomationsError] = useState<string | null>(null);
  const [automationAction, setAutomationAction] = useState<string | null>(null);
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
    automationPendingDelete,
    automationPendingEdit,
    automations,
    automationsError,
    automationsFilter,
    automationsLoading,
    cliApps,
    cliAppsAction,
    cliAppsError,
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
    mcpOAuthPopupBlocked,
    mcpOAuthPopupRef,
    mcpPresetAction,
    mcpPresets,
    mcpPresetsLoading,
    cirnoFeatureAction,
    cirnoFeatureActionRef,
    cirnoFeatureConfirm,
    cirnoFeatures,
    cirnoFeaturesError,
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
    setCirnoFeaturesError,
    setCirnoFeaturesLoading,
  };
}

export type SystemSettingsState = ReturnType<typeof useSystemSettingsState>;
