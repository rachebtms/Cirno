import { deferred } from "./helpers/deferred";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createSystemSettingsActions } from "@/features/settings/system/createSystemSettingsActions";
import { useSystemSettingsEffects } from "@/features/settings/system/useSystemSettingsEffects";
import { useSystemSettingsState } from "@/features/settings/system/useSystemSettingsState";
import { CirnoClient } from "@/lib/cirno-client";
import type { AutomationsPayload, SessionAutomationJob } from "@/lib/contracts/automations";
import i18n from "@/i18n";

const api = vi.hoisted(() => ({ read: vi.fn(), action: vi.fn(), edit: vi.fn(), chat: vi.fn() }));
vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof import("@/lib/api")>(),
  fetchAutomations: api.read, runAutomationAction: api.action,
  updateAutomation: api.edit, changeAutomationChat: api.chat,
}));
const token = () => "fixture-token";
const job: SessionAutomationJob = {
  id: "daily", name: "Report", enabled: true,
  schedule: { kind: "every", every_ms: 60000 }, state: {}, payload: { message: "Summarize" },
};
const saved: AutomationsPayload = { jobs: [{ ...job, enabled: false }] };
function harness(poll: boolean) {
  const client = new CirnoClient({ url: "ws://example.test" });
  return renderHook(({ visible }) => {
    const state = useSystemSettingsState();
    const { refreshAutomations } = useSystemSettingsEffects({
      state, activeSection: poll ? "automations" : "appearance", getToken: token, pageVisible: visible,
    });
    const actions = createSystemSettingsActions({
      state, featureCatalog: [], client, token: token(), getToken: token, t: i18n.t,
      applyPayload: vi.fn(), setPendingRestartSections: vi.fn(), refreshAutomations,
    });
    return { state, actions, refreshAutomations };
  }, { initialProps: { visible: true } });
}
beforeEach(() => { api.read.mockReset(); api.action.mockReset(); api.edit.mockReset(); api.chat.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

it.each([false, true])("does not overwrite an acknowledged change with an older poll (error=%s)", async fails => {
  const read = deferred<AutomationsPayload>();
  api.read.mockReturnValue(read.promise);
  api.action.mockResolvedValue(saved);
  const { result } = harness(true);
  await act(async () => { await result.current.actions.handleAutomationAction("disable", job); });
  await act(async () => {
    if (fails) read.reject(new Error("Old poll failed"));
    else read.resolve({ jobs: [job] });
  });
  expect(result.current.state.automations).toEqual(saved);
  expect(result.current.state.automationsError).toBeNull();
});

it("does not overwrite a saved edit with an older explicit refresh", async () => {
  const read = deferred<AutomationsPayload>();
  api.read.mockReturnValue(read.promise);
  api.edit.mockResolvedValue(saved);
  const { result } = harness(false);
  let refresh!: Promise<void>;
  act(() => { refresh = result.current.refreshAutomations(); });
  await act(async () => { await result.current.actions.handleAutomationEdit(job, { message: "New instructions" }); });
  await act(async () => { read.resolve({ jobs: [job] }); await refresh; });
  expect(result.current.state.automations).toEqual(saved);
});

it("admits one automation mutation through same-frame duplicate actions and edits", async () => {
  const pending = deferred<AutomationsPayload>();
  api.action.mockReturnValue(pending.promise);
  api.edit.mockResolvedValue(saved);
  const { result } = harness(false);
  let operations!: Promise<void>[];
  act(() => { operations = [
    result.current.actions.handleAutomationAction("disable", job),
    result.current.actions.handleAutomationAction("disable", job),
    result.current.actions.handleAutomationEdit(job, { message: "New instructions" }),
  ]; });
  const calls = api.action.mock.calls.length + api.edit.mock.calls.length;
  await act(async () => { pending.resolve(saved); await Promise.all(operations); });
  expect(calls).toBe(1);
  expect(result.current.state.automationAction).toBeNull();
});

it("fences poll results around a change-chat acknowledgement too", async () => {
  const read = deferred<AutomationsPayload>();
  api.read.mockReturnValue(read.promise);
  api.chat.mockResolvedValue(saved);
  const { result } = harness(true);
  await act(async () => { await result.current.actions.handleAutomationChat(job, { target_id: "target", revision: "rev", message: "Summarize" }); });
  await act(async () => read.resolve({ jobs: [job] }));
  expect(result.current.state.automations).toEqual(saved);
});

it("keeps the newest refresh loading until its own result arrives", async () => {
  const first = deferred<AutomationsPayload>(), second = deferred<AutomationsPayload>();
  api.read.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const { result } = harness(true);
  let refresh!: Promise<void>;
  act(() => { refresh = result.current.refreshAutomations(true); });
  await act(async () => first.resolve({ jobs: [job] }));
  expect(result.current.state.automationsLoading).toBe(true);
  expect(result.current.state.automations).toBeNull();
  await act(async () => { second.resolve(saved); await refresh; });
  expect(result.current.state.automationsLoading).toBe(false);
  expect(result.current.state.automations).toEqual(saved);
});

it("releases a failed action before accepting the next edit and refresh", async () => {
  api.action.mockRejectedValue(new Error("Cannot enable expired task"));
  api.edit.mockResolvedValue(saved);
  api.read.mockResolvedValue(saved);
  const { result } = harness(false);
  await act(async () => { await result.current.actions.handleAutomationAction("enable", job); });
  expect(result.current.state.automationAction).toBeNull();
  expect(result.current.state.automationsError).toBe("Cannot enable expired task");
  await act(async () => { await result.current.actions.handleAutomationEdit(job, { message: "Updated" }); });
  await act(async () => { await result.current.refreshAutomations(true); });
  expect(api.edit).toHaveBeenCalledOnce();
  expect(api.read).toHaveBeenCalledOnce();
  expect(result.current.state.automationsError).toBeNull();
  expect(result.current.state.automationsLoading).toBe(false);
});

it("cancels delayed post-run refreshes when settings unmounts", async () => {
  vi.useFakeTimers();
  api.read.mockResolvedValue(saved);
  api.action.mockResolvedValue(saved);
  const { result, unmount } = harness(true);
  await act(async () => { await result.current.actions.handleAutomationAction("run", job); });
  expect(api.read).toHaveBeenCalledOnce();
  unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(4500); });
  expect(api.read).toHaveBeenCalledOnce();
});

