import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useCapabilitySettingsActions } from "@/features/settings/capabilities/useCapabilitySettingsActions";
import { useCapabilitySettingsState } from "@/features/settings/capabilities/useCapabilitySettingsState";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { CirnoClient } from "@/lib/cirno-client";
import { settingsPayload } from "@/tests/settings-test-utils";
import i18n from "@/i18n";

const api = vi.hoisted(() => ({ save: vi.fn() }));
vi.mock("@/lib/api", async original => ({
  ...await original<typeof import("@/lib/api")>(), updateWebSearchSettings: api.save,
}));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
function harness(install = vi.fn(async () => true)) {
  const settings = settingsPayload();
  settings.web_search.provider = "olostep";
  settings.web_search.api_key_hint = "saved";
  settings.web_search.providers.push({ name: "olostep", label: "Olostep", credential: "api_key" });
  const applyPayload = vi.fn();
  const client = {} as CirnoClient;
  const view = renderHook(() => {
    const state = useCapabilitySettingsState(settings);
    const actions = useCapabilitySettingsActions({
      state, settings, client, t: i18n.t, applyPayload,
      setPendingRestartSections: vi.fn(), installCapabilities: install,
    });
    return { state, actions };
  });
  return { ...view, install, applyPayload, settings };
}
beforeEach(() => { api.save.mockReset(); });

it("coalesces an install save and the autosave of the same search draft", async () => {
  const install = deferred<boolean>();
  const view = harness(vi.fn(() => install.promise));
  api.save.mockResolvedValue(view.settings);
  let saves!: Promise<boolean>[];
  await act(async () => {
    saves = [view.result.current.actions.saveWebSearch(), view.result.current.actions.saveWebSearch()];
  });
  const installations = view.install.mock.calls.length;
  await act(async () => { install.resolve(true); await Promise.all(saves); });
  expect(installations).toBe(1);
  expect(api.save).toHaveBeenCalledTimes(1);
  expect(view.result.current.state.webSearchSaving).toBe(false);
});

it("does not submit an obsolete search provider after its dependency install completes", async () => {
  const install = deferred<boolean>();
  const view = harness(vi.fn(() => install.promise));
  api.save.mockResolvedValue(view.settings);
  let save!: Promise<boolean>;
  await act(async () => { save = view.result.current.actions.saveWebSearch(); });
  act(() => view.result.current.actions.handleWebSearchProviderChange("duckduckgo"));
  await act(async () => { install.resolve(true); await save; });
  expect(api.save).not.toHaveBeenCalled();
  expect(view.result.current.state.webSearchForm.provider).toBe("duckduckgo");
});

it("serializes newer search edits behind an accepted save", async () => {
  const first = deferred<SettingsPayload>(), second = deferred<SettingsPayload>();
  const view = harness();
  api.save.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  let oldSave!: Promise<boolean>, newSave!: Promise<boolean>;
  await act(async () => { oldSave = view.result.current.actions.saveWebSearch(); });
  act(() => view.result.current.actions.handleWebSearchProviderChange("duckduckgo"));
  await act(async () => { newSave = view.result.current.actions.saveWebSearch(); });
  const requestsBeforeAcknowledgement = api.save.mock.calls.length;
  await act(async () => { first.resolve(view.settings); await oldSave; });
  const savingSecondDraft = view.result.current.state.webSearchSaving;
  const saved = { ...view.settings, web_search: { ...view.settings.web_search, provider: "duckduckgo" } };
  await act(async () => { second.resolve(saved); await newSave; });
  expect(savingSecondDraft).toBe(true);
  expect(requestsBeforeAcknowledgement).toBe(1);
  expect(view.applyPayload.mock.calls.map(([payload]) => payload.web_search.provider)).toEqual(["olostep", "duckduckgo"]);
  expect(view.result.current.state.webSearchForm.provider).toBe("duckduckgo");
  expect(view.result.current.state.webSearchSaving).toBe(false);
});

it("does not attach an older provider save error to a newly selected provider", async () => {
  const pending = deferred<SettingsPayload>();
  const view = harness();
  api.save.mockReturnValue(pending.promise);
  let save!: Promise<boolean>;
  await act(async () => { save = view.result.current.actions.saveWebSearch(); });
  expect(api.save).toHaveBeenCalledOnce();
  act(() => view.result.current.actions.handleWebSearchProviderChange("duckduckgo"));
  await act(async () => { pending.reject(new Error("Olostep key rejected")); await save; });
  expect(view.result.current.state.capabilityErrors.web).toBeUndefined();
});

it("retains a current provider error and permits an explicit retry", async () => {
  const view = harness();
  api.save.mockRejectedValueOnce(new Error("Key rejected")).mockResolvedValueOnce(view.settings);
  await act(async () => { expect(await view.result.current.actions.saveWebSearch()).toBe(false); });
  expect(view.result.current.state.capabilityErrors.web).toBe("Key rejected");
  await act(async () => { expect(await view.result.current.actions.saveWebSearch()).toBe(true); });
  expect(api.save).toHaveBeenCalledTimes(2);
  expect(view.result.current.state.capabilityErrors.web).toBeUndefined();
});
