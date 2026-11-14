import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useDeferredActivityDetails } from "@/components/thread/activity/useDeferredActivityDetails";
import type { UIMessage } from "@/lib/contracts/messages";

const messages = (...refs: string[]): UIMessage[] => refs.map(ref => ({
  id: ref, role: "tool", kind: "trace", content: "exec(…)", createdAt: 1,
  traceDetail: { ref, traceCount: 1, bytes: 40000 },
}));

describe("Deferred activity detail loading", () => {
  it("retains a failed detail when another detail finishes, without automatically retrying it", async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error("first detail unavailable")).mockResolvedValue(undefined);
    const { result, rerender } = renderHook(({ refs }) => useDeferredActivityDetails({
      messages: messages(...refs), scope: "chat-a", expanded: true, load,
    }), { initialProps: { refs: ["a", "b"] } });
    await waitFor(() => expect(result.current.failed).toBe(true));
    rerender({ refs: ["a"] });
    await act(async () => {});
    expect(load).toHaveBeenCalledTimes(1);
    expect(result.current.failed).toBe(true);
    await act(() => result.current.retry());
    expect(load).toHaveBeenLastCalledWith(["a"]);
    expect(result.current.failed).toBe(false);
  });

  it("loads new details without retrying previous failures or clearing their warning", async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
    const { result, rerender } = renderHook(({ refs }) => useDeferredActivityDetails({
      messages: messages(...refs), scope: "chat-a", expanded: true, load,
    }), { initialProps: { refs: ["a"] } });
    await waitFor(() => expect(result.current.failed).toBe(true));
    rerender({ refs: ["a", "c"] });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(load).toHaveBeenLastCalledWith(["c"]);
    expect(result.current.failed).toBe(true);
    rerender({ refs: ["c"] });
    expect(result.current.failed).toBe(false);
  });

  it("does not reload the remaining subset while a successful batch is still pending", async () => {
    let finish!: () => void;
    const load = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
    const { rerender } = renderHook(({ refs }) => useDeferredActivityDetails({
      messages: messages(...refs), scope: "chat-a", expanded: true, load,
    }), { initialProps: { refs: ["a", "b"] } });
    expect(load).toHaveBeenCalledOnce();
    rerender({ refs: ["b"] });
    expect(load).toHaveBeenCalledOnce();
    await act(async () => { finish(); });
    expect(load).toHaveBeenCalledOnce();
  });

  it("ignores a stale failure after navigating away and back to the same conversation", async () => {
    const rejectors: Array<(reason: Error) => void> = [];
    const load = vi.fn(() => new Promise<void>((_resolve, reject) => rejectors.push(reject)));
    const { result, rerender } = renderHook(({ scope }) => useDeferredActivityDetails({
      messages: messages("a"), scope, expanded: true, load,
    }), { initialProps: { scope: "chat-a" } });
    rerender({ scope: "chat-b" });
    rerender({ scope: "chat-a" });
    expect(load).toHaveBeenCalledTimes(3);
    await act(async () => { rejectors[0](new Error("old request failed")); });
    expect(result.current.failed).toBe(false);
    await act(async () => { rejectors[2](new Error("current request failed")); });
    expect(result.current.failed).toBe(true);
    await act(async () => { rejectors[1](new Error("other conversation failed")); });
  });
});
