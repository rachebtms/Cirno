import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { createMemoryService } from "@/features/memory/model/service";
import { useMemorySearch } from "@/features/memory/model/useMemorySearch";
import type { MemoryRecord } from "@/lib/contracts/memory";

const record = (id: string): MemoryRecord => ({ id, title: id, source: "fixture", layer: "knowledge", kind: "fact",
  scope: "user", status: "active", revision: 1, tags: [], updated_at: "2026-11-10T00:00:00Z" });
const page = (id: string, offset: number, more: boolean) => ({ memories: [record(id)], links: [], has_more: more, next_offset: offset });
function fixture(handler: (values: Record<string, unknown>) => unknown) {
  const request = vi.fn(async <T,>(_action: string, payload?: Record<string, unknown>) =>
    await handler(payload?.values as Record<string, unknown>) as T);
  return { request, api: createMemoryService({ requestMutation: async <T,>(action: string, payload?: Record<string, unknown>) =>
    await request(action, payload) as T }) };
}

it("loads the applied query serially and publishes each page to the shared results", async () => {
  const pending: ((result: ReturnType<typeof page>) => void)[] = [];
  const source = fixture(values => values.offset ? new Promise(resolve => pending.push(resolve)) : page("one", 30, true));
  const { result } = renderHook(() => useMemorySearch(source.api, true));
  await waitFor(() => expect(result.current.snapshot).not.toBeNull());
  act(() => {
    result.current.change({ query: "unsent draft" });
    void result.current.loadAll();
    void result.current.loadAll();
    void result.current.more();
  });
  expect(source.request).toHaveBeenCalledTimes(2);
  expect(result.current.loadingAll).toBe(true);
  await act(async () => pending[0](page("two", 60, true)));
  expect(result.current.snapshot?.result.memories.map(row => row.id)).toEqual(["one", "two"]);
  expect(source.request).toHaveBeenCalledTimes(3);
  expect(source.request.mock.lastCall?.[1]).toEqual(expect.objectContaining({
    values: expect.objectContaining({ query: "", offset: 60, ids: ["one", "two"] }),
  }));
  await act(async () => pending[1](page("three", 61, false)));
  expect(result.current.snapshot?.result.memories.map(row => row.id)).toEqual(["one", "two", "three"]);
  expect(result.current.loadingAll).toBe(false);
});

it("retains completed pages after an error and retries from the failed cursor", async () => {
  let failed = false;
  const source = fixture(values => {
    if (!values.offset) return page("one", 30, true);
    if (values.offset === 30) return page("two", 60, true);
    if (!failed) { failed = true; throw new Error("Page read failed"); }
    return page("three", 61, false);
  });
  const { result } = renderHook(() => useMemorySearch(source.api, true));
  await waitFor(() => expect(result.current.snapshot).not.toBeNull());
  await act(async () => result.current.loadAll());
  expect(result.current.error).toBe("Page read failed");
  expect(result.current.snapshot?.result.memories).toHaveLength(2);
  expect(result.current.loadingAll).toBe(false);
  await act(async () => result.current.loadAll());
  expect(result.current.error).toBeNull();
  expect(result.current.snapshot?.result.memories).toHaveLength(3);
  expect(source.request.mock.calls.slice(1).map(call => (call[1]?.values as Record<string, unknown>).offset)).toEqual([30, 60, 60]);
});

it("stops a bulk load when a new search replaces its applied filters", async () => {
  let finish!: (value: ReturnType<typeof page>) => void;
  const source = fixture(values => values.query ? page("match", 1, false)
    : values.offset ? new Promise(resolve => { finish = resolve; }) : page("one", 30, true));
  const { result } = renderHook(() => useMemorySearch(source.api, true));
  await waitFor(() => expect(result.current.snapshot).not.toBeNull());
  act(() => { void result.current.loadAll(); });
  await act(async () => { result.current.apply({ query: "latest" }); });
  await act(async () => finish(page("old page", 60, true)));
  expect(result.current.snapshot?.result.memories.map(row => row.id)).toEqual(["match"]);
  expect(result.current.loadingAll).toBe(false);
  expect(source.request).toHaveBeenCalledTimes(3);
});

