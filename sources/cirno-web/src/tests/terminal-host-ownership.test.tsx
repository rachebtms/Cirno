import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useTerminalHosts } from "@/features/terminal/model/useTerminalHosts";
import type { CirnoClient } from "@/lib/cirno-client";

function pending<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
it("does not display another server's SSH choices while the new catalog is pending", async () => {
  const request = vi.fn().mockResolvedValue({ nodes: [{ id: "old", name: "Old server node" }] });
  const client = { requestMutation: request } as unknown as CirnoClient;
  const next = pending<{ nodes: { id: string; name: string }[] }>();
  const replacement = { requestMutation: vi.fn(() => next.promise) } as unknown as CirnoClient;
  const view = renderHook(({ client }) => useTerminalHosts(client), { initialProps: { client } });
  await act(async () => {});
  expect(view.result.current.nodes).toHaveLength(1);
  view.rerender({ client: replacement });
  expect(view.result.current.nodes).toEqual([]);
  await act(async () => next.resolve({ nodes: [{ id: "new", name: "New node" }] }));
  expect(view.result.current.nodes.map(node => node.id)).toEqual(["new"]);
});
it("clears another server's catalog error and ignores its retained retry action", async () => {
  const request = vi.fn().mockRejectedValue(new Error("Old catalog failed"));
  const client = { requestMutation: request } as unknown as CirnoClient;
  const replacementRequest = vi.fn(() => pending<{ nodes: [] }>().promise);
  const replacement = { requestMutation: replacementRequest } as unknown as CirnoClient;
  const view = renderHook(({ client }) => useTerminalHosts(client), { initialProps: { client } });
  await act(async () => {});
  expect(view.result.current.error).toContain("Old catalog failed");
  const retry = view.result.current.retry;
  view.rerender({ client: replacement });
  expect(view.result.current.error).toBe("");
  act(() => retry());
  expect(replacementRequest).toHaveBeenCalledTimes(1);
});
it("ignores late nodes from the retired client and permits a current retry", async () => {
  const first = pending<{ nodes: { id: string; name: string }[] }>();
  const client = { requestMutation: vi.fn(() => first.promise) } as unknown as CirnoClient;
  const request = vi.fn().mockRejectedValueOnce(new Error("Retry this catalog")).mockResolvedValue({ nodes: [{ id: "new", name: "New" }] });
  const replacement = { requestMutation: request } as unknown as CirnoClient;
  const view = renderHook(({ client }) => useTerminalHosts(client), { initialProps: { client } });
  view.rerender({ client: replacement });
  await act(async () => first.resolve({ nodes: [{ id: "old", name: "Old" }] }));
  expect(view.result.current.nodes).toEqual([]);
  expect(view.result.current.error).toBe("Retry this catalog");
  act(() => view.result.current.retry());
  await act(async () => {});
  expect(view.result.current.nodes.map(node => node.id)).toEqual(["new"]);
  expect(view.result.current.error).toBe("");
});
