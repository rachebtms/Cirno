import { createSettingsReadGate } from "./createSettingsReadGate";
import { useCallback, useEffect, useRef } from "react";

import type { SettingsSectionKey } from "@/features/settings/contracts";
import {
  CLI_APPS_REFRESH_MAX_RETRIES,
  CLI_APPS_REFRESH_RETRY_MS,
} from "@/features/settings/apps/model/contracts";
import type { SystemSettingsState } from "@/features/settings/system/useSystemSettingsState";
import {
  fetchAutomations,
  fetchCliApps,
  fetchMcpPresets,
  fetchCirnoFeatures,
} from "@/lib/api";

interface SystemSettingsEffectsOptions {
  state: SystemSettingsState;
  activeSection: SettingsSectionKey;
  getToken: () => string;
  pageVisible: boolean;
}

const MCP_RUNTIME_STATUS_REFRESH_MS = 1_000;

export function useSystemSettingsEffects({
  state,
  activeSection,
  getToken,
  pageVisible,
}: SystemSettingsEffectsOptions) {
  const {
    setAutomations,
    setAutomationsError,
    setAutomationsLoading,
    automationActionRef,
    automationsRevisionRef,
    isSystemSettingsCurrent,
    setCliApps,
    cliAppsActionRef,
    cliAppsRevisionRef,
    setCliAppsReadError,
    setCliAppsLoading,
    setMcpError,
    setMcpPresets,
    setMcpPresetsLoading,
    mcpActionRef,
    mcpRevisionRef,
    mcpRefreshRef,
    setCirnoFeatures,
    setCirnoFeaturesReadError,
    setCirnoFeaturesLoading,
    cirnoFeatureActionRef,
    cirnoFeaturesRevisionRef,
  } = state;
  const automationSurfaceRef = useRef({ activeSection, pageVisible });
  automationSurfaceRef.current = { activeSection, pageVisible };

  useEffect(() => {
    if (!pageVisible || !["apps", "mcp"].includes(activeSection)) return;
    let cancelled = false;
    let retry: number | null = null;
    let retryCount = 0;
    const scheduleRetry = () => {
      if (cancelled || retry !== null) return;
      retry = window.setTimeout(() => {
        retry = null;
        loadCliApps(false);
      }, CLI_APPS_REFRESH_RETRY_MS);
    };
    const beginRead = createSettingsReadGate({
      isCurrent: () => !cancelled && isSystemSettingsCurrent(),
      actionRef: cliAppsActionRef, revisionRef: cliAppsRevisionRef, getToken,
    });
    const loadCliApps = (showLoading: boolean) => {
      if (cancelled || !isSystemSettingsCurrent()) return;
      if (cliAppsActionRef.current) {
        scheduleRetry();
        return;
      }
      const read = beginRead();
      if (!read) return;
      if (showLoading) setCliAppsLoading(true);
      fetchCliApps(read.token)
        .then((payload) => {
          if (!read.isCurrent()) return;
          if (payload.catalog_refresh_pending && retryCount < CLI_APPS_REFRESH_MAX_RETRIES) {
            retryCount += 1;
            scheduleRetry();
          }
          setCliApps(payload);
          setCliAppsReadError(null);
        })
        .catch((err) => {
          if (read.isCurrent()) setCliAppsReadError((err as Error).message);
        })
        .finally(() => {
          if (read.isLatest()) setCliAppsLoading(false);
        });
    };
    loadCliApps(true);
    return () => {
      cancelled = true;
      if (retry !== null) window.clearTimeout(retry);
    };
  }, [activeSection, getToken, pageVisible, cliAppsActionRef, cliAppsRevisionRef, isSystemSettingsCurrent]);

  useEffect(() => {
    if (
      !pageVisible
      || !["channels", "models", "browser", "memory", "capabilities", "runtime"].includes(activeSection)
    ) {
      return;
    }
    let cancelled = false;
    let refreshing = false;
    const beginRead = createSettingsReadGate({
      isCurrent: () => !cancelled && isSystemSettingsCurrent(),
      actionRef: cirnoFeatureActionRef, revisionRef: cirnoFeaturesRevisionRef, getToken,
    });
    const refresh = async (showLoading = false): Promise<void> => {
      if (refreshing) return;
      const read = beginRead();
      if (!read) return;
      refreshing = true;
      if (showLoading) setCirnoFeaturesLoading(true);
      try {
        const payload = await fetchCirnoFeatures(read.token);
        if (read.isCurrent()) {
          setCirnoFeatures(payload);
          setCirnoFeaturesReadError(null);
        }
      } catch (err) {
        const message = (err as Error).message;
        if (read.isCurrent() && message !== "HTTP 404") setCirnoFeaturesReadError(message);
      } finally {
        refreshing = false;
        if (read.isLatest()) setCirnoFeaturesLoading(false);
      }
    };
    void refresh(true);
    const interval = activeSection === "channels"
      ? window.setInterval(() => void refresh(false), 5000)
      : null;
    const refreshOnFocus = () => {
      if (activeSection === "channels" && document.visibilityState !== "hidden") {
        void refresh(false);
      }
    };
    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshOnFocus);
    return () => {
      cancelled = true;
      if (interval !== null) window.clearInterval(interval);
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshOnFocus);
    };
  }, [activeSection, getToken, pageVisible, cirnoFeatureActionRef, cirnoFeaturesRevisionRef, isSystemSettingsCurrent]);

  useEffect(() => {
    if (!["apps", "mcp"].includes(activeSection) || !pageVisible) return;
    let cancelled = false;
    let retry: number | null = null;
    const scheduleRefresh = () => {
      if (cancelled || retry !== null) return;
      retry = window.setTimeout(() => {
        retry = null;
        loadMcpPresets(false);
      }, MCP_RUNTIME_STATUS_REFRESH_MS);
    };
    const beginRead = createSettingsReadGate({
      isCurrent: () => !cancelled && isSystemSettingsCurrent(),
      actionRef: mcpActionRef, revisionRef: mcpRevisionRef, getToken,
    });
    const loadMcpPresets = (showLoading: boolean) => {
      if (cancelled || !isSystemSettingsCurrent()) return;
      if (mcpActionRef.current) {
        scheduleRefresh();
        return;
      }
      const read = beginRead();
      if (!read) return;
      if (showLoading) setMcpPresetsLoading(true);
      fetchMcpPresets(read.token)
        .then((payload) => {
          if (!read.isCurrent()) return;
          setMcpPresets(payload);
          setMcpError(null);
          if (payload.presets.some((preset) => preset.runtime_status === "connecting")) scheduleRefresh();
        })
        .catch((err) => {
          if (read.isCurrent()) setMcpError((err as Error).message);
        })
        .finally(() => {
          if (read.isLatest()) setMcpPresetsLoading(false);
        });
    };
    mcpRefreshRef.current = scheduleRefresh;
    loadMcpPresets(true);
    return () => {
      cancelled = true;
      if (retry !== null) window.clearTimeout(retry);
      if (mcpRefreshRef.current === scheduleRefresh) mcpRefreshRef.current = null;
    };
  }, [activeSection, getToken, pageVisible, mcpActionRef, mcpRevisionRef, mcpRefreshRef, isSystemSettingsCurrent]);

  const loadAutomations = useCallback(
    async (showLoading = false, isActive: () => boolean = isSystemSettingsCurrent) => {
      const beginRead = createSettingsReadGate({
        isCurrent: () => isSystemSettingsCurrent() && isActive(),
        actionRef: automationActionRef, revisionRef: automationsRevisionRef, getToken,
      });
      const read = beginRead();
      if (!read) return;
      if (showLoading) setAutomationsLoading(true);
      try {
        const payload = await fetchAutomations(read.token);
        if (!read.isCurrent()) return;
        setAutomations(payload);
        setAutomationsError(null);
      } catch (err) {
        if (read.isCurrent()) setAutomationsError((err as Error).message);
      } finally {
        if (read.isLatest()) setAutomationsLoading(false);
      }
    },
    [getToken, automationActionRef, automationsRevisionRef, isSystemSettingsCurrent,
      setAutomations, setAutomationsError, setAutomationsLoading],
  );
  const refreshAutomations = useCallback(
    async (showLoading = false, automatic = false) => {
      if (automatic && (!automationSurfaceRef.current.pageVisible
        || automationSurfaceRef.current.activeSection !== "automations")) return;
      await loadAutomations(showLoading);
    },
    [loadAutomations],
  );

  useEffect(() => {
    if (activeSection !== "automations" || !pageVisible) return;
    let cancelled = false;
    let refreshing = false;
    const refresh = async (showLoading = false) => {
      if (cancelled || refreshing || automationActionRef.current) return;
      refreshing = true;
      try {
        await loadAutomations(showLoading, () => !cancelled);
      } finally {
        refreshing = false;
      }
    };
    void refresh(true);
    const interval = window.setInterval(() => void refresh(false), 5000);
    const refreshOnFocus = () => void refresh(false);
    window.addEventListener("focus", refreshOnFocus);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.removeEventListener("focus", refreshOnFocus);
    };
  }, [activeSection, pageVisible, automationActionRef, loadAutomations]);

  return { refreshAutomations };
}
