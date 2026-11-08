import { useStripReorder } from "./useStripReorder";
import { useSelectedTabVisibility } from "./useSelectedTabVisibility";
import { Button, Spinner, Tabs } from "@heroui/react";
import { Columns2, ArrowLeftRight, X, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TabGroup, WorkspaceTab } from "../contracts";
import type { WorkbenchModel } from "../model/useWorkbench";
import type { SplitLayout } from "../model/useSplitLayout";

export function TabBar({ model, title, icon, runningChatIds, split, group, tabs, selected }: {
  model: WorkbenchModel; title: (tab: WorkspaceTab) => string;
  split: SplitLayout; group: TabGroup; tabs: WorkspaceTab[]; selected: string | null;
  icon: (tab: WorkspaceTab) => LucideIcon; runningChatIds?: ReadonlySet<string>;
}) {
  const { t } = useTranslation();
  const reorder = useStripReorder(tabs.map(tab => tab.id), model.reorder, split.split ? (id, target, before) => {
    if (id === before) return;
    const tab = model.tabs.find(tab => tab.id === id);
    const nextGroup = Number(target) as TabGroup;
    if ((tab?.group ?? 0) === nextGroup) { if (before) model.reorder(id, before); }
    else split.transfer(id, nextGroup, before);
  } : undefined);
  const viewport = useSelectedTabVisibility(selected, model.active === selected ? model.focusRevision : null);
  return <div className="workbench-group-bar" data-tab-group={group} style={{ gridColumn: group === 1 ? 3 : 1, gridRow: 1 }}
    onPointerDownCapture={() => split.focus(group)} onFocusCapture={() => split.focus(group)}>
    <Tabs className="workbench-tabs" variant="secondary" selectedKey={selected ?? ""}
      onSelectionChange={id => split.activate(String(id))}>
      <div ref={viewport} className="workbench-tabs-viewport" data-dragging={reorder.dragged ?? undefined} {...reorder.handlers}>
        <Tabs.List aria-label={t("workspace.tabs")} className="workbench-tab-list">
          {tabs.map(tab => {
            const Icon = icon(tab), label = title(tab);
            const running = tab.type === "route" && tab.route.view === "chat" && tab.route.activeKey &&
              runningChatIds?.has(tab.route.activeKey.replace(/^websocket:/, ""));
            return <Tabs.Tab key={tab.id} id={tab.id} data-reorder-id={tab.id} aria-label={label} className="workbench-tab">
              <Icon size={16} strokeWidth={1.7} aria-hidden /><span className="workbench-tab-title">{label}</span>
              {running && <Spinner size="sm" aria-label={t("workspace.loading")} />}
              <Button isIconOnly variant="ghost" size="sm" className="workbench-tab-close"
                isDisabled={model.closing.has(tab.id)} aria-label={t("workspace.closeTab", { title: label })}
                onClick={event => event.stopPropagation()} onPress={() => model.requestClose(tab.id)}><X size={14} /></Button>
              <Tabs.Indicator />
            </Tabs.Tab>;
          })}
        </Tabs.List>
      </div>
    </Tabs>
    {split.desktop && <div className="workbench-group-actions">
      {split.split && selected && <Button isIconOnly variant="ghost" aria-label={t("workspace.moveOtherGroup")}
        onPress={() => { const other = (1 - group) as TabGroup; split.transfer(selected, other); }}><ArrowLeftRight size={16} /></Button>}
      <Button isIconOnly variant="ghost" aria-label={t(split.split ? "workspace.unsplit" : "workspace.split")} aria-pressed={split.split}
        onPress={split.toggle}><Columns2 size={18} /></Button>
    </div>}
  </div>;
}
