import type { WorkspaceModule, WorkspacePanelProps } from "@/features/workbench/contracts";
import { Route } from "lucide-react";
import { lazy, useCallback } from "react";
const TraceTab = lazy(() => import("./TraceTab").then((module) => ({ default: module.TraceTab })));
function TracePanel({ client, tab, active, registerClose }: WorkspacePanelProps) {
  const ready = useCallback((close: () => Promise<void>) => registerClose(tab.id, close), [registerClose, tab.id]);
  return <TraceTab client={client} recordingId={tab.id} active={active} onCloseReady={ready} />;
}
export const traceModule: WorkspaceModule = {
  id: "trace", panels: [
    { kind: "trace", titleKey: "workspace.trace", Icon: Route, Content: TracePanel, tabPolicy: "multiple", showInMenu: true, closeRestored: async (client, tab) => { await client.requestMutation("workbench.action", { action: "trace.close", values: { recording_id: tab.id } }); } },
  ]
};
