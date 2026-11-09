/** Models contracts shared by the browser and its transports. */

import type { SettingsPayload } from "./settings";

export type ModelRequestAPI =
  | "chat_completions"
  | "responses"
  | "anthropic_messages";

export interface ModelAPIConfig {
  supported_apis: ModelRequestAPI[];
  preferred_api?: ModelRequestAPI | null;
}

export type ProviderRequestAPI =
  | "chat_completions"
  | "responses"
  | "anthropic_messages"
  | "bedrock_converse";

export interface AutomaticModelAPIPayload {
  provider: string;
  api: ProviderRequestAPI;
}

export interface ProviderModelInfo {
  id: string;
  label?: string | null;
  description?: string | null;
  owned_by?: string | null;
  context_window?: number | null;
  max_output_tokens?: number;
  input_modalities?: string[];
  output_modalities?: string[];
  reasoning_efforts?: string[];
  default_reasoning_effort?: string;
  supports_backend_search?: boolean;
  api?: ModelAPIConfig | null;
}

export interface ProviderModelsPayload {
  provider: string;
  label: string;
  status:
    | "available"
    | "unsupported"
    | "not_configured"
    | "missing_api_base"
    | "error";
  catalog_kind:
    | "builtin"
    | "hybrid"
    | "official"
    | "catalog"
    | "local"
    | "custom"
    | "unsupported";
  source?: "remote" | "cache" | "stale" | "fallback";
  error_kind?: "auth_required" | "unavailable" | null;
  models: ProviderModelInfo[];
  model_count: number;
  message?: string | null;
  fetched_at?: number;
}

export interface ProviderOAuthAuthorizationRequired {
  status: "authorization_required";
  provider: string;
  flow_id: string;
  authorization_url: string;
  expires_in: number;
  completion_input?: "authorization_code" | "callback_url" | "device_code";
  user_code?: string;
}

export interface ProviderOAuthPending {
  status: "pending";
  provider: string;
  flow_id: string;
}

export type ProviderOAuthLoginResult =
  | SettingsPayload
  | ProviderOAuthAuthorizationRequired;

export type ProviderOAuthCompletionResult =
  | SettingsPayload
  | ProviderOAuthPending;

export interface ModelConfigurationCreate {
  name: string;
  provider: string;
  model: string;
  maxTokens?: number;
  contextWindowTokens?: number;
  idleCompactPercent?: number | null;
  idleCompactKeepPercent?: number | null;
  temperature?: number;
  reasoningEffort?: string | null;
  reasoningHistory?: "auto" | "preserve" | "omit";
  imageInput?: boolean | null;
  videoInput?: boolean | null;
  api?: ModelAPIConfig | null;
  extraHeaders?: string;
  extraQuery?: string;
  extraBody?: string;
}

export interface ModelConfigurationUpdate {
  id: string;
  name?: string;
  provider?: string;
  model?: string;
  maxTokens?: number;
  contextWindowTokens?: number;
  idleCompactPercent?: number | null;
  idleCompactKeepPercent?: number | null;
  temperature?: number;
  reasoningEffort?: string | null;
  reasoningHistory?: "auto" | "preserve" | "omit";
  imageInput?: boolean | null;
  videoInput?: boolean | null;
  api?: ModelAPIConfig | null;
  extraHeaders?: string;
  extraQuery?: string;
  extraBody?: string;
}

export interface ProviderSettingsUpdate {
  balance?: ProviderBalanceConfig | null;
  provider: string;
  displayName?: string;
  apiKey?: string;
  apiBase?: string;
  api?: ModelAPIConfig | null;
  use_proxy?: boolean;
  extraHeaders?: string;
  extraBody?: string;
  extraQuery?: string;
  thinkingStyle?: string;
  region?: string;
  profile?: string;
}

export interface ProviderCreationUpdate {
  name: string;
  apiKey?: string;
  apiBase: string;
  api?: ModelAPIConfig | null;
  use_proxy?: boolean;
  extraHeaders?: string;
  extraBody?: string;
  extraQuery?: string;
  thinkingStyle?: string;
}

export interface ProviderBalanceConfig {
  endpoint: string;
  format: "deepseek" | "json";
  amount_path: string;
  currency: string;
  api_key: string | null;
}

export interface ProviderBalancePayload {
  provider_id: string;
  status: "ok" | "disabled";
  balances: Array<{ amount: string; currency: string }>;
  checked_at?: string;
}
