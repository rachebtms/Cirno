import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { KeyRound } from "lucide-react";
import { useWorkbench } from "@/features/workbench/model/useWorkbench";
import { createWorkspaceRegistry } from "@/features/workbench/registry";
import { restoreTabs } from "@/features/workbench/model/persistence";
import type { WorkbenchProps } from "@/features/workbench/contracts";
import type { CirnoClient } from "@/lib/cirno-client";

const panels = createWorkspaceRegistry([{ id: "policy-fixture", panels: [
  { kind: "credentials", titleKey: "Vault", Icon: KeyRound, Content: () => null, showInMenu: true, tabPolicy: "single" },
  { kind: "terminal", titleKey: "Terminal", Icon: KeyRound, Content: () => null, showInMenu: true, tabPolicy: "multiple" },
  { kind: "file", titleKey: "Editor", Icon: KeyRound, Content: () => null, showInMenu: false, tabPolicy: { identity: tab => tab.path! } },
] }]);
const props = (): WorkbenchProps => ({ client: {} as CirnoClient,
  route: { view: "chat", activeKey: null, settingsSection: "overview" }, navigationSequence: 0,
  title: "Chat", children: null, sessions: [], onRouteVisibleChange: vi.fn(), onRoute: vi.fn(),
  onNewChat: vi.fn(), beforeActivate: action => action(),
});
beforeEach(() => localStorage.clear());
it("reuses registered singletons including rapid activations and retains their dirty owner", () => {
  const { result } = renderHook(() => useWorkbench(props(), panels));
  act(() => { result.current.open("credentials"); result.current.open("credentials"); });
  const id = result.current.active;
  act(() => result.current.setDirty(id, true));
  act(() => result.current.open("terminal"));
  act(() => result.current.open("credentials"));
  expect(result.current.tabs.filter(tab => tab.type === "credentials")).toHaveLength(1);
  expect(result.current.active).toBe(id);
  act(() => result.current.requestClose(id));
  expect(result.current.pendingClose).toBe(id);
});
it("creates separate terminals but reuses an already opened document", () => {
  const { result } = renderHook(() => useWorkbench(props(), panels));
  act(() => { result.current.open("terminal"); result.current.open("terminal"); });
  act(() => { result.current.open("file", "/a.md"); result.current.open("file", "/b.md"); result.current.open("file", "/a.md"); });
  expect(result.current.tabs.filter(tab => tab.type === "terminal")).toHaveLength(2);
  expect(result.current.tabs.filter(tab => tab.type === "file")).toHaveLength(2);
  expect(result.current.selected).toMatchObject({ type: "file", path: "/a.md" });
});
it("restores singleton utilities once while retaining all independent terminals", () => {
  localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify([
    ...["a", "b"].map(id => ({ id, type: "credentials", sessionKey: null })),
    ...["c", "d"].map(id => ({ id, type: "terminal", sessionKey: null })),
    ...["e", "f"].map(id => ({ id, type: "route", route: { view: "settings", settingsSection: "account", activeKey: null, tabId: id } })),
  ]));
  const restored = restoreTabs(props().route, panels);
  expect(restored.error).toBe("");
  expect(restored.tabs.filter(tab => tab.type === "credentials")).toHaveLength(1);
  expect(restored.tabs.filter(tab => tab.type === "terminal")).toHaveLength(2);
  expect(restored.tabs.filter(tab => tab.type === "route" && tab.route.view === "settings")).toHaveLength(1);
});
