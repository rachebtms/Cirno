import type { WorkspaceModule, WorkspacePanelProps } from "@/features/workbench/contracts";
import { KeyRound } from "lucide-react";
import { lazy, useCallback } from "react";
const CredentialsTab = lazy(() => import("./CredentialsTab").then((module) => ({ default: module.CredentialsTab })));
function CredentialPanel({ tab, client, active, setDirty }: WorkspacePanelProps) {
  const dirty = useCallback((value: boolean) => setDirty(tab.id, value), [setDirty, tab.id]);
  return <CredentialsTab client={client} active={active} onDirtyChange={dirty} />;
}
export const credentialsModule: WorkspaceModule = {
  id: "credentials", panels: [
    { kind: "credentials", titleKey: "workspace.credentials", Icon: KeyRound, Content: CredentialPanel, tabPolicy: "single", showInMenu: true },
  ]
};
