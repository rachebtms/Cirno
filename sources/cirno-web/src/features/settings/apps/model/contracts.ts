import type { Dispatch, SetStateAction } from "react";
import type { McpConfigEditor } from "../../mcp/model/contracts";
import type { CliAppsPayload } from "@/lib/contracts/apps";
import type { McpOAuthFlowPayload, McpPresetsPayload } from "@/lib/contracts/mcp";

export type AppsKindFilter = "ready" | "cli" | "mcp";
type CustomMcpTransport = "stdio" | "streamableHttp" | "sse";
type CustomMcpAuth = "none" | "oauth" | "headers";
export const CLI_APPS_REFRESH_RETRY_MS = 2_000;
export const CLI_APPS_REFRESH_MAX_RETRIES = 30;

export interface CustomMcpForm {
  name: string;
  transport: CustomMcpTransport;
  auth: CustomMcpAuth;
  command: string;
  args: string;
  url: string;
  env: string;
  headers: string;
  toolTimeout: string;
  useProxy: boolean;
}

export const DEFAULT_CUSTOM_MCP_FORM: CustomMcpForm = {
  name: "",
  transport: "stdio",
  auth: "none",
  command: "",
  args: "",
  url: "",
  env: "",
  headers: "",
  toolTimeout: "30",
  useProxy: false,
};

export interface AppsCatalogProps {
  mcpConfigEditor?: McpConfigEditor;
  hideFilters?: boolean;
  setupName?: string | null;
  onSetupOpened?: () => void;
  onConfigureProxy?: () => void;
  cliApps: CliAppsPayload | null;
  mcpPresets: McpPresetsPayload | null;
  cliAppsLoading: boolean;
  mcpPresetsLoading: boolean;
  query: string;
  filter: AppsKindFilter;
  cliActionKey: string | null;
  mcpActionKey: string | null;
  mcpOAuthFlow: McpOAuthFlowPayload | null;
  mcpOAuthPopupBlocked: boolean;
  mcpOAuthCallbackUrl: string;
  mcpOAuthCompleting: boolean;
  mcpOAuthCallbackError: string | null;
  cliMessage: string | null;
  cliError: string | null;
  cliFocusName: string | null;
  mcpMessage: string | null;
  mcpError: string | null;
  mcpFieldValues: Record<string, Record<string, string>>;
  customMcpForm: CustomMcpForm;
  mcpConfigImport: string;
  showBrandLogos: boolean;
  requiresRestartPending: boolean;
  onQueryChange: (value: string) => void;
  onFilterChange: (value: AppsKindFilter) => void;
  onCliAction: (action: "install" | "update" | "uninstall" | "test", name: string) => void;
  onMcpAction: (action: "enable" | "disable" | "remove" | "test" | "reconnect" | "proxy", name: string, values?: Record<string, string>) => void;
  onMcpOAuthConnect: (name: string, reset?: boolean, values?: Record<string, string>) => void;
  onMcpOAuthCancel: () => void;
  onMcpOAuthOpen: () => void;
  onMcpOAuthCallbackUrlChange: (value: string) => void;
  onMcpOAuthComplete: () => void;
  onDismissStatus: () => void;
  onBackToChat: () => void;
  onMcpFieldChange: (presetName: string, fieldName: string, value: string) => void;
  onCustomMcpFormChange: Dispatch<SetStateAction<CustomMcpForm>>;
  onMcpConfigImportChange: (value: string) => void;
  onSaveCustomMcp: () => void;
  onImportMcpConfig: () => void;
  onMcpToolsChange: (name: string, enabledTools: string[]) => void;
  onRestart?: () => void;
  isRestarting?: boolean;
}
