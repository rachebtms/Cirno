import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fetchAutomaticModelAPI } from "@/lib/api";
import { useAutomaticModelAPI } from "@/features/settings/models/useAutomaticModelAPI";

vi.mock("@/lib/api", () => ({ fetchAutomaticModelAPI: vi.fn() }));
const fetchAPI = vi.mocked(fetchAutomaticModelAPI);
const options = {
  token: "test",
  provider: "openai",
  model: "first",
  reasoningEffort: "",
  providers: [],
  supported: true,
  editorOpen: true,
};
beforeEach(() => {
  vi.useFakeTimers();
  fetchAPI.mockReset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("debounces model changes and rejects a late reply for the previous model", async () => {
  let finish!: (
    result: Awaited<ReturnType<typeof fetchAutomaticModelAPI>>,
  ) => void;
  fetchAPI.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  fetchAPI.mockResolvedValueOnce({ provider: "openai", api: "responses" });
  const { result, rerender } = renderHook(useAutomaticModelAPI, {
    initialProps: options,
  });
  await act(() => vi.advanceTimersByTimeAsync(150));
  rerender({ ...options, model: "discarded" });
  rerender({ ...options, model: "current" });
  await act(() => vi.advanceTimersByTimeAsync(150));
  expect(fetchAPI).toHaveBeenCalledTimes(2);
  expect(fetchAPI).toHaveBeenLastCalledWith("test", "openai", "current", "");
  await act(async () => {
    finish({ provider: "openai", api: "chat_completions" });
  });
  expect(result.current.result?.api).toBe("responses");
});

it("reports an API preview failure and supports an explicit retry", async () => {
  fetchAPI.mockRejectedValueOnce(new Error("Resolution unavailable"));
  fetchAPI.mockResolvedValueOnce({ provider: "openai", api: "responses" });
  const { result } = renderHook(useAutomaticModelAPI, {
    initialProps: options,
  });
  await act(() => vi.advanceTimersByTimeAsync(150));
  expect(result.current.error).toBe("Resolution unavailable");
  expect(result.current.result).toBeNull();
  await act(() => result.current.retry());
  expect(result.current.error).toBeNull();
  expect(result.current.result?.api).toBe("responses");
});

it("does not request resolution while unsupported or closed, and cancels the pending debounce on unmount", async () => {
  const { rerender, unmount } = renderHook(useAutomaticModelAPI, {
    initialProps: { ...options, supported: false },
  });
  await act(() => vi.advanceTimersByTimeAsync(150));
  rerender({ ...options, editorOpen: false });
  await act(() => vi.advanceTimersByTimeAsync(150));
  rerender(options);
  unmount();
  await act(() => vi.advanceTimersByTimeAsync(150));
  expect(fetchAPI).not.toHaveBeenCalled();
});
