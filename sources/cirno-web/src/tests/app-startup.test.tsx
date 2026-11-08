import {
  installAppTestLifecycle,
  appTest,
  connectSpy,
  requestMutationSpy,
  mockFetchRoutes,
  baseSettingsPayload,
} from "./helpers/app-harness";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fetchBootstrap } from "@/lib/bootstrap";
import App from "@/App";

describe("App startup", () => {
  installAppTestLifecycle();

  it.each(["skills", "apps", "channels", "automations", "settings", "chat"])(
    "keeps the %s document skeleton while bootstrap is pending",
    (surface) => {
      window.history.replaceState(null, "", `/#/${surface}`);
      vi.mocked(fetchBootstrap).mockReturnValueOnce(new Promise(() => {}));
      render(<App />);
      expect(screen.getByRole("main")).toHaveAttribute("aria-busy", "true");
      expect(screen.getByRole("main")).toHaveAttribute(
        "data-startup-surface",
        surface,
      );
      expect(screen.getByRole("status")).toHaveTextContent("Loading Cirno…");
    },
  );

  it.each([false, true])(
    "enables task controls only when bootstrap advertises support: %s",
    async (supported) => {
      appTest.sessions = [
        {
          key: "websocket:chat-a",
          channel: "websocket",
          chatId: "chat-a",
          createdAt: null,
          updatedAt: null,
          title: "Inspection",
          preview: "Inspect config",
        },
      ];
      window.history.replaceState(null, "", "/#/chat/websocket%3Achat-a");
      vi.mocked(fetchBootstrap).mockResolvedValue({
        token: "tok",
        api_token: "api-tok",
        ws_path: "/",
        expires_in: 300,
        terminal: {
          webui: {
            capabilities: supported
              ? ["webui.core.v1", "webui.subagents.v1"]
              : ["webui.core.v1"],
          },
        },
      });
      mockFetchRoutes({
        "/v0/sessions/websocket%3Achat-a/subagents": {
          tasks: [
            {
              task_id: "task-1",
              label: "Config check",
              task_description: "Inspect configuration",
              state: "running",
              phase: "awaiting_model",
              elapsed_seconds: 2,
              iteration: 1,
              tool_events: [],
              usage: null,
              receipts: {},
              result: null,
              partial: false,
              stop_reason: null,
              error: null,
              origin_turn_id: null,
              origin_message_id: null,
              created_at: 100,
              completed_at: null,
            },
          ],
        },
      });
      render(<App />);
      // Await the lazy module itself; cold Vite transformation is not the task
      // capability contract exercised by the timed DOM assertions below.
      await act(async () => {
        await import("@/components/thread/ThreadShell");
      });
      await screen.findByRole("textbox", {}, { timeout: 5_000 });
      if (supported) {
        const trigger = await screen.findByRole("button", {
          name: "Subtasks · Running: 1",
        });
        expect(trigger).toHaveAttribute("aria-expanded", "false");
        await userEvent.setup().click(trigger);
        expect(
          await screen.findByRole("button", { name: /Config check Running/ }),
        ).toBeVisible();
      } else
        expect(
          screen.queryByRole("button", { name: /Subtasks/ }),
        ).not.toBeInTheDocument();
      const reads = vi
        .mocked(fetch)
        .mock.calls.filter(([url]) => String(url).endsWith("/subagents"));
      expect(reads).toHaveLength(supported ? 1 : 0);
      expect(requestMutationSpy).not.toHaveBeenCalled();
    },
  );

  it("opens the full Models settings directly from the first-run prompt", async () => {
    const user = userEvent.setup();
    const base = baseSettingsPayload();
    mockFetchRoutes({
      "/v0/settings": {
        ...base,
        agent: {
          ...base.agent,
          model: "",
          resolved_provider: "",
          has_api_key: false,
          model_preset: "",
        },
        model_presets: [],
        model_call_order: [],
      },
    });

    render(<App />);

    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    await user.click(
      await screen.findByRole("button", { name: "Choose model" }),
    );

    expect(
      await screen.findByRole("navigation", { name: "Settings sections" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Models" }),
    ).toBeInTheDocument();
    await user.click(within(screen.getByRole("navigation", { name: "Settings sections" })).getByRole("button", { name: "Providers" }));
    expect(
      screen.getByRole("region", { name: "Providers" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Add provider" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("dialog", { name: "Choose model" }),
    ).not.toBeInTheDocument();
  });
});
