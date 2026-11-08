import { usePreferences } from "@/hooks/usePreferences";
import { patchPreferences } from "@/features/preferences/store";
import { reorderItems } from "../model/reorder";
import { useStripReorder } from "./useStripReorder";
import { Button } from "@heroui/react";
import { Clock3, Inbox, Library, Plus, Settings2, Snowflake, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Hint } from "@/ui/feedback/Hint";
import { appShortcutLabel, isApplePlatform, type AppShortcut } from "@/lib/app-shortcuts";
import type { WorkspaceRegistry } from "../registry";
import type { WorkbenchProps } from "../contracts";
import type { WorkbenchModel } from "../model/useWorkbench";
interface LauncherAction { id: string; label: string; Icon: LucideIcon; selected: boolean; shortcut?: AppShortcut; activate: () => void }
function LauncherItem({ action, unread = 0 }: { action: LauncherAction; unread?: number }) {
  const { t } = useTranslation();
  return <Hint contentClassName="workbench-shortcut-tooltip" content={<><span>{action.label}</span>{action.shortcut && <kbd>{appShortcutLabel(action.shortcut, isApplePlatform())}</kbd>}</>}>
    <Button isIconOnly variant={action.selected ? "secondary" : "ghost"} className="workbench-launcher-action"
      data-reorder-id={action.id} aria-label={t("workspace.openItem", { title: action.label })} aria-pressed={action.selected} onPress={action.activate}>
      <action.Icon size={21} strokeWidth={1.65} aria-hidden />
      {unread > 0 && <span className="workbench-unread">{unread > 99 ? "99+" : unread}</span>}
    </Button>
  </Hint>;
}
export function Launcher({ model, panels, route, inboxUnread, onNewChat, routerName }: {
  model: WorkbenchModel; panels: WorkspaceRegistry; routerName: string;
} & Pick<WorkbenchProps, "route" | "inboxUnread" | "onNewChat">) {
  const { t } = useTranslation();
  const routeSelected = (view: string) => model.routeVisible && route.view === view;
  const actions: LauncherAction[] = [
    { id: "cirno", label: routerName, Icon: Snowflake, selected: routeSelected("chat") && route.activeKey === "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", activate: () => model.routeTo("chat", "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb") },
    { id: "conversations", label: t("workspace.library"), Icon: Library, selected: model.selected?.type === "conversations", activate: () => model.open("conversations") },
    { id: "inbox", label: t("workspace.inbox"), Icon: Inbox, selected: routeSelected("inbox"), activate: () => model.routeTo("inbox") },
    { id: "automations", shortcut: "automations", label: t("workspace.automations"), Icon: Clock3, selected: routeSelected("automations"), activate: () => model.routeTo("automations") },
    ...panels.menu.filter(panel => panel.kind !== "conversations").map(panel => ({
      id: panel.kind, label: t(panel.titleKey), Icon: panel.Icon,
      selected: model.selected?.type === panel.kind || (panel.kind === "files" && ["file", "files.preview"].includes(model.selected?.type ?? "")),
      activate: () => model.open(panel.kind),
    })),
  ];
  const { launcherOrder = [] } = usePreferences();
  const ranked = new Map(launcherOrder.map((id, index) => [id, index]));
  const ordered = [...actions].sort((a, b) => (ranked.get(a.id) ?? launcherOrder.length) - (ranked.get(b.id) ?? launcherOrder.length));
  const reorder = useStripReorder(ordered.map(action => action.id), (id, target) => {
    void patchPreferences({ launcherOrder: reorderItems(ordered, id, target).map(action => action.id) });
  });
  return <nav className="workbench-launcher" aria-label={t("workspace.launcher")}>
    <div className="workbench-launcher-scroll" data-launcher-scroll data-dragging={reorder.dragged ?? undefined} {...reorder.handlers}>{ordered.map(action =>
      <LauncherItem key={action.id} action={action} unread={action.id === "inbox" ? inboxUnread : 0} />)}</div>
    <div className="workbench-launcher-utilities">
      <LauncherItem action={{ id: "settings", shortcut: "settings", label: t("workspace.settings"), Icon: Settings2, selected: routeSelected("settings"), activate: () => model.routeTo("settings") }} />
      <LauncherItem action={{ id: "new", shortcut: "newChat", label: t("sidebar.newChat"), Icon: Plus, selected: false, activate: onNewChat }} />
    </div>
  </nav>;
}
