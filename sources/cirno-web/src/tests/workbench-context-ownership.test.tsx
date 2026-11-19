import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { Boxes } from "lucide-react";
import { useWorkbench } from "@/features/workbench/model/useWorkbench";
import { createWorkspaceRegistry } from "@/features/workbench/registry";
import { filesModule } from "@/features/files/module";
import type { PanelKind, WorkbenchProps } from "@/features/workbench/contracts";
import type { CirnoClient } from "@/lib/cirno-client";

beforeEach(() => localStorage.clear());
const panels = createWorkspaceRegistry([filesModule, { id: "notes", panels: [{
  kind: "notes.editor", titleKey: "Notes", Icon: Boxes, Content: () => null,
  tabPolicy: "multiple", showInMenu: true,
}] }]);
function setup() {
  const props: WorkbenchProps = {
    client: {} as CirnoClient, route: { view: "chat", activeKey: "websocket:a", settingsSection: "overview" },
    scope: { project_path: "/research", access_mode: "full" },
    navigationSequence: 0, title: "Conversation", sessions: [],
    onRouteVisibleChange: vi.fn(), onRoute: vi.fn(), onNewChat: vi.fn(), beforeActivate: action => action(),
  };
  const hook = renderHook((value: WorkbenchProps) => useWorkbench(value, panels), { initialProps: props });
  return { ...hook, props };
}
for (const kind of ["file", "files.preview"] satisfies PanelKind[]) {
  for (const field of ["session", "access"] as const) {
    it(`keeps ${kind} request ownership separate after ${field} changes`, () => {
      const { result, rerender, props } = setup();
      act(() => result.current.open(kind, "notes.md"));
      const original = result.current.active;
      const next = field === "session"
        ? { ...props, route: { ...props.route, activeKey: "websocket:b" } }
        : { ...props, scope: { ...props.scope!, access_mode: "review" as const } };
      rerender(next);
      act(() => result.current.open(kind, "notes.md"));
      expect(result.current.active).not.toBe(original);
      expect(result.current.tabs.filter(tab => tab.type === kind)).toHaveLength(2);
      expect(result.current.selected).toMatchObject({
        type: kind, sessionKey: next.route.activeKey, scope: next.scope,
      });
    });
  }
}
it("reuses the same document when only scope display metadata changes", () => {
  const { result, rerender, props } = setup();
  act(() => result.current.open("file", "notes.md"));
  const original = result.current.active;
  rerender({ ...props, scope: { ...props.scope!, project_name: "Renamed project" } });
  act(() => result.current.open("file", "notes.md"));
  expect(result.current.active).toBe(original);
  expect(result.current.tabs.filter(tab => tab.type === "file")).toHaveLength(1);
});
it("does not resurrect a closed panel when opening its neighbor before rendering", async () => {
  const { result } = setup();
  act(() => result.current.open("notes.editor"));
  const closed = result.current.active;
  await act(async () => {
    await result.current.close(closed);
    result.current.open("notes.editor");
  });
  expect(result.current.tabs.some(tab => tab.id === closed)).toBe(false);
  expect(result.current.tabs.filter(tab => tab.type === "notes.editor")).toHaveLength(1);
});
it("does not restore either panel after simultaneous asynchronous closes and a new open", async () => {
  const { result } = setup();
  act(() => result.current.open("notes.editor"));
  const first = result.current.active;
  act(() => result.current.open("notes.editor"));
  const second = result.current.active;
  let finishFirst!: () => void, finishSecond!: () => void;
  act(() => {
    result.current.registerClose(first, () => new Promise<void>(resolve => { finishFirst = resolve; }));
    result.current.registerClose(second, () => new Promise<void>(resolve => { finishSecond = resolve; }));
  });
  let one!: Promise<void>, two!: Promise<void>;
  act(() => { one = result.current.close(first); two = result.current.close(second); });
  await act(async () => {
    finishFirst(); finishSecond(); await Promise.all([one, two]);
    result.current.open("notes.editor");
  });
  expect(result.current.tabs.some(tab => tab.id === first || tab.id === second)).toBe(false);
  expect(result.current.tabs.filter(tab => tab.type === "notes.editor")).toHaveLength(1);
});
it("does not activate a tab removed while its navigation guard was pending", async () => {
  const { result, rerender, props } = setup();
  const target = result.current.selected!;
  act(() => result.current.open("notes.editor"));
  const active = result.current.active;
  let confirm!: () => void;
  rerender({ ...props, beforeActivate: action => { confirm = action; } });
  act(() => result.current.activate(target));
  await act(async () => { await result.current.close(target.id); });
  act(() => confirm());
  expect(result.current.active).toBe(active);
  expect(props.onRoute).not.toHaveBeenCalled();
});
it("uses the surviving tab's latest group after a delayed activation", () => {
  const { result, rerender, props } = setup();
  act(() => result.current.open("notes.editor"));
  const target = result.current.selected!;
  let confirm!: () => void;
  rerender({ ...props, beforeActivate: action => { confirm = action; } });
  act(() => result.current.activate(target));
  const activate = confirm;
  act(() => result.current.move(target.id, 1));
  act(() => confirm());
  act(() => activate());
  act(() => result.current.open("notes.editor"));
  act(() => confirm());
  expect(result.current.selected?.group).toBe(1);
});
it("keeps the panel after disposal fails and allows a deliberate close retry", async () => {
  const { result } = setup();
  act(() => result.current.open("notes.editor"));
  const id = result.current.active;
  const dispose = vi.fn().mockRejectedValueOnce(new Error("Connection unavailable")).mockResolvedValue(undefined);
  act(() => result.current.registerClose(id, dispose));
  await act(async () => { await result.current.close(id); });
  expect(result.current.tabs.some(tab => tab.id === id)).toBe(true);
  expect(result.current.error).toContain("Connection unavailable");
  expect(result.current.closing.size).toBe(0);
  await act(async () => { await result.current.close(id); });
  expect(result.current.tabs.some(tab => tab.id === id)).toBe(false);
  expect(dispose).toHaveBeenCalledTimes(2);
});
it("preserves a reorder when another panel opens before the next render", () => {
  const { result } = setup();
  act(() => result.current.open("notes.editor"));
  const first = result.current.active;
  act(() => result.current.open("notes.editor"));
  const second = result.current.active;
  act(() => { result.current.reorder(second, first); result.current.open("notes.editor"); });
  const order = result.current.tabs.map(tab => tab.id);
  expect(order.indexOf(second)).toBeLessThan(order.indexOf(first));
});
it("preserves a group merge when another panel opens before the next render", () => {
  const { result } = setup();
  act(() => result.current.open("notes.editor"));
  const id = result.current.active;
  act(() => result.current.move(id, 1));
  act(() => { result.current.mergeGroups(); result.current.open("notes.editor"); });
  expect(result.current.tabs.find(tab => tab.id === id)?.group).toBe(0);
});
it("keeps the mounted draft owner while admitting its first message before catalog arrival", () => {
  const { result, rerender, props } = setup();
  const draft = { ...props, route: { ...props.route, activeKey: null }, sessionsLoaded: true };
  rerender(draft);
  const ownerId = result.current.selected?.ownerId;
  const admitted = { ...draft, route: { ...draft.route, activeKey: "websocket:new" }, admittedSessionKey: "websocket:new" };
  rerender(admitted);
  expect(result.current.selected).toMatchObject({ id: "chat:websocket:new", ownerId });
  expect(result.current.tabs.some(tab => tab.id === "chat:new")).toBe(false);
  expect(props.onNewChat).not.toHaveBeenCalled();
});
