import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { Boxes } from "lucide-react";
import { useWorkbench } from "@/features/workbench/model/useWorkbench";
import { createWorkspaceRegistry } from "@/features/workbench/registry";
import type { WorkbenchProps } from "@/features/workbench/contracts";
import type { CirnoClient } from "@/lib/cirno-client";

beforeEach(() => localStorage.clear());
function setup() {
  const props: WorkbenchProps = {
    client: {} as CirnoClient, route: { view: "chat", activeKey: null, settingsSection: "overview" },
    navigationSequence: 0, sessionsLoaded: true, title: "Conversation", children: null, sessions: [],
    onRouteVisibleChange: vi.fn(), onRoute: vi.fn(), onNewChat: vi.fn(), beforeActivate: action => action(),
  };
  const panels = createWorkspaceRegistry([{ id: "notes", panels: [{
    kind: "notes.editor", titleKey: "Notes", Icon: Boxes, Content: () => null, tabPolicy: "multiple", showInMenu: true,
  }] }]);
  return { ...renderHook(() => useWorkbench(props, panels)), props };
}
it("keeps a newly opened panel active while an older panel finishes closing", async () => {
  const { result, props } = setup();
  act(() => result.current.open("notes.editor"));
  const first = result.current.active;
  let finish!: () => void;
  const dispose = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  act(() => result.current.registerClose(first, dispose));
  let closing!: Promise<void>;
  act(() => { closing = result.current.close(first); });
  act(() => result.current.open("notes.editor"));
  const second = result.current.active;
  await act(async () => { finish(); await closing; });
  expect(result.current.active).toBe(second);
  expect(result.current.tabs.some(tab => tab.id === first)).toBe(false);
  expect(props.onRoute).not.toHaveBeenCalled();
});
it("disposes a panel once when close is requested twice before completion", async () => {
  const { result } = setup();
  act(() => result.current.open("notes.editor"));
  const id = result.current.active;
  let finish!: () => void;
  const dispose = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  act(() => result.current.registerClose(id, dispose));
  let closing!: Promise<void>;
  act(() => { closing = result.current.close(id); void result.current.close(id); });
  expect(dispose).toHaveBeenCalledTimes(1);
  expect(result.current.closing.has(id)).toBe(true);
  await act(async () => { finish(); await closing; });
  await waitFor(() => expect(result.current.closing.size).toBe(0));
});

it("preserves a replacement route when its previous conversation disappears in the same update", async () => {
  const props: WorkbenchProps = {
    client: {} as CirnoClient, route: { view: "chat", activeKey: "websocket:beta", settingsSection: "overview" },
    navigationSequence: 0, sessionsLoaded: true, title: "Conversation", children: null, sessions: ["alpha", "beta"].map(id => ({ key: `websocket:${id}`, chatId: id, channel: "websocket", title: id, preview: "", createdAt: null, updatedAt: null })),
    onRouteVisibleChange: vi.fn(), onRoute: vi.fn(), onNewChat: vi.fn(), beforeActivate: action => action(),
  };
  const panels = createWorkspaceRegistry([]);
  const { result, rerender } = renderHook((current: WorkbenchProps) => useWorkbench(current, panels), { initialProps: props });
  rerender({ ...props, route: { ...props.route, activeKey: "websocket:alpha" }, sessions: props.sessions.slice(0, 1) });
  await waitFor(() => expect(result.current.selected).toMatchObject({ type: "route", route: { activeKey: "websocket:alpha" } }));
  expect(result.current.tabs.some(tab => tab.type === "route" && tab.route.activeKey === "websocket:beta")).toBe(false);
  expect(props.onNewChat).not.toHaveBeenCalled();
});
