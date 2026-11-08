import type { ReactNode } from "react";
import type { McpPresetInfo } from "@/lib/contracts/mcp";

export type McpManagementTab = "overview" | "tools" | "connection";

export interface McpConfigEditor {
  load: (name: string) => Promise<string>;
  save: (name: string, config: string) => Promise<void>;
}

type McpAction = "enable" | "disable" | "remove" | "test" | "reconnect" | "proxy";

export interface McpManagementDialogProps {
  preset: McpPresetInfo;
  error?: string | null;
  values: Record<string, string>;
  actionKey: string | null;
  statusLabel: string;
  statusTone: "success" | "warning" | "neutral";
  tab: McpManagementTab;
  icon: ReactNode;
  onTabChange: (tab: McpManagementTab) => void;
  onOpenChange: (open: boolean) => void;
  onFieldChange: (presetName: string, fieldName: string, value: string) => void;
  onAction: (action: McpAction, name: string, values?: Record<string, string>) => void;
  onOAuthConnect: (name: string, reset?: boolean, values?: Record<string, string>) => void;
  onToolsChange: (name: string, enabledTools: string[]) => void;
  onConfigureProxy?: () => void;
  configEditor?: McpConfigEditor;
}
