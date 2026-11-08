import { openAppCatalog } from "./helpers/app-navigation";
import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  deleteChatSpy,
  getSessionAutomationsSpy,
  mockFetchRoutes,
  currentMonthTimestamp,
  baseSettingsPayload,
} from "./helpers/app-harness";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it } from "vitest";
import i18n from "@/i18n";
import { patchPreferences } from "@/features/preferences/store";
import App from "@/App";

describe("App automations", () => {
  installAppTestLifecycle();

  it("localizes the Automations surface", async () => {
    await i18n.changeLanguage("zh-CN");
    void patchPreferences({ language: "zh-CN" });
    mockFetchRoutes({
      "/v0/settings": baseSettingsPayload(),
      "/v0/webui/automations": {
        jobs: [
          {
            id: "job-zh",
            name: "每日检查",
            enabled: true,
            protected: false,
            delete_after_run: false,
            schedule: { kind: "every", every_ms: 86_400_000 },
            payload: {
              message: "检查仓库状态",
              kind: "agent_turn",
            },
            state: {
              next_run_at_ms: currentMonthTimestamp(17),
              last_run_at_ms: currentMonthTimestamp(16),
              last_status: "ok",
              pending: false,
              run_history: [
                {
                  run_at_ms: currentMonthTimestamp(16),
                  status: "ok",
                  duration_ms: 500,
                },
              ],
            },
            origin: {
              session_key: "websocket:chat-a",
              channel: "websocket",
              chat_id: "chat-a",
              title: "发布准备",
              preview: "检查发布阻塞项",
            },
          },
        ],
      },
    });

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = screen.getByRole("navigation", { name: "Launcher" });
    fireEvent.click(
      within(sidebar).getByRole("button", { name: "打开自动化" }),
    );

    const heading = await screen.findByRole("heading", { name: "自动任务" });
    expect(heading).toBeInTheDocument();
    const automationsMain = heading.closest("main");
    expect(automationsMain).not.toBeNull();
    expect(
      within(automationsMain as HTMLElement).queryByText("设置"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("任务队列")).not.toBeInTheDocument();
    expect((await screen.findAllByText("每日检查")).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("检查仓库状态")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /每日检查.*计划运行/ }));
    const detail = within(screen.getByRole("dialog", { name: "每日检查" }));
    expect(detail.getByText("检查仓库状态")).toBeVisible();
    expect(detail.queryByText(/每 1天/)).not.toBeInTheDocument();
    fireEvent.click(detail.getByRole("button", { name: "任务信息" }));
    expect(
      within(screen.getByRole("dialog", { name: "任务信息" })).getByText(
        /每 1天/,
      ),
    ).toBeVisible();
    expect(screen.queryByText("最近健康状态")).not.toBeInTheDocument();
    expect(screen.queryByText("近期无问题")).not.toBeInTheDocument();
    expect(screen.queryByText("Workspace automations")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "刷新" }),
    ).not.toBeInTheDocument();
    expect(document.title).toBe("自动任务");
  });

  it("shows localized bound automations in the first delete confirmation", async () => {
    appTest.sessions = [
      {
        key: "websocket:chat-a",
        channel: "websocket",
        chatId: "chat-a",
        createdAt: "2026-04-16T10:00:00Z",
        updatedAt: "2026-04-16T10:00:00Z",
        preview: "First chat",
      },
      {
        key: "websocket:chat-b",
        channel: "websocket",
        chatId: "chat-b",
        createdAt: "2026-04-16T11:00:00Z",
        updatedAt: "2026-04-16T11:00:00Z",
        preview: "Second chat",
      },
    ];
    getSessionAutomationsSpy.mockResolvedValue([
      {
        id: "job-1",
        name: "Daily repo check",
        enabled: true,
        schedule: { kind: "every", every_ms: 86_400_000 },
        payload: { message: "Check the repo" },
        state: { next_run_at_ms: Date.UTC(2026, 3, 17, 10, 0, 0) },
      },
    ]);
    await i18n.changeLanguage("zh-CN");
    void patchPreferences({ language: "zh-CN" });

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const sidebar = await openAppCatalog();
    await waitFor(() =>
      expect(
        within(sidebar).getByRole("button", { name: /^First chat$/ }),
      ).toBeInTheDocument(),
    );

    fireEvent.pointerDown(screen.getByLabelText(/First chat.*会话操作/), {
      button: 0,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "删除" }));

    await waitFor(() =>
      expect(screen.getByText("Daily repo check")).toBeInTheDocument(),
    );
    expect(getSessionAutomationsSpy).toHaveBeenCalledWith("websocket:chat-a");
    expect(
      screen.getByText("删除会话也会删除关联的自动任务"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Deleting this conversation also deletes its linked automations.",
      ),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "删除" }));

    await waitFor(() =>
      expect(deleteChatSpy).toHaveBeenCalledWith("websocket:chat-a", {
        deleteAutomations: true,
      }),
    );
    expect(deleteChatSpy).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Daily repo check")).not.toBeInTheDocument();
  }, 15_000);
});
