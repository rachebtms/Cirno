import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useThreadUsage } from "@/components/thread/useThreadUsage";
import { recentComposerRoundUsage } from "@/components/thread/composer-usage";
import type { UIMessage } from "@/lib/contracts/messages";

const { requestMutation } = vi.hoisted(() => ({ requestMutation: vi.fn() }));
const client = { requestMutation };
vi.mock("@/providers/ClientProvider", () => ({ useClient: () => ({ client }) }));
const thinking: UIMessage = { id: "live", role: "assistant", content: "", reasoning: "Working", createdAt: 2000, isStreaming: true };
const saved = {
  context_tokens: 12000, context_window_tokens: 128000, estimated: true,
  recent_requests: [{ id: "request-1", timestamp: 1500, usage: {
    prompt_tokens: 10000, completion_tokens: 200, cached_tokens: 9000,
    generation_ms: 4000, measured_completion_tokens: 200, ttft_ms: 500, timed_requests: 1,
  } }],
};
beforeEach(() => requestMutation.mockReset().mockResolvedValue(saved));

it("restores completed request details while the refreshed turn is still thinking", async () => {
  const state = renderHook(({ messages }) => useThreadUsage(messages, "websocket:worker", true), {
    initialProps: { messages: [thinking] },
  });
  await waitFor(() => expect(state.result.current.composerRoundUsage).toHaveLength(1));
  expect(state.result.current.composerRoundUsage[0]).toMatchObject({
    inputTokens: 10000, outputTokens: 200, cachedTokens: 9000, ttftMs: 500, generationMs: 4000,
  });
  for (let index = 0; index < 5; index++) {
    state.rerender({ messages: [thinking, { ...thinking, id: `live-${index}`, reasoning: "More thought".repeat(index + 1) }] });
  }
  expect(requestMutation).toHaveBeenCalledTimes(1);
  expect(state.result.current.composerContextUsage?.estimated).toBe(true);
});

it("uses newer server request details even when an earlier completed turn is loaded", async () => {
  const older: UIMessage = { id: "old", role: "assistant", content: "Done", createdAt: 1000,
    usage: { context_tokens: 4000 }, contextWindowTokens: 128000,
    roundUsages: [{ prompt_tokens: 4000, completion_tokens: 10 }] };
  const state = renderHook(() => useThreadUsage([older, thinking], "websocket:worker", true));
  await waitFor(() => expect(state.result.current.composerRoundUsage.at(-1)?.id).toBe("request-1"));
});

it("keeps actual details unavailable until the first request returns and isolates late responses", async () => {
  let finish!: (value: typeof saved) => void;
  requestMutation.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockResolvedValueOnce({ ...saved, recent_requests: [] });
  const state = renderHook(({ key }) => useThreadUsage([thinking], key, true), {
    initialProps: { key: "websocket:old" },
  });
  state.rerender({ key: "websocket:new" });
  await waitFor(() => expect(requestMutation).toHaveBeenCalledTimes(2));
  await act(async () => finish(saved));
  expect(state.result.current.composerRoundUsage).toEqual([]);
});

it("does not let a later empty assistant segment hide the same turn's completed usage", () => {
  const messages: UIMessage[] = [
    { id: "stats", role: "assistant", content: "Update", turnId: "same", createdAt: 1,
      roundUsages: [{ prompt_tokens: 1000, completion_tokens: 20 }] },
    { id: "later", role: "assistant", content: "Another update", turnId: "same", createdAt: 2 },
  ];
  expect(recentComposerRoundUsage(messages)).toHaveLength(1);
});
