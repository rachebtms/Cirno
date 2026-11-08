import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { installedMcpPresetsFromPayload } from "@/lib/mcp-preset-events";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import { requestMutationMock, jsonResponse, settingsPayload, renderSettingsView, installSettingsViewTestHooks } from "@/tests/settings-test-utils";

const installedAnyGen = {
  name: "anygen",
  display_name: "AnyGen",
  category: "generation",
  description: "Generate docs, slides, websites and more via AnyGen cloud API",
  requires: "ANYGEN_API_KEY",
  source: "harness",
  entry_point: "cli-anything-anygen",
  install_supported: true,
  installed: true,
  available: true,
  status: "installed",
  logo_url: "https://www.google.com/s2/favicons?domain=anygen.io&sz=64",
  brand_color: "#111827",
  skill_installed: true,
};

const agentPlugin = {
  name: "plugin-computer-use",
  display_name: "Computer Use",
  category: "Plugin",
  description: "Control the desktop with a live preview.",
  docs_url: "",
  note: "",
  requires: "screen-recording, accessibility",
  transport: "stdio",
  install_supported: false,
  installed: true,
  configured: true,
  enabled: false,
  available: false,
  status: "disabled",
  required_fields: [],
  connection_summary: "",
  source: "agent-plugin",
} satisfies McpPresetInfo;

describe("Installed catalog settings", () => {
  installSettingsViewTestHooks();

  it("keeps enabled Agent Plugins out of MCP composer attachments", () => {
    const enabled = { ...agentPlugin, enabled: true, available: true, status: "enabled" };
    expect(installedMcpPresetsFromPayload({ presets: [enabled], installed_count: 1 })).toEqual([]);
  });

  it("enables and disables an installed Agent Plugin explicitly", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(settingsPayload());
      if (url === "/v0/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
      if (url === "/v0/settings/mcp-presets") {
        return jsonResponse({ presets: [agentPlugin], installed_count: 0 });
      }
      return jsonResponse({});
    }));
    requestMutationMock.mockImplementation(async (action: string) => {
      const enabled = action.endsWith(".enable");
      return {
        presets: [{
          ...agentPlugin,
          enabled,
          available: enabled,
          status: enabled ? "enabled" : "disabled",
        }],
        installed_count: Number(enabled),
      };
    });

    renderSettingsView();

    const plugin = await screen.findByRole("article", { name: "Computer Use" });
    expect(within(plugin).getByText(/Control the desktop/)).toBeVisible();
    const toggle = within(plugin).getByRole("switch", { name: "Computer Use" });
    const user = userEvent.setup();
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    await waitFor(() => expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.mcp.enable", { name: "plugin-computer-use" }, 20_000,
    ));
    await waitFor(() => expect(toggle).toBeChecked());
    await user.click(toggle);
    await waitFor(() => expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.mcp.disable", { name: "plugin-computer-use" }, 20_000,
    ));
    await waitFor(() => expect(toggle).not.toBeChecked());
  });

  it("uninstalls an installed CLI app through its native action menu", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") {
        return jsonResponse(settingsPayload());
      }
      if (url === "/v0/settings/cli-apps") {
        return jsonResponse({
          apps: [installedAnyGen],
          installed_count: 1,
          catalog_updated_at: "2026-04-18",
        });
      }
      if (url === "/v0/settings/mcp-presets") {
        return jsonResponse({ presets: [], installed_count: 0 });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockResolvedValueOnce({
      apps: [{ ...installedAnyGen, installed: false, status: "available" }],
      installed_count: 0,
      catalog_updated_at: "2026-04-18",
      last_action: {
        ok: true,
        message: "Uninstalled CLI for AnyGen.",
        still_available: false,
      },
    });

    renderSettingsView();

    expect(await screen.findByText("AnyGen")).toBeInTheDocument();
    const user = userEvent.setup();
    const card = screen.getByRole("article", { name: "AnyGen" });
    await user.click(within(card).getByRole("button", { name: "More actions: AnyGen" }));
    await user.click(await screen.findByRole("menuitem", { name: "Uninstall app" }));

    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.cli_app.uninstall",
        { name: "anygen" },
        20_000,
      ),
    );
    expect(await screen.findByText("Uninstalled CLI for AnyGen.")).toBeInTheDocument();

    const notice = screen.getByText("Uninstalled CLI for AnyGen.").closest('[role="status"]')!;
    await user.click(within(notice as HTMLElement).getByRole("button", { name: "Close" }));
    expect(screen.queryByText("Uninstalled CLI for AnyGen.")).not.toBeInTheDocument();

  });

  it("keeps runtime dependencies out of Apps and explains chat mentions", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(settingsPayload());
      if (url === "/v0/settings/cli-apps") {
        return jsonResponse({
          apps: [{ ...installedAnyGen, installed: false, status: "available" }],
          installed_count: 0,
        });
      }
      if (url === "/v0/settings/mcp-presets") {
        return jsonResponse({ presets: [], installed_count: 0 });
      }
      if (url === "/v0/settings/cirno-features") {
        return jsonResponse({
          features: [
            {
              name: "api",
              display_name: "Api",
              type: "feature",
              enabled: true,
              installed: true,
              ready: true,
              status: "enabled",
              install_supported: true,
              requires_restart: true,
            },
          ],
          enabled_count: 1,
        });
      }
      return jsonResponse({});
    }));

    renderSettingsView({ initialSection: "apps" });

    expect(await screen.findByText("AnyGen")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tools & CLI Apps" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "MCP" })).toBeInTheDocument();
  });
});
