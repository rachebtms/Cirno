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
