import { deferred } from "./helpers/deferred";
import { act, fireEvent, renderHook } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { createSystemSettingsActions } from "@/features/settings/system/createSystemSettingsActions";
import { useSystemSettingsEffects } from "@/features/settings/system/useSystemSettingsEffects";
import { useSystemSettingsState } from "@/features/settings/system/useSystemSettingsState";
import { createChannelSections } from "@/features/settings/composition/ChannelSections";
import type { SettingsComposition } from "@/features/settings/composition/useSettingsComposition";
import { CirnoClient } from "@/lib/cirno-client";
import type { CirnoFeaturesPayload } from "@/lib/contracts/channels";
import i18n from "@/i18n";

const api = vi.hoisted(() => ({ read: vi.fn(), enable: vi.fn(), disable: vi.fn() }));
vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof import("@/lib/api")>(),
  fetchCirnoFeatures: api.read, enableCirnoFeature: api.enable, disableCirnoFeature: api.disable,
}));
vi.mock("@/features/channels/ChannelsSettings", () => ({ ChannelsSettings: () => null }));
const token = () => "fixture";
const saved: CirnoFeaturesPayload = { features: [], enabled_count: 2 };
function harness(poll = true) {
  const client = new CirnoClient({ url: "ws://example.test" }), restart = vi.fn();
  return renderHook(() => {
    const state = useSystemSettingsState();
    useSystemSettingsEffects({ state, activeSection: poll ? "channels" : "appearance", getToken: token, pageVisible: true });
    const actions = createSystemSettingsActions({
      state, featureCatalog: [], client, token: token(), getToken: token, t: i18n.t,
      applyPayload: vi.fn(), setPendingRestartSections: restart, refreshAutomations: vi.fn(),
    });
    const bindings = {
      systemState: state, systemActions: actions, displayPreferences: { brandLogos: false },
      settings: null, token: token(), restartInProgress: false,
      pendingRestartSections: { runtime: false, browser: false },
    } as unknown as SettingsComposition;
    const section = createChannelSections(bindings).channels!({ embedded: false }) as ReactElement<{
      onFeaturesUpdate: (payload: CirnoFeaturesPayload) => void;
      onDismissStatus: () => void;
    }>;
    return { state, actions, restart, publishChildReceipt: section.props.onFeaturesUpdate, dismiss: section.props.onDismissStatus };
  });
}
beforeEach(() => { for (const fn of Object.values(api)) fn.mockReset(); api.read.mockResolvedValue({ features: [], enabled_count: 0 }); });

it.each([false, true])("ignores a catalog read that predates a completed action (error=%s)", async (fails) => {
  const read = deferred<CirnoFeaturesPayload>();
  api.read.mockReturnValue(read.promise);
  api.disable.mockResolvedValue(saved);
  const { result } = harness();
  await act(async () => { await result.current.actions.handleCirnoFeatureAction("disable", "fixture"); });
  await act(async () => { if (fails) read.reject(new Error("Old read failed")); else read.resolve({ features: [], enabled_count: 0 }); });
  expect(result.current.state.cirnoFeatures).toEqual(saved);
  expect(result.current.state.cirnoFeaturesError).toBeNull();
});

it.each([false, true])("protects receipts from the real child-panel binding against older catalog reads (error=%s)", async (fails) => {
  const read = deferred<CirnoFeaturesPayload>();
  api.read.mockReturnValue(read.promise);
  const { result } = harness();
  act(() => result.current.publishChildReceipt(saved));
  await act(async () => { if (fails) read.reject(new Error("Old child read failed")); else read.resolve({ features: [], enabled_count: 0 }); });
  expect(result.current.state.cirnoFeatures).toEqual(saved);
  expect(result.current.state.cirnoFeaturesError).toBeNull();
});

it("keeps an explicit failed action visible across subsequent healthy polling", async () => {
  const failed = { ...saved, last_action: { ok: false, message: "Saved; stopping failed" } };
  api.disable.mockResolvedValue(failed);
  const { result } = harness();
  await act(async () => {});
  await act(async () => { await result.current.actions.handleCirnoFeatureAction("disable", "fixture"); });
  await act(async () => { fireEvent(window, new Event("focus")); });
  expect(result.current.state.cirnoFeaturesError).toBe(failed.last_action.message);
});

