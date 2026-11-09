import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RUNTIME_CONFIG_FIELDS, RUNTIME_CONFIG_GROUPS, type RuntimeConfigPage } from "@/features/settings/system/runtime-config-fields";
import { RuntimeConfiguration } from "@/features/settings/runtime/RuntimeConfiguration";
import { useRuntimeConfigSettings } from "@/features/settings/runtime/useRuntimeConfiguration";
import runtimeConfigKeys from "../../../cirno-server/tests/webui/fixtures/runtime-config-keys.json";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { CirnoClient } from "@/lib/cirno-client";
import { settingsPayload } from "@/tests/settings-test-utils";

const mutation = vi.fn();
function payload() {
  return { ...settingsPayload(), advanced: { ...settingsPayload().advanced, exec_max_runtime_limit: 86400 }, runtime_config: {
    "agents.defaults.timezone_mode": "auto", "agents.defaults.timezone": "UTC", "agents.defaults.dream.enabled": true,
    "agents.defaults.idle_compact_after_minutes": 15, "agents.defaults.idle_compact_percent": 5,
    "agents.defaults.idle_compact_keep_percent": 5, "tools.exec.enable": true, "tools.exec.max_runtime": 60,
    "tools.exec.allowed_env_keys": ["TERM"], "tools.exec.sandbox": "", "network.proxy": "http://localhost:8080",
    "agents.defaults.workspace": "/workspace", "agents.defaults.max_tool_iterations": 200,
  } } satisfies SettingsPayload;
}
function Harness({ page, initial = payload() }: { page: RuntimeConfigPage; initial?: SettingsPayload }) {
  const [settings, setSettings] = useState(initial);
  const client = { requestMutation: mutation } as unknown as CirnoClient;
  const state = useRuntimeConfigSettings(settings, client, setSettings);
  return <RuntimeConfiguration page={page} settings={settings} state={state} isRestarting={false} onRestart={() => {}} />;
}
beforeEach(() => { mutation.mockReset().mockImplementation(async (_method, args) => ({ ...payload(), requires_restart: true, runtime_config: { ...payload().runtime_config, ...args.values } })); });
afterEach(cleanup);

async function choose(label: string, option: string) {
  await userEvent.setup().click(screen.getByRole("button", { name: new RegExp(`${label}$`) }));
  await userEvent.setup().click(screen.getByRole("option", { name: option }));
}
function expectSave(values: Record<string, unknown>) {
  return waitFor(() => expect(mutation).toHaveBeenCalledWith("settings.runtime_config.update", { values }, 20_000));
}

