import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useSystemSettingsEffects } from "@/features/settings/system/useSystemSettingsEffects";
import { useSystemSettingsState } from "@/features/settings/system/useSystemSettingsState";
import type { SettingsSectionKey } from "@/features/settings/contracts";
import { deferred } from "./helpers/deferred";

const api = vi.hoisted(() => ({ cli: vi.fn(), features: vi.fn(), mcp: vi.fn(), automations: vi.fn() }));
vi.mock("@/lib/api", async original => ({
  ...await original<typeof import("@/lib/api")>(),
  fetchCliApps: api.cli, fetchCirnoFeatures: api.features,
  fetchMcpPresets: api.mcp, fetchAutomations: api.automations,
}));

const catalogs = [
  { api: "cli", section: "apps", value: { apps: [], installed_count: 7 }, field: "cliApps", error: "cliAppsError", loading: "cliAppsLoading" },
  { api: "features", section: "channels", value: { features: [], enabled_count: 7 }, field: "cirnoFeatures", error: "cirnoFeaturesError", loading: "cirnoFeaturesLoading" },
  { api: "mcp", section: "mcp", value: { presets: [], installed_count: 7 }, field: "mcpPresets", error: "mcpError", loading: "mcpPresetsLoading" },
  { api: "automations", section: "automations", value: { jobs: [] }, field: "automations", error: "automationsError", loading: "automationsLoading" },
] as const;

function harness(section: SettingsSectionKey) {
  let token = "first-account";
  const getToken = () => token;
  const view = renderHook(() => {
    const state = useSystemSettingsState();
    useSystemSettingsEffects({ state, activeSection: section, getToken, pageVisible: true });
    return state;
  });
  return { ...view, rotateToken: () => { token = "second-account"; } };
}

beforeEach(() => {
  vi.useFakeTimers();
  api.cli.mockReset().mockResolvedValue({ apps: [], installed_count: 0 });
  api.features.mockReset().mockResolvedValue({ features: [], enabled_count: 0 });
  api.mcp.mockReset().mockResolvedValue({ presets: [], installed_count: 0 });
  api.automations.mockReset().mockResolvedValue({ jobs: [] });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

it.each(catalogs)("discards $api results from a previous account and settles its loading indicator", async catalog => {
  const pending = deferred<unknown>();
  api[catalog.api].mockReturnValue(pending.promise);
  const { result, rotateToken } = harness(catalog.section);
  rotateToken();
  await act(async () => pending.resolve(catalog.value));
  expect(result.current[catalog.field]).toBeNull();
  expect(result.current[catalog.error]).toBeNull();
  expect(result.current[catalog.loading]).toBe(false);
});

it.each(catalogs)("discards $api errors from a previous account", async catalog => {
  const pending = deferred<unknown>();
  api[catalog.api].mockReturnValue(pending.promise);
  const { result, rotateToken } = harness(catalog.section);
  rotateToken();
  await act(async () => pending.reject(new Error("Previous account error")));
  expect(result.current[catalog.error]).toBeNull();
  expect(result.current[catalog.loading]).toBe(false);
});

it.each([false, true])("keeps MCP data and loading owned by the latest read (old first=%s)", async oldFirst => {
  const first = deferred<unknown>(), latest = deferred<unknown>();
  api.mcp.mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise);
  const { result } = harness("mcp");
  act(() => result.current.mcpRefreshRef.current?.());
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(api.mcp).toHaveBeenCalledTimes(2);
  if (oldFirst) {
    await act(async () => first.resolve({ presets: [], installed_count: 1 }));
    expect(result.current.mcpPresetsLoading).toBe(true);
  }
  await act(async () => latest.resolve({ presets: [], installed_count: 2 }));
  if (!oldFirst) await act(async () => first.resolve({ presets: [], installed_count: 1 }));
  expect(result.current.mcpPresets?.installed_count).toBe(2);
  expect(result.current.mcpPresetsLoading).toBe(false);
});
