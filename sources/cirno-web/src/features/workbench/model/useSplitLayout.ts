import { useEffect, useRef, useState } from "react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import type { TabGroup } from "../contracts";
import type { WorkbenchModel } from "./useWorkbench";
import { readGroupLayout, saveGroupLayout, type GroupLayout } from "./group-layout";

/** Mobile shows all tabs once; desktop ownership and both selections stay intact. */
export function useSplitLayout(model: WorkbenchModel) {
  const desktop = useMediaQuery("(min-width: 1024px)");
  const [initial] = useState(readGroupLayout);
  const [state, setState] = useState(initial.layout);
  const [error, setError] = useState(initial.error);
  const previous = useRef<string | null>(null);
  const activeTab = model.tabs.find(tab => tab.id === model.active);
  const groupTabs = ([0, 1] as const).map(group => model.tabs.filter(tab => (tab.group ?? 0) === group));
  const selected = groupTabs.map((tabs, group) => tabs.find(tab => tab.id === state.selected[group])?.id ?? tabs.at(-1)?.id ?? null);
  // New activations select their owning group, without disturbing the other group's page.
  useEffect(() => {
    if (previous.current === model.active) return;
    previous.current = model.active;
    if (!activeTab) return;
    const group = activeTab.group ?? 0;
    setState(current => ({ ...current, focused: group,
      selected: current.selected.map((id, index) => index === group ? activeTab.id : id) as GroupLayout["selected"] }));
  }, [model.active, activeTab]);
  useEffect(() => {
    try { saveGroupLayout(state); }
    catch (reason) { setError(`Could not save tab groups: ${String(reason)}`); }
  }, [state]);
  const focus = (group: TabGroup) => {
    model.focusGroup(group);
    setState(current => current.focused === group ? current : { ...current, focused: group });
  };
  const activate = (id: string) => {
    const tab = model.tabs.find(tab => tab.id === id);
    if (!tab) return;
    const group = tab.group ?? 0;
    focus(group);
    setState(current => ({ ...current, selected: current.selected.map((old, index) => index === group ? id : old) as GroupLayout["selected"] }));
    model.activate(tab);
  };
  const enabled = state.enabled || groupTabs[1].length > 0;
  const transfer = (id: string, group: TabGroup, before?: string) => {
    focus(group);
    setState(current => ({ ...current, selected: current.selected.map((old, index) => index === group ? id : old) as GroupLayout["selected"] }));
    model.move(id, group, before);
  };
  const toggle = () => {
    if (enabled) model.mergeGroups();
    const focused: TabGroup = enabled ? 0 : 1;
    model.focusGroup(focused);
    setState(current => ({ ...current, enabled: !enabled, focused,
      selected: enabled ? [model.active || selected[0] || selected[1], null] : [model.active || selected[0], null] }));
  };
  const mobileSelected = activeTab?.id ?? selected[state.focused] ?? selected[1 - state.focused];
  const slots = desktop && enabled ? selected : [mobileSelected];
  return { desktop, split: desktop && enabled, enabled, toggle, focus, activate,
    focused: state.focused, selected, groupTabs, slots, error, transfer, ratio: state.ratio,
    resize: (ratio: number) => setState(current => ({ ...current, ratio })) };
}
export type SplitLayout = ReturnType<typeof useSplitLayout>;
