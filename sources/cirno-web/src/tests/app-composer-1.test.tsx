import {
  closeAppConversationTab,
  openAppConversation,
  startAppTemporaryConversation,
} from "./helpers/app-navigation";
import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  createChatSpy,
  requestMutationSpy,
  discardTemporaryChatSpy,
  sendMessageSpy,
  statusHandlers,
  sessionUpdateHandlers,
  readyHandlers,
  mockFetchRoutes,
  baseSettingsPayload,
} from "./helpers/app-harness";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "@/App";

describe("App composer", () => {
  installAppTestLifecycle();

  it("uses one main landmark and a page heading in desktop settings", async () => {
    mockFetchRoutes({ "/v0/settings": baseSettingsPayload() });
    const { container } = render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.click(
      await screen.findByRole("button", { name: "Open Settings" }),
    );

    await act(async () => {
      await import("@/features/settings/SettingsView");
    });

    expect(
      screen.getByRole("navigation", { name: "Settings sections" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to chat" })).toBeVisible();
    expect(container.querySelectorAll("main")).toHaveLength(1);
    expect(
      screen.getByRole("navigation", { name: "Settings sections" }),
    ).toBeInTheDocument();
  });

  it("creates independent temporary conversations and disposes only the closed tab", async () => {
    const { unmount } = render(<App />);
    const firstHash = await startAppTemporaryConversation(
      "first private message",
    );
    expect(
      screen.queryByRole("button", { name: "Temporary chat" }),
    ).not.toBeInTheDocument();
    expect(createChatSpy).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Open New conversation" }),
    );
    const secondHash = await startAppTemporaryConversation(
      "second private message",
    );
    expect(secondHash).not.toBe(firstHash);
    expect(discardTemporaryChatSpy).not.toHaveBeenCalled();
    await openAppConversation("first private message");
    await waitFor(() => expect(window.location.hash).toBe(firstHash));
    expect(
      screen.getByRole("tab", { name: "first private message" }),
    ).toHaveAttribute("aria-selected", "true");
    await openAppConversation("second private message");
    await closeAppConversationTab("first private message");
    await waitFor(() =>
      expect(discardTemporaryChatSpy).toHaveBeenCalledTimes(1),
    );
    expect(window.location.hash).toBe(secondHash);
    expect(
      screen.queryByRole("tab", { name: "first private message" }),
    ).not.toBeInTheDocument();
    unmount();
    await waitFor(() =>
      expect(discardTemporaryChatSpy).toHaveBeenCalledTimes(2),
    );
    expect(
      new Set(discardTemporaryChatSpy.mock.calls.map(([id]) => id)).size,
    ).toBe(2);
  });

  it("offers temporary mode only before the first message and explains its lifetime", async () => {
    appTest.sessions = [
      {
        key: "websocket:existing-chat",
        channel: "websocket",
        chatId: "existing-chat",
        createdAt: null,
        updatedAt: null,
        preview: "Existing topic",
      },
    ];
    render(<App />);
    const toggle = await screen.findByRole("button", {
      name: "Temporary chat",
    });
    const user = userEvent.setup();
    await user.hover(toggle);
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Not saved to history or memory",
    );
    await user.unhover(toggle);
    await openAppConversation("Existing topic");
    expect(
      screen.queryByRole("button", { name: "Temporary chat" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Open New conversation" }),
    );
    await startAppTemporaryConversation("start temporary chat");
    expect(
      screen.queryByRole("button", { name: "Temporary chat" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Clear chat" }),
    ).not.toBeInTheDocument();
  });

  it("allows leaving a page with temporary chats without blocking", async () => {
    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.click(
      await screen.findByRole("button", { name: "Temporary chat" }),
    );
    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "do not lose this" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() =>
      expect(window.location.hash).toMatch(/^#\/temporary\/[0-9a-f-]+$/),
    );

    const beforeUnload = new Event("beforeunload", { cancelable: true });
    act(() => window.dispatchEvent(beforeUnload));
    expect(beforeUnload.defaultPrevented).toBe(false);
  });

  it("ends temporary chats quietly after a connection interruption", async () => {
    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    act(() => {
      statusHandlers.forEach((handler) => handler("open"));
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "Temporary chat" }),
    );
    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "connection-sensitive message" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() =>
      expect(window.location.hash).toMatch(/^#\/temporary\/[0-9a-f-]+$/),
    );

    act(() => {
      statusHandlers.forEach((handler) => handler("reconnecting"));
    });

    await waitFor(() => expect(window.location.hash).toBe("#/new"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.queryByText("connection-sensitive message"),
    ).not.toBeInTheDocument();
  });

  it("retains the last workspace selector when reconnect refresh fails", async () => {
    mockFetchRoutes({
      "/v0/workspaces": {
        schema_version: 1,
        default_access_mode: "full",
        default_scope: {
          project_path: "/tmp/workspace",
          project_name: "workspace",
          access_mode: "full",
          restrict_to_workspace: false,
        },
        controls: { can_change_project: true },
      },
    });
    render(<App />);
    expect(
      await screen.findByRole("button", { name: "Switch directory" }),
    ).toHaveTextContent("workspace");
    mockFetchRoutes({
      "/v0/workspaces": () => {
        throw new Error("Directory service unavailable");
      },
    });
    await act(async () => readyHandlers.forEach((handler) => handler()));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Directory service unavailable",
    );
    expect(
      screen.getByRole("button", { name: "Switch directory" }),
    ).toHaveTextContent("workspace");
    mockFetchRoutes({
      "/v0/workspaces": {
        schema_version: 1,
        default_access_mode: "full",
        default_scope: {
          project_path: "/tmp/restored",
          project_name: "restored",
          access_mode: "full",
          restrict_to_workspace: false,
        },
        controls: { can_change_project: true },
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Switch directory" }),
    ).toHaveTextContent("restored");
  });

  it("uses the restricted default scope without offering project selection", async () => {
    mockFetchRoutes({
      "/v0/workspaces": {
        schema_version: 1,
        default_access_mode: "full",
        default_scope: {
          project_path: "/tmp/workspace",
          project_name: "workspace",
          access_mode: "full",
          restrict_to_workspace: false,
        },
        controls: { can_change_project: true },
      },
    });
    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    expect(
      await screen.findByRole("button", { name: "Switch directory" }),
    ).toBeInTheDocument();
    act(() => {
      sessionUpdateHandlers.forEach((handler) =>
        handler("selected-chat", "metadata", {
          project_path: "/tmp/selected-project",
          project_name: "selected-project",
          access_mode: "full",
          restrict_to_workspace: false,
        }),
      );
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "Temporary chat" }),
    );

    expect(
      screen.queryByRole("button", { name: "Switch directory" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Full Access")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Message input"), {
      target: { value: "temporary project check" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(sendMessageSpy).toHaveBeenCalled());
    const options = sendMessageSpy.mock.calls.at(-1)?.[3];
    expect(options?.workspaceScope).toMatchObject({
      project_path: "/tmp/workspace",
      access_mode: "restricted",
      restrict_to_workspace: true,
    });
  });

  it("preserves the first message when the gateway rejects a project", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    const projectPath = "C:\\missing-project";
    const directory = (path: string) => ({
      path,
      parent: null,
      entries: [],
      partial: false,
      truncated: false,
      host: "test-host",
      platform: "Windows",
    });
    const directoryUrl = (path: string) =>
      `/v0/workspaces/directories?${new URLSearchParams({ path, q: "", hidden: "0", partial: "1" })}`;
    requestMutationSpy.mockResolvedValue({
      path: projectPath,
      name: "missing-project",
    });
    createChatSpy.mockRejectedValueOnce(
      new Error(
        "workspace_scope_rejected:project_path must be an existing directory",
      ),
    );
    mockFetchRoutes({
      "/v0/workspaces": {
        schema_version: 1,
        default_access_mode: "default",
        default_scope: {
          project_path: "C:\\workspace",
          project_name: "workspace",
          access_mode: "restricted",
          restrict_to_workspace: true,
        },
        controls: {
          can_change_project: true,
          can_browse_directories: true,
          can_resolve_project: true,
        },
      },
      [directoryUrl("C:\\workspace")]: directory("C:\\workspace"),
      [directoryUrl("C:\\workspace\\")]: directory("C:\\workspace"),
      [directoryUrl(projectPath)]: directory(projectPath),
      [directoryUrl(`${projectPath}\\`)]: directory(projectPath),
    });

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    fireEvent.click(
      await screen.findByRole("button", { name: "Switch directory" }),
    );
    fireEvent.click(screen.getByRole("button", { name: /^Edit path:/ }));
    fireEvent.change(await screen.findByRole("combobox"), {
      target: { value: projectPath },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );

    const message = screen.getByLabelText("Message input");
    fireEvent.change(message, { target: { value: "keep this first message" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(createChatSpy).toHaveBeenCalledTimes(1));
    expect(message).toHaveValue("keep this first message");
    const projectButton = screen.getByRole("button", {
      name: "Switch directory",
    });
    await waitFor(() => expect(projectButton).toHaveFocus());
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The Cirno server rejected this project or access mode. Choose an existing project or a different access mode, then try again.",
    );
    fireEvent.click(projectButton);
    fireEvent.click(screen.getByRole("button", { name: /^Edit path:/ }));
    const pathInput = await screen.findByRole("combobox");
    expect(pathInput).toHaveValue(`${projectPath}\\`);
    expect(pathInput).toHaveAttribute("aria-invalid", "true");
    expect(pathInput).toHaveFocus();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The Cirno server rejected this project or access mode. Choose an existing project or a different access mode, then try again.",
    );
    expect(window.location.hash).toBe("");
    consoleError.mockRestore();
  });
});
