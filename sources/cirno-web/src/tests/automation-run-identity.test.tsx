import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AutomationRunDialog } from "@/features/automations/runs/AutomationRunDialog";
import { CalendarPanel } from "@/features/automations/calendar/CalendarPanel";
import { fetchAutomationRunResult } from "@/lib/api";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import i18n from "@/i18n";

vi.mock("@/lib/api", () => ({ fetchAutomationRunResult: vi.fn() }));
const fetchResult = vi.mocked(fetchAutomationRunResult);
const job: SessionAutomationJob = { id: "review", name: "Review", kind: "local_trigger", enabled: true,
  schedule: { kind: "local" }, payload: { message: "Review reports" }, state: {} };
const run = { run_at_ms: 1000, status: "ok", run_id: "first" };
const props = { token: "owner", job, run, locale: "en", open: true, onOpenChange: vi.fn() };
beforeEach(async () => { fetchResult.mockReset(); await i18n.changeLanguage("en"); });
afterEach(cleanup);

it("recognizes a local trigger from its payload when an older host omits the job kind", async () => {
  fetchResult.mockResolvedValue({ response: null });
  render(<AutomationRunDialog {...props} job={{ ...job, kind: undefined, payload: { ...job.payload, kind: "local_trigger" } }} />);
  await screen.findByText("This record doesn’t include the response text.");
  expect(fetchResult.mock.calls[0][3]).toBe("local_trigger");
});

it("fetches the selected run ID and retires another run with the same timestamp", async () => {
  let finish!: (value: { response: string }) => void;
  fetchResult.mockResolvedValueOnce({ response: "First selected result" });
  fetchResult.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const { rerender } = render(<AutomationRunDialog {...props} />);
  await screen.findByText("First selected result");
  const oldSignal = fetchResult.mock.calls[0][4]!;
  rerender(<AutomationRunDialog {...props} run={{ ...run, run_id: "second" }} />);
  expect(oldSignal.aborted).toBe(true);
  expect(screen.queryByText("First selected result")).not.toBeInTheDocument();
  expect(fetchResult).toHaveBeenLastCalledWith("owner", "review", 1000, "local_trigger", expect.any(AbortSignal), "second");
  await act(async () => finish({ response: "Second selected result" }));
  expect(await screen.findByText("Second selected result")).toBeVisible();
});

it("reloads a run whose retry outcome changes without changing its identity", async () => {
  fetchResult.mockResolvedValueOnce({ response: null }).mockResolvedValueOnce({ response: "Final result" });
  const { rerender } = render(<AutomationRunDialog {...props} run={{ ...run, status: "error" }} />);
  await screen.findByText("This record doesn’t include the response text.");
  rerender(<AutomationRunDialog {...props} />);
  expect(await screen.findByText("Final result")).toBeVisible();
  expect(fetchResult).toHaveBeenCalledTimes(2);
});

it("refreshes the inspected calendar run when polling publishes its final outcome", async () => {
  fetchResult.mockResolvedValueOnce({ response: null }).mockResolvedValueOnce({ response: "Completed after retry" });
  const timestamp = new Date(2030, 0, 10, 10).getTime();
  const failed = { run_at_ms: timestamp, run_id: "delivery", status: "error", error: "Temporary delivery failure" };
  const base = { token: "owner", month: new Date(2030, 0, 1), loading: false, hasJobs: true, onInspect: vi.fn() };
  const { rerender } = render(<CalendarPanel {...base} jobs={[{ ...job, state: { run_history: [failed] } }]} />);
  await userEvent.click(screen.getByRole("button", { name: /^Review,.*Failed/ }));
  await screen.findByRole("alert");
  await waitFor(() => expect(fetchResult).toHaveBeenCalledOnce());
  rerender(<CalendarPanel {...base} jobs={[{ ...job, state: { run_history: [{ ...failed, status: "ok", error: null }] } }]} />);
  expect(await screen.findByText("Completed after retry")).toBeVisible();
  expect(screen.queryByText("Temporary delivery failure")).not.toBeInTheDocument();
});
