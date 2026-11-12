import { openAppCatalog } from "./helpers/app-navigation";
import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  createChatSpy,
  requestMutationSpy,
  statusHandlers,
  setNavigatorPlatform,
  mockFetchRoutes,
  baseSettingsPayload,
} from "./helpers/app-harness";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "@/App";

describe("App navigation", () => {
  installAppTestLifecycle();

  it("switches to a conversation tab after deferring a required settings restart", async () => {
    const payload = { ...baseSettingsPayload(), requires_restart: true };
    mockFetchRoutes({ "/v0/settings": payload });
    render(<App />);
    const user = userEvent.setup();
    await screen.findByRole("textbox", { name: "Message input" });
    await user.click(screen.getByRole("button", { name: "Open Settings" }));
    await screen.findByRole("navigation", { name: "Settings sections" });
    const chat = screen.getAllByRole("tab").find(tab => tab.getAttribute("aria-selected") !== "true")!;
    await user.click(chat);
    let dialog = await screen.findByRole("dialog", { name: "Restart before leaving?" });
    await user.keyboard("{Escape}");
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");
    expect(window.location.hash).toBe("#/settings");
    await user.click(chat);
    dialog = await screen.findByRole("dialog", { name: "Restart before leaving?" });
    await user.click(within(dialog).getByRole("button", { name: "Restart later" }));
    await waitFor(() => expect(window.location.hash).toBe("#/new"));
    expect(chat).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("textbox", { name: "Message input" })).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Settings" }));
    expect(await screen.findByText("Saved. Restart to apply changes.")).toBeVisible();
  });

  it("keeps a just-created topic route while the session list catches up", async () => {
    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const firstMessage = "keep this first turn visible";
    fireEvent.change(
      await screen.findByRole("textbox", { name: "Message input" }),
      {
        target: { value: firstMessage },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(createChatSpy).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(window.location.hash).toBe(
        `#/chat/${encodeURIComponent("websocket:chat-1")}`,
      ),
    );
    expect(await screen.findByText(firstMessage)).toBeInTheDocument();
  });

  it("keeps the context-menu project through navigation and first-message creation", async () => {
    const projectScope = {
      project_path: "/tmp/selected-project",
      project_name: "selected-project",
      access_mode: "full" as const,
      restrict_to_workspace: false,
    };
    appTest.sessions = [
      {
        key: "websocket:existing-chat",
        channel: "websocket",
        chatId: "existing-chat",
        createdAt: null,
        updatedAt: null,
        preview: "Existing topic",
        workspaceScope: projectScope,
        projectId: "selected-project-id",
      },
    ];
    mockFetchRoutes({
      "/v0/workspaces": {
        schema_version: 1,
        default_access_mode: "full",
        default_scope: {
          ...projectScope,
          project_path: "/tmp/workspace",
          project_name: "workspace",
        },
        controls: { can_change_project: true },
      },
    });
    requestMutationSpy.mockResolvedValue({
      projects: [
        {
          id: "selected-project-id",
          name: "selected-project",
          working_directory: projectScope.project_path,
        },
      ],
    });
    window.history.replaceState(null, "", "/#/chat/websocket%3Aexisting-chat");
    render(<App />);
    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    // Wait for the existing chat's lazy composer before opening its sidebar menu.
    await screen.findByRole("button", {
      name: "Workspace access mode: Full Access",
    });
    act(() => statusHandlers.forEach((handler) => handler("open")));
    await openAppCatalog();
    fireEvent.click(
      await screen.findByRole("button", {
        name: "New conversation in selected-project",
      }),
    );
    await waitFor(() => expect(window.location.hash).toBe("#/new"));
    expect(
      await screen.findByRole("button", { name: "Switch directory" }),
    ).toHaveTextContent("selected-project");
    fireEvent.change(screen.getByRole("textbox", { name: "Message input" }), {
      target: { value: "project topic" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() =>
      expect(createChatSpy).toHaveBeenCalledWith(projectScope),
    );
  });

  it("restores the active chat from the URL hash after a page reload", async () => {
    appTest.sessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "Active after reload",
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Other chat",
      },
    ];
    window.history.replaceState(
      null,
      "",
      `/#/chat/${encodeURIComponent("websocket:chat-a")}`,
    );

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    await waitFor(() => expect(document.title).toBe("Active after reload"));
    const sidebar = await openAppCatalog();
    expect(
      within(sidebar).getByRole("button", { name: /^Active after reload$/ }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe(
      `#/chat/${encodeURIComponent("websocket:chat-a")}`,
    );
  });

  it("restores the settings section from the URL hash after a page reload", async () => {
    mockFetchRoutes({ "/v0/settings": baseSettingsPayload() });
    window.history.replaceState(null, "", "/#/settings?section=models");

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    expect(await screen.findByRole("heading", { name: "Models", level: 1 })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/settings?section=models");
  });

  it("falls back to Overview for the retired Files settings URL", async () => {
    mockFetchRoutes({ "/v0/settings": baseSettingsPayload() });
    window.history.replaceState(null, "", "/#/settings?section=files");

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    expect(
      await screen.findByRole("navigation", { name: "Settings sections" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Overview", level: 1 })).toBeInTheDocument();
  });

  it("updates the URL hash when switching settings sections", async () => {
    mockFetchRoutes({ "/v0/settings": baseSettingsPayload() });

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.click(
      await screen.findByRole("button", { name: "Open Settings" }),
    );
    expect(
      await screen.findByRole("navigation", { name: "Settings sections" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/settings");

    const settingsNav = screen.getByRole("navigation", {
      name: "Settings sections",
    });
    const overviewButton = within(settingsNav).getByRole("button", {
      name: "Overview",
    });
    const modelsButton = within(settingsNav).getByRole("button", {
      name: "Models",
    });
    expect(overviewButton).toHaveAttribute("aria-current", "page");

    fireEvent.click(modelsButton);

    expect(await screen.findByRole("heading", { name: "Models", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New preset" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/settings?section=models");
    expect(modelsButton).toHaveAttribute("aria-current", "page");

    const webSearchButton = within(settingsNav).getByRole("button", {
      name: "Web search",
    });
    fireEvent.click(webSearchButton);

    expect(screen.getByTestId("settings-section-transition")).toHaveAttribute(
      "data-settings-section",
      "browser",
    );
    expect(window.location.hash).toBe("#/settings?section=browser");
    expect(webSearchButton).toHaveAttribute("aria-current", "page");
  });

  it.each([
    ["apps", "1", "Digit1", true],
    ["skills", "2", "Digit2", true],
    ["automations", "3", "Digit3", true],
    ["settings", ",", "Comma", false],
  ])(
    "opens %s using its sidebar shortcut",
    async (route, key, code, shiftKey) => {
      mockFetchRoutes({ "/v0/settings": baseSettingsPayload() });
      render(<App />);
      await waitFor(() => expect(connectSpy).toHaveBeenCalled());
      fireEvent.keyDown(window, { key, code, shiftKey, ctrlKey: true });
      await waitFor(() => expect(window.location.hash).toContain("#/" + route));
    },
  );

  it.each([
    ["Command", { metaKey: true }],
    ["Control", { ctrlKey: true }],
  ])(
    "starts a new chat from the %s keyboard shortcut",
    async (_label, modifier) => {
      appTest.sessions = [
        {
          key: "websocket:chat-a",
          channel: "websocket",
          chatId: "chat-a",
          createdAt: "2026-04-16T10:00:00Z",
          updatedAt: "2026-04-16T10:00:00Z",
          preview: "Existing chat",
        },
      ];

      render(<App />);

      await waitFor(() => expect(connectSpy).toHaveBeenCalled());
      fireEvent.keyDown(window, { key: "O", shiftKey: true, ...modifier });

      expect(window.location.hash).toBe("#/new");
    },
  );

  it("exposes the new chat keyboard shortcut in the sidebar tooltip", async () => {
    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const newChatButton = await screen.findByRole("button", {
      name: "Open New conversation",
    });
    expect(newChatButton).toHaveTextContent("");
    const input = await screen.findByRole("textbox", { name: "Message input" });
    await waitFor(() => expect(input).toHaveFocus());
    await userEvent.setup().keyboard("{Tab}");
    act(() => newChatButton.focus());
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("New conversation");
    expect(tooltip.querySelector("kbd")).toHaveTextContent("Ctrl+Shift+O");
    expect(newChatButton).toHaveAccessibleDescription(/New conversation.*Ctrl\+Shift\+O/);
  });

  it("uses macOS shortcut glyphs in the sidebar tooltip", async () => {
    setNavigatorPlatform("MacIntel");
    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const input = await screen.findByRole("textbox", { name: "Message input" });
    await waitFor(() => expect(input).toHaveFocus());
    const create = screen.getByRole("button", { name: "Open New conversation" });
    await userEvent.setup().keyboard("{Tab}");
    act(() => create.focus());
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("New conversation");
    expect(tooltip.querySelector("kbd")).toHaveTextContent("⌘⇧O");
  });
});
