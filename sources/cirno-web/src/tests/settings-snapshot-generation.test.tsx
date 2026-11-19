import { act, renderHook } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { useSettingsController } from "@/features/settings/useSettingsController";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { settingsPayload } from "@/tests/settings-test-utils";

const api = vi.hoisted(() => ({ read: vi.fn(), order: vi.fn(), usage: vi.fn() }));
vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof import("@/lib/api")>(),
  fetchSettings: api.read, updateModelCallOrder: api.order, fetchSettingsUsage: api.usage,
  fetchCirnoFeatures: vi.fn(async () => ({ features: [], enabled_count: 0 })),
}));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
const noModelChange = () => {};
function initial(): SettingsPayload {
  const base = settingsPayload();
  base.model_presets.push({ ...base.model_presets[0]!, id: "backup", name: "Backup" });
  base.model_call_order = ["primary", "backup"];
  return base;
}
function harness(section: "appearance" | "overview" = "appearance", seed: SettingsPayload | null = initial()) {
  const client = { requestMutation: vi.fn() } as unknown as CirnoClient;
  return renderHook(() => {
    // Mirrors the Workbench's state.setSettingsSnapshot callback and prop.
    const [snapshot, setSnapshot] = useState(seed);
    const controller = useSettingsController({
      initialSection: section, initialSettings: snapshot,
      onSettingsChange: setSnapshot, onModelNameChange: noModelChange,
    });
    return { controller, snapshot, receiveSnapshot: setSnapshot };
  }, { wrapper: ({ children }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider> });
}
beforeEach(() => { for (const fn of Object.values(api)) fn.mockReset(); });

it("does not apply an old initialization read after a saved order in the same React batch", async () => {
  const oldRead = deferred<SettingsPayload>(), save = deferred<SettingsPayload>();
  const base = initial(), saved = { ...base, model_call_order: ["backup", "primary"] };
  api.read.mockReturnValue(oldRead.promise);
  api.order.mockReturnValue(save.promise);
  const { result } = harness("appearance", base);
  let operation!: Promise<void>;
  act(() => { operation = result.current.controller.modelActions.changeModelCallOrder(saved.model_call_order!); });
  await act(async () => {
    save.resolve(saved);
    await operation;
    oldRead.resolve(base);
    await Promise.resolve();
  });
  expect(api.order).toHaveBeenCalledTimes(1);
  expect(result.current.snapshot?.model_call_order).toEqual(saved.model_call_order);
  expect(result.current.controller.settings?.model_call_order).toEqual(saved.model_call_order);
  expect(result.current.controller.modelState.modelCallOrder).toEqual(saved.model_call_order);
});

it("still accepts a current initialization response and clears initial loading", async () => {
  const pending = deferred<SettingsPayload>(), fresh = initial();
  api.read.mockReturnValue(pending.promise);
  const { result } = harness("appearance", null);
  expect(result.current.controller.loading).toBe(true);
  await act(async () => { pending.resolve(fresh); });
  expect(result.current.controller.settings).toBe(fresh);
  expect(result.current.snapshot).toBe(fresh);
  expect(result.current.controller.loading).toBe(false);
});

it("does not mistake a usage-only update for a saved configuration receipt", async () => {
  const pending = deferred<SettingsPayload>(), usage = deferred<SettingsPayload["usage"]>();
  const fresh = { ...initial(), model_call_order: ["backup", "primary"] };
  api.read.mockReturnValue(pending.promise);
  api.usage.mockReturnValue(usage.promise);
  const { result } = harness("overview");
  await act(async () => { usage.resolve({} as SettingsPayload["usage"]); });
  await act(async () => { pending.resolve(fresh); });
  expect(result.current.controller.settings?.model_call_order).toEqual(fresh.model_call_order);
});

it("does not show a rejected old initialization after the parent hydrates current settings", async () => {
  const pending = deferred<SettingsPayload>(), fresh = initial();
  api.read.mockReturnValue(pending.promise);
  const { result } = harness("appearance", null);
  act(() => result.current.receiveSnapshot(fresh));
  await act(async () => { pending.reject(new Error("Old initialization failed")); });
  expect(result.current.controller.settings).toBe(fresh);
  expect(result.current.controller.loading).toBe(false);
  expect(result.current.controller.error).toBeNull();
});

it("retains a rejected save reason when the initial read subsequently succeeds", async () => {
  const pending = deferred<SettingsPayload>(), base = initial();
  api.read.mockReturnValue(pending.promise);
  api.order.mockRejectedValue(new Error("Order save rejected"));
  const { result } = harness("appearance", base);
  await act(async () => { await result.current.controller.modelActions.changeModelCallOrder(["backup", "primary"]); });
  expect(result.current.controller.error).toBe("Order save rejected");
  await act(async () => { pending.resolve(base); });
  expect(result.current.controller.error).toBe("Order save rejected");
  expect(result.current.controller.modelState.modelCallOrder).toEqual(base.model_call_order);
});

it("clears an initial read failure when the parent supplies a usable snapshot", async () => {
  const pending = deferred<SettingsPayload>(), fresh = initial();
  api.read.mockReturnValue(pending.promise);
  const { result } = harness("appearance", null);
  await act(async () => { pending.reject(new Error("Settings unavailable")); });
  expect(result.current.controller.error).toBe("Settings unavailable");
  expect(result.current.controller.loading).toBe(false);
  act(() => result.current.receiveSnapshot(fresh));
  expect(result.current.controller.settings).toBe(fresh);
  expect(result.current.controller.error).toBeNull();
});
