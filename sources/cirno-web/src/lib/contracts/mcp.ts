/** Mcp contracts shared by the browser and its transports. */

import type { AppManifest } from "./apps";

export interface McpPresetField {
  name: string;
  label: string;
  secret: boolean;
  required: boolean;
  configured: boolean;
  placeholder?: string;
  env_var?: string | null;
}

export interface McpPresetInfo {
  name: string;
  display_name: string;
  category: string;
  description: string;
  docs_url: string;
  transport: "stdio" | "streamableHttp" | "sse" | "oauth" | string;
  auth?: "oauth" | null;
  use_proxy?: boolean;
  requires: string;
  note: string;
  install_supported: boolean;
  installed: boolean;
  configured: boolean;
  enabled?: boolean;
  available: boolean;
  status:
    | "not_installed"
    | "configured"
    | "missing_credentials"
    | "missing_dependency"
    | "coming_soon"
    | string;
  runtime_status?: "connecting" | "connected" | "failed" | string;
  logo_url?: string | null;
  brand_color?: string | null;
  required_fields: McpPresetField[];
  connection_summary: string;
  tool_count?: number;
  tool_names?: string[];
  checked_at?: string | null;
  error?: string | null;
  enabled_tools?: string[];
  source?: "preset" | "custom" | string;
  manifest?: AppManifest;
}

export type McpOAuthFlowStatus =
  | "starting"
  | "authorization_required"
  | "connecting"
  | "authorized"
  | "connected"
  | "failed"
  | "cancelled";

export interface McpOAuthFlowPayload {
  flow_id: string;
  name: string;
  status: McpOAuthFlowStatus;
  expires_in: number;
  authorization_url?: string;
  completion_input?: "callback_url";
  error?: string;
  hot_reload?: {
    ok: boolean;
    message?: string;
    requires_restart?: boolean;
  };
}

export interface McpPresetsPayload {
  presets: McpPresetInfo[];
  proxy_configured?: boolean;
  installed_count: number;
  requires_restart?: boolean;
  hot_reload?: {
    ok: boolean;
    message: string;
    added?: string[];
    changed?: string[];
    removed?: string[];
    retried?: string[];
    connected?: string[];
    configured?: string[];
    failed?: string[];
    tools_removed?: number;
    requires_restart?: boolean;
  };
  last_action?: {
    ok: boolean;
    message: string;
    installed?: boolean;
    removed?: boolean;
    managed_paths_removed?: string[];
    verification?: string[];
    verification_failed?: string[];
    tool_count?: number;
    tool_names?: string[];
    checked_at?: string | null;
    error?: string | null;
  };
}
