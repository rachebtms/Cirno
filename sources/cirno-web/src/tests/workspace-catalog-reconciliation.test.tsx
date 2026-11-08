import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useWorkbench } from "@/features/workbench/model/useWorkbench";
import { createWorkspaceRegistry } from "@/features/workbench/registry";
import type { WorkbenchProps } from "@/features/workbench/contracts";
import type { CirnoClient } from "@/lib/cirno-client";

beforeEach(() => localStorage.clear());
const panels = createWorkspaceRegistry([]);
const route = (id: string) => ({ view: "chat", activeKey: `websocket:${id}`, settingsSection: "overview" });
function props(id: string, ids: string[]): WorkbenchProps {
  return { client: {} as CirnoClient, route: route(id), navigationSequence: 0, title: id, sessionsLoaded: true,
    sessions: ids.map(id => ({ key: `websocket:${id}`, chatId: id, channel: "websocket", preview: "", createdAt: null, updatedAt: null })),
    onRouteVisibleChange: vi.fn(), onRoute: vi.fn(), onNewChat: vi.fn(), beforeActivate: action => action() };
}
function retain(ids: [string, number][]) {
  localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify(ids.map(([id, group]) => ({
    id: `chat:websocket:${id}`, type: "route", group, route: route(id),
  }))));
}

it("uses the same group neighbor after deletion as after closing, rather than selecting an unrelated group", async () => {
  retain([["alpha", 1], ["beta", 1], ["unrelated", 0]]);
  const initial = props("beta", ["alpha", "beta", "unrelated"]);
  const { result, rerender } = renderHook((value: WorkbenchProps) => useWorkbench(value, panels), { initialProps: initial });
  rerender({ ...initial, sessions: initial.sessions.filter(session => session.chatId !== "beta") });
  await waitFor(() => expect(initial.onRoute).toHaveBeenCalledWith(route("alpha")));
  expect(result.current.active).toBe("chat:websocket:alpha");
  expect(initial.onNewChat).not.toHaveBeenCalled();
});

it("does not prune retained conversations from a partial or failed catalog read", async () => {
  retain([["alpha", 0], ["beta", 1]]);
  const initial: WorkbenchProps = { ...props("alpha", []), sessionsLoaded: false };
  const { result, rerender } = renderHook((value: WorkbenchProps) => useWorkbench(value, panels), { initialProps: initial });
  expect(result.current.tabs).toHaveLength(2);
  rerender({ ...initial, sessions: props("alpha", ["alpha"]).sessions });
  expect(result.current.tabs).toHaveLength(2);
  rerender(props("alpha", ["alpha"]));
  await waitFor(() => expect(result.current.tabs).toHaveLength(1));
  expect(result.current.active).toBe("chat:websocket:alpha");
});

it("retains first-message admission before the complete catalog includes its new destination", async () => {
  const initial: WorkbenchProps = { ...props("pending", []), admittedSessionKey: "websocket:pending" };
  const { result, rerender } = renderHook((value: WorkbenchProps) => useWorkbench(value, panels), { initialProps: initial });
  expect(result.current.tabs).toHaveLength(1);
  expect(initial.onNewChat).not.toHaveBeenCalled();
  rerender(props("pending", ["pending"]));
  await act(async () => {});
  expect(result.current.active).toBe("chat:websocket:pending");
});
