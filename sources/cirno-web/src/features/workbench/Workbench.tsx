import { TabSurface } from "@/ui/layout/TabSurface";
import { routerLabel } from "@/lib/conversation-role";
import { useSplitLayout } from "./model/useSplitLayout";
import { SplitDivider } from "./ui/SplitDivider";
import { usePreferenceStatus } from "@/hooks/usePreferences";
import { Alert, Button, Spinner } from "@heroui/react";
import { Suspense, useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { TabGroup, WorkbenchProps } from "./contracts";
import { WorkspaceOpenContext } from "./context";
import { workspacePanels } from "./modules";
import { useWorkbench } from "./model/useWorkbench";
import { tabPresentation } from "./model/presentation";
import { DiscardDialog } from "./ui/DiscardDialog";
import { Launcher } from "./ui/Launcher";
import { TabBar } from "./ui/TabBar";
import "./workbench.css";

export function Workbench(props: WorkbenchProps) {
  const { t } = useTranslation(), preferenceStatus = usePreferenceStatus();
  const panels = props.panels ?? workspacePanels;
  const model = useWorkbench(props, panels), layout = useSplitLayout(model);
  const routeVisible = model.tabs.some(tab => tab.type === "route" && layout.slots.includes(tab.id));
  useEffect(() => props.onRouteVisibleChange(routeVisible), [routeVisible, props.onRouteVisibleChange]);
  const presentation = tabPresentation(props, panels, t, model.routeKey);
  const position = (id: string) => ({ gridColumn: layout.split && layout.slots[1] === id ? 3 : 1, gridRow: 2 });
  const visibleTabs = model.tabs.filter(tab => model.visited.has(tab.id) || layout.slots.includes(tab.id));
  const groups: TabGroup[] = layout.split ? [0, 1] : [0];
  return panels.wrap(<WorkspaceOpenContext.Provider value={(kind, options) => model.open(kind, options.path, { id: "source", type: "files", ...options })}>
    <div className="workbench" data-workspace-shell>
      <Launcher model={model} panels={panels} route={props.route} inboxUnread={props.inboxUnread} routerName={routerLabel(props.sessions)} onNewChat={props.onNewChat} />
      <div className="workbench-body">
        {(model.error || layout.error || preferenceStatus.error) && <Alert status="danger" role="alert"><Alert.Content><Alert.Description>{model.error || layout.error || preferenceStatus.error}</Alert.Description></Alert.Content></Alert>}
        <div className="workbench-surfaces" data-split={layout.split || undefined}
          style={layout.split ? { gridTemplateColumns: `minmax(0, ${layout.ratio}fr) 5px minmax(0, ${100 - layout.ratio}fr)` } : undefined}>
          {groups.map(group => <TabBar key={group} model={model} {...presentation} runningChatIds={props.runningChatIds} split={layout}
            group={group} tabs={layout.split ? layout.groupTabs[group] : model.tabs} selected={layout.slots[group] ?? null} />)}
          {visibleTabs.map(tab => {
            const visible = layout.slots.includes(tab.id);
            const Content = tab.type === "route" ? null : panels.get(tab.type).Content;
            return <TabSurface key={tab.ownerId ?? tab.id} role="tabpanel" hidden={!visible} style={position(tab.id)} className="workbench-pane" aria-label={presentation.title(tab)}
              onPointerDownCapture={() => { if (model.active !== tab.id) layout.activate(tab.id); }} onFocusCapture={() => { if (model.active !== tab.id) layout.activate(tab.id); }}>
              {tab.type === "route" ? props.renderRoute?.(tab.route, visible, model.active === tab.id) ?? (model.active === tab.id ? props.children : null) : Content &&
                <Suspense fallback={<div className="workbench-loading"><Spinner size="sm" /><span>{t("workspace.loading")}</span></div>}>
                  <Content tab={tab} client={props.client} active={visible} setDirty={model.setDirty}
                    registerClose={model.registerClose} openFile={(path, parent) => model.open("file", path, parent)} />
                </Suspense>}
            </TabSurface>;
          })}
          {groups.map(group => !layout.slots[group] && <section key={`empty-${group}`} className="workbench-empty" data-tab-group={group}
            style={{ gridColumn: group === 1 ? 3 : 1, gridRow: 2 }} onPointerDown={() => layout.focus(group)}>
            <p>{t("workspace.emptyGroup")}</p><Button variant="secondary" onPress={() => { layout.focus(group); props.onNewChat(); }}>{t("sidebar.newChat")}</Button>
          </section>)}
          {layout.split && <SplitDivider value={layout.ratio} onChange={layout.resize} />}
        </div>
      </div><DiscardDialog model={model} />
    </div>
  </WorkspaceOpenContext.Provider>);
}