it("pauses channel polling during an admitted catalog mutation and resumes afterward", async () => {
  const pending = deferred<CirnoFeaturesPayload>();
  api.disable.mockReturnValue(pending.promise);
  const { result } = harness();
  await act(async () => {});
  let request!: Promise<void>;
  act(() => { request = result.current.actions.handleCirnoFeatureAction("disable", "fixture"); });
  await act(async () => { fireEvent(window, new Event("focus")); });
  expect(api.read).toHaveBeenCalledTimes(1);
  await act(async () => { pending.resolve(saved); await request; });
  await act(async () => { fireEvent(window, new Event("focus")); });
  expect(api.read).toHaveBeenCalledTimes(2);
});

it("clears a recovered catalog-read error without confusing it with action errors", async () => {
  api.read.mockRejectedValueOnce(new Error("Catalog unavailable")).mockResolvedValue(saved);
  const { result } = harness();
  await act(async () => {});
  expect(result.current.state.cirnoFeaturesError).toBe("Catalog unavailable");
  await act(async () => { fireEvent(window, new Event("focus")); });
  expect(result.current.state.cirnoFeaturesError).toBeNull();
});

it("dismisses both read and action errors through the actual channel-section binding", async () => {
  api.read.mockRejectedValueOnce(new Error("Read failed"));
  const failed = { ...saved, last_action: { ok: false, message: "Action failed" } };
  api.disable.mockResolvedValue(failed);
  const { result } = harness();
  await act(async () => {});
  expect(result.current.state.cirnoFeaturesError).toBe("Read failed");
  act(() => result.current.dismiss());
  expect(result.current.state.cirnoFeaturesError).toBeNull();
  await act(async () => { await result.current.actions.handleCirnoFeatureAction("disable", "fixture"); });
  expect(result.current.state.cirnoFeaturesError).toBe("Action failed");
  act(() => result.current.dismiss());
  expect(result.current.state.cirnoFeaturesError).toBeNull();
});

it.each(["toggle", "install"] as const)("does not admit a retained %s callback after unmount", async kind => {
  const { result, unmount } = harness(false), actions = result.current.actions;
  unmount();
  if (kind === "toggle") await actions.handleCirnoFeatureAction("disable", "fixture");
  else await actions.installCapabilities(["first", "second"]);
  expect(api.disable).not.toHaveBeenCalled();
  expect(api.enable).not.toHaveBeenCalled();
});

it("does not start another capability install or publish restart after its owner leaves", async () => {
  const first = deferred<CirnoFeaturesPayload>();
  api.enable.mockReturnValue(first.promise);
  const { result, unmount } = harness(false), restart = result.current.restart;
  let request!: Promise<boolean>;
  act(() => { request = result.current.actions.installCapabilities(["first", "second"]); });
  unmount();
  await act(async () => { first.resolve({ ...saved, requires_restart: true }); await request; });
  expect(api.enable).toHaveBeenCalledTimes(1);
  expect(restart).not.toHaveBeenCalled();
});

it("retains an earlier successful installation receipt if a later dependency fails", async () => {
  api.enable.mockResolvedValueOnce(saved).mockRejectedValueOnce(new Error("Second install failed"));
  const { result } = harness(false);
  await act(async () => { expect(await result.current.actions.installCapabilities(["first", "second"])).toBe(false); });
  expect(result.current.state.cirnoFeatures).toEqual(saved);
  expect(result.current.state.cirnoFeaturesError).toBe("Second install failed");
});

it("stops the capability chain on an explicit failed receipt while preserving its saved state", async () => {
  const failed = { ...saved, last_action: { ok: false, message: "Support saved; activation failed" } };
  api.enable.mockResolvedValue(failed);
  const { result } = harness(false);
  await act(async () => { expect(await result.current.actions.installCapabilities(["first", "second"])).toBe(false); });
  expect(api.enable).toHaveBeenCalledTimes(1);
  expect(result.current.state.cirnoFeatures).toEqual(failed);
  expect(result.current.state.cirnoFeaturesError).toBe(failed.last_action.message);
});

it("does not publish restart state from an admitted toggle after the surface unmounts", async () => {
  const pending = deferred<CirnoFeaturesPayload>();
  api.disable.mockReturnValue(pending.promise);
  const { result, unmount } = harness(false), restart = result.current.restart;
  let request!: Promise<void>;
  act(() => { request = result.current.actions.handleCirnoFeatureAction("disable", "fixture"); });
  unmount();
  await act(async () => { pending.resolve({ ...saved, requires_restart: true }); await request; });
  expect(restart).not.toHaveBeenCalled();
});
