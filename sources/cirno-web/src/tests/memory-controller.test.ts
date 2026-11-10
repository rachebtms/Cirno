import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { createMemoryService } from "@/features/memory/model/service";
import { useMemorySearch } from "@/features/memory/model/useMemorySearch";
import { useMemoryInspector } from "@/features/memory/model/useMemoryInspector";
import { useMemoryMaintenance } from "@/features/memory/model/useMemoryMaintenance";
import { EMPTY_MEMORY_QUERY } from "@/features/memory/model/service";
import type { MemoryRecord } from "@/lib/contracts/memory";
const row: MemoryRecord = {
  id: "fact",
  title: "Calibration",
  source: "memory:source",
  scope: "session",
  layer: "knowledge",
  kind: "fact",
  revision: 2,
  status: "active",
  tags: [],
  updated_at: "2026-10-31T00:00:00Z",
};
function service(
  handler: (action: string, values: Record<string, unknown>) => unknown,
) {
  const requestMutation = vi.fn(
    async <T>(
      _method: string,
      { action, values = {} }: Record<string, unknown> = {},
    ) =>
      (await handler(String(action), values as Record<string, unknown>)) as T,
  );
  return {
    api: createMemoryService({
      requestMutation: async <T>(
        action: string,
        payload?: Record<string, unknown>,
      ) => (await requestMutation(action, payload)) as T,
    }),
    request: requestMutation,
  };
}
afterEach(cleanup);
it("waits for the server's whole-search embedding budget without extending lexical reads", async () => {
  const requestMutation = vi.fn().mockResolvedValue({ memories: [], has_more: false, next_offset: 0 });
  const api = createMemoryService({ requestMutation });
  await api.graph({ ...EMPTY_MEMORY_QUERY, query: "calibration", mode: "semantic" });
  expect(requestMutation).toHaveBeenLastCalledWith("instance.action", expect.any(Object), 150_000);
  await api.list({ ...EMPTY_MEMORY_QUERY, query: "calibration" });
  expect(requestMutation.mock.lastCall).toHaveLength(2);
});
it("paginates the submitted search rather than a newly typed draft", async () => {
  const fixture = service((action, values) =>
    action === "memory.list"
      ? {
          memories: [{ ...row, id: values.offset ? "second" : "first" }],
          has_more: !values.offset,
          next_offset: 10,
        }
      : {},
  );
  const { result } = renderHook(() => useMemorySearch(fixture.api));
  await waitFor(() => expect(result.current.snapshot).not.toBeNull());
  act(() => result.current.change({ query: "old query" }));
  await act(async () => {
    await result.current.submit();
  });
  act(() =>
    result.current.change({ query: "new unsent query", tags: "new-tag" }),
  );
  await act(async () => {
    await result.current.more();
  });
  expect(fixture.request).toHaveBeenLastCalledWith(
    "instance.action",
    expect.objectContaining({
      action: "memory.list",
      values: expect.objectContaining({
        query: "old query",
        tags: [],
        offset: 10,
      }),
    }),
  );
  expect(result.current.snapshot!.result.memories.map((row) => row.id)).toEqual(
    ["first", "second"],
  );
});
it("ignores a late search response and keeps the selected retrieval mode", async () => {
  let first!: (value: unknown) => void;
  const fixture = service((_action, values) =>
    values.query === "slow"
      ? new Promise((resolve) => {
          first = resolve;
        })
      : {
          memories: [{ ...row, title: String(values.query || "initial") }],
          has_more: false,
          next_offset: 0,
        },
  );
  const { result } = renderHook(() => useMemorySearch(fixture.api));
  await waitFor(() => expect(result.current.snapshot).not.toBeNull());
  act(() => result.current.apply({ query: "slow" }));
  await act(async () => {
    result.current.apply({ query: "latest", mode: "hybrid" });
  });
  await act(async () =>
    first({ memories: [row], has_more: false, next_offset: 0 }),
  );
  expect(result.current.snapshot!.result.memories[0].title).toBe("latest");
  expect(result.current.snapshot!.query.mode).toBe("hybrid");
});
it("continues the resolved source ID and revision through a split line", async () => {
  const fixture = service((action, values) => {
    if (action === "memory.read")
      return {
        ...row,
        revision: values.revision,
        content: "Exact value",
        links: [],
      };
    if (action === "memory.source")
      return {
        memory_id: "actual-evidence",
        revision: 3,
        source: "source.jsonl",
        lines: [{ line: 4, text: "partial", next_char_offset: 16000 }],
        next_line: 5,
      };
    return {};
  });
  const { result } = renderHook(() => useMemoryInspector(fixture.api, row));
  await waitFor(() => expect(result.current.record.value).not.toBeNull());
  await act(async () => {
    await result.current.openRevision(1);
  });
  await act(async () => {
    result.current.selectView("source");
  });
  expect(fixture.request).toHaveBeenLastCalledWith("instance.action", {
    action: "memory.source",
    values: { id: "fact", revision: 1 },
  });
  await act(async () => {
    result.current.more();
  });
  expect(fixture.request).toHaveBeenLastCalledWith("instance.action", {
    action: "memory.source",
    values: {
      id: "actual-evidence",
      revision: 3,
      start_line: 4,
      char_offset: 16000,
    },
  });
});
it("pins a requested version before its record read finishes", async () => {
  let finish!: (value: unknown) => void;
  const fixture = service((action, values) =>
    action === "memory.read" && values.revision === 1
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : action === "memory.read"
        ? { ...row, content: "Current", links: [] }
        : { memory_id: "fact", revision: 1, source: "old" },
  );
  const { result } = renderHook(() => useMemoryInspector(fixture.api, row));
  await waitFor(() => expect(result.current.record.value).not.toBeNull());
  act(() => {
    void result.current.openRevision(1);
  });
  await act(async () => {
    result.current.selectView("source");
  });
  expect(fixture.request).toHaveBeenLastCalledWith("instance.action", {
    action: "memory.source",
    values: { id: "fact", revision: 1 },
  });
  await act(async () =>
    finish({ ...row, revision: 1, content: "Old", links: [] }),
  );
});
it("finishes the current rebuild batch after Stop without issuing another request", async () => {
  let finish!: (value: unknown) => void;
  const fixture = service(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const changed = vi.fn().mockResolvedValue(undefined);
  const { result } = renderHook(() =>
    useMemoryMaintenance(fixture.api, changed),
  );
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.run("reindex");
  });
  act(() => result.current.stop());
  await act(async () => {
    finish({ scanned: 100, has_more: true });
    await pending;
  });
  expect(fixture.request).toHaveBeenCalledTimes(1);
  expect(result.current.phase).toBe("stopped");
  expect(result.current.scanned).toBe(100);
  expect(changed).toHaveBeenCalledTimes(1);
});
it("does not continue rebuilding after its owner unmounts", async () => {
  let finish!: (value: unknown) => void;
  const fixture = service(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const changed = vi.fn();
  const { result, unmount } = renderHook(() =>
    useMemoryMaintenance(fixture.api, changed),
  );
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.run("reindex");
  });
  unmount();
  await act(async () => {
    finish({ scanned: 100, has_more: true });
    await pending;
  });
  expect(fixture.request).toHaveBeenCalledTimes(1);
  expect(changed).not.toHaveBeenCalled();
});
