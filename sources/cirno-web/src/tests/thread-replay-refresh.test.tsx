import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import { useCirnoStream } from "@/hooks/useCirnoStream";
import { webuiThreadCache } from "@/lib/webui-thread-cache";
import { ClientProvider } from "@/providers/ClientProvider";
import { createStreamClient } from "./stream-client";
import { canonicalThreadPayload } from "./thread-test-payload";

function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((finish) => { resolve = finish; });
  return { promise, resolve };
}

function response(content: string) {
  return new Response(JSON.stringify(canonicalThreadPayload({ schemaVersion: 1, messages: [
    { id: "prompt", role: "user", content, turnId: "turn", turnSeq: 0, createdAt: 1 },
  ] })), { status: 200 });
}

afterEach(() => { vi.unstubAllGlobals(); webuiThreadCache.clear(); });

it("retires an old Working owner when HTTP discovers a clear missed by the socket", async () => {
  const { client, receive } = createStreamClient();
  const initial = { schemaVersion: 3, projection: "events", history_generation: "a", revision: "a1",
    completed_turn_ids: [], has_pending_tool_calls: true, active_turn_id: "old",
    events: [{ event: "user_message", chat_id: "missed", turn_id: "old", turn_seq: 0, text: "Deleted", starts_turn: true }] };
  const cleared = { ...initial, history_generation: "b", revision: "b1", events: [], has_pending_tool_calls: false, active_turn_id: null };
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(initial), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(cleared), { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  const view = renderHook(() => useCirnoStream("missed", undefined, false, undefined, undefined, [], { key: "websocket:missed" }), {
    wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider>,
  });
  try {
    await waitFor(() => expect(view.result.current.messages).toHaveLength(1));
    act(() => receive({ event: "goal_status", chat_id: "missed", turn_id: "old", status: "running", started_at: 100 }));
    expect(view.result.current.isStreaming).toBe(true);
    const owner = view.result.current.historyOwner;
    act(() => view.result.current.refreshHistory());
    await waitFor(() => expect(view.result.current.messages).toEqual([]));
    expect(view.result.current.isStreaming).toBe(false);
    expect(view.result.current.historyOwner).not.toBe(owner);
    act(() => receive({ event: "message", chat_id: "missed", turn_id: "old", turn_seq: 2, text: "Late deleted answer" }));
    expect(view.result.current.messages).toEqual([]);
  } finally { view.unmount(); client.close(); }
});

it("keeps new live work while HTTP retires the previous history generation", async () => {
  const { client, receive } = createStreamClient();
  const latest = deferred();
  const initial = { schemaVersion: 3, projection: "events", history_generation: "a", revision: "a1",
    completed_turn_ids: [], has_pending_tool_calls: true, active_turn_id: "old",
    events: [{ event: "user_message", chat_id: "replaced", turn_id: "old", turn_seq: 0, text: "Deleted", starts_turn: true }] };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(initial), { status: 200 }))
    .mockReturnValueOnce(latest.promise));
  const view = renderHook(() => useCirnoStream("replaced", undefined, false, undefined, undefined, [], { key: "websocket:replaced" }), {
    wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider>,
  });
  try {
    await waitFor(() => expect(view.result.current.messages).toHaveLength(1));
    act(() => {
      receive({ event: "goal_status", chat_id: "replaced", turn_id: "old", status: "running", started_at: 100 });
      view.result.current.refreshHistory();
    });
    const input = { event: "user_message" as const, chat_id: "replaced", turn_id: "new", turn_seq: 0, text: "Replacement", starts_turn: true };
    act(() => {
      receive({ event: "goal_status", chat_id: "replaced", turn_id: "new", status: "running", started_at: 200 });
      receive(input);
      receive({ event: "delta", chat_id: "replaced", turn_id: "new", turn_seq: 1, stream_id: "new-answer", text: "Current" });
    });
    await waitFor(() => expect(view.result.current.messages.at(-1)?.content).toBe("Current"));
    await act(async () => latest.resolve(new Response(JSON.stringify({ ...initial,
      history_generation: "b", revision: "b1", active_turn_id: "new", events: [input],
    }), { status: 200 })));
    expect(view.result.current.messages.map(row => row.content)).toEqual(["Replacement", "Current"]);
    expect(view.result.current.isStreaming).toBe(true);
    expect(client.getRunStartedAt("replaced")).toBe(200);
    act(() => receive({ event: "stream_end", chat_id: "replaced", turn_id: "new", turn_seq: 2, stream_id: "new-answer", text: "Current continues" }));
    expect(view.result.current.messages.at(-1)?.content).toBe("Current continues");
    act(() => receive({ event: "turn_end", chat_id: "replaced", turn_id: "new", turn_seq: 3 }));
    expect(view.result.current.isStreaming).toBe(false);
  } finally { view.unmount(); client.close(); }
});

