import { Brain } from "lucide-react";
import { lazy } from "react";
import type { WorkspaceModule, WorkspacePanelProps } from "@/features/workbench/contracts";
const MemoryTab = lazy(() => import("./MemoryTab").then(module => ({ default: module.MemoryTab })));
function MemoryPanel({ client, active }: WorkspacePanelProps) {
  return <MemoryTab client={client} active={active} />;
}
export const memoryModule: WorkspaceModule = {
  id: "memory", panels: [
    { kind: "memory", titleKey: "workspace.memory", Icon: Brain, Content: MemoryPanel, tabPolicy: "single", showInMenu: true },
  ],
};
