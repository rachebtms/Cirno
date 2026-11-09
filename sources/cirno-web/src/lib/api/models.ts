/** Models operations for the versioned Cirno API. */

import type {
  AutomaticModelAPIPayload,
  ModelConfigurationCreate,
  ModelConfigurationUpdate,
  ProviderCreationUpdate,
  ProviderModelsPayload,
  ProviderOAuthCompletionResult,
  ProviderOAuthLoginResult,
  ProviderSettingsUpdate,
} from "@/lib/contracts/models";
import { API_READ_TIMEOUT_MS, mutation, request } from "./transport";
import type { WebUIMutationTransport } from "./transport";
import type { SettingsPayload } from "@/lib/contracts/settings";

export async function fetchAutomaticModelAPI(
  token: string,
  provider: string,
  model: string,
  reasoningEffort: string,
  base: string = "",
): Promise<AutomaticModelAPIPayload> {
  const query = new URLSearchParams({
    provider,
    model,
    reasoning_effort: reasoningEffort,
  });
  const payload = await request<unknown>(
    `${base}/v0/settings/model-api?${query}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
  if (typeof payload !== "object" || payload === null)
    throw new Error("Invalid model API resolution");
  const result = payload as Record<string, unknown>;
  const api = result.api;
  if (
    typeof result.provider !== "string" ||
    (api !== "chat_completions" &&
      api !== "responses" &&
      api !== "anthropic_messages" &&
      api !== "bedrock_converse")
  )
    throw new Error("Invalid model API resolution");
  return { provider: result.provider, api };
}

export async function fetchProviderModels(
  token: string,
  provider: string,
  base: string = "",
  options?: { refresh?: boolean },
): Promise<ProviderModelsPayload> {
  const query = new URLSearchParams();
  query.set("provider", provider);
  if (options?.refresh) query.set("refresh", "1");
  return request<ProviderModelsPayload>(
    `${base}/v0/settings/provider-models?${query}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export function modelGenerationSettingsPayload(
  configuration: Pick<
    ModelConfigurationCreate,
    | "maxTokens"
    | "contextWindowTokens"
    | "idleCompactPercent"
    | "idleCompactKeepPercent"
    | "temperature"
    | "reasoningEffort"
    | "reasoningHistory"
    | "imageInput"
    | "videoInput"
    | "api"
    | "extraHeaders"
    | "extraQuery"
    | "extraBody"
  >,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  if (configuration.maxTokens !== undefined) {
    payload.max_tokens = configuration.maxTokens;
  }
  if (configuration.contextWindowTokens !== undefined) {
    payload.context_window_tokens = configuration.contextWindowTokens;
  }
  if (configuration.imageInput !== undefined) payload.image_input = configuration.imageInput;
  if (configuration.videoInput !== undefined) payload.video_input = configuration.videoInput;
  if (configuration.reasoningHistory !== undefined)
    payload.reasoning_history = configuration.reasoningHistory;
  if (configuration.idleCompactPercent !== undefined)
    payload.idle_compact_percent = configuration.idleCompactPercent ?? "";
  if (configuration.idleCompactKeepPercent !== undefined)
    payload.idle_compact_keep_percent =
      configuration.idleCompactKeepPercent ?? "";
  if (configuration.temperature !== undefined) {
    payload.temperature = configuration.temperature;
  }
  if (configuration.reasoningEffort !== undefined) {
    payload.reasoning_effort = configuration.reasoningEffort ?? "";
  }
  if (configuration.api !== undefined) {
    payload.api = configuration.api;
  }
  for (const [key, field] of [
    ["extraHeaders", "extra_headers"],
    ["extraQuery", "extra_query"],
    ["extraBody", "extra_body"],
  ] as const) {
    if (configuration[key] !== undefined) payload[field] = configuration[key];
  }
  return payload;
}

export async function createModelConfiguration(
  transport: WebUIMutationTransport,
  configuration: ModelConfigurationCreate,
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(
    transport,
    "settings.model_configuration.create",
    {
      name: configuration.name,
      provider: configuration.provider,
      model: configuration.model,
      ...modelGenerationSettingsPayload(configuration),
    },
  );
}

export async function updateModelConfiguration(
  transport: WebUIMutationTransport,
  configuration: ModelConfigurationUpdate,
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(
    transport,
    "settings.model_configuration.update",
    {
      id: configuration.id,
      ...(configuration.name !== undefined ? { name: configuration.name } : {}),
      ...(configuration.provider !== undefined
        ? { provider: configuration.provider }
        : {}),
      ...(configuration.model !== undefined
        ? { model: configuration.model }
        : {}),
      ...modelGenerationSettingsPayload(configuration),
    },
  );
}

export async function deleteModelConfiguration(
  transport: WebUIMutationTransport,
  id: string,
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(
    transport,
    "settings.model_configuration.delete",
    { id },
  );
}

export async function updateModelCallOrder(
  transport: WebUIMutationTransport,
  order: string[],
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(
    transport,
    "settings.model_call_order.update",
    { order },
  );
}

export async function updateProviderSettings(
  transport: WebUIMutationTransport,
  update: ProviderSettingsUpdate,
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(transport, "settings.provider.update", {
    ...update,
  });
}

export async function createProviderSettings(
  transport: WebUIMutationTransport,
  update: ProviderCreationUpdate,
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(transport, "settings.provider.create", {
    ...update,
  });
}

export async function loginProviderOAuth(
  transport: WebUIMutationTransport,
  provider: string,
  remoteBrowserAccess: boolean = false,
): Promise<ProviderOAuthLoginResult> {
  return mutation<ProviderOAuthLoginResult>(
    transport,
    "settings.provider.oauth_login",
    { provider, ...(remoteBrowserAccess ? { remote_browser: true } : {}) },
  );
}

export async function completeProviderOAuth(
  transport: WebUIMutationTransport,
  provider: string,
  flowId: string,
  authorizationResponse?: string,
): Promise<ProviderOAuthCompletionResult> {
  return mutation<ProviderOAuthCompletionResult>(
    transport,
    "settings.provider.oauth_complete",
    {
      provider,
      flow_id: flowId,
      ...(authorizationResponse
        ? { authorization_response: authorizationResponse }
        : {}),
    },
  );
}

export async function cancelProviderOAuth(
  transport: WebUIMutationTransport,
  provider: string,
  flowId: string,
): Promise<void> {
  await mutation(transport, "settings.provider.oauth_complete", {
    provider,
    flow_id: flowId,
    cancel: true,
  });
}

export async function logoutProviderOAuth(
  transport: WebUIMutationTransport,
  provider: string,
): Promise<SettingsPayload> {
  return mutation<SettingsPayload>(
    transport,
    "settings.provider.oauth_logout",
    { provider },
  );
}

export function fetchProviderBalance(
  token: string,
  providerId: string,
): Promise<import("@/lib/contracts/models").ProviderBalancePayload> {
  return request(
    `/v0/settings/provider-balance?${new URLSearchParams({ provider_id: providerId })}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}
