import { deferred } from "./helpers/deferred";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createSystemSettingsActions } from "@/features/settings/system/createSystemSettingsActions";
import { useSystemSettingsEffects } from "@/features/settings/system/useSystemSettingsEffects";
import { useSystemSettingsState } from "@/features/settings/system/useSystemSettingsState";
import { CirnoClient } from "@/lib/cirno-client";
import type { McpOAuthFlowPayload, McpPresetInfo, McpPresetsPayload } from "@/lib/contracts/mcp";
import i18n from "@/i18n";

const api = vi.hoisted(() => ({ read: vi.fn(), action: vi.fn(), custom: vi.fn(), import: vi.fn(), tools: vi.fn(), notify: vi.fn(), start: vi.fn(), status: vi.fn(), complete: vi.fn(), cancel: vi.fn() }));
vi.mock("@/lib/api", async (original) => ({
  ...await original<typeof import("@/lib/api")>(),
  fetchMcpPresets: api.read, runMcpPresetAction: api.action,
  fetchCliApps: vi.fn().mockResolvedValue({ apps: [], installed_count: 0 }),
  saveCustomMcpServer: api.custom, importMcpConfig: api.import, updateMcpServerTools: api.tools,
  startMcpOAuth: api.start, fetchMcpOAuthStatus: api.status, completeMcpOAuth: api.complete, cancelMcpOAuth: api.cancel,
}));
vi.mock("@/lib/mcp-preset-events", () => ({ notifyMcpPresetsChanged: api.notify }));
const token = () => "fixture-token";
const saved: McpPresetsPayload = { presets: [], installed_count: 1 };
function harness(poll = false) {
  const client = new CirnoClient({ url: "ws://example.test" });
  const restart = vi.fn();
  return renderHook(() => {
    const state = useSystemSettingsState();
    const { refreshAutomations } = useSystemSettingsEffects({
      state, activeSection: poll ? "mcp" : "appearance", getToken: token, pageVisible: true,
    });
    const actions = createSystemSettingsActions({
      state, featureCatalog: [], client, token: token(), getToken: token, t: i18n.t,
      applyPayload: vi.fn(), setPendingRestartSections: restart, refreshAutomations,
    });
    return { state, actions, restart };
  });
}
beforeEach(() => { for (const fn of Object.values(api)) fn.mockReset(); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

it.each(["import", "edit"] as const)("retains committed %s feedback and restart state when cleanup fails", async kind => {
  const payload: McpPresetsPayload = { ...saved, requires_restart: true,
    last_action: { ok: false, persisted: true, message: "Configuration saved; cleanup failed" } };
  api.import.mockResolvedValue(payload);
  const { result } = harness();
  const raw = '{"mcpServers":{"fixture":{"command":"fixture"}}}';
  act(() => { result.current.state.setMcpConfigImport(raw); });
  await act(async () => {
    if (kind === "import") await result.current.actions.handleImportMcpConfig();
    else await expect(result.current.actions.handleSaveMcpConfig("fixture", '{"command":"fixture"}')).rejects.toThrow("cleanup failed");
  });
  expect(result.current.state.mcpPresets).toEqual(payload);
  expect(result.current.state.mcpError).toBe(payload.last_action!.message);
  expect(result.current.restart).toHaveBeenCalledOnce();
  expect(result.current.restart.mock.calls[0][0]({})).toEqual({ runtime: true });
  expect(api.notify).toHaveBeenCalledWith(payload);
  if (kind === "import") expect(result.current.state.mcpConfigImport).toBe(raw);
});

it.each([false, true])("keeps a custom MCP draft only when its saved receipt reports incomplete cleanup (ok=%s)", async ok => {
  api.custom.mockResolvedValue({ ...saved, last_action: { ok, persisted: true, message: "Fixture receipt" } });
  const { result } = harness();
  act(() => { result.current.state.setCustomMcpForm(previous => ({ ...previous, name: "fixture", command: "fixture-command" })); });
  await act(async () => { await result.current.actions.handleSaveCustomMcp(); });
  expect(result.current.state.customMcpForm.name).toBe(ok ? "" : "fixture");
  expect(result.current.state.customMcpForm.command).toBe(ok ? "" : "fixture-command");
});

it.each([false, true])("does not overwrite an MCP mutation acknowledgement with an older catalog read (error=%s)", async fails => {
  const read = deferred<McpPresetsPayload>();
  api.read.mockReturnValue(read.promise);
  api.action.mockResolvedValue(saved);
  const { result } = harness(true);
  await act(async () => { await result.current.actions.handleMcpPresetAction("disable", "fixture"); });
  await act(async () => {
    if (fails) read.reject(new Error("Old request failed"));
    else read.resolve({ presets: [], installed_count: 0 });
  });
  expect(result.current.state.mcpPresets).toEqual(saved);
  expect(result.current.state.mcpError).toBeNull();
});

it("serializes same-frame MCP mutations across preset, tool and configuration controls", async () => {
  const pending = deferred<McpPresetsPayload>();
  for (const fn of [api.action, api.custom, api.import, api.tools]) fn.mockReturnValue(pending.promise);
  const { result } = harness();
  let operations!: Promise<unknown>[];
  act(() => { operations = [
    result.current.actions.handleMcpPresetAction("disable", "fixture"),
    result.current.actions.handleMcpPresetAction("enable", "other"),
    result.current.actions.handleMcpToolsChange("fixture", []),
    result.current.actions.handleSaveCustomMcp(),
    result.current.actions.handleImportMcpConfig(),
    result.current.actions.handleSaveMcpConfig("fixture", '{"command":"fixture"}'),
  ]; });
  const settled = Promise.allSettled(operations);
  const calls = [api.action, api.custom, api.import, api.tools].reduce((sum, fn) => sum + fn.mock.calls.length, 0);
  await act(async () => { pending.resolve(saved); await settled; });
  expect(calls).toBe(1);
  expect(result.current.state.mcpPresetAction).toBeNull();
});

const mutations = {
  preset: (actions: ReturnType<typeof createSystemSettingsActions>) => actions.handleMcpPresetAction("disable", "fixture"),
  tools: (actions: ReturnType<typeof createSystemSettingsActions>) => actions.handleMcpToolsChange("fixture", []),
  custom: (actions: ReturnType<typeof createSystemSettingsActions>) => actions.handleSaveCustomMcp(),
  import: (actions: ReturnType<typeof createSystemSettingsActions>) => actions.handleImportMcpConfig(),
  edit: (actions: ReturnType<typeof createSystemSettingsActions>) => actions.handleSaveMcpConfig("fixture", '{"command":"fixture"}'),
};
it.each(Object.keys(mutations) as (keyof typeof mutations)[])("does not start %s through a retained closed Settings callback", async kind => {
  for (const fn of [api.action, api.custom, api.import, api.tools]) fn.mockResolvedValue(saved);
  const { result, unmount } = harness();
  const actions = result.current.actions;
  unmount();
  await Promise.allSettled([mutations[kind](actions)]);
  for (const fn of [api.action, api.custom, api.import, api.tools]) expect(fn).not.toHaveBeenCalled();
});

it("does not announce a late MCP acknowledgement from a closed Settings surface", async () => {
  const pending = deferred<McpPresetsPayload>();
  api.action.mockReturnValue(pending.promise);
  const { result, unmount } = harness();
  let operation!: Promise<void>;
  act(() => { operation = result.current.actions.handleMcpPresetAction("disable", "fixture"); });
  unmount();
  await act(async () => { pending.resolve(saved); await operation; });
  expect(api.notify).not.toHaveBeenCalled();
});

it("releases a failed MCP mutation before the next control can save", async () => {
  api.action.mockRejectedValue(new Error("Fixture rejected"));
  api.tools.mockResolvedValue(saved);
  const { result } = harness();
  await act(async () => { await result.current.actions.handleMcpPresetAction("disable", "fixture"); });
  expect(result.current.state.mcpError).toBe("Fixture rejected");
  await act(async () => { await result.current.actions.handleMcpToolsChange("fixture", []); });
  expect(api.tools).toHaveBeenCalledOnce();
  expect(result.current.state.mcpPresets).toEqual(saved);
  expect(result.current.state.mcpPresetAction).toBeNull();
});

it("polls a connecting mutation acknowledgement after an earlier idle catalog read", async () => {
  vi.useFakeTimers();
  const preset: McpPresetInfo = { name: "fixture", display_name: "Fixture", category: "test", description: "Fixture",
    docs_url: "", transport: "stdio", requires: "", note: "", install_supported: true, installed: true, configured: true,
    available: true, status: "configured", required_fields: [], connection_summary: "Fixture", runtime_status: "connecting" };
  api.read.mockResolvedValueOnce(saved).mockResolvedValue({ ...saved, presets: [{ ...preset, runtime_status: "connected" }] });
  api.action.mockResolvedValue({ ...saved, presets: [preset] });
  const { result, unmount } = harness(true);
  await act(async () => {});
  await act(async () => { await result.current.actions.handleMcpPresetAction("reconnect", "fixture"); await vi.advanceTimersByTimeAsync(1200); });
  expect(result.current.state.mcpPresets?.presets[0]?.runtime_status).toBe("connected");
  unmount();
});

const flow: McpOAuthFlowPayload = { flow_id: "fixture-flow", name: "fixture", status: "authorization_required", completion_input: "callback_url", expires_in: 300 };
function mockPopup() {
  const popup = { closed: false, close: vi.fn(), focus: vi.fn(), location: { replace: vi.fn() }, document: { title: "", body: { textContent: "" } } };
  const open = vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
  return { popup, open };
}

it("admits one OAuth start and excludes another MCP change in the same frame", async () => {
  vi.useFakeTimers();
  mockPopup();
  const pending = deferred<McpOAuthFlowPayload>();
  api.start.mockReturnValue(pending.promise);
  api.action.mockResolvedValue(saved);
  const { result, unmount } = harness();
  let operations!: Promise<void>[];
  act(() => { operations = [
    result.current.actions.handleMcpOAuthConnect("fixture"),
    result.current.actions.handleMcpOAuthConnect("other"),
    result.current.actions.handleMcpPresetAction("disable", "other"),
  ]; });
  const calls = api.start.mock.calls.length;
  await act(async () => { pending.resolve(flow); await Promise.all(operations); });
  unmount();
  expect(calls).toBe(1);
  expect(api.action).not.toHaveBeenCalled();
});

it.each([false, true])("retires OAuth polling and closes its popup on unmount (start pending=%s)", async pendingStart => {
  vi.useFakeTimers();
  const { popup } = mockPopup();
  const pending = deferred<McpOAuthFlowPayload>();
  api.start.mockReturnValue(pendingStart ? pending.promise : Promise.resolve(flow));
  api.status.mockResolvedValue(flow);
  const { result, unmount } = harness();
  let operation!: Promise<void>;
  await act(async () => { operation = result.current.actions.handleMcpOAuthConnect("fixture"); if (!pendingStart) await operation; });
  unmount();
  await act(async () => { pending.resolve(flow); await operation; await vi.advanceTimersByTimeAsync(1700); });
  expect(api.status).not.toHaveBeenCalled();
  expect(popup.close).toHaveBeenCalledOnce();
});

it("does not regress a callback acknowledgement when an older OAuth status arrives", async () => {
  vi.useFakeTimers();
  mockPopup();
  const status = deferred<McpOAuthFlowPayload>();
  api.start.mockResolvedValue(flow);
  api.status.mockReturnValue(status.promise);
  api.complete.mockResolvedValue({ ...flow, status: "connecting" });
  const { result, unmount } = harness();
  await act(async () => { await result.current.actions.handleMcpOAuthConnect("fixture"); });
  await act(async () => { await vi.advanceTimersByTimeAsync(800); });
  act(() => { result.current.state.setMcpOAuthCallbackUrl("https://fixture.test/callback?code=fixture"); });
  await act(async () => { await result.current.actions.handleMcpOAuthComplete(); });
  await act(async () => { status.resolve(flow); });
  expect(result.current.state.mcpOAuthFlow?.status).toBe("connecting");
  unmount();
});

it("admits only one callback completion before React commits its busy state", async () => {
  vi.useFakeTimers();
  mockPopup();
  api.start.mockResolvedValue(flow);
  const pending = deferred<McpOAuthFlowPayload>();
  api.complete.mockReturnValue(pending.promise);
  const { result, unmount } = harness();
  await act(async () => { await result.current.actions.handleMcpOAuthConnect("fixture"); });
  act(() => { result.current.state.setMcpOAuthCallbackUrl("https://fixture.test/callback?code=fixture"); });
  let operations!: Promise<void>[];
  act(() => { operations = [result.current.actions.handleMcpOAuthComplete(), result.current.actions.handleMcpOAuthComplete()]; });
  const calls = api.complete.mock.calls.length;
  await act(async () => { pending.resolve({ ...flow, status: "connecting" }); await Promise.all(operations); });
  unmount();
  expect(calls).toBe(1);
});

it("retains a failed cancellation for an explicit retry instead of claiming the flow stopped", async () => {
  vi.useFakeTimers();
  mockPopup();
  api.start.mockResolvedValue(flow);
  api.cancel.mockRejectedValueOnce(new Error("Fixture cancel failed")).mockResolvedValue({ ...flow, status: "cancelled" });
  const { result, unmount } = harness();
  await act(async () => { await result.current.actions.handleMcpOAuthConnect("fixture"); });
  await act(async () => { await result.current.actions.handleMcpOAuthCancel(); });
  expect(result.current.state.mcpOAuthFlow?.flow_id).toBe(flow.flow_id);
  expect(result.current.state.mcpError).toBe("Fixture cancel failed");
  await act(async () => { await result.current.actions.handleMcpOAuthCancel(); });
  expect(api.cancel).toHaveBeenCalledTimes(2);
  expect(result.current.state.mcpOAuthFlow).toBeNull();
  expect(result.current.state.mcpPresetAction).toBeNull();
  unmount();
});

it("retires an old in-flight monitor before restarting after a failed cancellation", async () => {
  vi.useFakeTimers();
  mockPopup();
  const status = deferred<McpOAuthFlowPayload>();
  api.start.mockResolvedValue(flow);
  api.status.mockReturnValueOnce(status.promise).mockResolvedValue(flow);
  api.cancel.mockRejectedValue(new Error("Fixture cancel failed"));
  const { result, unmount } = harness();
  await act(async () => { await result.current.actions.handleMcpOAuthConnect("fixture"); await vi.advanceTimersByTimeAsync(800); });
  await act(async () => { await result.current.actions.handleMcpOAuthCancel(); });
  await act(async () => { status.resolve(flow); await vi.advanceTimersByTimeAsync(800); });
  expect(api.status).toHaveBeenCalledTimes(2);
  unmount();
});

it("keeps a pending callback single-flight when cancelling it fails", async () => {
  vi.useFakeTimers();
  mockPopup();
  api.start.mockResolvedValue(flow);
  const pending = deferred<McpOAuthFlowPayload>();
  api.complete.mockReturnValue(pending.promise);
  api.cancel.mockRejectedValue(new Error("Fixture cancel failed"));
  const { result, unmount } = harness();
  await act(async () => { await result.current.actions.handleMcpOAuthConnect("fixture"); });
  act(() => { result.current.state.setMcpOAuthCallbackUrl("https://fixture.test/callback?code=fixture"); });
  let completion!: Promise<void>;
  act(() => { completion = result.current.actions.handleMcpOAuthComplete(); });
  await act(async () => { await result.current.actions.handleMcpOAuthCancel(); });
  let duplicate!: Promise<void>;
  act(() => { duplicate = result.current.actions.handleMcpOAuthComplete(); });
  const calls = api.complete.mock.calls.length;
  await act(async () => { pending.resolve({ ...flow, status: "connecting" }); await Promise.all([completion, duplicate]); });
  expect(calls).toBe(1);
  expect(result.current.state.mcpOAuthCompleting).toBe(false);
  unmount();
});
