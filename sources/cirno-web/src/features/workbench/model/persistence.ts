import { isRecord } from "@/lib/record";
import type { WorkspaceRegistry } from "../registry";
import { panelTabIdentity } from "./tab-policy";
import type { WorkspaceRoute, WorkspaceTab } from "../contracts";
const KEY = "cirno-webui.workspace-tabs.v1";
export function routeTabId(route: WorkspaceRoute) {
  return route.view === "chat" ? `chat:${route.activeKey ?? "new"}` : route.view;
}
export function restoreTabs(route: WorkspaceRoute, panels: WorkspaceRegistry) {
  const current: WorkspaceTab = { ownerId: crypto.randomUUID(), id: routeTabId(route), type: "route", route };
  try {
    const value: unknown = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (value === null) return { tabs: [current], error: "" };
    if (!Array.isArray(value) || !value.every(tab => {
      if (!isRecord(tab) || typeof tab.id !== "string" || (tab.group !== undefined && tab.group !== 0 && tab.group !== 1)) return false;
      if (tab.type === "route") return isRecord(tab.route) && typeof tab.route.view === "string" &&
        typeof tab.route.settingsSection === "string" && (tab.route.activeKey === null || typeof tab.route.activeKey === "string") && !tab.route.temporary;
      return typeof tab.type === "string" && panels.has(tab.type) && (tab.sessionKey === null || typeof tab.sessionKey === "string");
    })) throw new Error("Saved workspace tabs have an invalid format");
    const seen = new Set<string>();
    const tabs = (value as WorkspaceTab[]).map(tab => tab.type === "route"
      ? { ...tab, ownerId: tab.ownerId ?? crypto.randomUUID(), id: routeTabId(tab.route) } : tab).filter(tab => {
        const key = tab.type === "route" ? tab.id : panelTabIdentity(tab, panels) ?? tab.id;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    return { tabs: tabs.length === 0 || tabs.some(tab => tab.id === current.id) ? tabs : [...tabs, current], error: "" };
  } catch (error) {
    return { tabs: [current], error: `Could not restore workspace tabs: ${String(error)}` };
  }
}
export function persistTabs(tabs: WorkspaceTab[]) {
  localStorage.setItem(KEY, JSON.stringify(tabs.filter(tab => tab.type !== "route" || !tab.route.temporary)));
}