it.each(["visibility", "pageshow"] as const)("keeps one reply across a %s foreground refresh and repeated delivery", async (resume) => {
  const { client, receive } = createStreamClient();
  const latest = deferred();
  const fetch = vi.fn().mockResolvedValueOnce(response("Question")).mockReturnValueOnce(latest.promise);
  vi.stubGlobal("fetch", fetch);
  let visible: DocumentVisibilityState = "visible";
  const visibility = vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visible);
  const view = renderHook(() => useCirnoStream("foreground", undefined, false, undefined, undefined, [], {
    key: "websocket:foreground",
  }), { wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider> });
  const reply = { event: "message" as const, chat_id: "foreground", turn_id: "turn", turn_seq: 1, text: "Inspection complete." };
  try {
    await waitFor(() => expect(view.result.current.history.loading).toBe(false));
    act(() => receive(reply));
    act(() => {
      visible = "hidden";
      document.dispatchEvent(new Event("visibilitychange"));
      visible = "visible";
      if (resume === "visibility") document.dispatchEvent(new Event("visibilitychange"));
      else {
        const event = new Event("pageshow");
        Object.defineProperty(event, "persisted", { value: true });
        window.dispatchEvent(event);
      }
    });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    act(() => receive(reply));
    expect(view.result.current.messages.filter(row => row.role === "assistant").map(row => row.content)).toEqual([reply.text]);
    await act(async () => { latest.resolve(new Response(JSON.stringify(canonicalThreadPayload({ schemaVersion: 1,
      messages: [
        { id: "prompt", role: "user", content: "Question", turnId: "turn", turnSeq: 0, createdAt: 1 },
        { id: "reply", role: "assistant", content: reply.text, turnId: "turn", turnSeq: 1, createdAt: 2 },
      ],
    })), { status: 200 })); });
    act(() => receive(reply));
    expect(view.result.current.messages.filter(row => row.role === "assistant")).toHaveLength(1);
    act(() => receive({ ...reply, turn_seq: 2 }));
    expect(view.result.current.messages.filter(row => row.role === "assistant").map(row => row.content)).toEqual([reply.text, reply.text]);
  } finally {
    view.unmount();
    visibility.mockRestore();
  }
});

it("does not concatenate a repeated delta inside one background paint batch", async () => {
  const { client, receive } = createStreamClient();
  const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
  const view = renderHook(() => useCirnoStream("buffered"), {
    wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider>,
  });
  try {
    act(() => {
      const delta = { event: "delta" as const, chat_id: "buffered", turn_id: "turn", turn_seq: 1, text: "Reply" };
      receive(delta);
      receive(delta);
      receive({ event: "stream_end", chat_id: "buffered", turn_id: "turn", turn_seq: 2 });
    });
    expect(view.result.current.messages.map(row => row.content)).toEqual(["Reply"]);
  } finally {
    view.unmount();
    visibility.mockRestore();
  }
});

