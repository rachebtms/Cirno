import { StrictMode } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ThreadVisibilityContext } from "@/hooks/useThreadVisibility";
import { useNodes } from "@/features/settings/nodes/model/useNodes";
import type { CirnoClient } from "@/lib/cirno-client";

const policy = { poll_interval_seconds: 60, retention_days: 30 };
const job = { id: "job", node_id: "node", state: "running", command: "train" };
afterEach(() => vi.useRealTimers());

it("refreshes the local catalog without flicker, overlap or SSH calls and stops while hidden", async () => {
  vi.useFakeTimers();
  let lists = 0, visible = true;
  let finish!: (value: unknown) => void;
  const request = vi.fn(async (_action: string, payload: { action: string }) => {
    if (payload.action === "credentials.list") return { records: [] };
    expect(payload.action).toBe("nodes.list");
    lists++;
    if (lists === 2) return new Promise(resolve => { finish = resolve; });
    return { nodes: [], jobs: [job], job_settings: policy };
  });
  const client = { requestMutation: request } as unknown as CirnoClient;
  const view = renderHook(() => useNodes(client), {
    wrapper: ({ children }) => <ThreadVisibilityContext.Provider value={visible}>{children}</ThreadVisibilityContext.Provider>,
  });
  await act(async () => {});
  expect(lists).toBe(1);
  expect(view.result.current.ready).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(lists).toBe(2);
  expect(view.result.current.loading).toBe(false);
  expect(view.result.current.jobs).toEqual([job]);
  await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
  expect(lists).toBe(2);
  await act(async () => finish({ nodes: [], jobs: [{ ...job, state: "completed" }], job_settings: policy }));
  expect(view.result.current.jobs[0].state).toBe("completed");
  visible = false; view.rerender();
  await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
  expect(lists).toBe(2);
  visible = true; view.rerender();
  await act(async () => {});
  expect(lists).toBe(3);
  view.unmount();
  await vi.advanceTimersByTimeAsync(20000);
  expect(lists).toBe(3);
});

it("does not let an older catalog response overwrite freshly saved monitoring settings", async () => {
  let finish!: (value: unknown) => void;
  let lists = 0;
  const request = vi.fn(async (_action: string, payload: { action: string }) => {
    if (payload.action === "credentials.list") return { records: [] };
    if (payload.action === "nodes.settings.save") return { job_settings: { ...policy, poll_interval_seconds: 0 } };
    if (++lists === 2) return new Promise(resolve => { finish = resolve; });
    return { nodes: [], jobs: [], job_settings: policy };
  });
  const client = { requestMutation: request } as unknown as CirnoClient;
  const view = renderHook(() => useNodes(client));
  await act(async () => {});
  let reading!: Promise<void>;
  act(() => { reading = view.result.current.refresh(true); });
  await act(async () => view.result.current.saveJobSettings({ poll_interval_seconds: 0 }));
  await act(async () => {
    finish({ nodes: [], jobs: [], job_settings: policy });
    await reading;
  });
  expect(view.result.current.jobSettings.poll_interval_seconds).toBe(0);
});


it("does not strand the catalog during Strict Mode effect cleanup and replay", async () => {
  const request = vi.fn(async (_action: string, payload: { action: string }) => payload.action === "credentials.list"
    ? { records: [] } : { nodes: [], jobs: [job], job_settings: policy });
  const client = { requestMutation: request } as unknown as CirnoClient;
  const view = renderHook(() => useNodes(client), { wrapper: StrictMode });
  await act(async () => {});
  expect(view.result.current.ready).toBe(true);
  expect(view.result.current.loading).toBe(false);
  expect(view.result.current.jobs).toEqual([job]);
});

it("does not let an older background read restore a Node after its removal", async () => {
  let finish!: (value: unknown) => void;
  let lists = 0;
  const node = { id: "node", name: "Node" };
  const request = vi.fn(async (_action: string, payload: { action: string }) => {
    if (payload.action === "credentials.list") return { records: [] };
    if (payload.action === "nodes.delete") return { ok: true };
    if (++lists === 2) return new Promise(resolve => { finish = resolve; });
    return { nodes: lists === 1 ? [node] : [], jobs: [], job_settings: policy };
  });
  const client = { requestMutation: request } as unknown as CirnoClient;
  const view = renderHook(() => useNodes(client));
  await act(async () => {});
  let reading!: Promise<void>;
  act(() => { reading = view.result.current.refresh(true); });
  await act(async () => view.result.current.remove(view.result.current.nodes[0]));
  expect(view.result.current.nodes).toEqual([]);
  await act(async () => {
    finish({ nodes: [node], jobs: [], job_settings: policy });
    await reading;
  });
  expect(view.result.current.nodes).toEqual([]);
});
