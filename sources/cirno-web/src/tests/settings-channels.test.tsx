import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type {
  ChannelSetupContractField,
  CirnoFeatureInfo,
  CirnoFeaturesPayload,
} from "@/lib/types";
import { requestMutationMock, jsonResponse, settingsPayload, renderSettingsView, installSettingsViewTestHooks } from "@/tests/settings-test-utils";


function channelSetupField(
  channel: string,
  field: string,
  kind: ChannelSetupContractField["kind"] = "string",
  options: {
    required?: boolean;
    choices?: string[];
    defaultValue?: string;
  } = {},
): ChannelSetupContractField {
  return {
    key: `channels.${channel}.${field}`,
    field,
    kind,
    choices: options.choices ?? [],
    required: options.required ?? false,
    ...(options.defaultValue === undefined ? {} : { default_value: options.defaultValue }),
  };
}

function uninstalledConnectFeature(
  name: "feishu" | "weixin" | "whatsapp",
): CirnoFeatureInfo {
  const displayNames = {
    feishu: "Feishu",
    weixin: "WeChat",
    whatsapp: "WhatsApp",
  };
  return {
    name,
    display_name: displayNames[name],
    webui: "webui/index.tsx",
    type: "channel",
    enabled: false,
    configured: false,
    installed: false,
    requires_dependencies: true,
    ready: false,
    runtime_status: "stopped",
    status: "not_enabled",
    install_supported: true,
    requires_restart: true,
    ...(name === "feishu"
      ? {
          instances: [{
            id: "default",
            name: "cirno",
            enabled: false,
            runtime_status: "stopped",
            configured: false,
            config_values: {},
            configured_fields: [],
          }],
        }
      : {}),
  };
}

function catalogFeature(
  name: string,
  enabled: boolean,
  requiresDependencies = false,
): CirnoFeatureInfo {
  return {
    name,
    display_name: name,
    type: "channel",
    enabled,
    configured: enabled,
    installed: true,
    requires_dependencies: requiresDependencies,
    ready: enabled,
    status: enabled ? "enabled" : "not_enabled",
    install_supported: true,
    requires_restart: false,
  };
}