it("lets slow history finish under repeated turn notifications and coalesces the next refresh", async () => {
  const { client, receive } = createStreamClient();
  const first = deferred(), next = deferred();
  const fetch = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(next.promise);
  vi.stubGlobal("fetch", fetch);
  const history = { key: "websocket:research" };
  const { result } = renderHook(() => useCirnoStream("research", undefined, false, undefined, undefined, [], history), {
    wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider>,
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () => {
    for (let index = 0; index < 20; index++) {
      receive({ event: "session_updated", chat_id: "research", scope: "thread" });
      result.current.refreshHistory();
    }
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(false);
  await act(async () => { first.resolve(response("Captured input")); });
  expect(result.current.messages.some((message) => message.content === "Captured input")).toBe(true);
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  await act(async () => { next.resolve(response("Captured input")); });
  expect(result.current.history.loading).toBe(false);
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("cancels immediately for a context reset and never reinstalls its earlier input", async () => {
  const { client } = createStreamClient();
  const first = deferred(), replacement = deferred();
  const fetch = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(replacement.promise);
  vi.stubGlobal("fetch", fetch);
  const history = { key: "websocket:reset" };
  const { result } = renderHook(() => useCirnoStream("reset", undefined, false, undefined, undefined, [], history), {
    wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider>,
  });
  act(() => { result.current.refreshHistory(); result.current.resetHistory(); });
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  await act(async () => {
    first.resolve(response("Deleted input"));
    replacement.resolve(response("Replacement input"));
  });
  expect(result.current.messages.map((message) => message.content)).toEqual(["Replacement input"]);
});

it("does not restore a completed turn's pending state from a late active snapshot", async () => {
  const { client, receive } = createStreamClient();
  const late = deferred(), fresh = deferred();
  const active = canonicalThreadPayload({ schemaVersion: 1, revision: "before-completion",
    has_pending_tool_calls: true, active_turn_id: "completed-turn", completed_turn_ids: [],
    messages: [{ id: "prompt", role: "user", content: "Research", turnId: "completed-turn", turnSeq: 0, createdAt: 1 }],
  });
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(active), { status: 200 }))
    .mockReturnValueOnce(late.promise).mockReturnValueOnce(fresh.promise);
  vi.stubGlobal("fetch", fetch);
  const history = { key: "websocket:finished" };
  const { result } = renderHook(() => useCirnoStream("finished", undefined, false, undefined, undefined, [], history), {
    wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider>,
  });
  await waitFor(() => expect(result.current.history.hasPendingToolCalls).toBe(true));
  act(() => result.current.refreshHistory());
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  await act(async () => {
    receive({ event: "goal_status", chat_id: "finished", turn_id: "completed-turn", status: "running", started_at: 1 });
    receive({ event: "message", chat_id: "finished", turn_id: "completed-turn", turn_seq: 1, text: "Verified conclusion" });
    receive({ event: "turn_end", chat_id: "finished", turn_id: "completed-turn", turn_seq: 2 });
    receive({ event: "session_updated", chat_id: "finished", scope: "thread" });
    result.current.refreshHistory();
    late.resolve(new Response(JSON.stringify({ ...active, revision: "stale-after-completion" }), { status: 200 }));
  });
  expect(result.current.history.hasPendingToolCalls).toBe(false);
  expect(result.current.history.activeTurnId).toBeNull();
  expect(result.current.isStreaming).toBe(false);
  expect(result.current.messages.at(-1)?.content).toBe("Verified conclusion");
  expect(webuiThreadCache.get(history.key)?.revision).toBe("before-completion");
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
  await act(async () => { fresh.resolve(new Response(JSON.stringify(canonicalThreadPayload({ schemaVersion: 1,
    completed_turn_ids: ["completed-turn"], messages: [
      { id: "prompt", role: "user", content: "Research", turnId: "completed-turn", turnSeq: 0, createdAt: 1 },
      { id: "answer", role: "assistant", content: "Verified conclusion", turnId: "completed-turn", turnSeq: 1, createdAt: 2 },
    ],
  })), { status: 200 })); });
  expect(result.current.messages.at(-1)?.content).toBe("Verified conclusion");
});
