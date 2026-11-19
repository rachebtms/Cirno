import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { installSettingsViewTestHooks, renderSettingsView, requestMutationMock } from "@/tests/settings-test-utils";
import { openModelPicker, presetSaveButton, settingsPayloadWithBackup } from "./helpers/settings-models";

installSettingsViewTestHooks();

function createdPayload(payload: SettingsPayload) {
  return { ...payload, created_model_preset: "writer", model_presets: [
    ...payload.model_presets, { ...payload.model_presets[0]!, id: "writer", name: "Writer" },
  ] };
}
async function openDraft(payload: SettingsPayload) {
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
  renderSettingsView({ initialSection: "models", initialSettings: payload });
  fireEvent.click(screen.getByRole("button", { name: "New preset" }));
  fireEvent.change(screen.getByRole("textbox", { name: /^Preset name/ }), { target: { value: "Writer" } });
  const model = await openModelPicker();
  fireEvent.change(model, { target: { value: "openai/gpt-4o-mini" } });
  fireEvent.keyDown(model, { key: "Enter" });
}

it.each([false, true])("admits one preset creation and one order update before the pending render (probe: %s)", async testing => {
  const { payload } = settingsPayloadWithBackup(), created = createdPayload(payload);
  payload.model_capability_testing_supported = testing;
  let resolve!: (value: SettingsPayload) => void;
  const pending = new Promise<SettingsPayload>(done => { resolve = done; });
  requestMutationMock.mockImplementation(action => action === "instance.action" ? Promise.resolve({})
    : action === "settings.model_configuration.create" ? pending
      : Promise.resolve({ ...created, model_call_order: ["primary", "backup", "writer"] }));
  await openDraft(payload);
  const form = presetSaveButton().closest("form")!;
  act(() => { fireEvent.submit(form); fireEvent.submit(form); });
  await act(async () => { resolve(created); });
  await waitFor(() => expect(screen.getByRole("textbox", { name: /^Preset name/ })).toBeEnabled());
  expect(requestMutationMock.mock.calls.filter(([action]) => action === "settings.model_configuration.create")).toHaveLength(1);
  expect(requestMutationMock.mock.calls.filter(([action]) => action === "settings.model_call_order.update")).toHaveLength(1);
  expect(requestMutationMock.mock.calls.filter(([action, values]) => action === "instance.action" && values.action === "models.probe")).toHaveLength(testing ? 1 : 0);
});

it("releases creation admission after failure so the same draft can be retried", async () => {
  const { payload } = settingsPayloadWithBackup(), created = createdPayload(payload);
  requestMutationMock.mockRejectedValueOnce(new Error("Create failed"))
    .mockResolvedValueOnce(created)
    .mockResolvedValueOnce({ ...created, model_call_order: ["primary", "backup", "writer"] });
  await openDraft(payload);
  fireEvent.submit(presetSaveButton().closest("form")!);
  expect(await within(screen.getByRole("dialog", { name: "New preset" })).findByRole("alert")).toHaveTextContent("Create failed");
  expect(screen.getByRole("textbox", { name: /^Preset name/ })).toHaveValue("Writer");
  await act(async () => { fireEvent.submit(presetSaveButton().closest("form")!); });
  await waitFor(() => expect(screen.queryAllByRole("alert")).toHaveLength(0));
  expect(requestMutationMock.mock.calls.filter(([action]) => action === "settings.model_configuration.create")).toHaveLength(2);
  expect(screen.getByTestId("model-call-order-row-writer")).toBeInTheDocument();
});
