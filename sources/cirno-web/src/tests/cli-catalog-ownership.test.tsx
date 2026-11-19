import { deferred } from "./helpers/deferred";
import { act, renderHook } from "@testing-library/react";
import { Children, type ReactElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createSystemSettingsActions } from "@/features/settings/system/createSystemSettingsActions";
import { useSystemSettingsEffects } from "@/features/settings/system/useSystemSettingsEffects";
import { useSystemSettingsState } from "@/features/settings/system/useSystemSettingsState";
import { CirnoClient } from "@/lib/cirno-client";
import type { CliAppsPayload } from "@/lib/contracts/apps";
import i18n from "@/i18n";
import { createAppSections } from "@/features/settings/composition/AppSections";
import type { SettingsComposition } from "@/features/settings/composition/useSettingsComposition";

const api = vi.hoisted(() => ({ read: vi.fn(), mutate: vi.fn(), notify: vi.fn() }));
vi.mock("@/lib/cli-app-events", () => ({ notifyCliAppsChanged: api.notify }));
vi.mock("@/features/settings/apps/AppsCatalogSettings", () => ({ AppsCatalogSettings: () => null }));
vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof import("@/lib/api")>(),
  fetchCliApps: api.read,
  runCliAppAction: api.mutate,
  fetchMcpPresets: vi.fn(async () => ({ presets: [], installed_count: 0 })),
  fetchCirnoFeatures: vi.fn(async () => ({ features: [], enabled_count: 0 })),
}));

const token = () => "fixture-token";
const payload: CliAppsPayload = { apps: [], installed_count: 2, last_action: { ok: true, message: "Saved" } };
function harness(effects = false, visible = true) {
  const client = new CirnoClient({ url: "ws://example.test" });
  return renderHook(({ isVisible }) => {
    const state = useSystemSettingsState();
    useSystemSettingsEffects({ state, activeSection: effects ? "apps" : "channels", getToken: token, pageVisible: isVisible });
    const actions = createSystemSettingsActions({
      state, featureCatalog: [], client, token: token(), getToken: token, t: i18n.t,
      applyPayload: vi.fn(), setPendingRestartSections: vi.fn(), refreshAutomations: vi.fn(),
    });
    const section = createAppSections({
      systemState: state, systemActions: actions, activeSection: "apps", showSidebar: false,
      displayPreferences: { brandLogos: false }, pendingRestartSections: { runtime: false, browser: false },
    } as unknown as SettingsComposition).apps!({ embedded: false }) as ReactElement<{ children: ReactNode }>;
    const catalog = Children.toArray(section.props.children).at(-1) as ReactElement<{ onDismissStatus: () => void }>;
    return { state, actions, dismiss: catalog.props.onDismissStatus };
  }, { initialProps: { isVisible: visible } });
}

