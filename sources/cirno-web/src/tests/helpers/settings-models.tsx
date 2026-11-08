import { fireEvent, screen, within } from "@testing-library/react";
import { vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { settingsPayload, openPopover } from "@/tests/settings-test-utils";

export function settingsPayloadWithBackup() {
  const base = settingsPayload();
  const backupPreset = {
    ...base.model_presets[0],
    id: "backup",
    name: "backup",
    active: false,
    model: "anthropic/claude-sonnet-4",
    provider: "anthropic",
    resolved_provider: "anthropic",
  };
  return {
    backupPreset,
    payload: {
      ...base,
      model_presets: [base.model_presets[0], backupPreset],
      model_call_order: ["primary", "backup"],
      providers: [
        {
          id: "openai",
          name: "OpenAI",
          configured: true,
        },
        {
          id: "anthropic",
          name: "Anthropic",
          configured: true,
        },
      ],
    } satisfies SettingsPayload,
  };
}

export function autoDynamicProviderPayload(options: {
  configured: boolean;
  hasApiKey: boolean;
  apiBase: string | null;
  apiKeyHint: string | null;
}): SettingsPayload {
  const base = settingsPayload();
  return {
    ...base,
    agent: {
      ...base.agent,
      model: "companyProxy/gpt-4o",
      provider: "companyProxy",
      resolved_provider: "companyProxy",
      has_api_key: options.hasApiKey,
    },
    model_presets: [
      {
        ...base.model_presets[0],
        model: "companyProxy/gpt-4o",
        provider: "auto",
        resolved_provider: "companyProxy",
      },
    ],
    providers: [
      {
        id: "companyProxy",
        name: "Company Proxy",
        configured: options.configured,
        auth_type: "api_key",
        api_key_required: false,
        api_key_hint: options.apiKeyHint,
        api_base: options.apiBase,
        default_api_base: null,
      },
    ],
  };
}

export async function togglePresetEditor(name = "primary") {
  const row = await screen.findByTestId(`model-call-order-row-${name}`);
  fireEvent.click(row.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!);
}

export function mockPresetRowLayout() {
  let top = 100;
  return screen.getAllByTestId(/^model-call-order-row-/).map((row, index) => {
    const rect = DOMRect.fromRect({ x: 0, y: top, width: 800, height: index === 0 ? 240 : 80 });
    vi.spyOn(row.closest('[role="listitem"]')!, "getBoundingClientRect").mockReturnValue(rect);
    vi.spyOn(row.closest("[data-preset-sort-surface]")!, "getBoundingClientRect").mockReturnValue(
      rect,
    );
    top += rect.height + (index === 0 ? 72 : 8);
    return rect.top + rect.height / 2;
  });
}

export async function openModelPicker() {
  const input = await screen.findByRole("combobox", { name: "Model" });
  await openPopover(screen.getByRole("button", { name: "Show suggestions Model" }));
  return input;
}

export async function returnToPresetEditor() {
  const advanced = screen.getByRole("button", { name: "Advanced options" });
  if (advanced.getAttribute("aria-expanded") === "true") await openPopover(advanced);
}

export function presetSaveButton() {
  return within(screen.getByRole("dialog")).getByRole("button", { name: "Save" });
}

export async function openPresetAdvancedOptions() {
  await togglePresetEditor();
  fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
}
