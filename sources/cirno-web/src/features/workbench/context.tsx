import { createContext, useContext } from "react";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import type { PanelKind } from "./contracts";

export const WorkspaceOpenContext = createContext<
  | ((
      type: PanelKind,
      options: {
        path?: string;
        sessionKey: string | null;
        scope?: WorkspaceScopePayload | null;
      },
    ) => void)
  | null
>(null);
export const useWorkspaceOpen = () => useContext(WorkspaceOpenContext);
