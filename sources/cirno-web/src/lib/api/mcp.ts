/** Mcp operations for the versioned Cirno API. */

import type {
  McpOAuthFlowPayload,
  McpPresetsPayload,
} from "@/lib/contracts/mcp";
import { API_READ_TIMEOUT_MS, mutation, request } from "./transport";
import type { WebUIMutationTransport } from "./transport";

export function compactMcpValues(
  values: Record<string, unknown>,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  Object.entries(values).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (trimmed) payload[key] = trimmed;
      return;
    }
    payload[key] = value;
  });
  return payload;
}

export async function fetchMcpPresets(
  token: string,
  base: string = "",
): Promise<McpPresetsPayload> {
  return request<McpPresetsPayload>(
    `${base}/v0/settings/mcp-presets`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchCustomMcpConfig(
  token: string,
  name: string,
  base = "",
): Promise<string> {
  const payload = await request<{ config: Record<string, unknown> }>(
    `${base}/v0/settings/mcp-presets/config?name=${encodeURIComponent(name)}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
  return JSON.stringify(payload.config, null, 2);
}

export async function startMcpOAuth(
  transport: WebUIMutationTransport,
  name: string,
  reset: boolean = false,
  values: Record<string, string> = {},
): Promise<McpOAuthFlowPayload> {
  return mutation<McpOAuthFlowPayload>(
    transport,
    "settings.mcp.oauth_start",
    { ...values, name, ...(reset ? { reset: true } : {}) },
    30_000,
  );
}

export async function fetchMcpOAuthStatus(
  token: string,
  flowId: string,
  base: string = "",
): Promise<McpOAuthFlowPayload> {
  const query = new URLSearchParams({ flow_id: flowId });
  return request<McpOAuthFlowPayload>(
    `${base}/v0/settings/mcp-oauth/status?${query}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function completeMcpOAuth(
  transport: WebUIMutationTransport,
  flowId: string,
  callbackUrl: string,
): Promise<McpOAuthFlowPayload> {
  return mutation<McpOAuthFlowPayload>(
    transport,
    "settings.mcp.oauth_complete",
    { flow_id: flowId, callback_url: callbackUrl },
  );
}

export async function cancelMcpOAuth(
  transport: WebUIMutationTransport,
  flowId: string,
): Promise<McpOAuthFlowPayload> {
  return mutation<McpOAuthFlowPayload>(transport, "settings.mcp.oauth_cancel", {
    flow_id: flowId,
  });
}

export async function runMcpPresetAction(
  transport: WebUIMutationTransport,
  action: "enable" | "disable" | "remove" | "test" | "reconnect" | "proxy",
  name: string,
  values: Record<string, string> = {},
): Promise<McpPresetsPayload> {
  return mutation<McpPresetsPayload>(transport, `settings.mcp.${action}`, {
    name,
    ...compactMcpValues(values),
  });
}

export async function saveCustomMcpServer(
  transport: WebUIMutationTransport,
  values: Record<string, string>,
): Promise<McpPresetsPayload> {
  return mutation<McpPresetsPayload>(
    transport,
    "settings.mcp.custom",
    compactMcpValues(values),
  );
}

export async function importMcpConfig(
  transport: WebUIMutationTransport,
  config: string,
): Promise<McpPresetsPayload> {
  return mutation<McpPresetsPayload>(transport, "settings.mcp.import", {
    config,
  });
}

export async function updateMcpServerTools(
  transport: WebUIMutationTransport,
  name: string,
  enabledTools: string[],
): Promise<McpPresetsPayload> {
  return mutation<McpPresetsPayload>(transport, "settings.mcp.tools", {
    name,
    enabled_tools: enabledTools,
  });
}