describe("Runtime configuration", () => {
  it.each([
    ["shared", "Shared additional system prompt"],
    ["router", "Router additional system prompt"],
    ["worker", "Worker additional system prompt"],
  ])("automatically saves and clears the %s system addition without changing other roles", async (role, label) => {
    const path = `agents.defaults.system_prompts.${role}`;
    const initial = payload() as SettingsPayload;
    initial.runtime_config = { ...initial.runtime_config, [path]: "Existing instructions" };
    render(<Harness page="personality" initial={initial} />);
    expect(screen.getAllByRole("textbox")).toHaveLength(3);
    const editor = screen.getByRole("textbox", { name: label });
    fireEvent.change(editor, { target: { value: "New instructions\nKeep this line" } });
    await expectSave({ [path]: "New instructions\nKeep this line" });
    await waitFor(() => expect(editor).toHaveValue("New instructions\nKeep this line"));
    fireEvent.change(editor, { target: { value: "" } });
    await expectSave({ [path]: "" });
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });
  it("covers the server wire catalogue exactly once", () => {
    const paths = RUNTIME_CONFIG_FIELDS.map(field => field.path);
    expect(new Set(paths).size).toBe(paths.length);
    expect(RUNTIME_CONFIG_GROUPS.find(group => group.id === "cli")?.enabledBy).toBe("tools.cli_apps.enable");
    expect([...paths, "tools.cli_apps.enable"].sort()).toEqual([...runtimeConfigKeys].sort());
  });
  it.each([
    ["agents.defaults.idle_compact_percent", "Idle compaction trigger (%)", 30],
    ["agents.defaults.idle_compact_keep_percent", "Recent context retention (%)", 4],
  ])("saves only the edited compaction setting %s", async (path, label, value) => {
    render(<Harness page="context" />);
    fireEvent.change(screen.getByRole("spinbutton", { name: label }), { target: { value: String(value) } });
    await expectSave({ [path]: value });
  });
  it("saves the Dream switch independently", async () => {
    render(<Harness page="dream" />);
    const control = screen.getByRole("switch", { name: "Memory consolidation" });
    await userEvent.setup().click(control);
    await expectSave({ "agents.defaults.dream.enabled": false });
    expect(control).not.toBeChecked();
  });
  it.each(["bwrap", "seatbelt", ""])("saves sandbox %s and shows only its relevant fields", async value => {
    const initial = payload(); initial.runtime_config["tools.exec.sandbox"] = value ? "" : "seatbelt";
    render(<Harness page="shell" initial={initial} />);
    await choose("Command sandbox", value || "None");
    expect(Boolean(screen.queryByRole("textbox", { name: "Read-only paths" }))).toBe(Boolean(value));
    await expectSave({ "tools.exec.sandbox": value });
  });
  it("edits lists in place, preserves a failed save, and retries without losing the draft", async () => {
    mutation.mockRejectedValueOnce(new Error("Could not save list"));
    render(<Harness page="shell" />);
    const editor = screen.getByRole("textbox", { name: "Environment variables" });
    expect(editor).toHaveValue("TERM");
    fireEvent.change(editor, { target: { value: " TERM \n\n COLORTERM " } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save list");
    expect(editor).toHaveValue(" TERM \n\n COLORTERM ");
    const group = screen.getByRole("region", { name: "Shell and sandbox" });
    await userEvent.setup().click(within(group).getByRole("button", { name: "Save changes" }));
    await expectSave({ "tools.exec.allowed_env_keys": ["TERM", "COLORTERM"] });
    await waitFor(() => expect(editor).toHaveValue("TERM\nCOLORTERM"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("keeps a custom duration focused while its value passes through a preset", async () => {
    render(<Harness page="shell" />);
    const input = screen.getByRole("spinbutton", { name: "Custom runtime (seconds)" });
    const user = userEvent.setup();
    await user.clear(input); await user.type(input, "900");
    expect(input).toHaveFocus(); expect(input).toHaveValue(900);
    await user.type(input, "0"); expect(input).toHaveFocus();
    await expectSave({ "tools.exec.max_runtime": 9000 });
  });
  it.each([["24 hours", 86400], ["No time limit", 0]] as const)("saves %s in seconds", async (label, value) => {
    render(<Harness page="shell" />); await choose("Command runtime", label);
    await expectSave({ "tools.exec.max_runtime": value });
  });
  it("rejects values outside the server limit and retains them for correction", async () => {
    render(<Harness page="shell" />);
    const input = screen.getByRole("spinbutton", { name: "Custom runtime (seconds)" });
    fireEvent.change(input, { target: { value: "86401" } });
    await screen.findByRole("alert"); expect(mutation).not.toHaveBeenCalled();
    expect(input).toHaveValue(86401); expect(input).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(input, { target: { value: "17" } }); await expectSave({ "tools.exec.max_runtime": 17 });
  });
  it("keeps Save actions hidden throughout ordinary automatic saving", async () => {
    let finish!: (value: SettingsPayload) => void;
    mutation.mockImplementationOnce(() => new Promise<SettingsPayload>(resolve => { finish = resolve; }));
    render(<Harness page="shell" />);
    fireEvent.change(screen.getByRole("spinbutton", { name: "Custom runtime (seconds)" }), { target: { value: "17" } });
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    await expectSave({ "tools.exec.max_runtime": 17 });
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    await act(async () => finish({ ...payload(), runtime_config: { ...payload().runtime_config, "tools.exec.max_runtime": 17 } }));
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });
  it("accepts zero for the maximum and long default durations with no ceiling", async () => {
    const initial = payload(); initial.advanced.exec_max_runtime_limit = 0;
    render(<Harness page="shell" initial={initial} />);
    fireEvent.change(screen.getByRole("spinbutton", { name: "Custom runtime (seconds)" }), { target: { value: "172800" } });
    await expectSave({ "tools.exec.max_runtime": 172800 });
  });
  it("does not clear newer input when an earlier request finishes", async () => {
    let finish!: (value: SettingsPayload) => void;
    mutation.mockImplementationOnce(() => new Promise<SettingsPayload>(resolve => { finish = resolve; }));
    render(<Harness page="shell" />);
    const input = screen.getByRole("spinbutton", { name: "Custom runtime (seconds)" });
    fireEvent.change(input, { target: { value: "17" } }); await expectSave({ "tools.exec.max_runtime": 17 });
    expect(input).toBeEnabled(); fireEvent.change(input, { target: { value: "19" } });
    await act(async () => finish({ ...payload(), runtime_config: { ...payload().runtime_config, "tools.exec.max_runtime": 17 } }));
    expect(input).toHaveValue(19); await expectSave({ "tools.exec.max_runtime": 19 });
  });
  it("requires explicit save for the workspace path and can discard it", async () => {
    render(<Harness page="execution" />);
    const input = screen.getByRole("textbox", { name: "Default workspace" });
    fireEvent.change(input, { target: { value: "/research" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Cancel" }));
    expect(input).toHaveValue("/workspace"); expect(mutation).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "/research" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Save changes" }));
    await expectSave({ "agents.defaults.workspace": "/research" });
  });
  it("saves proxy credentials as one value while keeping them out of the address field", async () => {
    render(<Harness page="network" />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Authentication (optional)" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Username" }), { target: { value: "owner" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    expect(screen.getByRole("textbox", { name: "Shared proxy" })).toHaveValue("http://localhost:8080");
    await userEvent.setup().click(screen.getByRole("button", { name: "Save changes" }));
    await expectSave({ "network.proxy": "http://owner:secret@localhost:8080" });
  });
  it("supports manual timezone search and saves the selected zone", async () => {
    render(<Harness page="regional" />);
    await userEvent.setup().click(screen.getByRole("switch", { name: "System timezone" }));
    const input = screen.getByRole("combobox", { name: "Timezone" });
    await userEvent.setup().clear(input); await userEvent.setup().type(input, "Tokyo");
    await userEvent.setup().click(await screen.findByRole("option", { name: "Asia/Tokyo" }));
    await waitFor(() => expect(Object.assign({}, ...mutation.mock.calls.map(call => call[1].values))).toMatchObject({ "agents.defaults.timezone_mode": "manual", "agents.defaults.timezone": "Asia/Tokyo" }));
  });
});
