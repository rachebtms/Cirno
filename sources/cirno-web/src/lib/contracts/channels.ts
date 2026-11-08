/** Channels contracts shared by the browser and its transports. */

export interface CirnoFeatureInfo {
  name: string;
  display_name: string;
  capabilities?: string[];
  settings_visible?: boolean;
  webui?: string;
  type: "channel" | "feature" | string;
  enabled: boolean;
  running?: boolean;
  runtime_status?: ChannelRuntimeStatus;
  runtime_error?: string;
  configured?: boolean;
  config_values?: Record<string, string>;
  configured_fields?: string[];
  setup?: ChannelSetupContract;
  instances?: CirnoChannelInstanceInfo[];
  installed: boolean;
  requires_dependencies?: boolean;
  ready: boolean;
  status: "enabled" | "missing_dependency" | "not_enabled" | string;
  install_supported: boolean;
  requires_restart: boolean;
  restart_pending?: boolean;
}

export interface ChannelSetupContractField {
  key: string;
  field: string;
  kind: "string" | "secret" | "int" | "bool" | "list" | "enum" | string;
  choices: string[];
  required: boolean;
  default_value?: string;
  inheritable?: boolean;
}

export interface ChannelSetupContract {
  fields: ChannelSetupContractField[];
  requirements?: ChannelSetupContractRequirement[];
  official_url?: string;
  verifies_connection?: boolean;
}

export interface ChannelSetupContractRequirement {
  alternatives: string[][];
}

export interface CirnoChannelInstanceInfo {
  id: string;
  name: string;
  display_name?: string;
  avatar_url?: string;
  enabled: boolean;
  running?: boolean;
  runtime_status?: ChannelRuntimeStatus;
  runtime_error?: string;
  configured: boolean;
  config_values: Record<string, string>;
  configured_fields: string[];
}

export type ChannelRuntimeStatus =
  | "running"
  | "starting"
  | "failed"
  | "stopped"
  | string;

export interface CirnoFeaturesPayload {
  features: CirnoFeatureInfo[];
  enabled_count: number;
  requires_restart?: boolean;
  last_action?: {
    ok: boolean;
    message: string;
    enabled?: boolean;
  };
}

export type ChannelSetupStatus =
  | "connected"
  | "configured"
  | "needs_setup"
  | "invalid"
  | "unsupported"
  | string;

export type ChannelValidationCheckStatus =
  | "pass"
  | "warn"
  | "fail"
  | "skipped"
  | string;

export interface ChannelValidationCheck {
  id: string;
  label: string;
  status: ChannelValidationCheckStatus;
  message?: string;
  action_url?: string;
}

export interface ChannelIdentity {
  name?: string;
  workspace?: string;
  account?: string;
  avatar_url?: string;
}

export interface ChannelValidationPayload {
  name: string;
  status: ChannelSetupStatus;
  checks: ChannelValidationCheck[];
  identity?: ChannelIdentity;
  missing_fields: string[];
  can_enable: boolean;
  requires_restart: boolean;
  checked_at?: string;
  message?: string;
}

export type ChannelConnectStatus =
  | "pending"
  | "succeeded"
  | "expired"
  | "cancelled"
  | "failed";

export interface ChannelConnectPayload {
  session_id: string;
  instance_id?: string;
  status: ChannelConnectStatus;
  message?: string;
  qr_url?: string;
  interval_ms?: number;
  expires_at_ms?: number;
  retrying?: boolean;
  cirno_features?: CirnoFeaturesPayload;
}

export interface ChannelConfigurePayload {
  name: string;
  saved: boolean;
  saved_keys?: string[];
  cirno_features?: CirnoFeaturesPayload;
}
