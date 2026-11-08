import type { WorkspaceTab } from "../contracts";
/** A first message changes its destination, while retaining the draft's mounted owner. */
export function updateRouteTab(tabs: WorkspaceTab[], next: WorkspaceTab, { admitDraft, requested }: { admitDraft: boolean; requested: boolean }) {
  const source = admitDraft ? tabs.find(tab => tab.id === "chat:new") : tabs.find(tab => tab.id === next.id);
  if (source) return tabs.filter(tab => tab.id !== next.id || tab === source).map(tab => tab === source
    ? { ...next, group: source.group, ownerId: source.ownerId ?? source.id } : tab);
  return requested ? [...tabs, next] : tabs;
}
