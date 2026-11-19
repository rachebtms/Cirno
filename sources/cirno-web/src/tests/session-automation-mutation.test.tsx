import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useSessionAutomationJobs } from "@/features/automations/model/useSessionAutomationJobs";
import { SessionAutomations } from "@/features/automations/session/SessionAutomations";
import { fetchSessionAutomations, runAutomationAction } from "@/lib/api";
import type { SessionAutomationJob } from "@/lib/contracts/automations";

vi.mock("@/lib/api", () => ({ fetchSessionAutomations: vi.fn(), runAutomationAction: vi.fn(), updateAutomation: vi.fn() }));
vi.mock("@/hooks/usePageVisibility", () => ({ usePageVisibility: () => true }));
const read = vi.mocked(fetchSessionAutomations);
const job: SessionAutomationJob = {
  id: "research", name: "Research", enabled: true,
  schedule: { kind: "every", every_ms: 60000 }, payload: { message: "Review results" }, state: {},
  origin: { channel: "websocket", session_key: "websocket:research" },
};
const foreign = { ...job, id: "foreign", origin: { channel: "websocket", session_key: "websocket:other" } };
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
beforeEach(() => { read.mockReset(); vi.mocked(runAutomationAction).mockReset(); });
afterEach(cleanup);

it.each([false, true])("publishes a scoped mutation receipt and ignores the older read (error=%s)", async fails => {
  const pending = deferred<{ jobs: SessionAutomationJob[] }>();
  read.mockReturnValue(pending.promise);
  const { result } = renderHook(() => useSessionAutomationJobs(true, "owner", "websocket:research"));
  const updated = { ...job, enabled: false };
  await act(async () => {
    await result.current.mutate(async () => [updated, foreign]);
  });
  expect(result.current.jobs).toEqual([updated]);
  await act(async () => {
    if (fails) pending.reject(new Error("Stale poll failed"));
    else pending.resolve({ jobs: [job] });
  });
  expect(result.current.jobs).toEqual([updated]);
  expect(result.current.loadError).toBeNull();
  expect(result.current.loading).toBe(false);
});

it("removes a deleted task from the list without including another session's tasks", async () => {
  read.mockResolvedValue({ jobs: [job] });
  const { result } = renderHook(() => useSessionAutomationJobs(true, "owner", "websocket:research"));
  await waitFor(() => expect(result.current.jobs).toEqual([job]));
  await act(async () => { await result.current.mutate(async () => [foreign]); });
  expect(result.current.jobs).toEqual([]);
});

it("uses the explicit bound conversation rather than its delivery address when filtering receipts", async () => {
  read.mockResolvedValue({ jobs: [job] });
  const { result } = renderHook(() => useSessionAutomationJobs(true, "owner", "websocket:research"));
  await waitFor(() => expect(result.current.jobs).toEqual([job]));
  const bound = { ...job, webui_session_key: "websocket:research", origin: { channel: "websocket", session_key: "websocket:delivery" } };
  const moved = { ...foreign, webui_session_key: "websocket:other", origin: job.origin };
  await act(async () => { await result.current.mutate(async () => [bound, moved]); });
  expect(result.current.jobs).toEqual([bound]);
});

it("does not publish a mutation into a replacement authorization or session", async () => {
  read.mockResolvedValue({ jobs: [job] });
  const pending = deferred<SessionAutomationJob[]>();
  const { result, rerender } = renderHook(
    ({ token, session }) => useSessionAutomationJobs(true, token, session),
    { initialProps: { token: "first", session: "websocket:research" } },
  );
  await waitFor(() => expect(result.current.jobs).toEqual([job]));
  let mutation!: Promise<SessionAutomationJob[]>;
  act(() => { mutation = result.current.mutate(() => pending.promise); });
  read.mockResolvedValue({ jobs: [foreign] });
  rerender({ token: "second", session: "websocket:other" });
  await waitFor(() => expect(result.current.jobs).toEqual([foreign]));
  await act(async () => { pending.resolve([{ ...job, enabled: false }]); await mutation; });
  expect(result.current.jobs).toEqual([foreign]);
});

it("releases mutation ownership on error so a corrected operation can succeed", async () => {
  read.mockResolvedValue({ jobs: [job] });
  const { result } = renderHook(() => useSessionAutomationJobs(true, "owner", "websocket:research"));
  await waitFor(() => expect(result.current.jobs).toEqual([job]));
  await act(async () => { await expect(result.current.mutate(async () => { throw new Error("Rejected"); })).rejects.toThrow("Rejected"); });
  expect(result.current.jobs).toEqual([job]);
  await act(async () => { await result.current.mutate(async () => []); });
  expect(result.current.jobs).toEqual([]);
});

it("closes the previous session's inspected task when its owner changes", async () => {
  read.mockResolvedValue({ jobs: [job] });
  const props = { client: { requestMutation: vi.fn() }, token: "owner", sessionKey: "websocket:research", title: "Research thread" };
  const { rerender } = render(<SessionAutomations {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "Session details" }));
  await userEvent.click(await screen.findByRole("button", { name: /^Research/ }));
  await screen.findByRole("dialog", { name: "Research" });
  rerender(<SessionAutomations {...props} sessionKey="websocket:other" title="Other thread" />);
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Session details" })).toBeEnabled();
});

it("keeps a confirmed disable in the actual dialog and list after an old read completes", async () => {
  const pending = deferred<{ jobs: SessionAutomationJob[] }>();
  read.mockResolvedValueOnce({ jobs: [job] }).mockReturnValue(pending.promise);
  vi.mocked(runAutomationAction).mockResolvedValue({ jobs: [{ ...job, enabled: false }, foreign] });
  render(<SessionAutomations client={{ requestMutation: vi.fn() }} token="owner" sessionKey="websocket:research" title="Research thread" />);
  await userEvent.click(screen.getByRole("button", { name: "Session details" }));
  await userEvent.click(await screen.findByRole("button", { name: /^Research,/ }));
  await screen.findByRole("dialog", { name: "Research" });
  await act(async () => { window.dispatchEvent(new Event("focus")); });
  await userEvent.click(await screen.findByRole("button", { name: "More actions" }));
  await userEvent.click(await screen.findByRole("menuitem", { name: "Disable" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Run now" })).toBeDisabled());
  read.mockResolvedValue({ jobs: [{ ...job, enabled: false }] });
  await act(async () => pending.resolve({ jobs: [job] }));
  expect(screen.getByRole("button", { name: "Run now" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Close" }));
  await userEvent.click(screen.getByRole("button", { name: "Session details" }));
  expect(await screen.findByRole("button", { name: /^Research, Paused/ })).toBeEnabled();
  expect(screen.queryByRole("button", { name: /^foreign,/ })).not.toBeInTheDocument();
  expect(runAutomationAction).toHaveBeenCalledOnce();
});
