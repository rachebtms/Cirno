import type { PanelTab } from "../contracts";
import type { WorkspaceRegistry } from "../registry";

/** Every feature declares whether activation reuses a view or creates a resource. */
export function panelTabIdentity(tab: PanelTab, panels: WorkspaceRegistry): string | undefined {
  const policy = panels.get(tab.type).tabPolicy;
  if (policy === "multiple") return undefined;
  return JSON.stringify([tab.type, policy === "single" ? null : policy.identity(tab)]);
}