it.each(["replace", "unmount"])("stops requesting further pages after owner %s", async action => {
  let finish!: (value: ReturnType<typeof page>) => void;
  const first = fixture(values => values.offset ? new Promise(resolve => { finish = resolve; }) : page("first", 30, true));
  const second = fixture(() => page("second", 1, false));
  const state = renderHook(({ service }) => useMemorySearch(service, true), { initialProps: { service: first.api } });
  await waitFor(() => expect(state.result.current.snapshot).not.toBeNull());
  act(() => { void state.result.current.loadAll(); });
  if (action === "replace") state.rerender({ service: second.api });
  else state.unmount();
  await act(async () => finish(page("late", 60, true)));
  expect(first.request).toHaveBeenCalledTimes(2);
  if (action === "replace") expect(state.result.current.snapshot?.result.memories[0].id).toBe("second");
});

it("retains the graph's bounded record and per-request ID limits", async () => {
  const source = fixture(values => {
    const offset = Number(values.offset), limit = Number(values.limit);
    expect((values.ids as string[]).length).toBeLessThan(300);
    return { memories: Array.from({ length: limit }, (_, i) => record(String(offset + i))), links: [],
      next_offset: offset + limit, has_more: true };
  });
  const { result } = renderHook(() => useMemorySearch(source.api, true));
  await waitFor(() => expect(result.current.snapshot).not.toBeNull());
  await act(async () => result.current.loadAll());
  expect(result.current.snapshot?.result.memories).toHaveLength(300);
  expect(result.current.snapshot?.result.has_more).toBe(false);
  expect(source.request).toHaveBeenCalledTimes(10);
});

it("uses a configurable graph limit above 300 and preserves the applied query when it changes", async () => {
  const source = fixture(values => {
    const offset = Number(values.offset), limit = Number(values.limit);
    return { memories: Array.from({ length: limit }, (_, i) => record(String(offset + i))), links: [],
      next_offset: offset + limit, has_more: true };
  });
  const state = renderHook(({ limit }) => useMemorySearch(source.api, true, limit), { initialProps: { limit: 450 } });
  await waitFor(() => expect(state.result.current.snapshot).not.toBeNull());
  await act(async () => { state.result.current.apply({ query: "calibration" }); });
  await act(async () => state.result.current.loadAll());
  expect(state.result.current.snapshot?.result.memories).toHaveLength(450);
  expect(source.request.mock.lastCall?.[1]).toEqual(expect.objectContaining({
    values: expect.objectContaining({ max_nodes: 450, offset: 420, ids: expect.any(Array) }),
  }));
  state.rerender({ limit: 12 });
  await waitFor(() => expect(state.result.current.snapshot?.result.memories).toHaveLength(12));
  expect(state.result.current.snapshot?.query.query).toBe("calibration");
  expect(state.result.current.snapshot?.result.has_more).toBe(false);
  expect(source.request.mock.lastCall?.[1]).toEqual(expect.objectContaining({
    values: expect.objectContaining({ max_nodes: 12, query: "calibration", offset: 0, limit: 12 }),
  }));
});

it("reports a non-advancing cursor instead of endlessly requesting the same page", async () => {
  const source = fixture(values => page(values.offset ? "duplicate" : "one", 30, true));
  const { result } = renderHook(() => useMemorySearch(source.api));
  await waitFor(() => expect(result.current.snapshot).not.toBeNull());
  await act(async () => result.current.loadAll());
  expect(result.current.error).toBe("Could not continue loading memories. Please search again.");
  expect(result.current.snapshot?.result.memories).toHaveLength(1);
  expect(source.request).toHaveBeenCalledTimes(2);
});
