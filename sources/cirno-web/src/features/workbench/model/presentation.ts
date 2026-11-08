import { routerLabel } from "@/lib/conversation-role";
import { Clock3, Inbox, MessageCircle, Settings2, Snowflake } from "lucide-react";
import { deriveTitle } from "@/lib/format";
import type { TFunction } from "i18next";
import type { WorkspaceRegistry } from "../registry";
import type { WorkbenchProps, WorkspaceTab } from "../contracts";
export function tabPresentation(props: WorkbenchProps, panels: WorkspaceRegistry, t: TFunction, routeKey: string) {
  return {
    title(tab: WorkspaceTab) {
      if (tab.type !== "route") { const panel = panels.get(tab.type); return panel.title?.(tab, t) || t(panel.titleKey); }
      if (tab.route.view !== "chat") return t(`workspace.${tab.route.view}`);
      if (tab.route.activeKey === "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb") return routerLabel(props.sessions);
      if (!tab.route.activeKey) return t("sidebar.newChat");
      if (tab.id === routeKey) return props.title;
      const session = props.sessions.find(session => session.key === tab.route.activeKey);
      return session?.title || deriveTitle(session?.preview ?? "", t("workspace.conversation"));
    },
    icon(tab: WorkspaceTab) {
      if (tab.type !== "route") return panels.get(tab.type).Icon;
      if (tab.route.view === "chat") return tab.route.activeKey === "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb" ? Snowflake : MessageCircle;
      return ({ inbox: Inbox, automations: Clock3, settings: Settings2 })[tab.route.view] ?? Settings2;
    },
  };
}
