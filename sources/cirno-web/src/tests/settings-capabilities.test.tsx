import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { SettingsPayload } from "@/lib/types";
import { requestMutationMock, jsonResponse, settingsPayload, renderSettingsView, installSettingsViewTestHooks } from "@/tests/settings-test-utils";


describe("Settings capabilities", () => {
  installSettingsViewTestHooks();

  it("keeps other capability switches stable while saving and queues their edits", async () => {
    const payload = { ...settingsPayload(), runtime_config: {
      "tools.web.enable": true, "agents.defaults.dream.enabled": true,
    } };
    const memorySaved = { ...payload, runtime_config: { ...payload.runtime_config, "agents.defaults.dream.enabled": false } };
    let finishMemory!: (value: SettingsPayload) => void;
    requestMutationMock.mockImplementationOnce(() => new Promise<SettingsPayload>((resolve) => { finishMemory = resolve; }))
      .mockResolvedValueOnce({ ...memorySaved, runtime_config: { ...memorySaved.runtime_config, "tools.web.enable": false } });
    renderSettingsView({ initialSection: "capabilities", initialSettings: payload });
    const memory = screen.getByRole("switch", { name: "Memory consolidation" });
    const web = screen.getByRole("switch", { name: "Web access" });
    expect(memory).toHaveClass("h-5", "w-9", "bg-foreground");
    expect(web).toHaveClass("h-5", "w-9", "bg-foreground");
    const webStyle = web.className;
    fireEvent.click(memory);
    await waitFor(() => expect(memory).toBeDisabled());
    expect(web).toBeEnabled();
    expect(web).toBeChecked();
    expect(web.className).toBe(webStyle);
    fireEvent.click(web);
    expect(web).not.toBeChecked();
    expect(web).toHaveClass("bg-muted-foreground/25");
    await act(async () => finishMemory(memorySaved));
    await waitFor(() => expect(requestMutationMock).toHaveBeenLastCalledWith(
      "settings.runtime_config.update", { values: { "tools.web.enable": false } }, 20_000,
    ));
    await waitFor(() => expect(web).toBeEnabled());
    expect(memory).not.toBeChecked();
    expect(web).not.toBeChecked();
  });

  it("reveals web search settings when web tools are enabled", async () => {
    const payload = { ...settingsPayload(), runtime_config: { "tools.web.enable": false } };
    requestMutationMock.mockResolvedValue({
      ...payload, runtime_config: { "tools.web.enable": true },
    });
    renderSettingsView({ initialSection: "browser", initialSettings: payload });
    fireEvent.click(screen.getByRole("switch", { name: "Web access" }));
    expect(screen.getByRole("combobox", { name: "DuckDuckGo" })).toBeVisible();
    await waitFor(() => expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.runtime_config.update", { values: { "tools.web.enable": true } }, 20_000,
    ));
  });

  it("saves network safety without exposing technical SSRF copy", async () => {
    const payload = settingsPayload();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") return jsonResponse(payload);
      if (url === "/api/settings/cli-apps") {
        return jsonResponse({ apps: [], installed_count: 0 });
      }
      if (url === "/api/settings/mcp-presets") {
        return jsonResponse({ presets: [], installed_count: 0 });
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockResolvedValueOnce({
      ...payload,
      advanced: { ...payload.advanced, webui_allow_local_service_access: false },
      requires_restart: true,
      restart_required_sections: ["runtime"],
    });

    renderSettingsView({ initialSection: "advanced" });

    expect(await screen.findByText("Web safety")).toBeInTheDocument();
    expect(screen.getByText("Default access")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Default Permission" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Full Access" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("switch", { name: "Local services" }));

    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.network_safety.update",
        {
          webui_allow_local_service_access: false,
          webui_default_access_mode: "default",
        },
        20_000,
      ),
    );
  });

  it("saves the web proxy switch separately from the shared address in Advanced", async () => {
    let payload = { ...settingsPayload(), runtime_config: {
      "tools.web.enable": false, "tools.web.use_proxy": false,
      "network.proxy": "http://old-proxy.example:8080", "tools.web.user_agent": null,
    } } as SettingsPayload;
    requestMutationMock.mockImplementation(async (_method, update) => {
      payload = { ...payload, runtime_config: { ...payload.runtime_config, ...update.values },
        requires_restart: true, restart_required_sections: ["runtime"] };
      return payload;
    });
    renderSettingsView({ initialSection: "capabilities", initialSettings: payload });
    fireEvent.click(within(screen.getByRole("region", { name: "Web access" })).getByRole("button", { name: "Configure" }));
    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    const useProxy = screen.getByRole("switch", { name: "Use proxy" });
    expect(useProxy).not.toBeChecked();
    expect(screen.queryByRole("textbox", { name: /proxy/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Shared proxy")).not.toBeInTheDocument();
    fireEvent.click(useProxy);
    await waitFor(() => expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.runtime_config.update", { values: { "tools.web.use_proxy": true } }, 20_000,
    ));
    await waitFor(() => expect(useProxy).toBeEnabled());
    expect(useProxy).toBeChecked();
    fireEvent.click(useProxy);
    await waitFor(() => expect(requestMutationMock).toHaveBeenLastCalledWith(
      "settings.runtime_config.update", { values: { "tools.web.use_proxy": false } }, 20_000,
    ));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Web access" })).getByRole("button", { name: "Close" }));
    expect(screen.getByRole("switch", { name: "Web access" })).not.toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Advanced" }));
    const proxy = screen.getByRole("textbox", { name: "Shared proxy" });
    expect(proxy).toHaveAttribute("type", "text");
    expect(proxy).toHaveValue("http://old-proxy.example:8080");
    expect(screen.queryByRole("switch", { name: "Use proxy" })).not.toBeInTheDocument();
    const address = "http://user:secret@new-proxy.example:7890";
    fireEvent.change(proxy, { target: { value: address } });
    expect(proxy).toHaveValue("http://new-proxy.example:7890");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    fireEvent.click(within(screen.getByRole("region", { name: "Shared proxy" })).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(requestMutationMock).toHaveBeenLastCalledWith(
      "settings.runtime_config.update", { values: { "network.proxy": address } }, 20_000,
    ));
    fireEvent.click(screen.getByRole("button", { name: "System" }));
    fireEvent.click(screen.getByRole("button", { name: "Advanced" }));
    expect(screen.getByLabelText("Shared proxy", { selector: "input" })).toHaveValue("http://new-proxy.example:7890");
    expect(screen.getByLabelText("Username")).toHaveValue("user");
    expect(screen.getByLabelText("Password")).toHaveValue("secret");
    expect(document.body).not.toHaveTextContent(address);
  });

  it("saves optional-key web search providers without an API key", async () => {
    const payload = {
      ...settingsPayload(),
      web_search: {
        ...settingsPayload().web_search,
        provider: "duckduckgo",
        providers: [
          { name: "duckduckgo", label: "DuckDuckGo", credential: "none" as const },
          { name: "keenable", label: "Keenable", credential: "optional_api_key" as const },
        ],
      },
    };
    const updatedPayload = {
      ...payload,
      web_search: {
        ...payload.web_search,
        provider: "keenable",
      },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") return jsonResponse(payload);
      if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
      if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockResolvedValueOnce(updatedPayload);

    renderSettingsView({ initialSection: "browser" });

    fireEvent.keyDown(await screen.findByRole("combobox", { name: /DuckDuckGo/ }), { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "Keenable" }));

    await waitFor(() =>
      expect(requestMutationMock).toHaveBeenCalledWith(
        "settings.web_search.update",
        {
          provider: "keenable",
          max_results: 5,
          timeout: 30,
          use_jina_reader: true,
        },
        20_000,
      ),
    );
  });

  it("requires an explicit DeepSeek search key before saving and preserves it on later edits", async () => {
    let payload: SettingsPayload = settingsPayload();
    payload.web_search.providers.push({
      name: "deepseek", label: "DeepSeek", credential: "api_key",
    });
    requestMutationMock.mockImplementation(async (_method, update) => {
      payload = { ...payload, web_search: {
        ...payload.web_search, provider: update.provider, timeout: update.timeout,
        api_key_hint: "sk-d...key",
      } };
      return payload;
    });
    renderSettingsView({ initialSection: "browser", initialSettings: payload });

    fireEvent.keyDown(screen.getByRole("combobox", { name: "DuckDuckGo" }), { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "DeepSeek" }));
    expect(await screen.findByText("Add the required credential before saving.")).toBeVisible();
    expect(requestMutationMock).not.toHaveBeenCalled();
    const key = screen.getByPlaceholderText("Enter API key");
    fireEvent.change(key, { target: { value: "sk-deepseek-search-key" } });
    fireEvent.blur(key);
    await waitFor(() => expect(requestMutationMock).toHaveBeenCalledWith(
      "settings.web_search.update",
      { provider: "deepseek", api_key: "sk-deepseek-search-key", max_results: 5, timeout: 30, use_jina_reader: true },
      20_000,
    ));
    expect(await screen.findByText("sk-d...key")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    const timeout = screen.getAllByRole("spinbutton").find((input) => (input as HTMLInputElement).value === "30")!;
    fireEvent.change(timeout, { target: { value: "45" } });
    fireEvent.blur(timeout);
    await waitFor(() => expect(requestMutationMock).toHaveBeenLastCalledWith(
      "settings.web_search.update",
      { provider: "deepseek", max_results: 5, timeout: 45, use_jina_reader: true },
      20_000,
    ));
  });

  it("keeps a newer credential draft visible when an older save response arrives", async () => {
    const payload = settingsPayload();
    payload.web_search = { ...payload.web_search, provider: "deepseek", api_key_hint: "old-key",
      providers: [...payload.web_search.providers, { name: "deepseek", label: "DeepSeek", credential: "api_key" }] };
    let finish!: (value: SettingsPayload) => void;
    requestMutationMock.mockImplementationOnce(() => new Promise<SettingsPayload>((resolve) => { finish = resolve; }))
      .mockResolvedValue({ ...payload, web_search: { ...payload.web_search, api_key_hint: "latest-key" } });
    renderSettingsView({ initialSection: "browser", initialSettings: payload });
    const credential = screen.getByText("old-key").parentElement!;
    fireEvent.click(within(credential).getByRole("button", { name: "Edit" }));
    const key = credential.querySelector("input")!;
    fireEvent.focus(key);
    fireEvent.change(key, { target: { value: "first-key" } });
    fireEvent.blur(key);
    await waitFor(() => expect(requestMutationMock).toHaveBeenCalledTimes(1));
    fireEvent.focus(key);
    fireEvent.change(key, { target: { value: "latest-key" } });
    await act(async () => finish({ ...payload, web_search: { ...payload.web_search, api_key_hint: "first-key" } }));
    expect(key).toBeVisible();
    expect(key).toHaveValue("latest-key");
    expect(requestMutationMock).toHaveBeenCalledTimes(1);
    fireEvent.blur(key);
    await waitFor(() => expect(requestMutationMock).toHaveBeenLastCalledWith(
      "settings.web_search.update", expect.objectContaining({ api_key: "latest-key" }), 20_000,
    ));
  });

  it("uses native host safety copy on the native surface", async () => {
    const payload = {
      ...settingsPayload(),
      surface: "native" as const,
      runtime_surface: "native" as const,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/settings") return jsonResponse(payload);
        if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
        if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
        return { ok: false, status: 404, json: async () => ({}) } as Response;
      }),
    );

    renderSettingsView({ initialSection: "advanced" });

    expect(await screen.findByText("App safety")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Local services" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Allow Full Access shell commands to reach services on this Mac.");
  });

  it("refreshes settings with a fresh token after native engine restart", async () => {
    const payload = {
      ...settingsPayload(),
      surface: "native" as const,
      runtime_surface: "native" as const,
      runtime_capabilities: {
        can_restart_engine: true,
        can_open_logs: true,
        can_export_diagnostics: true,
      },
    };
    const restartedPayload = {
      ...payload,
      advanced: { ...payload.advanced, webui_allow_local_service_access: false },
      requires_restart: true,
      restart_required_sections: ["runtime"],
    };
    const refreshedPayload = {
      ...restartedPayload,
      requires_restart: false,
      restart_required_sections: [],
    };
    const restartEngine = vi.fn(async () => "fresh-token");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
      if (url === "/api/settings" && auth === "Bearer fresh-token") {
        return jsonResponse(refreshedPayload);
      }
      if (url === "/api/settings") return jsonResponse(payload);
      if (url === "/api/settings/cli-apps") return jsonResponse({ apps: [], installed_count: 0 });
      if (url === "/api/settings/mcp-presets") return jsonResponse({ presets: [], installed_count: 0 });
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    requestMutationMock.mockResolvedValueOnce(restartedPayload);

    renderSettingsView({
      initialSection: "advanced",
      onNativeEngineRestart: restartEngine,
    });

    expect(await screen.findByText("App safety")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "Local services" }));

    await waitFor(() => expect(restartEngine).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/settings",
        expect.objectContaining({
          headers: { Authorization: "Bearer fresh-token" },
        }),
      ),
    );
  });
});
