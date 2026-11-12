import { useCallback, useEffect, useRef, useState } from "react";
import type { PanelKind, PanelTab, TabGroup, WorkbenchProps, WorkspaceTab } from "../contracts";
import type { WorkspaceRegistry } from "../registry";
import { updateRouteTab } from "./route-admission";
import { tabNeighbor } from "./tab-neighbor";
import { reorderItems } from "./reorder";
import { panelTabIdentity } from "./tab-policy";
import { persistTabs, restoreTabs, routeTabId } from "./persistence";

/** Owns tab identity and resource lifetime; views only express user actions. */
export function useWorkbench(props: WorkbenchProps, panels: WorkspaceRegistry) {
  const [initial] = useState(() => restoreTabs(props.route, panels));
  const [tabs, setTabs] = useState(initial.tabs);
  const [selection, setSelection] = useState(() => ({
    id: initial.tabs.some(tab => tab.id === routeTabId(props.route)) ? routeTabId(props.route) : "", revision: 0,
  }));
  const active = selection.id;
  const setActive = useCallback((id: string) => setSelection(old => ({ id, revision: old.revision + 1 })), []);
  const [visited, setVisited] = useState(() => new Set([active]));
  const [error, setError] = useState(initial.error);
  const [pendingClose, setPendingClose] = useState<string | null>(null);
  const [closing, setClosing] = useState<ReadonlySet<string>>(new Set());
  const closingIds = useRef(new Set<string>());
  const currentState = useRef({ tabs, active });
  currentState.current = { tabs, active };
  const dirty = useRef(new Set<string>());
  const closers = useRef(new Map<string, () => Promise<void>>());
  const routeKey = routeTabId(props.route);
  const route = useRef(props.route);
  route.current = props.route;
  const navigationSequence = useRef(props.navigationSequence);
  const selected = tabs.find(tab => tab.id === active);
  const routeVisible = selected?.type === "route";
  const focusedGroup = useRef<TabGroup>(0);
  const mounted = useRef(false);
  const previousRouteKey = useRef(routeKey);
  useEffect(() => {
    setVisited(current => current.has(active) ? current : new Set([...current, active]));
  }, [active]);
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return; }
    const admitDraft = previousRouteKey.current === "chat:new" && props.admittedSessionKey === route.current.activeKey && !!props.admittedSessionKey;
    const requested = navigationSequence.current !== props.navigationSequence || previousRouteKey.current !== routeKey;
    navigationSequence.current = props.navigationSequence;
    previousRouteKey.current = routeKey;
    const next: WorkspaceTab = { id: routeKey, type: "route", route: route.current, group: focusedGroup.current, ownerId: crypto.randomUUID() };
    setTabs(current => updateRouteTab(current, next, { admitDraft, requested }));
    if (requested) setActive(routeKey);
  }, [routeKey, props.navigationSequence, props.route.temporary, props.route.settingsSection, props.admittedSessionKey]);
  useEffect(() => {
    if (!props.sessionsLoaded) return;
    const known = new Set(props.sessions.map(session => session.key));
    const invalid = (tab: WorkspaceTab) => tab.type === "route" && tab.route.view === "chat"
      && !!tab.route.activeKey && !tab.route.temporary && !known.has(tab.route.activeKey)
      && props.admittedSessionKey !== tab.route.activeKey;
    const remaining = tabs.filter(tab => !invalid(tab));
    if (remaining.length === tabs.length) return;
    setTabs(current => current.filter(tab => !invalid(tab)));
    if (remaining.some(tab => tab.id === active)) return;
    // A simultaneous route change owns the new selection, including first-message admission.
    if (routeKey !== active) return;
    const next = tabNeighbor(tabs, active, remaining);
    setActive(next?.id ?? "");
    if (next?.type === "route") props.onRoute(next.route);
    else if (!next) props.onNewChat();
  }, [props.sessions, props.sessionsLoaded, props.admittedSessionKey, props.onRoute, props.onNewChat, tabs, active, routeKey]);
  useEffect(() => {
    try { persistTabs(tabs); }
    catch (reason) { setError(`Could not save workspace tabs: ${String(reason)}`); }
  }, [tabs]);
  const reorder = (id: string, before: string) => setTabs(current => reorderItems(current, id, before));
  const setDirty = useCallback((id: string, value: boolean) => {
    if (value) dirty.current.add(id); else dirty.current.delete(id);
  }, []);
  const registerClose = useCallback((id: string, close: () => Promise<void>) => { closers.current.set(id, close); }, []);
  const commitActivation = (tab: WorkspaceTab) => {
    focusedGroup.current = tab.group ?? 0;
    currentState.current = { ...currentState.current, active: tab.id };
    setActive(tab.id);
    if (tab.type === "route") props.onRoute(tab.route);
  };
  const activate = (tab: WorkspaceTab) => props.beforeActivate(() => commitActivation(tab));
  const focusGroup = (group: TabGroup) => { focusedGroup.current = group; };
  const mergeGroups = () => setTabs(current => current.map(tab => ({ ...tab, group: 0 })));
  const move = (id: string, group: TabGroup, before?: string) => props.beforeActivate(() => {
    const current = currentState.current;
    const target = current.tabs.find(tab => tab.id === id);
    if (!target) return;
    const moved = { ...target, group };
    const next = current.tabs.filter(tab => tab.id !== id);
    const index = before ? next.findIndex(tab => tab.id === before) : -1;
    next.splice(index < 0 ? next.length : index, 0, moved);
    currentState.current = { ...current, tabs: next };
    setTabs(next);
    commitActivation(moved);
  });
  const open = (type: PanelKind, path?: string, parent?: PanelTab) => props.beforeActivate(() => {
    const tab: WorkspaceTab & PanelTab = { id: crypto.randomUUID(), type, path, group: focusedGroup.current,
      sessionKey: parent ? parent.sessionKey : props.route.activeKey, scope: parent ? parent.scope : props.scope };
    const identity = panelTabIdentity(tab, panels);
    const current = currentState.current;
    const existing = identity && current.tabs.find(item => item.type !== "route" && panelTabIdentity(item, panels) === identity);
    const selected = existing || tab;
    const next = existing ? current.tabs : [...current.tabs, tab];
    currentState.current = { tabs: next, active: selected.id };
    setTabs(next);
    focusedGroup.current = selected.group ?? 0;
    setActive(selected.id);
  });
  const close = async (id: string) => {
    if (closingIds.current.has(id)) return;
    const tab = currentState.current.tabs.find(item => item.id === id);
    if (!tab) return;
    closingIds.current.add(id);
    setClosing(new Set(closingIds.current));
    try {
      const dispose = closers.current.get(id);
      if (dispose) await dispose();
      else if (tab && tab.type !== "route") await panels.get(tab.type).closeRestored?.(props.client, tab);
      if (tab?.type === "route" && tab.route.temporary && tab.route.activeKey) props.onCloseTemporaryChat?.(tab.route.activeKey);
      closers.current.delete(id);
      dirty.current.delete(id);
      setError("");
      const { tabs: latestTabs, active: latestActive } = currentState.current;
      const remaining = latestTabs.filter(item => item.id !== id);
      const next = tabNeighbor(latestTabs, id, remaining);
      setTabs(current => current.filter(item => item.id !== id));
      if (latestActive === id) { if (next) commitActivation(next); else setActive(""); }
    } catch (reason) { setError(String(reason)); }
    finally { closingIds.current.delete(id); setClosing(new Set(closingIds.current)); }
  };
  const requestClose = (id: string) => {
    if (dirty.current.has(id)) setPendingClose(id);
    else props.beforeActivate(() => void close(id));
  };
  const routeTo = (view: string, activeKey = props.route.activeKey) => props.beforeActivate(() => {
    const requested = { view, activeKey, settingsSection: view === "automations" ? "automations" : "overview" };
    const existing = currentState.current.tabs.find(tab => tab.id === routeTabId(requested));
    props.onRoute(existing?.type === "route" ? existing.route : requested);
  });
  return { tabs, active, focusRevision: selection.revision, visited, selected, routeVisible, routeKey, error, closing,
    pendingClose, setPendingClose, activate, open, close, requestClose, routeTo, reorder, setDirty, registerClose, focusGroup, move, mergeGroups };
}
export type WorkbenchModel = ReturnType<typeof useWorkbench>;
