import { screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/contracts/settings";
import {
  settingsPayload,
  renderSettingsView,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";

describe("Settings models", () => {
  installSettingsViewTestHooks();
  it("starts fresh users with an empty preset list instead of legacy conversion", async () => {
    const base = settingsPayload();
    const freshPayload: SettingsPayload = {
      ...base,
      agent: {
        ...base.agent,
        model: "anthropic/claude-opus-4-5",
        provider: "auto",
        resolved_provider: null,
        has_api_key: false,
        model_preset: "default",
      },
      model_presets: [
        {
          ...base.model_presets[0],
          id: "default",
          name: "default",

          active: true,
          is_default: true,
          model: "anthropic/claude-opus-4-5",
          provider: "auto",
          resolved_provider: null,
        },
      ],
      model_call_order: [],
      model_call_order_editable: false,

      providers: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );

    renderSettingsView({ initialSection: "models", initialSettings: freshPayload });

    expect(await screen.findByRole("button", { name: "New preset" })).toBeInTheDocument();
  });

  it("does not expose the synthetic default configuration as a WebUI preset", async () => {
    const base = settingsPayload();
    const payload: SettingsPayload = {
      ...base,
      agent: {
        ...base.agent,
        model: "MiniMax-M3",
        provider: "minimax_anthropic",
        resolved_provider: "minimax_anthropic",
        model_preset: "fast",
      },
      model_presets: [
        {
          ...base.model_presets[0],
          id: "default",
          name: "default",

          active: false,
          is_default: true,
          model: "openai-codex/gpt-5.5",
          provider: "openai_codex",
          resolved_provider: "openai_codex",
        },
        {
          ...base.model_presets[0],
          id: "fast",
          name: "fast",

          active: true,
          is_default: false,
          model: "MiniMax-M3",
          provider: "minimax_anthropic",
          resolved_provider: "minimax_anthropic",
        },
      ],
      model_call_order: ["fast"],
      providers: [
        {
          id: "openai_codex",
          name: "OpenAI Codex",
          configured: true,
          auth_type: "oauth",
          api_key_required: false,
          api_key_hint: null,
          api_base: null,
          default_api_base: null,
          oauth_account: "acct-test",
          oauth_expires_at: null,
          oauth_login_supported: true,
        },
        {
          id: "minimax_anthropic",
          name: "MiniMax (Anthropic)",
          configured: true,
          auth_type: "api_key",
          api_key_required: true,
          api_key_hint: "sk-...",
          api_base: "https://api.minimax.io/anthropic",
          default_api_base: "https://api.minimax.io/anthropic",
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );

    renderSettingsView({ initialSection: "models", initialSettings: payload });

    expect(screen.getAllByText("fast").length).toBeGreaterThan(0);
  });

  it("does not expose the synthetic default preset in the overview summary", async () => {
    const base = settingsPayload();
    const payload: SettingsPayload = {
      ...base,
      agent: {
        ...base.agent,
        model_preset: "default",
      },
      model_presets: [
        {
          ...base.model_presets[0],
          id: "default",
          name: "default",

          is_default: true,
        },
      ],
      model_call_order: [],
      model_call_order_editable: false,
      providers: [
        {
          id: "openai",
          name: "openai",
          configured: true,
          api_key_required: true,
          api_key_hint: "sk-...",
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );

    renderSettingsView({ initialSection: "overview", initialSettings: payload });

    expect(await screen.findByText("openai/gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
  });
});
