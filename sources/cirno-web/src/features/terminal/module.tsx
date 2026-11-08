import type { WorkspaceModule, WorkspacePanelProps } from "@/features/workbench/contracts";
import { TerminalSquare } from "lucide-react";
import { lazy, useCallback } from "react";
const TerminalTab = lazy(() => import("./TerminalTab").then((module) => ({ default: module.TerminalTab })));
function TerminalPanel({ tab, client, active, registerClose }: WorkspacePanelProps) {
  const ready = useCallback((close: () => Promise<void>) => registerClose(tab.id, close), [registerClose, tab.id]);
  return <TerminalTab client={client} cwd={tab.scope?.project_path} terminalKey={tab.id} active={active} onCloseReady={ready} />;
}
export const terminalModule: WorkspaceModule = {
  id: "terminal", panels: [
    {
      kind: "terminal", titleKey: "workspace.terminal", Icon: TerminalSquare, Content: TerminalPanel, tabPolicy: "multiple", showInMenu: true,
      closeRestored: async (client, tab) => { await client.requestMutation("workbench.action", { action: "terminal.close", values: { id: tab.id } }); }
    },
  ]
};
