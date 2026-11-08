import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useSessionAutomationJobs } from "@/features/automations/model/useSessionAutomationJobs";
import { fetchSessionAutomations } from "@/lib/api";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
vi.mock("@/lib/api", () => ({ fetchSessionAutomations: vi.fn() }));
vi.mock("@/hooks/usePageVisibility", () => ({ usePageVisibility: () => true }));
const read = vi.mocked(fetchSessionAutomations);
const job: SessionAutomationJob = {
  id: "research",
  name: "Research",
  enabled: true,
  schedule: { kind: "every", every_ms: 60000 },
  payload: { message: "Review results" },
  state: {},
};
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);
it("retains loaded tasks and exposes a failed refresh instead of silently suppressing it", async () => {
  read
    .mockResolvedValueOnce({ jobs: [job] })
    .mockRejectedValueOnce(new Error("Scheduler read timed out"));
  const { result, unmount } = renderHook(() =>
    useSessionAutomationJobs(true, "owner-token", "websocket:research"),
  );
  await waitFor(() => expect(result.current.jobs).toEqual([job]));
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await waitFor(() =>
    expect(result.current.loadError).toBe("Scheduler read timed out"),
  );
  expect(result.current.jobs).toEqual([job]);
  expect(result.current.loading).toBe(false);
  read.mockResolvedValueOnce({ jobs: [job] });
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await waitFor(() => expect(result.current.loadError).toBeNull());
  unmount();
});
it("does not overlap requests and aborts the read when its surface closes", async () => {
  read.mockReturnValue(new Promise(() => {}));
  const { rerender } = renderHook(
    ({ open }) =>
      useSessionAutomationJobs(open, "owner-token", "websocket:research"),
    { initialProps: { open: true } },
  );
  await act(async () => {
    for (let i = 0; i < 5; i++) window.dispatchEvent(new Event("focus"));
  });
  expect(read).toHaveBeenCalledTimes(1);
  const signal = read.mock.calls[0][3]!;
  expect(signal.aborted).toBe(false);
  rerender({ open: false });
  expect(signal.aborted).toBe(true);
});
it("drops a late response from the previous session", async () => {
  let first!: (result: { jobs: SessionAutomationJob[] }) => void;
  let next!: (result: { jobs: SessionAutomationJob[] }) => void;
  read.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        first = resolve;
      }),
  );
  read.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        next = resolve;
      }),
  );
  const { result, rerender } = renderHook(
    ({ session }) => useSessionAutomationJobs(true, "owner-token", session),
    { initialProps: { session: "websocket:first" } },
  );
  const signal = read.mock.calls[0][3]!;
  rerender({ session: "websocket:next" });
  expect(signal.aborted).toBe(true);
  await act(async () => first({ jobs: [job] }));
  expect(result.current.jobs).toEqual([]);
  expect(result.current.loading).toBe(true);
  await act(async () => next({ jobs: [] }));
  expect(result.current.loading).toBe(false);
});
it("clears the previous authorization's snapshot and refetches when credentials change", async () => {
  read.mockResolvedValueOnce({ jobs: [job] });
  const { result, rerender } = renderHook(
    ({ token }) => useSessionAutomationJobs(true, token, "websocket:research"),
    { initialProps: { token: "first-token" } },
  );
  await waitFor(() => expect(result.current.jobs).toEqual([job]));
  read.mockReturnValueOnce(new Promise(() => {}));
  rerender({ token: "next-token" });
  expect(result.current.jobs).toEqual([]);
  expect(result.current.loading).toBe(true);
  expect(read).toHaveBeenLastCalledWith(
    "next-token",
    "websocket:research",
    "",
    expect.any(AbortSignal),
  );
});