it("does not schedule refreshes for an action acknowledged after settings unmounts", async () => {
  vi.useFakeTimers();
  api.read.mockResolvedValue(saved);
  const pending = deferred<AutomationsPayload>();
  api.action.mockReturnValue(pending.promise);
  const { result, unmount } = harness(true);
  let operation!: Promise<void>;
  act(() => { operation = result.current.actions.handleAutomationAction("run", job); });
  unmount();
  await act(async () => { pending.resolve(saved); await operation; await vi.advanceTimersByTimeAsync(4500); });
  expect(api.read).toHaveBeenCalledOnce();
});

it("does not send an explicit refresh through a retained unmounted callback", async () => {
  api.read.mockResolvedValue(saved);
  const { result, unmount } = harness(false);
  const refresh = result.current.refreshAutomations;
  unmount();
  await refresh(true);
  expect(api.read).not.toHaveBeenCalled();
});

it("does not send a new mutation through a retained unmounted callback", async () => {
  api.action.mockResolvedValue(saved);
  const { result, unmount } = harness(false);
  const action = result.current.actions.handleAutomationAction;
  unmount();
  await action("disable", job);
  expect(api.action).not.toHaveBeenCalled();
});

it("keeps acknowledged data but skips delayed refreshes while the settings surface is hidden", async () => {
  vi.useFakeTimers();
  api.read.mockResolvedValue(saved);
  api.action.mockResolvedValue(saved);
  const { result, rerender, unmount } = harness(true);
  await act(async () => { await result.current.actions.handleAutomationAction("run", job); });
  rerender({ visible: false });
  await act(async () => { await vi.advanceTimersByTimeAsync(4500); });
  expect(api.read).toHaveBeenCalledOnce();
  expect(result.current.state.automations).toEqual(saved);
  unmount();
});