describe("Settings channels", () => {
  installSettingsViewTestHooks();

  it("shows enabled channels by default when any are enabled", async () => {
    const enabled = catalogFeature("Enabled channel", true);
    const enabledWithDependencies = catalogFeature("Enabled dependency channel", true, true);
    const disabled = catalogFeature("Disabled channel", false);
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") return jsonResponse(settingsPayload());
      if (url === "/api/settings/cirno-features") {
        return jsonResponse({ features: [enabled, enabledWithDependencies, disabled], enabled_count: 2 });
      }
      return jsonResponse({});
    }));

    renderSettingsView({ initialSection: "channels" });

    expect(await screen.findByRole("button", { name: "View Enabled channel settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View Enabled dependency channel settings" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View Disabled channel settings" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enabled" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("No installation needed")).not.toBeInTheDocument();
    expect(screen.queryByText("Requires dependencies")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByRole("button", { name: "View Disabled channel settings" })).toBeInTheDocument();
  });

  it("shows all channels by default when none are enabled", async () => {
    const first = catalogFeature("First channel", false);
    const second = catalogFeature("Second channel", false);
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") return jsonResponse(settingsPayload());
      if (url === "/api/settings/cirno-features") {
        return jsonResponse({ features: [first, second], enabled_count: 0 });
      }
      return jsonResponse({});
    }));

    renderSettingsView({ initialSection: "channels" });

    expect(await screen.findByRole("button", { name: "View First channel settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View Second channel settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows all channels by default when only the always-enabled WebUI is enabled", async () => {
    const websocket = {
      ...catalogFeature("websocket", true),
      display_name: "Cirno Web",
      capabilities: ["always_enabled"],
    };
    const disabled = catalogFeature("Disabled channel", false);
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") return jsonResponse(settingsPayload());
      if (url === "/api/settings/cirno-features") {
        return jsonResponse({ features: [websocket, disabled], enabled_count: 1 });
      }
      return jsonResponse({});
    }));

    renderSettingsView({ initialSection: "channels" });

    expect(await screen.findByText("Cirno Web")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View Disabled channel settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  });

  it("replaces the installed channel switch with an in-row restart action", async () => {
    const restart = vi.fn();
    const whatsappFeature = {
      name: "whatsapp",
      display_name: "WhatsApp",
      webui: "webui/index.tsx",
      type: "channel",
      enabled: false,
      configured: false,
      installed: false,
      requires_dependencies: true,
      ready: false,
      status: "not_enabled",
      install_supported: true,
      requires_restart: false,
    } as const;
    const weixinFeature = uninstalledConnectFeature("weixin");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/settings") return jsonResponse(settingsPayload());
        if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
        if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
        if (url === "/api/settings/cirno-features") {
          return jsonResponse({ features: [whatsappFeature, weixinFeature], enabled_count: 0 });
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response;
      }),
    );
    let finishInstall: (payload: CirnoFeaturesPayload) => void = () => {};
    requestMutationMock.mockImplementationOnce(() => new Promise((resolve) => {
      finishInstall = resolve;
    }));
    const installedPayload = {
      features: [{ ...whatsappFeature, installed: true, restart_pending: true }, weixinFeature],
      enabled_count: 0,
      requires_restart: true,
      last_action: {
        ok: true,
        message: "Installed support for channel 'whatsapp'",
        enabled: false,
      },
    };

    renderSettingsView({ initialSection: "channels", onRestart: restart });

    requestMutationMock.mockResolvedValueOnce({ status: "pending", session_id: "test-link" });
    expect(screen.queryByRole("switch", { name: "WhatsApp channel" })).not.toBeInTheDocument();
    const installationGroup = await screen.findByRole("region", { name: "Requires dependencies" });
    fireEvent.click(within(installationGroup).getByRole("button", { name: "Install WhatsApp" }));
    const secondInstall = within(installationGroup).getByRole("button", { name: "Install WeChat" });
    expect(secondInstall).toBeDisabled();
    fireEvent.click(secondInstall);
    expect(requestMutationMock).toHaveBeenCalledTimes(1);

    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.feature.enable",
        { name: "whatsapp", install_only: true },
        150_000,
      ),
    );
    finishInstall(installedPayload);
    expect(requestMutationMock).not.toHaveBeenCalledWith("settings.channel.connect.start", expect.anything(), expect.anything());
    const restartButton = await within(installationGroup).findByRole("button", { name: "Restart cirno" });
    const blockedInstallHint = within(installationGroup).getByRole("group", { name: "Install WeChat" });
    expect(secondInstall).toBeDisabled();
    await act(async () => { blockedInstallHint.focus(); });
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Restart cirno before installing another channel.");
    await userEvent.setup().keyboard("{Enter}");
    fireEvent.click(secondInstall);
    expect(requestMutationMock).toHaveBeenCalledTimes(1);
    expect(restartButton).toBeEnabled();
    await act(async () => { restartButton.focus(); });
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Restart cirno to apply updated channel support.");
    expect(screen.queryByRole("switch", { name: "WhatsApp channel" })).not.toBeInTheDocument();
    expect(restart).not.toHaveBeenCalled();
    fireEvent.click(restartButton);
    expect(restart).toHaveBeenCalledTimes(1);
    expect(requestMutationMock.mock.calls.map(([action]) => action)).toEqual([
      "settings.feature.enable",
    ]);
  });

  it("keeps a refreshed pending restart on its channel and restores switches after restart", async () => {
    let restartPending = true;
    const installed = { ...uninstalledConnectFeature("whatsapp"), installed: true };
    const other = { ...catalogFeature("Existing", false), requires_restart: true };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") {
        return jsonResponse({ ...settingsPayload(), requires_restart: restartPending });
      }
      if (url === "/api/settings/cirno-features") {
        return jsonResponse({
          features: [{ ...installed, restart_pending: restartPending }, other, uninstalledConnectFeature("weixin")],
          enabled_count: 0,
          requires_restart: restartPending,
        });
      }
      return jsonResponse({});
    }));
    renderSettingsView({ initialSection: "channels" });

    const installationGroup = await screen.findByRole("region", { name: "Requires dependencies" });
    expect(await within(installationGroup).findByRole("button", { name: "Restart cirno" })).toBeEnabled();
    expect(screen.getByRole("switch", { name: "Existing channel" })).toBeDisabled();

    restartPending = false;
    await act(async () => { fireEvent(window, new Event("focus")); });
    expect(await screen.findByRole("switch", { name: "WhatsApp channel" })).toBeEnabled();
    expect(screen.getByRole("switch", { name: "WhatsApp channel" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("switch", { name: "Existing channel" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Install WeChat" })).toBeEnabled();
  });

  it("announces an install-only failure and logs action context", async () => {
    const feature = uninstalledConnectFeature("whatsapp");
    const installError = new Error("Package install failed");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL) => {
          const url = String(input);
          if (url === "/api/settings") return jsonResponse(settingsPayload());
          if (url === "/api/settings/cli-apps") {
            return jsonResponse({ apps: [], installed_count: 0 });
          }
          if (url === "/api/settings/mcp-presets") {
            return jsonResponse({ presets: [], installed_count: 0 });
          }
          if (url === "/api/settings/cirno-features") {
            return jsonResponse({ features: [feature], enabled_count: 0 });
          }
          return { ok: false, status: 404, json: async () => ({}) } as Response;
        }),
      );
      requestMutationMock.mockRejectedValueOnce(installError);

      renderSettingsView({ initialSection: "channels" });

      fireEvent.click(await screen.findByRole("button", { name: "Install WhatsApp" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Package install failed");
      expect(screen.getByRole("button", { name: "Install WhatsApp" })).toBeEnabled();
      expect(consoleError).toHaveBeenCalledWith(
        "cirno feature action failed",
        expect.objectContaining({
          action: "enable",
          name: "whatsapp",
          installOnly: true,
          error: installError,
        }),
      );
    } finally {
      consoleError.mockRestore();
    }
  });

  it("shows an enabled channel with missing support as failed", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") return jsonResponse(settingsPayload());
      if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
      if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
      if (url === "/api/settings/cirno-features") {
        return jsonResponse({
          features: [{
            name: "matrix",
            display_name: "Matrix",
            type: "channel",
            enabled: true,
            running: false,
            runtime_status: "failed",
            runtime_error: "Channel dependencies could not be installed. Check gateway logs.",
            installed: false,
            requires_dependencies: true,
            ready: false,
            status: "missing_dependency",
            install_supported: true,
            requires_restart: true,
          }],
          enabled_count: 1,
        });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockResolvedValueOnce({
      features: [{
        name: "matrix",
        display_name: "Matrix",
        type: "channel",
        enabled: true,
        installed: true,
        requires_dependencies: true,
        ready: true,
        status: "enabled",
        install_supported: true,
        requires_restart: true,
      }],
      enabled_count: 1,
      last_action: { ok: true, message: "Enabled channel 'matrix'", enabled: true },
    });

    renderSettingsView({ initialSection: "channels" });

    expect((await screen.findAllByText("Failed")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("switch", { name: "Matrix channel" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Install Matrix" }));

    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.feature.enable",
        { name: "matrix", install_only: true },
        150_000,
      ),
    );
  });

  it("shows a configured channel as failed when its runtime did not start", async () => {
    const runtimeError = "Channel failed to start. Check gateway logs.";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/settings") return jsonResponse(settingsPayload());
        if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
        if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
        if (url === "/api/settings/cirno-features") {
          return jsonResponse({
            features: [{
              name: "matrix",
              display_name: "Matrix",
              type: "channel",
              enabled: true,
              configured: true,
              installed: true,
              ready: false,
              running: false,
              runtime_status: "failed",
              runtime_error: runtimeError,
              status: "failed",
              install_supported: true,
              requires_restart: false,
            }],
            enabled_count: 0,
          });
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response;
      }),
    );

    renderSettingsView({ initialSection: "channels" });

    fireEvent.click(await screen.findByRole("button", { name: "View Matrix settings" }));
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    expect(screen.getByText(runtimeError)).toBeInTheDocument();
    expect(screen.getByLabelText("Matrix channel")).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("renders external multi-instance channels from the shared contract", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") return jsonResponse(settingsPayload());
      if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
      if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
      if (url === "/api/settings/cirno-features") {
        return jsonResponse({
          features: [{
            name: "multiplugin",
            display_name: "Multi Plugin",
            type: "channel",
            enabled: true,
            running: true,
            runtime_status: "running",
            configured: true,
            installed: true,
            ready: true,
            status: "enabled",
            install_supported: true,
            requires_restart: false,
            setup: {
              fields: [
                channelSetupField("multiplugin", "token", "secret", { required: true }),
                channelSetupField("multiplugin", "region", "enum", {
                  choices: ["eu", "us"],
                  defaultValue: "us",
                }),
              ],
            },
            instances: [
              {
                id: "default",
                name: "Default worker",
                enabled: true,
                running: true,
                runtime_status: "running",
                configured: true,
                config_values: { "channels.multiplugin.region": "us" },
                configured_fields: ["channels.multiplugin.token"],
              },
              {
                id: "product",
                name: "Product worker",
                enabled: true,
                running: true,
                runtime_status: "running",
                configured: true,
                config_values: { "channels.multiplugin.region": "eu" },
                configured_fields: ["channels.multiplugin.token"],
              },
            ],
          }],
          enabled_count: 1,
        });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSettingsView({ initialSection: "channels" });

    fireEvent.click((await screen.findAllByRole("button", { name: /^View .+ settings$/ }))[0]);
    expect(await screen.findByText("Default worker")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Default worker instance" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("switch", { name: "Product worker instance" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    fireEvent.click(within(screen.getByText("Product worker").closest("article")!)
      .getByRole("button", { name: "Advanced" }));
    expect(screen.getByRole("radio", { name: "Eu" })).toBeChecked();
  });

  it("uses a list-to-detail navigation stack on compact screens", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/settings") return jsonResponse(settingsPayload());
        if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
        if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
        if (url === "/api/settings/cirno-features") {
          return jsonResponse({
            features: [{
              name: "email",
              display_name: "Email",
              type: "channel",
              enabled: false,
              installed: true,
              ready: false,
              status: "not_enabled",
              install_supported: true,
              requires_restart: true,
            }],
            enabled_count: 0,
          });
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response;
      }),
    );

    renderSettingsView({ initialSection: "channels" });

    const emailRow = await screen.findByRole("button", { name: "View Email settings" });
    expect(emailRow).toBeVisible();
    expect(screen.getByRole("switch", { name: "Email channel" })).toBeInTheDocument();

    fireEvent.click(emailRow);

    expect(screen.getByRole("dialog")).toHaveFocus();
    expect(within(screen.getByRole("dialog")).getByRole("heading", { name: "Email" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.getByRole("button", { name: "View Email settings" })).toBeInTheDocument();
  });

  it("shows an actionable credential guide for Telegram", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/settings") return jsonResponse(settingsPayload());
        if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
        if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
        if (url === "/api/settings/cirno-features") {
          return jsonResponse({
            features: [{
              name: "telegram",
              display_name: "Telegram",
              webui: "webui/index.ts",
              type: "channel",
              enabled: false,
              installed: true,
              ready: false,
              status: "not_enabled",
              install_supported: true,
              requires_restart: true,
            }],
            enabled_count: 0,
          });
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response;
      }),
    );

    renderSettingsView({ initialSection: "channels" });

    fireEvent.click(await screen.findByRole("button", { name: "View Telegram settings" }));
    fireEvent.pointerDown(screen.getByRole("button", { name: "Help" }), { button: 0, ctrlKey: false });
    expect(await screen.findByRole("menuitem", { name: "Open Telegram setup" })).toHaveAttribute(
      "href",
      "https://github.com/rachebtms/Cirno/blob/main/documents/configuration.md#telegram",
    );
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  });

  it("opens Web configuration while keeping the channel always enabled", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") return jsonResponse(settingsPayload());
      if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
      if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
      if (url === "/api/settings/cirno-features") {
        return jsonResponse({
          features: [{
            name: "websocket",
            display_name: "Websocket",
            capabilities: ["always_enabled"],
            webui: "webui/index.ts",
            type: "channel",
            enabled: true,
            installed: true,
            ready: true,
            status: "enabled",
            install_supported: true,
            requires_restart: true,
          }],
          enabled_count: 1,
        });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSettingsView({ initialSection: "channels" });

    const websocketName = await screen.findByText("Cirno Web");
    fireEvent.click(websocketName);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    const websocketSwitch = screen.getByRole("switch", { name: "Enable channel" });
    expect(websocketSwitch).toBeDisabled();
    expect(websocketSwitch).toHaveAttribute("aria-checked", "true");
    expect(requestMutationMock).not.toHaveBeenCalled();
  });
});
