import { deferred } from "./helpers/deferred";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useProviderBalance } from "@/features/settings/providers/model/useProviderBalance";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { ProviderBalancePayload } from "@/lib/contracts/models";
import { settingsPayload } from "./settings-test-utils";

const api = vi.hoisted(() => ({ read: vi.fn(), save: vi.fn() }));
vi.mock("@/lib/api", async original => ({
  ...await original<typeof import("@/lib/api")>(),
  fetchProviderBalance: api.read, updateProviderSettings: api.save,
}));
const row: SettingsPayload["providers"][number] = {
  id: "deepseek", name: "DeepSeek", configured: true,
  balance: { endpoint: "https://billing.example/account", format: "json", amount_path: "/balance", currency: "USD", api_key: "••••••••" },
};
const balance: ProviderBalancePayload = { provider_id: "deepseek", status: "ok", balances: [{ amount: "12.00", currency: "USD" }] };
function setup() {
  const saved = vi.fn();
  const client = {} as CirnoClient;
  let token = "fixture";
  const view = renderHook(({ provider }) => useProviderBalance(provider, saved), {
    initialProps: { provider: row },
    wrapper: ({ children }) => <ClientProvider client={client} token={token}>{children}</ClientProvider>,
  });
  return { ...view, saved, rotateToken: () => { token = "replacement"; view.rerender({ provider: row }); } };
}
beforeEach(() => { api.read.mockReset(); api.save.mockReset(); });

it("admits only one balance refresh before its pending indicator commits", async () => {
  const pending = deferred<ProviderBalancePayload>();
  api.read.mockReturnValue(pending.promise);
  const { result } = setup();
  let operations!: Promise<unknown>[];
  act(() => { operations = [result.current.refresh(), result.current.refresh()]; });
  const admitted = api.read.mock.calls.length;
  await act(async () => { pending.resolve(balance); await Promise.all(operations); });
  expect(admitted).toBe(1);
  expect(result.current.balances).toEqual(balance.balances);
});

it("does not revive an old balance read after configuration changes away and back", async () => {
  const pending = deferred<ProviderBalancePayload>();
  api.read.mockReturnValue(pending.promise);
  const { result, rerender } = setup();
  let operation!: Promise<unknown>;
  act(() => { operation = result.current.refresh(); });
  rerender({ provider: { ...row, balance: { ...row.balance!, endpoint: "https://new-billing.example" } } });
  rerender({ provider: row });
  await act(async () => { pending.resolve(balance); await operation; });
  expect(result.current.balances).toEqual([]);
});

it("keeps a replacement editor independent of retained draft and visibility setters", () => {
  const { result, rerender } = setup();
  act(() => result.current.edit());
  const { setDraft, setOpen } = result.current;
  rerender({ provider: { ...row, balance: { ...row.balance!, currency: "EUR" } } });
  act(() => result.current.edit());
  act(() => { setDraft({ ...row.balance!, currency: "stale" }); setOpen(false); });
  expect(result.current.open).toBe(true);
  expect(result.current.draft?.currency).toBe("EUR");
});

it("does not accept a balance response from the previous browser token", async () => {
  const pending = deferred<ProviderBalancePayload>();
  api.read.mockReturnValue(pending.promise);
  const { result, rotateToken } = setup();
  let operation!: Promise<unknown>;
  act(() => { operation = result.current.refresh(); });
  rotateToken();
  await act(async () => { pending.resolve(balance); await operation; });
  expect(result.current.balances).toEqual([]);
});

it("does not publish a balance save receipt after its settings view unmounts", async () => {
  const pending = deferred<SettingsPayload>();
  api.save.mockReturnValue(pending.promise);
  const { result, unmount, saved } = setup();
  act(() => result.current.edit());
  let operation!: Promise<unknown>;
  act(() => { operation = result.current.save(); });
  unmount();
  await act(async () => { pending.resolve(settingsPayload()); await operation; });
  expect(saved).not.toHaveBeenCalled();
});

it("retains a rejected balance save reason when an earlier read fails later", async () => {
  const pending = deferred<ProviderBalancePayload>();
  api.read.mockReturnValue(pending.promise);
  api.save.mockRejectedValue(new Error("Balance save rejected"));
  const { result } = setup();
  let read!: Promise<unknown>;
  act(() => { read = result.current.refresh(); result.current.edit(); });
  await act(async () => { await result.current.save(); });
  await act(async () => { pending.reject(new Error("Balance endpoint unavailable")); await read; });
  expect(result.current.error).toBe("Balance save rejected");
  expect(result.current.open).toBe(true);
});

it("invalidates an older read after saving a new secret whose masked signature is unchanged", async () => {
  const pending = deferred<ProviderBalancePayload>();
  api.read.mockReturnValue(pending.promise);
  api.save.mockResolvedValue({ ...settingsPayload(), providers: [row] });
  const { result } = setup();
  let read!: Promise<unknown>;
  act(() => { read = result.current.refresh(); result.current.edit(); });
  act(() => result.current.setDraft({ ...row.balance!, api_key: "replacement-test-key" }));
  await act(async () => { await result.current.save(); });
  expect(result.current.loading).toBe(true);
  await act(async () => { pending.resolve(balance); await read; });
  expect(result.current.loading).toBe(false);
  expect(result.current.balances).toEqual([]);
});

it("keeps a failed balance save draft and allows retry on the current view", async () => {
  api.save.mockRejectedValueOnce(new Error("Save unavailable")).mockResolvedValueOnce(settingsPayload());
  const { result, saved } = setup();
  act(() => result.current.edit());
  const draft = { ...row.balance!, currency: "credits" };
  act(() => result.current.setDraft(draft));
  await act(async () => { await result.current.save(); });
  expect(result.current.open).toBe(true);
  expect(result.current.draft).toEqual(draft);
  await act(async () => { await result.current.save(); });
  expect(result.current.open).toBe(false);
  expect(saved).toHaveBeenCalledTimes(1);
  expect(api.save).toHaveBeenLastCalledWith(expect.anything(), { provider: "deepseek", balance: draft });
});

it("submits one balance write for duplicate save callbacks in the same update", async () => {
  const pending = deferred<SettingsPayload>();
  api.save.mockReturnValue(pending.promise);
  const { result, saved } = setup();
  act(() => result.current.edit());
  let operations!: Promise<unknown>[];
  act(() => { operations = [result.current.save(), result.current.save()]; });
  const admitted = api.save.mock.calls.length;
  await act(async () => { pending.resolve(settingsPayload()); await Promise.all(operations); });
  expect(admitted).toBe(1);
  expect(saved).toHaveBeenCalledTimes(1);
});
