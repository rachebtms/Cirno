import { createSettingsActionGate } from "./createSettingsActionGate";
import { createMcpOAuthActions } from "./createMcpOAuthActions";
import type { Dispatch, SetStateAction } from "react";
import type { TFunction } from "i18next";

import type {
  PendingRestartSections,
} from "@/features/settings/contracts";
import { DEFAULT_CUSTOM_MCP_FORM } from "@/features/settings/apps/model/contracts";
import type { SystemSettingsState } from "@/features/settings/system/useSystemSettingsState";
import {
  fetchCustomMcpConfig,
  importMcpConfig,
  runMcpPresetAction,
  saveCustomMcpServer,
  updateMcpServerTools,
} from "@/lib/api";
import { notifyMcpPresetsChanged } from "@/lib/mcp-preset-events";
import type { CirnoClient } from "@/lib/cirno-client";
import type { McpPresetsPayload } from "@/lib/contracts/mcp";

function isExpectedMcpOAuthPendingReloadFailure(
  payload: McpPresetsPayload,
  expectedName?: string,
): boolean {
  if (
    !expectedName
    || payload.last_action?.ok === false
    || payload.hot_reload?.ok !== false
  ) return false;

  const normalizedName = expectedName.trim().toLowerCase();
  const failed = payload.hot_reload.failed ?? [];
  if (
    !normalizedName
    || failed.length !== 1
    || failed[0].trim().toLowerCase() !== normalizedName
  ) return false;

  return payload.presets.some((preset) => (
    preset.name.trim().toLowerCase() === normalizedName
    && preset.auth === "oauth"
    && preset.status === "authorization_required"
  ));
}

export interface McpSettingsActionsOptions {
  state: SystemSettingsState;
  client: CirnoClient;
  getToken: () => string;
  t: TFunction;

  setPendingRestartSections: Dispatch<SetStateAction<PendingRestartSections>>;
}

