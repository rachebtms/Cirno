import type { CirnoClient } from "@/lib/cirno-client";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import type { LucideIcon } from "lucide-react";
import type { ComponentType, ReactNode } from "react";

export type BuiltinPanelKind =
  | "conversations"
  | "files"
  | "file"
  | "terminal"
  | "browser"
  | "trace"
  | "credentials";
export type PanelKind = BuiltinPanelKind | `${string}.${string}`;

export type WorkspaceRoute = {
  view: string;
  activeKey: string | null;
  settingsSection: string;
  temporary?: boolean;
  tabId?: string;
};
export interface PanelTab {
  id: string;
  type: PanelKind;
  path?: string;
  sessionKey: string | null;
  scope?: WorkspaceScopePayload | null;
}
export type TabGroup = 0 | 1;
export type WorkspaceTab = (
  | { id: string; type: "route"; route: WorkspaceRoute }
  | PanelTab
) & { group?: TabGroup; ownerId?: string };

/** The workspace owns activation, unsaved changes and resource disposal. */
export interface WorkspacePanelProps {
  tab: PanelTab;
  client: CirnoClient;
  active: boolean;
  openFile: (path: string, parent: PanelTab) => void;
  setDirty: (id: string, dirty: boolean) => void;
  registerClose: (id: string, close: () => Promise<void>) => void;
}
export type PanelTabPolicy = "single" | "multiple" | { identity: (tab: PanelTab) => string };

export interface WorkspacePanelContribution {
  kind: PanelKind;
  titleKey: string;
  Icon: LucideIcon;
  Content: ComponentType<WorkspacePanelProps>;
  showInMenu: boolean;
  tabPolicy: PanelTabPolicy;
  title?: (
    tab: PanelTab,
    translate: (key: string) => string,
  ) => string | undefined;
  closeRestored?: (client: CirnoClient, tab: PanelTab) => Promise<void>;
}
export interface WorkspaceModule {
  id: string;
  panels: readonly WorkspacePanelContribution[];
  Provider?: ComponentType<{ children: ReactNode }>;
}

export interface WorkbenchProps {
  panels?: import("./registry").WorkspaceRegistry;
  children?: ReactNode;
  renderRoute?: (route: WorkspaceRoute, visible: boolean, focused: boolean) => ReactNode;
  client: CirnoClient;
  route: WorkspaceRoute;
  navigationSequence: number;
  admittedSessionKey?: string | null;
  title: string;
  inboxUnread?: number;
  runningChatIds?: ReadonlySet<string>;
  /** Reconcile restored tabs only against a successfully loaded complete catalog. */
  sessionsLoaded?: boolean;
  sessions: import("@/lib/contracts/conversations").ChatSummary[];
  scope?: WorkspaceScopePayload | null;
  onRouteVisibleChange: (visible: boolean) => void;
  onRoute: (route: WorkspaceRoute) => void;
  onNewChat: () => void;
  onCloseTemporaryChat?: (key: string) => void;
  beforeActivate: (action: () => void) => void;
}
