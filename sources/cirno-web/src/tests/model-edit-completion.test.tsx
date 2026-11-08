import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { installSettingsViewTestHooks, renderSettingsView, requestMutationMock, settingsPayload } from "@/tests/settings-test-utils";
import { togglePresetEditor } from "./helpers/settings-models";
function deferred<T>() {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((done) => { resolve = done; });
    return { promise, resolve };
}
describe("model editor completion boundaries", () => {
    installSettingsViewTestHooks();
    it("retains a focused draft through a pause and a failed close, then retries without losing it", async () => {
        const payload = settingsPayload();
        const saved = {
            ...payload,
            model_presets: payload.model_presets.map((preset) => ({ ...preset, name: "Renamed" })),
            model_call_order: ["primary"],
        };
        requestMutationMock.mockRejectedValueOnce(new Error("Save failed")).mockResolvedValueOnce(saved);
        renderSettingsView({ initialSection: "models", initialSettings: payload });
        await togglePresetEditor();
        const name = await screen.findByRole("textbox", { name: "Preset name" });
        fireEvent.focus(name);
        fireEvent.change(name, { target: { value: "Renamed" } });
        await act(async () => { await new Promise((done) => setTimeout(done, 700)); });
        expect(requestMutationMock).not.toHaveBeenCalled();
        fireEvent.blur(name);
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        await waitFor(() => expect(requestMutationMock).toHaveBeenCalledTimes(1));
        await act(async () => { });
        expect(screen.getByRole("textbox", { name: "Preset name" })).toHaveValue("Renamed");
        expect(within(screen.getByRole("dialog")).getByRole("alert")).toHaveTextContent("Save failed");
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(requestMutationMock).toHaveBeenCalledTimes(2);
    });
    it("keeps a failed context-window save visible in the advanced dialog", async () => {
        const payload = settingsPayload();
        requestMutationMock.mockRejectedValueOnce(new Error("Save failed"));
        renderSettingsView({ initialSection: "models", initialSettings: payload });
        await togglePresetEditor();
        fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
        const context = screen.getByRole("textbox", { name: "Context window" });
        fireEvent.focus(context);
        fireEvent.change(context, { target: { value: "500k" } });
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        await waitFor(() => expect(requestMutationMock).toHaveBeenCalledTimes(1));
        expect(within(screen.getByRole("dialog", { name: "primary" })).getByRole("alert")).toHaveTextContent("Save failed");
        expect(context).toHaveValue("500k");
    });
    it("does not let an unchanged reasoning selection complete subsequent typing", async () => {
        renderSettingsView({ initialSection: "models", initialSettings: settingsPayload() });
        await togglePresetEditor();
        const effort = await screen.findByRole("combobox", { name: "Reasoning effort" });
        fireEvent.click(screen.getByRole("button", { name: "Show suggestions Reasoning effort" }));
        fireEvent.click(await screen.findByRole("option", { name: "Default" }));
        fireEvent.focus(effort);
        fireEvent.change(effort, { target: { value: "m" } });
        await act(async () => { });
        expect(effort).toHaveValue("m");
        expect(requestMutationMock).not.toHaveBeenCalled();
        fireEvent.blur(effort);
        await waitFor(() => expect(requestMutationMock).toHaveBeenCalledWith("settings.model_configuration.update", { id: "primary", reasoning_effort: "m" }, 20000));
    });
    it("queues a rename back to its original name using the latest catalog", async () => {
        const payload = settingsPayload();
        const first = deferred<ReturnType<typeof settingsPayload>>();
        requestMutationMock.mockReturnValueOnce(first.promise).mockResolvedValueOnce(payload);
        renderSettingsView({ initialSection: "models", initialSettings: payload });
        await togglePresetEditor();
        const name = await screen.findByRole("textbox", { name: "Preset name" });
        fireEvent.focus(name);
        fireEvent.change(name, { target: { value: "First" } });
        fireEvent.blur(name);
        await waitFor(() => expect(requestMutationMock).toHaveBeenCalledTimes(1));
        fireEvent.focus(name);
        fireEvent.change(name, { target: { value: "primary" } });
        fireEvent.blur(name);
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        await act(async () => first.resolve({
            ...payload, model_presets: payload.model_presets.map((preset) => ({ ...preset, name: "First" })),
            model_call_order: ["primary"],
        }));
        await waitFor(() => expect(requestMutationMock).toHaveBeenLastCalledWith("settings.model_configuration.update", { id: "primary", name: "primary" }, 20000));
        await waitFor(() => expect(screen.getByRole("button", { name: "Close" })).toBeEnabled());
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(screen.getByTestId("model-call-order-row-primary")).toBeInTheDocument();
        expect(requestMutationMock).toHaveBeenCalledTimes(2);
    });
    it("preserves and queues a later rename while the previous rename response is pending", async () => {
        const payload = settingsPayload();
        const first = deferred<ReturnType<typeof settingsPayload>>();
        requestMutationMock.mockReturnValueOnce(first.promise).mockImplementationOnce(async (_action, args) => ({
            ...payload,
            model_presets: payload.model_presets.map((preset) => ({ ...preset, name: args.name })),
            model_call_order: ["primary"],
        }));
        renderSettingsView({ initialSection: "models", initialSettings: payload });
        await togglePresetEditor();
        const name = await screen.findByRole("textbox", { name: "Preset name" });
        fireEvent.focus(name);
        fireEvent.change(name, { target: { value: "First" } });
        fireEvent.blur(name);
        await waitFor(() => expect(requestMutationMock).toHaveBeenCalledTimes(1));
        expect(screen.getByRole("button", { name: "Close" })).toBeDisabled();
        fireEvent.focus(name);
        fireEvent.change(name, { target: { value: "Latest" } });
        fireEvent.blur(name);
        await act(async () => first.resolve({
            ...payload,
            model_presets: payload.model_presets.map((preset) => ({ ...preset, name: "First" })),
            model_call_order: ["primary"],
        }));
        await waitFor(() => expect(requestMutationMock).toHaveBeenLastCalledWith("settings.model_configuration.update", { id: "primary", name: "Latest" }, 20000));
        await waitFor(() => expect(screen.getByRole("button", { name: "Close" })).toBeEnabled());
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(screen.getByTestId("model-call-order-row-primary")).toBeInTheDocument();
    });
});
