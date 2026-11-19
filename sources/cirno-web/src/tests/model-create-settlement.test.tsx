import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { installSettingsViewTestHooks, renderSettingsView, requestMutationMock } from "./settings-test-utils";
import { openModelPicker, presetSaveButton, settingsPayloadWithBackup, togglePresetEditor } from "./helpers/settings-models";

installSettingsViewTestHooks();

function createdPayload(payload: SettingsPayload) {
  return { ...payload, created_model_preset: "writer", model_presets: [
    ...payload.model_presets, { ...payload.model_presets[0]!, id: "writer", name: "Writer", provider: "openai", model: "openai/gpt-4o-mini" },
  ] };
}

async function submitDraft() {
  fireEvent.click(screen.getByRole("button", { name: "New preset" }));
  fireEvent.change(screen.getByRole("textbox", { name: /^Preset name/ }), { target: { value: "Writer" } });
  const model = await openModelPicker();
  fireEvent.change(model, { target: { value: "openai/gpt-4o-mini" } });
  fireEvent.keyDown(model, { key: "Enter" });
  await act(async () => { fireEvent.submit(presetSaveButton().closest("form")!); });
}

it("retains a committed preset after an order conflict and retries enabling it without recreating", async () => {
  const { payload } = settingsPayloadWithBackup(), created = createdPayload(payload);
  requestMutationMock.mockResolvedValueOnce(created)
    .mockRejectedValueOnce(new ApiError(409, "Order changed"))
    .mockResolvedValueOnce({ ...created, model_call_order: ["primary", "backup", "writer"] });
  renderSettingsView({ initialSection: "models", initialSettings: payload });
  await submitDraft();
  const editor = screen.getByRole("dialog", { name: "Writer" });
  expect(within(editor).getByLabelText(/^Preset name/)).not.toHaveAttribute("aria-invalid", "true");
  expect(await within(editor).findByRole("alert")).toHaveTextContent(/Preset created.*call order.*Order changed/);
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  fireEvent.click(within(editor).getByRole("button", { name: "Close" }));
  const row = screen.getByTestId("model-call-order-row-writer");
  expect(screen.getByRole("alert")).toHaveTextContent(/Preset created/);
  fireEvent.click(within(row).getByRole("switch", { name: "Enable preset" }));
  await waitFor(() => expect(within(screen.getByTestId("model-call-order-row-writer")).getByRole("switch", { name: "Disable preset" })).toBeChecked());
  expect(screen.queryAllByRole("alert")).toHaveLength(0);
  expect(requestMutationMock.mock.calls.map(([action]) => action)).toEqual([
    "settings.model_configuration.create", "settings.model_call_order.update", "settings.model_call_order.update",
  ]);
});

it("extends the order returned by creation rather than replacing a newer server order", async () => {
  const { payload } = settingsPayloadWithBackup(), created = createdPayload(payload);
  created.model_call_order = ["backup", "primary", "backup"];
  requestMutationMock.mockResolvedValueOnce(created)
    .mockResolvedValueOnce({ ...created, model_call_order: [...created.model_call_order, "writer"] });
  renderSettingsView({ initialSection: "models", initialSettings: payload });
  await submitDraft();
  expect(requestMutationMock).toHaveBeenLastCalledWith("settings.model_call_order.update",
    { order: ["backup", "primary", "backup", "writer"] }, 20_000);
});

it("does not republish an order that already enabled the created preset", async () => {
  const { payload } = settingsPayloadWithBackup(), created = createdPayload(payload);
  payload.model_presets = [];
  payload.model_call_order = [];
  created.model_presets = [created.model_presets.at(-1)!];
  created.model_call_order = ["writer"];
  requestMutationMock.mockResolvedValue(created);
  renderSettingsView({ initialSection: "models", initialSettings: payload });
  await submitDraft();
  expect(requestMutationMock.mock.calls.map(([action]) => action)).toEqual(["settings.model_configuration.create"]);
  expect(within(screen.getByTestId("model-call-order-row-writer")).getByRole("switch", { name: "Disable preset" })).toBeChecked();
});

it.each([false, true])("initializes all per-model defaults from the primary preset after inspecting a backup (overrides: %s)", async overrides => {
  const { payload } = settingsPayloadWithBackup();
  Object.assign(payload.model_presets[0]!, { reasoning_history: overrides ? "preserve" : "auto",
    idle_compact_percent: overrides ? 40 : null, idle_compact_keep_percent: overrides ? 10 : null });
  Object.assign(payload.model_presets[1]!, { reasoning_history: "omit", idle_compact_percent: 80, idle_compact_keep_percent: 20 });
  requestMutationMock.mockResolvedValueOnce(createdPayload(payload))
    .mockResolvedValueOnce({ ...createdPayload(payload), model_call_order: ["primary", "backup", "writer"] });
  renderSettingsView({ initialSection: "models", initialSettings: payload });
  await togglePresetEditor("backup");
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  await submitDraft();
  expect(requestMutationMock).toHaveBeenCalledWith("settings.model_configuration.create", expect.objectContaining({
    reasoning_history: overrides ? "preserve" : "auto",
    idle_compact_percent: overrides ? 40 : "", idle_compact_keep_percent: overrides ? 10 : "",
  }), 20_000);
});

it("shows a creation error once in its editor", async () => {
  const { payload } = settingsPayloadWithBackup();
  requestMutationMock.mockRejectedValueOnce(new Error("Create failed"));
  renderSettingsView({ initialSection: "models", initialSettings: payload });
  await submitDraft();
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(within(screen.getByRole("dialog", { name: "New preset" })).getByRole("alert")).toHaveTextContent("Create failed");
});