export function createMcpSettingsActions({
  state,
  client,
  getToken,
  t,

  setPendingRestartSections,
}: McpSettingsActionsOptions) {
  const {
    customMcpForm,
    mcpConfigImport,
    mcpOAuthFlowRef,
    mcpActionRef,
    mcpRevisionRef,
    mcpRefreshRef,
    isSystemSettingsCurrent,
    setCustomMcpForm,
    setMcpConfigImport,
    setMcpError,
    setMcpFieldValues,
    setMcpMessage,
    setMcpPresetAction,
    setMcpPresets,
    setMcpPresetsLoading,
  } = state;

  const { begin: beginMcpAction, end: endMcpAction } = createSettingsActionGate({
    isCurrent: isSystemSettingsCurrent, actionRef: mcpActionRef, revisionRef: mcpRevisionRef,
    setAction: setMcpPresetAction, setLoading: setMcpPresetsLoading,
    isBlocked: () => Boolean(mcpOAuthFlowRef.current),
  });

  const publishMcpPresets = (payload: McpPresetsPayload) => {
    setMcpPresets(payload);
    if (payload.presets.some(preset => preset.runtime_status === "connecting")) mcpRefreshRef.current?.();
  };

  const retireMcpProxyDrafts = (names: string[]) => {
    setMcpFieldValues((prev) => {
      const next = { ...prev };
      for (const name of names) {
        const key = name.trim().toLowerCase();
        if (prev[key]?.use_proxy === undefined) continue;
        const fields = { ...prev[key] };
        delete fields.use_proxy;
        next[key] = fields;
      }
      return next;
    });
  };

  const mcpOAuthActions = createMcpOAuthActions({
    state, client, getToken, t, setPendingRestartSections,
    beginAction: beginMcpAction, endAction: endMcpAction, retireProxyDrafts: retireMcpProxyDrafts,
  });

  const applyMcpActionFeedback = (
    payload: McpPresetsPayload,
    announceSuccess = false,
    expectedOAuthPendingName?: string,
  ) => {
    const expectedOAuthPending = isExpectedMcpOAuthPendingReloadFailure(
      payload,
      expectedOAuthPendingName,
    );
    const actionError = payload.last_action?.ok === false
      ? payload.last_action.error || payload.last_action.message
      : payload.hot_reload?.ok === false && !expectedOAuthPending
        ? payload.hot_reload.message
        : null;
    setMcpError(actionError || null);
    setMcpMessage(
      actionError || !announceSuccess
        ? null
        : payload.last_action?.message ?? null,
    );
  };

  const handleMcpPresetAction = async (
    action: "enable" | "disable" | "remove" | "test" | "reconnect" | "proxy",
    name: string,
    values: Record<string, string> = {},
  ) => {
    const key = `${action}:${name}`;
    if (!beginMcpAction(key)) return;
    setMcpMessage(null);
    setMcpError(null);
    try {
      const payload = await runMcpPresetAction(client, action, name, values);
      if (!isSystemSettingsCurrent()) return;
      publishMcpPresets(payload);
      applyMcpActionFeedback(payload, action === "test");
      if (action !== "test") {
        notifyMcpPresetsChanged(payload);
      }
      if (payload.requires_restart) {
        setPendingRestartSections((prev) => ({ ...prev, runtime: true }));
      }
      if (
        (action === "proxy" || action === "remove")
        && payload.last_action?.ok !== false
      ) {
        retireMcpProxyDrafts([name]);
      }

      if (action === "enable") {
        setMcpFieldValues((prev) => ({ ...prev, [name]: {} }));
      }
    } catch (err) {
      if (isSystemSettingsCurrent()) setMcpError((err as Error).message);
    } finally {
      endMcpAction(key);
    }
  };

  const handleSaveCustomMcp = async () => {
    const name = customMcpForm.name.trim();
    const expectsOAuthAuthorization = (
      customMcpForm.transport !== "stdio" && customMcpForm.auth === "oauth"
    );
    const key = `custom:${name || "new"}`;
    if (!beginMcpAction(key)) return;
    setMcpMessage(null);
    setMcpError(null);
    try {
      const payload = await saveCustomMcpServer(client, {
        name,
        transport: customMcpForm.transport,
        auth:
          customMcpForm.transport !== "stdio" && customMcpForm.auth === "oauth"
            ? "oauth"
            : "",
        command: customMcpForm.command,
        args: customMcpForm.args,
        url: customMcpForm.url,
        env: customMcpForm.env,
        headers:
          customMcpForm.transport !== "stdio" && customMcpForm.auth === "headers"
            ? customMcpForm.headers
            : "",
        tool_timeout: customMcpForm.toolTimeout,
        ...(customMcpForm.transport !== "stdio" ? { use_proxy: String(customMcpForm.useProxy) } : {}),
      });
      if (!isSystemSettingsCurrent()) return;
      publishMcpPresets(payload);
      applyMcpActionFeedback(
        payload,
        false,
        expectsOAuthAuthorization ? name : undefined,
      );
      if (payload.last_action?.ok !== false) {
        retireMcpProxyDrafts([name]);
      }
      notifyMcpPresetsChanged(payload);
      if (payload.requires_restart) {
        setPendingRestartSections((prev) => ({ ...prev, runtime: true }));
      }

      if (payload.last_action?.ok !== false) {
        setCustomMcpForm((prev) => ({ ...DEFAULT_CUSTOM_MCP_FORM, transport: prev.transport }));
      }
    } catch (err) {
      if (isSystemSettingsCurrent()) setMcpError((err as Error).message);
    } finally {
      endMcpAction(key);
    }
  };

  const saveImportedMcpConfig = async (rawConfig: string) => {
    const payload = await importMcpConfig(client, rawConfig);
    if (!isSystemSettingsCurrent()) return;
    publishMcpPresets(payload);
    applyMcpActionFeedback(payload);
    // A cleanup failure can follow a successful configuration commit. Publish
    // the receipt and restart requirement before keeping the editor open.
    notifyMcpPresetsChanged(payload);
    if (payload.requires_restart) {
      setPendingRestartSections((prev) => ({ ...prev, runtime: true }));
    }
    if (payload.last_action?.ok === false) throw new Error(payload.last_action.message);
    const config: { mcpServers?: object } = JSON.parse(rawConfig);
    retireMcpProxyDrafts(Object.keys(config.mcpServers ?? config));

  };

  const handleSaveMcpConfig = async (name: string, rawConfig: string) => {
    const config: unknown = JSON.parse(rawConfig);
    if (!config || typeof config !== "object" || Array.isArray(config)) {
      throw new Error(t("settings.mcp.configObjectRequired", { defaultValue: "MCP configuration must be a JSON object." }));
    }
    const key = `edit:${name}`;
    if (!beginMcpAction(key)) throw new Error(t("settings.mcp.changePending"));
    setMcpMessage(null);
    setMcpError(null);
    try {
      await saveImportedMcpConfig(JSON.stringify({ mcpServers: { [name]: config } }));
    } finally {
      endMcpAction(key);
    }
  };

  const handleReadMcpConfig = (name: string) => fetchCustomMcpConfig(getToken(), name);

  const handleImportMcpConfig = async () => {
    const key = "import";
    if (!beginMcpAction(key)) return;
    setMcpMessage(null);
    setMcpError(null);
    try {
      await saveImportedMcpConfig(mcpConfigImport);
      if (isSystemSettingsCurrent()) setMcpConfigImport("");
    } catch (err) {
      if (isSystemSettingsCurrent()) setMcpError((err as Error).message);
    } finally {
      endMcpAction(key);
    }
  };

  const handleMcpToolsChange = async (name: string, enabledTools: string[]) => {
    const key = `tools:${name}`;
    if (!beginMcpAction(key)) return;
    setMcpMessage(null);
    setMcpError(null);
    try {
      const payload = await updateMcpServerTools(client, name, enabledTools);
      if (!isSystemSettingsCurrent()) return;
      publishMcpPresets(payload);
      applyMcpActionFeedback(payload);
      notifyMcpPresetsChanged(payload);
      if (payload.requires_restart) {
        setPendingRestartSections((prev) => ({ ...prev, runtime: true }));
      }

    } catch (err) {
      if (isSystemSettingsCurrent()) setMcpError((err as Error).message);
    } finally {
      endMcpAction(key);
    }
  };

  return {
    ...mcpOAuthActions,
    handleImportMcpConfig,
    handleMcpPresetAction,
    handleMcpToolsChange,
    handleSaveCustomMcp,
    handleReadMcpConfig,
    handleSaveMcpConfig,
  };
}
