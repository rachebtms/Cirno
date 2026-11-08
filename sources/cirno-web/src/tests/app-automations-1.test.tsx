import { openAppCatalog } from "./helpers/app-navigation";
import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  requestMutationSpy,
  sidebarStateUpdateHandlers,
  mockFetchRoutes,
  currentMonthTimestamp,
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
import type { SidebarStatePayload } from "@/lib/contracts/conversation-preferences";
import App from "@/App";

describe("App automations", () => {
  installAppTestLifecycle();

  it("opens Automations from the main sidebar", async () => {
    mockFetchRoutes({
      "/v0/settings": baseSettingsPayload(),
      "/v0/webui/automations": {
        jobs: [
          {
            id: "job-1",
            name: "Daily repo check",
            enabled: true,
            protected: false,
            delete_after_run: false,
            schedule: { kind: "every", every_ms: 86_400_000 },
            payload: {
              message: "Check the repo status",
              kind: "agent_turn",
            },
            state: {
              next_run_at_ms: currentMonthTimestamp(17),
              last_status: "ok",
              pending: false,
              run_history: [],
            },
            origin: {
              session_key: "websocket:chat-a",
              channel: "websocket",
              chat_id: "chat-a",
              title: "Release prep",
              preview: "Check release blockers",
            },
          },
          {
            id: "external-quiz",
            name: "WeChat quiz",
            enabled: true,
            protected: false,
            delete_after_run: false,
            schedule: {
              kind: "cron",
              expr: "30 9-23 * * *",
              tz: "Asia/Shanghai",
            },
            payload: {
              message: "Send a quiz",
              kind: "agent_turn",
            },
            state: {
              next_run_at_ms: currentMonthTimestamp(17, 11, 30),
              last_status: "ok",
              pending: false,
              run_history: [],
            },
            origin: {
              channel: "weixin",
              title: "",
              preview: "",
            },
          },
          {
            id: "heartbeat",
            name: "heartbeat",
            enabled: true,
            protected: true,
            schedule: { kind: "every", every_ms: 60_000 },
            payload: { message: "", kind: "system_event" },
            state: { next_run_at_ms: null, pending: false, run_history: [] },
            origin: null,
          },
        ],
      },
    });

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", {
      name: "Launcher",
    });
    const automationsButton = within(sidebar).getByRole("button", {
      name: "Open Automations",
    });

    fireEvent.click(automationsButton);

    const heading = await screen.findByRole(
      "heading",
      { name: "Automations" },
      { timeout: 5_000 },
    );
    expect(heading).toBeInTheDocument();
    const automationsMain = heading.closest("main");
    expect(automationsMain).not.toBeNull();
    expect(
      within(automationsMain as HTMLElement).queryByText("Settings"),
    ).not.toBeInTheDocument();
    expect(
      (await screen.findAllByText("Daily repo check", {}, { timeout: 5_000 }))
        .length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Check the repo status")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Daily repo check/ }));
    expect(
      within(
        screen.getByRole("dialog", { name: "Daily repo check" }),
      ).getByText("Check the repo status"),
    ).toBeVisible();
    const detail = within(
      screen.getByRole("dialog", { name: "Daily repo check" }),
    );
    expect(detail.queryByText("Release prep")).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(detail.getByRole("button", { name: "More actions" }));
    expect(
      screen.getByRole("menuitem", { name: "Open a chat" }),
    ).toHaveAttribute("href", "#/chat/websocket%3Achat-a");
    await user.keyboard("{Escape}");
    expect(detail.getByRole("button", { name: "More actions" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.getByText("WeChat quiz")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /WeChat quiz/ }));
    expect(screen.getByText("weixin")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByText("weixin:wx-chat")).not.toBeInTheDocument();
    expect(
      screen.queryByText("memory with dream state"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /heartbeat/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "System tasks 1" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("heartbeat")).not.toBeInTheDocument();
    expect(
      within(sidebar).getByRole("button", { name: "Open Automations" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(document.title).toBe("Automations");
  });

  it("keeps the automation chat link stable across live sidebar renames without duplicating titles", async () => {
    const key = "websocket:linked-chat";
    appTest.sessions = [
      {
        key,
        channel: "websocket",
        chatId: "linked-chat",
        createdAt: null,
        updatedAt: null,
        title: "Stored title",
        preview: "Original preview",
      },
    ];
    const sidebarState: SidebarStatePayload = {
      schema_version: 1,
      pinned_keys: [],
      archived_keys: [],
      session_order: [],
      title_overrides: { [key]: "推特大战场" },
      project_name_overrides: {},
      tags_by_key: {},
      collapsed_groups: {},
      view: {
        density: "comfortable",
        show_archived: false,
        sort: "updated_desc",
      },
    };
    mockFetchRoutes({
      "/v0/settings": baseSettingsPayload(),
      "/v0/webui/sidebar-state": sidebarState,
      "/v0/webui/automations": {
        jobs: [
          {
            id: "reminder",
            name: "Drink water",
            enabled: true,
            schedule: { kind: "every", every_ms: 60_000 },
            payload: { message: "Take a break" },
            state: { next_run_at_ms: currentMonthTimestamp(17) },
            origin: {
              session_key: key,
              channel: "websocket",
              chat_id: "linked-chat",
              title: "Stored title",
              preview: "Original preview",
            },
          },
        ],
      },
    });
    render(<App />);
    const sidebar = await openAppCatalog();
    await within(sidebar).findByRole("button", { name: "推特大战场" });
    fireEvent.click(screen.getByRole("button", { name: "Open Automations" }));
    fireEvent.click(await screen.findByRole("button", { name: /Drink water/ }));
    const dialog = screen.getByRole("dialog", { name: "Drink water" });
    expect(within(dialog).queryByText("推特大战场")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Stored title")).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(
      within(dialog).getByRole("button", { name: "More actions" }),
    );
    expect(
      screen.getByRole("menuitem", { name: "Open a chat" }),
    ).toHaveAttribute("href", "#/chat/websocket%3Alinked-chat");
    for (const title of ["新会话名称", ""]) {
      act(() => {
        sidebarStateUpdateHandlers.forEach((handler) =>
          handler({
            ...sidebarState,
            title_overrides: title ? { [key]: title } : {},
          }),
        );
      });
      const expected = title || "Stored title";
      expect(within(sidebar).getByText(expected)).toBeInTheDocument();
      expect(within(dialog).queryByText(expected)).not.toBeInTheDocument();
      expect(
        screen.getByRole("menuitem", { name: "Open a chat" }),
      ).toHaveAttribute("href", "#/chat/websocket%3Alinked-chat");
    }
    await user.keyboard("{Escape}");
    expect(
      within(dialog).getByRole("button", { name: "More actions" }),
    ).toHaveFocus();
    expect(requestMutationSpy).not.toHaveBeenCalled();
  });

  it("edits a past one-time automation without resubmitting its old schedule", async () => {
    const pastOneShot = {
      id: "past-one-shot",
      name: "Past one-shot",
      enabled: true,
      protected: false,
      delete_after_run: true,
      schedule: { kind: "at", at_ms: 1 },
      payload: {
        message: "Old one-shot message",
        kind: "agent_turn",
      },
      state: {
        next_run_at_ms: null,
        last_run_at_ms: currentMonthTimestamp(12),
        last_status: "ok",
        pending: false,
        run_history: [],
      },
      origin: {
        session_key: "websocket:chat-a",
        channel: "websocket",
        chat_id: "chat-a",
        title: "Release prep",
        preview: "Check release blockers",
      },
    };
    mockFetchRoutes({
      "/v0/settings": baseSettingsPayload(),
      "/v0/webui/automations": { jobs: [pastOneShot] },
    });
    requestMutationSpy.mockResolvedValueOnce({
      jobs: [
        {
          ...pastOneShot,
          payload: {
            ...pastOneShot.payload,
            message: "Updated one-shot message",
          },
        },
      ],
    });

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", {
      name: "Launcher",
    });
    fireEvent.click(
      within(sidebar).getByRole("button", { name: "Open Automations" }),
    );

    expect(
      (await screen.findAllByText("Past one-shot")).length,
    ).toBeGreaterThanOrEqual(1);
    fireEvent.click(screen.getByRole("button", { name: /Past one-shot/ }));
    const runDetail = within(
      screen.getByRole("dialog", { name: "Past one-shot" }),
    );
    expect(runDetail.getByText("Completed")).toBeVisible();
    expect(
      runDetail.queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument();
    fireEvent.click(runDetail.getByRole("button", { name: "Close" }));
    fireEvent.click(screen.getByRole("tab", { name: "Tasks" }));
    fireEvent.click(screen.getByRole("button", { name: /Past one-shot/ }));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    await screen.findByRole("dialog", { name: "Edit task" });
    expect(
      screen.queryByText("Run time must be in the future."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        "Update the prompt and schedule. The linked chat stays unchanged.",
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("Old one-shot message")).toBeVisible();

    fireEvent.change(screen.getByDisplayValue("Old one-shot message"), {
      target: { value: "Updated one-shot message" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(requestMutationSpy).toHaveBeenCalledWith(
        "automation.update",
        {
          id: "past-one-shot",
          values: {
            message: "Updated one-shot message",
          },
        },
        20_000,
      );
    });
  });

  it("keeps long automation details expandable without nested scrolling", async () => {
    const longMessage = [
      "Review the release plan and prepare a concise status update for the channel.",
      "Include blockers, owners, follow-up dates, and any risky assumptions that changed since yesterday.",
      "Keep the output actionable and avoid repeating context that the team already confirmed in the thread.",
      "If a dependency looks stale, call it out explicitly and ask for a fresh owner update.",
      "This message is intentionally long enough to require progressive disclosure in the automation details panel.",
      "The full content should remain available without forcing the user into a small nested scroll area.",
    ].join("\n");
    const history = [
      {
        run_at_ms: currentMonthTimestamp(12),
        status: "error",
        duration_ms: 900,
        error: "oldest failure",
      },
      {
        run_at_ms: currentMonthTimestamp(13),
        status: "error",
        duration_ms: 800,
        error: "second oldest failure",
      },
      { run_at_ms: currentMonthTimestamp(14), status: "ok", duration_ms: 700 },
      { run_at_ms: currentMonthTimestamp(15), status: "ok", duration_ms: 600 },
      { run_at_ms: currentMonthTimestamp(16), status: "ok", duration_ms: 500 },
      { run_at_ms: currentMonthTimestamp(17), status: "ok", duration_ms: 400 },
    ];
    mockFetchRoutes({
      "/v0/settings": baseSettingsPayload(),
      "/v0/webui/automations": {
        jobs: [
          {
            id: "long-details",
            name: "Long detail automation",
            enabled: true,
            protected: false,
            delete_after_run: false,
            schedule: { kind: "every", every_ms: 3_600_000 },
            payload: {
              message: longMessage,
              kind: "agent_turn",
            },
            state: {
              next_run_at_ms: currentMonthTimestamp(18),
              last_status: "ok",
              pending: false,
              run_history: history,
            },
            origin: {
              session_key: "websocket:chat-a",
              channel: "websocket",
              chat_id: "chat-a",
              title: "Release prep",
              preview: "Check release blockers",
            },
          },
        ],
      },
    });

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", {
      name: "Launcher",
    });
    fireEvent.click(
      within(sidebar).getByRole("button", { name: "Open Automations" }),
    );

    fireEvent.click(
      await screen.findByRole(
        "button",
        { name: /Long detail automation.*Planned/ },
        { timeout: 5_000 },
      ),
    );
    const detailPanel = await screen.findByRole("dialog", {
      name: "Long detail automation",
    });
    const message = Array.from(detailPanel.querySelectorAll("section p")).find(
      (node) => node.textContent === longMessage,
    ) as HTMLElement | undefined;
    expect(message).toBeTruthy();
    const preview = message!.closest(".expandable-text")!;
    expect(preview).toHaveAttribute("data-state", "closed");

    fireEvent.click(
      within(detailPanel).getByRole("button", { name: "Show full message" }),
    );
    expect(
      within(detailPanel).getByRole("button", { name: "Show less" }),
    ).toBeInTheDocument();
    expect(preview).toHaveAttribute("data-state", "open");
    expect(preview).toContainElement(message!);

    expect(
      within(detailPanel).queryByText("Recent health"),
    ).not.toBeInTheDocument();
    expect(
      within(detailPanel).queryByRole("button", { name: /Run history/ }),
    ).not.toBeInTheDocument();
    expect(
      within(detailPanel).queryByText(/oldest failure/),
    ).not.toBeInTheDocument();
    expect(
      within(detailPanel).queryByText("No error recorded"),
    ).not.toBeInTheDocument();
  });
});
