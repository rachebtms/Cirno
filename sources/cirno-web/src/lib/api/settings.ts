/** Settings operations for the versioned Cirno API. */

import type {
  NetworkSafetySettingsUpdate,
  SettingsPayload,
  WebSearchSettingsUpdate,
} from "@/lib/contracts/settings";
import { API_READ_TIMEOUT_MS, mutation, request } from "./transport";
import type { WebUIMutationTransport } from "./transport";

export async function fetchSettings(
  token: string,
  base: string = "",
): Promise<SettingsPayload> {
  return request<SettingsPayload>(
    `${base}/v0/settings`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchSettingsUsage(
  token: string,
  base: string = "",
): Promise<NonNullable<SettingsPayload["usage"]>> {
  return request<NonNullable<SettingsPayload["usage"]>>(
    `${base}/v0/settings/usage`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function updateWebSearchSettings(
  transport: WebUIMutationTransport,
  update: WebSearchSettingsUpdate,
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(transport, "settings.web_search.update", {
    provider: update.provider,
    ...(update.apiKey !== undefined ? { api_key: update.apiKey } : {}),
    ...(update.baseUrl !== undefined ? { base_url: update.baseUrl } : {}),
    ...(update.maxResults !== undefined
      ? { max_results: update.maxResults }
      : {}),
    ...(update.timeout !== undefined ? { timeout: update.timeout } : {}),
    ...(update.useJinaReader !== undefined
      ? { use_jina_reader: update.useJinaReader }
      : {}),
  });
}

export async function updateNetworkSafetySettings(
  transport: WebUIMutationTransport,
  update: NetworkSafetySettingsUpdate,
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(
    transport,
    "settings.network_safety.update",
    {
      webui_allow_local_service_access: update.webuiAllowLocalServiceAccess,
      webui_default_access_mode: update.webuiDefaultAccessMode,
    },
  );
}

export async function updateRuntimeConfigSettings(
  transport: WebUIMutationTransport,
  values: Record<string, import("@/lib/contracts/settings").RuntimeConfigValue>,
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(
    transport,
    "settings.runtime_config.update",
    { values },
  );
}
