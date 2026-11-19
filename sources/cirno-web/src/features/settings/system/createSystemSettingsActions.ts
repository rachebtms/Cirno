import { createMcpSettingsActions, type McpSettingsActionsOptions } from "./createMcpSettingsActions";
import { createCliSettingsActions } from "./createCliSettingsActions";
import { createFeatureSettingsActions } from "./createFeatureSettingsActions";
import { createAutomationSettingsActions } from "./createAutomationSettingsActions";
import type { ApplySettingsPayload } from "@/features/settings/contracts";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";

interface SystemSettingsActionsOptions extends McpSettingsActionsOptions {
  featureCatalog: CirnoFeatureInfo[];
  token: string;
  applyPayload: ApplySettingsPayload;
  refreshAutomations: (showLoading?: boolean, automatic?: boolean) => Promise<void>;
}

/** Compose domain actions; each domain owns its workflow and shared read/write gate. */
export function createSystemSettingsActions(options: SystemSettingsActionsOptions) {
  return {
    ...createMcpSettingsActions(options),
    ...createCliSettingsActions(options),
    ...createFeatureSettingsActions(options),
    ...createAutomationSettingsActions(options),
  };
}
