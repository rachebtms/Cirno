import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import {
  requestMutationMock,
  jsonResponse,
  settingsPayload,
  renderSettingsView,
  openPopover,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { openModelPicker, returnToPresetEditor, presetSaveButton } from "./helpers/settings-models";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("creates presets in a dialog and can cancel", async () => {
    const payload = settingsPayload();
    payload.providers = [{ id: "openai", name: "OpenAI", configured: true }];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/v0/settings") return jsonResponse(payload);
        if (url === "/v0/settings/cli-apps") {
          return jsonResponse({ apps: [], installed_count: 0 });
        }
        if (url === "/v0/settings/mcp-presets") {
          return jsonResponse({ presets: [], installed_count: 0 });
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response;
      }),
    );

    renderSettingsView({ initialSection: "models" });

    const createButton = await screen.findByRole("button", { name: "New preset" });
    const previousPointerEvents = document.body.style.pointerEvents;
    await openPopover(createButton);

    expect(screen.getByRole("dialog", { name: "New preset" })).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toContainElement(
      document.querySelector<HTMLElement>(".model-preset-dialog")!,
    );
    expect(screen.getByRole("textbox", { name: /^Preset name/ })).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    expect(screen.getByText("Temperature")).toBeInTheDocument();
    await returnToPresetEditor();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(document.body.style.pointerEvents).toBe(previousPointerEvents));
    await waitFor(() => expect(createButton).toHaveFocus());

    fireEvent.click(screen.getByRole("button", { name: "New preset" }));
    const nameInput = await screen.findByRole("textbox", { name: /^Preset name/ });
    expect(nameInput).toHaveValue("");
    expect(nameInput).toHaveAttribute("placeholder", "e.g. Fast writing");

    const modelSearch = await openModelPicker();
    fireEvent.change(modelSearch, { target: { value: "openai/gpt-4o-mini" } });
    fireEvent.keyDown(modelSearch, { key: "Enter" });

    expect(nameInput).toHaveValue("gpt-4o-mini");
    expect(presetSaveButton()).toBeEnabled();

    fireEvent.change(nameInput, { target: { value: "Writer" } });
    const nextModelSearch = await openModelPicker();
    fireEvent.change(nextModelSearch, { target: { value: "openai/gpt-4.1-mini" } });
    fireEvent.keyDown(nextModelSearch, { key: "Enter" });
    expect(nameInput).toHaveValue("Writer");
  });

  it.each([
    { context: 1_000_000, manual: undefined, expected: "1m" },
    { context: 1_000_000, manual: "256k", expected: "256k" },
    { context: null, manual: undefined, expected: "200k" },
  ])(
    "initializes new preset context from the selected model while preserving overrides ($expected)",
    async ({ context, manual, expected }) => {
      const payload = settingsPayload();
      payload.model_presets[0].provider = "openai";
      payload.model_presets[0].context_window_tokens = 200_000;
      payload.providers = [{ id: "openai", name: "OpenAI", configured: true }];
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL) => {
          const url = String(input);
          if (url === "/v0/settings") return new Promise<Response>(() => {});
          if (url.includes("/provider-models?"))
            return jsonResponse({
              provider: "openai",
              status: "available",
              catalog_kind: "official",
              models: [
                {
                  id: "catalog-model",
                  context_window: context,
                  reasoning_efforts: ["low", "high"],
                },
              ],
              model_count: 1,
            });
          return jsonResponse(payload);
        }),
      );
      requestMutationMock.mockResolvedValue(payload);
      renderSettingsView({ initialSection: "models", initialSettings: payload });
      fireEvent.click(screen.getByRole("button", { name: "New preset" }));
      fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
      if (manual)
        fireEvent.change(screen.getByRole("textbox", { name: "Context window" }), {
          target: { value: manual },
        });
      await returnToPresetEditor();
      await openModelPicker();
      fireEvent.click(await screen.findByRole("option", { name: /catalog-model/ }));
      fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
      await waitFor(() =>
        expect(screen.getByRole("textbox", { name: "Context window" })).toHaveValue(expected),
      );
      await returnToPresetEditor();
      fireEvent.click(presetSaveButton());
      await waitFor(() =>
        expect(requestMutationMock).toHaveBeenCalledWith(
          "settings.model_configuration.create",
          expect.objectContaining({ context_window_tokens: manual ? 256000 : (context ?? 200000) }),
          expect.any(Number),
        ),
      );
    },
  );
});