describe("CLI catalog request ownership", () => {
  beforeEach(() => { api.read.mockReset(); api.mutate.mockReset(); api.notify.mockReset(); });
  afterEach(() => vi.useRealTimers());

  it("retains one CLI mutation owner through duplicate and other-app requests", async () => {
    const pending = deferred<CliAppsPayload>();
    api.mutate.mockReturnValue(pending.promise);
    const { result } = harness();
    let requests!: Promise<void>[];
    act(() => { requests = [
      result.current.actions.handleCliAppAction("install", "first"),
      result.current.actions.handleCliAppAction("install", "first"),
      result.current.actions.handleCliAppAction("update", "second"),
    ]; });
    const accepted = api.mutate.mock.calls.length;
    await act(async () => { pending.resolve(payload); await Promise.all(requests); });
    expect(accepted).toBe(1);
    api.mutate.mockResolvedValue(payload);
    await act(async () => { await result.current.actions.handleCliAppAction("update", "second"); });
    expect(api.mutate).toHaveBeenCalledTimes(2);
  });

  it.each([false, true])("does not let an old catalog read replace a finished mutation (read error=%s)", async (fails) => {
    const read = deferred<CliAppsPayload>();
    api.read.mockReturnValue(read.promise);
    api.mutate.mockResolvedValue(payload);
    const { result } = harness(true);
    await act(async () => { await result.current.actions.handleCliAppAction("install", "first"); });
    expect(result.current.state.cliAppsLoading).toBe(false);
    await act(async () => {
      if (fails) read.reject(new Error("Stale read failed"));
      else read.resolve({ apps: [], installed_count: 0 });
    });
    expect(result.current.state.cliApps?.installed_count).toBe(2);
    expect(result.current.state.cliAppsError).toBeNull();
  });

  it("does not start catalog polling while the page is hidden", async () => {
    api.read.mockResolvedValue({ apps: [], installed_count: 0 });
    harness(true, false);
    await act(async () => {});
    expect(api.read).not.toHaveBeenCalled();
  });

  it("does not admit retained CLI mutation callbacks after unmount", async () => {
    const { result, unmount } = harness();
    const retained = result.current.actions.handleCliAppAction;
    unmount();
    await retained("install", "late");
    expect(api.mutate).not.toHaveBeenCalled();
  });

  it("does not notify a new surface when a retired CLI request completes", async () => {
    const pending = deferred<CliAppsPayload>();
    api.mutate.mockReturnValue(pending.promise);
    const { result, unmount } = harness();
    let request!: Promise<void>;
    act(() => { request = result.current.actions.handleCliAppAction("install", "first"); });
    unmount();
    await act(async () => { pending.resolve(payload); await request; });
    expect(api.notify).not.toHaveBeenCalled();
  });

  it("defers a scheduled CLI catalog retry while installation owns the surface", async () => {
    vi.useFakeTimers();
    api.read.mockResolvedValue({ apps: [], installed_count: 0, catalog_refresh_pending: true });
    const pending = deferred<CliAppsPayload>();
    api.mutate.mockReturnValue(pending.promise);
    const { result } = harness(true);
    await act(async () => {});
    let request!: Promise<void>;
    act(() => { request = result.current.actions.handleCliAppAction("install", "first"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(api.read).toHaveBeenCalledTimes(1);
    await act(async () => { pending.resolve(payload); await request; });
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(api.read).toHaveBeenCalledTimes(2);
  });

  it.each([false, true])("keeps a failed CLI action visible after its catalog retry (read failure=%s)", async fails => {
    vi.useFakeTimers();
    api.read.mockResolvedValueOnce({ apps: [], installed_count: 0, catalog_refresh_pending: true });
    if (fails) api.read.mockRejectedValue(new Error("New read failed"));
    else api.read.mockResolvedValue({ apps: [], installed_count: 2 });
    const failed = { ...payload, last_action: { ok: false, message: "Installed command failed verification" } };
    api.mutate.mockResolvedValue(failed);
    const { result } = harness(true);
    await act(async () => {});
    await act(async () => { await result.current.actions.handleCliAppAction("install", "first"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current.state.cliAppsError).toBe(failed.last_action.message);
  });

  it("recovers a read error when the visible catalog loads again", async () => {
    api.read.mockRejectedValueOnce(new Error("Catalog unavailable")).mockResolvedValue(payload);
    const { result, rerender } = harness(true);
    await act(async () => {});
    expect(result.current.state.cliAppsError).toBe("Catalog unavailable");
    rerender({ isVisible: false });
    rerender({ isVisible: true });
    await act(async () => {});
    expect(result.current.state.cliAppsError).toBeNull();
  });

  it("dismisses read and action errors through the actual Apps section binding", async () => {
    api.read.mockRejectedValue(new Error("Read failed"));
    api.mutate.mockResolvedValue({ ...payload, last_action: { ok: false, message: "Action failed" } });
    const { result } = harness(true);
    await act(async () => {});
    act(() => result.current.dismiss());
    expect(result.current.state.cliAppsError).toBeNull();
    await act(async () => { await result.current.actions.handleCliAppAction("install", "first"); });
    expect(result.current.state.cliAppsError).toBe("Action failed");
    act(() => result.current.dismiss());
    expect(result.current.state.cliAppsError).toBeNull();
  });
});
