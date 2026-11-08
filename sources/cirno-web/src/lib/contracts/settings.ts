/** Settings contracts shared by the browser and its transports. */

import type {
  ModelAPIConfig,
  ProviderBalanceConfig,
  ProviderModelsPayload,
  ProviderRequestAPI,
} from "./models";
import type { WebuiDefaultAccessMode } from "./workspaces";

export type SettingsApplyStatus = "idle" | "pending";

export type RuntimeConfigValue = string | number | boolean | string[] | null;

export interface SettingsPayload {
  runtime_config?: Record<string, RuntimeConfigValue>;
  apply_state?: {
    status: SettingsApplyStatus;
    sections: string[];
  };
  agent: {
    model: string;
    provider: string;
    resolved_provider: string | null;
    has_api_key: boolean;
    model_preset: string | null;
    max_tokens: number;
    context_window_tokens: number;
    idle_compact_percent?: number | null;
    idle_compact_keep_percent?: number | null;
    temperature: number;
    reasoning_effort: string | null;
    reasoning_history?: "auto" | "preserve" | "omit";
    api?: ModelAPIConfig | null;
    timezone: string;
    tool_status_summary_max_chars: number;
  };
  model_presets: Array<{
    id: string;
    name: string;
    active: boolean;
    is_default: boolean;
    model: string;
    provider: string;
    resolved_provider?: string | null;
    max_tokens: number;
    context_window_tokens: number;
    idle_compact_percent?: number | null;
    idle_compact_keep_percent?: number | null;
    temperature: number;
    reasoning_effort: string | null;
    reasoning_history?: "auto" | "preserve" | "omit";
    reasoning_effort_values?: string[];
    api?: ModelAPIConfig | null;
    extra_headers?: Record<string, string> | null;
    extra_query?: Record<string, string> | null;
    extra_body?: Record<string, unknown> | null;
  }>;
  model_call_order: string[];
  model_call_order_editable: boolean;
  /** Host can resolve the default request API for an unsaved model configuration. */
  model_api_resolution_supported?: boolean;
  provider_api_configuration_supported?: boolean;
  model_request_overrides_supported?: boolean;
  created_model_preset?: string;
  created_provider?: string;
  providers: Array<{
    balance?: ProviderBalanceConfig | null;
    id: string;
    name: string;
    is_custom?: boolean;
    configured: boolean;
    auth_type?: "api_key" | "oauth";
    api_key_required?: boolean;
    api_key_hint?: string | null;
    api_base?: string | null;
    default_api_base?: string | null;
    model_selectable?: boolean;
    model_catalog?: ProviderModelsPayload["catalog_kind"];
    model_api_configurable?: boolean;
    /** Request formats allowed by this connection, or adapter formats when undeclared. */
    request_apis?: ProviderRequestAPI[];
    adapter_request_apis?: ProviderRequestAPI[];
    provider_api_configurable?: boolean;
    api?: ModelAPIConfig | null;
    oauth_account?: string | null;
    oauth_expires_at?: number | null;
    oauth_login_supported?: boolean;
    oauth_error?: string | null;
    use_proxy?: boolean;
    advanced_fields?: Array<
      | "extra_headers"
      | "extra_body"
      | "extra_query"
      | "use_proxy"
      | "thinking_style"
      | "region"
      | "profile"
    >;
    extra_headers?: Record<string, string> | null;
    extra_body?: Record<string, unknown> | null;
    extra_query?: Record<string, string> | null;
    thinking_style?: string | null;
    region?: string | null;
    profile?: string | null;
  }>;
  web_search: {
    provider: string;
    api_key_hint?: string | null;
    base_url?: string | null;
    max_results: number;
    timeout: number;
    providers: Array<{
      name: string;
      label: string;
      credential: "none" | "api_key" | "optional_api_key" | "base_url";
    }>;
  };
  web: {
    enable: boolean;
    use_proxy?: boolean;
    user_agent?: string | null;
    search: {
      max_results: number;
      timeout: number;
    };
    fetch: {
      use_jina_reader: boolean;
    };
  };
  runtime: {
    config_path: string;
    workspace_path: string;
    health_host: string;
    health_port: number;
    heartbeat: {
      enabled: boolean;
      interval_s: number;
    };
    dream: {
      schedule: string;
    };
  };
  usage?: {
    days: Array<{
      date: string;
      input_tokens: number;
      output_tokens: number;
      cache_read_tokens: number;
      cache_write_tokens: number;
      cache_read_observed_input_tokens: number;
      cache_write_observed_input_tokens: number;
      total_tokens: number;
      reported_tokens?: number;
      estimated_tokens?: number;
      requests: number;
      reported_requests?: number;
      estimated_requests?: number;
      successful_requests?: number;
      failed_requests?: number;
      generation_ms?: number;
      measured_output_tokens?: number;
      ttft_ms?: number;
      timed_requests?: number;
      duration_ms?: number;
      sources?: Record<
        "user" | "api" | "cron" | "dream" | "system" | string,
        {
          input_tokens: number;
          output_tokens: number;
          cache_read_tokens: number;
          cache_write_tokens: number;
          cache_read_observed_input_tokens: number;
          cache_write_observed_input_tokens: number;
          total_tokens: number;
          reported_tokens?: number;
          estimated_tokens?: number;
          requests: number;
          reported_requests?: number;
          estimated_requests?: number;
          successful_requests?: number;
          failed_requests?: number;
          generation_ms?: number;
          measured_output_tokens?: number;
          ttft_ms?: number;
          timed_requests?: number;
          duration_ms?: number;
        }
      >;
    }>;
    total_tokens: number;
    total_tokens_30d: number;
    total_tokens_365d: number;
    peak_day_tokens: number;
    current_streak_days: number;
    longest_streak_days: number;
    active_days_30d: number;
    requests_30d: number;
    failed_requests_30d?: number;
    reported_tokens_30d?: number;
    estimated_tokens_30d?: number;
    cache_read_tokens_30d?: number;
    cache_read_observed_input_tokens_30d?: number;
    cache_read_rate_30d?: number | null;
    providers_30d?: Array<{
      provider: string;
      model: string;
      input_tokens: number;
      output_tokens: number;
      cache_read_tokens: number;
      cache_write_tokens: number;
      cache_read_observed_input_tokens: number;
      cache_write_observed_input_tokens: number;
      total_tokens: number;
      reported_tokens: number;
      estimated_tokens: number;
      requests: number;
      successful_requests: number;
      failed_requests: number;
      reported_requests: number;
      estimated_requests: number;
      generation_ms: number;
      measured_output_tokens: number;
      ttft_ms: number;
      timed_requests: number;
      duration_ms: number;
    }>;
    model_days_30d?: Array<{
      date: string;
      provider: string;
      model: string;
      total_tokens: number;
    }>;
    updated_at?: string | null;
  };
  advanced: {
    restrict_to_workspace: boolean;
    workspace_sandbox?: {
      restrict_to_workspace: boolean;
      workspace_root: string;
      level: "off" | "application" | "system" | string;
      enforced: boolean;
      provider: string;
      provider_label: string;
      summary: string;
    };
    ssrf_whitelist_count: number;
    webui_allow_local_service_access: boolean;
    webui_default_access_mode: WebuiDefaultAccessMode;
    private_service_protection_enabled: boolean;
    mcp_server_count: number;
    exec_enabled: boolean;
    exec_max_runtime_limit?: number;
    exec_sandbox?: string | null;
    exec_path_prepend_set: boolean;
    exec_path_append_set: boolean;
  };
  requires_restart: boolean;
  restart_required_sections?: Array<"runtime" | "browser" | "image">;
  version?: {
    current: string;
    commit?: string | null;
  };
  environment?: {
    python_version: string;
    os: string;
    os_version: string;
    architecture: string;
  };
  docs?: {
    version: string;
    base_url: string;
    chat_apps_url: string;
    latest_url?: string;
  };
}

export interface WebSearchSettingsUpdate {
  provider: string;
  apiKey?: string;
  baseUrl?: string;
  maxResults?: number;
  timeout?: number;
  useJinaReader?: boolean;
}

export interface NetworkSafetySettingsUpdate {
  webuiAllowLocalServiceAccess: boolean;
  webuiDefaultAccessMode: WebuiDefaultAccessMode;
}
