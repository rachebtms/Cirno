import type { WorkspaceTab } from "../contracts";

/** Keep selection in the removed tab's group, preferring its preceding neighbor. */
export function tabNeighbor(tabs: readonly WorkspaceTab[], removedId: string, remaining: readonly WorkspaceTab[]) {
  const index = tabs.findIndex(tab => tab.id === removedId);
  const removed = tabs[index];
  if (!removed) return undefined;
  const siblings = remaining.filter(tab => (tab.group ?? 0) === (removed.group ?? 0));
  return [...siblings].reverse().find(tab => tabs.indexOf(tab) < index) ?? siblings[0];
}
