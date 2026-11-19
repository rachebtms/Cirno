import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ModelsSettings } from "@/features/settings/models/ModelsSettings";
import { agentDraftFromPayload } from "@/features/settings/models/modelDraft";
import { useEditCompletion } from "@/features/settings/shared/useEditCompletion";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import { settingsPayload } from "@/tests/settings-test-utils";
import { togglePresetEditor } from "./helpers/settings-models";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("binds parameter drafts to the preset selected in the real model editor", async () => {
  const settings = settingsPayload();
  settings.providers = [{ id: "openai", name: "OpenAI", configured: true, advanced_fields: ["extra_headers"] }];
  settings.model_presets = ["primary", "backup"].map(id => ({ ...settings.model_presets[0]!, id, name: id, provider: "openai" }));
  settings.model_call_order = ["primary", "backup"];
  settings.model_request_overrides_supported = true;
  const save = vi.fn(async () => {}), noChange = vi.fn();
  const client = { requestMutation: vi.fn() } as unknown as CirnoClient;
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ models: [], status: "unsupported" }) })));
  function Page({ owner }: { owner: string }) {
    const form = agentDraftFromPayload(settings, owner);
    const editCompletion = useEditCompletion(form, false, noChange, false, owner);
    return <ClientProvider client={client} token="fixture"><ModelsSettings
      editCompletion={editCompletion} token="fixture" form={form} setForm={noChange}
      editingPresetId={owner} presetNameError={null} settings={settings} dirty={false}
      creating={false} creatingSaving={false} callOrder={settings.model_call_order!}
      saving={false} orderSaving={false} showBrandLogos={false} providerSaving={null}
      onChangeCallOrder={noChange} onProviderOAuthLogin={noChange} onAddProvider={noChange}
      onConfigureProvider={noChange} onManageProviders={noChange} onSave={noChange}
      onSaveRequestSettings={save} onBeginCreate={noChange} onCancelCreate={noChange}
      onClearPresetNameError={noChange} onSelectConfiguration={noChange} onDeleteConfiguration={noChange}
    /></ClientProvider>;
  }
  const { rerender } = render(<Page owner="primary" />);
  await togglePresetEditor();
  fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
  fireEvent.change(await screen.findByRole("textbox", { name: "Headers" }), {
    target: { value: '{"Authorization":"primary-only-secret"}' },
  });
  rerender(<Page owner="backup" />);
  await waitFor(() => expect(screen.getByRole("dialog", { name: "backup" })).toBeVisible());
  const advanced = screen.getByRole("button", { name: "Advanced options" });
  if (advanced.getAttribute("aria-expanded") !== "true") fireEvent.click(advanced);
  expect(await screen.findByRole("textbox", { name: "Headers" })).toHaveValue("");
  expect(save).not.toHaveBeenCalled();
});
